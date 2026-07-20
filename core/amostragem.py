import html
import unicodedata

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


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


def selecionar_procedimentos_ignorados(df: pd.DataFrame, db, key_prefix: str) -> set:
    """Renderiza o multiselect "Ignorar procedimentos nesta análise" + botão
    para salvar a seleção como padrão (por especialidade, persistido em
    amostragem_procs_ignorados). A seleção salva vira default automático nas
    próximas análises, mas pode ser ajustada só-nesta-sessão sem salvar.

    `key_prefix` deve variar por dataset (ex.: versão do texto colado, ou o
    processo buscado) para o multiselect resetar corretamente ao trocar de
    entrada — mesmo padrão já usado no key do texto/processo.

    Retorna o set de códigos selecionados AGORA (salvos ou não), pronto para
    filtrar o `df`.
    """
    from services.relatorio_5302.glosa_matcher import carregar_mapa_procedimentos

    mapa_procedimentos = carregar_mapa_procedimentos()

    # Primeira especialidade em que cada código aparece neste dataset —
    # usado pra saber em qual especialidade salvar/remover o código.
    cod_para_especialidade = {}
    for _, row in df[["CD_PROCEDIMENTO", "Especialidade"]].drop_duplicates().iterrows():
        cod_para_especialidade.setdefault(row["CD_PROCEDIMENTO"], row["Especialidade"])

    codigos_presentes = sorted(cod_para_especialidade.keys())
    opcoes = {
        f"{cod} - {mapa_procedimentos.get(cod, 'descrição não encontrada')}": cod
        for cod in codigos_presentes
    }

    salvos = db.carregar_procs_ignorados()  # {especialidade: set(codigos)}
    default_labels = [
        lbl for lbl, cod in opcoes.items()
        if cod in salvos.get(cod_para_especialidade[cod], set())
    ]

    col_multi, col_salvar = st.columns([5, 1.2])
    with col_multi:
        labels_selecionados = st.multiselect(
            "Ignorar procedimentos nesta análise",
            options=sorted(opcoes.keys()),
            default=default_labels,
            key=f"{key_prefix}_procs_ignorados",
            help=(
                "Selecionados aqui não entram na contagem nem no sorteio. "
                "Clique em \"Salvar como padrão\" para aplicar automaticamente "
                "nas próximas análises, sem precisar marcar de novo."
            ),
        )
    codigos_selecionados = {opcoes[lbl] for lbl in labels_selecionados}

    with col_salvar:
        st.write("")
        if st.button("Salvar como padrão", key=f"{key_prefix}_salvar_procs", use_container_width=True):
            pares_para_salvar = [
                (cod_para_especialidade[cod], cod)
                for cod in codigos_selecionados
                if cod not in salvos.get(cod_para_especialidade[cod], set())
            ]
            pares_para_remover = [
                (esp, cod)
                for cod, esp in cod_para_especialidade.items()
                if cod in salvos.get(esp, set()) and cod not in codigos_selecionados
            ]
            ok = True
            if pares_para_salvar:
                ok = ok and db.salvar_procs_ignorados(pares_para_salvar)
            if pares_para_remover:
                ok = ok and db.remover_procs_ignorados(pares_para_remover)
            if ok:
                st.toast("Padrão salvo — aplicado automaticamente nas próximas análises.")
            else:
                st.error("Erro ao salvar o padrão.")

    return codigos_selecionados


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


def renderizar_tabela_guias(df_guias: pd.DataFrame, titulo_descritivo: str, objetivo: int,
                             guias_vistas: set = frozenset()):
    """Renderiza tabela HTML com NU_GUIA como botão clicável (copia ao clicar).

    `objetivo` é o tamanho de amostra requerido pela regra da especialidade
    (mostrado como denominador do contador).

    `guias_vistas`: NU_GUIA já marcados como auditados (vindos do Supabase —
    compartilhado entre qualquer um que abrir a mesma guia depois). Ao clicar,
    a marcação é gravada direto do navegador na tabela
    amostragem_guias_vistas (chave publicável do Supabase, sem vínculo a
    usuário por enquanto).
    """
    supabase_url = st.secrets["supabase"]["url"].rstrip("/")
    supabase_key = st.secrets["supabase"]["key"]

    mostrar_motivo = "Motivo" in df_guias.columns
    linhas_html = []
    for _, row in df_guias.iterrows():
        guia = html.escape(str(row["NU_GUIA"]))
        procs = html.escape(str(row["Procedimentos"]))
        qtde = int(row["Qtde_procs"])
        classe_vista = " vista" if str(row["NU_GUIA"]) in guias_vistas else ""
        motivo_html = ""
        if mostrar_motivo:
            motivo = html.escape(str(row.get("Motivo", "")))
            classe = "motivo-critica" if "crítica" in motivo.lower() or "critica" in motivo.lower() else "motivo-sorteio"
            motivo_html = f"<td class='{classe}'>{motivo}</td>"
        linhas_html.append(
            f"<tr>"
            f"<td><button class='copy-btn{classe_vista}' data-val='{guia}' title='Clique para copiar'>{guia}</button></td>"
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
        const SUPABASE_URL = '{supabase_url}';
        const SUPABASE_KEY = '{supabase_key}';

        function marcarVistaNoServidor(nu_guia) {{
            fetch(`${{SUPABASE_URL}}/rest/v1/amostragem_guias_vistas`, {{
                method: 'POST',
                headers: {{
                    'apikey': SUPABASE_KEY,
                    'Authorization': `Bearer ${{SUPABASE_KEY}}`,
                    'Content-Type': 'application/json',
                    'Prefer': 'resolution=merge-duplicates,return=minimal',
                }},
                body: JSON.stringify({{ nu_guia: nu_guia }}),
            }}).catch(() => {{}});
        }}

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
                    marcarVistaNoServidor(val);
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
