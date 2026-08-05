import unicodedata
from datetime import date, datetime

import pandas as pd
import streamlit as st

# Campos do REL5201 usados pelo painel de Produtividade e pelo aviso de
# status/auditor na Amostragem. O relatório tem dezenas de colunas
# (financeiro, filial, prestador, CPF/CNPJ...) que não servem a nenhuma das
# duas telas e por isso não são lidas nem armazenadas (minimiza o que fica
# gravado, mesmo cifrado).
COLUNAS_NECESSARIAS = {
    "ORDEM", "STATUS", "QT_PROCEDIMENTO",
    "DATA_CONSISTENCIA", "LOGIN_CONSISTENCIA",
    "DATA_FECHAMENTO", "LOGIN_FECHAMENTO",
}
CAMPOS_REGISTRO = list(COLUNAS_NECESSARIAS)

STATUS_LABELS = {
    "CONSISTIDO": "Consistido (em aberto)",
    "FECHADO": "Fechado",
    "GLOSADO": "Glosado",
    "CALCULADO": "Calculado",
}

# Mesmos tokens de cor já usados no resto do app (core/settings.py::TEMA) —
# reaproveita o significado que sucesso/erro/laranja já têm nas outras telas
# em vez de inventar uma paleta nova só pro gráfico.
STATUS_CORES = {
    "FECHADO": "#22C55E",
    "CONSISTIDO": "#F59E0B",
    "GLOSADO": "#EF5350",
    "CALCULADO": "#6F84A5",
    "_outro": "#6F84A5",
}


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
        return pd.read_excel(arquivo, engine="openpyxl")

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
    for col in ("DATA_CONSISTENCIA", "DATA_FECHAMENTO"):
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


COLUNAS_PRODUTIVIDADE = ["Auditor", "Fechados", "Calculados", "Total", "Procedimentos"]

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
    """Uma linha por auditor com quantos processos FECHADO/CALCULADO ele é
    responsável, e a soma de procedimentos desses processos.

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
            "Fechados": int((grupo["STATUS"] == "FECHADO").sum()),
            "Calculados": int((grupo["STATUS"] == "CALCULADO").sum()),
            "Total": len(grupo),
            "Procedimentos": int(grupo["QT_PROCEDIMENTO"].sum()),
        })

    resultado = pd.DataFrame(linhas)
    return resultado[COLUNAS_PRODUTIVIDADE].sort_values("Total", ascending=False).reset_index(drop=True)


def status_processo(df: pd.DataFrame, nu_ordem: str) -> dict:
    """Status/auditor do processo informado no snapshot atual, para evitar
    que dois auditores auditem o mesmo processo ao mesmo tempo. Visível para
    todos os roles na tela de Amostragem. Retorna None se o processo não
    estiver no relatório importado mais recente."""
    if df is None or df.empty or "ORDEM" not in df.columns:
        return None
    encontrado = df[df["ORDEM"] == str(nu_ordem).strip()]
    if encontrado.empty:
        return None
    row = encontrado.iloc[0]
    status = row.get("STATUS") or ""
    login_fechamento = row.get("LOGIN_FECHAMENTO")
    login_consistencia = row.get("LOGIN_CONSISTENCIA")

    if status == "FECHADO" and _presente(login_fechamento):
        auditor, data, situacao = login_fechamento, row.get("DATA_FECHAMENTO"), "fechado"
    elif _presente(login_consistencia):
        auditor, data, situacao = login_consistencia, row.get("DATA_CONSISTENCIA"), "em_analise"
    else:
        auditor, data, situacao = None, None, "livre"

    data_fmt = data.strftime("%d/%m/%Y %H:%M") if pd.notna(data) else ""

    return {
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "auditor": auditor,
        "data_fmt": data_fmt,
        "situacao": situacao,
    }
