"""Motor de classificação de ocorrências do FAROL.

Decide, a partir do texto de uma ocorrência de auditoria, se o processo deve
ser S (vai pro farol), N (não vai), PAR (análise de padrão/fraude) ou
REVISAR (ambíguo, revisão manual). Não depende de pandas nem de arquivo —
só de string in, string out.
"""

import difflib
import re
import unicodedata

PALAVRAS_MODELO_LIMPO = set('''PROCESSO REALIZADO ANALISADO ANALISE POR AMOSTRAGEM SEM ESPECIALIDADE ESPECIALIDADES ESPEC
CRITICA CRITICAS NO NA NAS DO DA DOS DAS DE ENVIO IMAGENS SOMENTE DESVIO DESVIOS E PRESTADOR ENVIOU AS
RADIOGRAFIAS RADIOGRAFIA FISICAS FISICA LIBERADO LIBERACAO NESSA PRODUCAO IN COMPANY SOLICITACOES BOA CONDUTA
INTEGRANTE PROJETO REMUNERACAO VARIAVEL PELA IA ALTA'''.split())

# palavras-base que toleram erro de digitação (a planilha tem bastante typo nelas)
PALAVRAS_BASE_TOLERANTES_TYPO = ['REALIZADO', 'AMOSTRAGEM', 'ESPECIALIDADES', 'CRITICAS', 'ANALISADO', 'ESPECIALIDADE']


def _normalizar(t):
    t = t.upper()
    for a, b in [('Á', 'A'), ('Ã', 'A'), ('Â', 'A'), ('É', 'E'), ('Ê', 'E'),
                 ('Í', 'I'), ('Ó', 'O'), ('Õ', 'O'), ('Ô', 'O'), ('Ç', 'C')]:
        t = t.replace(a, b)
    return t


def _e_variacao_com_typo(palavra, base):
    if abs(len(palavra) - len(base)) > 1:
        return False
    return difflib.SequenceMatcher(None, palavra, base).ratio() > 0.82


def _e_palavra_do_modelo(palavra):
    if palavra in PALAVRAS_MODELO_LIMPO:
        return True
    if len(palavra) <= 3:
        return False  # nao aplica tolerancia de typo em palavra curta (risco de falso positivo)
    return any(_e_variacao_com_typo(palavra, base) for base in PALAVRAS_BASE_TOLERANTES_TYPO)


def eh_so_modelo_limpo(t):
    """True se TODA palavra do texto for uma das palavras-modelo conhecidas de
    'sem problema' (com tolerância a erro de digitação nas palavras-chave) —
    ou seja, o texto não tem nenhum conteúdo extra descrevendo um achado real."""
    tt = _normalizar(t)
    tt = re.sub(r'\d{1,3}([.,]\d+)?\s*%', '', tt)  # tira percentuais (ex: 100%, 98%)
    palavras = re.findall(r'[A-Z]+', tt)
    return all(_e_palavra_do_modelo(p) for p in palavras)


PADROES_ACHADO_TECNICO = [
    r'NAO\s+ENVIOU', r'NAO\s+ENVIA(DO)?', r'NAO\s+FOI\s+ENVI(A|E)?DO', r'NAO\s+FORAM\s+ENVIAD(O|A)S?',
    r'NAO\s+ENVIO\s+DE', r'SEM\s+ENVIO\s+D[AEO]', r'SEM\s+ENVIAR', r'NAO\s+ANEXOU', r'NAO\s+ANEXA',
    r'DEIXOU\s+DE\s+(ENVIAR|ANEXAR)', r'SEM\s+RX\b', r'FALTA\s+DE\s+RX', r'FALTA\s+DE\s+RADIOGRAFIA',
    r'FALTA\s+DE\s+FOTO', r'FALTA\s+DE\s+SELAMENTO', r'FALTA\s+DE\s+MATERIAL',
    r'FALTA(NDO)?\s+(RX|RADIOGRAFIA|FOTO|IMAGEM)\b',
    r'SUB\s*-?\s*OBT[UI]RADO', r'SOBRE\s*-?\s*OBT[UI]RADO', r'NAO\s+OBTURADO',
    r'MA\s+QUALIDADE', r'PESSIMA\s+QUALIDADE', r'INSATISFAT[OÓ]RIO',
    r'\bCURTOS?\b', r'MAL\s+ADAPTADA', r'DESADAPTADA', r'MA\s+ADAPTA[CÇ][AÃ]O',
    r'NAO\s+EVIDENCIA', r'NAO\s+CORRESPOND', r'AUSENCIA\s+DE', r'APIC(E|ES)\s+CORTADO',
    r'BANCO\s+DE\s+IMAGENS', r'PANORAMICA\s+COMO\s+PERIAPICAL', r'RECORTE\s+DE\s+PANORAMICA',
    r'NAO\s+EXECUTOU', r'NAO\s+EXECUTAD(O|A)S?',
]

