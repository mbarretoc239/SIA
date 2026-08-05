import requests
import streamlit as st

# gemini-1.5-flash foi descontinuado; "-latest" é o alias que o Google mantém
# apontando pro modelo atual, evitando quebrar de novo em troca de versão.
# Tenta primeiro o Flash "cheio" (melhor qualidade, cota de RPM mais curta);
# se estourar o limite (ou falhar por qualquer outro motivo), cai pro Lite,
# que tem cota bem maior e qualidade equivalente pra essa reescrita.
_MODELO_PRIMARIO = "gemini-flash-latest"
_MODELO_FALLBACK = "gemini-flash-lite-latest"
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"

_SYSTEM_PROMPT = (
    "Você é um revisor técnico. Reescreva o texto abaixo para torná-lo coeso, natural, direto e "
    "o mais CURTO possível — corte redundância e frases de preenchimento, mantendo só a "
    "informação essencial de cada motivo. Remova conectivos repetitivos e evite repetições de "
    "jargões iniciais. Ajuste o texto para o formato de frase (remova o Caps Lock excessivo). "
    "IMPORTANTE: a frase inicial de contexto (explicando que a análise/liberação do repasse "
    "depende da conformidade com as normas técnicas e contratuais) NÃO é enchimento — mantenha "
    "uma versão curta dela antes da lista de motivos, não vá direto da saudação pros tópicos. "
    "Se houver mais de um motivo, liste em tópicos curtos usando hífen (-), sem markdown "
    "(nada de **negrito**, #, ou outra marcação) e sem título/rótulo antes de cada tópico. "
    "NÃO altere os motivos técnicos das recusas, NÃO adicione informações e mantenha o tom "
    "profissional estrito."
)


def _chamar_gemini(texto: str, api_key: str, modelo: str) -> tuple[str, str]:
    """Uma tentativa de chamada a `modelo`. Retorna (texto_resultado, erro)."""
    url = _ENDPOINT.format(modelo=modelo)
    payload = {"contents": [{"parts": [{"text": f"{_SYSTEM_PROMPT}\n\nTexto:\n{texto}"}]}]}

    try:
        resp = requests.post(f"{url}?key={api_key}", json=payload, timeout=30)
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


def melhorar_texto_com_ia(texto: str) -> tuple[str, str]:
    """Reescreve `texto` via Gemini (camada gratuita do Google AI Studio).

    Tenta o modelo primário (Flash) e, se falhar por qualquer motivo —
    principalmente limite de RPM estourado —, tenta automaticamente o
    modelo de fallback (Flash-Lite, cota maior) antes de desistir.

    Retorna (texto_resultado, erro): em caso de sucesso, erro é "" e
    texto_resultado é a versão reescrita. Se os dois modelos falharem,
    texto_resultado é o texto ORIGINAL inalterado e erro descreve o
    problema do último modelo tentado — nunca trava o fluxo nem apaga
    o texto do usuário.

    Só deve ser chamada com texto genérico (sem PII — nome de prestador,
    CPF/CNPJ, paciente, número de guia/processo): a camada gratuita do
    Gemini pode usar o conteúdo enviado para treinar modelos.
    """
    api_key = st.secrets.get("gemini", {}).get("api_key", "")
    if not api_key:
        return texto, "IA não configurada (gemini.api_key ausente em secrets.toml)."

    texto_novo, erro = _chamar_gemini(texto, api_key, _MODELO_PRIMARIO)
    if not erro:
        return texto_novo, ""

    return _chamar_gemini(texto, api_key, _MODELO_FALLBACK)
