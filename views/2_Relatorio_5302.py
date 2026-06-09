import streamlit as st
import pdfplumber
import re
import pandas as pd
import csv
import collections
import io
import unicodedata

import json
import os

st.set_page_config(page_title="Relatório 5302", page_icon="📄", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar esta ferramenta.")
    st.stop()



def salvar_no_supabase(arquivo_origem, texto_gerado, df_final, meta):
    import requests
    if df_final is None or df_final.empty:
        raise ValueError("Não há glosas para salvar. O processo será ignorado.")
        
    url = st.secrets["supabase"]["url"].rstrip("/")
    key = st.secrets["supabase"]["key"]
    
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    # 1. Verifica duplicatas pelo número do processo (se houver número)
    processo_id = meta.get("processo", "Desconhecido")
    if processo_id != "Desconhecido":
        check_res = requests.get(
            f"{url}/rest/v1/analises_auditoria?select=id&processo=eq.{processo_id}&limit=1",
            headers=headers
        )
        if check_res.ok and len(check_res.json()) > 0:
            raise ValueError(f"O processo {processo_id} já consta no banco de dados!")
    
    # 2. Salva se passou na checagem
    data = {
        "arquivo_origem": arquivo_origem,
        "processo": processo_id,
        "prestador": meta.get("prestador", "Desconhecido"),
        "data_producao": meta.get("producao", "Desconhecida"),
        "texto_gerado": texto_gerado,
        "glosas_json": df_final.fillna("").to_dict(orient="records")
    }
    
    response = requests.post(f"{url}/rest/v1/analises_auditoria", headers=headers, json=data)
    if response.status_code == 403:
        raise ValueError("Permissão negada (Erro 403). Verifique as políticas de RLS no Supabase.")
    response.raise_for_status()

def limpar_banco_supabase(meses=6):
    import requests
    from datetime import datetime, timedelta
    
    url = st.secrets["supabase"]["url"].rstrip("/")
    key = st.secrets["supabase"]["key"]
    
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    
    # Calcula data limite
    data_limite = (datetime.now() - timedelta(days=meses*30)).isoformat()
    
    # RLS: a role anon deve ter permissão de DELETE, caso contrário falha.
    # Adicionaremos essa nota para o usuário.
    response = requests.delete(
        f"{url}/rest/v1/analises_auditoria?criado_em=lt.{data_limite}",
        headers=headers
    )
    if response.status_code == 403:
        raise ValueError("Sem permissão de exclusão. Adicione uma política de DELETE para a role anon.")
    response.raise_for_status()

def mixar_textos_inteligente(textos):
    if not textos: return ""
    if len(textos) == 1: return textos[0]
    
    padrao_saudacao = re.compile(r"^(CARO PRESTADOR,|PREZADO\(A\) PRESTADOR\(A\),?|Prezado\(a\) Prestador\(a\),?)\s*", re.IGNORECASE)
    padrao_despedida = re.compile(r"(EM CASO[S]? DE DÚVIDA[S]?.*?4002[^\d]*2722\.?)", re.IGNORECASE | re.DOTALL)
    
    saudacao_final = "CARO PRESTADOR,\n"
    despedida_final = "\n\nEM CASOS DE DÚVIDAS, ENTRAR EM CONTATO COM A CAP, PELO TELEFONE 4002-2722."
    
    corpos = []
    for t in textos:
        t_clean = t.strip()
        t_clean = padrao_saudacao.sub("", t_clean).strip()
        t_clean = padrao_despedida.sub("", t_clean).strip()
        if t_clean:
            corpos.append(t_clean)
            
    if not corpos:
        return ""
        
    texto_combinado = corpos[0]
    conectivos = [
        "Além disso, ",
        "Adicionalmente, ",
        "Ressaltamos também que ",
        "Ademais, "
    ]
    
    for i in range(1, len(corpos)):
        conectivo = conectivos[(i-1) % len(conectivos)]
        paragrafo = corpos[i].strip()
        
        # Identificar se o texto está todo em maiúsculo para combinar o case
        letras = [c for c in paragrafo if c.isalpha()]
        maiusculas = [c for c in letras if c.isupper()]
        is_upper = len(letras) > 0 and (len(maiusculas) / len(letras)) > 0.8
        
        if is_upper:
            conectivo = conectivo.upper()
        else:
            if paragrafo and paragrafo[0].isupper() and (len(paragrafo) == 1 or paragrafo[1].islower()):
                paragrafo = paragrafo[0].lower() + paragrafo[1:]
                
        texto_combinado += "\n\n" + conectivo + paragrafo
            
    return saudacao_final + "\n" + texto_combinado + despedida_final

@st.cache_data(ttl=300)
def carregar_mapa_glosas():
    from shared.database import DatabaseManager
    db = DatabaseManager()
    mapa = {}
    try:
        rows = db._get("glosas_padrao?select=codigo,descricao")
        for r in rows:
            mapa[r['codigo'].strip()] = r['descricao'].strip()
    except Exception:
        pass
    # Merge com customizadas (override)
    try:
        for gb in db.carregar_glosas_customizadas():
            mapa[str(gb['codigo_glosa']).strip()] = str(gb['descricao']).strip()
    except Exception:
        pass
    return mapa

@st.cache_data(ttl=300)
def carregar_mapa_procedimentos():
    from shared.database import DatabaseManager
    db = DatabaseManager()
    mapa = {}
    try:
        rows = db._get("tabela_procedimentos?select=codigo_tuss,descricao")
        for r in rows:
            mapa[str(r['codigo_tuss']).strip()] = r['descricao'].strip()
    except Exception:
        pass
    return mapa

@st.cache_data(ttl=60)
def carregar_glosas_criticas():
    caminho = r'C:\Users\matheus.cardoso\AppData\Roaming\AuditoriaOdonto\CLASSIFICACAO_GLOSAS.csv'
    criticas = set()
    try:
        with open(caminho, 'r', encoding='utf-8-sig', errors='ignore') as f:
            reader = csv.reader(f, delimiter=';')
            headers = next(reader, None)
            tipo_idx = headers.index('TIPO') if headers and 'TIPO' in headers else -1
            if tipo_idx != -1:
                for row in reader:
                    if len(row) > tipo_idx and str(row[tipo_idx]).strip().upper() == 'CRITICA':
                        criticas.add(str(row[0]).strip())
    except Exception:
        criticas = {'438', '450', '463', '480'}
    
    if not criticas:
        criticas = {'438', '450', '463', '480'}
        
    # Integração com Nuvem (Override)
    try:
        from shared.database import DatabaseManager
        db = DatabaseManager()
        glosas_banco = db.carregar_glosas_customizadas()
        for gb in glosas_banco:
            cod = str(gb['codigo_glosa']).strip()
            if gb.get('is_critica'):
                criticas.add(cod)
            else:
                if cod in criticas:
                    criticas.remove(cod)
    except Exception as e:
        pass
    return criticas

@st.cache_data(ttl=300)
def carregar_mapa_subglosas():
    from shared.database import DatabaseManager
    db = DatabaseManager()
    mapa = {}
    try:
        rows = db._get("glosas_padrao?select=codigo,sub_glosa,descricao_sub_glosa&sub_glosa=neq.")
        for r in rows:
            if r.get('sub_glosa') and r.get('descricao_sub_glosa'):
                mapa[(r['codigo'].strip(), r['sub_glosa'].strip())] = r['descricao_sub_glosa'].strip()
    except Exception:
        pass
    return mapa

def formatar_conectivo_subglosa(t):
    if not t: return ""
    t_orig = t
    t = t.strip().lower()
    if t.endswith('.'): t = t[:-1]
    
    # NOVAS REGRAS DE CONJUGAÇÃO (Gramática Perfeita)
    t = t.replace('não enviada', 'não foi enviada').replace('não enviado', 'não foi enviado')
    t = t.replace('nã£o enviada', 'não foi enviada').replace('nã£o enviado', 'não foi enviado')
    t = t.replace('usuário em tratamento', 'usuário está em tratamento')
    t = t.replace('usuã¡rio em tratamento', 'usuário está em tratamento')
    t = t.replace('usurio em tratamento', 'usuário está em tratamento')
    t = t.replace('solicitar todas as faces', 'deve-se solicitar todas as faces')
    t = t.replace('incluso no procedimento', 'está incluso no procedimento')
    t = t.replace('incompatível com', 'é incompatível com').replace('incompatvel com', 'é incompatível com')
    
    if t in ['raio x final', 'raio x inicial', 'rx final', 'rx inicial']:
        return 'por falta do ' + t
    if t in ['imagem', 'fotografia', 'tomografia', 'documentação', 'documentaçã£o', 'radiografia', 'panorâmica', 'panormica']:
        return 'por falta da ' + t

    if t.startswith(('pois ', 'devido ', 'visto que ', 'por ')):
        return t_orig[0].lower() + t_orig[1:]
        
    if t.startswith('falta '):
        if not t.startswith('falta de '):
            return re.sub(r'^falta\s+', 'por falta de ', t)
        return 'por ' + t
    
    elif t.startswith('no envio ') or t.startswith('não envio ') or t.startswith('nã£o envio '):
        return re.sub(r'^n[aã]o envio\s+(de\s+)?', 'pelo não envio de ', t)
    elif t.startswith('no foi enviado ') or t.startswith('não foi enviado '):
        return 'pois ' + t
    elif t.startswith('ausncia') or t.startswith('ausência'):
        return 'por ' + t
        
    elif t.startswith('imagem repassada'):
        return t.replace('imagem repassada', 'pois a imagem foi repassada', 1)
    elif t.startswith(('imagem', 'fotografia', 'panorâmica', 'panormica', 'radiografia', 'tomografia', 'documentação')):
        return 'pois a ' + t
    elif t.startswith(('raio x', 'rx', 'levantamento radiográfico', 'conduto', 'detalhamento')):
        return 'pois o ' + t
        
    elif t.startswith(('laudo', 'relatório', 'relatrio', 'histórico', 'histerico')):
        return 'visto que o ' + t
    elif t.startswith(('requisição', 'requisio', 'solicitação', 'solicitao', 'prescrição', 'prescrio', 'divergência', 'divergncia', 'falha')):
        return 'devido à ' + t
        
    elif t.startswith(('procedimento', 'usuário', 'usurio')):
        return 'visto que o ' + t
    elif t.startswith('procedimentos'):
        return 'visto que os ' + t
    elif t.startswith(('idade', 'justificativa')):
        return 'pois a ' + t
    elif t.startswith(('presença', 'presena', 'sobrecontorno')):
        return 'pois há ' + t
    else:
        return 'pois ' + t

mapa_glosas = carregar_mapa_glosas()
mapa_procedimentos = carregar_mapa_procedimentos()
glosas_criticas = carregar_glosas_criticas()
mapa_subglosas = carregar_mapa_subglosas()

def processar_pdf(pdf_file):
    import pdfplumber

    mapa_procedimentos = carregar_mapa_procedimentos()
    mapa_glosas = carregar_mapa_glosas()
    glosas_criticas = carregar_glosas_criticas()
    mapa_subglosas = carregar_mapa_subglosas()

    from shared.database import DatabaseManager
    db = DatabaseManager()
    logins_validos = db.carregar_logins_validos()

    meta = {"processo": "Desconhecido", "prestador": "Desconhecido", "producao": "Desconhecida"}

    # Lê o PDF uma vez: texto (para meta) + palavras com coordenadas (para glosas)
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
    
    # Estratégia 1: header "Credenciado" com dados na linha seguinte
    # Formato Hapvida: linha de traços separa header dos dados
    # 'Processso Mês Producao CGC/CPF Credenciado'
    # '------...'
    # '8202619126 02/2026 32441906000138 NEGROMONTE ODONTOLOGIA LTDA'
    for i, linha in enumerate(linhas_extraidas):
        if re.search(r'\bCredenciado\b', linha, re.IGNORECASE):
            for j in range(i + 1, min(i + 8, len(linhas_extraidas))):
                prox = linhas_extraidas[j].strip()
                if not prox or re.match(r'^[-\s]+$', prox):
                    continue  # pula vazias e separadores de traço
                m_cnpj = re.match(r'\S+\s+\d{2}/\d{4}\s+\d{9,14}\s+(.+)', prox)
                if m_cnpj:
                    meta["prestador"] = m_cnpj.group(1).strip()
                break
            break

    # Estratégia 2: inline — 'Prestador: NOME' ou 'Credenciado: NOME'
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
        
    # ── Detecção de glosas por COORDENADAS (lógica em shared/glosa_pdf.py) ──────
    from shared.glosa_pdf import extrair_glosas_coords
    registros = extrair_glosas_coords(paginas_words, mapa_glosas, mapa_procedimentos, logins_validos)

    glosas_encontradas = []
    for r in registros:
        cod = r["glosa"]
        sub_cod = r["sub"]
        is_auto = len(cod) <= 2 or cod.startswith('0')
        is_critica = cod in glosas_criticas
        oficial = str(mapa_glosas.get(cod, "")).lower()

        justificativa = ""
        if cod != '480' and sub_cod:
            desc_oficial = mapa_subglosas.get((cod, sub_cod))
            if desc_oficial:
                justificativa = formatar_conectivo_subglosa(desc_oficial)

        glosas_encontradas.append({
            "Incluir no Relatório": not is_auto,
            "Tipo": "Automática" if is_auto else ("Crítica" if is_critica else "Técnica"),
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
    import unicodedata
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "", texto)

def processar_csv(csv_file):
    import csv, io
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
    
    from shared.database import DatabaseManager
    db = DatabaseManager()
    logins_validos = db.carregar_logins_validos()
    
    # Extrair meta baseado na posição
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
                # Verifica a liberação (login do auditor) - coluna 9
                liberacao = campos[9].strip().upper() if len(campos) > 9 else ""
                login_autorizado = bool(liberacao and liberacao in logins_validos)
                continue
                
        if guia_atual and item_atual and len(preenchidos) == 1:
            col_idx, valor = preenchidos[0]
            if col_idx == 10:
                match_glosa = re.match(r"^(\d{1,3})\s*-\s*(.+)$", valor)
                if match_glosa:
                    if login_autorizado:
                        continue # Ignora a glosa pois o procedimento foi autorizado pelo auditor!
                        
                    cod = match_glosa.group(1).lstrip('0')
                    if not cod: cod = '0'
                    
                    if cod not in ['71', '72']:
                        is_auto = len(cod) <= 2 or cod.startswith('0')
                        is_critica = cod in glosas_criticas
                        chave_visto = (guia_atual, cod, proc_cod_atual, item_atual)
                        
                        oficial = str(mapa_glosas.get(cod, match_glosa.group(2).strip())).lower()
                        
                        if chave_visto not in vistos:
                            glosas_encontradas.append({
                                "Incluir no Relatório": not is_auto,
                                "Tipo": "Automática" if is_auto else ("Crítica" if is_critica else "Técnica"),
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
                # Se for SubGlosa (coluna 11), registramos como Justificativa da glosa anterior usando o Motor Semântico
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

def gerar_texto(df_glosas, tipo_geracao):
    df = df_glosas[df_glosas['Incluir no Relatório'] == True].copy()
    
    if tipo_geracao == "Só Glosas Críticas":
        df = df[df['Tipo'] == 'Crítica']
        
    if df.empty:
        return "Nenhuma glosa aplicável encontrada no documento para o filtro selecionado."
        
    prefixo = ""
    
    if tipo_geracao == "Versão Completa (Detalhada)":
        clausulas = []
        for i, row in df.iterrows():
            justificativa = (str(row.get('Justificativa') or "")).strip()
            glosa = str(row['Glosa'])
            desc_oficial = str(row['Descrição Oficial'])
            cod_proc = str(row['Cód. Procedimento'])
            proc = str(row['Procedimento']).lower()
            guia = str(row['Guia'])
            
            texto = f"glosa por {desc_oficial} (glosa {glosa}) no procedimento {cod_proc} - {proc}, na guia {guia}"
            if justificativa:
                texto += f", {justificativa}"
            clausulas.append(texto)
        if not clausulas:
            return "Nenhuma glosa selecionada."
        texto_final = "; ".join(clausulas[:-1]) + "; e " + clausulas[-1] + "."
        return "O prestador apresentou " + texto_final

    # --- NOVO MOTOR MISTO COM FATORAÇÃO DE GUIAS ---
    itens = []
    for _, row in df.iterrows():
        justificativa = (str(row.get('Justificativa') or "")).strip()
        glosa = str(row['Glosa'])
        desc_oficial = str(row['Descrição Oficial'])
        cod_proc = str(row['Cód. Procedimento'])
        proc = str(row['Procedimento']).lower()
        guia = str(row['Guia'])
        
        proc_str = f"{cod_proc} - {proc}" if cod_proc != "N/A" else "procedimento não identificado"
        
        itens.append({
            "glosa": glosa,
            "desc": desc_oficial,
            "justificativa": justificativa,
            "proc": proc_str,
            "guia": guia
        })
        
    def formatar_guias(lista):
        if not lista or lista[0] == "Desconhecida": return ""
        if len(lista) == 1: return f"guia {lista[0]}"
        if len(lista) == 2: return f"guias {lista[0]} e {lista[1]}"
        if len(lista) == 3: return f"guias {lista[0]}, {lista[1]} e {lista[2]}"
        return f"guias {lista[0]}, {lista[1]}, {lista[2]} e mais {len(lista) - 3}"

    guias_480 = df[df['Glosa'] == '480']['Guia'].unique().tolist()
    clausula_480 = ""
    if guias_480:
        sep_480 = "na" if len(guias_480) == 1 else "nas"
        clausula_480 = f"Houve glosa 480 por falta de documentação ou ausência de envio da guia {sep_480} {formatar_guias(guias_480)}"
        itens = [i for i in itens if i['glosa'] != '480']

    agrupamento_glosas = collections.defaultdict(lambda: collections.defaultdict(list))
    for item in itens:
        chave_glosa = (item['glosa'], item['desc'], item['justificativa'])
        agrupamento_glosas[chave_glosa][item['proc']].append(item['guia'])
        
    glosas_por_footprint = collections.defaultdict(list)
    for chave_glosa, proc_guias in agrupamento_glosas.items():
        footprint_items = []
        for p, gs in sorted(proc_guias.items()):
            footprint_items.append((p, tuple(sorted(list(set(gs))))))
        footprint = tuple(footprint_items)
        glosas_por_footprint[(footprint, chave_glosa[2])].append((chave_glosa[0], chave_glosa[1])) 

    fatoracao_global_guias = None
    if glosas_por_footprint: 
        guias_candidatas = set()
        possivel_fatorar = True
        
        for i, (footprint, justif) in enumerate(glosas_por_footprint.keys()):
            guias_deste_footprint = set()
            for proc, guias in footprint:
                guias_deste_footprint.update(guias)
                
            for proc, guias in footprint:
                if set(guias) != guias_deste_footprint:
                    possivel_fatorar = False
                    break
            
            if not possivel_fatorar: break
            
            if i == 0:
                guias_candidatas = guias_deste_footprint
            elif guias_deste_footprint != guias_candidatas:
                possivel_fatorar = False
                break
                
        if possivel_fatorar and guias_candidatas:
            fatoracao_global_guias = sorted(list(guias_candidatas))
            
    def formatar_procs(lista):
        if len(lista) == 1: return lista[0]
        if len(lista) == 2: return f"{lista[0]} e {lista[1]}"
        return f"{', '.join(lista[:-1])} e {lista[-1]}"

    clausulas = []
    
    for i, ((footprint, justificativa), lista_glosas) in enumerate(glosas_por_footprint.items()):
        textos_glosas = []
        for cod, desc in lista_glosas:
            textos_glosas.append(f"{desc} (glosa {cod})")
            
        if len(textos_glosas) == 1:
            texto_glosa = f"glosa por {textos_glosas[0]}"
        else:
            texto_glosa = f"glosas por {', '.join(textos_glosas[:-1])} e {textos_glosas[-1]}"
            
        procs_unicos = [p for p, gs in footprint]
        n_procs = len(procs_unicos)
        
        todas_guias = []
        for p, gs in footprint: todas_guias.extend(gs)
        guias_unicas_totais = sorted(list(set(todas_guias)))
        n_guias = len(guias_unicas_totais)
        
        if fatoracao_global_guias:
            prefixo_guia_local = ""
            sep_proc = "no procedimento " if n_procs == 1 else "nos procedimentos "
            frase_proc = f"{sep_proc}{formatar_procs(procs_unicos)}"
        else:
            todas_mesmas_guias = False
            if n_procs > 1:
                assinaturas_guias = set([tuple(gs) for p, gs in footprint])
                if len(assinaturas_guias) == 1:
                    todas_mesmas_guias = True
                    
            if n_procs == 1 or todas_mesmas_guias:
                # Guias são uniformes para esta cláusula (Casos A, B, D)
                sep_guia = "na" if n_guias == 1 else "nas"
                prefixo_guia_local = f"{sep_guia} {formatar_guias(guias_unicas_totais)}, "
                sep_proc = "no procedimento " if n_procs == 1 else "nos procedimentos "
                frase_proc = f"{sep_proc}{formatar_procs(procs_unicos)}"
            else:
                # Caso C: Guias mistas por procedimento
                prefixo_guia_local = ""
                partes_proc = []
                for proc, gs in footprint:
                    if not gs or gs[0] == "Desconhecida":
                        partes_proc.append(f"{proc}")
                    else:
                        g_text = formatar_guias(gs).replace("guias ", "").replace("guia ", "")
                        sep_g = "guia" if len(gs) == 1 else "guias"
                        partes_proc.append(f"{proc} ({sep_g} {g_text})")
                frase_proc = f"nos procedimentos {formatar_procs(partes_proc)}"
                
        abertura = ""
        if i == 0 and not fatoracao_global_guias and not clausula_480:
            abertura = "O prestador apresentou, " if prefixo_guia_local else "O prestador apresentou "
            
        frase = f"{abertura}{prefixo_guia_local}{texto_glosa} {frase_proc}".strip()
        
        if justificativa:
            frase += f", {justificativa}"
            
        clausulas.append(frase)
        
    texto_complementar = ""
    if fatoracao_global_guias:
        sep_global = "na" if len(fatoracao_global_guias) == 1 else "nas"
        abertura_global = f"O prestador apresentou, {sep_global} {formatar_guias(fatoracao_global_guias)}, "
        if len(clausulas) == 1:
            texto_complementar = abertura_global + clausulas[0] + "."
        elif len(clausulas) > 1:
            texto_complementar = abertura_global + "; ".join(clausulas[:-1]) + "; e " + clausulas[-1] + "."
    else:
        if len(clausulas) == 1:
            texto_complementar = clausulas[0] + "."
        elif len(clausulas) > 1:
            texto_complementar = "; ".join(clausulas[:-1]) + "; e " + clausulas[-1] + "."
            
    texto_final = ""
    if clausula_480:
        texto_final = clausula_480
        if texto_complementar:
            # Capitalizar a primeira letra do complemento para ficar gramaticalmente correto após o ponto
            texto_complementar = texto_complementar[0].upper() + texto_complementar[1:]
            texto_final += ". " + texto_complementar
    else:
        texto_final = texto_complementar
            
    if not texto_final:
        return prefixo + "Nenhuma glosa selecionada."
        
    return prefixo + texto_final

st.title("📄 Gerador Offline - Relatório 5302")
st.markdown("Faça o upload do PDF da operadora para iniciar a análise inteligente e extração de glosas. **Tudo ocorre na memória RAM.**")

pdf_file = st.file_uploader("Arraste o arquivo PDF ou CSV aqui", type=["pdf", "csv"])

if pdf_file is not None:
    if "dados_pdf" not in st.session_state or st.session_state.get("pdf_name") != pdf_file.name:
        with st.spinner("Analisando arquivo em memória..."):
            if pdf_file.name.lower().endswith(".csv"):
                glosas, meta = processar_csv(pdf_file)
            else:
                glosas, meta = processar_pdf(pdf_file)
            st.session_state["dados_pdf"] = glosas
            st.session_state["meta_pdf"] = meta
            st.session_state["pdf_name"] = pdf_file.name

    dados = st.session_state.get("dados_pdf", [])
    meta = st.session_state.get("meta_pdf", {"processo": "Desconhecido", "prestador": "Desconhecido", "producao": "Desconhecida"})
    
    if dados:
        st.success(f"Análise concluída! {len(dados)} glosas detectadas. Prestador: **{meta.get('prestador')}** | Processo: **{meta.get('processo')}** | Produção: **{meta.get('producao')}**")
        
        st.markdown("### 1. Auditoria e Justificativas")
        st.markdown("Marque **Incluir no Relatório** para as glosas que deseja exportar. As glosas automáticas (ex: glosa 12) já vêm desmarcadas por padrão.")
        
        df = pd.DataFrame(dados)
        
        col_config = {
            "Incluir no Relatório": st.column_config.CheckboxColumn("Incluir no Relatório", default=True),
            "Justificativa": st.column_config.TextColumn("Justificativa", required=False),
        }
        
        df_editado = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic",
            column_config=col_config
        )
        
        st.markdown("### 2. Motor de Texto Offline")
        col1, col2 = st.columns([1, 2])
        
        with col1:
            opcao_agrupamento = st.radio(
                "Nível de Detalhe:",
                ["Versão Resumida (Agrupada)", "Versão Completa (Detalhada)"],
                index=1
            )
            
            opcao_filtro = st.radio(
                "Filtro de Glosas:",
                ["Todas selecionadas na tabela", "Somente Glosas Críticas"]
            )
            
            opcao_prefixo = st.radio(
                "Cabeçalho do Relatório:",
                [
                    "Nenhum Cabeçalho",
                    "c/ Especialidades Críticas",
                    "s/ Especialidades Críticas (Apenas Imagens)"
                ]
            )
            
            btn_gerar = st.button("Gerar Texto", type="primary", use_container_width=True)
            
        with col2:
            if btn_gerar:
                st.session_state["mostrar_texto"] = True
                
            if st.session_state.get("mostrar_texto", False):
                # O tipo de geracao passado dita a regra interna
                tipo = "Versão Resumida" if "Resumida" in opcao_agrupamento else "Versão Completa"
                
                # Vamos injetar "Só Glosas Críticas" como flag temporaria na hora de chamar
                if "Somente" in opcao_filtro:
                    tipo = "Só Glosas Críticas"
                    
                df_final = df_editado[df_editado['Incluir no Relatório'] == True].copy()
                if "Somente" in opcao_filtro:
                    df_final = df_final[df_final['Tipo'] == 'Crítica']
                
                texto_gerado = gerar_texto(df_final, tipo)
                
                # Limpa prefixos caso a funcao os tenha gerado
                texto_gerado = texto_gerado.replace("PROCESSO ANALISADO POR AMOSTRAGEM DAS ESPECIALIDADES CRÍTICAS///\\n", "")
                texto_gerado = texto_gerado.replace("PROCESSO ANALISADO POR AMOSTRAGEM DAS ESPECIALIDADES CRÍTICAS///\n", "")
                texto_gerado = texto_gerado.replace("PROCESSO ANALISADO POR AMOSTRAGEM DAS ESPECIALIDADES CRÍTICAS/// ", "")
                
                texto_pronto = texto_gerado
                if "Nenhuma glosa" not in texto_gerado:
                    if "c/ Especialidades" in opcao_prefixo:
                        texto_pronto = "PROCESSO ANALISADO POR AMOSTRAGEM DAS ESPECIALIDADES CRÍTICAS/// " + texto_gerado
                    elif "s/ Especialidades" in opcao_prefixo:
                        texto_pronto = "PROCESSO SEM ESPECIALIDADES CRÍTICAS ANALISADO POR AMOSTRAGEM DO ENVIO DE IMAGENS/// " + texto_gerado
                    
                st.text_area("Texto Final (Pronto para copiar):", texto_pronto, height=180)
                
                # Cópia automática apenas quando o botão acabou de ser clicado
                if btn_gerar and "Nenhuma glosa" not in texto_gerado:
                    try:
                        import pyperclip
                        pyperclip.copy(texto_pronto)
                        st.toast("📋 Texto copiado automaticamente para a Área de Transferência!")
                    except Exception:
                        pass  # pyperclip não disponível no ambiente web (Streamlit Cloud)
                
                if "Nenhuma glosa" not in texto_gerado:
                    if st.button("💾 Salvar Análise no Supabase"):
                        with st.spinner("Salvando na nuvem..."):
                            try:
                                salvar_no_supabase(st.session_state.get("pdf_name", "Desconhecido"), texto_pronto, df_final, meta)
                                st.success("Análise salva com sucesso no banco de dados!")
                            except Exception as e:
                                st.error(f"Erro ao salvar no banco. A tabela 'analises_auditoria' foi criada no Supabase? Detalhe: {e}")
                
                st.markdown("### 💬 Textos Adicionais ao Prestador")
                if "Nenhuma glosa" not in texto_gerado:
                    glosas_presentes = set(df_final['Glosa'].unique())
                    from shared.database import DatabaseManager
                    if "db" not in st.session_state:
                        st.session_state.db = DatabaseManager()
                    
                    textos_db = st.session_state.db.carregar_textos_prestador()
                    
                    textos_sugeridos = []
                    
                    for txt in textos_db:
                        glosas_relacionadas = set([g.strip() for g in str(txt.get('glosas_relacionadas', '')).split(',') if g.strip()])
                        # Se houver intersecção entre as glosas presentes e as mapeadas no texto
                        if glosas_relacionadas & glosas_presentes:
                            # Adiciona um cabecalhozinho opcional ou so o texto
                            textos_sugeridos.append(txt.get('texto', '').strip())
                    
                    if textos_sugeridos:
                        texto_mixado = mixar_textos_inteligente(textos_sugeridos)
                        st.text_area("Mensagem Combinada (Copie e cole):", texto_mixado, height=150)
                    else:
                        st.info("Nenhum texto adicional mapeado para as glosas detectadas.")
            else:
                st.info("💡 Selecione os filtros ao lado e clique em Gerar Texto.")
            
    else:
        st.warning("Nenhuma glosa identificada neste documento com os padrões atuais.")

