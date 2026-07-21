"""Testes do motor de texto do Relatorio 5302.

Cada teste declara um cenario minimo (dataframe de glosas) e checa que o
texto gerado contem/nao contem trechos-chave. Nao verificamos texto exato
palavra-a-palavra para nao ficar fragil demais - se a redacao final mudar,
so os asserts semanticamente relevantes precisam ser ajustados.
"""

import pandas as pd
import pytest

from services.relatorio_5302 import text_engine


META_BASE = {
    "processo": "TESTE",
    "prestador": "PRESTADOR TESTE",
    "producao": "01/2026",
    "valor_cobrado": 10000.0,
    "valor_calculado": 8000.0,
    "valor_glosa": 2000.0,
}


def _row(guia, cod_proc, proc, glosa, tipo, just="", sub=""):
    return {
        "Incluir no Relatório": True,
        "Tipo": tipo,
        "Guia": guia,
        "Cód. Procedimento": cod_proc,
        "Procedimento": proc,
        "Glosa": glosa,
        "Descrição Oficial": "descricao teste",
        "Justificativa": just,
        "Cód. Sub-Glosa": sub,
    }


def _gerar(rows, tipo="Resumido"):
    df = pd.DataFrame(rows)
    return text_engine.gerar_texto(df, tipo, META_BASE)


# ============================================================
# 1) Formato basico da glosa 480
# ============================================================

def test_glosa_480_uma_guia_sem_descricao():
    txt = _gerar([_row("G1", "N/A", "", "480", "Crítica")])
    assert "Houve glosa 480 na guia G1" in txt
    # nao deve citar "falta de documentacao" que era o antigo texto redundante
    assert "documentação" not in txt.lower()


def test_glosa_480_multiplas_guias():
    txt = _gerar([_row(g, "N/A", "", "480", "Crítica") for g in ["G1", "G2"]])
    assert "nas guias G1 e G2" in txt


# ============================================================
# 2) Compactacao por tipo
# ============================================================

def test_automatica_sempre_compacta():
    # Automatica com 1 categoria e 5 guias -> compacta "nas guias ..."
    rows = [_row(f"G{i}", "120", "consulta", "13", "Automática") for i in range(1, 6)]
    txt = _gerar(rows)
    assert "glosa 13" in txt
    # Formato compacto: nao lista "N consultas"
    assert "5 consultas" not in txt


def test_critica_com_muitos_procs_nao_compacta():
    # Critica com 10 categorias diferentes deve DETALHAR (nunca compacta)
    cats = [("120", "consulta"), ("800", "raspagem"), ("4170", "resina"),
            ("4040", "metalica"), ("330", "fotografia"), ("210", "radiografia"),
            ("2015", "endo"), ("5031", "exodontia"), ("5810", "ulotomia"),
            ("2035", "endo multi")]
    rows = []
    for g in ["G1", "G2"]:
        for cod, desc in cats:
            rows.append(_row(g, cod, desc, "459", "Crítica"))
    txt = _gerar(rows)
    # Deve mencionar as varias categorias, nao apenas "em N guias"
    assert "consulta" in txt.lower()
    assert "raspag" in txt.lower()  # raspagem/raspagens


def test_administrativa_com_5_cats_compacta():
    cats = [("120", "consulta"), ("800", "raspagem"), ("4170", "resina"),
            ("4040", "metalica"), ("330", "fotografia")]
    rows = []
    for g in ["G1", "G2"]:
        for cod, desc in cats:
            rows.append(_row(g, cod, desc, "200", "Administrativa"))
    txt = _gerar(rows)
    # Compactou -> nao lista categorias individuais
    assert "5 consultas" not in txt
    assert "glosa 200" in txt


