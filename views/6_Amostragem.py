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


def _norm(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("ASCII")
    return sem_acento.strip().upper()


def parse_powerbi(texto: str) -> pd.DataFrame:
    """Parse texto colado do PowerBI (TSV, 5 colunas).

    Espera as colunas: Especialidade, CD_PROCEDIMENTO, NU_GUIA, LIBERACAO, Qtde.
    Linhas com NU_GUIA vazio são descartadas (procedimentos sem guia não
    auditáveis individualmente). Cabeçalho é detectado e ignorado.
    """
    registros = []
    for linha in texto.splitlines():
        if not linha.strip():
            continue
        partes = linha.split("\t")
        if len(partes) < 5:
            continue
        especialidade = partes[0].strip()
        cd_proc = partes[1].strip()
        nu_guia = partes[2].strip()
        liberacao = partes[3].strip()
        qtde_bruta = partes[4].strip()

        if _norm(especialidade) == "ESPECIALIDADE":
            continue
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


def renderizar_tabela_guias(df_guias: pd.DataFrame, titulo_descritivo: str):
    """Renderiza tabela HTML com NU_GUIA como botão clicável (copia ao clicar)."""
    linhas_html = []
    for _, row in df_guias.iterrows():
        guia = html.escape(str(row["NU_GUIA"]))
        procs = html.escape(str(row["Procedimentos"]))
        qtde = int(row["Qtde_procs"])
        linhas_html.append(
            f"<tr>"
            f"<td><button class='copy-btn' data-val='{guia}' title='Clique para copiar'>{guia}</button></td>"
            f"<td>{procs}</td>"
            f"<td style='text-align:right'>{qtde}</td>"
            f"</tr>"
        )
    rows = "\n".join(linhas_html)

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
        }}
    </style>
    <div class='pbi-wrap'>
        <div class='pbi-counter'><strong>0</strong> de {len(df_guias)} analisado(s)</div>
        <table class='pbi-table'>
            <thead>
                <tr><th style='width: 30%'>NU_GUIA</th><th>Procedimentos</th><th style='width: 10%; text-align:right'>Qtde</th></tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    <script>
        const PREFIX = 'amostragem_guia_vista_';

        function atualizarContador() {{
            const total = document.querySelectorAll('.copy-btn').length;
            const vistos = document.querySelectorAll('.copy-btn.vista').length;
            const c = document.querySelector('.pbi-counter');
            if (c) c.innerHTML = '<strong>' + vistos + '</strong> de ' + total + ' analisado(s)';
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
        "Especialidade\tCD_PROCEDIMENTO\tNU_GUIA\tLIBERAÇÃO\tQtde itens\n"
        "ENDODONTIA\t2015\t27029804\tN\t1\n"
        "PROTESE\t4080\t26411962\tN\t1\n..."
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
        "Nenhuma linha válida encontrada. Esperado: 5 colunas separadas por TAB "
        "(Especialidade, CD_PROCEDIMENTO, NU_GUIA, LIBERAÇÃO, Qtde). "
        "Linhas com NU_GUIA vazio são ignoradas."
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
    df_esp_guias = df_guias[df_guias["Especialidade"] == esp]
    total_procs = int(df_esp_total["Qtde"].sum())
    total_guias = len(df_esp_guias)
    n_amostra, _ = calcular_amostra(esp, total_procs, total_guias)
    resumo.append({
        "Especialidade": esp,
        "Guias únicas": total_guias,
        "Total de procs": total_procs,
        "Amostra sugerida": n_amostra,
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
    n_amostra, _ = calcular_amostra(esp, total_procs, total_guias)
    df_amostra = sortear_amostra(df_esp_guias, n_amostra, seed=int(seed))

    st.markdown(f"#### {esp}")
    st.caption(f"{total_guias} guia(s), {total_procs} proc(s)")

    with st.expander(f"Tabela completa — {total_guias} guia(s)", expanded=True):
        renderizar_tabela_guias(df_esp_guias, esp)

    with st.expander(f"Sugestão de amostra — {len(df_amostra)} guia(s)", expanded=True):
        renderizar_tabela_guias(df_amostra, esp)
