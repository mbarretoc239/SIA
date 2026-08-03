import csv
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
    """Lê o arquivo cru (.xlsx ou .csv), sem normalizar colunas ainda."""
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

    try:
        separador = csv.Sniffer().sniff(amostra, delimiters=";,\t").delimiter
    except csv.Error:
        separador = ";"

    return pd.read_csv(arquivo, sep=separador, encoding=codificacao)


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


def resumo_geral(df: pd.DataFrame) -> dict:
    total_processos = len(df)
    total_procedimentos = int(df["QT_PROCEDIMENTO"].sum()) if "QT_PROCEDIMENTO" in df.columns and total_processos else 0
    por_status = df["STATUS"].value_counts().to_dict() if "STATUS" in df.columns else {}
    return {
        "total_processos": total_processos,
        "total_procedimentos": total_procedimentos,
        "por_status": por_status,
    }


def produtividade_por_auditor(df: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por auditor com quantos processos ele consistiu e quantos
    fechou, mais a soma de procedimentos em cada ação."""
    linhas = {}

    def _acumular(coluna_login, rotulo):
        if coluna_login not in df.columns:
            return
        sub = df[df[coluna_login].apply(_presente)]
        for login, grupo in sub.groupby(coluna_login):
            linha = linhas.setdefault(
                login, {"Auditor": login, "Consistidos": 0, "Fechados": 0, "Procedimentos": 0}
            )
            linha[rotulo] = len(grupo)
            linha["Procedimentos"] += int(grupo["QT_PROCEDIMENTO"].sum())

    _acumular("LOGIN_CONSISTENCIA", "Consistidos")
    _acumular("LOGIN_FECHAMENTO", "Fechados")

    if not linhas:
        return pd.DataFrame(columns=["Auditor", "Consistidos", "Fechados", "Total", "Procedimentos"])

    resultado = pd.DataFrame(linhas.values())
    resultado["Total"] = resultado["Consistidos"] + resultado["Fechados"]
    return resultado[["Auditor", "Consistidos", "Fechados", "Total", "Procedimentos"]].sort_values(
        "Total", ascending=False
    ).reset_index(drop=True)


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
