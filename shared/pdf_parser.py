import re

class PDFParser:
    def __init__(self, app_master):
        self.app_master = app_master

    @property
    def mapa_glosas(self):
        return self.app_master.mapa_glosas

    @property
    def mapa_procedimentos(self):
        return self.app_master.mapa_procedimentos
        
    def extrair_texto_pdf(self, caminho_pdf):
        try:
            pdfplumber = self.app_master._lazy_import_pdfplumber()
            linhas_texto = []
            with pdfplumber.open(caminho_pdf) as pdf:
                for pagina in pdf.pages:
                    texto = pagina.extract_text()
                    if texto:
                        linhas_texto.extend(texto.split('\n'))
            return '\n'.join(self._normalizar_linhas_extraidas_pdf(linhas_texto))
        except Exception:
            return ''

    def _normalizar_linhas_extraidas_pdf(self, linhas):
        linhas_norm = []
        i_norm = 0
        while i_norm < len(linhas):
            linha_atual = re.sub('\\s+', ' ', (linhas[i_norm] or '').strip())
            codigo_glosa, linha_preparada = self.app_master._identificar_cabecalho_glosa_fragmentada(linha_atual)
            if codigo_glosa and codigo_glosa in self.app_master.mapa_glosas:
                partes = [linha_preparada]
                j_norm = i_norm + 1
                coletou_descricao = False
                while j_norm < len(linhas) and len(partes) < 7:
                    proxima = re.sub('\\s+', ' ', (linhas[j_norm] or '').strip())
                    if not proxima:
                        j_norm += 1
                        continue
                    if re.search('\\b(\\d{7,9})\\b', proxima):
                        break
                    if self.app_master._linha_eh_ponte_detalhe_glosa_offline(proxima):
                        j_norm += 1
                        continue
                    proximo_codigo, proxima_preparada = self.app_master._identificar_cabecalho_glosa_fragmentada(proxima)
                    if proximo_codigo and proximo_codigo in self.app_master.mapa_glosas:
                        break
                    if self.app_master._linha_eh_ruido_cabecalho_glosa_offline(proxima):
                        break
                    if not self.app_master._linha_inicia_descricao_glosa_fragmentada(proxima):
                        break
                    partes.append(proxima_preparada)
                    coletou_descricao = True
                    j_norm += 1
                if coletou_descricao or linha_preparada != linha_atual:
                    linhas_norm.append(' '.join(partes))
                    i_norm = j_norm
                    continue
            linhas_norm.append(linhas[i_norm])
            i_norm += 1
        return linhas_norm


    def _linha_parece_item_pdf_segura(self, linha):
        texto = (linha or '').strip().upper()
        if not texto:
            return False
        return bool(re.match('^\\s*\\d{1,3}\\s+\\d{3,4}\\s+[A-Z]', texto))
    
    def _extrair_glosa_textual_linha_segura(self, linha, permitir_orfa=True):
        texto = (linha or '').strip().upper()
        if not texto:
            return (None, None, False)
        texto = re.sub('^(\\d{2,3})(?=[A-ZÃ\x81Ã‰Ã\x8dÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡])', '\\1 ', texto)
        padrao_glosa = re.compile('[\\.,]\\d{2}.*?(?:\\s|^)(\\d{2,3})(?:\\s+\\d{1,2})?\\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\\n]*)$')
        match = padrao_glosa.search(texto)
        if match:
            return (match.group(1), match.group(2).strip(), False)
        if permitir_orfa and (not self._linha_parece_item_pdf_segura(texto)):
            padrao_glosa_orfan = re.compile('^\\s*(\\d{2,3})(?:\\s+\\d{1,2})?(?:\\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9\\s\\-\\/]{2,}))?$')
            match = padrao_glosa_orfan.match(texto)
            if match:
                codigo = self._normalizar_codigo_glosa(match.group(1))
                descricao = (match.group(2) or '').strip()
                if descricao or codigo in self.mapa_glosas:
                    return (match.group(1), descricao, True)
        return (None, None, False)
    
    def _extrair_glosas_textuais_linha_segura(self, linha, permitir_orfa=True):
        texto = re.sub('\\s+', ' ', (linha or '').strip()).upper()
        if not texto:
            return []
        texto = re.sub('^(\\d{2,3})(?=[A-ZÃ\x81Ã‰Ã\x8dÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡])', '\\1 ', texto)
    
        def _token_limpo(token):
            return token.strip('.,;:()[]{}')
    
        def _descricao_inicia(tokens, indice):
            if indice >= len(tokens):
                return False
            return bool(re.match('^[A-ZÃ\x81Ã‰Ã\x8dÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡]', _token_limpo(tokens[indice])))
    
        def _codigo_valido(token):
            token_limpo = _token_limpo(token)
            if not re.fullmatch('\\d{2,3}', token_limpo):
                return ''
            codigo = self._normalizar_codigo_glosa(token_limpo)
            return codigo if codigo in self.mapa_glosas else ''
    
        def _cabecalho_glosa(tokens, indice):
            if indice >= len(tokens):
                return ('', indice)
            codigo = _codigo_valido(tokens[indice])
            if not codigo:
                return ('', indice)
            prox_idx = indice + 1
            if prox_idx >= len(tokens):
                return (codigo, prox_idx)
            if re.fullmatch('\\d{1,2}', _token_limpo(tokens[prox_idx])):
                if prox_idx + 1 >= len(tokens):
                    return (codigo, prox_idx + 1)
                if _descricao_inicia(tokens, prox_idx + 1):
                    return (codigo, prox_idx + 1)
                return ('', indice)
            if _descricao_inicia(tokens, prox_idx):
                return (codigo, prox_idx)
            return ('', indice)
    
        def _extrair_do_trecho(trecho, glosa_orfan):
            tokens = re.findall('\\S+', trecho)
            resultados = []
            idx = 0
            while idx < len(tokens):
                codigo, desc_inicio = _cabecalho_glosa(tokens, idx)
                if not codigo:
                    idx += 1
                    continue
                desc_fim = desc_inicio
                while desc_fim < len(tokens):
                    proximo_codigo, _ = _cabecalho_glosa(tokens, desc_fim)
                    if proximo_codigo:
                        break
                    desc_fim += 1
                descricao = ' '.join(tokens[desc_inicio:desc_fim]).strip()
                if descricao or codigo:
                    resultados.append((codigo, descricao, glosa_orfan))
                idx = max(desc_fim, desc_inicio, idx + 1)
            return resultados
        resultados = []
        match_decimal = re.search('[\\.,]\\d{2}', texto)
        if match_decimal:
            resultados = _extrair_do_trecho(texto[match_decimal.end():], False)
        if not resultados and permitir_orfa and (not self._linha_parece_item_pdf_segura(texto)):
            tokens_orfa = re.findall('\\S+', texto)
            codigo_inicial, _ = _cabecalho_glosa(tokens_orfa, 0)
            if codigo_inicial:
                resultados = _extrair_do_trecho(texto, True)
        if resultados:
            return resultados
        cod_glosa, descricao, glosa_orfan = self._extrair_glosa_textual_linha_segura(linha, permitir_orfa=permitir_orfa)
        if not cod_glosa:
            return []
        return [(self._normalizar_codigo_glosa(cod_glosa), descricao, glosa_orfan)]
    
