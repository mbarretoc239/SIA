import os
import sys
import types

# Permite `from services...` e `from shared...` a partir da raiz do projeto
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Streamlit precisa de secrets para instanciar DatabaseManager. Como os testes
# NAO devem tocar Supabase, mockamos duas coisas:
#   1) st.secrets com valores fake, para importacoes que passam por DatabaseManager;
#   2) A funcao carregar_regras_gramaticais_cache do text_engine, que faria REST call.

# Antes de qualquer import do projeto, garantimos que st.secrets nao explode.
import streamlit as st  # noqa: E402


class _FakeSecrets(dict):
    def __getitem__(self, key):
        if key not in self:
            self[key] = _FakeSecrets()
        return super().__getitem__(key)

    def get(self, key, default=None):
        return super().get(key, default if default is not None else _FakeSecrets())


_fake = _FakeSecrets({
    "supabase": _FakeSecrets({
        "url": "https://exemplo.supabase.co",
        "key": "fake_anon_key",
        "service_role": "fake_service_role",
    }),
    "seguranca": _FakeSecrets({
        # Fernet exige chave URL-safe base64 de 32 bytes (44 chars com padding).
        # Usamos uma chave gerada estaticamente APENAS para testes.
        "fernet_key": "aGVsbG8td29ybGQtZmFrZS1rZXktZm9yLXRlc3RzMTIzNA==",
    }),
})

# Substitui atributo secrets do streamlit. Como st.secrets e um property/objeto
# especial, faz-se por atribuicao direta no modulo.
try:
    st.secrets = _fake
except Exception:
    setattr(st, "secrets", _fake)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_regras_gramaticais(monkeypatch):
    """Impede que text_engine tente conectar ao Supabase para carregar
    dicionario_glosas. Retorna dict vazio (sem regras de substituicao)."""
    from services.relatorio_5302 import text_engine

    def _fake_regras():
        return {}

    monkeypatch.setattr(text_engine, "carregar_regras_gramaticais_cache", _fake_regras)
    yield
