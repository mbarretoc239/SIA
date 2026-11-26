"""Fila operacional: quem está em cada processo (substitui a planilha do time).

Acesso: módulo "fila_operacional" em Configurações > Permissões (beta liberada por exceção
individual). A trava contra duas pessoas no mesmo processo está no banco (ver
DatabaseManager.atualizar_fila e migrations/fila_operacional.sql), não na tela.

Egress (ver docs/turso_bloqueado_2026-09-23.md): a lista fica num cache único do servidor,
compartilhado por todos os usuários. Só a carga inicial baixa tudo; depois disso, no máximo
uma busca a cada INTERVALO_SEGUNDOS traz apenas o que mudou, independente de quantas
pessoas estejam na tela. Sem ninguém usando, nada é consultado.
"""
from __future__ import annotations

import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import streamlit as st

MODULO = "fila_operacional"
STATUS_FINAIS = ["Fechado", "Calculado", "Glosado", "Consistido"]
LIVRE, EM_ANDAMENTO, CONCLUIDO = "Livre", "Em andamento", "Concluído"

INTERVALO_SEGUNDOS = 30
RECARGA_COMPLETA_SEGUNDOS = 6 * 3600   # rede de segurança (ex.: linha apagada direto no banco)
MARGEM_RELOGIO = timedelta(seconds=60)  # diferença entre o relógio do app e o do banco
BRT = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------- cache compartilhado
class CacheFila:
    def __init__(self, relogio=time.monotonic):
        self._relogio = relogio
        self._trava = threading.Lock()
        self._linhas: dict[str, dict] = {}
        self._cursor: str | None = None
        self._ultima_busca = 0.0
        self._ultima_completa = 0.0

    def sincronizar(self, db, completa: bool = False) -> None:
        with self._trava:
            agora = self._relogio()
            completa = (
                completa or self._cursor is None
                or agora - self._ultima_completa >= RECARGA_COMPLETA_SEGUNDOS
            )
            if not completa and agora - self._ultima_busca < INTERVALO_SEGUNDOS:
                return
            cursor = (datetime.now(timezone.utc) - MARGEM_RELOGIO).strftime("%Y-%m-%dT%H:%M:%SZ")
            linhas = db.listar_fila(None if completa else self._cursor)
            if completa:
                self._linhas = {}
                self._ultima_completa = agora
            for linha in linhas:
                self._linhas[linha["processo"]] = linha
            self._cursor = cursor
            self._ultima_busca = agora

    def aplicar(self, linha: dict | None) -> None:
        """Coloca no cache a linha que o banco acabou de devolver numa gravação."""
        if linha:
            with self._trava:
                self._linhas[linha["processo"]] = linha

    def linhas(self) -> list[dict]:
        with self._trava:
            return list(self._linhas.values())

    def obter(self, processo) -> dict | None:
        with self._trava:
            return self._linhas.get(str(processo).strip())


@st.cache_resource
def cache_da_fila() -> CacheFila:
    return CacheFila()


# ---------------------------------------------------------------- regras
def situacao(linha: dict) -> str:
    if linha.get("status"):
        return CONCLUIDO
    return EM_ANDAMENTO if linha.get("auditor_nome") else LIVRE


def e_dono(linha: dict, login: str) -> bool:
    return bool(login) and str(linha.get("auditor_login") or "").upper() == login.upper()


def hora_brt(iso: str | None) -> str:
    if not iso:
        return ""
    momento = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(BRT)
    if momento.date() == datetime.now(BRT).date():
        return momento.strftime("%H:%M")
    return momento.strftime("%d/%m %H:%M")


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gravar(db, cache: CacheFila, processo: str, campos: dict, condicoes: dict | None = None):
    """(True, linha nova) se gravou; (False, linha atual) se a condição não bateu."""
    linha = db.atualizar_fila(processo, campos, condicoes)
    if linha:
        cache.aplicar(linha)
        return True, linha
    atual = db.buscar_fila_processo(processo)
    cache.aplicar(atual)
    return False, atual


def _condicao_dono(login: str, gestor: bool) -> dict:
    """Só quem assumiu mexe no processo; Gestor/Admin mexem em qualquer um."""
    condicao = {"auditor_nome": "not.is.null"}
    if not gestor:
        condicao["auditor_login"] = f"eq.{login}"
    return condicao


def assumir(db, cache, processo, login: str, nome: str):
    if not login:
        raise ValueError("Usuário sem login SIGO na sessão: saia e entre de novo.")
    return _gravar(
        db, cache, processo,
        {"auditor_login": login.upper(), "auditor_nome": nome.upper(), "assumido_em": _agora_iso()},
        {"auditor_nome": "is.null", "status": "is.null"},
    )


def concluir(db, cache, processo, status: str, login: str, gestor: bool):
    if status not in STATUS_FINAIS:
        raise ValueError(f"Status inválido: {status!r}")
    return _gravar(
        db, cache, processo, {"status": status, "concluido_em": _agora_iso()},
        {**_condicao_dono(login.upper(), gestor), "status": "is.null"},
    )