PADROES_INDICIO_PAGAMENTO = [
    r'FOI\s+PAGO', r'FORAM\s+PAGAS?', r'REPASSE', r'\bIOD\b',
]

# --- Acrescentado na integração com o SIA (pedido explícito do usuário) ---
# Frases que, sozinhas, valem S. Comparação pelo texto INTEIRO normalizado
# (sem acento, sem pontuação, sem caixa) -- NÃO entram na whitelist de
# palavras porque PARA/O/PERIODO liberariam S pra outros textos. Qualquer
# coisa a mais no texto (ex: uma glosa citada em seguida) segue as regras de
# sempre.
FRASES_SEM_OCORRENCIAS = frozenset({
    'SEM OCORRENCIAS PARA O PERIODO AUDITADO',
    'SEM OCORRENCIAS PARA O PERIODO SOLICITADO',
})

# Modelos de fechamento compulsório que viram S quando o usuário marca
# "Incluir no SIM os fechamentos compulsórios" (por padrão continuam N, ver
# classificar_ocorrencia). Só o texto INTEIRO igual a um dos modelos conta --
# texto com glosa/observação a mais, "REABERTO", "AÇÃO PARA EVITAR ATRASO" e o
# modelo "100% DE LIBERAÇÃO DA IA" (o que vale é a liberação do mês atual, ver
# regra dos 100% em processamento.py) ficam de fora e continuam N.
# Lista editável: a cada mês pode aparecer modelo novo -- acrescentar aqui
# (já normalizado, ver normalizar_frase).
MODELOS_FECHAMENTO_COMPULSORIO_SIM = frozenset({
    'FECHAMENTO COMPULSORIO',
    'FECHAMENTO COMPULSORIO SEM DESVIO NO MES ANTERIOR',
    'FECHAMENTO COMPULSORIO SEM DESVIOS NO MES ANTERIOR',
    'FECHAMENTO COMPULSORIO PROCESSO COM MENOS DE 20 PROCEDIMENTOS E SEM ESPECIALIDADE CRITICA',
    'FECHAMENTO COMPULSORIO PROCESSO SEM ESPECIALIDADE CRITICA',
    'FECHAMENTO COMPULSORIO SEM ESPECIALIDADE CRITICA',
    'FECHAMENTO COMPULSORIO PROCESSO S ESPEC CRITICA',
})


def normalizar_frase(texto):
    """Maiúsculas, sem acento, sem pontuação, espaços colapsados -- forma
    usada pra comparar o texto INTEIRO com as frases/modelos acima."""
    sem_acento = ''.join(
        c for c in unicodedata.normalize('NFKD', str(texto)) if not unicodedata.combining(c)
    )
    return re.sub(r'[^A-Z0-9]+', ' ', sem_acento.upper()).strip()


def tem_fechamento_compulsorio(texto):
    """Mesmo teste da regra soberana de classificar_ocorrencia."""
    return 'FECHAMENTO COMPULS' in str(texto).upper()


def eh_modelo_fechamento_compulsorio(texto):
    return normalizar_frase(texto) in MODELOS_FECHAMENTO_COMPULSORIO_SIM


def _tem_achado_tecnico(t):
    tt = _normalizar(t)
    return any(re.search(p, tt) for p in PADROES_ACHADO_TECNICO)


def _tem_indicio_de_pagamento(t):
    tt = _normalizar(t)
    return any(re.search(p, tt) for p in PADROES_INDICIO_PAGAMENTO)


