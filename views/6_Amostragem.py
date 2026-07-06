import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import html
import unicodedata

from core.settings import tem_acesso_modulo
from shared.database import DatabaseManager

st.set_page_config(page_title="Amostragem", page_icon="", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar esta ferramenta.")
    st.stop()

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()


REGRAS_AMOSTRAGEM = {
    "IMPLANTE": {"tipo": "todas"},
    "PROTESE": {"tipo": "todas"},
    "PROTESE ESPECIAL": {"tipo": "todas"},
    "CIRURGIA": {"tipo": "percentual", "pct": 0.30, "minimo_procs": 10},
    "PERIODONTIA": {"tipo": "percentual", "pct": 0.30, "minimo_procs": 10},
    "ENDODONTIA": {"tipo": "percentual", "pct": 0.50, "minimo_procs": 10},
}

ORDEM_CRITICAS = [
    "IMPLANTE",
    "PROTESE",
    "PROTESE ESPECIAL",
    "CIRURGIA",
    "PERIODONTIA",
    "ENDODONTIA",
]

# Procedimentos "não-críticos" por especialidade — os mais recorrentes/baratos
# que passam pelo sorteio de amostragem normal. Guias que contêm QUALQUER
# procedimento fora desta lista são consideradas importantes e entram na
# amostra automaticamente.
#
# Motivação: certos procedimentos são raros e/ou custosos e não podem cair
# fora da amostra por acaso do sorteio (ex.: exodontia de incluso na
# CIRURGIA). Deixá-los "sempre auditar" garante cobertura.
PROCS_NAO_CRITICOS = {
    "CIRURGIA": {"5010", "5030", "5031"},
}


def _norm(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("ASCII")
    return sem_acento.strip().upper()


# Sinônimos aceitos pra cada campo lógico. Novos formatos do PowerBI podem
# adicionar/renomear colunas — cadastrar aqui em vez de mexer no parser.
SINONIMOS_COLUNAS = {
    "especialidade": {"ESPECIALIDADE", "DS_GRUPO", "GRUPO"},
    "cd_procedimento": {"CD_PROCEDIMENTO", "CD PROCEDIMENTO", "PROCEDIMENTO", "COD_PROCEDIMENTO"},
    "nu_guia": {"NU_GUIA", "NU GUIA", "GUIA", "NUMERO_GUIA"},
    "liberacao": {"LIBERACAO", "LIBERACÃO", "LIBERAÇÃO"},
    "qtde": {"QTDE_ITENS", "QTDE ITENS", "QTDE", "QUANTIDADE", "QUANTIDADE_ITENS"},
}
CAMPOS_OBRIGATORIOS = ("especialidade", "cd_procedimento", "nu_guia", "qtde")


def _detectar_colunas(partes: list) -> dict:
    """Dado um cabeçalho (lista de células), retorna {campo_logico: indice}.

    Só reconhece a linha como header se conseguir mapear todos os campos
    obrigatórios — evita falso-positivo em linhas de dados que por acaso
    tenham "5010" ou similar.
    """
    mapa = {}
    for i, celula in enumerate(partes):
        norm = _norm(celula)
        for campo, sinonimos in SINONIMOS_COLUNAS.items():
            if norm in sinonimos:
                mapa.setdefault(campo, i)
                break
    if all(k in mapa for k in CAMPOS_OBRIGATORIOS):
        return mapa
    return {}


def parse_powerbi(texto: str) -> pd.DataFrame:
    """Parse texto colado do PowerBI (TSV).

    Detecta as colunas pelo cabeçalho (aceita sinônimos: Especialidade /
    DS_GRUPO, etc.). Se não houver cabeçalho, cai num fallback por número
    de colunas: 5 = formato legado, 6 = formato novo (com CRITICIDADE na
    frente). Linhas com NU_GUIA vazio são descartadas.
    """
    linhas = [l for l in texto.splitlines() if l.strip()]
    if not linhas:
        return pd.DataFrame()

    # 1. Procura cabeçalho nas primeiras 5 linhas.
    mapa_cols = {}
    dados_inicio = 0
    for i, linha in enumerate(linhas[:5]):
        candidato = _detectar_colunas(linha.split("\t"))
        if candidato:
            mapa_cols = candidato
            dados_inicio = i + 1
            break

    # 2. Fallback: sem cabeçalho, infere pelo número de colunas da 1ª linha.
    if not mapa_cols:
        n_cols = len(linhas[0].split("\t"))
        if n_cols == 5:
            # Legado: Especialidade, CD, Guia, Liberacao, Qtde
            mapa_cols = {"especialidade": 0, "cd_procedimento": 1, "nu_guia": 2, "liberacao": 3, "qtde": 4}
        elif n_cols == 6:
            # Novo: Criticidade, DS_GRUPO, CD, Guia, Liberacao, Qtde
            mapa_cols = {"especialidade": 1, "cd_procedimento": 2, "nu_guia": 3, "liberacao": 4, "qtde": 5}
        else:
            return pd.DataFrame()

    idx_esp = mapa_cols["especialidade"]
    idx_cd = mapa_cols["cd_procedimento"]
    idx_guia = mapa_cols["nu_guia"]
    idx_qtde = mapa_cols["qtde"]
    idx_lib = mapa_cols.get("liberacao")
    max_idx = max(mapa_cols.values())

    registros = []
    for linha in linhas[dados_inicio:]:
        partes = linha.split("\t")
        if len(partes) <= max_idx:
            continue
        especialidade = partes[idx_esp].strip()
        cd_proc = partes[idx_cd].strip()
        nu_guia = partes[idx_guia].strip()
        liberacao = partes[idx_lib].strip() if idx_lib is not None else ""
        qtde_bruta = partes[idx_qtde].strip()

        if not especialidade or not cd_proc or not nu_guia:
            continue
        try:
            qtde = int(qtde_bruta)
        except ValueError:
            continue

        registros.append({
            "Especialidade": especialidade,
            "CD_PROCEDIMENTO": cd_proc,
            "NU_GUIA": nu_guia,
            "LIBERACAO": liberacao,
            "Qtde": qtde,
        })
    return pd.DataFrame(registros)


def consolidar_por_guia(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa por (Especialidade, NU_GUIA), juntando procedimentos."""
    if df.empty:
        return df
    return (
        df.groupby(["Especialidade", "NU_GUIA"], sort=False)
        .agg(
            Procedimentos=("CD_PROCEDIMENTO", lambda s: ", ".join(sorted(set(s)))),
            Qtde_procs=("Qtde", "sum"),
        )
        .reset_index()
    )


def calcular_amostra(especialidade: str, total_procs: int, total_guias: int):
    """Retorna (n_amostra, descricao_da_regra)."""
    regra = REGRAS_AMOSTRAGEM.get(_norm(especialidade))
    if not regra:
        return total_guias, "Não-crítica — sem regra de amostragem"
    if regra["tipo"] == "todas":
        return total_guias, "Crítica integral — auditar todas"
    if regra["tipo"] == "percentual":
        if total_procs < regra["minimo_procs"]:
            return total_guias, f"Menos de {regra['minimo_procs']} procs — auditar todas"
        n = max(1, round(total_guias * regra["pct"]))
        pct = int(regra["pct"] * 100)
        return n, f"{pct}% das guias — auditar {n} de {total_guias}"
    return total_guias, ""


def sortear_amostra(df_guias: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    if n >= len(df_guias):
        return df_guias.copy()
    return df_guias.sample(n=n, random_state=seed).sort_index()


def _guia_tem_proc_critico(procs_str: str, procs_nao_criticos: set) -> bool:
    """True se a guia contém pelo menos um procedimento fora da lista
    de não-críticos (procs que ficam sujeitos ao sorteio)."""
    procs = {p.strip() for p in procs_str.split(",") if p.strip()}
    return bool(procs - procs_nao_criticos)


def marcar_amostra(df_esp_guias: pd.DataFrame, especialidade: str,
                   df_esp_procs_brutos: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Retorna DataFrame de guias com a amostra sugerida.

    Fluxo:
      1. Aplica a regra da especialidade sobre o TOTAL de procs (não separa
         por critério de criticidade nesse passo). Se cai em 'auditar todas'
         (integral, ou < mínimo de procs), retorna tudo.
      2. Caso contrário, o tamanho da amostra = % das guias da especialidade
         (ex.: 30% pra CIRURGIA). Dentro desse tamanho, prioriza guias com
         procs críticos:
           - Se guias críticas ≤ 5: entram todas + completa com sorteio das
             normais até bater o tamanho da amostra.
           - Se guias críticas > 5: 50% da amostra vira crítica sorteada +
             50% vira normal sorteada.

    Coluna 'Motivo' é mantida por compatibilidade (dropada antes de renderizar).
    """
    if df_esp_guias.empty:
        return df_esp_guias.assign(Motivo=[])

    n_total_guias = len(df_esp_guias)
    total_procs_esp = int(df_esp_procs_brutos["Qtde"].sum())
    procs_nao_criticos = PROCS_NAO_CRITICOS.get(_norm(especialidade))
    regra = REGRAS_AMOSTRAGEM.get(_norm(especialidade), {})

    # Caminho 1: sem lista de críticos OU regra que manda auditar tudo.
    def _todas(motivo=""):
        amostra = df_esp_guias.copy()
        amostra["Motivo"] = motivo
        return amostra

    if procs_nao_criticos is None or not regra:
        n, _ = calcular_amostra(especialidade, total_procs_esp, n_total_guias)
        amostra = sortear_amostra(df_esp_guias, n, seed=seed).copy()
        amostra["Motivo"] = ""
        return amostra

    if regra.get("tipo") == "todas":
        return _todas("")

    if regra.get("tipo") == "percentual":
        # Gatilho <N procs = auditar todas — avaliado sobre o TOTAL da
        # especialidade, sem separar críticas de normais.
        if total_procs_esp < regra["minimo_procs"]:
            return _todas("")

        pct = regra["pct"]
        tamanho_amostra = max(1, round(n_total_guias * pct))

        df = df_esp_guias.copy()
        df["_critica"] = df["Procedimentos"].apply(
            lambda p: _guia_tem_proc_critico(p, procs_nao_criticos)
        )
        df_criticas = df[df["_critica"]].drop(columns=["_critica"]).copy()
        df_normais = df[~df["_critica"]].drop(columns=["_critica"]).copy()
        n_crit = len(df_criticas)
        n_norm = len(df_normais)

        if n_crit <= 5:
            # Todas as críticas entram (limitadas ao tamanho da amostra) e o
            # restante da amostra é preenchido com sorteio das normais.
            n_crit_amostra = min(n_crit, tamanho_amostra)
            n_norm_amostra = min(tamanho_amostra - n_crit_amostra, n_norm)
            df_criticas_final = df_criticas
        else:
            # Composição 50/50 dentro da amostra.
            n_crit_amostra = min(tamanho_amostra // 2, n_crit)
            n_norm_amostra = min(tamanho_amostra - n_crit_amostra, n_norm)
            df_criticas_final = sortear_amostra(df_criticas, n_crit_amostra, seed=seed)

        df_normais_final = sortear_amostra(df_normais, n_norm_amostra, seed=seed)

        df_criticas_final = df_criticas_final.copy()
        df_criticas_final["Motivo"] = ""
        df_normais_final = df_normais_final.copy()
        df_normais_final["Motivo"] = ""
        return pd.concat([df_criticas_final, df_normais_final], ignore_index=True)

    return _todas("")


def renderizar_tabela_guias(df_guias: pd.DataFrame, titulo_descritivo: str, objetivo: int):
    """Renderiza tabela HTML com NU_GUIA como botão clicável (copia ao clicar).

    `objetivo` é o tamanho de amostra requerido pela regra da especialidade
    (mostrado como denominador do contador).
    """
    mostrar_motivo = "Motivo" in df_guias.columns
    linhas_html = []
    for _, row in df_guias.iterrows():
        guia = html.escape(str(row["NU_GUIA"]))
        procs = html.escape(str(row["Procedimentos"]))
        qtde = int(row["Qtde_procs"])
        motivo_html = ""
        if mostrar_motivo:
            motivo = html.escape(str(row.get("Motivo", "")))
            classe = "motivo-critica" if "crítica" in motivo.lower() or "critica" in motivo.lower() else "motivo-sorteio"
            motivo_html = f"<td class='{classe}'>{motivo}</td>"
        linhas_html.append(
            f"<tr>"
            f"<td><button class='copy-btn' data-val='{guia}' title='Clique para copiar'>{guia}</button></td>"
            f"<td>{procs}</td>"
            f"<td style='text-align:right'>{qtde}</td>"
            f"{motivo_html}"
            f"</tr>"
        )
    rows = "\n".join(linhas_html)
    th_motivo = "<th style='width: 18%'>Motivo</th>" if mostrar_motivo else ""

    html_tabela = f"""
    <style>
        body {{ color: #1f2937; background: transparent; margin: 0; }}
        .pbi-wrap {{ font-family: 'Source Sans Pro', sans-serif; color: inherit; }}
        .pbi-table {{ width: 100%; border-collapse: collapse; font-size: 14px; color: inherit; }}
        .pbi-table th, .pbi-table td {{
            padding: 7px 10px; text-align: left;
            border-bottom: 1px solid rgba(125,125,125,0.25);
            color: inherit;
        }}
        .pbi-table th {{
            background: #f0f2f6; font-weight: 600;
            position: sticky; top: 0; z-index: 1;
            box-shadow: 0 1px 0 rgba(125,125,125,0.35);
        }}
        .copy-btn {{
            background: transparent;
            border: 1px solid rgba(125,125,125,0.5);
            border-radius: 4px;
            padding: 3px 10px;
            cursor: pointer;
            font-family: ui-monospace, 'Cascadia Mono', Menlo, monospace;
            font-size: 13px;
            color: inherit;
        }}
        .copy-btn:hover {{ background: rgba(125,125,125,0.15); border-color: rgba(125,125,125,0.8); }}
        .copy-btn.vista {{
            background: rgba(46, 125, 50, 0.18);
            border-color: rgba(76, 175, 80, 0.65);
        }}
        .copy-btn.vista:hover {{ background: rgba(46, 125, 50, 0.32); }}
        .copy-btn.copied {{ background: #2e7d32; color: #fff; border-color: #43a047; }}
        .pbi-counter {{
            font-size: 12.5px;
            color: rgba(120,120,120,0.95);
            margin: 0 0 8px 2px;
            font-family: 'Source Sans Pro', sans-serif;
        }}
        .pbi-counter strong {{ color: rgba(76, 175, 80, 1); font-weight: 600; }}
        .pbi-counter.atingido strong {{ color: rgba(46, 125, 50, 1); }}
        .pbi-counter.atingido::after {{ content: ' ✓'; color: rgba(46, 125, 50, 1); font-weight: 600; }}
        .motivo-critica {{ color: #b45309; font-weight: 600; font-size: 12.5px; }}
        .motivo-sorteio {{ color: rgba(120,120,120,0.85); font-size: 12.5px; }}

        @media (prefers-color-scheme: dark) {{
            body {{ color: #e6ecf5; }}
            .pbi-table th {{ background: #1c2230; box-shadow: 0 1px 0 rgba(255,255,255,0.15); }}
            .copy-btn {{ border-color: rgba(255,255,255,0.25); }}
            .copy-btn:hover {{ background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.5); }}
            .copy-btn.vista {{
                background: rgba(76, 175, 80, 0.22);
                border-color: rgba(102, 187, 106, 0.75);
            }}
            .copy-btn.vista:hover {{ background: rgba(76, 175, 80, 0.4); }}
            .motivo-critica {{ color: #fbbf24; }}
            .motivo-sorteio {{ color: rgba(255,255,255,0.55); }}
        }}
    </style>
    <div class='pbi-wrap'>
        <div class='pbi-counter'><strong>0</strong> de {objetivo} analisado(s)</div>
        <table class='pbi-table'>
            <thead>
                <tr><th style='width: 30%'>NU_GUIA</th><th>Procedimentos</th><th style='width: 10%; text-align:right'>Qtde</th>{th_motivo}</tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    <script>
        const PREFIX = 'amostragem_guia_vista_';

        const OBJETIVO = {objetivo};
        function atualizarContador() {{
            const vistos = document.querySelectorAll('.copy-btn.vista').length;
            const c = document.querySelector('.pbi-counter');
            if (!c) return;
            c.innerHTML = '<strong>' + vistos + '</strong> de ' + OBJETIVO + ' analisado(s)';
            if (vistos >= OBJETIVO) c.classList.add('atingido');
            else c.classList.remove('atingido');
        }}

        function aplicarEstadoVistas() {{
            document.querySelectorAll('.copy-btn').forEach(btn => {{
                const val = btn.getAttribute('data-val');
                if (localStorage.getItem(PREFIX + val) === '1') {{
                    btn.classList.add('vista');
                }}
            }});
            atualizarContador();
        }}

        aplicarEstadoVistas();

        // Sincroniza entre os dois iframes (tabela completa e amostra) na mesma janela
        window.addEventListener('storage', (e) => {{
            if (e.key && e.key.startsWith(PREFIX)) aplicarEstadoVistas();
        }});
        setInterval(aplicarEstadoVistas, 1500);

        document.querySelectorAll('.copy-btn').forEach(btn => {{
            btn.addEventListener('click', () => {{
                const val = btn.getAttribute('data-val');
                navigator.clipboard.writeText(val).then(() => {{
                    localStorage.setItem(PREFIX + val, '1');
                    btn.classList.add('vista');
                    atualizarContador();
                    const orig = btn.innerText;
                    btn.innerText = '✓ ' + val;
                    btn.classList.add('copied');
                    setTimeout(() => {{
                        btn.innerText = orig;
                        btn.classList.remove('copied');
                    }}, 1100);
                }});
            }});
        }});
    </script>
    """
    altura = 82 + 36 * max(1, len(df_guias))
    components.html(html_tabela, height=min(altura, 540), scrolling=True)


# --------------------------------------------------------------------- UI ----

st.title("Amostragem de Guias")
st.markdown(
    "Cole o texto da seleção do PowerBI (**Liberação de IA por procedimento**) abaixo. "
    "O app deduplica as guias por especialidade e sugere a amostra a auditar."
)

_is_admin = st.session_state.get("role_interno") == "Admin"

# Versão da key do text_area: usada para "resetar" o widget no clique do Limpar
# (Streamlit não limpa widget só removendo do session_state após render).
if "texto_powerbi_v" not in st.session_state:
    st.session_state["texto_powerbi_v"] = 0
# Seed da amostra. Cliques no "Gerar amostra" geram um novo seed aleatório.
if "seed_amostra" not in st.session_state:
    st.session_state["seed_amostra"] = 42

texto = st.text_area(
    "Texto copiado do PowerBI",
    height=200,
    key=f"texto_powerbi_v{st.session_state['texto_powerbi_v']}",
    placeholder=(
        "CRITICIDADE\tDS_GRUPO\tCD_PROCEDIMENTO\tNU_GUIA\tLIBERAÇÃO\tQtde itens\n"
        "SIM\tCIRURGIA\t5010\t26996546\tS\t1\n"
        "SIM\tCIRURGIA\t5030\t27294440\tS\t1\n..."
    ),
)

if _is_admin:
    col_limpar, col_gerar, col_seed, _ = st.columns([1, 1, 1, 2])
    with col_limpar:
        limpar = st.button("Limpar", use_container_width=True)
    with col_gerar:
        gerar_amostra = st.button("Gerar amostra", use_container_width=True)
    with col_seed:
        seed = st.number_input(
            "Seed do sorteio",
            min_value=0,
            max_value=9999,
            value=int(st.session_state["seed_amostra"]),
            step=1,
            help="Trocar o seed gera outra amostra aleatória.",
        )
        st.session_state["seed_amostra"] = int(seed)
else:
    col_limpar, col_gerar, _ = st.columns([1, 1, 3])
    with col_limpar:
        limpar = st.button("Limpar", use_container_width=True)
    with col_gerar:
        gerar_amostra = st.button("Gerar amostra", use_container_width=True)
    seed = int(st.session_state["seed_amostra"])

if limpar:
    st.session_state["texto_powerbi_v"] += 1
    st.session_state["limpar_marcas_pendente"] = True
    st.rerun()

if st.session_state.pop("limpar_marcas_pendente", False):
    components.html(
        "<script>"
        "Object.keys(localStorage).filter(k => k.startsWith('amostragem_guia_vista_'))"
        ".forEach(k => localStorage.removeItem(k));"
        "</script>",
        height=0,
    )

if gerar_amostra:
    import random
    novo = random.randint(0, 9999)
    if novo == int(st.session_state["seed_amostra"]):
        novo = (novo + 1) % 10000
    st.session_state["seed_amostra"] = novo
    st.rerun()

if not texto.strip():
    st.info("Cole o texto e o resultado aparece aqui.")
    st.stop()

df = parse_powerbi(texto)

if df.empty:
    st.warning(
        "Nenhuma linha válida encontrada. Esperado: TSV com colunas "
        "(DS_GRUPO ou Especialidade), CD_PROCEDIMENTO, NU_GUIA, LIBERAÇÃO, Qtde itens. "
        "O cabeçalho pode vir junto ou não. Linhas com NU_GUIA vazio são ignoradas."
    )
    st.stop()

df_guias = consolidar_por_guia(df)

especialidades = df_guias["Especialidade"].unique().tolist()
especialidades.sort(
    key=lambda e: (
        ORDEM_CRITICAS.index(_norm(e)) if _norm(e) in ORDEM_CRITICAS else 999,
        _norm(e),
    )
)

# --- Resumo ---
resumo = []
for esp in especialidades:
    df_esp_total = df[df["Especialidade"] == esp]
    df_esp_guias = df_guias[df_guias["Especialidade"] == esp].reset_index(drop=True)
    total_procs = int(df_esp_total["Qtde"].sum())
    total_guias = len(df_esp_guias)
    df_amostra_resumo = marcar_amostra(df_esp_guias, esp, df_esp_total, seed=int(seed))
    resumo.append({
        "Especialidade": esp,
        "Guias únicas": total_guias,
        "Total de procs": total_procs,
        "Amostra sugerida": len(df_amostra_resumo),
    })

st.markdown("### Resumo")
st.dataframe(pd.DataFrame(resumo), use_container_width=True, hide_index=True)

# --- Detalhamento ---
st.markdown("### Detalhamento por especialidade")
st.caption("Clique no número da guia para copiar.")

for esp in especialidades:
    df_esp_total = df[df["Especialidade"] == esp]
    df_esp_guias = df_guias[df_guias["Especialidade"] == esp].reset_index(drop=True)
    total_procs = int(df_esp_total["Qtde"].sum())
    total_guias = len(df_esp_guias)

    df_amostra = marcar_amostra(df_esp_guias, esp, df_esp_total, seed=int(seed))
    n_objetivo = len(df_amostra)

    st.markdown(f"#### {esp}")
    st.caption(f"{total_guias} guia(s), {total_procs} proc(s)")

    with st.expander(f"Tabela completa — {total_guias} guia(s)", expanded=True):
        renderizar_tabela_guias(df_esp_guias, esp, objetivo=n_objetivo)

    with st.expander(f"Sugestão de amostra — {n_objetivo} guia(s)", expanded=True):
        renderizar_tabela_guias(
            df_amostra.drop(columns=["Motivo"], errors="ignore"),
            esp,
            objetivo=n_objetivo,
        )
