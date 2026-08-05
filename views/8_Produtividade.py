from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from core.relatorio_5201 import (
    STATUS_CORES,
    STATUS_LABELS,
    agrupar_por_status,
    carregar_dados_atuais,
    dias_disponiveis,
    ler_relatorio_5201,
    meses_disponiveis,
    montar_registros,
    procedimentos_consistido_digitado_por_canal,
    produtividade_por_auditor,
    resumo_geral,
)
from shared.database import DatabaseManager


def _secao_visao_geral(df: pd.DataFrame, titulo: str = "Visão Geral"):
    """Métricas + gráfico de status de TODOS os processos do mês (não filtra
    por auditor) — igual pro Gestor e pro usuário comum; só a tabela por
    pessoa abaixo disso é que fica exclusiva do Gestor."""
    resumo = resumo_geral(df)
    procedimentos_por_status = resumo["procedimentos_por_status"]

    st.markdown(f"### {titulo}")

    grupos_procedimentos = agrupar_por_status(procedimentos_por_status)
    total_procedimentos = resumo["total_procedimentos"]

    def _pct(parte: int, total: int) -> str:
        if not total:
            return "0%"
        return f"{parte / total * 100:.1f}".replace(".", ",") + "%"

    # Resumo rápido nos números que a equipe acompanha: total, analisado
    # (estado final), cancelado/glosado (não vai gerar pagamento) e
    # consistido/digitado (ainda em algum ponto do fluxo). O detalhe fino
    # por status individual continua no gráfico logo abaixo.
    with st.container(border=True):
        st.caption("Procedimentos")
        # Rótulos curtos pra caber em 5 colunas numa linha só sem truncar —
        # a explicação completa de cada um fica no tooltip (ícone "?" do
        # st.metric), não precisa estar visível o tempo todo.
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total", _fmt_num(total_procedimentos))
        with m2:
            st.metric("Analisado", _fmt_num(grupos_procedimentos["analisado"]), help="Fechado + Calculado")
            pct_analisado = _pct(grupos_procedimentos["analisado"], total_procedimentos)
            st.markdown(
                f"<span style='background: rgba(148,163,184,0.18); color: #94a3b8; "
                f"padding: 2px 10px; border-radius: 999px; font-size: 0.8rem; "
                f"display: inline-block;'>{pct_analisado}</span>",
                unsafe_allow_html=True,
            )
        m3.metric("Cancelado/Glosado", _fmt_num(grupos_procedimentos["cancelado_glosado"]))
        m4.metric("Consistido/Digitado", _fmt_num(grupos_procedimentos["consistido_digitado"]))
        m5.metric(
            "App + Misto/Não App",
            _fmt_num(procedimentos_consistido_digitado_por_canal(df)),
            help=(
                "Dos Consistido/Digitado: todo canal App (independente de "
                "data) + Misto/Não App que já têm data de entrada preenchida."
            ),
        )

    if resumo["total_processos"]:
        st.altair_chart(_grafico_status(procedimentos_por_status), use_container_width=True)