def reabrir(db, cache, processo, login: str, gestor: bool):
    return _gravar(
        db, cache, processo, {"status": None, "concluido_em": None},
        _condicao_dono(login.upper(), gestor),
    )


def liberar(db, cache, processo, motivo: str, login: str, nome: str, gestor: bool):
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("Informe o motivo da liberação.")
    return _gravar(
        db, cache, processo,
        {"auditor_login": None, "auditor_nome": None, "assumido_em": None,
         "liberado_motivo": motivo, "liberado_por": nome.upper(), "liberado_em": _agora_iso()},
        {**_condicao_dono(login.upper(), gestor), "status": "is.null"},
    )


def salvar_observacoes(db, cache, processo, campos: dict):
    permitidos = {"obs_contas", "obs_auditoria", "sem_biometria"}
    if set(campos) - permitidos:
        raise ValueError("Campo não editável por aqui.")
    return _gravar(db, cache, processo, campos)


# ---------------------------------------------------------------- leitura da planilha
def _normalizar(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


def _texto(valor) -> str | None:
    texto = str(valor).strip() if valor is not None else ""
    return texto or None


def _inteiro(valor) -> int | None:
    if valor is None or str(valor).strip() == "":
        return None
    if isinstance(valor, float) and not valor.is_integer():
        # "1.041" digitado como milhar e gravado pelo Excel como decimal
        if abs(valor * 1000 - round(valor * 1000)) < 1e-6:
            return int(round(valor * 1000))
        return None
    try:
        return int(float(str(valor).strip()))
    except ValueError:
        return None


def ler_planilha(arquivo) -> tuple[list[dict], list[str]]:
    """Lê a planilha no formato usado pelo time. Devolve (registros, avisos).

    As colunas Proced, Guias e TIPO são identificadas pelo conteúdo: há planilhas (e
    blocos de linhas) em que os valores estão fora da ordem do cabeçalho. O tipo é o
    texto Físico/Jurídico; os outros dois valores, na ordem, são procedimentos e guias.
    """
    import openpyxl

    planilha = openpyxl.load_workbook(arquivo, read_only=True, data_only=True).worksheets[0]
    linhas = planilha.iter_rows(values_only=True)
    cabecalho = [_normalizar(c) for c in next(linhas, [])]
    posicao = {nome: i for i, nome in enumerate(cabecalho) if nome}
    faltando = [c for c in ("processo", "prestador", "proced", "guias", "tipo") if c not in posicao]
    if faltando:
        raise ValueError(f"Colunas não encontradas na planilha: {', '.join(faltando)}.")
    trio = sorted(posicao[c] for c in ("proced", "guias", "tipo"))
    tipos = {"fisico": "Físico", "juridico": "Jurídico"}
    status_validos = {_normalizar(s): s for s in STATUS_FINAIS}

    registros, avisos, vistos = [], [], set()
    for numero, linha in enumerate(linhas, start=2):
        def celula(nome):
            i = posicao.get(nome)
            return linha[i] if i is not None and i < len(linha) else None

        bruto = celula("processo")
        if bruto is None or str(bruto).strip() == "":
            continue
        processo = str(_inteiro(bruto) or "")
        if not processo:
            avisos.append(f"Linha {numero}: número de processo inválido, ignorada.")
            continue
        if processo in vistos:
            avisos.append(f"Linha {numero}: processo {processo} repetido, ignorada.")
            continue
        vistos.add(processo)

        valores = [linha[i] if i < len(linha) else None for i in trio]
        tipo = next((tipos[_normalizar(v)] for v in valores if _normalizar(v) in tipos), None)
        numeros = [_inteiro(v) for v in valores if _normalizar(v) not in tipos]
        if tipo is None or len(numeros) != 2 or None in numeros:
            avisos.append(f"Linha {numero}: confira Proced, Guias e TIPO do processo {processo}.")
            numeros = [None, None]

        status_bruto = _normalizar(celula("status"))
        status = status_validos.get(status_bruto)
        if status_bruto and not status:
            avisos.append(f"Linha {numero}: status '{celula('status')}' não reconhecido, ficou em branco.")
        auditor = _texto(celula("auditor"))

        registros.append({
            "processo": processo,
            "prestador": _texto(celula("prestador")),
            "cidade": _texto(celula("cidade")),
            "uf": _texto(celula("uf")),
            "tipo": tipo,
            "procedimentos": numeros[0],
            "guias": numeros[1],
            "status": status,
            "auditor_nome": auditor.upper() if auditor else None,
            "obs_contas": _texto(celula("obs contas")),
            "obs_auditoria": _texto(celula("obs auditoria")),
            "sem_biometria": _inteiro(celula("quantidade sem biometria")),
        })
    return registros, avisos
