"""Lista de processos do mês (Amostragem): coluna "Data de entrada", vinda de
DATA_RECEBIMENTO_PROCESSO_FISICO do REL5201, e escolha do mês mais recente
quando o processo está nos 2 meses retidos."""

from unittest.mock import patch

import pandas as pd

from core.amostragem import filtrar_por_data_entrada, montar_lista_processos_mes
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


def _df_para_filtro():
    """Processo com data, processo sem data mas com REL5201 (Status
    preenchido), e processo sem match nenhum no REL5201 (Status vazio)."""
    return pd.DataFrame({
        "Processo": ["1", "2", "3"],
        "Status": ["Fechado", "Consistido", None],
        "Data de entrada": [pd.Timestamp("2026-09-01"), pd.NaT, pd.NaT],
    })


def test_filtro_todos_nao_muda_nada():
    df = _df_para_filtro()
    assert filtrar_por_data_entrada(df, "Todos").equals(df)


def test_filtro_sim_so_quem_tem_data():
    resultado = filtrar_por_data_entrada(_df_para_filtro(), "Sim")
    assert resultado["Processo"].tolist() == ["1"]


def test_filtro_nao_so_quem_bateu_no_rel5201_mas_sem_data():
    """Processo "3" não tem match no REL5201 (Status vazio) -- não sabe se
    tem data ou não, então fica fora do "Não" (mesma regra do "Login de
    digitador")."""
    resultado = filtrar_por_data_entrada(_df_para_filtro(), "Não")
    assert resultado["Processo"].tolist() == ["2"]
