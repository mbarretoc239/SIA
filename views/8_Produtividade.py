import altair as alt
import pandas as pd
import streamlit as st

from core.relatorio_5201 import (
    STATUS_CORES,
    STATUS_LABELS,
    agrupar_por_status,
    carregar_dados_atuais,
    detalhe_processos_dia,
    dias_disponiveis,
    meses_disponiveis,
    procedimentos_consistido_digitado_por_canal,
    produtividade_por_auditor,
    resumo_geral,
    tempo_medio_resolucao,
)
from shared.database import DatabaseManager


def _secao_visao_geral(df: pd.DataFrame, titulo: str = "Visão Geral"):
    """Métricas + gráfico de status de TODOS os processos do mês (não filtra
    por auditor) — igual pro Gestor e pro usuário comum; só a tabela por
    pessoa abaixo disso é que fica exclusiva do Gestor."""
    resumo = resumo_geral(df)
    procedimentos_por_status = resumo["procedimentos_por_status"]

    grupos_procedimentos = agrupar_por_status(procedimentos_por_status)
    total_procedimentos = resumo["total_procedimentos"]

    def _pct(parte: int, total: int) -> str:
        if not total:
            return "0%"
        return f"{parte / total * 100:.1f}".replace(".", ",") + "%"

    with st.expander(titulo, expanded=True):
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
    # Domínio do eixo Y com folga acima da maior barra — sem isso o rótulo
    # (desenhado 8px acima da barra) da barra mais alta encosta no topo da
    # área do gráfico e fica cortado.
    maior_valor = df_status["Procedimentos"].max() if not df_status.empty else 0
    escala_y = alt.Scale(domain=[0, maior_valor * 1.15]) if maior_valor else alt.Scale()

    barras = alt.Chart(df_status).mark_bar(cornerRadiusEnd=4, size=40).encode(
        x=alt.X("Status:N", sort="-y", title=None),
        y=alt.Y("Procedimentos:Q", scale=escala_y),
        color=alt.Color("_cor:N", scale=None, legend=None),
        tooltip=["Status", "Procedimentos"],
    )
    # Rótulo acima de cada barra: mesmo as pequenas (perto de zero, ao lado
    # de uma barra 500x maior) ficam com o número legível sem precisar de
    # hover nem de escala log.
    rotulos = alt.Chart(df_status).mark_text(dy=-8, color="white", fontSize=12).encode(
        x=alt.X("Status:N", sort="-y"),
        y=alt.Y("Procedimentos:Q", scale=escala_y),
        text="_rotulo:N",
    )
    return barras + rotulos


def _secao_detalhe_dia(df: pd.DataFrame, dia, auditor: str):
    """Detalhe de processos do auditor num dia específico: tempo médio até o
    fechamento + lista processo a processo. Só faz sentido com um dia
    específico escolhido (não em "Todos os dias", onde não há uma única
    janela de tempo pra medir)."""
    detalhe = detalhe_processos_dia(df, dia, auditor)
    if detalhe.empty:
        st.info("Nenhum processo Fechado/Calculado desse auditor nesse dia.")
        return

    st.metric("Tempo médio até o fechamento", tempo_medio_resolucao(detalhe) or "—")
    st.dataframe(detalhe.drop(columns=["_minutos"]), use_container_width=True, hide_index=True)


