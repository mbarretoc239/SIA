import altair as alt
import pandas as pd
import streamlit as st

from core.relatorio_5201 import (
    STATUS_CORES,
    STATUS_LABELS,
    carregar_dados_atuais,
    ler_relatorio_5201,
    montar_registros,
    produtividade_por_auditor,
    resumo_geral,
)
from shared.database import DatabaseManager

st.set_page_config(page_title="Produtividade", page_icon="", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar esta ferramenta.")
    st.stop()

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()

# Só Gestor (dono do processo) e Admin (fins de teste) acessam este painel —
# não é um módulo configurável em permissoes_modulos como os demais.
_ROLES_PRODUTIVIDADE = {"Gestor", "Admin"}
_role = st.session_state.get("role_interno", "Contas")
if _role not in _ROLES_PRODUTIVIDADE:
    st.error("Você não tem permissão para acessar este módulo.")
    st.stop()

st.title("Produtividade — Relatório 5201")
st.caption(
    "Suba o REL5201 do dia (mesmo arquivo baixado do sistema) para atualizar os números "
    "abaixo. Prestador, CPF/CNPJ e demais dados de negócio não são armazenados — só o "
    "necessário para status e produtividade, e mesmo assim de forma cifrada no banco."
)

with st.expander("Atualizar dados de hoje", expanded=False):
    arquivo = st.file_uploader("Relatório REL5201 (.xlsx ou .csv)", type=["xlsx", "csv"], key="upload_rel5201")
    if arquivo and st.button("Processar e substituir snapshot atual", type="primary"):
        try:
            with st.spinner("Lendo e importando o relatório..."):
                df_bruto = ler_relatorio_5201(arquivo)
                registros = montar_registros(df_bruto)
                total = st.session_state.db.importar_relatorio_5201(
                    registros, importado_por=st.session_state.get("usuario_id")
                )
            carregar_dados_atuais.clear()
            st.success(f"{total} processo(s) importado(s) com sucesso.")
            st.rerun()
        except Exception as erro:
            st.error(f"Falha na importação: {erro}")

df = carregar_dados_atuais()

if df.empty:
    st.info("Nenhum relatório importado ainda. Suba o REL5201 do dia acima.")
    st.stop()

if "_importado_em" in df.columns and df["_importado_em"].notna().any():
    ultima = pd.to_datetime(df["_importado_em"]).max()
    st.caption(f"Última atualização: {ultima.strftime('%d/%m/%Y %H:%M')}")

resumo = resumo_geral(df)
por_status = resumo["por_status"]

st.markdown("### Visão Geral")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total de processos", resumo["total_processos"])
c2.metric("Total de procedimentos", resumo["total_procedimentos"])
c3.metric("Fechados", por_status.get("FECHADO", 0))
c4.metric("Consistidos (em aberto)", por_status.get("CONSISTIDO", 0))
c5.metric("Glosados", por_status.get("GLOSADO", 0))

if por_status.get("CALCULADO"):
    st.caption(f"Calculados: {por_status.get('CALCULADO', 0)}")

df_status = pd.DataFrame([
    {"Status": STATUS_LABELS.get(status, status), "Processos": qtd, "_cor": STATUS_CORES.get(status, STATUS_CORES["_outro"])}
    for status, qtd in por_status.items()
])
grafico_status = alt.Chart(df_status).mark_bar(cornerRadiusEnd=4).encode(
    x=alt.X("Processos:Q"),
    y=alt.Y("Status:N", sort="-x", title=None),
    color=alt.Color("_cor:N", scale=None, legend=None),
    tooltip=["Status", "Processos"],
)
st.altair_chart(grafico_status, use_container_width=True)

st.divider()

st.markdown("### Produtividade por Auditor")
st.caption("Só conta processos em estado final (Fechado ou Calculado) — Consistido ainda está em aberto e não entra na contagem.")
tabela_auditores = produtividade_por_auditor(df)
if tabela_auditores.empty:
    st.info("Nenhum processo com auditor (consistência/fechamento) registrado neste snapshot.")
else:
    st.dataframe(tabela_auditores, use_container_width=True, hide_index=True)

    grafico_auditores = alt.Chart(tabela_auditores).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X("Total:Q", title="Processos concluídos (Fechado + Calculado)"),
        y=alt.Y("Auditor:N", sort="-x", title=None),
        color=alt.value("#4F8CFF"),
        tooltip=["Auditor", "Fechados", "Calculados", "Total", "Procedimentos"],
    )
    st.altair_chart(grafico_auditores, use_container_width=True)
