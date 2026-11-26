"""Fila operacional: trava de dono, cache compartilhado e leitura da planilha do time."""
import io

import openpyxl
import pytest

from core import fila_operacional as fila


class _DbFalso:
    """Imita o UPDATE condicional do PostgREST pros filtros que a fila usa."""

    def __init__(self, *linhas):
        self.linhas = {l["processo"]: dict(l) for l in linhas}
        self.leituras = []

    def listar_fila(self, desde=None):
        self.leituras.append(desde)
        return [dict(l) for l in self.linhas.values()] if desde is None else []

    def buscar_fila_processo(self, processo):
        linha = self.linhas.get(processo)
        return dict(linha) if linha else None

    def atualizar_fila(self, processo, campos, condicoes=None):
        linha = self.linhas.get(processo)
        if linha is None:
            return None
        for coluna, filtro in (condicoes or {}).items():
            if coluna == "or":   # só o "(auditor_nome.is.null,auditor_login.eq.X)" das observações
                dono = filtro.rstrip(")").split("auditor_login.eq.")[1]
                if linha.get("auditor_nome") is not None and linha.get("auditor_login") != dono:
                    return None
                continue
            valor = linha.get(coluna)
            if filtro == "is.null" and valor is not None:
                return None
            if filtro == "not.is.null" and valor is None:
                return None
            if filtro.startswith("eq.") and valor != filtro[3:]:
                return None
        linha.update(campos)
        return dict(linha)


def _cenario():
    db = _DbFalso({"processo": "1", "status": None, "auditor_nome": None, "auditor_login": None})
    return db, fila.CacheFila()


def test_segunda_pessoa_nao_assume_e_ve_quem_esta_com_o_processo():
    db, cache = _cenario()
    assert fila.assumir(db, cache, "1", "ana1", "Ana")[0] is True
    gravou, atual = fila.assumir(db, cache, "1", "bruno1", "Bruno")
    assert gravou is False
    assert atual["auditor_nome"] == "ANA"
    assert cache.obter("1")["auditor_nome"] == "ANA"


def test_so_quem_assumiu_mexe_no_processo():
    db, cache = _cenario()
    fila.assumir(db, cache, "1", "ana1", "Ana")
    assert fila.pode_mexer(cache.obter("1"), "bruno1") is False
    assert fila.concluir(db, cache, "1", "Fechado", "bruno1")[0] is False
    assert fila.liberar(db, cache, "1", "não é meu", "bruno1", "Bruno")[0] is False
    assert fila.salvar_observacoes(db, cache, "1", {"obs_contas": "x"}, "bruno1")[0] is False
    assert fila.salvar_observacoes(db, cache, "1", {"obs_contas": "PAR"}, "ana1")[0] is True
    assert fila.concluir(db, cache, "1", "Fechado", "ana1")[0] is True
    assert fila.situacao(cache.obter("1")) == fila.CONCLUIDO
    # concluído continua só dela, e não libera sem reabrir
    assert fila.reabrir(db, cache, "1", "bruno1")[0] is False
    assert fila.liberar(db, cache, "1", "motivo", "ana1", "Ana")[0] is False
    assert fila.reabrir(db, cache, "1", "ana1")[0] is True
    assert fila.liberar(db, cache, "1", "direcionado", "ana1", "Ana")[0] is True
    assert fila.situacao(cache.obter("1")) == fila.LIVRE
    assert cache.obter("1")["liberado_motivo"] == "direcionado"
    assert cache.obter("1")["liberado_por"] == "ANA"
    # livre: qualquer um anota
    assert fila.salvar_observacoes(db, cache, "1", {"obs_contas": "y"}, "bruno1")[0] is True


def test_liberar_sem_motivo_e_recusado():
    db, cache = _cenario()
    fila.assumir(db, cache, "1", "ana1", "Ana")
    with pytest.raises(ValueError):
        fila.liberar(db, cache, "1", "   ", "ana1", "Ana")
    assert cache.obter("1")["auditor_nome"] == "ANA"


def test_status_fora_da_lista_e_recusado():
    db, cache = _cenario()
    with pytest.raises(ValueError):
        fila.concluir(db, cache, "1", "Pago", "ana1")


