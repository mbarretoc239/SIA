import re
import csv
import io
import unicodedata
import pdfplumber

from services.relatorio_5302.glosa_matcher import (
    carregar_mapa_procedimentos,
    carregar_mapa_glosas,
    carregar_glosas_criticas,
    carregar_mapa_subglosas,
    carregar_mapa_tipos_glosa
)
from services.relatorio_5302.text_engine import formatar_conectivo_subglosa
from shared.database import DatabaseManager

def processar_pdf(pdf_file):
    mapa_procedimentos = carregar_mapa_procedimentos()
    mapa_glosas = carregar_mapa_glosas()
    glosas_criticas = carregar_glosas_criticas()
    mapa_subglosas = carregar_mapa_subglosas()
    mapa_tipos_glosa = carregar_mapa_tipos_glosa()

    db = DatabaseManager()
    logins_validos = db.carregar_logins_validos()

    meta = {"processo": "Desconhecido", "prestador": "Desconhecido", "producao": "Desconhecida"}

    linhas_extraidas = []
    paginas_words = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            texto_pagina = page.extract_text()
            if texto_pagina:
                linhas_extraidas.extend(texto_pagina.split('\n'))
            paginas_words.append(page.extract_words(use_text_flow=False, keep_blank_chars=False))

    texto_completo = "\n".join(linhas_extraidas)
    
    mp = re.search(r"(?:Processo|Lote)[\s\:\;\-\"\'\=]+(\d+)", texto_completo, re.IGNORECASE)
    if mp: meta["processo"] = mp.group(1).strip()
    
    def parse_float(val_str):
        try:
            clean = re.sub(r'[^\d\,\.-]', '', val_str)
            if ',' in clean and '.' in clean:
                # O separador decimal é o último símbolo (vírgula ou ponto) que aparece;
                # o outro é separador de milhar. O PDF mistura formato BR (1.234,56)
                # e US (1,234.56) entre campos diferentes.
                if clean.rfind(',') > clean.rfind('.'):
                    clean = clean.replace('.', '').replace(',', '.')
                else:
                    clean = clean.replace(',', '')
            elif ',' in clean:
                clean = clean.replace(',', '.')
            return float(clean)
        except:
            return 0.0
            
    m_cobrado = re.search(r"Vl\.Cobrado\s+([\d\.\,]+)", texto_completo, re.IGNORECASE)
    if m_cobrado: meta["valor_cobrado"] = parse_float(m_cobrado.group(1))
    
    m_calculado = re.search(r"Vl\.Calculado\s+([\d\.\,]+)", texto_completo, re.IGNORECASE)
    if m_calculado: meta["valor_calculado"] = parse_float(m_calculado.group(1))
    
    m_glosa = re.search(r"Vl\.\s*Glosa\s+([\d\.\,]+)", texto_completo, re.IGNORECASE)
    if m_glosa: meta["valor_glosa"] = parse_float(m_glosa.group(1))
    
    for i, linha in enumerate(linhas_extraidas):
        if re.search(r'\bCredenciado\b', linha, re.IGNORECASE):
            for j in range(i + 1, min(i + 8, len(linhas_extraidas))):
                prox = linhas_extraidas[j].strip()
                if not prox or re.match(r'^[-\s]+$', prox):
                    continue
                m_cnpj = re.match(r'\S+\s+\d{2}/\d{4}\s+\d{9,14}\s+(.+)', prox)
                if m_cnpj:
                    meta["prestador"] = m_cnpj.group(1).strip()
                break
            break

    if meta["prestador"] == "Desconhecido":
        mpr = re.search(
            r"(?:Prestador|Credenciado)\s*[\:\;\-\=]+\s*(?:\d+[\s\-]+)?([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þa-zà-öø-þ\s\.\&\-]{3,})",
            texto_completo, re.IGNORECASE
        )
        if mpr:
            nome = mpr.group(1).strip()
            if len(nome) > 3:
                meta["prestador"] = nome
        
    mprod = re.search(r"(?:Competência|Mês.*?Produ[cç][aã]o|Produção|Referência).*?(\d{2}/\d{4})", texto_completo, re.IGNORECASE | re.DOTALL)
    if mprod:
        meta["producao"] = mprod.group(1).strip()
        
    from shared.glosa_pdf import extrair_glosas_coords
    registros = extrair_glosas_coords(paginas_words, mapa_glosas, mapa_procedimentos, logins_validos)

    glosas_encontradas = []
    for r in registros:
        cod = r["glosa"]
        sub_cod = r["sub"]
        is_auto = len(cod) <= 2 or cod.startswith('0')
        is_critica = cod in glosas_criticas
        oficial = str(mapa_glosas.get(cod, "")).lower()

        if is_auto:
            tipo = "Automática"
        elif is_critica:
            tipo = "Crítica"
        else:
            tipo = mapa_tipos_glosa.get(cod) or "Técnica"

        justificativa = ""
        if cod != '480' and sub_cod:
            desc_oficial = mapa_subglosas.get((cod, sub_cod))
            if desc_oficial:
                justificativa = formatar_conectivo_subglosa(desc_oficial)

        glosas_encontradas.append({
            "Incluir no Relatório": not is_auto,
            "Tipo": tipo,
            "Guia": str(r["guia"]),
            "Cód. Procedimento": str(r["proc_cod"]),
            "Procedimento": str(r["proc_desc"]).lower(),
            "Glosa": str(cod),
            "Descrição Oficial": oficial,
            "Justificativa": justificativa,
        })

    return glosas_encontradas, meta

