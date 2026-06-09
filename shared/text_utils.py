import re
import unicodedata
from difflib import SequenceMatcher

def normalizar_codigo_glosa(cod_glosa, mapa_glosas):
    codigo = '' if cod_glosa is None else str(cod_glosa).strip()
    if not codigo:
        return ''
    if codigo in mapa_glosas:
        return codigo
    codigo_preenchido = codigo.zfill(3)
    if codigo_preenchido in mapa_glosas:
        return codigo_preenchido
    codigo_sem_zero = codigo.lstrip('0')
    if codigo_sem_zero and codigo_sem_zero in mapa_glosas:
        return codigo_sem_zero
    return codigo

def limpar_ruido_descricao_glosa(texto):
    texto_limpo = re.sub('\\s+', ' ', (texto or '').strip())
    if not texto_limpo:
        return ''
    texto_limpo = re.sub('^\\s*(71|72)\\s+', '', texto_limpo, flags=re.IGNORECASE)
    texto_limpo = re.sub('\\b(71|72)\\b(?=\\s+VALOR\\b)', '', texto_limpo, flags=re.IGNORECASE)
    texto_limpo = re.sub('VALOR\\s+TOTAL\\s+DIFERE\\s+VALOR\\s+APRESENTADO', '', texto_limpo, flags=re.IGNORECASE)
    texto_limpo = re.sub('VALOR\\s+APRESENTADO\\s+ACIMA\\s+DO\\s+TETO', '', texto_limpo, flags=re.IGNORECASE)
    texto_limpo = re.sub('\\s+', ' ', texto_limpo).strip(' -/;:,')
    return texto_limpo

def normalizar_justificativa_redacao(justificativa):
    justificativa = (justificativa or '').strip().rstrip('.;:')
    if not justificativa:
        return ''
    if justificativa.lower().startswith(('pois', 'devido', 'por ', 'justificado', 'como ', 'uma vez que', 'já que', 'visto que', 'em razão', 'conforme')):
        return justificativa
    return f'pois {justificativa}'

def normalizar_nome_prestador_risco(nome):
    if not nome:
        return ''
    nome_ascii = unicodedata.normalize('NFKD', str(nome)).encode('ascii', 'ignore').decode('ascii')
    nome_ascii = nome_ascii.upper()
    nome_ascii = re.sub('\\b(CREDENCIADO|PRESTADOR)\\b', ' ', nome_ascii)
    nome_ascii = re.sub('[^A-Z0-9]+', ' ', nome_ascii)
    nome_ascii = re.sub('\\s+', ' ', nome_ascii).strip()
    if not nome_ascii or 'IDENTIFIC' in nome_ascii:
        return ''
    return nome_ascii

def nomes_prestador_risco_equivalentes(nome_a, nome_b):
    norm_a = normalizar_nome_prestador_risco(nome_a)
    norm_b = normalizar_nome_prestador_risco(nome_b)
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    menor, maior = sorted((norm_a, norm_b), key=len)
    if len(menor) >= 8 and menor in maior:
        return True
    return SequenceMatcher(None, norm_a, norm_b).ratio() >= 0.94