def test_cache_consulta_o_banco_no_maximo_uma_vez_por_intervalo():
    db, _ = _cenario()
    relogio = [1000.0]
    cache = fila.CacheFila(relogio=lambda: relogio[0])
    for _usuario in range(8):
        cache.sincronizar(db)
    assert db.leituras == [None]
    relogio[0] += fila.INTERVALO_SEGUNDOS
    cache.sincronizar(db)
    cache.sincronizar(db)
    assert len(db.leituras) == 2 and db.leituras[1] is not None
    assert len(cache.linhas()) == 1   # busca vazia não apaga o que já estava no cache


def _planilha(*linhas):
    wb = openpyxl.Workbook()
    wb.active.append(["Processo", "Prestador", "Cidade", "UF", "Proced", "Guias", "TIPO", "Status",
                      "Auditor", "OBS Contas", "OBS Auditoria", "Quantidade SEM Biometria"])
    for linha in linhas:
        wb.active.append(list(linha))
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def test_planilha_aceita_as_duas_ordens_de_proced_guias_tipo():
    registros, avisos = fila.ler_planilha(_planilha(
        [10, "A", "X", "SP", 40, 12, "Jurídico", "FECHADO", "lara", "PAR", None, 3],
        [11, "B", "X", "SP", "Físico", 1.041, 220],
    ))
    assert avisos == []
    assert [(r["procedimentos"], r["guias"], r["tipo"]) for r in registros] == [
        (40, 12, "Jurídico"), (1041, 220, "Físico"),
    ]
    assert registros[0]["status"] == "Fechado" and registros[0]["auditor_nome"] == "LARA"
    assert registros[0]["sem_biometria"] == 3
    # o PostgREST exige as mesmas chaves em todas as linhas de um insert em lote
    assert registros[0].keys() == registros[1].keys()


def test_planilha_ignora_repetido_e_avisa_status_desconhecido():
    registros, avisos = fila.ler_planilha(_planilha(
        [10, "A", "X", "SP", "Físico", 4, 2, "pago"],
        [10, "A", "X", "SP", "Físico", 4, 2],
    ))
    assert len(registros) == 1 and registros[0]["status"] is None
    assert len(avisos) == 2


def test_5201_manda_pro_banco_so_os_calculados():
    class Db:
        def marcar_fila_calculados(self, processos):
            self.recebidos = processos
            return 1

    db = Db()
    registros = [
        {"ORDEM": "2", "STATUS": "CALCULADO"},
        {"ORDEM": "1", "STATUS": "CALCULADO"},
        {"ORDEM": "1", "STATUS": "CALCULADO"},
        {"ORDEM": "3", "STATUS": "FECHADO"},
        {"ORDEM": None, "STATUS": "CALCULADO"},
    ]
    assert fila.aplicar_relatorio_5201(db, registros) == 1
    assert db.recebidos == ["1", "2"]
    assert fila.aplicar_relatorio_5201(Db(), [{"ORDEM": "3", "STATUS": "FECHADO"}]) == 0


def _fila_de_tres():
    db = _DbFalso(*[
        {"processo": p, "posicao": i, "status": None, "auditor_nome": None, "auditor_login": None}
        for i, p in enumerate(("a", "b", "c"), start=1)
    ])
    cache = fila.CacheFila()
    cache.sincronizar(db)
    return db, cache


def _ordem(cache):
    return [l["processo"] for l in fila.ordenar(cache.linhas())]


def test_assumir_e_concluir_nao_mudam_a_ordem():
    db, cache = _fila_de_tres()
    fila.assumir(db, cache, "c", "ana1", "Ana")
    fila.concluir(db, cache, "c", "Fechado", "ana1")
    assert _ordem(cache) == ["a", "b", "c"]


@pytest.mark.parametrize("processo,destino,esperado", [
    ("c", 1, ["c", "a", "b"]),
    ("a", 3, ["b", "c", "a"]),
    ("a", 2, ["b", "a", "c"]),
    ("b", 99, ["a", "c", "b"]),
])
def test_gestor_move_o_processo(processo, destino, esperado):
    db, cache = _fila_de_tres()
    assert fila.mover(db, cache, processo, destino, "Gestor")[0] is True
    assert _ordem(cache) == esperado


def test_auditor_nao_altera_a_ordem():
    db, cache = _fila_de_tres()
    for role in ("Auditor", "CISO", None):
        with pytest.raises(PermissionError):
            fila.mover(db, cache, "c", 1, role)
    assert _ordem(cache) == ["a", "b", "c"]
