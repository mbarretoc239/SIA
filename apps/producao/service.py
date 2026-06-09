import os
import re
import unicodedata

def extrair_nome_prestador_demonstrativo(texto):
    m = re.search('Nome:\\s*(.+)', texto)
    return m.group(1).strip() if m else 'Prestador não identificado'

def extrair_linhas_demonstrativo(caminho_pdf, lazy_import_pdfplumber):
    pdfplumber = lazy_import_pdfplumber()
    linhas = []
    with pdfplumber.open(caminho_pdf) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ''
            for linha in texto.splitlines():
                lin = re.sub('\\s+', ' ', linha).strip()
                if lin:
                    linhas.append(lin)
    return linhas

def normalizar_descricao_procedimento(descricao):
    return re.sub('\\s+', ' ', (descricao or '').strip())

def extrair_procedimento_demonstrativo_linha(linha, mapa_procedimentos):
    linha = re.sub('\\s+', ' ', (linha or '').strip())
    if not linha or 'DEMONSTRATIVO DE PAGAMENTO' in linha.upper():
        return None
    if not re.search('\\d{2}/\\d{2}/\\d{4}', linha):
        return None
    linha_regex = unicodedata.normalize('NFKD', linha).encode('ascii', 'ignore').decode('ascii')
    linha_regex = re.sub('\\s+', ' ', linha_regex).strip()
    padrao = re.compile('\\d{2}/\\d{2}/\\d{4}\\s+\\d+\\s+(\\d{3,4})\\s*([A-Za-z0-9/\\-\\.\\(\\) ]+?)\\s+\\d{1,2}\\s+\\d{1,2}(?:\\s+[A-Z]{1,4})?\\s+[\\d\\.,]+\\s+[\\d\\.,]+\\s+[\\d\\.,]+\\s*$')
    m = padrao.search(linha_regex)
    if not m:
        return None
    codigo = m.group(1).strip()
    codigo_normalizado = str(int(codigo)) if codigo.isdigit() else codigo
    descricao = mapa_procedimentos.get(codigo_normalizado) or normalizar_descricao_procedimento(m.group(2))
    if len(descricao) < 3:
        return None
    nums = re.findall('[\\d\\.]+,\\d{2}', linha_regex)
    valor_pago = 0.0
    if len(nums) >= 2:
        try:
            valor_pago = float(nums[-2].replace('.', '').replace(',', '.'))
        except Exception:
            valor_pago = 0.0
    return {'codigo': codigo_normalizado, 'descricao': descricao, 'valor_pago': valor_pago}

def processar_demonstrativos_producao(caminhos_pdf, mapa_procedimentos, lazy_import_pdfplumber, norm_prestador_func, eq_prestador_func):
    contador = {}
    valores = {}
    total_linhas = 0
    prestadores = []
    detalhes_pdf = []
    grupos_prestador = []
    for caminho_pdf in caminhos_pdf:
        linhas = extrair_linhas_demonstrativo(caminho_pdf, lazy_import_pdfplumber)
        if not linhas:
            continue
        prestador = extrair_nome_prestador_demonstrativo('\n'.join(linhas[:20]))
        prestadores.append(prestador)
        if norm_prestador_func(prestador):
            grupo_existente = next((grupo for grupo in grupos_prestador if eq_prestador_func(grupo['nome'], prestador)), None)
            if grupo_existente is None:
                grupos_prestador.append({'nome': prestador, 'arquivos': [os.path.basename(caminho_pdf)]})
            else:
                grupo_existente['arquivos'].append(os.path.basename(caminho_pdf))
        lidas_pdf = 0
        for linha in linhas:
            item = extrair_procedimento_demonstrativo_linha(linha, mapa_procedimentos)
            if not item:
                continue
            chave = f"{item['codigo']} - {item['descricao']}"
            contador[chave] = contador.get(chave, 0) + 1
            valores[chave] = valores.get(chave, 0.0) + float(item.get('valor_pago', 0.0) or 0.0)
            total_linhas += 1
            lidas_pdf += 1
        detalhes_pdf.append((os.path.basename(caminho_pdf), prestador, lidas_pdf))
    if len(grupos_prestador) > 1:
        descricoes = []
        for grupo in grupos_prestador[:3]:
            nomes_arquivos = ', '.join(grupo['arquivos'][:2])
            extras = len(grupo['arquivos']) - min(2, len(grupo['arquivos']))
            if extras > 0:
                nomes_arquivos += f' e +{extras}'
            descricoes.append(f"{grupo['nome']} ({nomes_arquivos})")
        raise ValueError('Os demonstrativos selecionados pertencem a prestadores diferentes. Separe um lote por prestador. Detectados: ' + '; '.join(descricoes))
    if not contador:
        raise ValueError('Nenhuma linha de procedimento foi identificada. Confirme se o PDF e um demonstrativo de pagamento com tabela de servicos.')
    if grupos_prestador:
        prestador_final = grupos_prestador[0]['nome']
    else:
        prestador_final = prestadores[0] if prestadores else 'Prestador nao identificado'
    ranking = sorted(contador.items(), key=lambda kv: (-kv[1], kv[0]))
    return {'prestador': prestador_final, 'qtd_pdfs': len(caminhos_pdf), 'total_linhas': total_linhas, 'ranking': ranking, 'valores': valores, 'detalhes_pdf': detalhes_pdf}