def corrigir_mojibake(texto):
    if not isinstance(texto, str):
        return texto
    try:
        return texto.encode('latin1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto

def normalizar_chave_csv(texto):
    texto = corrigir_mojibake(str(texto or "").strip())
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "", texto)

def processar_csv(csv_file):
    glosas_encontradas = []
    meta = {"processo": "Desconhecido", "prestador": "Desconhecido", "producao": "Desconhecida"}
    
    content = csv_file.getvalue()
    linhas_csv = []
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = content.decode(encoding)
            leitor = csv.reader(io.StringIO(texto), delimiter=";")
            for row in leitor:
                linhas_csv.append([corrigir_mojibake(col).strip() for col in row])
            break
        except UnicodeDecodeError:
            continue
            
    mapa_procedimentos = carregar_mapa_procedimentos()
    mapa_glosas = carregar_mapa_glosas()
    glosas_criticas = carregar_glosas_criticas()
    mapa_subglosas = carregar_mapa_subglosas()
    mapa_tipos_glosa = carregar_mapa_tipos_glosa()

    db = DatabaseManager()
    logins_validos = db.carregar_logins_validos()
    
    for i, row in enumerate(linhas_csv):
        chaves = [normalizar_chave_csv(col) for col in row]
        if "credenciado" in chaves:
            idx = chaves.index("credenciado")
            if len(linhas_csv) > i + 1 and len(linhas_csv[i+1]) > idx:
                val = linhas_csv[i+1][idx].strip()
                if len(val) > 3: meta["prestador"] = val
        if "processo" in chaves:
            idx = chaves.index("processo")
            if len(linhas_csv) > i + 1 and len(linhas_csv[i+1]) > idx:
                meta["processo"] = linhas_csv[i+1][idx].strip()
        if "mesproducao" in chaves or "producao" in chaves:
            idx = chaves.index("mesproducao") if "mesproducao" in chaves else chaves.index("producao")
            if len(linhas_csv) > i + 1 and len(linhas_csv[i+1]) > idx:
                meta["producao"] = linhas_csv[i+1][idx].strip()
                
        def parse_float_csv(val_str):
            try:
                clean = re.sub(r'[^\d\,\.-]', '', val_str)
                if ',' in clean and '.' in clean:
                    if clean.rfind(',') > clean.rfind('.'):
                        clean = clean.replace('.', '').replace(',', '.')
                    else:
                        clean = clean.replace(',', '')
                elif ',' in clean:
                    clean = clean.replace(',', '.')
                return float(clean)
            except:
                return 0.0

        # VL.COBRADO / VL.CALCULADO / VL.GLOSA vêm com o valor na mesma linha,
        # na coluna seguinte ao rótulo (ex.: ['VL. COBRADO', '36107,40']) —
        # diferente de "Credenciado"/"Processo", que são cabeçalho de tabela
        # com o valor na linha de baixo.
        if "vlcobrado" in chaves:
            idx = chaves.index("vlcobrado")
            if len(row) > idx + 1:
                meta["valor_cobrado"] = parse_float_csv(row[idx + 1])

        if "vlcalculado" in chaves:
            idx = chaves.index("vlcalculado")
            if len(row) > idx + 1:
                meta["valor_calculado"] = parse_float_csv(row[idx + 1])

        if "vlglosa" in chaves or "vlglosado" in chaves:
            idx = chaves.index("vlglosa") if "vlglosa" in chaves else chaves.index("vlglosado")
            if len(row) > idx + 1:
                meta["valor_glosa"] = parse_float_csv(row[idx + 1])
    
    guia_atual = "N/A"
    item_atual = ""
    proc_cod_atual = "N/A"
    proc_desc_atual = "N/A"
    login_autorizado = False
    
    vistos = set()
    
    for row in linhas_csv:
        campos = [str(col or "").strip() for col in row]
        preenchidos = [(col_idx, valor) for col_idx, valor in enumerate(campos) if valor]
        if not preenchidos:
            continue
            
        chaves = [normalizar_chave_csv(col) for col in campos]
        if chaves[:8] == ["guia", "senha", "codigo", "usuario", "dtsolicitacao", "vlguia", "seq", "situacao"]:
            continue
        if chaves[:11] == ["item", "procedimento", "dini", "dfim", "qt", "vlinf", "qtp", "vlpagto", "e", "liberacao", "glosa"]:
            continue
            
        if re.fullmatch(r"\d{7,9}", campos[0]):
            guia_atual = campos[0]
            item_atual = ""
            proc_cod_atual = "N/A"
            proc_desc_atual = "N/A"
            continue
            
        if re.fullmatch(r"\d{1,3}", campos[0]) and len(campos) > 1:
            match_proc = re.match(r"^(\d{3,10})\s*-\s*(.+)$", campos[1])
            if match_proc:
                item_atual = campos[0]
                proc_cod_atual = str(int(match_proc.group(1)))
                proc_desc_atual = mapa_procedimentos.get(proc_cod_atual) or match_proc.group(2).strip()
                liberacao = campos[9].strip().upper() if len(campos) > 9 else ""
                login_autorizado = bool(liberacao and liberacao in logins_validos)
                continue
                
        if guia_atual and item_atual and len(preenchidos) == 1:
            col_idx, valor = preenchidos[0]
            if col_idx == 10:
                match_glosa = re.match(r"^(\d{1,3})\s*-\s*(.+)$", valor)
                if match_glosa:
                    if login_autorizado:
                        continue 
                        
                    cod = match_glosa.group(1).lstrip('0')
                    if not cod: cod = '0'
                    
                    if cod not in ['71', '72']:
                        is_auto = len(cod) <= 2 or cod.startswith('0')
                        is_critica = cod in glosas_criticas
                        chave_visto = (guia_atual, cod, proc_cod_atual, item_atual)

                        oficial = str(mapa_glosas.get(cod, match_glosa.group(2).strip())).lower()

                        if is_auto:
                            tipo = "Automática"
                        elif is_critica:
                            tipo = "Crítica"
                        else:
                            tipo = mapa_tipos_glosa.get(cod) or "Técnica"

                        if chave_visto not in vistos:
                            glosas_encontradas.append({
                                "Incluir no Relatório": not is_auto,
                                "Tipo": tipo,
                                "Guia": str(guia_atual),
                                "Cód. Procedimento": str(proc_cod_atual),
                                "Procedimento": str(proc_desc_atual).lower(),
                                "Glosa": str(cod),
                                "Descrição Oficial": oficial,
                                "Justificativa": ""
                            })
                            vistos.add(chave_visto)
                    continue
            elif col_idx == 11:
                if glosas_encontradas:
                    match_sub = re.match(r"^(\d{1,3})\s*-\s*(.+)$", valor)
                    ultima_glosa = glosas_encontradas[-1]["Glosa"]
                    
                    if ultima_glosa == '480':
                        glosas_encontradas[-1]["Justificativa"] = ""
                    else:
                        if match_sub:
                            sub_cod = match_sub.group(1).lstrip('0')
                            if not sub_cod: sub_cod = '0'
                            
                            desc_oficial = mapa_subglosas.get((ultima_glosa, sub_cod))
                            texto_bruto = desc_oficial if desc_oficial else match_sub.group(2).strip()
                            glosas_encontradas[-1]["Justificativa"] = formatar_conectivo_subglosa(texto_bruto)
                        else:
                            glosas_encontradas[-1]["Justificativa"] = formatar_conectivo_subglosa(valor.strip())
                continue
                
    return glosas_encontradas, meta
