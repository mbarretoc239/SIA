"""Farol Mensal (views/9_Farol_Mensal.py) -- monta a lista de processos do mês,
aplica os filtros da tela e calcula o resumo. O motor de classificação por
ocorrência (S/N/PAR/REVISAR) fica em services/farol_mensal/.

Fontes (todas já no SIA, exceto o arquivo de ocorrências, enviado na hora):
- REL5201 do mês mais recente (Supabase): status, execução, modalidade,
  prestador, quantidades, % liberação IA e login de digitador;
- base IA (Turso): especialidades/procedimentos e biometria, sobre TODAS as
  guias do processo (liberadas e não liberadas);
- REL5310 (Turso): glosas por processo, só pra coluna OBS (sinaliza, não muda
  a classificação).

Funções de montagem/filtro são puras (recebem dados, devolvem DataFrame) --
só os carregadores no fim do arquivo tocam banco.
"""

import unicodedata
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from core.relatorio_5201 import STATUS_LABELS

EXECUCOES_DISPONIVEIS = ["APP", "MISTO", "N_APP"]
# Recurso nunca entra no Farol e não há opção de incluir (pedido do usuário).
MODALIDADE_SEMPRE_EXCLUIDA = "RECURSO"
STATUS_PADRAO = ("Consistido", "Digitado")

CRITICA_TODOS = "Todos"
CRITICA_COM = "Com críticas"
CRITICA_SEM = "Sem críticas"
DIGITADOR_TODOS = "Todos"
DIGITADOR_SIM = "Sim"
DIGITADOR_NAO = "Não"

COLUNAS_IA = [
    "nu_ordem", "especialidades", "procedimentos", "total_itens",
    "itens_biometria", "itens_com_operador", "mes_referencia",
]


def _norm(texto) -> str:
    """Mesma normalização de core.amostragem._norm (maiúsculas, sem acento) --
    é como as especialidades críticas são gravadas em ordem_criticas."""
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("ASCII")
    return sem_acento.strip().upper()


@dataclass
class BaseFarol:
    """Todos os processos do REL5201 mais recente (inclusive RECURSO -- o
    total do mês pro % do resumo conta tudo) já cruzados com a base IA."""
    df: pd.DataFrame
    mes_5201: str = None
    mes_ia: str = None
    total_processos_mes: int = 0
    total_procedimentos_mes: int = 0
    tem_digitador: bool = False     # a 5201 importada tem OP_ENC_DIGITACAO
    tem_nao_avaliado: bool = False  # a 5201 importada tem QUANTIDADE_NAO_AVALIADO_IA


COLUNAS_BASE = [
    "ORDEM", "PRESTADOR", "QT_PROCEDIMENTO", "STATUS", "EXECUCAO", "MODALIDADE", "DIGITADO",
    "PCT_LIBERACAO_IA", "PCT_BIOMETRIA", "ESPECIALIDADES", "CRITICA", "SEM_DADO_IA",
    "LIBERADO_100_IA", "OBS", "_ESPECIALIDADES_SET",
]


def _numerica(df: pd.DataFrame, coluna: str) -> pd.Series:
    if coluna in df.columns:
        return pd.to_numeric(df[coluna], errors="coerce")
    return pd.Series(float("nan"), index=df.index, dtype="float64")


def _texto(df: pd.DataFrame, coluna: str) -> pd.Series:
    if coluna in df.columns:
        return df[coluna].fillna("").astype(str).str.strip()
    return pd.Series("", index=df.index, dtype="object")


def _conjunto(texto) -> frozenset:
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return frozenset()
    return frozenset(p.strip() for p in str(texto).split(",") if p.strip())


