import streamlit as st
from cryptography.fernet import Fernet
import json
import base64

def get_fernet() -> Fernet:
    """Retorna uma instância Fernet usando a chave segura do secrets."""
    try:
        # Pega a chave que já usamos pra LGPD
        key_str = st.secrets["seguranca"]["fernet_key"]
        return Fernet(key_str)
    except Exception:
        # Fallback de desenvolvimento caso não esteja configurado
        fallback_key = base64.urlsafe_b64encode(b"0" * 32)
        return Fernet(fallback_key)

def criar_token_sessao(usuario_id: str, nome: str, role: str, equipe: str) -> str:
    """Cria um token JWT-like criptografado com os dados do usuário."""
    f = get_fernet()
    dados = {
        "id": usuario_id,
        "nome": nome,
        "role": role,
        "equipe": equipe
    }
    dados_bytes = json.dumps(dados).encode('utf-8')
    token = f.encrypt(dados_bytes)
    return token.decode('utf-8')

def decifrar_token_sessao(token: str) -> dict:
    """Decifra o token. Retorna dict se válido, ou None se inválido/forjado."""
    if not token:
        return None
    f = get_fernet()
    try:
        dados_bytes = f.decrypt(token.encode('utf-8'), ttl=2592000) # Expira em 30 dias (30 * 24 * 60 * 60)
        dados = json.loads(dados_bytes.decode('utf-8'))
        return dados
    except Exception:
        return None
