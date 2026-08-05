import streamlit as st
from cryptography.fernet import Fernet
import json

def get_fernet() -> Fernet:
    """Retorna uma instância Fernet usando a chave segura do secrets.

    Sem fallback de propósito: se a chave não estiver configurada, é melhor
    o app quebrar visivelmente (erro claro) do que assinar tokens de sessão
    com uma chave pública e previsível — isso permitiria forjar login,
    inclusive como Admin, sem nunca ter autenticado de verdade."""
    key_str = st.secrets["seguranca"]["fernet_key"]
    return Fernet(key_str)

def criar_token_sessao(usuario_id: str, nome: str, role: str, equipe: str, usuario_sigo: str = "") -> str:
    """Cria um token JWT-like criptografado com os dados do usuário."""
    f = get_fernet()
    dados = {
        "id": usuario_id,
        "nome": nome,
        "role": role,
        "equipe": equipe,
        "usuario_sigo": usuario_sigo,
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
        dados_bytes = f.decrypt(token.encode('utf-8'), ttl=28800) # Expira em 8 horas (8 * 60 * 60)
        dados = json.loads(dados_bytes.decode('utf-8'))
        return dados
    except Exception:
        return None
