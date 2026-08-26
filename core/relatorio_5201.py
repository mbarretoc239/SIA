import unicodedata
import zipfile
from datetime import date, datetime

import pandas as pd
import streamlit as st

# Campos do REL5201 usados pelo painel de Produtividade e pelo aviso de
# status/auditor na Amostragem. O relatório tem dezenas de colunas
# (financeiro, filial, CPF/CNPJ...) que não servem a nenhuma das duas telas
# e por isso não são lidas nem armazenadas (minimiza o que fica gravado,
# mesmo cifrado).
COLUNAS_NECESSARIAS = {
    "ORDEM", "STATUS", "QT_PROCEDIMENTO",
    "DATA_CONSISTENCIA", "LOGIN_CONSISTENCIA",
    "DATA_FECHAMENTO", "LOGIN_FECHAMENTO",
}
# Colunas extras, só pra cortes de canal de entrada do processo (EXECUCAO:
# App/Misto/Não App; DATA_RECEBIMENTO_PROCESSO_FISICO: data de entrada), pra
# contagem oficial de guias (QT_GUIAS/QUANTIDADE_*_LIBERADOS_IA -- vem pronta
# do sistema, mais confiável que recalcular a partir da planilha da base IA,
# que é só um snapshot mensal e pode ficar defasado) e pro nome do prestador
# (PRESTADOR -- reversão parcial e consciente da decisão de não capturar
# dado de prestador: só o nome, sem CPF/CNPJ, usado como chave pra cruzar
# com o histórico de glosas do Relatório 5302/5310 -- ver
# historico_glosas_prestador). Opcionais -- se o arquivo não tiver (formato
# mais antigo, ou exportação diferente), a importação não falha, só fica
# sem esse corte específico.
# VALOR_COBRADO/VALOR_CALCULADO: pra calcular o % de glosa em R$ por
# processo (glosado = cobrado - calculado, recalculado aqui em vez de usar
# a coluna VALOR_GLOSA do relatório -- por pedido explícito do time,
# receio de a coluna vir inconsistente).
COLUNAS_OPCIONAIS = {
    "EXECUCAO", "MODALIDADE", "DATA_RECEBIMENTO_PROCESSO_FISICO",
    "QT_GUIAS", "QUANTIDADE_LIBERADOS_IA", "QUANTIDADE_NAO_LIBERADOS_IA",
    "PRESTADOR", "VALOR_COBRADO", "VALOR_CALCULADO",
}
CAMPOS_REGISTRO = list(COLUNAS_NECESSARIAS | COLUNAS_OPCIONAIS)

STATUS_LABELS = {
    "CONSISTIDO": "Consistido",
    "FECHADO": "Fechado",
    "GLOSADO": "Glosado",
    "CALCULADO": "Calculado",
    "CANCELADO": "Cancelado",
    "DIGITADO": "Digitado",
}

# Mesmos tokens de cor já usados no resto do app (core/settings.py::TEMA) —
# reaproveita o significado que sucesso/erro/laranja já têm nas outras telas
# em vez de inventar uma paleta nova só pro gráfico.
STATUS_CORES = {
    "FECHADO": "#22C55E",
    "CONSISTIDO": "#F59E0B",
    "GLOSADO": "#EF5350",
    "CALCULADO": "#6F84A5",
    "CANCELADO": "#B91C1C",
    "DIGITADO": "#8B5CF6",
    "_outro": "#6F84A5",
}

# Agrupamentos usados no resumo rápido da Visão Geral: "analisado" é estado
# final (processo/procedimento já passou pelo auditor); "cancelado/glosado"
# é o que não vai gerar pagamento; "consistido/digitado" é o que ainda está
# em algum ponto do fluxo antes da analise final.
STATUS_ANALISADO = {"FECHADO", "CALCULADO"}
STATUS_CANCELADO_GLOSADO = {"CANCELADO", "GLOSADO"}
STATUS_CONSISTIDO_DIGITADO = {"CONSISTIDO", "DIGITADO"}