def formatar_glosas_5310(linhas: list) -> dict:
    """{nu_ordem: "REL5310: glosa 46 (3 guias); glosa 66 (1 guia)"} a partir
    das linhas (nu_ordem, glosa, qtd_guias) de listar_glosas_5310_agregado."""
    por_processo: dict = {}
    for linha in linhas or []:
        por_processo.setdefault(str(linha["nu_ordem"]), []).append(
            (str(linha["glosa"]).strip(), int(linha.get("qtd_guias") or 0))
        )

    def _chave(item):
        glosa = item[0]
        return (0, int(glosa), glosa) if glosa.isdigit() else (1, 0, glosa)

    resultado = {}
    for ordem, glosas in por_processo.items():
        partes = [
            f"glosa {glosa} ({qtd} {'guia' if qtd == 1 else 'guias'})"
            for glosa, qtd in sorted(glosas, key=_chave)
        ]
        resultado[ordem] = "REL5310: " + "; ".join(partes)
    return resultado


def montar_base_farol(
    df_5201: pd.DataFrame, processos_ia: list, glosas_5310: dict,
    ordem_criticas, procedimentos_criticos: set,
) -> BaseFarol:
    """Uma linha por processo do REL5201 mais recente, cruzada com a base IA.

    `ordem_criticas`: especialidades críticas já normalizadas (ver
    core.amostragem.carregar_regras_amostragem_cache); `procedimentos_criticos`:
    códigos críticos (core.amostragem.carregar_procedimentos_criticos).
    "Crítica" = tem especialidade crítica OU procedimento crítico, igual à
    lista da Amostragem, só que sobre TODAS as guias do processo.

    % Liberação IA = liberados / (liberados + não liberados) -- por
    procedimento, vem da 5201, 1 casa decimal (mesma conta da Amostragem).
    LIBERADO_100_IA NÃO usa esse % arredondado: exige contagem exata
    (liberados > 0, não liberados == 0 e não avaliados == 0)."""
    if df_5201 is None or df_5201.empty or "ORDEM" not in df_5201.columns:
        return BaseFarol(df=pd.DataFrame(columns=COLUNAS_BASE))

    df = df_5201
    mes_5201 = None
    if "_mes_referencia" in df.columns and df["_mes_referencia"].notna().any():
        mes_5201 = df["_mes_referencia"].dropna().max()
        df = df[df["_mes_referencia"] == mes_5201]
    df = df.drop_duplicates(subset="ORDEM").copy()
    df["ORDEM"] = df["ORDEM"].astype(str)

    tem_digitador = "OP_ENC_DIGITACAO" in df.columns and bool(df["OP_ENC_DIGITACAO"].notna().any())
    tem_nao_avaliado = "QUANTIDADE_NAO_AVALIADO_IA" in df.columns and bool(df["QUANTIDADE_NAO_AVALIADO_IA"].notna().any())

    ia = pd.DataFrame(processos_ia or [], columns=COLUNAS_IA)
    ia["nu_ordem"] = ia["nu_ordem"].astype(str)
    mes_ia = ia["mes_referencia"].dropna().max() if not ia.empty else None
    df = df.merge(ia.drop(columns="mes_referencia"), left_on="ORDEM", right_on="nu_ordem", how="left")

    # Total do mês = TODOS os processos do REL5201 mais recente (recurso,
    # fechados etc. incluídos, sem nenhum filtro) -- denominador do % do resumo.
    qt_procedimento = _numerica(df, "QT_PROCEDIMENTO").fillna(0).astype("int64")
    total_procedimentos_mes = int(qt_procedimento.sum())
    total_processos_mes = len(df)

    especialidades = df["especialidades"].apply(_conjunto)
    procedimentos = df["procedimentos"].apply(_conjunto)
    ordem_criticas = set(ordem_criticas)
    critica = (
        especialidades.apply(lambda esps: any(_norm(e) in ordem_criticas for e in esps))
        | procedimentos.apply(lambda procs: bool(procs & procedimentos_criticos))
    )

    itens_biometria = _numerica(df, "itens_biometria")
    itens_com_operador = _numerica(df, "itens_com_operador")
    total_itens = _numerica(df, "total_itens")
    pct_biometria = (itens_biometria / total_itens * 100).where(itens_com_operador > 0).round(1)

    liberados = _numerica(df, "QUANTIDADE_LIBERADOS_IA")
    nao_liberados = _numerica(df, "QUANTIDADE_NAO_LIBERADOS_IA")
    nao_avaliados = _numerica(df, "QUANTIDADE_NAO_AVALIADO_IA")
    avaliados = liberados + nao_liberados
    pct_liberacao = (liberados / avaliados * 100).where(avaliados > 0).round(1)
    liberado_100 = (liberados > 0) & (nao_liberados == 0) & (nao_avaliados == 0)

    if tem_digitador:
        login = _texto(df, "OP_ENC_DIGITACAO")
        digitado = (login != "").astype("boolean")
    else:
        digitado = pd.Series(pd.NA, index=df.index, dtype="boolean")

    status_bruto = _texto(df, "STATUS")

    base = pd.DataFrame({
        "ORDEM": df["ORDEM"],
        "PRESTADOR": _texto(df, "PRESTADOR"),
        "QT_PROCEDIMENTO": qt_procedimento,
        "STATUS": status_bruto.apply(lambda s: STATUS_LABELS.get(s, s) if s else ""),
        "EXECUCAO": _texto(df, "EXECUCAO"),
        "MODALIDADE": _texto(df, "MODALIDADE"),
        "DIGITADO": digitado,
        "PCT_LIBERACAO_IA": pct_liberacao,
        "PCT_BIOMETRIA": pct_biometria,
        "ESPECIALIDADES": especialidades.apply(lambda s: ", ".join(sorted(s))),
        "CRITICA": critica,
        "SEM_DADO_IA": df["nu_ordem"].isna(),
        "LIBERADO_100_IA": liberado_100,
        "OBS": df["ORDEM"].map(lambda o: (glosas_5310 or {}).get(o, "")),
        "_ESPECIALIDADES_SET": especialidades,
    })[COLUNAS_BASE].sort_values("ORDEM").reset_index(drop=True)

    return BaseFarol(
        df=base, mes_5201=mes_5201, mes_ia=mes_ia,
        total_processos_mes=total_processos_mes, total_procedimentos_mes=total_procedimentos_mes,
        tem_digitador=tem_digitador, tem_nao_avaliado=tem_nao_avaliado,
    )


