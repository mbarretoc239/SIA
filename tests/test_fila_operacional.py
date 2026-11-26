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


def test_so_o_dono_ou_gestor_conclui_e_libera():
    db, cache = _cenario()
    fila.assumir(db, cache, "1", "ana1", "Ana")
    assert fila.concluir(db, cache, "1", "Fechado", "bruno1", False)[0] is False
    assert fila.liberar(db, cache, "1", "não é meu", "bruno1", "Bruno", False)[0] is False
    assert fila.concluir(db, cache, "1", "Fechado", "ana1", False)[0] is True
    assert fila.situacao(cache.obter("1")) == fila.CONCLUIDO
    # concluído não libera nem é assumido de novo; precisa reabrir
    assert fila.liberar(db, cache, "1", "motivo", "ana1", "Ana", False)[0] is False
    assert fila.reabrir(db, cache, "1", "gestor1", True)[0] is True
    assert fila.liberar(db, cache, "1", "direcionado", "gestor1", "Lia", True)[0] is True
    assert fila.situacao(cache.obter("1")) == fila.LIVRE
    assert cache.obter("1")["liberado_motivo"] == "direcionado"
    assert cache.obter("1")["liberado_por"] == "LIA"


def test_liberar_sem_motivo_e_recusado():
    db, cache = _cenario()
    fila.assumir(db, cache, "1", "ana1", "Ana")
    with pytest.raises(ValueError):
        fila.liberar(db, cache, "1", "   ", "ana1", "Ana", False)
    assert cache.obter("1")["auditor_nome"] == "ANA"


def test_status_fora_da_lista_e_recusado():
    db, cache = _cenario()
    with pytest.raises(ValueError):
        fila.concluir(db, cache, "1", "Pago", "ana1", False)


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
