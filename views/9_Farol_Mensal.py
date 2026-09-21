import io

import pandas as pd
import streamlit as st

from core.amostragem import carregar_procedimentos_criticos, carregar_regras_amostragem_cache
from core.farol_mensal import (
    CRITICA_COM,
    CRITICA_SEM,
    CRITICA_TODOS,
    DIGITADOR_NAO,
    DIGITADOR_SIM,
    DIGITADOR_TODOS,
    EXECUCOES_DISPONIVEIS,
    MODALIDADE_SEMPRE_EXCLUIDA,
    STATUS_PADRAO,
    BaseFarol,
    FiltrosFarol,
    aplicar_filtros,
    carregar_glosas_5310,
    carregar_processos_ia,
    montar_base_farol,
    opcoes_especialidades,
    resumo_farol,
    separar_para_cruzamento,
)
from core.relatorio_5201 import carregar_dados_atuais
from core.settings import tem_acesso_modulo
from services.farol_mensal.erros import ColunasFaltandoError
from services.farol_mensal.processamento import (
    ABAS_SAIDA,
    abas_de_ocorrencias,
    carregar_ocorrencias,
    cruzar,
    para_bytes,
)
from shared.database import DatabaseManager
from shared.ui import (
    COR_SUCESSO,
    filtro_numerico,
    fmt_num,
    persistir_entre_paginas,
    pilula,
    valor_persistido,
)

