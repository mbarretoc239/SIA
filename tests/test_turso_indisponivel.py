"""shared.database._turso_pipeline: distinguir o bloqueio de PLANO do Turso
(code "BLOCKED", visto em produção 2026-09-23: "SQL read operations are
forbidden ... do you need to upgrade your plan?") de um erro de SQL comum --
a UI precisa mostrar um aviso amigável só no primeiro caso, sem esconder um
bug de verdade atrás dessa mensagem."""

from unittest.mock import patch

import pytest

from shared.database import DatabaseManager, TursoIndisponivelError


def _db():
    with patch.object(DatabaseManager, "__init__", lambda self: None):
        db = DatabaseManager()
    db.turso_url = "https://exemplo.turso.io"
    return db


def _resposta(status_code=200, json_data=None):
    class _Resp:
        ok = status_code < 400

        def json(self):
            return json_data

    resp = _Resp()
    resp.status_code = status_code
    resp.text = ""
    return resp


def test_erro_code_blocked_vira_tursoindisponivelerror():
    db = _db()
    resposta = _resposta(json_data={"results": [
        {"type": "error", "error": {"message": "Operation was blocked: SQL read operations are forbidden "
                                                "(reads are blocked, do you need to upgrade your plan?)",
                                     "code": "BLOCKED"}},
        {"type": "ok"},  # close
    ]})
    with patch("shared.database.requests.post", return_value=resposta):
        with pytest.raises(TursoIndisponivelError):
            db._turso_pipeline([{"sql": "SELECT 1"}], "token")


def test_tursoindisponivelerror_e_um_runtimeerror():
    """Código que já captura RuntimeError (ex.: except Exception genérico em
    Configurações) continua funcionando -- é subclasse, não um tipo à parte."""
    assert issubclass(TursoIndisponivelError, RuntimeError)


@pytest.mark.parametrize("erro", [
    {"message": "syntax error near SELECT", "code": "SQLITE_ERROR"},
    {"message": "no such table: base_ia_guias", "code": "SQLITE_UNKNOWN"},
    None,
])
def test_outros_erros_de_sql_continuam_runtimeerror_comum(erro):
    """Só "BLOCKED" vira o aviso amigável -- qualquer outro erro de SQL
    precisa continuar aparecendo como falha de verdade, não sumir atrás da
    mensagem "conta bloqueada" (ver memória "verificar antes de refutar")."""
    db = _db()
    resposta = _resposta(json_data={"results": [
        {"type": "error", "error": erro},
        {"type": "ok"},
    ]})
    with patch("shared.database.requests.post", return_value=resposta):
        with pytest.raises(RuntimeError) as excinfo:
            db._turso_pipeline([{"sql": "SELECT 1"}], "token")
        assert not isinstance(excinfo.value, TursoIndisponivelError)


def test_sem_token_continua_erro_normal_nao_tursoindisponivel():
    db = _db()
    with pytest.raises(RuntimeError) as excinfo:
        db._turso_pipeline([{"sql": "SELECT 1"}], "")
    assert not isinstance(excinfo.value, TursoIndisponivelError)


def test_http_nao_ok_continua_erro_normal_nao_tursoindisponivel():
    db = _db()
    with patch("shared.database.requests.post", return_value=_resposta(status_code=500)):
        with pytest.raises(RuntimeError) as excinfo:
            db._turso_pipeline([{"sql": "SELECT 1"}], "token")
        assert not isinstance(excinfo.value, TursoIndisponivelError)


def test_sucesso_normal_nao_afetado():
    db = _db()
    resposta = _resposta(json_data={"results": [
        {"type": "ok", "response": {"result": {"cols": [], "rows": []}}},
        {"type": "ok"},
    ]})
    with patch("shared.database.requests.post", return_value=resposta):
        assert db._turso_pipeline([{"sql": "SELECT 1"}], "token") == [{"cols": [], "rows": []}]


def _db_supabase():
    db = _db()
    db.supabase_url = "https://exemplo.supabase.co"
    db.headers = {}
    return db


def test_fallback_apagado_vira_tursoindisponivelerror():
    """As tabelas turso_fallback_* são apagadas pelo job pg_cron
    apagar_fallback_turso (03/10/2026). Se o Turso ainda estiver bloqueado
    nesse dia, a tabela sumida (HTTP 404) tem que degradar igual ao Turso
    bloqueado -- as views capturam TursoIndisponivelError e não quebram."""
    db = _db_supabase()
    with patch("shared.database.requests.get", return_value=_resposta(status_code=404)):
        with pytest.raises(TursoIndisponivelError):
            db._fallback_guias_ia_por_processo("123", "N")


def test_fallback_com_outro_erro_http_continua_erro_de_verdade():
    """Só 404 (tabela apagada) vira o silêncio de "Turso indisponível" --
    timeout/500 no fallback precisa continuar aparecendo como falha."""
    db = _db_supabase()
    with patch("shared.database.requests.get", return_value=_resposta(status_code=500)):
        with pytest.raises(RuntimeError) as excinfo:
            db._fallback_guias_ia_por_processo("123", "N")
    assert not isinstance(excinfo.value, TursoIndisponivelError)
