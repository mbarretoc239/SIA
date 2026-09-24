"""registrar_uso_tela: gravação leve em uso_telas, que nunca pode segurar a
navegação (timeout curto) nem devolver dado (return=minimal)."""

from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet

from shared.database import DatabaseManager

_SECRETS = {
    "supabase": {"url": "https://exemplo.supabase.co", "key": "anon", "service_role": "srv"},
    "seguranca": {"fernet_key": Fernet.generate_key().decode()},
}


def test_registrar_uso_tela_grava_sem_retorno_e_com_timeout_curto():
    with patch("shared.database.st.secrets", _SECRETS):
        db = DatabaseManager()

    with patch("shared.database.requests.post", return_value=MagicMock(status_code=201)) as post:
        db.registrar_uso_tela("uuid-1", "Auditor", "Amostragem")

    args, kwargs = post.call_args
    assert args[0] == "https://exemplo.supabase.co/rest/v1/uso_telas"
    assert kwargs["json"] == {"usuario_id": "uuid-1", "role": "Auditor", "tela": "Amostragem"}
    assert kwargs["headers"]["Prefer"] == "return=minimal"
    assert kwargs["timeout"] <= 5
