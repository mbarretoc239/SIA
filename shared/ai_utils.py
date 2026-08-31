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

def _chamar_gemini(texto: str, api_key: str, modelo: str, prompt: str, temperature: float = 0.2) -> tuple[str, str]:
    """Uma tentativa de chamada a `modelo`. Retorna (texto_resultado, erro)."""
    url = _ENDPOINT.format(modelo=modelo)
    payload = {
        "contents": [{"parts": [{"text": f"{prompt}\n\nTexto:\n{texto}"}]}],
        # Temperatura baixa: essa tarefa é reescrita fiel, não criação de
        # conteúdo -- o padrão do Gemini (~1.0) já trocou o motivo técnico
        # de um tópico por outro genérico numa reescrita real.
        "generationConfig": {"temperature": temperature},
    }

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


_SYSTEM_PROMPT_OCORRENCIA = (
    "Você é um analista de auditoria escrevendo um resumo narrativo de USO INTERNO "
    "(não é a comunicação oficial ao prestador) a partir de um texto de ocorrência já "
    "detalhado glosa a glosa. Reescreva como um relato corrido, em terceira pessoa, "
    "começando com algo como 'Prestador apresenta...' — NUNCA use saudação, cabeçalho, "
    "frase de aviso de glosa ou telefone de contato: é só o relato em si, nada dos "
    "elementos formais do texto de orientação ao prestador. "
    "Agrupe as ocorrências por TEMA/PADRÃO de comportamento (ex: qualidade técnica em "
    "procedimentos de prótese, falta de documentação, problemas de imagem/RX) em vez de "
    "por código de glosa isolado — o objetivo é contar a história do que está "
    "acontecendo com esse prestador, não listar item por item. "
    "NÃO invente nenhum motivo novo — só reorganize e agrupe o que já está no texto "
    "original, mantendo os fatos (códigos de glosa, tipos de procedimento, motivos) "
    "fiéis ao que foi informado. "
    "CRÍTICO — cada motivo no texto original pertence a um código de glosa específico "
    "(está sempre escrito logo depois desse código). Ao agrupar por tema, essa amarração "
    "motivo↔código NÃO pode mudar: se o motivo 'falta de selamento' está junto da glosa "
    "459 no original, ele continua sendo da 459 no relato final, mesmo que apareça numa "
    "frase que também mencione outros códigos. Antes de escrever cada frase, confira "
    "mentalmente: 'esse motivo que estou citando aqui é realmente o que o texto original "
    "atribui a ESSE código, ou é o motivo de um código vizinho que acabei juntando por "
    "engano?' — no caso de dúvida, separe em frases diferentes em vez de arriscar "
    "atribuir o motivo errado a um código. "
    "Ao citar guias, NÃO liste todas: cite no máximo 1 guia de exemplo por afirmação, "
    "seguida de 'e mais N guias' quando houver mais do que essa (ex: 'guia 27169616 e "
    "mais 4 guias') — nunca enumere a lista inteira de números. Copie o número da guia "
    "exemplo EXATAMENTE como está no texto original, dígito por dígito — nunca digite um "
    "número de guia de memória, sempre copie o caractere exato do texto de entrada. "
    "TRÊS CUIDADOS ADICIONAIS que já causaram erro antes: "
    "(1) Se uma cláusula do texto original NÃO tiver nenhum motivo escrito depois dela "
    "(só o código, o procedimento e a guia, sem 'pois'/'visto que'/'por falta de' etc.), "
    "NÃO invente um motivo pra ela — trate como um evento à parte, sem explicação (ex: "
    "'também há glosa 420 sem motivo detalhado na guia X'), ou simplesmente não a inclua "
    "no relato se ela não se encaixar em nenhum tema. Nunca empreste o motivo de uma "
    "cláusula vizinha pra preencher essa lacuna. "
    "(2) O MESMO código de glosa pode aparecer em cláusulas DIFERENTES e SEPARADAS do "
    "texto original (guias diferentes, às vezes com motivo diferente ou sem motivo). "
    "Cada ocorrência do código é um evento distinto — não assuma que 'código igual' "
    "significa 'é a mesma cláusula que eu já processei'. Trate cada uma separadamente, "
    "mesmo que isso signifique citar o mesmo código de glosa duas vezes no relato final, "
    "em frases/temas diferentes. "
    "(3) Números de guia têm 8 dígitos e costumam ser parecidos entre si (ex: 27252374 e "
    "27253374 diferem em 1 dígito só) — depois de escrever cada número de guia, releia e "
    "confira dígito a dígito contra o número correspondente no texto original antes de "
    "seguir pra próxima frase. "
    "Seja conciso: 2 a 4 frases no total, mesmo que o texto original seja bem mais longo."
)


def gerar_texto_ocorrencia_com_ia(texto: str) -> tuple[str, str]:
    """Reescreve o 'Texto Final' (saída de text_engine.gerar_texto, glosa a glosa)
    como um relato narrativo curto, agrupado por padrão de comportamento do
    prestador, pra uso interno — não é a comunicação oficial ao prestador.

    Recebe número de guia (decisão consciente: risco considerado baixo, guia
    sozinho sem nome de prestador/paciente/CPF). Ressalva de sempre sobre a
    camada gratuita do Gemini: não mandar nome de prestador/CPF aqui também.

    Retorna (texto_resultado, erro): em caso de sucesso, erro é "" e
    texto_resultado é a versão reescrita. Se os dois modelos falharem,
    texto_resultado é o texto ORIGINAL inalterado e erro descreve o
    problema do último modelo tentado — nunca trava o fluxo nem apaga
    o texto do usuário.
    """
    api_key = st.secrets.get("gemini", {}).get("api_key", "")
    if not api_key:
        return texto, "IA não configurada (gemini.api_key ausente em secrets.toml)."

    # Temperatura um pouco mais alta que a reescrita fiel (0.2): aqui a tarefa
    # exige reorganizar/agrupar por tema, não só trocar a forma -- precisa de
    # alguma liberdade pra fazer isso bem, mas ainda conservadora o bastante
    # pra não inventar motivo.
    texto_novo, erro = _chamar_gemini(texto, api_key, _MODELO_PRIMARIO, prompt=_SYSTEM_PROMPT_OCORRENCIA, temperature=0.3)
    if not erro:
        return texto_novo, ""

    return _chamar_gemini(texto, api_key, _MODELO_FALLBACK, prompt=_SYSTEM_PROMPT_OCORRENCIA, temperature=0.3)
