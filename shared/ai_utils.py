import requests
import streamlit as st

# gemini-1.5-flash foi descontinuado; "-latest" é o alias que o Google mantém
# apontando pro flash atual, evitando quebrar de novo em troca de versão.
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"

_SYSTEM_PROMPT = (
    "Você é um revisor técnico. Reescreva o texto abaixo para torná-lo coeso, natural e direto. "
    "Remova conectivos repetitivos e evite repetições de jargões iniciais. Ajuste o texto para o "
    "formato de frase (remova o Caps Lock excessivo). Formate os motivos específicos em bullet "
    "points se houver mais de um. NÃO altere os motivos técnicos das recusas, NÃO adicione "
    "informações e mantenha o tom profissional estrito."
)


def melhorar_texto_com_ia(texto: str) -> tuple[str, str]:
    """Reescreve `texto` via Gemini (camada gratuita do Google AI Studio).

    Retorna (texto_resultado, erro): em caso de sucesso, erro é "" e
    texto_resultado é a versão reescrita. Em qualquer falha (sem chave
    configurada, timeout, erro de rede, resposta inesperada), texto_resultado
    é o texto ORIGINAL inalterado e erro descreve o problema — nunca trava
    o fluxo nem apaga o texto do usuário.

    Só deve ser chamada com texto genérico (sem PII — nome de prestador,
    CPF/CNPJ, paciente, número de guia/processo): a camada gratuita do
    Gemini pode usar o conteúdo enviado para treinar modelos.
    """
    api_key = st.secrets.get("gemini", {}).get("api_key", "")
    if not api_key:
        return texto, "IA não configurada (gemini.api_key ausente em secrets.toml)."

    payload = {
        "contents": [{"parts": [{"text": f"{_SYSTEM_PROMPT}\n\nTexto:\n{texto}"}]}]
    }

    try:
        resp = requests.post(f"{_ENDPOINT}?key={api_key}", json=payload, timeout=15)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        return texto, "Tempo limite excedido ao chamar a IA."
    except requests.exceptions.RequestException as e:
        return texto, f"Falha de rede ao chamar a IA: {e}"

    try:
        dados = resp.json()
        texto_novo = dados["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (ValueError, KeyError, IndexError) as e:
        return texto, f"Resposta inesperada da IA: {e}"

    if not texto_novo:
        return texto, "A IA retornou uma resposta vazia."

    return texto_novo, ""