def classificar_ocorrencia(texto):
    """Classifica um texto de ocorrência em S (vai pro farol), N (não vai), PAR
    (análise de padrão/fraude) ou REVISAR (ambíguo).

    Estratégia: só vira S se TODA palavra do texto for uma das palavras-modelo
    conhecidas de "sem problema" (whitelist tolerante a typo). Qualquer palavra
    fora dessa lista (mesmo sem falar "glosa" ou "desvio") não vira S
    automaticamente — cai em REVISAR ou N. É proposital pecar por excesso de
    REVISAR em vez de deixar passar um achado real como S.
    """
    if texto is None or not str(texto).strip() or str(texto).strip().lower() == 'nan':
        return "REVISAR"  # sem texto -> mais seguro conferir manualmente

    t = str(texto).upper()
    t = re.sub(r'GLOSSA', 'GLOSA', t)  # typo comum na fonte ("glossa" com dois S)

    # prioridade 1: fechamento compulsório sempre vai pra N,
    # independente de mencionar glosa ou desvio
    if "FECHAMENTO COMPULS" in t:
        return "N"

    # prioridade 2: sigla PAR (análise de padrão/fraude) tem aba própria,
    # independente do resultado de glosa/desvio -- "análise integral" é a mesma
    # análise de risco/fraude, só que escrita por extenso, sem a sigla "PAR"
    if re.search(r'\bPAR\b', t) or re.search(r'AN[ÁA]LISE\s+INTEGRAL', t):
        return "PAR"

    # texto que é SÓ "sem ocorrências para o período auditado/solicitado" -> S
    # (regra acrescentada na integração com o SIA -- ver FRASES_SEM_OCORRENCIAS)
    if normalizar_frase(t) in FRASES_SEM_OCORRENCIAS:
        return "S"

    # se o texto é só o modelo padrão de "sem problema", sem nada a mais -> S
    if eh_so_modelo_limpo(t):
        return "S"

    # a partir daqui, o texto tem conteúdo além do modelo limpo -> não é mais S automático
    t_limpo = t

    padroes_negativos = [
        r'NENHUMA\s+GLOSA[A-ZÀ-Ú\s]*ENCONTRADA[A-ZÀ-Ú\s]*',
        r'NENHUMA\s+GLOSA[A-ZÀ-Ú\s]*APLIC[ÁA]VEL[A-ZÀ-Ú\s]*',
        r'SEM\s+GLOSAS?\b',
        r'N[ÃA]O\s+FOI\s+GLOSADO',
    ]
    tinha_padrao_negativo = False
    for pad in padroes_negativos:
        novo = re.sub(pad, '', t_limpo)
        if novo != t_limpo:
            tinha_padrao_negativo = True
        t_limpo = novo

    tem_glosa_real = 'GLOSA' in t_limpo

    if tem_glosa_real and not tinha_padrao_negativo:
        return "N"

    # não achou glosa explícita, mas o texto pode descrever um achado técnico real
    # (ex: "não enviou RX", "conduto subobturado", "pino curto") sem usar a palavra
    # glosa/desvio -> também vira N, EXCETO quando o texto também indica que, apesar
    # do achado, o procedimento foi pago mesmo assim (ex: caso de IOD)
    tem_achado = _tem_achado_tecnico(t)
    if tem_achado and not _tem_indicio_de_pagamento(t):
        return "N"

    # texto disse explicitamente "sem glosa" / "nenhuma glosa aplicável", não tem
    # achado técnico, E o que sobra depois de tirar essa frase de negação é só
    # modelo limpo (sem nenhum outro conteúdo extra, tipo suspeita de fraude ou
    # observação pra próxima produção) -> aí sim é uma afirmação de "sem problema", vira S
    if tinha_padrao_negativo and not tem_achado and eh_so_modelo_limpo(t_limpo):
        return "S"

    # tem conteúdo extra que não é um dos modelos limpos, não é achado técnico
    # reconhecido, ou foi achado técnico mas com indício de pagamento -> revisão manual
    return "REVISAR"


def classificar_texto(texto, incluir_compulsorio_no_sim=False):
    """Ponto de entrada usado pelo pipeline do SIA. Com
    `incluir_compulsorio_no_sim=False` (padrão) é exatamente
    classificar_ocorrencia. Com True, o texto que for INTEIRO um dos
    MODELOS_FECHAMENTO_COMPULSORIO_SIM vira S em vez de N -- qualquer outro
    texto (inclusive outro fechamento compulsório) segue classificar_ocorrencia."""
    if incluir_compulsorio_no_sim and eh_modelo_fechamento_compulsorio(texto):
        return "S"
    return classificar_ocorrencia(texto)


def prioridade(lista_classificacoes):
    """Quando um prestador tem mais de uma ocorrência: N > PAR > REVISAR > S."""
    if "N" in lista_classificacoes:
        return "N"
    elif "PAR" in lista_classificacoes:
        return "PAR"
    elif "REVISAR" in lista_classificacoes:
        return "REVISAR"
    else:
        return "S"
