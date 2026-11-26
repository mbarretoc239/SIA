"""Cache do REL5201 por mês (core/relatorio_5201.py): só o mês que mudou no
banco é baixado de novo."""

from core.relatorio_5201 import CacheMesesRel5201


class _DbFalso:
    def __init__(self):
        self.versoes = {"2026-10": (10, "1"), "2026-11": (20, "1")}
        self.baixados = []

    def versoes_relatorio_5201(self):
        return dict(self.versoes)

    def carregar_relatorio_5201(self, mes):
        self.baixados.append(mes)
        return [{"ORDEM": mes, "STATUS": "CONSISTIDO", "_mes_referencia": mes, "_importado_por": "x"}]


def _cache_carregado():
    db, cache = _DbFalso(), CacheMesesRel5201()
    cache.carregar(db, agora=0)
    db.baixados.clear()
    return db, cache


def test_primeira_carga_traz_todos_os_meses_em_ordem():
    db, cache = _DbFalso(), CacheMesesRel5201()
    registros = cache.carregar(db, agora=0)
    assert [r["_mes_referencia"] for r in registros] == ["2026-10", "2026-11"]
    assert sorted(db.baixados) == ["2026-10", "2026-11"]


def test_sem_mudanca_nao_baixa_nada():
    db, cache = _cache_carregado()
    assert len(cache.carregar(db, agora=3600)) == 2
    assert db.baixados == []


def test_reimportacao_baixa_so_o_mes_que_mudou():
    db, cache = _cache_carregado()
    db.versoes["2026-11"] = (35, "1")
    cache.carregar(db, agora=3600)
    assert db.baixados == ["2026-11"]


def test_mes_novo_entra_e_mes_descartado_sai():
    db, cache = _cache_carregado()
    del db.versoes["2026-10"]
    db.versoes["2026-12"] = (50, "1")
    registros = cache.carregar(db, agora=3600)
    assert [r["_mes_referencia"] for r in registros] == ["2026-11", "2026-12"]
    assert db.baixados == ["2026-12"]


def test_depois_da_validade_baixa_de_novo():
    db, cache = _cache_carregado()
    cache.carregar(db, agora=CacheMesesRel5201.VALIDADE_SEGUNDOS)
    assert sorted(db.baixados) == ["2026-10", "2026-11"]


def test_status_manual_aparece_sem_baixar_e_preserva_os_dados_da_importacao():
    db, cache = _cache_carregado()
    cache.atualizar({"ORDEM": "2026-11", "STATUS": "FECHADO", "_mes_referencia": "2026-11"})
    registros = cache.carregar(db, agora=3600)
    assert registros[1]["STATUS"] == "FECHADO"
    assert registros[1]["_importado_por"] == "x"
    assert registros[0]["STATUS"] == "CONSISTIDO"
    assert db.baixados == []
