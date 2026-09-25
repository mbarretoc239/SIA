"""Lista de processos do mês (Amostragem): coluna "Data de entrada", vinda de
DATA_RECEBIMENTO_PROCESSO_FISICO do REL5201, e escolha do mês mais recente
quando o processo está nos 2 meses retidos."""

from unittest.mock import patch

import pandas as pd

from core.amostragem import montar_lista_processos_mes
from core.relatorio_5201 import registros_para_df


def _processo_turso(nu_ordem):
    return {"nu_ordem": nu_ordem, "especialidades": "CLINICO", "procedimentos": "81000065",
            "total_itens": 1, "itens_biometria": 0, "itens_com_operador": 0}


def _lista(registros_5201, processos):
    df_rel = registros_para_df(registros_5201)
    with patch("core.amostragem.carregar_regras_amostragem_cache", return_value=({}, [])):
        return montar_lista_processos_mes(processos, df_rel, set())


def test_data_de_entrada_vem_do_rel5201_e_prefere_o_mes_mais_recente():
    registros = [
        # agosto na frente, como o banco está devolvendo hoje
        {"ORDEM": "10", "STATUS": "CONSISTIDO", "EXECUCAO": "N_APP", "_mes_referencia": "2026-08",
         "DATA_RECEBIMENTO_PROCESSO_FISICO": "2026-08-05T00:00:00"},
        {"ORDEM": "10", "STATUS": "FECHADO", "EXECUCAO": "N_APP", "_mes_referencia": "2026-09",
         "DATA_RECEBIMENTO_PROCESSO_FISICO": "2026-09-01T00:00:00"},
    ]
    lista = _lista(registros, [_processo_turso("10")])
    linha = lista.iloc[0]
    assert linha["Status"] == "Fechado"
    assert linha["Data de entrada"] == pd.Timestamp("2026-09-01")


def test_data_de_agosto_gravada_como_1970_aparece_com_a_data_certa():
    registros = [
        {"ORDEM": "20", "STATUS": "FECHADO", "EXECUCAO": "APP", "_mes_referencia": "2026-08",
         "DATA_RECEBIMENTO_PROCESSO_FISICO": "1970-01-01T00:00:00.000046204"},
    ]
    lista = _lista(registros, [_processo_turso("20")])
    assert lista.iloc[0]["Data de entrada"] == pd.Timestamp("2026-07-01")


def test_processo_sem_data_ou_sem_rel5201_fica_em_branco():
    registros = [
        {"ORDEM": "30", "STATUS": "CONSISTIDO", "EXECUCAO": "MISTO", "_mes_referencia": "2026-09",
         "DATA_RECEBIMENTO_PROCESSO_FISICO": None},
    ]
    lista = _lista(registros, [_processo_turso("30"), _processo_turso("99")])
    assert lista["Data de entrada"].isna().all()


def test_filtro_por_periodo_da_tela():
    """Mesma conta do filtro em views/7_Amostragem_Beta.py: 1 data = só o dia,
    2 = intervalo fechado; sem data nunca passa."""
    datas = pd.Series(pd.to_datetime(["2026-09-01", "2026-09-10", None])).dt.date
    um_dia = (pd.Timestamp("2026-09-01").date(),)
    intervalo = (pd.Timestamp("2026-09-01").date(), pd.Timestamp("2026-09-05").date())
    assert datas.between(um_dia[0], um_dia[-1]).tolist() == [True, False, False]
    assert datas.between(intervalo[0], intervalo[-1]).tolist() == [True, False, False]