st.set_page_config(page_title="Farol Mensal", page_icon="🦷", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar esta ferramenta.")
    st.stop()

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()

_role = st.session_state.get("role_interno", "Contas")
_usuario_id = st.session_state.get("usuario_id")
_permissoes = st.session_state.db.carregar_permissoes_modulos()
_excecoes = st.session_state.db.carregar_excecoes_modulos()
if not tem_acesso_modulo(_permissoes, _role, "farol_mensal", _usuario_id, _excecoes):
    st.error("Você não tem permissão para acessar este módulo.")
    st.stop()

NOMES_BALDES = {chave: nome for chave, nome in ABAS_SAIDA}
LIMITE_ALERTA_SEM_OCORRENCIA = 70  # % -- mesmo limite da GUI original


def _mes_br(mes: str) -> str:
    """'2026-07' -> '07/2026' (devolve o texto como veio se não for esse formato)."""
    partes = str(mes).split("-")
    return f"{partes[1]}/{partes[0]}" if len(partes) == 2 else str(mes)


def _pct_br(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",") + "%"


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_base() -> BaseFarol:
    _, ordem_criticas = carregar_regras_amostragem_cache()
    return montar_base_farol(
        carregar_dados_atuais(), carregar_processos_ia(), carregar_glosas_5310(),
        ordem_criticas, carregar_procedimentos_criticos(),
    )


@st.cache_data(show_spinner=False)
def _classificar_ocorrencias(dados: bytes, nome: str, aba, incluir_compulsorio_no_sim: bool):
    """Classificação do arquivo de ocorrências, cacheada por conteúdo -- mexer
    nos filtros não reclassifica os textos, só o cruzamento."""
    fonte = io.BytesIO(dados)
    fonte.name = nome
    return carregar_ocorrencias(fonte, aba, incluir_compulsorio_no_sim)


st.title("Farol Mensal")
st.caption(
    "Lista dos processos do mês que podem ir pro FAROL, classificados pelas ocorrências do mês anterior (5307). "
    "Usa o último REL5201 e a base IA já importados; a 5307 é enviada aqui e não fica gravada."
)

try:
    with st.spinner("Carregando processos do mês..."):
        base = _carregar_base()
except Exception as erro:
    st.error(f"Não foi possível carregar os dados do mês: {erro}")
    st.stop()

if base.df.empty:
    st.info("Nenhum processo encontrado no REL5201 importado. Importe o relatório em Configurações → Importação de Planilhas.")
    st.stop()

col_info, col_recarregar = st.columns([5, 1])
with col_info:
    st.caption(
        f"REL5201 de {_mes_br(base.mes_5201) if base.mes_5201 else '—'} · "
        f"Base IA de {_mes_br(base.mes_ia) if base.mes_ia else '—'} · "
        f"{fmt_num(base.total_processos_mes)} processos e {fmt_num(base.total_procedimentos_mes)} procedimentos no mês"
    )
with col_recarregar:
    if st.button("Recarregar dados", use_container_width=True, help="Ignora o cache de 5 minutos e busca tudo de novo."):
        for carregador in (_carregar_base, carregar_dados_atuais, carregar_processos_ia, carregar_glosas_5310):
            carregador.clear()
        st.rerun()

if not base.tem_digitador:
    st.warning(
        "O REL5201 importado não tem a coluna OP_ENC_DIGITAÇÃO — o filtro de login de digitador fica "
        "desativado até reimportar o relatório em Configurações."
    )
if not base.tem_nao_avaliado:
    st.warning(
        "O REL5201 importado não tem a coluna QUANTIDADE_NÃO_AVALIADO_IA — a regra dos 100% liberados pela "
        "IA fica desativada (ninguém é considerado 100%) até reimportar o relatório em Configurações."
    )

# --- 1. Ocorrências do mês anterior (5307) ---
st.subheader("1. Ocorrências do mês anterior")
arquivo_ocorrencias = st.file_uploader(
    "Planilha 5307 (.xlsx ou .csv)", type=["xlsx", "csv"], key="farol_upload_5307",
    help="Colunas obrigatórias: Nu. Ordem, Nome Prestador, Desc. Ocorrencia. O nome da aba pode variar.",
)
incluir_compulsorio = st.checkbox(
    "Incluir no SIM os fechamentos compulsórios",
    value=False, key="farol_incluir_compulsorio",
    help=(
        "Desmarcado (padrão): prestador com fechamento compulsório vai pro N, como sempre. "
        "Marcado: só os textos padrão de fechamento compulsório (lista em "
        "services/farol_mensal/classificacao.py) vão pro S; qualquer outro texto segue as regras normais."
    ),
)

agregado = None
info_ocorrencias = None
if arquivo_ocorrencias is not None:
    try:
        abas = abas_de_ocorrencias(arquivo_ocorrencias)
        aba = None
        if arquivo_ocorrencias.name.lower().endswith(".xlsx"):
            if not abas:
                st.error(
                    "Nenhuma aba dessa planilha tem as colunas Nu. Ordem, Nome Prestador e Desc. Ocorrencia. "
                    "Confira se é a planilha 5307."
                )
                st.stop()
            aba = abas[0] if len(abas) == 1 else st.selectbox("Aba com as ocorrências", abas, key="farol_aba_5307")
        with st.spinner("Classificando ocorrências..."):
            agregado, info_ocorrencias = _classificar_ocorrencias(
                arquivo_ocorrencias.getvalue(), arquivo_ocorrencias.name, aba, incluir_compulsorio,
            )
    except ColunasFaltandoError as erro:
        st.error(str(erro))
        st.stop()
    except Exception as erro:
        st.error(f"Não foi possível ler a planilha de ocorrências: {erro}")
        st.stop()

    mes_ocorrencias = _mes_br(info_ocorrencias.mes_producao) if info_ocorrencias.mes_producao else "—"
    st.caption(
        f"Ocorrências da produção de {mes_ocorrencias} · {fmt_num(info_ocorrencias.total_processos)} ocorrências lidas · "
        f"{fmt_num(info_ocorrencias.fechamentos_compulsorios)} de fechamento compulsório"
    )
    if incluir_compulsorio:
        st.caption(
            f"{fmt_num(info_ocorrencias.compulsorios_no_sim)} fechamento(s) compulsório(s) com texto padrão foram pro SIM."
        )
        if info_ocorrencias.compulsorios_fora_do_padrao:
            st.warning(
                f"{fmt_num(info_ocorrencias.compulsorios_fora_do_padrao)} fechamento(s) compulsório(s) têm texto fora "
                "do padrão (glosa citada, observação ou modelo novo) e continuam no N."
            )

# --- 2. Filtros ---
st.subheader("2. Filtros")
df_base = base.df

col_critica, col_extras = st.columns([1, 2])
with col_critica:
    filtro_critica = st.segmented_control(
        "Especialidade", [CRITICA_TODOS, CRITICA_COM, CRITICA_SEM],
        default=valor_persistido("farol_filtro_critica", CRITICA_TODOS),
        key="farol_filtro_critica", on_change=persistir_entre_paginas, args=("farol_filtro_critica",),
    ) or CRITICA_TODOS
with col_extras:
    todas_especialidades = opcoes_especialidades(df_base)
    filtro_extras = st.multiselect(
        "Aceitar também estas especialidades críticas",
        todas_especialidades,
        default=[v for v in valor_persistido("farol_filtro_extras", []) if v in todas_especialidades],
        key="farol_filtro_extras", on_change=persistir_entre_paginas, args=("farol_filtro_extras",),
        disabled=filtro_critica != CRITICA_SEM,
        help=(
            "Só vale em 'Sem críticas'. Entram os processos sem nenhuma crítica e, além deles, os processos cujas "
            "ÚNICAS críticas são as escolhidas aqui. Ex.: escolhendo cirurgia entram processos com cirurgia + consulta "
            "+ dentística, mas não cirurgia + endodontia (endodontia é crítica e não foi escolhida)."
        ),
    )

col_status, col_execucao, col_modalidade, col_digitador = st.columns(4)
with col_status:
    opcoes_status = sorted(df_base["STATUS"].replace("", pd.NA).dropna().unique())
    filtro_status = st.multiselect(
        "Status", opcoes_status,
        default=[v for v in valor_persistido("farol_filtro_status", list(STATUS_PADRAO)) if v in opcoes_status],
        key="farol_filtro_status", on_change=persistir_entre_paginas, args=("farol_filtro_status",),
    )
with col_execucao:
    execucoes_presentes = set(df_base["EXECUCAO"])
    opcoes_execucao = [e for e in EXECUCOES_DISPONIVEIS if e in execucoes_presentes] or EXECUCOES_DISPONIVEIS
    filtro_execucao = st.multiselect(
        "Execução", opcoes_execucao,
        default=[v for v in valor_persistido("farol_filtro_execucao", []) if v in opcoes_execucao],
        key="farol_filtro_execucao", on_change=persistir_entre_paginas, args=("farol_filtro_execucao",),
    )
with col_modalidade:
    opcoes_modalidade = sorted(m for m in df_base["MODALIDADE"].unique() if m and m != MODALIDADE_SEMPRE_EXCLUIDA)
    filtro_modalidade = st.multiselect(
        "Modalidade", opcoes_modalidade,
        default=[v for v in valor_persistido("farol_filtro_modalidade", []) if v in opcoes_modalidade],
        key="farol_filtro_modalidade", on_change=persistir_entre_paginas, args=("farol_filtro_modalidade",),
        help="Recursos são sempre ignorados no Farol e não podem ser incluídos.",
    )
with col_digitador:
    filtro_digitador = st.segmented_control(
        "Tem login de digitador?", [DIGITADOR_TODOS, DIGITADOR_SIM, DIGITADOR_NAO],
        default=valor_persistido("farol_filtro_digitador", DIGITADOR_TODOS),
        key="farol_filtro_digitador", on_change=persistir_entre_paginas, args=("farol_filtro_digitador",),
        disabled=not base.tem_digitador,
    ) or DIGITADOR_TODOS

col_pct_lib, col_pct_bio, _ = st.columns([1, 1, 2])
with col_pct_lib:
    filtro_liberacao = filtro_numerico("% Liberação IA", "farol_filtro_liberacao")
with col_pct_bio:
    filtro_biometria = filtro_numerico("% Biometria", "farol_filtro_biometria")

st.caption(
    "Recursos ficam sempre de fora. Processos sem dado na base IA aparecem mesmo com filtro de especialidade, "
    "% de liberação ou % de biometria — precisam ser vistos manualmente."
)

filtros = FiltrosFarol(
    critica=filtro_critica,
    especialidades_extras=tuple(filtro_extras) if filtro_critica == CRITICA_SEM else (),
    liberacao_ia=filtro_liberacao,
    biometria=filtro_biometria,
    status=tuple(filtro_status),
    digitador=filtro_digitador if base.tem_digitador else DIGITADOR_TODOS,
    execucao=tuple(filtro_execucao),
    modalidade=tuple(filtro_modalidade),
)
df_filtrado = aplicar_filtros(df_base, filtros)

with st.expander(f"Lista de processos filtrada ({fmt_num(len(df_filtrado))})"):
    if df_filtrado.empty:
        st.info("Nenhum processo com esses filtros.")
    else:
        exibicao = df_filtrado.assign(
            DIGITADO=df_filtrado["DIGITADO"].apply(lambda v: "—" if pd.isna(v) else ("Sim" if v else "Não")),
            # sem dado na base IA não dá pra dizer se tem crítica ou não
            CRITICA=df_filtrado.apply(lambda l: "—" if l["SEM_DADO_IA"] else ("Sim" if l["CRITICA"] else "Não"), axis=1),
            LIBERADO_100_IA=df_filtrado["LIBERADO_100_IA"].apply(lambda v: "Sim" if v else ""),
        ).rename(columns={
            "ORDEM": "Processo", "PRESTADOR": "Prestador", "QT_PROCEDIMENTO": "Procedimentos", "STATUS": "Status",
            "EXECUCAO": "Execução", "MODALIDADE": "Modalidade", "DIGITADO": "Digitador", "PCT_LIBERACAO_IA": "% Liberação IA",
            "PCT_BIOMETRIA": "% Biometria", "ESPECIALIDADES": "Especialidades", "CRITICA": "Crítica",
            "LIBERADO_100_IA": "100% IA",
        })[[
            "Processo", "Prestador", "Procedimentos", "Status", "Execução", "Modalidade", "Digitador",
            "% Liberação IA", "% Biometria", "Especialidades", "Crítica", "100% IA", "OBS",
        ]]
        st.caption(f"{fmt_num(len(df_filtrado))} de {fmt_num(len(df_base))} processo(s) do mês.")
        st.dataframe(
            exibicao, use_container_width=True, hide_index=True,
            column_config={
                "% Liberação IA": st.column_config.NumberColumn(format="%.1f%%"),
                "% Biometria": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )

# --- 3. Resultado ---
st.subheader("3. Resultado")
if agregado is None:
    st.info("Envie a planilha 5307 acima para classificar os processos filtrados.")
    st.stop()
if df_filtrado.empty:
    st.info("Nenhum processo com os filtros atuais.")
    st.stop()

producao, sem_dado = separar_para_cruzamento(df_filtrado)
resultado = cruzar(producao, agregado, sem_dado)
resumo = resumo_farol(resultado, base.total_processos_mes, base.total_procedimentos_mes)

resumo_s = resumo["S"]
st.markdown("**Vai pro FAROL (S)**")
m1, m2, m3 = st.columns(3)
m1.metric("Processos", fmt_num(resumo_s["processos"]))
m2.metric("Procedimentos", fmt_num(resumo_s["procedimentos"]))
with m3:
    st.metric(
        "% do mês (procedimentos)", _pct_br(resumo_s["pct_procedimentos_mes"]),
        help="Procedimentos em S ÷ total de procedimentos do mês (último REL5201, sem nenhum filtro, inclui recursos).",
    )
    st.markdown(pilula(f"{_pct_br(resumo_s['pct_processos_mes'])} dos processos", cor_texto=COR_SUCESSO), unsafe_allow_html=True)
st.caption(
    f"Total do mês: {fmt_num(base.total_procedimentos_mes)} procedimentos em {fmt_num(base.total_processos_mes)} processos "
    f"(REL5201 de {_mes_br(base.mes_5201) if base.mes_5201 else '—'}, sem filtros)."
)

tabela_resumo = pd.DataFrame([
    {
        "Balde": NOMES_BALDES[chave], "Processos": dados["processos"], "Procedimentos": dados["procedimentos"],
        "% do mês (procedimentos)": round(dados["pct_procedimentos_mes"], 1),
    }
    for chave, dados in resumo.items()
])
st.dataframe(
    tabela_resumo, use_container_width=True, hide_index=True,
    column_config={"% do mês (procedimentos)": st.column_config.NumberColumn(format="%.1f%%")},
)

if resultado.automaticos_100:
    st.info(
        f"{fmt_num(resultado.automaticos_100)} processo(s) foram pro S por estarem 100% liberados pela IA "
        "(independente da ocorrência do prestador) — marcados no OBS."
    )
if resultado.percentual_sem_ocorrencia >= LIMITE_ALERTA_SEM_OCORRENCIA:
    st.warning(
        f"{resultado.percentual_sem_ocorrencia:.0f}% dos processos ficaram sem ocorrência correspondente. "
        "Isso pode indicar que a planilha 5307 enviada não é a do período certo, ou que os nomes de prestador não batem."
    )
if resultado.nomes_corrigidos:
    with st.expander(f"{len(resultado.nomes_corrigidos)} nome(s) de prestador corrigido(s) automaticamente"):
        st.caption(
            "O nome na produção tinha caractere corrompido (normalmente um 'Ç') e foi casado com o único nome "
            "correspondente nas ocorrências."
        )
        st.dataframe(pd.DataFrame(resultado.nomes_corrigidos), use_container_width=True, hide_index=True)
if resultado.nomes_suspeitos:
    st.warning(
        f"{len(resultado.nomes_suspeitos)} processo(s) foram para 'Ocorrência não encontrada' porque o nome do prestador "
        "tem caractere corrompido e não achei candidato único nas ocorrências — não é falta de ocorrência de verdade."
    )
    st.dataframe(pd.DataFrame(resultado.nomes_suspeitos), use_container_width=True, hide_index=True)

tabs_baldes = st.tabs([f"{nome} ({fmt_num(resultado.contagem[chave])})" for chave, nome in ABAS_SAIDA])
for tab_balde, (_, nome) in zip(tabs_baldes, ABAS_SAIDA):
    with tab_balde:
        df_aba = resultado.planilhas[nome]
        if df_aba.empty:
            st.caption("Nenhum processo nesta aba.")
        else:
            st.dataframe(df_aba, use_container_width=True, hide_index=True)

st.download_button(
    "Baixar Excel (6 abas)", data=para_bytes(resultado), file_name="farol_mes_vigente.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary",
)