def _secao_produtividade_individual(
    df: pd.DataFrame, auditor: str, dias: list, dia_filtro, escolha_dia: str,
    key_prefix: str, titulo: str = "Minha Produtividade",
):
    """Produtividade de UM auditor: métricas do período + detalhe do dia (se
    filtrado) + gráfico dia-a-dia do mês com clique pra detalhar. Usada tanto
    pelo próprio auditor (vendo a si mesmo) quanto pelo Gestor (escolhendo
    quem quiser ver) -- é a mesma seção, só muda quem é o `auditor`.

    `key_prefix`: só precisa ser único quando o Gestor pode trocar de
    auditor na mesma página -- evita que o clique/seleção do gráfico de um
    auditor vaze pro de outro ao trocar a escolha (mesmo problema que já
    tivemos com a seleção do Vega-Lite persistindo entre reruns)."""
    st.markdown(f"### {titulo}")
    st.caption("Só conta processos em estado final (Fechado ou Calculado) — Consistido ainda está em aberto e não entra na contagem.")
    tabela = produtividade_por_auditor(df, dia=dia_filtro, auditor=auditor)
    if tabela.empty:
        st.info("Nenhum processo fechado/calculado" + (f" em {escolha_dia}." if dia_filtro else " neste mês."))
    else:
        linha = tabela.iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Fechados", _fmt_num(int(linha["Fechados"])))
        c2.metric("Calculados", _fmt_num(int(linha["Calculados"])))
        c3.metric("Total", _fmt_num(int(linha["Total"])))

        if dia_filtro is not None:
            st.markdown("#### Detalhe de Processos do Dia")
            _secao_detalhe_dia(df, dia_filtro, auditor)

    if not dias:
        return

    linhas_por_dia = []
    for d in dias:
        t = produtividade_por_auditor(df, dia=d, auditor=auditor)
        if not t.empty:
            linha = t.iloc[0]
            linhas_por_dia.append({
                "Dia": d,
                "Dia_fmt": d.strftime("%d/%m/%Y"),
                "Fechados": int(linha["Fechados"]),
                "Calculados": int(linha["Calculados"]),
                "Total": int(linha["Total"]),
            })

    if not linhas_por_dia:
        st.caption("Nenhum dia com produtividade registrada ainda.")
        return

    df_por_dia = pd.DataFrame(linhas_por_dia).sort_values("Dia")

    st.markdown("#### Produtividade ao longo do mês")
    st.caption("Clique numa barra para ver o detalhe daquele dia.")
    selecao_dia = alt.selection_point(name=f"selecao_dia_{key_prefix}", fields=["Dia_fmt"], on="click", empty=False)
    grafico_dia = alt.Chart(df_por_dia).mark_bar(cornerRadiusEnd=4, color="#4F8CFF").encode(
        x=alt.X("Dia_fmt:N", sort=None, title=None),
        y=alt.Y("Total:Q", title="Procedimentos concluídos (Fechado + Calculado)"),
        tooltip=["Dia_fmt", "Fechados", "Calculados", "Total"],
        opacity=alt.condition(selecao_dia, alt.value(1), alt.value(0.65)),
    ).add_params(selecao_dia)
    evento_grafico = st.altair_chart(
        grafico_dia, use_container_width=True, on_select="rerun", key=f"grafico_prod_mes_{key_prefix}",
    )
    pontos_clicados = evento_grafico.selection.get(f"selecao_dia_{key_prefix}") if evento_grafico else None
    dia_clicado = pontos_clicados[0].get("Dia_fmt") if pontos_clicados else None
    # A seleção do Vega-Lite persiste entre reruns até um novo clique no
    # gráfico -- sem essa comparação, o mesmo clique antigo seria
    # reprocessado a cada rerun (inclusive sobrescrevendo de volta quando o
    # usuário escolhe "Todos os dias" no selectbox acima). Só age quando o
    # clique em si mudou desde o último processado.
    chave_click_ultimo = f"_dia_click_ultimo_{key_prefix}"
    if dia_clicado != st.session_state.get(chave_click_ultimo):
        st.session_state[chave_click_ultimo] = dia_clicado
        # dia_clicado None = clicou fora das barras (deseleção) -> volta pra "Todos os dias".
        alvo = dia_clicado or "Todos os dias"
        if alvo != escolha_dia:
            st.session_state["_dia_click_pendente"] = alvo
            st.rerun()

    with st.expander("Ver tabela por dia"):
        st.dataframe(
            df_por_dia.drop(columns=["Dia"]).rename(columns={"Dia_fmt": "Dia"}),
            use_container_width=True, hide_index=True,
        )


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
        "Para subir um novo REL5201, vá em **Configurações → Importação de Planilhas**. "
        "Prestador, CPF/CNPJ e demais dados de negócio não são armazenados — só o "
        "necessário para status e produtividade, e mesmo assim de forma cifrada no banco."
    )
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

# Clique numa barra do gráfico "Produtividade ao longo do mês" (mais abaixo)
# guarda o dia clicado aqui e força um rerun — precisa ser aplicado ANTES do
# selectbox nascer (senão o widget já existente ignora o novo valor).
if "_dia_click_pendente" in st.session_state:
    dia_clicado = st.session_state.pop("_dia_click_pendente")
    if dia_clicado in opcoes_dia:
        st.session_state["dia_select_box"] = dia_clicado

escolha_dia = st.selectbox("Ver produtividade de:", opcoes_dia, key="dia_select_box")
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

        tabela_auditores = tabela_auditores.assign(_rotulo=tabela_auditores["Total"].apply(_fmt_num))
        maior_valor_auditores = tabela_auditores["Total"].max()
        escala_y_auditores = alt.Scale(domain=[0, maior_valor_auditores * 1.15]) if maior_valor_auditores else alt.Scale()
        barras_auditores = alt.Chart(tabela_auditores).mark_bar(cornerRadiusEnd=4, size=40).encode(
            x=alt.X("Auditor:N", sort="-y", title=None, axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("Total:Q", title="Procedimentos concluídos (Fechado + Calculado)", scale=escala_y_auditores),
            color=alt.value("#4F8CFF"),
            tooltip=["Auditor", "Fechados", "Calculados", "Total"],
        )
        rotulos_auditores = alt.Chart(tabela_auditores).mark_text(dy=-8, color="white", fontSize=12).encode(
            x=alt.X("Auditor:N", sort="-y"),
            y=alt.Y("Total:Q", scale=escala_y_auditores),
            text="_rotulo:N",
        )
        st.altair_chart(barras_auditores + rotulos_auditores, use_container_width=True)

        st.divider()
        st.markdown("### Ver produtividade individual")
        st.caption("Mesma visão que o próprio auditor tem da produtividade dele.")
        auditor_escolhido = st.selectbox(
            "Auditor", tabela_auditores["Auditor"].tolist(), key="gestor_auditor_escolhido",
        )
        _secao_produtividade_individual(
            df, auditor_escolhido, dias, dia_filtro, escolha_dia,
            key_prefix=f"gestor_{auditor_escolhido}", titulo=f"Produtividade de {auditor_escolhido}",
        )

else:
    if not _usuario_sigo:
        st.warning("Não identifiquei seu usuário SIGO nesta sessão — faça login novamente.")
        st.stop()

    # Mesma visão geral do Gestor (status de TODOS os processos do mês) —
    # só a tabela por pessoa (auditor a auditor) que fica exclusiva dele.
    _secao_visao_geral(df, titulo="Visão Geral do Mês")

    st.divider()

    _secao_produtividade_individual(
        df, _usuario_sigo, dias, dia_filtro, escolha_dia, key_prefix="proprio", titulo="Minha Produtividade",
    )
