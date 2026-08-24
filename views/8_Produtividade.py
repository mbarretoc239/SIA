import altair as alt
import pandas as pd
import streamlit as st

from shared.ui import fmt_num as _fmt_num, pilula

from core.relatorio_5201 import (
    STATUS_CORES,
    STATUS_LABELS,
    agrupar_por_status,
    carregar_dados_atuais,
    detalhe_processos_periodo,
    dias_disponiveis,
    meses_disponiveis,
    procedimentos_consistido_digitado_por_canal,
    produtividade_por_auditor,
    resumo_geral,
    tempo_medio_resolucao,
)
from core.settings import (
    carregar_excecoes_modulos_cache,
    carregar_permissoes_modulos_cache,
    tem_acesso_modulo,
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
                st.markdown(pilula(pct_analisado), unsafe_allow_html=True)
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


def _secao_lista_processos(df: pd.DataFrame, auditor: str, dia=None, expandido: bool = False):
    """Lista processo a processo (Fechado/Calculado) do auditor -- tempo
    médio até o fechamento + tabela completa. Com `dia` informado, restringe
    a esse dia; sem ele, cobre todo o período já filtrado em `df`
    (normalmente o mês selecionado) -- é a lista que tanto o auditor quanto
    o Gestor usam pra conferir o que foi feito, não só as métricas
    agregadas."""
    detalhe = detalhe_processos_periodo(df, auditor, dia=dia)
    titulo = f"Processos do dia ({len(detalhe)})" if dia is not None else f"Lista de processos do período ({len(detalhe)})"
    with st.expander(titulo, expanded=expandido):
        if detalhe.empty:
            st.info("Nenhum processo Fechado/Calculado desse auditor" + (" nesse dia." if dia is not None else " nesse período."))
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

        _secao_lista_processos(df, auditor, dia=dia_filtro)

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
    # Padding proporcional no eixo X -- sem isso, com poucos dias (ex: só 3)
    # as barras ficam enormes e coladas; com muitos dias, ficam apertadas.
    # Mesmo ajuste já aplicado no gráfico "Produtividade por Auditor".
    escala_x_dia = alt.Scale(paddingInner=0.35, paddingOuter=0.15)
    grafico_dia = alt.Chart(df_por_dia).mark_bar(cornerRadiusEnd=4, color="#4F8CFF").encode(
        # labelOverlap=False -- mesmo cuidado do gráfico por auditor: sem
        # isso, um mês com muitos dias faz o Vega-Lite esconder alguns
        # rótulos de data silenciosamente.
        x=alt.X(
            "Dia_fmt:N", sort=None, title=None,
            axis=alt.Axis(labelAngle=-45, labelOverlap=False), scale=escala_x_dia,
        ),
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


st.set_page_config(page_title="Produtividade", page_icon="🦷", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar esta ferramenta.")
    st.stop()

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()

_ROLES_GERAL = {"Gestor", "Admin"}
_role = st.session_state.get("role_interno", "Contas")
_ve_geral = _role in _ROLES_GERAL
_usuario_sigo = st.session_state.get("usuario_sigo", "")

_permissoes = carregar_permissoes_modulos_cache()
_excecoes = carregar_excecoes_modulos_cache()
if not tem_acesso_modulo(_permissoes, _role, "produtividade", st.session_state.get("usuario_id"), _excecoes):
    st.error("Você não tem permissão para acessar este módulo.")
    st.stop()

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
    escolha_mes = st.selectbox("Mês de referência", meses, index=0, width=300)
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

escolha_dia = st.selectbox("Ver produtividade de:", opcoes_dia, key="dia_select_box", width=300)
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
        # Largura de barra fixa (size=40) ficava apertada com muitos auditores
        # -- barras coladas, rótulos vizinhos colidindo (ex: dois valores
        # próximos como 103.111/103.059 desenhados quase na mesma posição).
        # Padding proporcional no eixo X deixa o espaçamento consistente
        # não importa quantos auditores entrem na tabela.
        escala_x_auditores = alt.Scale(paddingInner=0.35, paddingOuter=0.15)
        # Clique numa barra seleciona esse auditor no seletor de produtividade
        # individual logo abaixo (mesmo padrão de clique-seleciona já usado
        # no gráfico "Produtividade ao longo do mês").
        selecao_auditor = alt.selection_point(name="selecao_auditor", fields=["Auditor"], on="click", empty=False)
        barras_auditores = alt.Chart(tabela_auditores).mark_bar(cornerRadiusEnd=4).encode(
            # labelOverlap=False -- por padrão o Vega-Lite esconde rótulos do
            # eixo que colidiriam entre si (com muitos auditores, alguns
            # nomes somem silenciosamente). Força todos a aparecer.
            x=alt.X(
                "Auditor:N", sort="-y", title=None,
                axis=alt.Axis(labelAngle=-45, labelOverlap=False),
                scale=escala_x_auditores,
            ),
            y=alt.Y("Total:Q", title="Procedimentos concluídos (Fechado + Calculado)", scale=escala_y_auditores),
            color=alt.value("#4F8CFF"),
            opacity=alt.condition(selecao_auditor, alt.value(1), alt.value(0.65)),
            tooltip=["Auditor", "Fechados", "Calculados", "Total"],
        ).add_params(selecao_auditor)
        rotulos_auditores = alt.Chart(tabela_auditores).mark_text(dy=-8, color="white", fontSize=11).encode(
            x=alt.X("Auditor:N", sort="-y", scale=escala_x_auditores),
            y=alt.Y("Total:Q", scale=escala_y_auditores),
            text="_rotulo:N",
        )
        st.caption("Clique numa barra pra ver a produtividade individual desse auditor.")
        evento_grafico_auditor = st.altair_chart(
            (barras_auditores + rotulos_auditores).properties(height=380),
            use_container_width=True, on_select="rerun", key="grafico_prod_auditor",
        )
        pontos_clicados_auditor = evento_grafico_auditor.selection.get("selecao_auditor") if evento_grafico_auditor else None
        auditor_clicado = pontos_clicados_auditor[0].get("Auditor") if pontos_clicados_auditor else None
        # Mesmo cuidado do clique-no-dia: só age quando o clique em si mudou
        # desde o último processado, senão a seleção do Vega-Lite (que
        # persiste entre reruns) reprocessaria o mesmo clique sem parar.
        if auditor_clicado != st.session_state.get("_auditor_click_ultimo"):
            st.session_state["_auditor_click_ultimo"] = auditor_clicado
            if auditor_clicado and auditor_clicado != st.session_state.get("gestor_auditor_escolhido"):
                st.session_state["_auditor_click_pendente"] = auditor_clicado
                st.session_state["gestor_auditor_expander_aberto"] = True
                st.rerun()

        # Aplica o clique pendente ANTES do selectbox nascer (senão o widget
        # já existente ignora o novo valor) -- mesmo padrão do seletor de dia.
        if "_auditor_click_pendente" in st.session_state:
            auditor_pendente = st.session_state.pop("_auditor_click_pendente")
            if auditor_pendente in tabela_auditores["Auditor"].tolist():
                st.session_state["gestor_auditor_escolhido"] = auditor_pendente

        with st.expander(
            "Ver produtividade individual",
            expanded=st.session_state.get("gestor_auditor_expander_aberto", False),
            key="gestor_auditor_expander_aberto",
            # Controlar o estado via session_state (pra abrir sozinho quando
            # o usuário clica numa barra) só funciona de verdade com
            # on_change="rerun" -- sem isso o key não fica de fato vinculado.
            on_change="rerun",
        ):
            auditor_escolhido = st.selectbox(
                "Auditor", tabela_auditores["Auditor"].tolist(), key="gestor_auditor_escolhido", width=300,
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
