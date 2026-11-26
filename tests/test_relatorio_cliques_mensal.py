import importlib.util
import os
from datetime import datetime, timedelta, timezone

_spec = importlib.util.spec_from_file_location(
    "relatorio_cliques_mensal",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "relatorio_cliques_mensal.py"),
)
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)
BRT = timezone(timedelta(hours=-3))


def test_mes_anterior_vira_o_ano():
    assert rc.mes_anterior(2027, 1) == (2026, 12)
    assert rc.mes_anterior(2026, 12) == (2026, 11)


def test_limites_do_mes_cobrem_dia_1_ate_o_ultimo_dia_em_brt():
    ini, fim = rc.limites_do_mes("2026-11")
    assert ini == datetime(2026, 11, 1, 0, 0, tzinfo=BRT)
    assert fim == datetime(2026, 12, 1, 0, 0, tzinfo=BRT)  # 30/11 23:59:59 ainda é novembro


def test_limites_de_dezembro_viram_janeiro_do_ano_seguinte():
    ini, fim = rc.limites_do_mes("2026-12")
    assert (ini.month, fim.year, fim.month) == (12, 2027, 1)


def test_segunda_da_semana_passada():
    seg16 = datetime(2026, 11, 16, 7, 0, tzinfo=BRT)  # segunda, dia da execução
    assert rc.segunda_da_semana_passada(seg16) == datetime(2026, 11, 9, tzinfo=BRT)
    qua18 = datetime(2026, 11, 18, 15, 0, tzinfo=BRT)  # rodando atrasado no meio da semana
    assert rc.segunda_da_semana_passada(qua18) == datetime(2026, 11, 9, tzinfo=BRT)
    dom22 = datetime(2026, 11, 22, 23, 0, tzinfo=BRT)  # domingo ainda é a semana de 16/11
    assert rc.segunda_da_semana_passada(dom22) == datetime(2026, 11, 9, tzinfo=BRT)
