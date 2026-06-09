"""
Extração de glosas de PDFs de relatório Hapvida (5302) por COORDENADAS.

Lê as palavras do pdfplumber (`page.extract_words`) usando a posição x fixa das
colunas "Glosa" e "Sub Glosa". Resolve de forma definitiva os três problemas do
parser textual antigo:

1. Múltiplas glosas no mesmo procedimento — a 2ª glosa vem numa linha "sem valor"
   (sem o decimal que o regex antigo exigia antes do código) e era ignorada.
2. Descrição da glosa e da sub-glosa interleavadas quando o texto quebra em mais
   de uma linha visual (as duas colunas ficam lado a lado).
3. Guia/procedimento que continua na página seguinte (cabeçalho repetido).

Este módulo é a fonte única da lógica: tanto o app (views/2_Relatorio_5302.py)
quanto os testes importam daqui.
"""
import re


def agrupar_linhas_pdf(words, tol=4):
    """Agrupa palavras (pdfplumber.extract_words) em linhas físicas por
    proximidade vertical (top). A tolerância pequena junta texto da mesma linha
    visual que o pdfplumber separa por diferença de baseline (~1px), sem juntar
    linhas de continuação (espaçamento ~16px)."""
    words = sorted(words, key=lambda w: (w['top'], w['x0']))
    linhas = []
    atual = []
    top_ref = None
    for w in words:
        if top_ref is None or abs(w['top'] - top_ref) <= tol:
            atual.append(w)
            if top_ref is None:
                top_ref = w['top']
        else:
            linhas.append(atual)
            atual = [w]
            top_ref = w['top']
    if atual:
        linhas.append(atual)
    return linhas


def extrair_glosas_coords(paginas_words, mapa_glosas, mapa_procedimentos,
                          logins_validos=None):
    """Recebe uma lista (uma entrada por página) de listas de words do pdfplumber
    e retorna a lista de glosas detectadas, na ordem do documento.

    Cada item é um dict:
        {"guia", "proc_cod", "proc_desc", "glosa", "sub"}

    `mapa_glosas`        : {codigo_glosa: descricao}
    `mapa_procedimentos` : {codigo_proc: descricao}
    `logins_validos`     : iterável de logins de auditor; se um login aparece na
                           linha, a glosa é considerada autorizada e ignorada.
    """
    logins_validos = logins_validos or []
    resultados = []

    guia_atual = "N/A"
    proc_cod_atual = "N/A"
    proc_desc_atual = "N/A"
    glosa_x = None
    sub_x = None
    vistos = set()

    for words in paginas_words:
        for row in agrupar_linhas_pdf(words):
            row = sorted(row, key=lambda w: w['x0'])
            textos = [w['text'] for w in row]
            if not row:
                continue

            # Cabeçalho da tabela de itens: fixa as posições das colunas Glosa/Sub
            if 'Glosa' in textos and 'Sub' in textos and 'Procedimento' in textos:
                gx = [w['x0'] for w in row if w['text'] == 'Glosa']
                sx = [w['x0'] for w in row if w['text'] == 'Sub']
                if gx:
                    glosa_x = min(gx)
                sub_x = min(sx) if sx else (glosa_x + 200 if glosa_x else None)
                continue

            # Linha de dados da guia (nº de 7-9 dígitos numa coluna à esquerda).
            # Independe de glosa_x pois pode vir antes do 1º cabeçalho de itens.
            if row[0]['x0'] < 30 and re.fullmatch(r'\d{7,9}', textos[0]):
                # Só reseta o procedimento quando a guia realmente muda (o cabeçalho
                # da guia é repetido quando ela continua na página seguinte).
                if textos[0] != guia_atual:
                    guia_atual = textos[0]
                    proc_cod_atual = "N/A"
                    proc_desc_atual = "N/A"
                continue

            if glosa_x is None or sub_x is None:
                continue  # ainda não entrou num bloco de detalhe

            tol = 8
            col_item = [w for w in row if w['x0'] < 30]
            col_proc = [w for w in row if 30 <= w['x0'] < 140]
            col_glosa = [w for w in row if (glosa_x - tol) <= w['x0'] < (sub_x - tol)]
            col_sub = [w for w in row if w['x0'] >= (sub_x - tol)]

            # Linha de item → atualiza o procedimento corrente
            if col_item and re.fullmatch(r'\d{1,3}', col_item[0]['text']) and col_proc:
                m_proc = re.match(r'^(\d{3,5})', col_proc[0]['text'])
                if m_proc:
                    proc_cod_atual = str(int(m_proc.group(1)))
                    proc_desc_atual = mapa_procedimentos.get(proc_cod_atual, "Procedimento Desconhecido")

            # Glosa na coluna Glosa (vale para a linha do item e p/ continuações)
            if not col_glosa:
                continue
            m_g = re.match(r'^(\d{2,3})', col_glosa[0]['text'])
            if not m_g:
                continue
            cod = m_g.group(1).lstrip('0') or '0'
            if cod not in mapa_glosas or cod in ('71', '72'):
                continue

            # Autorização do auditor (login válido presente na linha) → ignora
            row_text = " ".join(textos).upper()
            if logins_validos and any(f" {login} " in f" {row_text} " for login in logins_validos):
                continue

            # Sub-glosa: código numérico isolado no início da coluna Sub
            sub_cod = ""
            if col_sub:
                m_s = re.match(r'^(\d{1,3})$', col_sub[0]['text'])
                if m_s:
                    sub_cod = m_s.group(1).lstrip('0') or '0'

            chave = (guia_atual, cod, proc_cod_atual, round(row[0]['top']))
            if chave in vistos:
                continue
            vistos.add(chave)

            resultados.append({
                "guia": guia_atual,
                "proc_cod": proc_cod_atual,
                "proc_desc": proc_desc_atual,
                "glosa": cod,
                "sub": sub_cod,
            })

    return resultados