def test_administrativa_com_4_cats_nao_compacta():
    cats = [("120", "consulta"), ("800", "raspagem"), ("4170", "resina"),
            ("4040", "metalica")]
    rows = []
    for g in ["G1", "G2"]:
        for cod, desc in cats:
            rows.append(_row(g, cod, desc, "200", "Administrativa"))
    txt = _gerar(rows)
    # Nao compactou -> menciona categorias
    assert "consulta" in txt.lower()


# ============================================================
# 3) Ordenacao (Critica -> Adm/Tec -> Auto -> 480)
# ============================================================

def test_ordem_critica_antes_de_automatica():
    rows = [
        _row("G1", "120", "consulta", "13", "Automática"),
        _row("G2", "4170", "resina", "459", "Crítica"),
    ]
    txt = _gerar(rows)
    pos_critica = txt.find("459")
    pos_auto = txt.find("13")
    assert pos_critica != -1 and pos_auto != -1
    assert pos_critica < pos_auto


def test_ordem_glosa_480_no_final():
    rows = [
        _row("G1", "N/A", "", "480", "Crítica"),
        _row("G2", "120", "consulta", "13", "Automática"),
    ]
    txt = _gerar(rows)
    pos_480 = txt.find("Houve glosa 480")
    pos_auto = txt.find("glosa 13")
    assert pos_480 > pos_auto


def test_ordem_admin_antes_de_automatica():
    rows = [
        _row("G1", "120", "consulta", "13", "Automática"),
        _row("G2", "4170", "resina", "200", "Administrativa"),
    ]
    txt = _gerar(rows)
    pos_admin = txt.find("200")
    pos_auto = txt.find("13")
    assert pos_admin < pos_auto


# ============================================================
# 4) Merge de glosas diferentes no mesmo procedimento+guia
# ============================================================

def test_merge_glosas_diferentes_mesmo_proc_guia():
    # Duas glosas nao-Automaticas no mesmo proc/guia devem virar
    # "glosas X e Y em 1 procedimento..."
    rows = [
        _row("G1", "4170", "resina", "459", "Crítica"),
        _row("G1", "4170", "resina", "455", "Crítica"),
    ]
    txt = _gerar(rows)
    assert "glosas 455 e 459" in txt or "glosas 459 e 455" in txt


def test_mesma_glosa_repetida_nao_mescla():
    # 4x glosa 430 no mesmo proc/guia NAO deve virar "glosas 430 e 430..."
    rows = [_row("G1", "5031", "exodontia", "430", "Crítica") for _ in range(4)]
    txt = _gerar(rows)
    assert "glosa 430" in txt
    assert "glosas 430 e 430" not in txt


# ============================================================
# 5) Deduplicacao de guias em categorias distintas
# ============================================================

def test_mesma_glosa_categorias_com_guias_iguais_lista_guias_uma_vez():
    # Glosa 446 em 2 cats diferentes mas MESMAS guias -> guias so 1 vez
    rows = []
    for g in ["G1", "G2"]:
        rows.append(_row(g, "4170", "restauração em resina", "446", "Automática"))
        rows.append(_row(g, "330", "fotografia", "446", "Automática"))
    txt = _gerar(rows)
    # Como e Automatica, compacta -> "nas guias G1 e G2" aparece uma vez
    assert txt.count("G1") <= 2   # tolera menção em "guias G1 e G2"
    assert "G1 e G2" in txt


# ============================================================
# 6) Casos vazios / negativos
# ============================================================

def test_df_vazio_retorna_mensagem_padrao():
    df = pd.DataFrame([_row("G1", "120", "consulta", "13", "Automática")])
    df["Incluir no Relatório"] = False
    txt = text_engine.gerar_texto(df, "Resumido", META_BASE)
    assert "Nenhuma glosa" in txt


def test_completa_e_resumida_ambas_funcionam():
    rows = [_row("G1", "4170", "resina", "459", "Crítica")]
    resumida = _gerar(rows, "Resumido")
    completa = _gerar(rows, "Detalhado")
    assert "459" in resumida
    assert "459" in completa
    assert resumida != completa
