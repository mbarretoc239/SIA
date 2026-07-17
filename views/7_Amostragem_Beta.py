import io

import streamlit as st
import pandas as pd

from core.amostragem import (
    ORDEM_CRITICAS,
    _norm,
    consolidar_por_guia,
    marcar_amostra,
    renderizar_tabela_guias,
)

st.set_page_config(page_title="Amostragem BETA", page_icon="", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar esta ferramenta.")
    st.stop()


# Colunas mínimas esperadas na planilha mensal da base IA (mesma que alimenta
# o PowerBI). Nomes normalizados via _norm (maiúsculo, sem acento).
COLUNAS_NECESSARIAS = {"NU_ORDEM", "NU_GUIA", "CD_PROCEDIMENTO", "DS_GRUPO", "LIBERACAO"}

SEED_PADRAO = 42


@st.cache_data(show_spinner="Lendo planilha da base IA (pode levar alguns segundos, é um arquivo grande)...")
def _carregar_base_ia(arquivo_bytes: bytes, aba_preferida: str) -> pd.DataFrame:
    """Lê a planilha mensal exportada (mesma base que alimenta o PowerBI) e
    normaliza as colunas necessárias para busca por processo."""
    excel = pd.ExcelFile(io.BytesIO(arquivo_bytes))
    aba = aba_preferida if aba_preferida in excel.sheet_names else excel.sheet_names[0]
    df = excel.parse(aba)
    df.columns = [_norm(str(c)) for c in df.columns]

    faltantes = COLUNAS_NECESSARIAS - set(df.columns)
    if faltantes:
        raise ValueError(
            "Colunas não encontradas na planilha (aba '" + aba + "'): "
            + ", ".join(sorted(faltantes))
        )

    df["NU_ORDEM"] = pd.to_numeric(df["NU_ORDEM"], errors="coerce").astype("Int64").astype(str)
    df["NU_GUIA"] = df["NU_GUIA"].astype(str).str.strip()
    df["CD_PROCEDIMENTO"] = df["CD_PROCEDIMENTO"].astype(str).str.strip()
    df["DS_GRUPO"] = df["DS_GRUPO"].astype(str).str.strip()
    df["LIBERACAO"] = df["LIBERACAO"].astype(str).str.strip().str.upper()
    return df[list(COLUNAS_NECESSARIAS)]


def _guias_do_processo(df_base: pd.DataFrame, processo: str) -> pd.DataFrame:
    """Filtra a base pelo processo, só guias NÃO liberadas pela IA
    (LIBERACAO == 'N'), no mesmo formato que parse_powerbi() produz —
    assim o resto do pipeline (consolidar_por_guia, marcar_amostra) não
    precisa mudar nada."""
    processo = processo.strip()
    sub = df_base[(df_base["NU_ORDEM"] == processo) & (df_base["LIBERACAO"] == "N")]
    if sub.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "Especialidade": sub["DS_GRUPO"].values,
        "CD_PROCEDIMENTO": sub["CD_PROCEDIMENTO"].values,
        "NU_GUIA": sub["NU_GUIA"].values,
        "Qtde": 1,
    })


# --------------------------------------------------------------------- UI ----

st.title("Amostragem de Guias (BETA)")
st.caption(
    "Sobe a planilha mensal da base IA (a mesma que alimenta o PowerBI) e "
    "digita o número do processo — as guias com LIBERAÇÃO = N são buscadas "
    "automaticamente e a amostra é gerada igual ao fluxo atual. Prestador e "
    "percentuais continuam só no PowerBI; aqui entra apenas processo e guias."
)

arquivo = st.file_uploader(
    "Planilha mensal da base IA (.xlsx)",
    type=["xlsx"],
    help="Arquivo com as colunas NU_ORDEM, NU_GUIA, CD_PROCEDIMENTO, DS_GRUPO e LIBERAÇÃO.",
)

if not arquivo:
    st.info("Envie a planilha do mês para começar.")
    st.stop()

try:
    df_base = _carregar_base_ia(arquivo.getvalue(), "Planilha1")
except ValueError as erro:
    st.error(str(erro))
    st.stop()

n_processos = df_base["NU_ORDEM"].nunique()
st.caption(f"{len(df_base):,} linha(s) carregada(s) — {n_processos:,} processo(s) único(s).".replace(",", "."))

col_processo, col_buscar = st.columns([3, 1])
with col_processo:
    processo_digitado = st.text_input("Número do processo", placeholder="Ex: 8202650447")
with col_buscar:
    st.write("")
    buscar = st.button("Buscar guias", use_container_width=True)

if buscar:
    st.session_state["_amostragem_beta_processo"] = processo_digitado.strip()

processo_ativo = st.session_state.get("_amostragem_beta_processo", "")

if not processo_ativo:
    st.info("Digite o número do processo e clique em Buscar guias.")
    st.stop()

df = _guias_do_processo(df_base, processo_ativo)

if df.empty:
    st.warning(
        f"Nenhuma guia com LIBERAÇÃO = N encontrada para o processo "
        f"'{processo_ativo}' nesta planilha. Confira o número ou se o "
        f"processo está no mês certo."
    )
    st.stop()

st.success(f"Processo {processo_ativo}: {len(df)} item(ns) com LIBERAÇÃO = N.")

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
    df_amostra_resumo = marcar_amostra(df_esp_guias, esp, df_esp_total, seed=SEED_PADRAO)
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

    df_amostra = marcar_amostra(df_esp_guias, esp, df_esp_total, seed=SEED_PADRAO)
    n_objetivo = len(df_amostra)

    st.markdown(f"#### {esp}")
    st.caption(f"{total_guias} guia(s), {total_procs} proc(s)")

    with st.expander(f"Tabela completa — {total_guias} guia(s)", expanded=False):
        renderizar_tabela_guias(df_esp_guias, esp, objetivo=n_objetivo)

    with st.expander(f"Sugestão de amostra — {n_objetivo} guia(s)", expanded=False):
        renderizar_tabela_guias(
            df_amostra.drop(columns=["Motivo"], errors="ignore"),
            esp,
            objetivo=n_objetivo,
        )