@dataclass
class FiltrosFarol:
    """Filtros da tela. Lista/tupla vazia = sem filtro naquele campo.
    `liberacao_ia`/`biometria`: (operador, valor) de shared.ui.filtro_numerico."""
    critica: str = CRITICA_TODOS
    especialidades_extras: tuple = ()
    liberacao_ia: tuple = None
    biometria: tuple = None
    status: tuple = ()
    digitador: str = DIGITADOR_TODOS
    execucao: tuple = ()
    modalidade: tuple = ()


_OPERADORES = {
    "Maior que": lambda serie, v: serie > v,
    "Menor que": lambda serie, v: serie < v,
    "Maior ou igual a": lambda serie, v: serie >= v,
    "Menor ou igual a": lambda serie, v: serie <= v,
    "Igual a": lambda serie, v: serie == v,
}


def _filtro_numerico(df: pd.DataFrame, coluna: str, filtro) -> pd.DataFrame:
    if filtro is None:
        return df
    operador, valor = filtro
    return df[_OPERADORES[operador](df[coluna], valor)]


def opcoes_especialidades(df: pd.DataFrame) -> list:
    """Especialidades que existem na base do mês (pro botão de exceção)."""
    return sorted({e for conjunto in df["_ESPECIALIDADES_SET"] for e in conjunto})