def _fmt_num(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _grafico_status(procedimentos_por_status: dict):
    df_status = pd.DataFrame([
        {
            "Status": STATUS_LABELS.get(status, status),
            "Procedimentos": qtd,
            "_rotulo": _fmt_num(qtd),
            "_cor": STATUS_CORES.get(status, STATUS_CORES["_outro"]),
        }
        for status, qtd in procedimentos_por_status.items()
    ])
    barras = alt.Chart(df_status).mark_bar(cornerRadiusEnd=4, size=40).encode(
        x=alt.X("Status:N", sort="-y", title=None),
        y=alt.Y("Procedimentos:Q"),
        color=alt.Color("_cor:N", scale=None, legend=None),
        tooltip=["Status", "Procedimentos"],
    )
    # Rótulo acima de cada barra: mesmo as pequenas (perto de zero, ao lado
    # de uma barra 500x maior) ficam com o número legível sem precisar de
    # hover nem de escala log.
    rotulos = alt.Chart(df_status).mark_text(dy=-8, color="white", fontSize=12).encode(
        x=alt.X("Status:N", sort="-y"),
        y=alt.Y("Procedimentos:Q"),
        text="_rotulo:N",
    )
    return barras + rotulos

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
    _secao_visao_geral(df)

    st.divider()

    st.markdown("### Produtividade por Auditor")
    st.caption("Só conta processos em estado final (Fechado ou Calculado) — Consistido ainda está em aberto e não entra na contagem.")
    tabela_auditores = produtividade_por_auditor(df, dia=dia_filtro)
    if tabela_auditores.empty:
        st.info("Nenhum processo com auditor (consistência/fechamento) registrado nesse período.")
    else:
        st.dataframe(tabela_auditores, use_container_width=True, hide_index=True)

        tabela_auditores = tabela_auditores.assign(_rotulo=tabela_auditores["Procedimentos"].apply(_fmt_num))
        barras_auditores = alt.Chart(tabela_auditores).mark_bar(cornerRadiusEnd=4, size=40).encode(
            x=alt.X("Auditor:N", sort="-y", title=None, axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("Procedimentos:Q", title="Procedimentos concluídos (Fechado + Calculado)"),
            color=alt.value("#4F8CFF"),
            tooltip=["Auditor", "Fechados", "Calculados", "Total", "Procedimentos"],
        )
        rotulos_auditores = alt.Chart(tabela_auditores).mark_text(dy=-8, color="white", fontSize=12).encode(
            x=alt.X("Auditor:N", sort="-y"),
            y=alt.Y("Procedimentos:Q"),
            text="_rotulo:N",
        )
        st.altair_chart(barras_auditores + rotulos_auditores, use_container_width=True)

else:
    if not _usuario_sigo:
        st.warning("Não identifiquei seu usuário SIGO nesta sessão — faça login novamente.")
        st.stop()

    # Mesma visão geral do Gestor (status de TODOS os processos do mês) —
    # só a tabela por pessoa (auditor a auditor) que fica exclusiva dele.
    _secao_visao_geral(df, titulo="Visão Geral do Mês")

    st.divider()

    st.markdown("### Minha Produtividade")
    st.caption("Só conta processos em estado final (Fechado ou Calculado) — Consistido ainda está em aberto e não entra na contagem.")
    minha_tabela = produtividade_por_auditor(df, dia=dia_filtro, auditor=_usuario_sigo)
    if minha_tabela.empty:
        st.info("Nenhum processo fechado/calculado" + (f" em {escolha_dia}." if dia_filtro else " neste mês."))
    else:
        linha = minha_tabela.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Fechados", _fmt_num(int(linha["Fechados"])))
        c2.metric("Calculados", _fmt_num(int(linha["Calculados"])))
        c3.metric("Total", _fmt_num(int(linha["Total"])))
        c4.metric("Procedimentos", _fmt_num(int(linha["Procedimentos"])))

    if dias:
        linhas_por_dia = []
        for d in dias:
            t = produtividade_por_auditor(df, dia=d, auditor=_usuario_sigo)
            if not t.empty:
                linha = t.iloc[0]
                linhas_por_dia.append({
                    "Dia": d,
                    "Dia_fmt": d.strftime("%d/%m/%Y"),
                    "Fechados": int(linha["Fechados"]),
                    "Calculados": int(linha["Calculados"]),
                    "Total": int(linha["Total"]),
                    "Procedimentos": int(linha["Procedimentos"]),
                })

        if linhas_por_dia:
            df_por_dia = pd.DataFrame(linhas_por_dia).sort_values("Dia")

            st.markdown("#### Produtividade ao longo do mês")
            grafico_dia = alt.Chart(df_por_dia).mark_bar(cornerRadiusEnd=4, color="#4F8CFF").encode(
                x=alt.X("Dia_fmt:N", sort=None, title=None),
                y=alt.Y("Total:Q", title="Processos concluídos (Fechado + Calculado)"),
                tooltip=["Dia_fmt", "Fechados", "Calculados", "Total", "Procedimentos"],
            )
            st.altair_chart(grafico_dia, use_container_width=True)

            with st.expander("Ver tabela por dia"):
                st.dataframe(
                    df_por_dia.drop(columns=["Dia"]).rename(columns={"Dia_fmt": "Dia"}),
                    use_container_width=True, hide_index=True,
                )
        else:
            st.caption("Nenhum dia com produtividade registrada ainda.")
