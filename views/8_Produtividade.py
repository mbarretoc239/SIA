from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from core.relatorio_5201 import (
    STATUS_CORES,
    STATUS_LABELS,
    carregar_dados_atuais,
    dias_disponiveis,
    ler_relatorio_5201,
    meses_disponiveis,
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

_ROLES_GERAL = {"Gestor", "Admin"}
_role = st.session_state.get("role_interno", "Contas")
_ve_geral = _role in _ROLES_GERAL
_usuario_sigo = st.session_state.get("usuario_sigo", "")

st.title("Produtividade — Relatório 5201")

if _ve_geral:
    st.caption(
        "Suba o REL5201 (mesmo arquivo baixado do sistema) para atualizar os números "
        "abaixo, informando a qual mês ele se refere. Prestador, CPF/CNPJ e demais dados "
        "de negócio não são armazenados — só o necessário para status e produtividade, "
        "e mesmo assim de forma cifrada no banco."
    )

    with st.expander("Atualizar dados", expanded=False):
        mes_upload = st.date_input(
            "Mês de referência deste arquivo",
            value=date.today().replace(day=1),
            help="Normalmente é o mês atual. Mude aqui se estiver subindo o arquivo de um mês anterior — "
            "isso NÃO sobrescreve outros meses já importados, só substitui os dados desse mês específico. "
            "Só os 2 meses mais recentes ficam guardados; o mais antigo é descartado ao entrar um novo.",
        )
        mes_referencia_upload = mes_upload.strftime("%Y-%m")
        arquivo = st.file_uploader("Relatório REL5201 (.xlsx ou .csv)", type=["xlsx", "csv"], key="upload_rel5201")
        if arquivo and st.button(f"Processar e substituir dados de {mes_referencia_upload}", type="primary"):
            try:
                with st.spinner("Lendo e importando o relatório..."):
                    df_bruto = ler_relatorio_5201(arquivo)
                    registros = montar_registros(df_bruto)
                    total = st.session_state.db.importar_relatorio_5201(
                        registros,
                        importado_por=st.session_state.get("usuario_id"),
                        mes_referencia=mes_referencia_upload,
                    )
                carregar_dados_atuais.clear()
                st.success(f"{total} processo(s) importado(s) em {mes_referencia_upload} com sucesso.")
                st.rerun()
            except Exception as erro:
                st.error(f"Falha na importação: {erro}")
else:
    st.caption("Acompanhe aqui sua produtividade no Relatório 5201, com base no seu login SIGO.")

df = carregar_dados_atuais()

if df.empty:
    st.info("Nenhum relatório importado ainda. Peça para um Gestor/Admin subir o REL5201 do dia.")
    st.stop()

if "_importado_em" in df.columns and df["_importado_em"].notna().any():
    ultima = pd.to_datetime(df["_importado_em"]).max()
    st.caption(f"Última atualização: {ultima.strftime('%d/%m/%Y %H:%M')}")

# -------------------------------------------------------- Seletor de mês ----
meses = meses_disponiveis(df)
if meses:
    escolha_mes = st.selectbox("Mês de referência", meses, index=0)
    df = df[df["_mes_referencia"] == escolha_mes]

# --------------------------------------------------------- Seletor de dia ----
dias = dias_disponiveis(df)
opcoes_dia = ["Todos os dias"] + [d.strftime("%d/%m/%Y") for d in dias]
escolha_dia = st.selectbox("Ver produtividade de:", opcoes_dia)
dia_filtro = None
if escolha_dia != "Todos os dias":
    dia_filtro = dias[opcoes_dia.index(escolha_dia) - 1]

if _ve_geral:
    resumo = resumo_geral(df)
    por_status = resumo["por_status"]

    st.markdown("### Visão Geral")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total de processos", resumo["total_processos"])
    c2.metric("Total de procedimentos", resumo["total_procedimentos"])
    c3.metric("Fechados", por_status.get("FECHADO", 0))
    c4.metric("Consistidos (em aberto)", por_status.get("CONSISTIDO", 0))
    c5.metric("Glosados", por_status.get("GLOSADO", 0))
    c6.metric("Calculados", por_status.get("CALCULADO", 0))

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
    tabela_auditores = produtividade_por_auditor(df, dia=dia_filtro)
    if tabela_auditores.empty:
        st.info("Nenhum processo com auditor (consistência/fechamento) registrado nesse período.")
    else:
        st.dataframe(tabela_auditores, use_container_width=True, hide_index=True)

        grafico_auditores = alt.Chart(tabela_auditores).mark_bar(cornerRadiusEnd=4).encode(
            x=alt.X("Total:Q", title="Processos concluídos (Fechado + Calculado)"),
            y=alt.Y("Auditor:N", sort="-x", title=None),
            color=alt.value("#4F8CFF"),
            tooltip=["Auditor", "Fechados", "Calculados", "Total", "Procedimentos"],
        )
        st.altair_chart(grafico_auditores, use_container_width=True)

else:
    st.markdown("### Minha Produtividade")
    if not _usuario_sigo:
        st.warning("Não identifiquei seu usuário SIGO nesta sessão — faça login novamente.")
        st.stop()

    minha_tabela = produtividade_por_auditor(df, dia=dia_filtro, auditor=_usuario_sigo)
    if minha_tabela.empty:
        st.info(
            f"Nenhum processo fechado/calculado no login **{_usuario_sigo}** "
            + (f"em {escolha_dia}." if dia_filtro else "no snapshot atual.")
        )
    else:
        linha = minha_tabela.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Fechados", int(linha["Fechados"]))
        c2.metric("Calculados", int(linha["Calculados"]))
        c3.metric("Total", int(linha["Total"]))
        c4.metric("Procedimentos", int(linha["Procedimentos"]))

    if dia_filtro is None and dias:
        st.divider()
        st.markdown("#### Por dia")
        linhas_por_dia = []
        for d in dias:
            t = produtividade_por_auditor(df, dia=d, auditor=_usuario_sigo)
            if not t.empty:
                linha = t.iloc[0]
                linhas_por_dia.append({
                    "Dia": d.strftime("%d/%m/%Y"),
                    "Fechados": int(linha["Fechados"]),
                    "Calculados": int(linha["Calculados"]),
                    "Total": int(linha["Total"]),
                    "Procedimentos": int(linha["Procedimentos"]),
                })
        if linhas_por_dia:
            st.dataframe(pd.DataFrame(linhas_por_dia), use_container_width=True, hide_index=True)
        else:
            st.caption("Nenhum dia com produtividade registrada ainda.")
