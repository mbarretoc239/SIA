"""Escritas no PostgREST pedem return=minimal por padrão: devolver a linha
gravada/apagada conta como egress igual a uma leitura, e quase nenhum
chamador usa esse retorno. Só quem precisa do ID recém-criado pede
return=representation na própria chamada."""

from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet

from shared.database import DatabaseManager

_SECRETS = {
    "supabase": {"url": "https://exemplo.supabase.co", "key": "anon", "service_role": "srv"},
    "seguranca": {"fernet_key": Fernet.generate_key().decode()},
}


def _db():
    with patch("shared.database.st.secrets", _SECRETS):
        return DatabaseManager()


def _resposta_criado(novo_id):
    resp = MagicMock()
    resp.status_code = 201
    resp.json.return_value = [{"id": novo_id}]
    return resp


def test_headers_padrao_pedem_return_minimal():
    db = _db()
    assert db.headers["Prefer"] == "return=minimal"
    assert db._admin_headers()["Prefer"] == "return=minimal"


def test_criar_usuario_pede_a_linha_de_volta_pra_pegar_o_id():
    db = _db()
    db.marcar_todos_alinhamentos_lidos = MagicMock()
    with patch.object(db, "_hash_senha", return_value="hash"), \
            patch("shared.database.requests.post", return_value=_resposta_criado(42)) as post:
        assert db.criar_usuario("USR1", "Fulano", "Senha@123", "Contas") is True

    assert post.call_args.kwargs["headers"]["Prefer"] == "return=representation"
    db.marcar_todos_alinhamentos_lidos.assert_called_once_with(42)
    assert db.headers["Prefer"] == "return=minimal"


def test_inserir_alinhamento_pede_a_linha_de_volta_pra_pegar_o_id():
    db = _db()
    db.marcar_alinhamento_lido = MagicMock()
    with patch("shared.database.requests.post", return_value=_resposta_criado(7)) as post:
        assert db.inserir_alinhamento("Título", "Texto", "Geral", "Auditor", autor_id=3) is True

    assert post.call_args.kwargs["headers"]["Prefer"] == "return=representation"
    db.marcar_alinhamento_lido.assert_called_once_with(7, 3)
    assert db.headers["Prefer"] == "return=minimal"
