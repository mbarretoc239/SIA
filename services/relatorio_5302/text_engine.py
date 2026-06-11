import re
import collections
from shared.database import DatabaseManager
import streamlit as st
import pandas as pd

@st.cache_data(ttl=600, show_spinner=False)
def carregar_regras_gramaticais_cache():
    try:
        from shared.database import DatabaseManager
        db = DatabaseManager()
        return db.carregar_dicionario_glosas()
    except Exception:
        return {}


def formatar_descricao_glosa_inteligente(desc, glosa):
    desc = desc.strip().lower()
    
    regras = carregar_regras_gramaticais_cache()

    if regras:
        # Ordena pelas regras mais específicas (mais longas) primeiro e para na
        # primeira que casar, evitando que uma regra genérica (ex: "rx evidencia")
        # seja reaplicada sobre o resultado de uma regra mais específica que já
        # contém o mesmo trecho (ex: "rx evidenciar"), gerando texto duplicado.
        for original, substituto in sorted(regras.items(), key=lambda kv: len(kv[0]), reverse=True):
            if original in desc:
                desc = desc.replace(original, substituto)
                break
    else:
        # Fallback de segurança caso a tabela ainda esteja vazia
        desc = desc.replace("rx evidencia", "o rx evidenciar")
        desc = desc.replace("radiografia evidencia", "a radiografia evidenciar")
        desc = desc.replace("imagem evidencia", "a imagem evidenciar")
        desc = desc.replace("documentação evidencia", "a documentação evidenciar")
        
        if desc.startswith("falta "):
            if not desc.startswith("falta de "):
                desc = desc.replace("falta ", "falta de ", 1)
                
        if desc.startswith("ausência ") and not desc.startswith("ausência de "):
            desc = desc.replace("ausência ", "ausência de ", 1)
        if desc.startswith("ausencia ") and not desc.startswith("ausencia de "):
            desc = desc.replace("ausencia ", "ausência de ", 1)
        
    conectivo = "por "
    if desc.startswith("o "):
        conectivo = "pelo "
        desc = desc[2:]
    elif desc.startswith("a "):
        conectivo = "pela "
        desc = desc[2:]
    elif desc.startswith("os "):
        conectivo = "pelos "
        desc = desc[3:]
    elif desc.startswith("as "):
        conectivo = "pelas "
        desc = desc[3:]
        
    return f"glosa {conectivo}{desc} (glosa {glosa})"


def formatar_conectivo_subglosa(t):
    if not t: return ""
    t_orig = t
    t = t.strip().lower()
    if t.endswith('.'): t = t[:-1]

    # Sub-glosas 32 e 33 da glosa 438: a operadora marca apenas com os
    # símbolos "@" e "*" no PDF, sem texto descritivo associado.
    if t == '@':
        return 'pois a imagem sugere ser advinda da internet'
    if t == '*':
        return 'pois a imagem sugere manipulação'

    regras = carregar_regras_gramaticais_cache()
    if regras:
        for original, substituto in sorted(regras.items(), key=lambda kv: len(kv[0]), reverse=True):
            # Regras que reescrevem "X evidencia" -> "X evidenciar" servem ao
            # conectivo "por/pelo X evidenciar Y" da descricao principal
            # (formatar_descricao_glosa_inteligente). Aplicadas aqui, na
            # descricao_sub_glosa, trocariam erroneamente o presente do
            # indicativo ("evidencia") pelo infinitivo ("evidenciar").
            if "evidenciar" in substituto:
                continue
            if original in t:
                t = t.replace(original, substituto)
                break
    else:
        # Fallback manual antigo
        t = t.replace('não enviada', 'não foi enviada').replace('não enviado', 'não foi enviado')
        t = t.replace('usuário em tratamento', 'usuário está em tratamento')
        t = t.replace('incluso no procedimento', 'está incluso no procedimento')
        t = t.replace('incompatível com', 'é incompatível com')
    
    if t in ['raio x final', 'raio x inicial', 'rx final', 'rx inicial']:
        return 'por falta do ' + t
    if t in ['imagem', 'fotografia', 'tomografia', 'documentação', 'documentaçã£o', 'radiografia', 'panorâmica', 'panormica', 'fotografia inicial', 'fotografia final']:
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