def aplicar_filtros(df: pd.DataFrame, filtros: FiltrosFarol) -> pd.DataFrame:
    """Aplica os filtros da tela. RECURSO sai sempre. Processos SEM dado na
    base IA passam por cima dos filtros derivados da IA (crítica, % liberação,
    % biometria) -- eles precisam ser vistos manualmente e um filtro numérico
    descartaria todos (sem dado = sem número) -- e respeitam os filtros da 5201
    (status, execução, modalidade, digitador).

    Exceção de especialidade (só em "Sem críticas"): além dos processos sem
    crítica entram os que têm crítica mas cujas especialidades são TODAS
    subconjunto das escolhidas -- ex.: escolher CIRURGIA traz quem tem só
    cirurgia, nunca quem tem cirurgia + endodontia."""
    if df.empty:
        return df
    df = df[df["MODALIDADE"] != MODALIDADE_SEMPRE_EXCLUIDA]
    if filtros.status:
        df = df[df["STATUS"].isin(filtros.status)]
    if filtros.execucao:
        df = df[df["EXECUCAO"].isin(filtros.execucao)]
    if filtros.modalidade:
        df = df[df["MODALIDADE"].isin(filtros.modalidade)]
    if filtros.digitador == DIGITADOR_SIM:
        df = df[df["DIGITADO"].fillna(False).astype(bool)]
    elif filtros.digitador == DIGITADOR_NAO:
        df = df[~df["DIGITADO"].fillna(True).astype(bool)]

    sem_dado = df[df["SEM_DADO_IA"]]
    com_dado = df[~df["SEM_DADO_IA"]]

    if filtros.critica == CRITICA_COM:
        com_dado = com_dado[com_dado["CRITICA"]]
    elif filtros.critica == CRITICA_SEM:
        manter = ~com_dado["CRITICA"]
        if filtros.especialidades_extras:
            alvo = frozenset(filtros.especialidades_extras)
            manter = manter | com_dado["_ESPECIALIDADES_SET"].apply(lambda s: bool(s) and s <= alvo)
        com_dado = com_dado[manter]
    com_dado = _filtro_numerico(com_dado, "PCT_LIBERACAO_IA", filtros.liberacao_ia)
    com_dado = _filtro_numerico(com_dado, "PCT_BIOMETRIA", filtros.biometria)

    return pd.concat([com_dado, sem_dado]).sort_values("ORDEM").reset_index(drop=True)


def separar_para_cruzamento(df_filtrado: pd.DataFrame):
    """(producao, sem_dado) no formato que services.farol_mensal.processamento
    .cruzar espera. Sem dado na IA vai pra aba própria, sem classificar por
    ocorrência (revisão manual)."""
    colunas = ["ORDEM", "PRESTADOR", "QT_PROCEDIMENTO", "LIBERADO_100_IA", "OBS"]
    producao = df_filtrado[~df_filtrado["SEM_DADO_IA"]][colunas].reset_index(drop=True)
    sem_dado = df_filtrado[df_filtrado["SEM_DADO_IA"]][["ORDEM", "PRESTADOR", "QT_PROCEDIMENTO", "OBS"]].reset_index(drop=True)
    return producao, sem_dado


def resumo_farol(resultado, total_processos_mes: int, total_procedimentos_mes: int) -> dict:
    """Por balde: processos, procedimentos e % sobre o TOTAL do mês (último
    REL5201, sem filtro nenhum) -- pra prever quanto do mês o Farol adianta.
    {chave_do_balde: {"processos", "procedimentos", "pct_procedimentos_mes",
    "pct_processos_mes"}}."""
    def _pct(parte, total):
        return (parte / total * 100) if total else 0.0

    return {
        chave: {
            "processos": processos,
            "procedimentos": resultado.procedimentos.get(chave, 0),
            "pct_procedimentos_mes": _pct(resultado.procedimentos.get(chave, 0), total_procedimentos_mes),
            "pct_processos_mes": _pct(processos, total_processos_mes),
        }
        for chave, processos in resultado.contagem.items()
    }


# --- Carregadores (tocam banco; cacheados 5min, mesmo padrão de core.amostragem) ---

@st.cache_data(ttl=300)
def carregar_processos_ia() -> list:
    from shared.database import DatabaseManager
    return DatabaseManager().listar_processos_farol_agregado()


@st.cache_data(ttl=300)
def carregar_glosas_5310() -> dict:
    from shared.database import DatabaseManager
    return formatar_glosas_5310(DatabaseManager().listar_glosas_5310_agregado())
