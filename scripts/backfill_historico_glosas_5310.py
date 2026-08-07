"""Backfill único do histórico de glosas por prestador a partir dos 3
relatórios REL5310 (jun/jul/ago 2026) fornecidos pelo usuário.

Lê cada planilha, filtra só as linhas com glosa de fato (GLOSA não nulo),
deduplica por (GUIA, CODIGO DO PROCEDIMENTO GLOSADO, GLOSA, SUBGLOSA) --
a mesma chave da constraint UNIQUE da tabela historico_glosas_prestador --
e envia via DatabaseManager.salvar_historico_glosas (idempotente,
ON CONFLICT DO NOTHING). Rodar uma única vez.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from shared.database import DatabaseManager

ARQUIVOS = [
    r"C:\Users\matheus.cardoso\Desktop\202606_5310.xlsx",
    r"C:\Users\matheus.cardoso\Desktop\202607_5310.xlsx",
    r"C:\Users\matheus.cardoso\Desktop\202608_5310_.xlsx",
]


def _texto(v) -> str:
    if pd.isna(v):
        return ""
    # Colunas de código (procedimento/glosa/subglosa) vêm como float no
    # pandas quando a coluna do Excel tem alguma célula vazia (NaN força o
    # dtype pra float64) -- sem isso, "430" vira "430.0" no banco.
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _mes_referencia(data_producao) -> str:
    if pd.isna(data_producao):
        return ""
    ts = pd.to_datetime(data_producao, errors="coerce")
    if pd.isna(ts):
        return ""
    return ts.strftime("%Y-%m")


def montar_registros(caminho: str) -> list:
    df = pd.read_excel(caminho)
    df = df[df["GLOSA"].notna() & df["GUIA"].notna() & df["CODIGO DO PROCEDIMENTO GLOSADO"].notna()]

    vistos = set()
    registros = []
    for _, row in df.iterrows():
        guia = _texto(row["GUIA"])
        procedimento = _texto(row["CODIGO DO PROCEDIMENTO GLOSADO"])
        glosa = _texto(row["GLOSA"])
        subglosa = _texto(row.get("SUBGLOSA"))
        chave = (guia, procedimento, glosa, subglosa)
        if chave in vistos:
            continue
        vistos.add(chave)
        registros.append({
            "processo": _texto(row.get("PROCESSO")),
            "prestador": _texto(row.get("PRESTADOR")),
            "mes_referencia": _mes_referencia(row.get("DATA DE PRODUCAO")),
            "procedimento": procedimento,
            "glosa": glosa,
            "subglosa": subglosa,
            "justificativa": _texto(row.get("JUSTIFICATIVA DA GLOSA")),
            "guia": guia,
            "origem": "5310_backfill",
        })
    return registros


def main():
    db = DatabaseManager()
    total_enviado = 0
    for caminho in ARQUIVOS:
        registros = montar_registros(caminho)
        print(f"{os.path.basename(caminho)} -> {len(registros)} registros deduplicados")
        if registros:
            enviados = db.salvar_historico_glosas(registros)
            total_enviado += enviados
            print(f"  enviados ao Supabase: {enviados}")
    print(f"\nTOTAL enviado (3 arquivos): {total_enviado}")


if __name__ == "__main__":
    main()
