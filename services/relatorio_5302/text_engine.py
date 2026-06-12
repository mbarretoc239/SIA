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
        def formatar_lista_guias(lista):
            if len(lista) == 1: return lista[0]
            if len(lista) == 2: return f"{lista[0]} e {lista[1]}"
            if len(lista) <= 6:
                return f"{', '.join(lista[:-1])} e {lista[-1]}"
            return f"{', '.join(lista[:6])} e mais {len(lista) - 6}"

        def formatar_guias_detalhada(lista):
            if not lista or lista[0] == "Desconhecida": return ""
            prefixo = "guia" if len(lista) == 1 else "guias"
            return f"{prefixo} {formatar_lista_guias(lista)}"

        guias_480 = df[df['Glosa'] == '480']['Guia'].unique().tolist()
        clausula_480 = ""
        if guias_480:
            sep_480 = "na" if len(guias_480) == 1 else "nas"
            clausula_480 = f"Houve glosa 480 por falta de documentação ou ausência de envio da guia {sep_480} {formatar_guias_detalhada(guias_480)}"

        guia_proc_glosas = {}
        globais_dict = {}
        ordem_guias = []

        for _, row in df[df['Glosa'] != '480'].iterrows():
            justificativa = (str(row.get('Justificativa') or "")).strip()
            glosa = str(row['Glosa'])
            desc_oficial = str(row['Descrição Oficial'])
            cod_proc = str(row['Cód. Procedimento'])
            proc = str(row['Procedimento']).lower()
            guia = str(row['Guia'])
            tipo_glosa = str(row.get('Tipo', ''))

            texto_base = formatar_descricao_glosa_inteligente(desc_oficial, glosa)

            if tipo_glosa == 'Automática':
                texto_glosa = texto_base
                if justificativa:
                    texto_glosa += f", {justificativa}"
                globais_dict.setdefault(texto_glosa, set()).add(guia)
                continue

            if guia not in ordem_guias:
                ordem_guias.append(guia)

            proc_key = f"{cod_proc} - {proc}" if cod_proc not in ("N/A", "") else ""
            guia_proc_glosas.setdefault(guia, {}).setdefault(proc_key, []).append({
                "base": texto_base, "justificativa": justificativa, "glosa": glosa
            })

        # Regra Família de Glosas: Mesclar rx inicial (430) e rx final (420)
        for guia, procs in guia_proc_glosas.items():
            for proc_key, lista in procs.items():
                codigos = [g['glosa'] for g in lista]
                if '420' in codigos and '430' in codigos:
                    nova_lista = [g for g in lista if g['glosa'] not in ('420', '430')]
                    nova_lista.append({
                        "base": "glosas por falta de rx inicial e final (glosas 430 e 420)",
                        "justificativa": "",
                        "glosa": "430_420"
                    })
                    procs[proc_key] = nova_lista

        # Agrupa por (descrição da glosa, justificativa) entre todas as guias, para
        # consolidar repetições da mesma glosa+motivo em guias diferentes.
        grupos_ordem = []
        grupos = {}
        for guia in ordem_guias:
            for proc_key, lista in guia_proc_glosas.get(guia, {}).items():
                for g in lista:
                    chave = (g["base"], g["justificativa"])
                    if chave not in grupos:
                        grupos[chave] = {}
                        grupos_ordem.append(chave)
                    guias_proc = grupos[chave].setdefault(proc_key, [])
                    if guia not in guias_proc:
                        guias_proc.append(guia)

        clausulas_por_guia = {}
        clausulas_globais = []

        for chave in grupos_ordem:
            base, justificativa = chave
            proc_map = grupos[chave]

            todas_guias = []
            for guias_lista in proc_map.values():
                for g in guias_lista:
                    if g not in todas_guias:
                        todas_guias.append(g)

            if len(todas_guias) == 1:
                guia = todas_guias[0]
                procs = [pk for pk in proc_map.keys() if pk]

                if len(procs) == 0:
                    clausula = base
                elif len(procs) == 1:
                    clausula = f"{base} no procedimento {procs[0]}"
                else:
                    procs_str = ", ".join(procs[:-1]) + " e " + procs[-1]
                    clausula = f"{base} nos procedimentos {procs_str}"

                if justificativa:
                    clausula += f", {justificativa}"

                clausulas_por_guia.setdefault(guia, []).append(clausula)
            elif len(proc_map) > 3:
                # Glosa+justificativa repetida em muitos procedimentos diferentes:
                # detalhar por procedimento deixaria a frase enorme, então resume
                # apenas pela quantidade e lista de guias (igual às glosas automáticas).
                guias_ordenadas = sorted(todas_guias)
                n_guias = len(guias_ordenadas)

                clausula = base
                if justificativa:
                    clausula += f", {justificativa}"
                clausula += f" em {n_guias} {'guia' if n_guias == 1 else 'guias'} ({formatar_lista_guias(guias_ordenadas)})"

                ordering_key = min(ordem_guias.index(g) for g in todas_guias)
                clausulas_globais.append((ordering_key, len(clausulas_globais), clausula))
            else:
                # Glosa+justificativa idêntica em mais de uma guia: consolida em
                # uma única cláusula, listando as guias por procedimento.
                partes = []
                for proc_key, guias_lista in proc_map.items():
                    guias_fmt = formatar_guias_detalhada(guias_lista)
                    prep = "na" if len(guias_lista) == 1 else "nas"
                    if proc_key:
                        partes.append(f"no procedimento {proc_key} {prep} {guias_fmt}")
                    else:
                        partes.append(f"{prep} {guias_fmt}")

                if len(partes) == 1:
                    partes_str = partes[0]
                else:
                    partes_str = ", ".join(partes[:-1]) + ", e " + partes[-1]

                clausula = base
                if justificativa:
                    clausula += f", {justificativa}"
                clausula += f", {partes_str}"

                ordering_key = min(ordem_guias.index(g) for g in todas_guias)
                clausulas_globais.append((ordering_key, len(clausulas_globais), clausula))

        itens_ordenados = []
        for guia in ordem_guias:
            if guia in clausulas_por_guia:
                lista_glosas = clausulas_por_guia[guia]
                if len(lista_glosas) == 1:
                    texto_guia = lista_glosas[0]
                else:
                    texto_guia = ", ".join(lista_glosas[:-1]) + ", além de " + lista_glosas[-1]
                itens_ordenados.append((ordem_guias.index(guia), 1, f"na guia {guia}, {texto_guia}"))

        for ordering_key, seq, clausula in clausulas_globais:
            itens_ordenados.append((ordering_key, 0, clausula))

        itens_ordenados.sort(key=lambda x: (x[0], x[1]))

        clausulas = []
        for idx, (_, _, texto) in enumerate(itens_ordenados):
            if idx == 0:
                clausulas.append(f"Foram identificadas glosas nas seguintes guias: {texto}")
            else:
                clausulas.append(texto)

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
        
        if 'semi-inclus' in desc_lower or 'semi inclus' in desc_lower:
            return 'exodontia de semi-incluso/impactado', 'exodontias de semi-incluso/impactado'
        if 'incluso' in desc_lower or 'inclusos' in desc_lower or 'impactad' in desc_lower:
            return 'exodontia de incluso/impactado', 'exodontias de incluso/impactado'
        if 'exodontia' in desc_lower: return 'exodontia', 'exodontias'
        if 'protese' in desc_lower or 'prótese' in desc_lower or 'protétic' in desc_lower or 'protetic' in desc_lower:
            if 'recimenta' in desc_lower:
                return 'recimentação de prótese', 'recimentações de prótese'
            if 'remoção' in desc_lower or 'remocao' in desc_lower:
                return 'remoção de prótese', 'remoções de prótese'
            if 'reembasamento' in desc_lower:
                return 'reembasamento de prótese', 'reembasamentos de prótese'
            if 'conserto' in desc_lower:
                return 'conserto de prótese', 'consertos de prótese'
            if 'planejamento' in desc_lower:
                return 'planejamento em prótese', 'planejamentos em prótese'
            if 'implant' in desc_lower:
                return 'prótese sobre implante', 'próteses sobre implante'
            if 'fixa adesiva' in desc_lower:
                return 'prótese fixa adesiva', 'próteses fixas adesivas'
            if 'parcial remov' in desc_lower:
                return 'prótese parcial removível', 'próteses parciais removíveis'
            if 'parcial fixa' in desc_lower:
                return 'prótese parcial fixa', 'próteses parciais fixas'
            if 'total' in desc_lower:
                return 'prótese total', 'próteses totais'
            return 'prótese', 'próteses'
        if 'radiografia panor' in desc_lower: return 'radiografia panorâmica', 'radiografias panorâmicas'
        if 'radiografia' in desc_lower or 'periapical' in desc_lower or 'bite-wing' in desc_lower or cod_str == '210':
            return 'radiografia periapical', 'radiografias periapicais'
        if 'retratamento endod' in desc_lower or cod_str == '2040':
            return 'retratamento endodôntico', 'retratamentos endodônticos'
        if 'tratamento endod' in desc_lower or cod_str.startswith('20'):
            return 'tratamento endodôntico', 'tratamentos endodônticos'
        if 'aumento de coroa' in desc_lower:
            return 'aumento de coroa clínica', 'aumentos de coroa clínica'
        if 'gengivectomia' in desc_lower: return 'gengivectomia', 'gengivectomias'
        if 'gengivoplastia' in desc_lower: return 'gengivoplastia', 'gengivoplastias'
        if 'pino pré' in desc_lower or 'pino pre' in desc_lower:
            return 'pino pré-fabricado', 'pinos pré-fabricados'
        if 'núcleo' in desc_lower or 'nucleo' in desc_lower:
            if 'metálic' in desc_lower or 'metalic' in desc_lower:
                return 'núcleo metálico fundido', 'núcleos metálicos fundidos'
            return 'núcleo de preenchimento', 'núcleos de preenchimento'
        if 'coroa' in desc_lower:
            if 'provis' in desc_lower:
                return 'coroa provisória', 'coroas provisórias'
            if 'metálica' in desc_lower or 'metalica' in desc_lower:
                return 'coroa total metálica', 'coroas totais metálicas'
            if 'cerômero' in desc_lower or 'ceromero' in desc_lower:
                return 'coroa em cerômero', 'coroas em cerômero'
            return 'coroa', 'coroas'
        if 'metálica fundida' in desc_lower or 'metalica fundida' in desc_lower:
            return 'restauração metálica fundida', 'restaurações metálicas fundidas'
        if 'atraumática' in desc_lower or 'atraumatica' in desc_lower:
            return 'restauração atraumática', 'restaurações atraumáticas'
        if 'amálgama' in desc_lower or 'amalgama' in desc_lower:
            return 'restauração em amálgama', 'restaurações em amálgama'
        if 'ionômero' in desc_lower or 'ionomero' in desc_lower:
            return 'restauração em ionômero de vidro', 'restaurações em ionômero de vidro'
        if 'resina' in desc_lower:
            return 'restauração em resina', 'restaurações em resina'
        if 'cerômero' in desc_lower or 'ceromero' in desc_lower:
            if 'onlay' in desc_lower:
                return 'restauração em cerômero (onlay)', 'restaurações em cerômero (onlay)'
            if 'inlay' in desc_lower:
                return 'restauração em cerômero (inlay)', 'restaurações em cerômero (inlay)'
            return 'restauração em cerômero', 'restaurações em cerômero'
        if 'restaura' in desc_lower or cod_str.startswith('40'):
            return 'restauração', 'restaurações'
        if 'raspagem' in desc_lower or 'alisamento' in desc_lower or cod_str.startswith('80'):
            return 'raspagem', 'raspagens'
        if 'profilaxia' in desc_lower: return 'profilaxia', 'profilaxias'
        if 'fluor' in desc_lower or 'flúor' in desc_lower: return 'aplicação de flúor', 'aplicações de flúor'
        if 'selante' in desc_lower: return 'aplicação de selante', 'aplicações de selante'
        if 'clareamento' in desc_lower: return 'clareamento', 'clareamentos'
        if 'consulta' in desc_lower:
            if 'urg' in desc_lower:
                return 'consulta de urgência', 'consultas de urgência'
            return 'consulta', 'consultas'

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