def gerar_texto(df_glosas, tipo_geracao, meta=None):
    df = df_glosas[df_glosas['Incluir no Relatório'] == True].copy()
    
    if tipo_geracao == "Só Glosas Críticas":
        df = df[df['Tipo'] == 'Crítica']
        
    if df.empty:
        return "Nenhuma glosa aplicável encontrada no documento para o filtro selecionado."
        
    prefixo = ""
    
    if tipo_geracao == "Versão Completa (Detalhada)":
        def formatar_guias_detalhada(lista):
            if not lista or lista[0] == "Desconhecida": return ""
            if len(lista) == 1: return f"guia {lista[0]}"
            if len(lista) == 2: return f"guias {lista[0]} e {lista[1]}"
            if len(lista) <= 6:
                return f"guias {', '.join(lista[:-1])} e {lista[-1]}"
            return f"guias {', '.join(lista[:6])} e mais {len(lista) - 6}"

        guias_480 = df[df['Glosa'] == '480']['Guia'].unique().tolist()
        clausula_480 = ""
        if guias_480:
            sep_480 = "na" if len(guias_480) == 1 else "nas"
            clausula_480 = f"Houve glosa 480 por falta de documentação ou ausência de envio da guia {sep_480} {formatar_guias_detalhada(guias_480)}"

        guias_raw = {}
        globais_dict = {}

        for _, row in df[df['Glosa'] != '480'].iterrows():
            justificativa = (str(row.get('Justificativa') or "")).strip()
            glosa = str(row['Glosa'])
            desc_oficial = str(row['Descrição Oficial'])
            cod_proc = str(row['Cód. Procedimento'])
            proc = str(row['Procedimento']).lower()
            guia = str(row['Guia'])
            tipo_glosa = str(row.get('Tipo', ''))

            texto_base = formatar_descricao_glosa_inteligente(desc_oficial, glosa)
            texto_glosa = texto_base
            if justificativa:
                texto_glosa += f", {justificativa}"

            if tipo_glosa == 'Automática':
                globais_dict.setdefault(texto_glosa, set()).add(guia)
            else:
                proc_key = f"{cod_proc} - {proc}" if cod_proc not in ("N/A", "") else ""
                guias_raw.setdefault(guia, {}).setdefault(proc_key, []).append({
                    "texto": texto_glosa, "base": texto_base, "justificativa": justificativa, "glosa": glosa
                })

        guias_dict = {}
        for guia, procs in guias_raw.items():
            guias_dict[guia] = {}
            for proc_key, glosas_list in procs.items():
                codigos = [g['glosa'] for g in glosas_list]

                # Regra Família de Glosas: Mesclar rx inicial (430) e rx final (420)
                if '420' in codigos and '430' in codigos:
                    glosas_list = [g for g in glosas_list if g['glosa'] not in ('420', '430')]
                    glosas_list.append({
                        "texto": "glosas por falta de rx inicial e final (glosas 430 e 420)",
                        "base": "glosas por falta de rx inicial e final (glosas 430 e 420)",
                        "justificativa": "",
                        "glosa": "430_420"
                    })

                for g in glosas_list:
                    t = g["texto"]
                    guias_dict[guia].setdefault(t, {"base": g["base"], "justificativa": g["justificativa"], "procs": []})
                    if proc_key and proc_key not in guias_dict[guia][t]["procs"]:
                        guias_dict[guia][t]["procs"].append(proc_key)

        clausulas = []
        for idx, (guia, glosas_d) in enumerate(guias_dict.items()):
            clausulas_glosas = []
            for texto_glosa, info in glosas_d.items():
                base = info["base"]
                justificativa_item = info["justificativa"]
                procs = info["procs"]

                if len(procs) == 0:
                    clausula = base
                    if justificativa_item:
                        clausula += f", {justificativa_item}"
                elif len(procs) == 1:
                    clausula = f"{base} no procedimento {procs[0]}"
                    if justificativa_item:
                        clausula += f", {justificativa_item}"
                else:
                    procs_str = ", ".join(procs[:-1]) + " e " + procs[-1]
                    clausula = f"{base} nos procedimentos {procs_str}"
                    if justificativa_item:
                        clausula += f", {justificativa_item}"

                clausulas_glosas.append(clausula)

            if len(clausulas_glosas) == 1:
                procs_str = clausulas_glosas[0]
            else:
                procs_str = ", ".join(clausulas_glosas[:-1]) + ", além de " + clausulas_glosas[-1]

            if idx == 0:
                clausulas.append(f"Foram identificadas glosas nas seguintes guias: na guia {guia}, {procs_str}")
            else:
                clausulas.append(f"na guia {guia}, {procs_str}")

        for texto_glosa, guias_set in globais_dict.items():
            guias_list = sorted(list(guias_set))
            n_guias = len(guias_list)

            if n_guias == 1:
                guias_formatado = f"guia {guias_list[0]}"
            elif n_guias == 2:
                guias_formatado = f"guias {guias_list[0]} e {guias_list[1]}"
            elif n_guias == 3:
                guias_formatado = f"guias {guias_list[0]}, {guias_list[1]} e {guias_list[2]}"
            else:
                guias_formatado = f"guias {guias_list[0]}, {guias_list[1]}, {guias_list[2]} e mais {n_guias - 3}"

            clausulas.append(f"{texto_glosa} em {n_guias} {'guia' if n_guias == 1 else 'guias'} ({guias_formatado})")

        texto_complementar = ""
        if len(clausulas) == 1:
            texto_complementar = clausulas[0] + "."
        elif len(clausulas) > 1:
            texto_complementar = "; ".join(clausulas[:-1]) + "; e " + clausulas[-1] + "."

        texto_final = ""
        if clausula_480:
            texto_final = clausula_480
            if texto_complementar:
                texto_complementar = texto_complementar[0].upper() + texto_complementar[1:]
                texto_final += ". " + texto_complementar
        else:
            texto_final = texto_complementar

        if not texto_final:
            return "Nenhuma glosa selecionada."

        resumo_financeiro = ""
        if meta and "valor_cobrado" in meta and meta["valor_cobrado"] > 0:
            cobrado = meta.get("valor_cobrado", 0)
            calculado = meta.get("valor_calculado", 0)
            glosa = meta.get("valor_glosa", 0)

            diferenca = cobrado - calculado
            glosa_real = diferenca if diferenca > 0 else glosa

            if glosa_real > 0:
                pct = (glosa_real / cobrado) * 100
                resumo_financeiro = f", totalizando um percentual de glosa de {pct:.1f}% do valor cobrado no processo"

        if texto_final.endswith('.'): texto_final = texto_final[:-1]
        return texto_final + resumo_financeiro + "."

    # --- NOVO MOTOR MISTO COM FATORAÇÃO DE GUIAS ---
    def categorizar_procedimento(cod, desc):
        desc_lower = str(desc).lower()
        cod_str = str(cod).strip()
        
        if 'exodontia' in desc_lower: return 'exodontia', 'exodontias'
        if 'radiografia panor' in desc_lower: return 'radiografia panorâmica', 'radiografias panorâmicas'
        if 'radiografia' in desc_lower or 'periapical' in desc_lower or 'bite-wing' in desc_lower or cod_str == '210': 
            return 'radiografia periapical', 'radiografias periapicais'
        if 'retratamento endod' in desc_lower or cod_str == '2040': 
            return 'retratamento endodôntico', 'retratamentos endodônticos'
        if 'tratamento endod' in desc_lower or cod_str.startswith('20'): 
            return 'tratamento endodôntico', 'tratamentos endodônticos'
        if 'restaura' in desc_lower or cod_str.startswith('40'): 
            return 'restauração', 'restaurações'
        if 'raspagem' in desc_lower or 'alisamento' in desc_lower or cod_str.startswith('80'): 
            return 'raspagem', 'raspagens'
        if 'coroa' in desc_lower: return 'coroa', 'coroas'
        if 'profilaxia' in desc_lower: return 'profilaxia', 'profilaxias'
        if 'fluor' in desc_lower or 'flúor' in desc_lower: return 'aplicação de flúor', 'aplicações de flúor'
        if 'selante' in desc_lower: return 'aplicação de selante', 'aplicações de selante'
        if 'clareamento' in desc_lower: return 'clareamento', 'clareamentos'
        if 'pino' in desc_lower or 'núcleo' in desc_lower or 'nucleo' in desc_lower: return 'pino/núcleo', 'pinos/núcleos'
        if 'protese' in desc_lower or 'prótese' in desc_lower: return 'prótese', 'próteses'
        
        return 'procedimento', 'procedimentos'

    temp_itens = collections.defaultdict(list)
    for _, row in df.iterrows():
        cod_proc = str(row['Cód. Procedimento'])
        proc = str(row['Procedimento']).lower()
        cat_singular, cat_plural = categorizar_procedimento(cod_proc, proc)
        
        temp_itens[(str(row['Guia']), cod_proc, cat_singular, cat_plural)].append({
            "glosa": str(row['Glosa']),
            "desc": str(row['Descrição Oficial']),
            "justificativa": (str(row.get('Justificativa') or "")).strip()
        })
        
    itens = []
    for (guia, cod_proc, cat_s, cat_p), lista_glosas in temp_itens.items():
        codigos = [g['glosa'] for g in lista_glosas]
        if '420' in codigos and '430' in codigos:
            lista_glosas = [g for g in lista_glosas if g['glosa'] not in ('420', '430')]
            lista_glosas.append({
                "glosa": "430_420",
                "desc": "falta de rx inicial e final",
                "justificativa": ""
            })
            
        for g in lista_glosas:
            texto_formatado = ""
            if g["glosa"] == "430_420":
                texto_formatado = "glosas 420 e 430"
            elif g["glosa"] != "480":
                texto_formatado = f"glosa {g['glosa']}"
                
            if texto_formatado:
                itens.append({
                    "glosa": g["glosa"],
                    "texto_formatado": texto_formatado,
                    "justificativa": g["justificativa"],
                    "cat": (cat_s, cat_p),
                    "guia": guia
                })

    def formatar_guias_resumo(lista):
        if not lista or lista[0] == "Desconhecida": return ""
        if len(lista) == 1: return f"guia {lista[0]}"
        if len(lista) == 2: return f"guias {lista[0]} e {lista[1]}"
        if len(lista) <= 6:
            return f"guias {', '.join(lista[:-1])} e {lista[-1]}"
        return f"guias {', '.join(lista[:6])} e mais {len(lista) - 6}"

    guias_480 = df[df['Glosa'] == '480']['Guia'].unique().tolist()
    clausula_480 = ""
    if guias_480:
        sep_480 = "na" if len(guias_480) == 1 else "nas"
        clausula_480 = f"Houve glosa 480 por falta de documentação ou ausência de envio da guia {sep_480} {formatar_guias_resumo(guias_480)}"
        itens = [i for i in itens if i['glosa'] != '480']

    # Agrupar por (texto_formatado, justificativa)
    agrupamento_glosas = collections.defaultdict(list)
    for item in itens:
        chave_glosa = (item['texto_formatado'], item['justificativa'])
        agrupamento_glosas[chave_glosa].append(item)

    clausulas = []
    
    for (texto_glosa, justificativa), lista_itens in agrupamento_glosas.items():
        # Agrupar por categoria dentro desta glosa
        cat_counts = collections.defaultdict(list)
        for item in lista_itens:
            cat_counts[item['cat']].append(item['guia'])
            
        partes_categoria = []
        for (cat_s, cat_p), guias_lista in cat_counts.items():
            n_itens = len(guias_lista)
            guias_unicas = sorted(list(set(guias_lista)))
            nome_cat = cat_s if n_itens == 1 else cat_p
            
            str_guias = formatar_guias_resumo(guias_unicas)
            
            if n_itens == 1:
                partes_categoria.append(f"{n_itens} {nome_cat} na {str_guias}")
            else:
                partes_categoria.append(f"{n_itens} {nome_cat} ({str_guias})")
                
        if len(partes_categoria) == 1:
            texto_categorias = partes_categoria[0]
        else:
            texto_categorias = ", ".join(partes_categoria[:-1]) + " e " + partes_categoria[-1]
            
        frase = f"{texto_glosa} em {texto_categorias}"
        if justificativa:
            frase += f", {justificativa}"
            
        clausulas.append(frase)
        
    texto_complementar = ""
    if len(clausulas) == 1:
        texto_complementar = "O prestador apresentou " + clausulas[0] + "."
    elif len(clausulas) > 1:
        texto_complementar = "O prestador apresentou " + "; ".join(clausulas[:-1]) + "; e " + clausulas[-1] + "."
        
    texto_final = ""
    if clausula_480:
        texto_final = clausula_480
        if texto_complementar:
            texto_complementar = texto_complementar[0].upper() + texto_complementar[1:]
            texto_final += ". " + texto_complementar
    else:
        texto_final = texto_complementar
    if not texto_final:
        return prefixo + "Nenhuma glosa selecionada."
        
    resumo_financeiro = ""
    if meta and "valor_cobrado" in meta and meta["valor_cobrado"] > 0:
        cobrado = meta.get("valor_cobrado", 0)
        calculado = meta.get("valor_calculado", 0)
        glosa = meta.get("valor_glosa", 0)
        
        diferenca = cobrado - calculado
        glosa_real = diferenca if diferenca > 0 else glosa
        
        if glosa_real > 0:
            pct = (glosa_real / cobrado) * 100
            resumo_financeiro = f", totalizando um percentual de glosa de {pct:.1f}% do valor cobrado no processo"
            
    # Garantir que terminamos com ponto final corretamente
    if texto_final.endswith('.'):
        texto_final = texto_final[:-1]
        
    return prefixo + texto_final + resumo_financeiro + "."

