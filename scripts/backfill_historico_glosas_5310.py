"""Backfill único do histórico de glosas por prestador a partir dos 3
relatórios REL5310 (jun/jul/ago 2026) fornecidos pelo usuário.

Lê cada planilha, filtra só as linhas com glosa de fato (GLOSA não nulo),
deduplica por (GUIA, CODIGO DO PROCEDIMENTO GLOSADO, GLOSA, SUBGLOSA) --
a mesma chave da constraint UNIQUE da tabela historico_glosas_prestador --
e envia via DatabaseManager.salvar_historico_glosas (idempotente,
ON CONFLICT DO NOTHING). Rodar uma única vez.

O REL5310 traz o código TUSS "de verdade" (longo, ex.: 85200158) em
CODIGO DO PROCEDIMENTO GLOSADO -- diferente do código curto interno usado
em tabela_procedimentos/base IA (ex.: 2015), sem tabela de conversão entre
os dois. Cruza pelo NOME do procedimento (normalizado) contra o catálogo;
quando bate, usa o código curto; quando não bate, cai pro TUSS do arquivo
mesmo (ver bug real encontrado em 2026-09: a primeira versão deste script
gravou o TUSS puro em 76 mil linhas, corrigido depois via migração SQL
direta no Supabase -- não repetir esse erro num backfill futuro).
"""
import sys
import os
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from services.relatorio_5302.glosa_matcher import carregar_mapa_procedimentos
from shared.database import DatabaseManager


def _norm(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("ASCII")
    return sem_acento.strip().upper()

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


def montar_registros(caminho: str, mapa_por_descricao: dict) -> list:
    df = pd.read_excel(caminho)
    df = df[df["GLOSA"].notna() & df["GUIA"].notna() & df["CODIGO DO PROCEDIMENTO GLOSADO"].notna()]

    vistos = set()
    registros = []
    for _, row in df.iterrows():
        guia = _texto(row["GUIA"])
        procedimento_tuss = _texto(row["CODIGO DO PROCEDIMENTO GLOSADO"])
        descricao_glosado = _texto(row.get("NOMECLATURA DO PROCEDIMENTO GLOSADO"))
        # Cruza pelo nome pro código curto interno -- sem isso, grava o
        # TUSS longo direto (ver bug de 2026-09 no cabeçalho deste arquivo).
        procedimento = mapa_por_descricao.get(_norm(descricao_glosado)) or procedimento_tuss
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
            "descricao_procedimento": descricao_glosado,
            "guia": guia,
            "origem": "5310_backfill",
        })
    return registros


def main():
    db = DatabaseManager()

    mapa_por_descricao = {}
    for codigo_curto, descricao in carregar_mapa_procedimentos().items():
        mapa_por_descricao.setdefault(_norm(descricao), codigo_curto)

    total_enviado = 0
    for caminho in ARQUIVOS:
        registros = montar_registros(caminho, mapa_por_descricao)
        nao_cruzados = sum(1 for r in registros if len(r["procedimento"]) > 6)
        print(
            f"{os.path.basename(caminho)} -> {len(registros)} registros deduplicados "
            f"({nao_cruzados} sem cruzamento por nome, ficaram com o TUSS do arquivo)"
        )
        if registros:
            enviados = db.salvar_historico_glosas(registros)
            total_enviado += enviados
            print(f"  enviados ao Supabase: {enviados}")
    print(f"\nTOTAL enviado (3 arquivos): {total_enviado}")


if __name__ == "__main__":
    main()
