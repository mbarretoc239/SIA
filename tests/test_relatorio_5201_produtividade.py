"""_produtivos_com_auditor_e_data / dias_disponiveis / produtividade_por_auditor
(core/relatorio_5201.py): AUT.PAGTO já apareceu no REL5201 com LOGIN_FECHAMENTO
preenchido mas DATA_FECHAMENTO vazia (ver conversa 2026-09-22) -- o processo
continuava no total agregado (não depende de `_data`), mas sumia da quebra por
dia (gráfico "Produtividade ao longo do mês"), fazendo parecer que o auditor
trabalhou bem menos dias do que de fato trabalhou."""

import pandas as pd
import pytest

from core.relatorio_5201 import dias_disponiveis, produtividade_por_auditor


def _df(linhas):
    """linhas: ORDEM, STATUS, QT_PROCEDIMENTO, LOGIN_FECHAMENTO, DATA_FECHAMENTO,
    LOGIN_CONSISTENCIA, DATA_CONSISTENCIA (datas como str "YYYY-MM-DD" ou None)."""
    colunas = ["ORDEM", "STATUS", "QT_PROCEDIMENTO", "LOGIN_FECHAMENTO", "DATA_FECHAMENTO",
               "LOGIN_CONSISTENCIA", "DATA_CONSISTENCIA"]
    df = pd.DataFrame(linhas, columns=colunas)
    df["DATA_FECHAMENTO"] = pd.to_datetime(df["DATA_FECHAMENTO"])
    df["DATA_CONSISTENCIA"] = pd.to_datetime(df["DATA_CONSISTENCIA"])
    return df


def test_aut_pagto_com_login_fechamento_mas_sem_data_fechamento_cai_para_consistencia():
    """O caso real: AUT.PAGTO com LOGIN_FECHAMENTO preenchido e
    DATA_FECHAMENTO vazia -- antes da correção, isso deixava `_data` nula e o
    processo sumia de dias_disponiveis/produtividade por dia, mesmo contando
    no agregado."""
    df = _df([
        ["1", "AUT.PAGTO", 100, "AUDITOR1", None, "AUDITOR1", "2026-09-10"],
    ])
    assert dias_disponiveis(df) == [pd.Timestamp("2026-09-10").date()]

    agregado = produtividade_por_auditor(df, auditor="AUDITOR1")
    do_dia = produtividade_por_auditor(df, dia=pd.Timestamp("2026-09-10").date(), auditor="AUDITOR1")
    assert agregado.iloc[0]["Total"] == 100
    assert do_dia.iloc[0]["Total"] == 100  # antes da correção: do_dia vinha vazio (Total sumia do gráfico por dia)


def test_total_agregado_bate_com_a_soma_dos_dias_mesmo_com_datas_de_fechamento_faltando():
    """Propriedade que o bug quebrava: a soma das barras do gráfico "por dia"
    tem que bater com o total mostrado nas métricas, processo a processo,
    mesmo quando alguns AUT.PAGTO não têm DATA_FECHAMENTO."""
    df = _df([
        ["1", "FECHADO", 50, "AUDITOR1", "2026-09-03", "AUDITOR1", "2026-09-02"],
        ["2", "AUT.PAGTO", 30, "AUDITOR1", None, "AUDITOR1", "2026-09-09"],       # sem DATA_FECHAMENTO
        ["3", "AUT.PAGTO", 20, "AUDITOR1", "2026-09-17", "AUDITOR1", "2026-09-16"],  # com DATA_FECHAMENTO
        ["4", "CALCULADO", 10, None, None, "AUDITOR1", "2026-09-21"],             # CALCULADO nunca tem LOGIN_FECHAMENTO
    ])
    total = produtividade_por_auditor(df, auditor="AUDITOR1").iloc[0]["Total"]
    assert total == 50 + 30 + 20 + 10

    soma_dos_dias = sum(
        produtividade_por_auditor(df, dia=d, auditor="AUDITOR1").iloc[0]["Total"]
        for d in dias_disponiveis(df)
        if not produtividade_por_auditor(df, dia=d, auditor="AUDITOR1").empty
    )
    assert soma_dos_dias == total


def test_login_fechamento_e_data_fechamento_presentes_continua_usando_o_par_fechamento():
    """Não muda o comportamento já validado: com os dois presentes (caso
    normal de FECHADO/AUT.PAGTO), continua usando LOGIN_FECHAMENTO/
    DATA_FECHAMENTO, não CONSISTENCIA -- mesmo que as datas sejam diferentes."""
    df = _df([
        ["1", "FECHADO", 40, "FECHOU", "2026-09-05", "CONSISTIU", "2026-09-01"],
    ])
    assert dias_disponiveis(df) == [pd.Timestamp("2026-09-05").date()]
    tabela = produtividade_por_auditor(df, auditor="FECHOU")
    assert tabela.iloc[0]["Total"] == 40
    assert produtividade_por_auditor(df, auditor="CONSISTIU").empty


def test_calculado_sem_login_fechamento_sempre_usou_consistencia():
    df = _df([
        ["1", "CALCULADO", 15, None, None, "AUDITOR1", "2026-09-08"],
    ])
    assert dias_disponiveis(df) == [pd.Timestamp("2026-09-08").date()]
    assert produtividade_por_auditor(df, auditor="AUDITOR1").iloc[0]["Total"] == 15


def test_sem_login_nenhum_fica_fora_da_produtividade():
    df = _df([
        ["1", "FECHADO", 15, None, None, None, None],
    ])
    assert dias_disponiveis(df) == []
    assert produtividade_por_auditor(df).empty


def test_status_nao_produtivo_nao_entra():
    df = _df([
        ["1", "CONSISTIDO", 15, None, None, "AUDITOR1", "2026-09-08"],
        ["2", "GLOSADO", 15, "AUDITOR1", "2026-09-08", "AUDITOR1", "2026-09-01"],
    ])
    assert dias_disponiveis(df) == []
    assert produtividade_por_auditor(df).empty


def test_df_vazio_nao_quebra():
    df = _df([])
    assert dias_disponiveis(df) == []
    assert produtividade_por_auditor(df).empty