def mixar_textos_inteligente(textos):
    if not textos: return ""
    if len(textos) == 1: return textos[0]
    
    # Regex melhorado para capturar as diversas formas de despedida e saudações
    padrao_saudacao = re.compile(r"^(CARO PRESTADOR,|PREZADO\(A\) PRESTADOR\(A\),?|Prezado\(a\) Prestador\(a\),?)\s*", re.IGNORECASE)
    padrao_despedida = re.compile(r"(EM CASO[S]? DE DÚVIDA[S]?.*?(?:4002[\W_]*2722)\.?)", re.IGNORECASE | re.DOTALL)
    
    saudacao_final = "CARO PRESTADOR,\n"
    despedida_final = "\n\nEM CASO DE DÚVIDAS, ENTRE EM CONTATO COM A CAP, PELO TELEFONE 4002-2722."
    
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
            if paragrafo:
                primeira_palavra = paragrafo.split()[0]
                # Só reduzimos a primeira letra se:
                # 1. A primeira palavra não for totalmente maiúscula (ex: não reduzimos "RX", "PANORÂMICA")
                # 2. OU a primeira palavra for de uma única letra (ex: "A", "O")
                if not primeira_palavra.isupper() or len(primeira_palavra) == 1:
                    paragrafo = paragrafo[0].lower() + paragrafo[1:]
                
        # Junta em texto corrido (mantendo parágrafos simples, sem bullets)
        texto_combinado += "\n\n" + conectivo + paragrafo
            
    return saudacao_final + "\n" + texto_combinado + despedida_final