def _norm(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("ASCII")
    return sem_acento.strip().upper()


def _presente(valor) -> bool:
    if valor is None:
        return False
    if isinstance(valor, float) and pd.isna(valor):
        return False
    return str(valor).strip() != ""


def _ler_bruto(arquivo) -> pd.DataFrame:
    """Lê o arquivo cru (.xlsx ou .csv), sem normalizar colunas ainda.

    Números no CSV seguem o padrão BR (ex.: "3.806" = três mil oitocentos e
    seis, não 3,806) — daí thousands="." e decimal=",". Sem isso,
    QT_PROCEDIMENTO com milhar vira um número bem menor (ex.: "3.806" lido
    como float 3.806, truncado pra 3 ao converter pra inteiro).

    O separador de campo é detectado pela primeira linha (cabeçalho): contar
    ";"/","/tab só nos nomes de coluna evita confundir separador de campo com
    separador decimal (que também usa vírgula nas linhas de dados).
    """
    nome = (getattr(arquivo, "name", "") or "").lower()
    if not nome.endswith(".csv"):
        try:
            return pd.read_excel(arquivo, engine="openpyxl")
        except zipfile.BadZipFile:
            # .xlsx é um zip por dentro -- esse erro sai como "File is not a
            # zip file" (mensagem do Python, sem contexto nenhum pro
            # usuário) sempre que o arquivo está corrompido, é um .xls
            # antigo só renomeado pra .xlsx, ou o download/upload foi
            # interrompido no meio.
            raise ValueError(
                f"O arquivo '{arquivo.name}' não é um .xlsx válido (pode estar corrompido, "
                "ser um .xls antigo renomeado, ou o download ter sido interrompido). "
                "Baixe o relatório de novo e tente subir novamente."
            )

    arquivo.seek(0)
    bruto = arquivo.read()
    arquivo.seek(0)
    for codificacao in ("utf-8-sig", "latin-1"):
        try:
            amostra = bruto[:4096].decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Não foi possível identificar a codificação do CSV.")

    primeira_linha = amostra.splitlines()[0] if amostra else ""
    candidatos = {c: primeira_linha.count(c) for c in (";", ",", "\t")}
    separador = max(candidatos, key=candidatos.get) if any(candidatos.values()) else ";"

    return pd.read_csv(arquivo, sep=separador, encoding=codificacao, thousands=".", decimal=",")


def ler_relatorio_5201(arquivo) -> pd.DataFrame:
    """Lê o REL5201 (.xlsx ou .csv) via pandas e devolve um DataFrame só com
    as colunas usadas pelo painel de status/produtividade, já normalizadas."""
    df = _ler_bruto(arquivo)
    df.columns = [_norm(c) for c in df.columns]

    faltantes = COLUNAS_NECESSARIAS - set(df.columns)
    if faltantes:
        raise ValueError(
            "Colunas não encontradas no relatório: " + ", ".join(sorted(faltantes))
        )

    df = df[df["ORDEM"].notna()].copy()
    df["ORDEM"] = df["ORDEM"].astype("int64").astype(str)
    df["STATUS"] = df["STATUS"].fillna("").apply(_norm)
    df["QT_PROCEDIMENTO"] = pd.to_numeric(df["QT_PROCEDIMENTO"], errors="coerce").fillna(0).astype(int)
    for col in ("DATA_CONSISTENCIA", "DATA_FECHAMENTO"):
        df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    if "EXECUCAO" in df.columns:
        df["EXECUCAO"] = df["EXECUCAO"].fillna("").apply(_norm)
    else:
        df["EXECUCAO"] = ""

    if "MODALIDADE" in df.columns:
        df["MODALIDADE"] = df["MODALIDADE"].fillna("").apply(_norm)
    else:
        df["MODALIDADE"] = ""

    if "DATA_RECEBIMENTO_PROCESSO_FISICO" in df.columns:
        df["DATA_RECEBIMENTO_PROCESSO_FISICO"] = pd.to_datetime(
            df["DATA_RECEBIMENTO_PROCESSO_FISICO"], errors="coerce", dayfirst=True
        )
    else:
        df["DATA_RECEBIMENTO_PROCESSO_FISICO"] = pd.NaT

    # Numéricos opcionais: None (não 0) quando o arquivo não tem a coluna --
    # "não sei" é diferente de "zero guias".
    for col in ("QT_GUIAS", "QUANTIDADE_LIBERADOS_IA", "QUANTIDADE_NAO_LIBERADOS_IA"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        else:
            df[col] = pd.array([None] * len(df), dtype="Int64")

    # Valores em R$: None (não 0) quando a coluna não existe no arquivo --
    # mesmo cuidado do QT_GUIAS acima, "sem dado" != "cobrado zero".
    for col in ("VALOR_COBRADO", "VALOR_CALCULADO"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = pd.array([None] * len(df), dtype="float64")

    if "PRESTADOR" in df.columns:
        # Sem _norm() (que uppercase e tira acento) -- mantém o mesmo
        # formato do nome que o parser do 5302 extrai, pra bater na hora de
        # cruzar (ver historico_glosas_prestador).
        df["PRESTADOR"] = df["PRESTADOR"].fillna("").astype(str).str.strip()
    else:
        df["PRESTADOR"] = ""

    return df[CAMPOS_REGISTRO]


def montar_registros(df: pd.DataFrame) -> list:
    """Converte o DataFrame lido em uma lista de dicts JSON-serializáveis —
    um payload por processo, pronto para ser criptografado e gravado."""
    registros = []
    for _, row in df.iterrows():
        registro = {}
        for campo in CAMPOS_REGISTRO:
            valor = row[campo]
            if pd.isna(valor):
                registro[campo] = None
            elif isinstance(valor, (pd.Timestamp, datetime, date)):
                registro[campo] = valor.isoformat()
            else:
                registro[campo] = valor.item() if hasattr(valor, "item") else valor
        registros.append(registro)
    return registros


def registros_para_df(registros: list) -> pd.DataFrame:
    """Reconstrói o DataFrame a partir dos registros já decifrados (vindos do
    Supabase), convertendo as datas de volta para datetime."""
    if not registros:
        return pd.DataFrame(columns=CAMPOS_REGISTRO)
    df = pd.DataFrame(registros)
    for col in ("DATA_CONSISTENCIA", "DATA_FECHAMENTO", "DATA_RECEBIMENTO_PROCESSO_FISICO"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


@st.cache_data(ttl=300)
def carregar_dados_atuais() -> pd.DataFrame:
    """Busca e decifra o snapshot atual do REL5201 (cacheado por 5min —
    evita decifrar todas as linhas a cada rerun de Amostragem/Produtividade)."""
    from shared.database import DatabaseManager
    db = DatabaseManager()
    registros = db.carregar_relatorio_5201()
    return registros_para_df(registros)


def meses_disponiveis(df: pd.DataFrame) -> list:
    """Meses de referência (mais recente primeiro) presentes no que está
    hoje retido no banco (só os 2 mais recentes — ver _importar_por_mes)."""
    if df.empty or "_mes_referencia" not in df.columns:
        return []
    return sorted(df["_mes_referencia"].dropna().unique().tolist(), reverse=True)


def resumo_geral(df: pd.DataFrame) -> dict:
    total_processos = len(df)
    total_procedimentos = int(df["QT_PROCEDIMENTO"].sum()) if "QT_PROCEDIMENTO" in df.columns and total_processos else 0
    por_status = df["STATUS"].value_counts().to_dict() if "STATUS" in df.columns else {}
    procedimentos_por_status = (
        df.groupby("STATUS")["QT_PROCEDIMENTO"].sum().astype(int).to_dict()
        if "STATUS" in df.columns and "QT_PROCEDIMENTO" in df.columns and total_processos
        else {}
    )
    return {
        "total_processos": total_processos,
        "total_procedimentos": total_procedimentos,
        "por_status": por_status,
        "procedimentos_por_status": procedimentos_por_status,
    }


def agrupar_por_status(contagens: dict) -> dict:
    """Soma um dict {STATUS: quantidade} (processos ou procedimentos, tanto
    faz) nos 3 agrupamentos usados no resumo rápido da Visão Geral."""
    return {
        "analisado": sum(contagens.get(s, 0) for s in STATUS_ANALISADO),
        "cancelado_glosado": sum(contagens.get(s, 0) for s in STATUS_CANCELADO_GLOSADO),
        "consistido_digitado": sum(contagens.get(s, 0) for s in STATUS_CONSISTIDO_DIGITADO),
    }


# O valor real da coluna EXECUCAO pra "Não App" vem com underscore
# ("N_APP"), não espaço -- confirmado direto nos dados decifrados depois
# que essa métrica deu 0 mesmo com dado importado (ver conversa 2026-08-05).
EXECUCAO_COM_DATA_OBRIGATORIA = {"MISTO", "N_APP"}

# Rótulos amigáveis pra exibição -- os valores crus (normalizados por _norm,
# maiúsculo e sem acento) ficam feios direto na tabela ("N_APP", "FIXO").
# Valor não mapeado (planilha antiga, ou variante nova) cai no fallback
# _titulo_amigavel, não fica em branco.
EXECUCAO_LABELS = {"APP": "App", "MISTO": "Misto", "N_APP": "Não App"}
MODALIDADE_LABELS = {"FIXO": "Fixo", "PACOTE": "Pacote", "NORMAL": "Normal", "RECURSO": "Recurso"}


def _titulo_amigavel(valor: str, mapa: dict) -> str:
    if not valor:
        return "—"
    return mapa.get(valor, valor.replace("_", " ").title())


def procedimentos_consistido_digitado_por_canal(df: pd.DataFrame) -> int:
    """Procedimentos com STATUS Consistido/Digitado, contando: todo EXECUCAO
    "APP" (não depende de data de entrada) + "MISTO"/"N_APP" que já têm
    DATA_RECEBIMENTO_PROCESSO_FISICO preenchida (chegada física já
    registrada — sem isso, o processo físico ainda nem deu entrada)."""
    colunas = {"STATUS", "EXECUCAO", "QT_PROCEDIMENTO", "DATA_RECEBIMENTO_PROCESSO_FISICO"}
    if df.empty or not colunas <= set(df.columns):
        return 0

    em_fluxo = df[df["STATUS"].isin(STATUS_CONSISTIDO_DIGITADO)]
    app = em_fluxo[em_fluxo["EXECUCAO"] == "APP"]
    misto_napp_com_data = em_fluxo[
        em_fluxo["EXECUCAO"].isin(EXECUCAO_COM_DATA_OBRIGATORIA)
        & em_fluxo["DATA_RECEBIMENTO_PROCESSO_FISICO"].notna()
    ]
    return int(app["QT_PROCEDIMENTO"].sum() + misto_napp_com_data["QT_PROCEDIMENTO"].sum())


def _pct_glosa_valor(valor_cobrado, valor_calculado):
    """% de glosa em R$ de UM processo: (cobrado - calculado) / cobrado.
    Recalculado a partir de VALOR_COBRADO/VALOR_CALCULADO -- não usa a
    coluna VALOR_GLOSA do próprio relatório, por pedido explícito (receio
    de vir inconsistente). None quando falta um dos dois valores (arquivo
    sem essas colunas) ou valor_cobrado <= 0 (nada a dividir)."""
    if pd.isna(valor_cobrado) or pd.isna(valor_calculado) or valor_cobrado <= 0:
        return None
    return (valor_cobrado - valor_calculado) / valor_cobrado * 100


def _pct_glosa_grupo(grupo: pd.DataFrame):
    """% de glosa em R$ agregado de um GRUPO de processos (ex.: todos os de
    um auditor) -- soma dos valores primeiro, divide depois (não a média
    dos percentuais de cada processo). Isso pesa cada processo pelo seu
    valor real: um processo de R$50.000 não pode contar igual a um de R$44
    só porque os dois têm 1 processo cada."""
    if "VALOR_COBRADO" not in grupo.columns or "VALOR_CALCULADO" not in grupo.columns:
        return None
    valido = grupo["VALOR_COBRADO"].notna() & grupo["VALOR_CALCULADO"].notna() & (grupo["VALOR_COBRADO"] > 0)
    cobrado_total = grupo.loc[valido, "VALOR_COBRADO"].sum()
    if cobrado_total <= 0:
        return None
    calculado_total = grupo.loc[valido, "VALOR_CALCULADO"].sum()
    return (cobrado_total - calculado_total) / cobrado_total * 100


def _fmt_pct_glosa(pct) -> str:
    if pct is None:
        return "—"
    return f"{pct:.1f}".replace(".", ",") + "%"


COLUNAS_PRODUTIVIDADE = ["Auditor", "Fechados", "Calculados", "Total", "% Glosa"]

# Só processos num estado final contam como produtividade — CONSISTIDO ainda
# está em aberto e GLOSADO não é uma ação do auditor.
STATUS_PRODUTIVOS = {"FECHADO", "CALCULADO"}


def _produtivos_com_auditor_e_data(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra pra só FECHADO/CALCULADO com auditor identificável, e adiciona
    as colunas auxiliares `_auditor` (LOGIN_FECHAMENTO ou LOGIN_CONSISTENCIA)
    e `_data` (a data correspondente a esse mesmo login) — base compartilhada
    por produtividade_por_auditor e dias_disponiveis."""
    if df.empty or "STATUS" not in df.columns:
        return pd.DataFrame(columns=list(df.columns) + ["_auditor", "_data"])

    produtivos = df[df["STATUS"].isin(STATUS_PRODUTIVOS)].copy()
    if produtivos.empty:
        return produtivos.assign(_auditor=None, _data=None)

    tem_fechamento = produtivos["LOGIN_FECHAMENTO"].apply(_presente)
    produtivos["_auditor"] = produtivos["LOGIN_FECHAMENTO"].where(tem_fechamento, produtivos["LOGIN_CONSISTENCIA"])
    produtivos["_data"] = produtivos["DATA_FECHAMENTO"].where(tem_fechamento, produtivos["DATA_CONSISTENCIA"])
    return produtivos[produtivos["_auditor"].apply(_presente)]


def dias_disponiveis(df: pd.DataFrame) -> list:
    """Datas (mais recente primeiro) em que houve algum FECHADO/CALCULADO
    no snapshot atual — usadas pra popular o seletor de dia da Produtividade."""
    produtivos = _produtivos_com_auditor_e_data(df)
    if produtivos.empty:
        return []
    datas = produtivos["_data"].dropna().dt.date.unique().tolist()
    return sorted(datas, reverse=True)


def produtividade_por_auditor(df: pd.DataFrame, dia=None, auditor: str = None) -> pd.DataFrame:
    """Uma linha por auditor com a soma de PROCEDIMENTOS (não processos) dos
    processos FECHADO/CALCULADO sob sua responsabilidade -- procedimentos é
    a métrica oficial de produtividade, processos é só o contêiner.

    O auditor responsável é LOGIN_FECHAMENTO quando presente (processos
    FECHADO sempre têm) — senão LOGIN_CONSISTENCIA, que é o campo preenchido
    nos processos CALCULADO. Cada processo entra uma única vez (não há
    dupla contagem entre as duas colunas de status).

    `dia`: se informado (date), restringe aos processos resolvidos naquele
    dia (pela mesma data usada como `_auditor` — DATA_FECHAMENTO ou
    DATA_CONSISTENCIA). `auditor`: se informado, restringe a esse login
    (comparação case-insensitive) — usado pra "minha produtividade".
    """
    produtivos = _produtivos_com_auditor_e_data(df)
    if produtivos.empty:
        return pd.DataFrame(columns=COLUNAS_PRODUTIVIDADE)

    if dia is not None:
        produtivos = produtivos[produtivos["_data"].dt.date == dia]
    if auditor is not None:
        alvo = auditor.strip().upper()
        produtivos = produtivos[produtivos["_auditor"].astype(str).str.strip().str.upper() == alvo]

    if produtivos.empty:
        return pd.DataFrame(columns=COLUNAS_PRODUTIVIDADE)

    linhas = []
    for nome_auditor, grupo in produtivos.groupby("_auditor"):
        linhas.append({
            "Auditor": nome_auditor,
            "Fechados": int(grupo.loc[grupo["STATUS"] == "FECHADO", "QT_PROCEDIMENTO"].sum()),
            "Calculados": int(grupo.loc[grupo["STATUS"] == "CALCULADO", "QT_PROCEDIMENTO"].sum()),
            "Total": int(grupo["QT_PROCEDIMENTO"].sum()),
            "% Glosa": _fmt_pct_glosa(_pct_glosa_grupo(grupo)),
        })

    resultado = pd.DataFrame(linhas)
    return resultado[COLUNAS_PRODUTIVIDADE].sort_values("Total", ascending=False).reset_index(drop=True)


def _formatar_duracao(minutos: float) -> str:
    """minutos -> "Xd Yh", "Xh Ymin" ou "Xmin", omitindo unidades zeradas."""
    total = int(round(minutos))
    horas, resto_min = divmod(total, 60)
    dias, resto_horas = divmod(horas, 24)
    partes = []
    if dias:
        partes.append(f"{dias}d")
    if resto_horas:
        partes.append(f"{resto_horas}h")
    if resto_min or not partes:
        partes.append(f"{resto_min}min")
    return " ".join(partes)


def detalhe_processos_periodo(df: pd.DataFrame, auditor: str, dia=None) -> pd.DataFrame:
    """Uma linha por processo Fechado/Calculado do auditor -- número do
    processo, status, as duas datas e o tempo entre elas. `dia` (date)
    restringe a um dia específico; sem ele, lista todo o período já
    filtrado em `df` (normalmente o mês selecionado) -- é a lista completa
    de processos que o auditor tocou, pra checagem tanto dele quanto do
    Gestor.

    Tempo (Consistência -> Fechamento) só é calculado para Fechado com as
    duas datas presentes e em ordem (delta > 0, protege contra inconsistência
    na planilha) — Calculado não tem uma segunda data e aparece com "—".
    `_minutos` fica na saída (float ou None) pra tempo_medio_resolucao usar;
    quem for exibir a tabela deve descartar essa coluna auxiliar.
    """
    colunas = ["Processo", "Status", "Execução", "Modalidade", "Consistência", "Fechamento", "Tempo", "% Glosa", "_minutos"]
    produtivos = _produtivos_com_auditor_e_data(df)
    if produtivos.empty:
        return pd.DataFrame(columns=colunas)

    alvo = auditor.strip().upper()
    filtro = produtivos["_auditor"].astype(str).str.strip().str.upper() == alvo
    if dia is not None:
        filtro &= produtivos["_data"].dt.date == dia
    filtrado = produtivos[filtro]
    if filtrado.empty:
        return pd.DataFrame(columns=colunas)

    linhas = []
    for _, row in filtrado.iterrows():
        consistencia = row["DATA_CONSISTENCIA"]
        fechamento = row["DATA_FECHAMENTO"]
        minutos = None
        if row["STATUS"] == "FECHADO" and pd.notna(consistencia) and pd.notna(fechamento):
            delta_min = (fechamento - consistencia).total_seconds() / 60
            if delta_min > 0:
                minutos = delta_min
        linhas.append({
            "Processo": row["ORDEM"],
            "Status": STATUS_LABELS.get(row["STATUS"], row["STATUS"]),
            "Execução": _titulo_amigavel(row.get("EXECUCAO", ""), EXECUCAO_LABELS),
            "Modalidade": _titulo_amigavel(row.get("MODALIDADE", ""), MODALIDADE_LABELS),
            "Consistência": consistencia.strftime("%d/%m/%Y %H:%M") if pd.notna(consistencia) else "—",
            "Fechamento": fechamento.strftime("%d/%m/%Y %H:%M") if pd.notna(fechamento) else "—",
            "Tempo": _formatar_duracao(minutos) if minutos is not None else "—",
            "% Glosa": _fmt_pct_glosa(_pct_glosa_valor(row.get("VALOR_COBRADO"), row.get("VALOR_CALCULADO"))),
            "_minutos": minutos,
        })

    return pd.DataFrame(linhas)[colunas].sort_values("Consistência").reset_index(drop=True)


def tempo_medio_resolucao(detalhe: pd.DataFrame):
    """Média de `_minutos` de detalhe_processos_dia (ignora os sem duração
    computável), formatada com _formatar_duracao. None se nenhum processo do
    dia tiver duração computável (ex.: só Calculados, sem nenhum Fechado)."""
    if detalhe.empty or "_minutos" not in detalhe.columns:
        return None
    validos = detalhe["_minutos"].dropna()
    if validos.empty:
        return None
    return _formatar_duracao(validos.mean())


def formatar_status_processo(registro: dict) -> dict:
    """Monta o dict de status/auditor a partir de um registro do REL5201
    (STATUS, LOGIN_FECHAMENTO/CONSISTENCIA, DATA_FECHAMENTO/CONSISTENCIA).
    Usado tanto por status_processo (DataFrame completo já carregado) quanto
    por DatabaseManager.buscar_status_processo (busca direta de 1 processo,
    sem carregar/decifrar o snapshot inteiro)."""
    status = registro.get("STATUS") or ""
    login_fechamento = registro.get("LOGIN_FECHAMENTO")
    login_consistencia = registro.get("LOGIN_CONSISTENCIA")

    if status == "FECHADO" and _presente(login_fechamento):
        auditor, data, situacao = login_fechamento, registro.get("DATA_FECHAMENTO"), "fechado"
    elif _presente(login_consistencia):
        auditor, data, situacao = login_consistencia, registro.get("DATA_CONSISTENCIA"), "em_analise"
    else:
        auditor, data, situacao = None, None, "livre"

    data_ts = pd.to_datetime(data, errors="coerce")
    data_fmt = data_ts.strftime("%d/%m/%Y %H:%M") if pd.notna(data_ts) else ""

    def _int_ou_none(valor):
        # registro pode vir de dois lugares: JSON decifrado direto (None
        # de verdade pra campo faltante) ou reconstruído via pandas
        # (status_processo -> DataFrame -> .to_dict(), onde campo faltante
        # vira NaN/pd.NA, não None) -- pd.isna() cobre os dois casos, `is
        # not None` sozinho deixaria NaN passar e quebrar no int(NaN).
        if valor is None or pd.isna(valor):
            return None
        return int(valor)

    qt_procedimento = _int_ou_none(registro.get("QT_PROCEDIMENTO"))
    qt_guias = _int_ou_none(registro.get("QT_GUIAS"))
    qt_guias_nao_liberadas = _int_ou_none(registro.get("QUANTIDADE_NAO_LIBERADOS_IA"))
    qt_liberados_ia = _int_ou_none(registro.get("QUANTIDADE_LIBERADOS_IA"))
    execucao_bruta = registro.get("EXECUCAO")
    execucao = execucao_bruta if execucao_bruta and pd.notna(execucao_bruta) else None

    # % Liberação IA = liberados / (liberados + não liberados) -- é por
    # PROCEDIMENTO avaliado pela IA, não por guia (mesma conta da lista de
    # processos, ver core/amostragem.py::montar_lista_processos_mes).
    pct_liberacao_ia = None
    if qt_liberados_ia is not None and qt_guias_nao_liberadas is not None:
        total_avaliado = qt_liberados_ia + qt_guias_nao_liberadas
        if total_avaliado > 0:
            pct_liberacao_ia = round(qt_liberados_ia / total_avaliado * 100, 1)

    return {
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "auditor": auditor,
        "data_fmt": data_fmt,
        "situacao": situacao,
        # Já vem no mesmo payload decifrado (REL5201) -- não é uma busca
        # extra, só não era exposto no resumo. Mostrar isso na tela de
        # Amostragem cruza com o PowerBI sem custo de latência adicional.
        "qt_procedimento": qt_procedimento,
        # Contagem oficial de guias (vem pronta do REL5201) -- não recalcula
        # a partir da planilha da base IA, que é só um snapshot mensal.
        "qt_guias": qt_guias,
        "qt_guias_nao_liberadas": qt_guias_nao_liberadas,
        "pct_liberacao_ia": pct_liberacao_ia,
        # MISTO/N_APP/APP -- canal de entrada do processo.
        "execucao": execucao,
        # Nome do prestador -- chave pra cruzar com o histórico de glosas
        # (ver DatabaseManager.obter_risco_prestador).
        "prestador": (registro.get("PRESTADOR") or "").strip() or None,
    }


def status_processo(df: pd.DataFrame, nu_ordem: str) -> dict:
    """Status/auditor do processo informado no snapshot atual, para evitar
    que dois auditores auditem o mesmo processo ao mesmo tempo. Visível para
    todos os roles na tela de Amostragem. Retorna None se o processo não
    estiver no relatório importado mais recente.

    Prefira DatabaseManager.buscar_status_processo quando só precisar de UM
    processo — evita carregar/decifrar o snapshot inteiro."""
    if df is None or df.empty or "ORDEM" not in df.columns:
        return None
    encontrado = df[df["ORDEM"] == str(nu_ordem).strip()]
    if encontrado.empty:
        return None
    return formatar_status_processo(encontrado.iloc[0].to_dict())


@st.cache_data(ttl=300)
def obter_risco_prestador_cacheado(prestador: str) -> dict:
    """Wrapper cacheado de DatabaseManager.obter_risco_prestador (5min --
    mesmo padrão de carregar_dados_atuais), pra não bater no Supabase toda
    vez que a tela de Amostragem faz rerun com o mesmo processo aberto."""
    from shared.database import DatabaseManager
    db = DatabaseManager()
    return db.obter_risco_prestador(prestador)


@st.cache_data(ttl=300)
def obter_detalhe_glosas_prestador_cacheado(prestador: str) -> list:
    """Wrapper cacheado de DatabaseManager.obter_detalhe_glosas_prestador --
    mesmo padrão de obter_risco_prestador_cacheado."""
    from shared.database import DatabaseManager
    db = DatabaseManager()
    return db.obter_detalhe_glosas_prestador(prestador)
