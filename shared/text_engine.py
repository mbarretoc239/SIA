class TextEngine:
    def __init__(self, mapa_glosas):
        self.mapa_glosas = mapa_glosas

    def _gerar_texto_resumido_offline_dados(self):
        dados = list(getattr(self, 'dados_extraidos_offline', []) or [])
        if not dados:
            return ''
        dados_sem_480 = [g for g in dados if str(g.get('cod', '')).strip() != '480']
        if not dados_sem_480:
            return ''
        achados_estruturados = [self._estruturar_achado(g) for g in dados_sem_480]
        itens = self._consolidar_por_item(achados_estruturados)
        if not itens:
            return ''
        grupos_base = self._agrupar_por_assinatura(itens)
        ordem_base_por_item = {}
        for ordem_grupo, grupo in enumerate(grupos_base):
            for item in grupo.get('itens', []):
                ordem_base_por_item[id(item)] = ordem_grupo
        entradas_resumo = []
        consumidos = set()
        familias_por_guia = {}
        for idx, item in enumerate(itens):
            agrupamento = self._obter_agrupamento_procedimento_resumo(item.get('proc_cod'))
            if not agrupamento:
                continue
            chave = (item.get('guia', ''), agrupamento['chave'], item.get('justificativa', ''))
            familias_por_guia.setdefault(chave, []).append((idx, item))
        for chave, pares in sorted(familias_por_guia.items(), key=lambda kv: min((idx for idx, _ in kv[1]))):
            if len(pares) <= 1:
                continue
            itens_mesma_guia = [item for _, item in pares]
            consumidos.update((idx for idx, _ in pares))
            entradas_resumo.append({'ordem': min((ordem_base_por_item.get(id(item), idx) for idx, item in pares)), 'itens': itens_mesma_guia, 'justificativa': chave[2]})
        itens_restantes = [item for idx, item in enumerate(itens) if idx not in consumidos]
        grupos_restantes = self._agrupar_por_assinatura(itens_restantes) if itens_restantes else []
        for ordem_grupo, grupo in enumerate(grupos_restantes, start=len(entradas_resumo)):
            ordem = min((ordem_base_por_item.get(id(item), ordem_grupo) for item in grupo.get('itens', [])), default=ordem_grupo)
            entradas_resumo.append({'ordem': ordem, 'itens': list(grupo.get('itens', [])), 'justificativa': grupo.get('justificativa', '')})
        entradas_resumo.sort(key=lambda entrada: entrada['ordem'])
        clausulas = []
        for idx, entrada in enumerate(entradas_resumo):
            itens_entrada = entrada.get('itens', [])
            if not itens_entrada:
                continue
            codigos = []
            for item in itens_entrada:
                for achado in item.get('achados', []):
                    codigos.append(achado.get('cod'))
            prefixo = self._formatar_prefixo_glosas_resumo(codigos)
            alvo = self._renderizar_alvo_resumo_itens(itens_entrada)
            abertura = 'O prestador apresentou ' if idx == 0 else ''
            frase = f'{abertura}{prefixo} {alvo}'
            justificativa = entrada.get('justificativa', '')
            if justificativa:
                frase += f', {justificativa}'
            clausulas.append(frase)
        texto = self._juntar_clausulas_paragrafo(clausulas).strip()
        return self._processar_texto_resumido(texto) if texto else ''

    def _estruturar_achado(self, g):
        """Camada 1 — transforma um registro bruto em estrutura intermediária
            com campos normalizados prontos para consolidação e agrupamento."""
        cod_glosa = str(g.get('cod', '')).strip()
        guia = str(g.get('guia', '')).strip()
        proc_cod = str(g.get('proc_cod', '')).strip()
        proc_desc = str(g.get('proc_desc', '')).strip()
        motivo_raw = str(g.get('motivo_limpo', '')).strip()
        justificativa = self._normalizar_justificativa_redacao(g.get('justificativa', ''))
        if proc_cod and proc_cod not in ('SEM_PROC', 'N/A') and proc_desc:
            proc_label = f'{proc_cod} - {proc_desc}'
        elif proc_cod and proc_cod not in ('SEM_PROC', 'N/A'):
            proc_label = proc_cod
        else:
            proc_label = 'procedimento não identificado'
        return {'guia': guia, 'proc_cod': proc_cod, 'proc_label': proc_label, 'cod_glosa': cod_glosa, 'motivo_raw': motivo_raw, 'motivo_norm': self._normalizar_motivo(motivo_raw), 'justificativa': justificativa}

    def _consolidar_por_item(self, achados_estruturados):
        """Camada 2 — consolida achados pelo item lógico (guia + proc_cod).
            Cada item resultante representa um procedimento em uma guia, com a
            lista completa de achados (glosas) que incidem sobre ele.
            A assinatura é frozenset de (motivo_norm, cod_glosa): chave de agrupamento.
            """
        por_item = {}
        for a in achados_estruturados:
            chave_item = (a['guia'], a['proc_cod'])
            if chave_item not in por_item:
                por_item[chave_item] = {'guia': a['guia'], 'proc_cod': a['proc_cod'], 'proc_label': a['proc_label'], 'achados_vistos': set(), 'achados': [], 'justificativas': []}
            item = por_item[chave_item]
            chave_achado = (a['motivo_norm'], a['cod_glosa'], a['justificativa'])
            if chave_achado not in item['achados_vistos']:
                item['achados_vistos'].add(chave_achado)
                item['achados'].append({'cod': a['cod_glosa'], 'motivo_norm': a['motivo_norm'], 'motivo_raw': a['motivo_raw'], 'justificativa': a['justificativa']})
                item['justificativas'].append(a['justificativa'])
        itens = []
        for item in por_item.values():
            achados = item['achados']
            assinatura = frozenset(((a['motivo_norm'], a['cod']) for a in achados))
            justs_nao_vazias = list(dict.fromkeys((j for j in item['justificativas'] if j)))
            justificativa_dominante = justs_nao_vazias[0] if len(justs_nao_vazias) == 1 else ''
            itens.append({'guia': item['guia'], 'proc_cod': item['proc_cod'], 'proc_label': item['proc_label'], 'assinatura': assinatura, 'achados': achados, 'justificativa': justificativa_dominante})
        return itens

    def _agrupar_por_assinatura(self, itens):
        """Camada 3 â€” agrupa itens consolidados por assinatura semântica."""
        por_assinatura = {}
        for item in itens:
            chave = (item['assinatura'], item['justificativa'])
            if chave not in por_assinatura:
                por_assinatura[chave] = {'assinatura': item['assinatura'], 'achados': item['achados'], 'itens': [], 'guias': [], 'procs_unicos': [], 'justificativa': item['justificativa']}
            grupo = por_assinatura[chave]
            grupo['itens'].append(item)
            grupo['guias'].append(item['guia'])
            if item['proc_label'] not in grupo['procs_unicos']:
                grupo['procs_unicos'].append(item['proc_label'])
        grupos = list(por_assinatura.values())
        grupos.sort(key=lambda g: (0 if self._grupo_tem_glosa_critica(g) else 1, -len(set(g['guias'])), -len(g['itens']), g['procs_unicos'][0] if g['procs_unicos'] else ''))
        return grupos

    def _obter_agrupamento_procedimento_resumo(self, proc_cod):
        codigo = str(proc_cod or '').strip()
        if not codigo:
            return None
        for agrupamento in AGRUPAMENTOS_PROCEDIMENTOS_RESUMO:
            if codigo in agrupamento.get('codigos', set()):
                return agrupamento
        return None

    def _formatar_prefixo_glosas_resumo(self, codigos):
        codigos_unicos = list(dict.fromkeys((str(c or '').strip() for c in codigos if str(c or '').strip())))
        if not codigos_unicos:
            return 'glosa nao identificada'
        codigos_ordenados = sorted(codigos_unicos, key=lambda x: (0 if self._eh_glosa_critica(x) else 1, self._ordenar_codigo_glosa(x)))
        if len(codigos_ordenados) == 1:
            return f'glosa {codigos_ordenados[0]}'
        return f'glosas {self._juntar_lista_natural(codigos_ordenados)}'

    def _renderizar_alvo_resumo_itens(self, itens):
        blocos = self._montar_blocos_procedimento_resumo(itens)
        grupos = []
        especificos = []
        for bloco in blocos:
            texto_bloco = self._renderizar_bloco_procedimento_resumo(bloco)
            if not texto_bloco:
                continue
            if bloco.get('tipo') == 'grupo':
                grupos.append(texto_bloco)
            else:
                especificos.append(texto_bloco)
        partes = []
        if grupos:
            partes.append(f'em {self._juntar_lista_natural(grupos)}')
        if especificos:
            prefixo = 'no procedimento de' if len(especificos) == 1 else 'nos procedimentos de'
            partes.append(f'{prefixo} {self._juntar_lista_natural(especificos)}')
        return self._juntar_lista_natural(partes)

    def _juntar_clausulas_paragrafo(self, clausulas):
        clausulas_limpas = []
        for clausula in clausulas:
            texto = re.sub('[.;:\\s]+$', '', (clausula or '').strip())
            if texto:
                clausulas_limpas.append(texto)
        if not clausulas_limpas:
            return ''
        if len(clausulas_limpas) == 1:
            return clausulas_limpas[0] + '.'
        if len(clausulas_limpas) == 2:
            segunda = self._suavizar_inicio_continuacao(clausulas_limpas[1])
            return f'{clausulas_limpas[0]}; {segunda}.'
        meio = [self._suavizar_inicio_continuacao(c) for c in clausulas_limpas[1:-1]]
        ultima = self._suavizar_inicio_continuacao(clausulas_limpas[-1])
        prefixo = [clausulas_limpas[0]] + meio
        return f"{'; '.join(prefixo)}; e {ultima}."

    def _processar_texto_resumido(self, texto):
        import re
        texto = ' '.join((texto or '').strip().split())
        if not texto:
            return ''
        texto = re.sub('(?i)\\bglosas?\\s+por\\s+[^;,.()]*?\\((glosas?\\s+[0-9,\\se]+)\\)', lambda m: m.group(1).lower(), texto)
        texto = re.sub('(?i)(?<=;\\s)[^;,.()]*?\\((glosas?\\s+[0-9,\\se]+)\\)', lambda m: m.group(1).lower(), texto)
        texto = re.sub('(?i)\\b\\d{3,4}\\s*-\\s*(?=[A-Za-zÀ-ÿ])', '', texto)
        texto = re.sub('(?i)verificad[oa]s?\\s+em\\s+\\d+\\s+guias\\s*\\(([^)]+)\\)', 'verificada nas guias \\1', texto)
        texto = re.sub('(?i)guias\\s*\\(([^)]+)\\)', 'guias \\1', texto)
        texto = re.sub('(?i)\\(guia\\s+(\\d+)\\)', 'na guia \\1', texto)
        texto = re.sub('(?i)(?<!na )guia\\s+(\\d+)', 'na guia \\1', texto)
        texto = re.sub('(?i)\\bglosas?\\s+glosas?\\b', 'glosas', texto)
        texto = re.sub('(?i)\\bglosa\\s+glosa\\b', 'glosa', texto)
        texto = re.sub('\\s+', ' ', texto)
        texto = texto.replace(' ,', ',').replace(' ;', ';').replace(' .', '.')
        texto = texto.replace('na guia na guia', 'na guia').replace('nas guias nas guias', 'nas guias')
        return texto.strip(' ;')
        texto = re.sub('guias\\s+\\(([\\d,\\se]+)\\)', 'nas guias \\1', texto)
        texto = re.sub('\\(guia\\s+(\\d+)\\)', 'na guia \\1', texto)
        texto = re.sub('\\d{3,4}\\s*(?:-|\\s)\\s*[A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç0-9\\s\\-/]+(?= na? guias?|;|\\.)', '', texto)
        texto = re.sub('\\bverificado em \\d+ guias\\b', 'nas guias', texto)
        texto = re.sub('\\bem\\s+(?=nas? guias?)', '', texto)
        texto = re.sub('\\s+', ' ', texto)
        texto = texto.replace(' ,', ',').replace(' ;', ';').replace(' .', '.')
        texto = texto.replace('nas guias nas guias', 'nas guias').replace('na guia na guia', 'na guia')
        return texto.strip()

