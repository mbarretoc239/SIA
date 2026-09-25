"""Datas do REL5201 (core/relatorio_5201.py). Em 2026-09-25 o card
"App + Misto/Não App" da Produtividade zerou: os registros de ago/2026 tinham
DATA_RECEBIMENTO_PROCESSO_FISICO gravada como '1970-01-01T00:00:00.000046204'
(número de série do Excel lido como nanossegundos), e ao juntar os 2 meses o
pandas escolhia o formato pelo primeiro valor e anulava as datas de setembro."""

import pandas as pd

from core.relatorio_5201 import _ler_data, procedimentos_consistido_digitado_por_canal, registros_para_df


def _registro(ordem, data_recebimento, execucao="N_APP", status="CONSISTIDO"):
    return {"ORDEM": ordem, "STATUS": status, "EXECUCAO": execucao, "QT_PROCEDIMENTO": 10,
            "DATA_RECEBIMENTO_PROCESSO_FISICO": data_recebimento}


def test_mes_com_fracao_de_segundo_na_frente_nao_apaga_as_datas_do_outro_mes():
    registros = [
        _registro("1", "1970-01-01T00:00:00.000046204", status="FECHADO"),  # ago/2026, como estava no banco
        _registro("2", "2026-09-01T00:00:00"),
        _registro("3", "2026-09-10T00:00:00"),
    ]
    df = registros_para_df(registros)
    assert df["DATA_RECEBIMENTO_PROCESSO_FISICO"].notna().all()
    assert procedimentos_consistido_digitado_por_canal(df[df["ORDEM"] != "1"]) == 20


def test_status_manual_com_microssegundos_nao_apaga_as_outras_datas():
    """marcar_status_manual_5201 grava datetime.now().isoformat(), com fração."""
    registros = [
        {"ORDEM": "1", "DATA_FECHAMENTO": "2026-09-23T10:15:30.123456"},
        {"ORDEM": "2", "DATA_FECHAMENTO": "2026-09-23T09:12:34"},
    ]
    df = registros_para_df(registros)
    assert df["DATA_FECHAMENTO"].notna().all()


def test_numero_de_serie_do_excel_vira_data_certa():
    serie = pd.Series([46204.0, None])
    datas = _ler_data(serie)
    assert datas.iloc[0] == pd.Timestamp("2026-07-01")
    assert pd.isna(datas.iloc[1])


def test_texto_do_csv_com_e_sem_hora_na_mesma_coluna():
    serie = pd.Series(["01/09/2026", "21/09/2026 14:27:14", None])
    datas = _ler_data(serie)
    assert datas.iloc[0] == pd.Timestamp("2026-09-01")
    assert datas.iloc[1] == pd.Timestamp("2026-09-21 14:27:14")
    assert pd.isna(datas.iloc[2])


def test_coluna_que_ja_vem_como_data_do_excel_nao_muda():
    serie = pd.Series(pd.to_datetime(["2026-09-01", "2026-09-02"]))
    assert _ler_data(serie).equals(serie)
