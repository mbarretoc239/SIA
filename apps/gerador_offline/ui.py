import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import time
import os
import io
import re
import csv
import unicodedata


from core.database import conectar_sqlite
from core.settings import TEMA, CLASSIFICACAO_GLOSAS_PADRAO
from shared.utils import corrigir_mojibake, widget_existe, copiar_texto_clipboard, registrar_erro

GLOSAS_IGNORAR = ['71', '72']

PROMPT_BASE = """Base text for Copilot..."""


class FrameGeradorOffline(ctk.CTkFrame):
    def __init__(self, master, app_master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app_master = app_master
        
        # Inicializa variáveis necessárias
        self.resumo_ativo_offline = False
        self.dados_extraidos_offline = []
        self.glosas_auto_offline = {}
        self.itens_risco_offline = []
        self.itens_tecnicos_offline = []
        self.metadata_pdf_offline = {}
        self.mapa_procedimentos = {}
        
        self.setup_tela_5302_offline()

    def __getattr__(self, name):
        if hasattr(self.app_master, name):
            return getattr(self.app_master, name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def _tratar_erro_5302(self, erro):
        self.lbl_status_5302.configure(text=f"Erro ao processar PDF: {erro}", text_color=TEMA["erro"])
        self.btn_selecionar_5302.configure(state="normal")
        self.btn_cancelar_5302.pack_forget()

    def _tratar_erro_offline(self, erro):
        self._mostrar_progresso_offline(False)
        self.lbl_status_offline.configure(text=f"Erro ao processar arquivo: {erro}", text_color=TEMA["erro"])
        self.btn_selecionar_offline.configure(state="normal")

    def _arquivo_offline_e_csv(self, caminho):
        return str(caminho or "").strip().lower().endswith(".csv")

    def _obter_fonte_offline_label(self, caminho):
        return "CSV" if self._arquivo_offline_e_csv(caminho) else "PDF"

    def _normalizar_chave_csv_offline(self, texto):
        texto = corrigir_mojibake(str(texto or "").strip())
        texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()
        return re.sub(r"[^a-z0-9]+", "", texto)

    def _ler_linhas_relatorio_csv_offline(self, caminho_csv):
        ultimo_erro = None
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                with open(caminho_csv, mode="r", encoding=encoding, newline="") as f:
                    leitor = csv.reader(f, delimiter=";")
                    linhas = []
                    for row in leitor:
                        linhas.append([corrigir_mojibake(col).strip() for col in row])
                return linhas
            except UnicodeDecodeError as erro:
                ultimo_erro = erro
                continue
        if ultimo_erro:
            raise ultimo_erro
        return []

    def _extrair_metadados_csv_offline(self, linhas_csv):
        meta = {"processo": "N/A", "mes": "N/A", "prestador": "N/A"}
    
        for idx, row in enumerate(linhas_csv):
            campos = [str(col or "").strip() for col in row]
            if not any(campos):
                continue
    
            linha_unida = " ".join(campos)
            match_processo = re.search(r"PROCESSO:\s*(\d+)", linha_unida, flags=re.IGNORECASE)
            if match_processo and meta["processo"] == "N/A":
                meta["processo"] = match_processo.group(1)
    
            chaves = [self._normalizar_chave_csv_offline(col) for col in campos]
            if chaves[:4] == ["processo", "mesproducao", "cgccpf", "credenciado"]:
                prox = idx + 1
                while prox < len(linhas_csv) and not any(str(col or "").strip() for col in linhas_csv[prox]):
                    prox += 1
                if prox < len(linhas_csv):
                    valores = [corrigir_mojibake(str(col or "").strip()) for col in linhas_csv[prox]]
                    if len(valores) > 0 and valores[0]:
                        meta["processo"] = valores[0]
                    if len(valores) > 1 and valores[1]:
                        meta["mes"] = valores[1]
                    if len(valores) > 3 and valores[3]:
                        meta["prestador"] = valores[3]
                break
    
        return meta

    def _registrar_glosa_csv_offline(self, dados, glosas_auto, indice_detalhes, vistos_auto, guia, item, proc_cod, proc_desc, cod_glosa, desc_glosa="", detalhe=""):
        guia = str(guia or "").strip()
        item = str(item or "").strip()
        proc_cod = str(proc_cod or "").strip() or "N/A"
        proc_desc = str(proc_desc or "").strip().lower() or "procedimento não identificado"
        codigo = self._normalizar_codigo_glosa(cod_glosa)
        descricao = corrigir_mojibake(str(desc_glosa or "").strip())
        detalhe = corrigir_mojibake(str(detalhe or "").strip())
    
        if not guia or not codigo or codigo in GLOSAS_IGNORAR:
            return None
    
        codigo, motivo_limpo = self._resolver_glosa(codigo, descricao, detalhe)
    
        if len(codigo) <= 2 or codigo.startswith("0"):
            chave_auto = (guia, codigo)
            if chave_auto not in vistos_auto:
                glosas_auto.append({"cod": codigo, "guia": guia, "motivo": motivo_limpo})
                vistos_auto.add(chave_auto)
            return None
    
        chave = (guia, codigo, proc_cod, item)
        entry = indice_detalhes.get(chave)
        if entry is None:
            entry = {
                "cod": codigo,
                "motivo_limpo": motivo_limpo,
                "proc_cod": proc_cod,
                "proc_desc": proc_desc,
                "guia": guia,
                "item": item,
                "justificativa": "",
                "detalhe_pdf": detalhe,
            }
            dados.append(entry)
            indice_detalhes[chave] = entry
        elif detalhe:
            self._anexar_detalhe_glosa_csv_offline(entry, detalhe)
        return entry

    def _anexar_detalhe_glosa_csv_offline(self, entry, detalhe):
        if not entry:
            return
        detalhe = corrigir_mojibake(str(detalhe or "").strip())
        if not detalhe:
            return
    
        detalhe_atual = str(entry.get("detalhe_pdf") or "").strip()
        if detalhe_atual:
            if detalhe.upper() in detalhe_atual.upper():
                return
            detalhe_final = f"{detalhe_atual} {detalhe}".strip()
        else:
            detalhe_final = detalhe
    
        entry["detalhe_pdf"] = detalhe_final
        codigo, motivo_limpo = self._resolver_glosa(entry.get("cod"), entry.get("motivo_limpo", ""), detalhe_final)
        entry["cod"] = codigo
        entry["motivo_limpo"] = motivo_limpo

    def processar_csv_thread_offline(self, caminho_csv):
        try:
            self.after(0, lambda: self.lbl_status_offline.configure(text="Lendo CSV... (Aguarde)"))
            linhas_csv = self._ler_linhas_relatorio_csv_offline(caminho_csv)
            self.metadata_pdf_offline = self._extrair_metadados_csv_offline(linhas_csv)
    
            dados = []
            glosas_auto = []
            indice_detalhes = {}
            vistos_auto = set()
    
            guia_atual = ""
            item_atual = ""
            proc_cod_atual = "N/A"
            proc_desc_atual = "N/A"
            glosa_atual = None
    
            total_linhas = len(linhas_csv)
            for idx, row in enumerate(linhas_csv):
                if idx % 200 == 0:
                    self.after(0, lambda p=idx + 1, t=total_linhas: self.lbl_status_offline.configure(
                        text=f"Processando CSV: linha {p} de {t}... (Aguarde)"
                    ))
    
                campos = [corrigir_mojibake(str(col or "").strip()) for col in row]
                preenchidos = [(col_idx, valor) for col_idx, valor in enumerate(campos) if valor]
                if not preenchidos:
                    continue
    
                chaves = [self._normalizar_chave_csv_offline(col) for col in campos]
                if chaves[:8] == ["guia", "senha", "codigo", "usuario", "dtsolicitacao", "vlguia", "seq", "situacao"]:
                    glosa_atual = None
                    continue
                if chaves[:11] == ["item", "procedimento", "dini", "dfim", "qt", "vlinf", "qtp", "vlpagto", "e", "liberacao", "glosa"]:
                    glosa_atual = None
                    continue
    
                if re.fullmatch(r"\d{7,9}", campos[0]):
                    guia_atual = campos[0]
                    item_atual = ""
                    proc_cod_atual = "N/A"
                    proc_desc_atual = "N/A"
                    glosa_atual = None
                    continue
    
                if re.fullmatch(r"\d{1,3}", campos[0]) and len(campos) > 1:
                    match_proc = re.match(r"^(\d{3,4})\s*-\s*(.+)$", campos[1])
                    if match_proc:
                        item_atual = campos[0]
                        proc_cod_atual = str(int(match_proc.group(1)))
                        proc_desc_atual = self.mapa_procedimentos.get(proc_cod_atual) or self._normalizar_descricao_procedimento(match_proc.group(2))
                        glosa_atual = None
                        continue
    
                if guia_atual and item_atual and len(preenchidos) == 1:
                    col_idx, valor = preenchidos[0]
                    match_glosa = re.match(r"^(\d{1,3})\s*-\s*(.+)$", valor)
                    if match_glosa and col_idx >= 10:
                        codigo = match_glosa.group(1)
                        descricao = match_glosa.group(2).strip()
                        if col_idx == 10:
                            glosa_atual = self._registrar_glosa_csv_offline(
                                dados,
                                glosas_auto,
                                indice_detalhes,
                                vistos_auto,
                                guia_atual,
                                item_atual,
                                proc_cod_atual,
                                proc_desc_atual,
                                codigo,
                                descricao,
                                "",
                            )
                        else:
                            self._anexar_detalhe_glosa_csv_offline(glosa_atual, descricao)
                        continue
    
            self.dados_extraidos_offline = dados
            self.glosas_auto_offline = glosas_auto
            self.after(0, self._concluir_processamento_offline)
    
        except Exception as erro:
            import traceback
            traceback.print_exc()
            self.after(0, lambda: self._mostrar_progresso_offline(False))
            self.after(0, lambda: self.lbl_status_offline.configure(
                text="Erro na leitura do CSV.",
                text_color="#E74C3C"
            ))
            self.after(0, lambda: self.btn_selecionar_offline.configure(state="normal"))

    def setup_tela_5302(self):
        wrapper = ctk.CTkFrame(self, fg_color="transparent")
        wrapper.pack(expand=True)
        ctk.CTkLabel(wrapper, text="Gerador 5302 (Copilot/IA)", font=("Segoe UI", 28, "bold"), text_color=TEMA["texto_claro"]).pack(pady=(10, 5))
        ctk.CTkLabel(wrapper, text="Extracao e fatiamento para leitura no Copilot", text_color="#D6E2F2", font=("Segoe UI", 14)).pack(pady=(0, 20))
    
        f_acao = ctk.CTkFrame(wrapper, corner_radius=15, fg_color="#31455C")
        f_acao.pack(pady=10, padx=20, ipadx=40, ipady=30)
    
        ctk.CTkLabel(f_acao, text="Arraste e solte o arquivo PDF aqui", font=("Segoe UI", 16), text_color="#D6E2F2").pack(pady=(15, 20))
        self.btn_selecionar_5302 = ctk.CTkButton(f_acao, text="Selecionar Manualmente", command=self.iniciar_selecao_manual_5302, height=50, width=250, font=("Segoe UI", 14, "bold"))
        self.btn_selecionar_5302.pack(pady=(0, 10))
    
        self.btn_cancelar_5302 = ctk.CTkButton(f_acao, text="Cancelar / Reiniciar", command=self.reiniciar_app_5302, fg_color="#E74C3C", hover_color="#C0392B", height=35, font=("Segoe UI", 12, "bold"))
    
        self.lbl_status_5302 = ctk.CTkLabel(wrapper, text="Pronto para gerar...", text_color="#D6E2F2", font=("Segoe UI", 12, "italic"))
        self.lbl_status_5302.pack(pady=15)

    def reiniciar_app_5302(self):
        self.lista_de_partes.clear()
        self.indice_parte_atual = 0
        self.btn_selecionar_5302.configure(text="Selecionar Manualmente", command=self.iniciar_selecao_manual_5302, fg_color=["#3a7ebf", "#1f538d"], hover_color=["#325882", "#14375e"], state="normal")
        self.lbl_status_5302.configure(text="Arraste um arquivo ou clique acima", text_color="#D6E2F2")
        self.btn_cancelar_5302.pack_forget()

    def copiar_proxima_parte_5302(self):
        if self.indice_parte_atual < len(self.lista_de_partes):
            self._copiar_texto(self.lista_de_partes[self.indice_parte_atual])
            self.indice_parte_atual += 1
            if self.indice_parte_atual < len(self.lista_de_partes):
                self.btn_selecionar_5302.configure(text=f"Copiar Parte {self.indice_parte_atual + 1} de {len(self.lista_de_partes)}", fg_color="#E67E22", hover_color="#D35400")
                self.lbl_status_5302.configure(text=f"Parte {self.indice_parte_atual} copiada! Cole no Copilot e volte.", text_color=TEMA["texto_claro"])
            else:
                self.btn_selecionar_5302.configure(text="Finalizado! Reiniciar", command=self.reiniciar_app_5302, fg_color="#2ECC71", hover_color="#27AE60")
                self.lbl_status_5302.configure(text="Ultima parte copiada! Siga no Copilot.", text_color="#2ECC71")
                self.btn_cancelar_5302.pack_forget()
                self.lista_de_partes.clear()
                self.indice_parte_atual = 0

    def processar_pdf_thread_5302(self, caminho_pdf):
        texto_extraido = self.extrair_texto_pdf(caminho_pdf)
        linhas = texto_extraido.split('\n')
        linhas_limpas = []
        padrao_guia = re.compile(r'\b(2[56789]\d{6})\b')
        guia_atual = "N/A"
        ultimo_item_autorizado = False
        palavras_ignoradas = [
            "PAGINA", "MÊS PRODUCAO", "HORA", "DATA", "ROD",
            "A B O", "ABO", "SAO", "PAULO", "FILIAL", "ESTATISTICA",
            "TOTALIZACAO", "QUANTIDADE", "QTDE", "PROCESSSO",
            "SISTEMA DE CONTROLE", "RESUMO DO PROCESSO",
        ]
    
        for idx, linha in enumerate(linhas):
            linha_limpa = linha.strip()
            proc_detectado = False
    
            if linha_limpa:
                mg = padrao_guia.search(linha_limpa)
                if mg:
                    nova_guia = mg.group(1)
                    if nova_guia != guia_atual:
                        guia_atual = nova_guia
                        ultimo_item_autorizado = False
    
                mp_item = re.search(r'^\s*(\d{1,3})\s+(\d{3,4})\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]+)', linha_limpa.upper())
                mp_livre = None if mp_item else re.search(r'(?:^\s*\d{1,3}\s+)?(\d{3,4})\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]+)', linha_limpa.upper())
                mp = mp_item or mp_livre
                if mp:
                    if mp_item:
                        cod_extraido = mp_item.group(2)
                        desc_tmp = mp_item.group(3).strip()
                    else:
                        cod_extraido = mp_livre.group(1)
                        desc_tmp = mp_livre.group(2).strip()
    
                    if (
                        len(desc_tmp) > 2
                        and not any(lixo in desc_tmp for lixo in palavras_ignoradas)
                        and desc_tmp != "TOTAL"
                    ):
                        cod_encontrado = str(int(cod_extraido))
                        e_glosa = cod_encontrado in self.mapa_glosas
                        e_proc_conhecido = (cod_encontrado in self.mapa_procedimentos) and not e_glosa
                        if mp_item or e_proc_conhecido:
                            pass
    
            glosas_linha = self._extrair_glosas_textuais_linha_segura(linha)
            if glosas_linha:
                glosa_autorizada = self._linha_tem_login_auditor(linha) or self._glosa_tem_login_proximo(linhas, idx, self.login_auditor)
                if glosa_autorizada:
                    continue
                if any(self._normalizar_codigo_glosa(cod_glosa) not in GLOSAS_IGNORAR for cod_glosa, _, _ in glosas_linha):
                    continue
    
            linhas_limpas.append(linha)
    
        texto_limpo = "\n".join(linhas_limpas)
        self.after(0, self.finalizar_processamento_5302, texto_limpo, caminho_pdf)
        return
    
        texto_extraido = self.extrair_texto_pdf(caminho_pdf)
        linhas = texto_extraido.split('\n')
        linhas_limpas = []
        padrao_glosa = re.compile(r'[\.,]\d{2}.*?(?:\s|^)(\d{2,3})\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\n]*)$')
        for idx, linha in enumerate(linhas):
            m_glosa = padrao_glosa.search(linha)
            if m_glosa:
                if m_glosa.group(1) in GLOSAS_IGNORAR: continue 
            linhas_limpas.append(linha)
    
        texto_limpo = "\n".join(linhas_limpas)
        self.after(0, self.finalizar_processamento_5302, texto_limpo, caminho_pdf)

    def finalizar_processamento_5302(self, texto_extraido, caminho_pdf):
        if not texto_extraido.strip():
            self.lbl_status_5302.configure(text="Erro: PDF vazio ou ilegível.", text_color="#E74C3C")
            self.btn_selecionar_5302.configure(state="normal")
            return
    
        LIMITE_CARACTERES = 12000 
        TAMANHO_MAX_CHUNK = 7500 
        prompt_completo = PROMPT_BASE.format(login_auditor=self.login_auditor, texto_extraido=texto_extraido)
    
        try:
            if len(prompt_completo) <= LIMITE_CARACTERES:
                self.btn_cancelar_5302.pack_forget()
                prompt_final = "[INSTRUÇÃO INICIAL] Leia o texto abaixo e aplique as regras. SE HOUVER GLOSA 438, 450 OU 463, me pergunte antes de gerar o resumo.\n\n" + prompt_completo
                self._copiar_texto(prompt_final)
                self.lbl_status_5302.configure(text="Copiado! Abrindo o Copilot...", text_color="#2ECC71")
                self.btn_selecionar_5302.configure(state="normal", text="Selecionar novo PDF", command=self.iniciar_selecao_manual_5302)
                self.abrir_copilot()
            else:
                self.btn_cancelar_5302.pack(pady=(5, 10), fill="x")
                self.lbl_status_5302.configure(text="Texto longo! Fatiando as partes...", text_color=TEMA["texto_claro"])
                linhas = texto_extraido.split('\n')
                chunks, chunk_atual = [], ""
                for linha in linhas:
                    if len(chunk_atual) + len(linha) > TAMANHO_MAX_CHUNK:
                        chunks.append(chunk_atual)
                        chunk_atual = linha + "\n"
                    else:
                        chunk_atual += linha + "\n"
                if chunk_atual: chunks.append(chunk_atual)
    
                total_partes = len(chunks)
                self.lista_de_partes.clear()
    
                for i, chunk in enumerate(chunks, 1):
                    if i == 1:
                        texto = (f"[INSTRUÇÃO PARA A IA] Vou te enviar um texto dividido em {total_partes} partes. ESTA É A PARTE 1. LEIA AS REGRAS ABAIXO, MAS NÃO FAÇA NADA AINDA. Apenas responda: 'Recebido. Aguardando a próxima parte'.\n\n{PROMPT_BASE.format(login_auditor=self.login_auditor, texto_extraido=chunk)}")
                    elif i < total_partes:
                        texto = (f"[INSTRUÇÃO PARA A IA] ESTA É A PARTE {i} DE {total_partes}. CONTINUANDO... NÃO FAÇA NADA AINDA. Apenas responda: 'Recebido. Aguardando a próxima parte'.\n\n{chunk}")
                    else:
                        texto = (f"[INSTRUÇÃO PARA A IA] ESTA É A PARTE {i} DE {total_partes} (ÚLTIMA). O texto acabou. Agora analise tudo. 1º - Verifique glosas 438, 450 ou 463 e siga a Regra 4.1. 2º - Se não houver, gere o parágrafo de resumo.\n\n{chunk}")
                    self.lista_de_partes.append(texto)
    
                self.indice_parte_atual = 0
                self.btn_selecionar_5302.configure(text=f"Copiar Parte 1 de {total_partes}", command=self.copiar_proxima_parte_5302, state="normal", fg_color="#E67E22", hover_color="#D35400")
                self.lbl_status_5302.configure(text="Texto fatiado! Clique no botão acima.", text_color=TEMA["texto_claro"])
                self.abrir_copilot()
        except Exception:
            self.lbl_status_5302.configure(text="Erro ao processar.", text_color="#E74C3C")
            self.btn_selecionar_5302.configure(state="normal")
            self.btn_cancelar_5302.pack_forget()

    def validar_e_iniciar_5302(self, caminho_pdf):
        self.lbl_status_5302.configure(text="Extraindo texto... (Aguarde)", text_color="#E67E22")
        self.btn_selecionar_5302.configure(state="disabled")
        self.btn_cancelar_5302.pack_forget()
        self._executar_em_thread(self.processar_pdf_thread_5302, caminho_pdf, on_error=self._tratar_erro_5302)

    def iniciar_selecao_manual_5302(self):
        caminho = filedialog.askopenfilename(title="Selecione o PDF", filetypes=[("PDF", "*.pdf")])
        if caminho: self.validar_e_iniciar_5302(caminho)

    def setup_tela_5302_offline(self):
        wrapper = ctk.CTkFrame(self, fg_color="transparent")
        wrapper.pack(expand=True, fill="both", padx=20, pady=15)
    
        # --- CABEÇALHO ---
        header = ctk.CTkFrame(wrapper, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(header, text="Relatório 5302 Offline", font=("Segoe UI", 26, "bold"), text_color=TEMA["texto_claro"]).pack(side="left")
        ctk.CTkLabel(header, text="Redação automática imediata", text_color="#8899AA", font=("Segoe UI", 13)).pack(side="left", padx=(12, 0), pady=(6, 0))
    
        header_status = ctk.CTkFrame(header, fg_color="transparent")
        header_status.pack(side="right", padx=(12, 0))
    
        self.btn_selecionar_offline = ctk.CTkButton(
            header_status,
            text="Processar PDF/CSV",
            command=self.iniciar_selecao_manual_offline,
            width=184,
            height=42,
            font=("Segoe UI", 13, "bold"),
            corner_radius=10,
            fg_color="#203551",
            hover_color="#1A2A40"
        )
    
        self.lbl_status_offline = ctk.CTkLabel(
            header_status,
            text="Aguardando arquivo...",
            text_color="#7F8C9B",
            font=("Segoe UI", 11, "italic")
        )
        self.lbl_status_offline.pack(anchor="e", pady=(6, 0))
    
        # Barra de progresso indeterminada (oculta por padrão)
        self.progress_offline = ctk.CTkProgressBar(header_status, mode="indeterminate", height=4, corner_radius=2, progress_color="#3498DB", width=220)
        # Não fazemos pack — mostrado apenas durante processamento
    
        # --- CARDS KPI (inicialmente ocultos) ---
        self.frame_kpis_offline = ctk.CTkFrame(wrapper, fg_color="transparent")
        self._kpi_cards_offline = {}
        kpis_config = [
            ("guias",       "Guias Processadas",  "0", "#3498DB"),
            ("glosas",      "Glosas Detectadas",  "0", "#E67E22"),
            ("taxa_risco",  "Taxa Crítica",       "0%", "#E74C3C"),
        ]
        for col, (key, titulo, default, cor) in enumerate(kpis_config):
            card = ctk.CTkFrame(self.frame_kpis_offline, corner_radius=10, fg_color="#1B2838", border_width=1, border_color=cor)
            card.grid(row=0, column=col, padx=8, pady=6, sticky="nsew")
            self.frame_kpis_offline.grid_columnconfigure(col, weight=1)
            barra = ctk.CTkFrame(card, height=3, fg_color=cor, corner_radius=0)
            barra.pack(fill="x", side="top")
            ctk.CTkLabel(card, text=titulo, font=("Segoe UI", 11), text_color="#8899AA").pack(anchor="w", padx=14, pady=(10, 0))
            lbl_valor = ctk.CTkLabel(card, text=default, font=("Segoe UI", 28, "bold"), text_color="white")
            lbl_valor.pack(anchor="w", padx=14, pady=(2, 10))
            self._kpi_cards_offline[key] = lbl_valor
    
        self.ranking_glosas_offline_atual = []
        self.resumo_critico_offline = ""
    
        # --- ÁREA DE RESULTADOS (textboxes + painel de ações) ---
        area_resultados = ctk.CTkFrame(wrapper, fg_color="transparent")
        area_resultados.pack(fill="both", expand=True, pady=(4, 0))
    
        area_textos = ctk.CTkFrame(area_resultados, fg_color="transparent")
        area_textos.pack(side="left", fill="both", expand=True, padx=(0, 10))
    
        coluna_lateral_offline = ctk.CTkFrame(area_resultados, width=400, fg_color="transparent")
        coluna_lateral_offline.pack(side="right", fill="y")
        coluna_lateral_offline.pack_propagate(False)
    
        # --- BARRA DE META-INFO (oculta até processamento) ---
        self.frame_meta_offline = ctk.CTkFrame(
            area_textos, fg_color="#182433", corner_radius=8,
            border_width=1, border_color="#2A3C55"
        )
        # pack feito dinamicamente em _atualizar_metadados_offline
        self._meta_cards_offline = {}
        _meta_row = ctk.CTkFrame(self.frame_meta_offline, fg_color="transparent")
        _meta_row.pack(fill="x", padx=12, pady=8)
        for _key, _default in [
            ("prestador", "Prestador: -"),
            ("processo", "Processo: -"),
            ("mes", "Mês: -"),
        ]:
            _lbl = ctk.CTkLabel(
                _meta_row, text=_default,
                font=("Segoe UI", 11, "bold"), text_color="#FFFFFF"
            )
            _lbl.pack(side="left", padx=(0, 20))
            self._meta_cards_offline[_key] = _lbl
    
        # --- BARRA DE META-INFO (oculta até processamento) ---
        self.frame_meta_offline = ctk.CTkFrame(
            area_textos, fg_color="#182433", corner_radius=8,
            border_width=1, border_color="#2A3C55"
        )
        self._meta_cards_offline = {}
        _meta_row = ctk.CTkFrame(self.frame_meta_offline, fg_color="transparent")
        _meta_row.pack(fill="x", padx=12, pady=8)
        for _key, _default in [("prestador", "Prestador: -"), ("processo", "Processo: -"), ("mes", "Mês: -")]:
            _lbl = ctk.CTkLabel(_meta_row, text=_default, font=("Segoe UI", 11, "bold"), text_color="#FFFFFF")
            _lbl.pack(side="left", padx=(0, 20))
            self._meta_cards_offline[_key] = _lbl
    
        ctk.CTkLabel(area_textos, text="Relatório Principal (editável):", font=("Segoe UI", 12, "bold"), text_color="#D6E2F2").pack(anchor="w")
        self.caixa_texto_offline = ctk.CTkTextbox(area_textos, height=180, font=("Consolas", 13), wrap="word", corner_radius=8, fg_color="#0D1B2A", border_width=1, border_color="#2C3E50")
        self.caixa_texto_offline.pack(fill="both", expand=True, pady=(5, 4))
        self.caixa_texto_offline.bind("<KeyRelease>", lambda e: self._atualizar_contador_offline())
    
        # Contador de caracteres
        self.lbl_char_count_offline = ctk.CTkLabel(area_textos, text="0 caracteres", font=("Segoe UI", 10), text_color="#5A6A7A")
        self.lbl_char_count_offline.pack(anchor="e", pady=(0, 6))
    
        ctk.CTkLabel(area_textos, text="Glosas Automáticas:", font=("Segoe UI", 12, "bold"), text_color="#D6E2F2").pack(anchor="w")
        self.caixa_texto_auto = ctk.CTkTextbox(area_textos, height=80, font=("Consolas", 12), wrap="word", corner_radius=8, fg_color="#0D1B2A", border_width=1, border_color="#2C3E50")
        self.caixa_texto_auto.pack(fill="x", pady=(5, 0))
    
        # --- PAINEL DE AÇÕES (botões à direita) ---
        painel_acoes = ctk.CTkFrame(coluna_lateral_offline, fg_color="transparent")
        painel_acoes.pack(fill="x")
    
        btn_style = {"height": 38, "font": ("Segoe UI", 12, "bold"), "corner_radius": 8}
    
        # --- Grupo: Redação Final ---
        f_redacao = ctk.CTkFrame(painel_acoes, fg_color="#1B2838", corner_radius=10, border_width=1, border_color="#2C3E50")
        f_redacao.pack(fill="x", pady=(0, 10), ipady=5)
        ctk.CTkLabel(f_redacao, text="Redação Final", font=("Segoe UI", 11, "bold"), text_color="#8899AA").pack(pady=(8, 4))
    
        self.btn_copiar_offline = ctk.CTkButton(f_redacao, text="📋 Copiar Relatório Completo", command=lambda: self._copiar_com_feedback(self.btn_copiar_offline, self.caixa_texto_offline.get("0.0", "end").strip()), fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"], state="disabled", **btn_style)
        self.btn_copiar_offline.pack(pady=4, padx=12, fill="x")
    
        # Grid 2x2 para opções principais
        f_grid_main = ctk.CTkFrame(f_redacao, fg_color="transparent")
        f_grid_main.pack(fill="x", padx=10, pady=2)
        f_grid_main.columnconfigure((0, 1), weight=1)
    
        self.btn_toggle_resumo_offline = ctk.CTkButton(f_grid_main, text="📝 Resumir Texto", command=self.toggle_resumo_offline, fg_color="#1F618D", hover_color="#1A5276", state="disabled", height=34, font=("Segoe UI", 11, "bold"), corner_radius=6)
        self.btn_toggle_resumo_offline.grid(row=0, column=0, padx=2, pady=2, sticky="ew")
    
        self.btn_mensagens_prestador_offline = ctk.CTkButton(f_grid_main, text="💬 Mensagens", command=self.abrir_popup_mensagens_prestador_offline, fg_color="#186A3B", hover_color="#145A32", height=34, font=("Segoe UI", 11, "bold"), corner_radius=6)
        self.btn_mensagens_prestador_offline.grid(row=0, column=1, padx=2, pady=2, sticky="ew")
    
        self.btn_copiar_resumo_criticas = ctk.CTkButton(f_grid_main, text="📄 Só Críticas", command=lambda: self._copiar_com_feedback(self.btn_copiar_resumo_criticas, self.resumo_critico_offline), fg_color="#34495E", hover_color="#2C3E50", state="disabled", height=34, font=("Segoe UI", 11, "bold"), corner_radius=6)
        self.btn_copiar_resumo_criticas.grid(row=1, column=0, padx=2, pady=2, sticky="ew")
    
        self.btn_ranking_glosas_offline = ctk.CTkButton(f_grid_main, text="📊 Ranking", command=self.abrir_popup_ranking_glosas_offline, fg_color="#5D6D7E", hover_color="#34495E", state="disabled", height=34, font=("Segoe UI", 11, "bold"), corner_radius=6)
        self.btn_ranking_glosas_offline.grid(row=1, column=1, padx=2, pady=2, sticky="ew")
    
        # Grid 2x1 para Cópia Especial
        f_grid_copy = ctk.CTkFrame(f_redacao, fg_color="transparent")
        f_grid_copy.pack(fill="x", padx=10, pady=(2, 6))
        f_grid_copy.columnconfigure((0, 1), weight=1)
    
        self.btn_copiar_critico = ctk.CTkButton(f_grid_copy, text="⚠️ c/ Esp. Crítica", command=lambda: self._copiar_com_feedback(self.btn_copiar_critico, None, self.copiar_offline_com_esp_critica), fg_color="#2E86C1", hover_color="#21618C", state="disabled", height=32, font=("Segoe UI", 10, "bold"), corner_radius=6)
        self.btn_copiar_critico.grid(row=0, column=0, padx=2, pady=2, sticky="ew")
    
        self.btn_copiar_sem_critico = ctk.CTkButton(f_grid_copy, text="✅ s/ Esp. Crítica", command=lambda: self._copiar_com_feedback(self.btn_copiar_sem_critico, None, self.copiar_offline_sem_esp_critica), fg_color="#1A5276", hover_color="#154360", state="disabled", height=32, font=("Segoe UI", 10, "bold"), corner_radius=6)
        self.btn_copiar_sem_critico.grid(row=0, column=1, padx=2, pady=2, sticky="ew")
    
        # --- Grupo: Justificativas ---
        f_just = ctk.CTkFrame(painel_acoes, fg_color="#1B2838", corner_radius=10, border_width=1, border_color="#2C3E50")
        f_just.pack(fill="x", pady=(0, 10), ipady=5)
        ctk.CTkLabel(f_just, text="Auditoria Manual", font=("Segoe UI", 11, "bold"), text_color="#F39C12").pack(pady=(8, 4))
    
        self.btn_justificar_tecnicas = ctk.CTkButton(f_just, text="🔧 Justificar Glosas Técnicas", command=self.abrir_popup_justificativas_tecnicas, fg_color="#D35400", hover_color="#BA4A00", state="disabled", **btn_style)
        self.btn_justificar_tecnicas.pack(pady=4, padx=12, fill="x")
    
        self.btn_justificar_criticas = ctk.CTkButton(f_just, text="⚠️ Justificar Glosas Críticas", command=self.abrir_popup_justificativas_offline, fg_color="#C0392B", hover_color="#A93226", state="disabled", **btn_style)
        self.btn_justificar_criticas.pack(pady=4, padx=12, fill="x")
    
        painel_acoes.destroy()
        _scroll_coluna = ctk.CTkScrollableFrame(coluna_lateral_offline, fg_color="transparent", scrollbar_button_color=TEMA["bg_surface_3"], scrollbar_button_hover_color=TEMA["azul_primario"])
        _scroll_coluna.pack(fill="both", expand=True)
        painel_acoes = ctk.CTkFrame(_scroll_coluna, fg_color="transparent")
        painel_acoes.pack(fill="x")
    
        ctk.CTkLabel(
            painel_acoes,
            text="Ações Rápidas",
            font=("Segoe UI", 18, "bold"),
            text_color=TEMA["texto_claro"]
        ).pack(anchor="w", pady=(0, 10))
    
        btn_style = {"height": 38, "font": ("Segoe UI", 12, "bold"), "corner_radius": 12}
        btn_style_small = {"height": 46, "font": ("Segoe UI", 10, "bold"), "corner_radius": 12}
        btn_style_aux = {"height": 38, "font": ("Segoe UI", 11, "bold"), "corner_radius": 12}
    
        self.btn_novo_pdf_acoes_offline = ctk.CTkButton(
            painel_acoes,
            text="Processar PDF/CSV",
            command=self.abrir_novo_pdf_offline_acao,
            fg_color="#203551",
            hover_color="#1A2A40",
            text_color="#F2F6FC",
            border_width=1,
            border_color="#2A3C55",
            **btn_style
        )
        self.btn_novo_pdf_acoes_offline.pack(fill="x", pady=(0, 8))
    
        f_redacao = ctk.CTkFrame(painel_acoes, fg_color="#182433", corner_radius=16, border_width=1, border_color="#2A3C55")
        f_redacao.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(f_redacao, text="Relatório Final", font=("Segoe UI", 13, "bold"), text_color="#F2F6FC").pack(anchor="w", padx=14, pady=(10, 6))
    
        self.btn_copiar_offline = ctk.CTkButton(
            f_redacao,
            text="Copiar Redação",
            command=lambda: self._copiar_com_feedback(self.btn_copiar_offline, self.caixa_texto_offline.get("0.0", "end").strip()),
            fg_color=TEMA["azul_primario"],
            hover_color=TEMA["azul_hover"],
            text_color="#FFFFFF",
            state="disabled",
            **btn_style
        )
        self.btn_copiar_offline.pack(padx=12, pady=(0, 8), fill="x")
    
        f_grid_variacoes = ctk.CTkFrame(f_redacao, fg_color="transparent")
        f_grid_variacoes.pack(fill="x", padx=12, pady=(0, 6))
        f_grid_variacoes.columnconfigure((0, 1), weight=1)
    
        self.btn_copiar_sem_critico = ctk.CTkButton(
            f_grid_variacoes,
            text="s/ Esp. Críticas",
            command=lambda: self._copiar_com_feedback(self.btn_copiar_sem_critico, None, self.copiar_offline_sem_esp_critica),
            fg_color="#203551",
            hover_color="#1A2A40",
            border_width=1,
            border_color="#2A3C55",
            text_color="#DCE7F8",
            state="disabled",
            **btn_style_small
        )
        self.btn_copiar_sem_critico.grid(row=0, column=0, padx=(0, 4), sticky="ew")
    
        self.btn_copiar_critico = ctk.CTkButton(
            f_grid_variacoes,
            text="c/ Esp. Críticas",
            command=lambda: self._copiar_com_feedback(self.btn_copiar_critico, None, self.copiar_offline_com_esp_critica),
            fg_color="#203551",
            hover_color="#1A2A40",
            border_width=1,
            border_color="#2A3C55",
            text_color="#DCE7F8",
            state="disabled",
            **btn_style_small
        )
        self.btn_copiar_critico.grid(row=0, column=1, padx=(4, 0), sticky="ew")
    
        f_grid_aux = ctk.CTkFrame(f_redacao, fg_color="transparent")
        f_grid_aux.pack(fill="x", padx=12, pady=(0, 6))
        f_grid_aux.columnconfigure((0, 1), weight=1)
    
        self.btn_toggle_resumo_offline = ctk.CTkButton(
            f_grid_aux,
            text="Resumo",
            command=self.toggle_resumo_offline,
            fg_color="#203551",
            hover_color="#1A2A40",
            border_width=1,
            border_color="#2A3C55",
            text_color="#DCE7F8",
            state="disabled",
            **btn_style_aux
        )
        self.btn_toggle_resumo_offline.grid(row=0, column=0, padx=(0, 4), sticky="ew")
    
        self.btn_copiar_resumo_criticas = ctk.CTkButton(
            f_grid_aux,
            text="Copiar Críticas",
            command=lambda: self._copiar_com_feedback(self.btn_copiar_resumo_criticas, self.resumo_critico_offline),
            fg_color=TEMA["azul_primario"],
            hover_color=TEMA["azul_hover"],
            text_color="#FFFFFF",
            state="disabled",
            **btn_style_aux
        )
        self.btn_copiar_resumo_criticas.grid(row=0, column=1, padx=(4, 0), sticky="ew")
    
        self.btn_ranking_glosas_offline = ctk.CTkButton(
            f_redacao,
            text="Ranking de Glosas",
            command=self.abrir_popup_ranking_glosas_offline,
            fg_color="transparent",
            hover_color="#203551",
            border_width=1,
            border_color="#4F8CFF",
            text_color="#DCE7F8",
            state="disabled",
            **btn_style_aux
        )
        self.btn_ranking_glosas_offline.pack(padx=12, pady=(0, 10), fill="x")
    
        f_just = ctk.CTkFrame(painel_acoes, fg_color="#182433", corner_radius=16, border_width=1, border_color="#2A3C55")
        f_just.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(f_just, text="Justificativas", font=("Segoe UI", 13, "bold"), text_color="#F2F6FC").pack(anchor="w", padx=14, pady=(10, 6))
    
        self.btn_justificar_tecnicas = ctk.CTkButton(
            f_just,
            text="Glosas Técnicas",
            command=self.abrir_popup_justificativas_tecnicas,
            fg_color="#E86D11",
            hover_color="#C95C0C",
            text_color="#FFFFFF",
            state="disabled",
            **btn_style
        )
        self.btn_justificar_tecnicas.pack(padx=12, pady=(0, 6), fill="x")
    
        self.btn_justificar_criticas = ctk.CTkButton(
            f_just,
            text="Glosas Críticas",
            command=self.abrir_popup_justificativas_offline,
            fg_color="transparent",
            hover_color="#2B3647",
            border_width=1,
            border_color="#E86D11",
            text_color="#F2F6FC",
            state="disabled",
            **btn_style
        )
        self.btn_justificar_criticas.pack(padx=12, pady=(0, 10), fill="x")
    
        f_util = ctk.CTkFrame(painel_acoes, fg_color="#182433", corner_radius=16, border_width=1, border_color="#2A3C55")
        f_util.pack(fill="x")
        ctk.CTkLabel(f_util, text="Utilidades", font=("Segoe UI", 13, "bold"), text_color="#F2F6FC").pack(anchor="w", padx=14, pady=(10, 6))
    
        self.btn_mensagens_prestador_offline = ctk.CTkButton(
            f_util,
            text="Mensagens para Prestador",
            command=self.abrir_popup_mensagens_prestador_offline,
            fg_color="transparent",
            hover_color="#203551",
            border_width=1,
            border_color="#4F8CFF",
            text_color="#DCE7F8",
            **btn_style
        )
        self.btn_mensagens_prestador_offline.pack(padx=12, pady=(0, 10), fill="x")

    def toggle_resumo_offline(self):
        if not self.resumo_ativo_offline:
            self.texto_completo_offline = self.caixa_texto_offline.get("0.0", "end").strip()
            if not self.texto_completo_offline:
                return
            texto_resumido = ""
            if getattr(self, 'dados_extraidos_offline', None):
                texto_resumido = self._gerar_texto_resumido_offline_dados()
            if not texto_resumido:
                texto_resumido = self._processar_texto_resumido(self.texto_completo_offline)
            self.caixa_texto_offline.delete("0.0", "end")
            self.caixa_texto_offline.insert("0.0", texto_resumido)
            self.resumo_ativo_offline = True
            self.btn_toggle_resumo_offline.configure(text="Desfazer Resumo", fg_color="#5D6D7E", hover_color="#34495E")
        else:
            self.caixa_texto_offline.delete("0.0", "end")
            self.caixa_texto_offline.insert("0.0", self.texto_completo_offline)
            self.resumo_ativo_offline = False
            self.btn_toggle_resumo_offline.configure(text="Resumo", fg_color="#203551", hover_color="#1A2A40")
        self._atualizar_contador_offline()

    def abrir_popup_mensagens_prestador_offline(self):
        popup = ctk.CTkToplevel(self)
        popup.title("Mensagens para Prestador")
        popup.geometry("620x520")
        popup.attributes('-topmost', True)
        popup.grab_set()
        self._tematizar_popup(popup)
    
        container = ctk.CTkFrame(popup, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
    
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            header,
            text="Mensagens para Prestador",
            font=("Segoe UI", 22, "bold"),
            text_color=TEMA["texto_claro"]
        ).pack(side="left")
        ctk.CTkButton(
            header,
            text="Fechar",
            width=90,
            height=34,
            command=popup.destroy,
            fg_color=TEMA["bg_surface_3"],
            hover_color=TEMA["azul_sidebar_hover"]
        ).pack(side="right")
    
        ctk.CTkLabel(
            container,
            text="Selecione uma mensagem salva para copiar o texto completo.",
            font=("Segoe UI", 12),
            text_color=TEMA["texto_secundario"]
        ).pack(anchor="w", pady=(0, 10))
    
        lista = ctk.CTkScrollableFrame(container, fg_color="transparent")
        lista.pack(fill="both", expand=True)
    
        mensagens = self._obter_textos_prestador_salvos()
        if not mensagens:
            ctk.CTkLabel(
                lista,
                text="Nenhuma mensagem cadastrada em Textos para Prestador.",
                font=("Segoe UI", 13),
                text_color=TEMA["texto_muted"]
            ).pack(pady=30)
            return
    
        for row in mensagens:
            item = ctk.CTkFrame(
                lista,
                fg_color=TEMA["bg_surface_2"],
                corner_radius=12,
                border_width=1,
                border_color=TEMA["borda"]
            )
            item.pack(fill="x", pady=6)
            item.grid_columnconfigure(0, weight=1)
    
            ctk.CTkLabel(
                item,
                text=row["titulo"],
                font=("Segoe UI", 14, "bold"),
                text_color=TEMA["texto_claro"],
                anchor="w",
                justify="left",
                wraplength=430
            ).grid(row=0, column=0, sticky="ew", padx=(14, 10), pady=14)
    
            ctk.CTkButton(
                item,
                text="Copiar",
                width=90,
                height=34,
                fg_color=TEMA["azul_primario"],
                hover_color=TEMA["azul_hover"],
                command=lambda conteudo=row["conteudo"]: self._copiar_texto(
                    conteudo,
                    mensagem_sucesso="Mensagem copiada!"
                )
            ).grid(row=0, column=1, padx=(0, 14), pady=10)

    def _atualizar_contador_offline(self):
        """Atualiza o label de contagem de caracteres."""
        try:
            texto = self.caixa_texto_offline.get("0.0", "end").strip()
            self.lbl_char_count_offline.configure(text=f"{len(texto)} caracteres")
        except Exception:
            pass

    def _mostrar_progresso_offline(self, ativo=True):
        """Mostra/oculta a barra de progresso indeterminada."""
        if ativo:
            self.progress_offline.pack(anchor="e", fill="x", pady=(4, 0))
            self.progress_offline.start()
        else:
            self.progress_offline.stop()
            self.progress_offline.pack_forget()

    def _atualizar_kpis_offline(self, guias=0, glosas=0, taxa=0.0):
        """Atualiza os cards KPI e torna-os visíveis após o processamento."""
        if not self.frame_kpis_offline.winfo_ismapped():
            self.frame_kpis_offline.pack(fill="x", pady=(0, 8), before=self.frame_kpis_offline.master.winfo_children()[-1])
        self._kpi_cards_offline["guias"].configure(text=str(guias))
        self._kpi_cards_offline["glosas"].configure(text=str(glosas))
        self._kpi_cards_offline["taxa_risco"].configure(text=f"{taxa:.1f}%")

    def copiar_offline_com_esp_critica(self):
        texto = self.caixa_texto_offline.get('0.0', 'end').strip()
        # Garante que o texto tenha o prefixo, mas não duplicado
        prefixo = 'PROCESSO ANALISADO POR AMOSTRAGEM DAS ESPECIALIDADES CRÍTICAS///'
        if texto.startswith(prefixo):
            self._copiar_texto(texto)
        else:
            self._copiar_texto(f'{prefixo}{texto}')

    def copiar_offline_sem_esp_critica(self):
        texto = self.caixa_texto_offline.get('0.0', 'end').strip()
        prefixo = 'PROCESSO SEM ESPECIALIDADES CRÍTICAS ANALISADO POR AMOSTRAGEM DO ENVIO DE IMAGENS///'
        if texto.startswith(prefixo):
            self._copiar_texto(texto)
        else:
            self._copiar_texto(f'{prefixo}{texto}')

    def _agrupar_palavras_por_linha_offline(self, page, y_bucket=3):
        rows = {}
        try:
            words = page.extract_words(x_tolerance=2, y_tolerance=2, keep_blank_chars=False)
        except Exception:
            words = []
        for w in words:
            key = int(round(w['top'] / float(y_bucket)) * y_bucket)
            rows.setdefault(key, []).append(w)
        linhas = []
        for key in sorted(rows):
            row = sorted(rows[key], key=lambda x: x['x0'])
            linhas.append({
                'y': key,
                'words': row,
                'text': ' '.join(w['text'] for w in row)
            })
        return linhas

    def _linha_eh_cabecalho_detalhe_offline(self, linha):
        texto = (linha.get('text') or '').upper()
        return 'PROCEDIMENTO' in texto and 'GLOSA' in texto and 'IT' in texto

    def _extrair_guia_linha_offline(self, linha):
        # Aceita guias de 7-9 dígitos (ex: 187xxxxx do aa.pdf, 25xxxxx de outros processos)
        texto = linha.get('text') or ''
        m = re.search(r'\b(\d{7,9})\b', texto)
        return m.group(1) if m else None

    def _extrair_glosa_linha_offline(self, linha):
        texto_linha = (linha.get('text') or '').strip().upper()
    
        # Ignora lixo de cabeçalho e rodapé
        if any(k in texto_linha for k in ['PAGINA', 'DATA', 'HORA', 'FILIAL:', 'PROCESSO:', 'TOTAL']):
            return None, None
    
        palavras = linha.get('words', [])
        # Pega do meio pro final da página (x0 >= 300) para pular o nome do procedimento e não cortar o 66
        palavras_direita = [w for w in palavras if w['x0'] >= 300]
        if not palavras_direita:
            return None, None
    
        texto_direita = ' '.join(w['text'] for w in palavras_direita).strip()
    
        # Busca código de glosa: 1 a 3 dígitos isolados, seguidos de palavras
        m = re.search(r'\b(\d{1,3})\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]+)', texto_direita)
        if not m:
            return None, None
    
        cod_glosa = m.group(1)
        desc_glosa = m.group(2).strip(' -()')
    
        # Blindagem contra falsos positivos do cabeçalho
        if cod_glosa in ['016', '09', '15'] and ('PAULO' in desc_glosa or 'SAO' in desc_glosa):
            return None, None
    
        # Trata a diferença entre "66" e "066" se o usuário ou sistema salvar diferente
        motivo_limpo = self.mapa_glosas.get(cod_glosa)
        if not motivo_limpo:
            motivo_limpo = self.mapa_glosas.get(cod_glosa.zfill(3))
            if motivo_limpo:
                cod_glosa = cod_glosa.zfill(3)
            else:
                motivo_limpo = self.mapa_glosas.get(cod_glosa.lstrip('0'))
                if motivo_limpo:
                    cod_glosa = cod_glosa.lstrip('0')
                else:
                    motivo_limpo = desc_glosa.lower().strip()
                    if desc_glosa:
                        self.aprender_nova_glosa(cod_glosa, desc_glosa)
    
        return cod_glosa, motivo_limpo

    def _extrair_procedimento_linha_offline(self, linha):
        texto = (linha.get('text') or '').upper()
        # Busca por um código de procedimento na linha inteira, sem depender de margem
        m = re.search(r'(?:^\s*\d{1,3}\s+)?(\d{3,4})\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]+)', texto)
        if m:
            proc_cod = m.group(1)
            # Validação extrema: Só aceita se for um procedimento OFICIAL cadastrado no sistema
            if proc_cod in self.mapa_procedimentos:
                return proc_cod, self.mapa_procedimentos[proc_cod]
        return None, None

    def _extrair_detalhes_offline_por_blocos(self, caminho_pdf):
        dados = []
        pdfplumber = self._lazy_import_pdfplumber()
        glosas_auto = []
        vistos_detalhe = set()
        vistos_auto = set()
        guia_atual = None
        glosa_pendente = None
        em_detalhe = False
    
        with pdfplumber.open(caminho_pdf) as pdf:
            for pagina in pdf.pages:
                for linha in self._agrupar_palavras_por_linha_offline(pagina):
                    texto_upper = (linha.get('text') or '').strip().upper()
                    if not texto_upper: continue
    
                    guia_linha = self._extrair_guia_linha_offline(linha)
                    if guia_linha:
                        guia_atual = guia_linha
                        em_detalhe = False
                        glosa_pendente = None
                        continue
    
                    if self._linha_eh_cabecalho_detalhe_offline(linha):
                        em_detalhe = True
                        glosa_pendente = None
                        continue
    
                    if not em_detalhe: continue
                    if texto_upper.startswith('GUIA ') or 'VALOR APRESENTADO ACIMA DO TETO' in texto_upper or 'SUB GLOSA' in texto_upper:
                        continue
    
                    cod_glosa_linha, motivo_glosa_linha = self._extrair_glosa_linha_offline(linha)
                    proc_cod, proc_desc = self._extrair_procedimento_linha_offline(linha)
    
                    # --- CORREÇÃO: CAPTURA IMEDIATA DE GLOSAS AUTOMÁTICAS ---
                    if cod_glosa_linha and (len(cod_glosa_linha) <= 2 or cod_glosa_linha.startswith('0')):
                        if guia_atual and cod_glosa_linha not in GLOSAS_IGNORAR:
                            item_key_auto = (guia_atual, cod_glosa_linha)
                            if item_key_auto not in vistos_auto:
                                glosas_auto.append({'cod': cod_glosa_linha, 'guia': guia_atual, 'motivo': motivo_glosa_linha})
                                vistos_auto.add(item_key_auto)
                        cod_glosa_linha = None # Consome a glosa automática para ela não bagunçar o procedimento abaixo
    
                    if proc_cod:
                        cod_glosa = cod_glosa_linha or (glosa_pendente[0] if glosa_pendente else None)
                        motivo_limpo = motivo_glosa_linha or (glosa_pendente[1] if glosa_pendente else None)
                        glosa_pendente = None
    
                        if not guia_atual or not cod_glosa: continue
                        if cod_glosa in GLOSAS_IGNORAR: continue
    
                        item_key = (guia_atual, proc_cod, cod_glosa)
                        if item_key not in vistos_detalhe:
                            dados.append({
                                'cod': cod_glosa,
                                'motivo_limpo': motivo_limpo,
                                'proc_cod': proc_cod,
                                'proc_desc': proc_desc,
                                'guia': guia_atual,
                                'justificativa': ''
                            })
                            vistos_detalhe.add(item_key)
                        continue
    
                    if cod_glosa_linha:
                        if cod_glosa_linha not in GLOSAS_IGNORAR:
                            glosa_pendente = (cod_glosa_linha, motivo_glosa_linha)
    
        return dados, glosas_auto

    def _extrair_detalhes_offline_legado(self, caminho_pdf):
        linhas = []
        pdfplumber = self._lazy_import_pdfplumber()
        with pdfplumber.open(caminho_pdf) as pdf:
            for pagina in pdf.pages:
                txt = pagina.extract_text()
                if txt:
                    linhas.extend(txt.split('\n'))
                pagina.flush_cache()
        dados = []
        glosas_auto = []
        guia_atual = 'N/A'
        proc_cod_atual = 'N/A'
        proc_desc_atual = 'N/A'
        # Aceita guias de 7-9 dígitos (ex: 187xxxxx do aa.pdf, 25xxxxx de outros processos)
        padrao_guia = re.compile(r'\b(\d{7,9})\b')
        padrao_proc = re.compile(r'(?:^\s*\d{1,3}\s+)?(\d{3,4})\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]+)')
        # Glosa após valor decimal — aceita espaço opcional entre código e descrição
        # Ex. padrão antigo: "430 FALTA RX"  |  Novo: "430FALTA RX" (grudado, aa.pdf)
        padrao_glosa = re.compile(r'[\.,]\d{2}.*?(?:\s|^)(\d{2,3})\s?([A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\n]*)$')
        for linha in linhas:
            lin = linha.strip()
            if not lin:
                continue
            mg = padrao_guia.search(lin)
            if mg:
                guia_atual = mg.group(1)
            mp = padrao_proc.search(lin)
            if mp:
                desc_tmp = mp.group(2).strip()
                palavras_ignoradas = ['TOTAL', 'PAGINA', 'MÊS PRODUCAO', 'HORA', 'DATA', 'ROD', 'A B O', 'ABO']
                if len(desc_tmp) > 2 and not any(lixo in desc_tmp for lixo in palavras_ignoradas):
                    cod_encontrado = str(int(mp.group(1)))
                    if cod_encontrado in self.mapa_procedimentos:
                        proc_cod_atual = cod_encontrado
                        proc_desc_atual = self.mapa_procedimentos[proc_cod_atual]
            m_glosa = padrao_glosa.search(lin)
            if m_glosa:
                cod_glosa = m_glosa.group(1)
                desc_glosa = m_glosa.group(2).strip()
                if self.login_auditor in lin:
                    continue
                if cod_glosa in GLOSAS_IGNORAR:
                    continue
                if cod_glosa in self.mapa_glosas:
                    motivo_limpo = self.mapa_glosas[cod_glosa]
                else:
                    motivo_limpo = desc_glosa.lower()
                    self.aprender_nova_glosa(cod_glosa, desc_glosa)
                if len(cod_glosa) <= 2 or cod_glosa.startswith('0'):
                    if not any(g['cod'] == cod_glosa and g['guia'] == guia_atual for g in glosas_auto):
                        glosas_auto.append({'cod': cod_glosa, 'guia': guia_atual, 'motivo': motivo_limpo})
                else:
                    if not any(g['cod'] == cod_glosa and g['guia'] == guia_atual and g['proc_cod'] == proc_cod_atual for g in dados):
                        dados.append({
                            'cod': cod_glosa,
                            'motivo_limpo': motivo_limpo,
                            'proc_cod': proc_cod_atual,
                            'proc_desc': proc_desc_atual,
                            'guia': guia_atual,
                            'justificativa': ''
                        })
        return dados, glosas_auto

    def processar_pdf_thread_offline(self, caminho_pdf):
        try:
            pdfplumber = self._lazy_import_pdfplumber()
            linhas = []
            import time
            with pdfplumber.open(caminho_pdf) as pdf:
                total_pag = len(pdf.pages)
                for i_pag, pagina in enumerate(pdf.pages):
                    self.after(0, lambda p=i_pag+1, t=total_pag: self.lbl_status_offline.configure(
                        text=f"Lendo página {p} de {t}... (Aguarde)"
                    ))
                    txt = pagina.extract_text()
                    if txt:
                        linhas.extend(txt.split("\n"))
                    pagina.flush_cache()
                    time.sleep(0.01)
    
            self.dados_extraidos_offline = []
            self.glosas_auto_offline = []
            linhas = self._normalizar_linhas_extraidas_pdf(linhas)
    
            # --- Extrair Metadados do PDF ---
            # ── Normalização de layout colunar ──────────────────────────────────
            # PDFs com colunas extraídas separadamente pelo pdfplumber podem gerar
            # um código de glosa sozinho numa linha e a descrição fragmentada nas
            # linhas seguintes. A regra abaixo une essas partes numa única linha
            # antes do loop de detecção, sem mudar nenhuma outra lógica.
            linhas_norm = []
            i_norm = 0
            padrao_cod_isolado = re.compile(r'^\s*(\d{2,3})\s*$')
            padrao_desc_inicio = re.compile(r'^[A-ZÁÉÍÓÚÂÊÔÃÕÇ]')
            while i_norm < len(linhas):
                lin_norm = linhas[i_norm].strip()
                m_iso = padrao_cod_isolado.match(lin_norm)
                if m_iso and self._normalizar_codigo_glosa(m_iso.group(1)) in self.mapa_glosas:
                    partes = []
                    j_norm = i_norm + 1
                    while j_norm < len(linhas) and len(partes) < 6:
                        prox = linhas[j_norm].strip()
                        if not prox:
                            j_norm += 1
                            continue
                        if re.match(r'^\s*\d', prox) or not padrao_desc_inicio.match(prox.upper()):
                            break
                        partes.append(prox)
                        j_norm += 1
                    if partes:
                        linhas_norm.append(lin_norm + " " + " ".join(partes))
                        i_norm = j_norm
                        continue
                linhas_norm.append(linhas[i_norm])
                i_norm += 1
            linhas = linhas_norm
            # ────────────────────────────────────────────────────────────────────
    
            texto_pdf_completo = "\n".join(linhas)
            match_meta = re.search(r'(\d+)\s+(\d{2}/\d{4})\s+\d+\s+(.+?)(?=\n)', texto_pdf_completo)
            self.metadata_pdf_offline = {
                'processo': match_meta.group(1) if match_meta else "N/A",
                'mes': match_meta.group(2) if match_meta else "N/A",
                'prestador': match_meta.group(3).strip() if match_meta else "N/A"
            }
    
            guia_atual = "N/A"
            proc_cod_atual = "N/A"
            proc_desc_atual = "N/A"
            item_atual = ""
    
            # Rastreia o último item registrado da guia corrente.
            # Glosas encontradas sem procedimento na mesma linha serão
            # associadas a ele (ex: glosa 420 em linha órfã logo abaixo
            # de uma linha com glosa 430 — ambas pertencem ao mesmo item).
            ultimo_item_guia = None  # dict: guia, proc_cod, proc_desc, item
    
            # Deduplicação com sets — O(1) no lugar de O(n²)
            vistos_detalhe = set()  # (guia, cod_glosa, proc_cod, item)
            vistos_auto = set()     # (guia, cod_glosa)
    
            # Aceita guias de 7-9 dígitos (cobre aa.pdf com 187xxxxx e PDFs padrão com 25xxxxx)
            padrao_guia = re.compile(r'\b(\d{7,9})\b')
            padrao_proc_item = re.compile(r'^\s*(\d{1,3})\s+(\d{3,4})\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]+)')
            padrao_proc_livre = re.compile(r'(?:^\s*\d{1,3}\s+)?(\d{3,4})\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]+)')
            # Regex principal: glosa na mesma linha do procedimento (após valor decimal)
            # Ex. padrão: "114.70  2035  1  430  FALTA RX INICIAL"
            # aa.pdf:     "15.13 1 472FALTA REQUISITO" (código grudado na descrição)
            # A diferença é o \s? (0 ou 1 espaço) em vez de \s* entre código e descrição
            padrao_glosa = re.compile(r'[\.,]\d{2}.*?(?:\s|^)(\d{2,3})\s?([A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\n]*)$')
            # Regex secundário: linha órfã só com código+descrição de glosa
            # Ex: "420  FALTA RX FINAL" (sem valor decimal antes)
            padrao_glosa_orfan = re.compile(r'^\s*(\d{2,3})\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s\-\/]{2,})$')
            palavras_ignoradas = [
                "PAGINA", "MÊS PRODUCAO", "HORA", "DATA", "ROD",
                "A B O", "ABO", "SAO", "PAULO", "FILIAL", "ESTATISTICA",
                "TOTALIZACAO", "QUANTIDADE", "QTDE", "PROCESSSO",
                "SISTEMA DE CONTROLE", "RESUMO DO PROCESSO",
            ]
    
            self.after(0, lambda: self.lbl_status_offline.configure(
                text="Processando conteúdo extraído... (Aguarde)"
            ))
            for idx, linha in enumerate(linhas):
                if idx % 1000 == 0:
                    time.sleep(0.005)
                lin = linha.strip()
                if not lin:
                    continue
    
                # Detecta mudança de guia — reseta rastreamento de último item
                mg = padrao_guia.search(lin)
                if mg:
                    nova_guia = mg.group(1)
                    if nova_guia != guia_atual:
                        guia_atual = nova_guia
                        item_atual = ""
                        ultimo_item_guia = None
    
                # Detecta procedimento
                proc_detectado = False
                mp_item = padrao_proc_item.search(lin)
                mp_livre = None if mp_item else padrao_proc_livre.search(lin)
                mp = mp_item or mp_livre
                if mp:
                    if mp_item:
                        item_atual = mp_item.group(1).strip()
                        cod_extraido = mp_item.group(2)
                        desc_tmp = mp_item.group(3).strip()
                    else:
                        cod_extraido = mp_livre.group(1)
                        desc_tmp = mp_livre.group(2).strip()
    
                    if (
                        len(desc_tmp) > 2
                        and not any(lixo in desc_tmp for lixo in palavras_ignoradas)
                        and desc_tmp != "TOTAL"
                    ):
                        cod_encontrado = str(int(cod_extraido))
                        # padrao_proc_item (tem número de item) → sempre é procedimento.
                        # padrao_proc_livre (sem número de item) → só confirma como proc
                        # se o código estiver no mapa. Isso evita que glosas órfãs como
                        # "420FALTA RX FINAL" sejam capturadas como procedimento, já que
                        # códigos de glosa (3 dígitos, ex: 410-490) também casam no regex.
                        # Um código nunca é procedimento se já está registrado como glosa.
                        # Isso evita que glosas órfãs como "420FALTA RX FINAL" sejam
                        # engolidas pelo proc_livre, mesmo que o CSV tenha esse código.
                        e_glosa = cod_encontrado in self.mapa_glosas
                        e_proc_conhecido = (cod_encontrado in self.mapa_procedimentos) and not e_glosa
                        if mp_item or e_proc_conhecido:
                            proc_cod_atual = cod_encontrado
                            proc_desc_atual = self.mapa_procedimentos.get(cod_encontrado, desc_tmp.lower())
                            proc_detectado = True
                            # Atualiza referência do último item da guia corrente
                            ultimo_item_guia = {
                                "guia": guia_atual,
                                "proc_cod": proc_cod_atual,
                                "proc_desc": proc_desc_atual,
                                "item": str(item_atual or ""),
                                "autorizado": self._linha_tem_login_auditor(lin),
                            }
    
                # Detecta uma ou mais glosas na mesma linha, inclusive quando o PDF
                # concatena múltiplos códigos/descrições no mesmo trecho.
                glosas_linha = self._extrair_glosas_textuais_linha_segura(
                    lin,
                    permitir_orfa=not proc_detectado,
                )
                if not glosas_linha:
                    continue
    
                detalhe_pdf = self._extrair_detalhe_glosa_pdf_offline(linhas, idx)
    
                for cod_glosa_extraido, desc_glosa, glosa_orfan in glosas_linha:
                    cod_glosa = self._normalizar_codigo_glosa(cod_glosa_extraido)
                    desc_glosa = (desc_glosa or "").strip()
    
                    glosa_autorizada = self._linha_tem_login_auditor(lin)
                    if (not proc_detectado or glosa_orfan) and ultimo_item_guia and ultimo_item_guia["guia"] == guia_atual:
                        glosa_autorizada = glosa_autorizada or bool(ultimo_item_guia.get("autorizado"))
    
                    if glosa_autorizada:
                        continue
                    if cod_glosa in GLOSAS_IGNORAR:
                        continue
    
                    cod_glosa, motivo_limpo = self._resolver_glosa(cod_glosa, desc_glosa, detalhe_pdf)
    
                    # Glosa automática (≤ 2 dígitos ou começa com 0)
                    if len(cod_glosa) <= 2 or cod_glosa.startswith('0'):
                        chave_auto = (guia_atual, cod_glosa)
                        if chave_auto not in vistos_auto:
                            self.glosas_auto_offline.append({
                                'cod': cod_glosa,
                                'guia': guia_atual,
                                'motivo': motivo_limpo
                            })
                            vistos_auto.add(chave_auto)
                        continue
    
                    # Glosa sem procedimento na linha (ou linha órfã detectada)
                    # → associa ao último item da guia corrente.
                    if (not proc_detectado or glosa_orfan) and ultimo_item_guia and ultimo_item_guia["guia"] == guia_atual:
                        ref_proc = ultimo_item_guia["proc_cod"]
                        ref_desc = ultimo_item_guia["proc_desc"]
                        ref_item = ultimo_item_guia["item"]
                    else:
                        ref_proc = proc_cod_atual
                        ref_desc = proc_desc_atual
                        ref_item = str(item_atual or "")
    
                    if guia_atual == "N/A":
                        continue
    
                    chave = (guia_atual, cod_glosa, ref_proc, ref_item)
                    if chave not in vistos_detalhe:
                        self.dados_extraidos_offline.append({
                            'cod': cod_glosa,
                            'motivo_limpo': motivo_limpo,
                            'proc_cod': ref_proc,
                            'proc_desc': ref_desc,
                            'guia': guia_atual,
                            'item': ref_item,
                            'justificativa': "",
                            'detalhe_pdf': detalhe_pdf,
                        })
                        vistos_detalhe.add(chave)
    
            self.after(0, self._concluir_processamento_offline)
    
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.after(0, lambda: self._mostrar_progresso_offline(False))
            self.after(0, lambda: self.lbl_status_offline.configure(
                text="Erro na leitura do PDF.",
                text_color="#E74C3C"
            ))
            self.after(0, lambda: self.btn_selecionar_offline.configure(state="normal"))

    def _concluir_processamento_offline(self):
        try:
            self.verificar_riscos_offline()
        except Exception as erro:
            registrar_erro("Erro ao concluir processamento offline", erro)
            self._mostrar_progresso_offline(False)
            self.lbl_status_offline.configure(
                text=f"Erro ao concluir análise: {erro}",
                text_color=TEMA["erro"]
            )
            self.btn_selecionar_offline.configure(state="normal")

    def verificar_riscos_offline(self):
        self.itens_risco_offline = [g for g in self.dados_extraidos_offline if self._eh_glosa_critica(g.get('cod'))]
        self.itens_tecnicos_offline = [g for g in self.dados_extraidos_offline if self._eh_glosa_tecnica(g.get('cod'))]
    
        # Habilitar botões se houver glosas correspondentes
        if self.dados_extraidos_offline:
            self.btn_toggle_resumo_offline.configure(state="normal")
            self.btn_copiar_offline.configure(state="normal")
            self.btn_copiar_critico.configure(state="normal")
            self.btn_copiar_sem_critico.configure(state="normal")
    
        if self.itens_risco_offline:
            self.btn_justificar_criticas.configure(state="normal")
            self.btn_copiar_resumo_criticas.configure(state="normal")
        if self.itens_tecnicos_offline:
            self.btn_justificar_tecnicas.configure(state="normal")
    
        # Mantém o fluxo automático para críticas se o usuário ainda não tiver justificado
        # mas só faz isso se o popup já não estiver aberto.
        tem_alguma_justificativa = any(g.get('justificativa') for g in self.itens_risco_offline)
        if self.itens_risco_offline and not tem_alguma_justificativa: 
            self._mostrar_progresso_offline(False)
            self.lbl_status_offline.configure(
                text="Glosas críticas detectadas. Aguardando justificativas.",
                text_color="#E67E22"
            )
            self.abrir_popup_justificativas_offline()
        else:
            self.lbl_status_offline.configure(text="Gerando redação final...", text_color="#E67E22")
            self.gerar_redacao_final_offline()

    def abrir_popup_justificativas_offline(self):
        self.popup = ctk.CTkToplevel(self)
        self.popup.title("Justificativas - Glosas Críticas")
        self.popup.geometry("820x760")
        self.popup.grab_set()
        self._tematizar_popup(self.popup)

        # --- Cabeçalho ---
        topo = ctk.CTkFrame(self.popup, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(
            topo,
            text="Justificativas — Glosas Críticas",
            font=("Segoe UI", 20, "bold"),
            text_color=TEMA["texto_claro"]
        ).pack(side="left")
        ctk.CTkButton(
            topo, text="Cancelar", width=100, height=32,
            fg_color="transparent", hover_color=TEMA["bg_surface_3"],
            border_width=1, border_color=TEMA["borda"],
            text_color=TEMA["texto_secundario"],
            command=self.popup.destroy
        ).pack(side="right")

        # --- Painel de aplicação em lote ---
        f_lote = ctk.CTkFrame(
            self.popup, fg_color=TEMA["bg_surface"],
            corner_radius=12, border_width=1, border_color=TEMA["borda"]
        )
        f_lote.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(
            f_lote,
            text="Aplicação em lote (aplica o texto às glosas marcadas):",
            font=("Segoe UI", 12, "bold"), text_color=TEMA["texto_claro"]
        ).pack(anchor="w", pady=(10, 6), padx=12)
        f_lote_input = ctk.CTkFrame(f_lote, fg_color="transparent")
        f_lote_input.pack(fill="x", padx=12, pady=(0, 10))
        self.entry_master = ctk.CTkEntry(
            f_lote_input, placeholder_text="Ex: por repetição de imagem...",
            height=36, fg_color=TEMA["bg_surface_2"],
            border_color=TEMA["borda"], text_color=TEMA["texto_claro"]
        )
        self.entry_master.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(
            f_lote_input, text="Aplicar Selecionadas", width=160, height=36,
            fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"],
            font=("Segoe UI", 12, "bold"),
            command=self.aplicar_justificativa_lote
        ).pack(side="right")

        # --- Lista de itens ---
        scroll = ctk.CTkScrollableFrame(
            self.popup, fg_color="transparent"
        )
        scroll.pack(padx=20, pady=(0, 10), fill="both", expand=True)
        self.entradas_justificativa_offline = []

        for item in self.itens_risco_offline:
            card = ctk.CTkFrame(
                scroll, fg_color=TEMA["bg_surface"],
                corner_radius=12, border_width=1, border_color=TEMA["borda"]
            )
            card.pack(fill="x", pady=6)
            card.grid_columnconfigure(1, weight=1)

            var_check = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(
                card, text="", variable=var_check, width=24
            ).grid(row=0, column=0, rowspan=3, padx=(12, 8), pady=12, sticky="ns")

            info = (
                f"Guia: {item['guia']} | Proc: {item['proc_cod']} - {item['proc_desc']}\n"
                f"Glosa: [{item['cod']}] {item['motivo_limpo'].upper()}"
            )
            ctk.CTkLabel(
                card, text=info, justify="left",
                font=("Segoe UI", 12, "bold"), text_color=TEMA["texto_claro"]
            ).grid(row=0, column=1, sticky="w", padx=(0, 12), pady=(12, 4))

            textos_prontos = self._obter_textos_prontos(item['cod'])
            entry = ctk.CTkEntry(
                card, placeholder_text="Ex: devido a imagem divergente...",
                fg_color=TEMA["bg_surface_2"],
                border_color=TEMA["borda"], text_color=TEMA["texto_claro"],
                height=34
            )
            if item.get('justificativa'):
                entry.insert(0, item['justificativa'].replace("pois ", "", 1))

            if textos_prontos:
                valores = ["Frases Sugeridas..."] + [txt['texto'] for txt in textos_prontos]
                def f_selecionar(val, e=entry):
                    if val != "Frases Sugeridas...":
                        e.delete(0, 'end'); e.insert(0, val)
                ctk.CTkOptionMenu(
                    card, values=valores, height=30,
                    fg_color=TEMA["bg_surface_2"],
                    button_color=TEMA["azul_primario"],
                    button_hover_color=TEMA["azul_hover"],
                    text_color=TEMA["texto_claro"],
                    dynamic_resizing=False, command=f_selecionar
                ).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 4))
                entry.grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=(0, 12))
            else:
                entry.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 12))

            self.entradas_justificativa_offline.append(
                {'item': item, 'entry': entry, 'check': var_check}
            )

        # --- Botão salvar ---
        ctk.CTkButton(
            self.popup, text="Salvar e Redigir",
            command=self.salvar_riscos_e_gerar_offline,
            height=46, font=("Segoe UI", 13, "bold"),
            fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"]
        ).pack(pady=(0, 16), padx=20, fill="x")

    def salvar_tecnicos_e_gerar_offline(self):
        for obj in self.entradas_justificativa_tecnica:
            item = obj['item']
            just = obj['entry'].get().strip()
            if just:
                if not just.lower().startswith(("pois", "devido", "por ", "justificado", "como ", "uma vez que", "já que", "visto que", "em razão")):
                    just = f"pois {just}"
                item['justificativa'] = just
            else: item['justificativa'] = ""
        self.lbl_status_offline.configure(text="Gerando redação final...", text_color="#E67E22")
        self.popup_tecnico.destroy()
        self.gerar_redacao_final_offline()

    def salvar_riscos_e_gerar_offline(self):
        for obj in self.entradas_justificativa_offline:
            item = obj['item']
            just = obj['entry'].get().strip()
            if just:
                if not just.lower().startswith(("pois", "devido", "por ", "justificado", "como ", "uma vez que", "já que", "visto que", "em razão")):
                    just = f"pois {just}"
                item['justificativa'] = just
            else: item['justificativa'] = ""
        self.lbl_status_offline.configure(text="Gerando redação final...", text_color="#E67E22")
        self.popup.destroy()
        self.gerar_redacao_final_offline()

    def _linha_pode_ser_detalhe_glosa_offline(self, linha):
        lin = (linha or "").strip().upper()
        if not lin:
            return False
        if self._linha_eh_ruido_cabecalho_glosa_offline(linha):
            return False
        # Filtra linhas que contêm número de guia (7-9 dígitos) — cobre todos os formatos
        if re.search(r'\b(\d{7,9})\b', lin):
            return False
        if lin.startswith((
            "GUIA ",
            "IT PROCEDIMENTO",
            "HAPVIDA ",
            "SISTEMA DE CONTROLE",
            "RESUMO DO PROCESSO",
            "PROCESSSO",
            "ROD",
            "ESTATISTICA",
            "TOTALIZACAO",
            "QTDE",
            "VL.",
            "PAGINA",
            "TOTAL ",
        )):
            return False
        if re.match(r'^\d{1,3}\s+\d{3,4}\s*[A-ZÁÉÍÓÚÂÊÔÃÕÇ]', lin):
            return False
        if re.match(r'^\d{1,3}\d{3,4}[A-ZÁÉÍÓÚÂÊÔÃÕÇ]', lin):
            return False
        return True

    def _linha_eh_ruido_cabecalho_glosa_offline(self, linha):
        lin = re.sub(r'\s+', ' ', (linha or '').strip()).upper()
        if not lin:
            return False
        if lin in {"71", "72"}:
            return True
        if "VALOR TOTAL DIFERE VALOR APRESENTADO" in lin:
            return True
        if "VALOR APRESENTADO ACIMA DO TETO" in lin:
            return True
        return False

    def _linha_eh_ponte_detalhe_glosa_offline(self, linha):
        lin = re.sub(r'\s+', ' ', (linha or '').strip()).upper()
        if not lin:
            return True
        if set(lin) <= {'-'}:
            return True
        if lin.startswith((
            "HAPVIDA ",
            "SISTEMA DE CONTROLE",
            "RESUMO DO PROCESSO",
            "DATA ",
            "PAGINA",
            "FILIAL:",
            "PROCESSO:",
            "ROD",
            "GUIA SENHA CÓDIGO USUÁRIO",
            "GUIA SENHA CODIGO USUARIO",
            "IT PROCEDIMENTO",
            "SUB GLOSA",
            "GUIA ",
        )):
            return True
        if re.search(r'\b(2[56789]\d{6})\b', lin) and '3-ERRO' in lin:
            return True
        return False

    def _extrair_detalhe_glosa_pdf_offline(self, linhas, indice_glosa, max_linhas=2):
        detalhes = []
        itens_pulados = 0
        for deslocamento in range(1, 25):
            indice = indice_glosa + deslocamento
            if indice >= len(linhas):
                break
            proxima = (linhas[indice] or "").strip()
            if self._linha_eh_ponte_detalhe_glosa_offline(proxima):
                continue
            if self._linha_eh_ruido_cabecalho_glosa_offline(proxima):
                break
            if not detalhes and itens_pulados < 1 and self._linha_parece_item_pdf_segura(proxima):
                itens_pulados += 1
                continue
            if not self._linha_pode_ser_detalhe_glosa_offline(proxima):
                break
            detalhes.append(proxima)
            if len(detalhes) >= max(2, max_linhas):
                break
        return " ".join(detalhes).strip()

    def _linha_inicia_nova_glosa_offline(self, linha):
        texto = re.sub(r'\s+', ' ', (linha or '').strip())
        if not texto:
            return False
        if self._linha_parece_item_pdf_segura(texto):
            return False
    
        codigo_fragmentado, _ = self._identificar_cabecalho_glosa_fragmentada(texto)
        if codigo_fragmentado:
            return True
    
        codigo_linha, _, glosa_orfan = self._extrair_glosa_textual_linha_segura(texto, permitir_orfa=True)
        return bool(codigo_linha and glosa_orfan)

    def _linha_pode_ser_detalhe_glosa_offline(self, linha):
        lin = (linha or "").strip().upper()
        if not lin:
            return False
        if self._linha_eh_ruido_cabecalho_glosa_offline(linha):
            return False
        if self._linha_inicia_nova_glosa_offline(linha):
            return False
        if re.search(r'\b(\d{7,9})\b', lin):
            return False
        if lin.startswith((
            "GUIA ",
            "IT PROCEDIMENTO",
            "HAPVIDA ",
            "SISTEMA DE CONTROLE",
            "RESUMO DO PROCESSO",
            "PROCESSSO",
            "ROD",
            "ESTATISTICA",
            "TOTALIZACAO",
            "QTDE",
            "VL.",
            "PAGINA",
            "TOTAL ",
        )):
            return False
        if re.match(r'^\d{1,3}\s+\d{3,4}\s*[A-ZÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡]', lin):
            return False
        if re.match(r'^\d{1,3}\d{3,4}[A-ZÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡]', lin):
            return False
        return True

    def _extrair_detalhe_glosa_pdf_offline(self, linhas, indice_glosa, max_linhas=2):
        detalhes = []
        itens_pulados = 0
        for deslocamento in range(1, 25):
            indice = indice_glosa + deslocamento
            if indice >= len(linhas):
                break
            proxima = (linhas[indice] or "").strip()
            if self._linha_eh_ponte_detalhe_glosa_offline(proxima):
                continue
            if self._linha_eh_ruido_cabecalho_glosa_offline(proxima):
                break
            if self._linha_inicia_nova_glosa_offline(proxima):
                break
            if not detalhes and itens_pulados < 1 and self._linha_parece_item_pdf_segura(proxima):
                itens_pulados += 1
                continue
            if not self._linha_pode_ser_detalhe_glosa_offline(proxima):
                break
            detalhes.append(proxima)
            if len(detalhes) >= max(2, max_linhas):
                break
        return " ".join(detalhes).strip()


    def _montar_frase_grupo_reincidente_offline(self, proc, motivo, justificativa, codigo_glosa, info):
        guias_unicas = sorted({g for g in info["guias"] if g})
        qtd_guias = len(guias_unicas)
        qtd_ocorrencias = len(info.get("ocorrencias_ids", set())) or info["ocorrencias"]
        lista_guias = self._formatar_lista_guias(guias_unicas)
        sufixo_glosa = self._formatar_sufixo_glosa_offline([codigo_glosa])
        semente = f"{proc}{motivo}{codigo_glosa}"
    
        if qtd_guias > 1:
            templates = [
                f"{motivo} em {proc}, com ocorrência em {qtd_guias} guias ({lista_guias}){sufixo_glosa}",
                f"{motivo} no {proc}, verificado em {qtd_guias} guias ({lista_guias}){sufixo_glosa}",
                f"{motivo} em {proc}, presente nas guias {lista_guias}{sufixo_glosa}",
                f"{motivo} em {proc}, reincidente em {qtd_guias} guias ({lista_guias}){sufixo_glosa}",
            ]
            frase = self._variar_template(templates, semente)
        elif qtd_ocorrencias > 1 and lista_guias:
            templates = [
                f"{motivo} em {proc}, repetido em {qtd_ocorrencias} procedimentos na guia {lista_guias}{sufixo_glosa}",
                f"{motivo} em {proc}, identificado {qtd_ocorrencias} vezes na guia {lista_guias}{sufixo_glosa}",
                f"{motivo} no {proc} em {qtd_ocorrencias} oportunidades na guia {lista_guias}{sufixo_glosa}",
            ]
            frase = self._variar_template(templates, semente)
        elif lista_guias:
            templates = [
                f"{motivo} em {proc}, na guia {lista_guias}{sufixo_glosa}",
                f"{motivo} no {proc} (guia {lista_guias}){sufixo_glosa}",
                f"{motivo} em {proc} — guia {lista_guias}{sufixo_glosa}",
            ]
            frase = self._variar_template(templates, semente)
        else:
            frase = f"{motivo} em {proc}{sufixo_glosa}"
    
        if justificativa:
            frase += f", {justificativa}"
        return frase

    def _montar_frase_guia_offline(self, guia, ocorrencias):
        # --- Prob.6: Agrupar procs com mesmo motivo+glosa numa única frase ---
        # Primeiro agrupa por (motivo, codigo_glosa, justificativa): lista de procs
        por_motivo_glosa = {}
        for ocorrencia in ocorrencias:
            chave_mg = (ocorrencia["motivo"], ocorrencia["codigo_glosa"], ocorrencia["justificativa"])
            por_motivo_glosa.setdefault(chave_mg, []).append(ocorrencia["proc"])
    
        # Constrói um conjunto de ocorrências normalizadas: (proc_canônico, motivos_unidos, glosas_unidas, justificativa)
        # Para cada proc, agrupa os motivos que tem múltiplos glosas no mesmo proc
        por_procedimento = {}
        for ocorrencia in ocorrencias:
            chave_proc = (ocorrencia["proc"], ocorrencia["justificativa"])
            por_procedimento.setdefault(chave_proc, []).append(ocorrencia)
    
        partes_guia = []
        procs_ja_incluidos = set()  # evita duplicar procs que foram fundidos via motivo+glosa
    
        # Fase 1: motivos que aparecem em múltiplos procs → funde em "motivo (glosa X) em proc1 e proc2"
        motivos_multiplos_proc = {}
        for (motivo, cod, just), procs_lista in por_motivo_glosa.items():
            procs_unicos = list(dict.fromkeys(procs_lista))  # preserva ordem, remove dups
            if len(procs_unicos) > 1:
                chave = (motivo, cod, just)
                motivos_multiplos_proc[chave] = procs_unicos
    
        for (motivo, cod, just), procs_unicos in sorted(motivos_multiplos_proc.items(), key=lambda x: x[0][0]):
            sufixo = self._formatar_sufixo_glosa_offline([cod])
            lista_procs = self._juntar_lista_natural(procs_unicos)
            bloco = f"{motivo}{sufixo} em {lista_procs}"
            if just:
                bloco += f", {just}"
            partes_guia.append(bloco)
            for p in procs_unicos:
                procs_ja_incluidos.add((p, just))
    
        # Fase 2: procs restantes (motivo único por proc, ou proc não fundido)
        def _ordem_motivo(it):
            m = it["motivo"].lower()
            if "inicial" in m: return (0, it["codigo_glosa"], m)
            if "final" in m:   return (1, it["codigo_glosa"], m)
            return (2, it["codigo_glosa"], m)
    
        for (proc, justificativa), itens_proc in sorted(por_procedimento.items(), key=lambda item: item[0][0]):
            if (proc, justificativa) in procs_ja_incluidos:
                continue
            # --- Prob.1+3: sufixo único ao final do bloco proc quando há múltiplos motivos ---
            codigos_no_proc = [it["codigo_glosa"] for it in itens_proc]
            motivos_no_proc = [it["motivo"] for it in sorted(itens_proc, key=_ordem_motivo)]
            if len(set(codigos_no_proc)) > 1:
                # Múltiplos códigos: cada motivo mantém seu sufixo individual
                descricoes = [f'{it["motivo"]}{self._formatar_sufixo_glosa_offline([it["codigo_glosa"]])}'
                              for it in sorted(itens_proc, key=_ordem_motivo)]
            else:
                # Mesmo código: sufixo único no final
                descricoes = [it["motivo"] for it in sorted(itens_proc, key=_ordem_motivo)]
                sufixo_unico = self._formatar_sufixo_glosa_offline(codigos_no_proc)
                bloco_proc = f"{self._juntar_lista_natural(descricoes)}{sufixo_unico} em {proc}"
                if justificativa:
                    bloco_proc += f", {justificativa}"
                partes_guia.append(bloco_proc)
                continue
            bloco_proc = f"{self._juntar_lista_natural(descricoes)} em {proc}"
            if justificativa:
                bloco_proc += f", {justificativa}"
            partes_guia.append(bloco_proc)
    
        if not partes_guia:
            return ""
    
        # Conector inteligente: analisa o motivo principal e adapta o verbo
        motivo_principal = (ocorrencias[0]["motivo"] if ocorrencias else "").strip()
        conector = self._classificar_conector_glosa(motivo_principal)
        return f"na guia {guia}, {conector}" + "; ".join(partes_guia)

    def _montar_bloco_pontual_offline(self, pontuais_por_guia, houve_reincidencia=False):
        blocos = []
        for guia, ocorrencias in sorted(pontuais_por_guia.items(), key=lambda item: item[0]):
            frase_guia = self._montar_frase_guia_offline(guia, ocorrencias)
            if frase_guia:
                blocos.append(frase_guia)
    
        if not blocos:
            return ""
    
        semente = "".join(sorted(pontuais_por_guia.keys()))
        if houve_reincidencia:
            conectores = [
                "Além disso, ",
                "Adicionalmente, ",
                "Também foram identificadas ocorrências: ",
                "Ainda, ",
            ]
            conector = self._variar_template(conectores, semente)
            primeiro, *resto = blocos
            primeiro = primeiro[0].upper() + primeiro[1:]
            return conector + ". ".join([primeiro] + resto) + "."
        else:
            # --- Prob.3: prefixo contextual quando há múltiplas guias pontuais sem reincidentes ---
            blocos_cap = [b[0].upper() + b[1:] for b in blocos]
            if len(blocos_cap) > 1:
                return "Foram identificadas as seguintes ocorrências: " + ". ".join(blocos_cap) + "."
            return blocos_cap[0] + "."

    def _gerar_texto_resumido_offline_dados(self):
        dados = list(getattr(self, 'dados_extraidos_offline', []) or [])
        if not dados:
            return ""
    
        dados_sem_480 = [g for g in dados if str(g.get("cod", "")).strip() != "480"]
        if not dados_sem_480:
            return ""
    
        achados_estruturados = [self._estruturar_achado(g) for g in dados_sem_480]
        itens = self._consolidar_por_item(achados_estruturados)
        if not itens:
            return ""
    
        grupos_base = self._agrupar_por_assinatura(itens)
        ordem_base_por_item = {}
        for ordem_grupo, grupo in enumerate(grupos_base):
            for item in grupo.get("itens", []):
                ordem_base_por_item[id(item)] = ordem_grupo
    
        entradas_resumo = []
        consumidos = set()
        familias_por_guia = {}
    
        for idx, item in enumerate(itens):
            agrupamento = self._obter_agrupamento_procedimento_resumo(item.get("proc_cod"))
            if not agrupamento:
                continue
            chave = (
                item.get("guia", ""),
                agrupamento["chave"],
                item.get("justificativa", ""),
            )
            familias_por_guia.setdefault(chave, []).append((idx, item))
    
        for chave, pares in sorted(familias_por_guia.items(), key=lambda kv: min(idx for idx, _ in kv[1])):
            if len(pares) <= 1:
                continue
            itens_mesma_guia = [item for _, item in pares]
            consumidos.update(idx for idx, _ in pares)
            entradas_resumo.append({
                "ordem": min(ordem_base_por_item.get(id(item), idx) for idx, item in pares),
                "itens": itens_mesma_guia,
                "justificativa": chave[2],
            })
    
        itens_restantes = [item for idx, item in enumerate(itens) if idx not in consumidos]
        grupos_restantes = self._agrupar_por_assinatura(itens_restantes) if itens_restantes else []
        for ordem_grupo, grupo in enumerate(grupos_restantes, start=len(entradas_resumo)):
            ordem = min((ordem_base_por_item.get(id(item), ordem_grupo) for item in grupo.get("itens", [])), default=ordem_grupo)
            entradas_resumo.append({
                "ordem": ordem,
                "itens": list(grupo.get("itens", [])),
                "justificativa": grupo.get("justificativa", ""),
            })
    
        entradas_resumo.sort(key=lambda entrada: entrada["ordem"])
    
        clausulas = []
        for idx, entrada in enumerate(entradas_resumo):
            itens_entrada = entrada.get("itens", [])
            if not itens_entrada:
                continue
            codigos = []
            for item in itens_entrada:
                for achado in item.get("achados", []):
                    codigos.append(achado.get("cod"))
            prefixo = self._formatar_prefixo_glosas_resumo(codigos)
            alvo = self._renderizar_alvo_resumo_itens(itens_entrada)
            abertura = "O prestador apresentou " if idx == 0 else ""
            frase = f"{abertura}{prefixo} {alvo}"
            justificativa = entrada.get("justificativa", "")
            if justificativa:
                frase += f", {justificativa}"
            clausulas.append(frase)
    
        texto = self._juntar_clausulas_paragrafo(clausulas).strip()
        return self._processar_texto_resumido(texto) if texto else ""

    def _montar_texto_redacao_offline(self, dados_extraidos, agrupar_familias=False):
        if hasattr(self, 'btn_toggle_resumo_offline'):
            self.btn_toggle_resumo_offline.configure(text="Resumo", fg_color="#203551", hover_color="#1A2A40")
    
        guias_480 = set()
        dados_sem_480 = []
        for g in dados_extraidos:
            if str(g.get("cod", "")).strip() == "480":
                if g.get("guia"):
                    guias_480.add(g["guia"])
            else:
                dados_sem_480.append(g)
    
        if not dados_sem_480 and not guias_480 and not getattr(self, "glosas_auto_offline", []):
            return "Nenhuma glosa aplicável encontrada no documento."
    
        clausulas_texto = []
        if dados_sem_480:
            achados_estruturados = [self._estruturar_achado(g) for g in dados_sem_480]
            itens = self._consolidar_por_item(achados_estruturados)
            grupos = self._agrupar_por_assinatura(itens)
            formulacoes_usadas = []
            clausulas_texto.extend(
                self._coletar_frases_grupos(
                    grupos,
                    formulacoes_usadas,
                    agrupar_familias=agrupar_familias,
                )
            )
    
        if guias_480:
            clausulas_texto.append(
                f"Houve glosa 480 por falta de documentação ou ausência de envio da guia "
                f"nas guias {self._formatar_lista_guias(sorted(guias_480))}"
            )
    
        texto_final = self._juntar_clausulas_paragrafo(clausulas_texto).strip()
        return texto_final or "Nenhuma glosa aplicável encontrada no documento."

    def _gerar_resumo_critico_offline(self):
        dados_criticos = [g for g in self.dados_extraidos_offline if self._eh_glosa_critica(g.get("cod"))]
        if not dados_criticos:
            return ""
        return self._montar_texto_redacao_offline(dados_criticos)

    def gerar_redacao_final_offline(self):
        """Pipeline de 4 camadas para geração do texto de auditoria e blocos de apoio."""
        if not hasattr(self, 'resumo_ativo_offline'):
            self.resumo_ativo_offline = False
    
        # Reseta estado visual do resumo ao gerar novo relatório, mas mantém lógica interna se necessário
        self.resumo_ativo_offline = False
        if hasattr(self, 'btn_toggle_resumo_offline'):
            self.btn_toggle_resumo_offline.configure(text="Resumo", fg_color="#203551", hover_color="#1A2A40")
    
        guias_480 = set()
        dados_sem_480 = []
        for g in self.dados_extraidos_offline:
            if str(g.get("cod", "")).strip() == "480":
                if g.get("guia"):
                    guias_480.add(g["guia"])
            else:
                dados_sem_480.append(g)
    
        if not dados_sem_480 and not guias_480:
            texto_final = "Nenhuma glosa aplicável encontrada no documento."
        else:
            achados_estruturados = [self._estruturar_achado(g) for g in dados_sem_480]
            itens = self._consolidar_por_item(achados_estruturados)
            grupos = self._agrupar_por_assinatura(itens)
            clausulas_texto = []
            formulacoes_usadas = []
            clausulas_texto.extend(self._coletar_frases_grupos(grupos, formulacoes_usadas))
    
            if guias_480:
                clausulas_texto.append(
                    f"Houve glosa 480 por falta de documentação ou ausência de envio da guia "
                    f"nas guias {self._formatar_lista_guias(sorted(guias_480))}"
                )
            texto_final = self._juntar_clausulas_paragrafo(clausulas_texto)
    
        # Salva o texto base para permitir o toggle de resumo
        self.texto_completo_offline = texto_final
    
        self.resumo_critico_offline = self._gerar_resumo_critico_offline()
    
        # Glosas automáticas
        texto_auto = ""
        if self.glosas_auto_offline:
            grupos_auto = {}
            for g in self.glosas_auto_offline:
                chave_auto = (g["cod"], g["motivo"].upper())
                grupos_auto.setdefault(chave_auto, []).append(g["guia"])
            linhas_auto = []
            for (cod, motivo_auto), guias_lista in sorted(grupos_auto.items(), key=lambda x: self._ordenar_codigo_glosa(x[0][0])):
                guias_str = self._formatar_lista_guias(sorted(set(guias_lista)))
                plural = "guias" if len(set(guias_lista)) > 1 else "guia"
                linhas_auto.append(f"Glosa {cod} ({motivo_auto}): {plural} {guias_str}")
            texto_auto = "O prestador apresentou as seguintes glosas automáticas:\n" + "\n".join(linhas_auto)
    
        if hasattr(self, 'btn_toggle_resumo_offline'):
            self.btn_toggle_resumo_offline.configure(text="Resumo", state="normal")
    
        self.caixa_texto_offline.delete("0.0", "end")
        self.caixa_texto_offline.insert("0.0", texto_final)
    
        self.btn_copiar_offline.configure(state="normal")
        self.btn_copiar_critico.configure(state="normal")
        self.btn_copiar_sem_critico.configure(state="normal")
        if hasattr(self, 'btn_toggle_resumo_offline'):
            self.btn_toggle_resumo_offline.configure(state="normal")
        if hasattr(self, 'btn_ranking_glosas_offline'):
            self.btn_ranking_glosas_offline.configure(state="normal")
    
        self.caixa_texto_auto.delete("0.0", "end")
        if texto_auto:
            self.caixa_texto_auto.insert("0.0", texto_auto)
        else:
            self.caixa_texto_auto.insert("0.0", "Nenhuma glosa automatica identificada no documento.")
    
        self.btn_copiar_resumo_criticas.configure(state="normal" if self.resumo_critico_offline else "disabled")
        self.lbl_status_offline.configure(text="Relatório redigido com sucesso!", text_color="#2ECC71")
        self.btn_selecionar_offline.configure(state="normal", text="Processar PDF/CSV")
        self.update_idletasks()
    
        # Salvar Histórico
        if hasattr(self, 'metadata_pdf_offline') and self.metadata_pdf_offline:
            meta = self.metadata_pdf_offline
            self._atualizar_metadados_offline(meta)
            texto_completo_para_salvar = texto_final + ("\n\n" + texto_auto if texto_auto else "")
            if "Nenhuma glosa" not in texto_final or texto_auto:
                try:
                    with conectar_sqlite(self.arq_historico_db) as conn:
                        conn.execute(
                            "INSERT INTO historico (processo, mes_ref, prestador, texto_relatorio, data_criacao) VALUES (?, ?, ?, ?, ?)",
                            (meta.get('processo', 'N/A'), meta.get('mes', 'N/A'), meta.get('prestador', 'N/A'), texto_completo_para_salvar, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                        )
                        conn.commit()
                    if hasattr(self, 'frame_historico_relatorios') and self.frame_historico_relatorios:
                        try: self.frame_historico_relatorios.carregar_historico()
                        except: pass
                except Exception as e:
                    registrar_erro("Erro ao salvar relatorio no historico", e)
    
        guias_unicas = {g.get("guia") for g in self.dados_extraidos_offline if g.get("guia")}
        total_glosas = len(self.dados_extraidos_offline) + len(self.glosas_auto_offline)
        glosas_risco = len([g for g in self.dados_extraidos_offline if self._eh_glosa_critica(g.get("cod"))])
        taxa = (glosas_risco / total_glosas * 100) if total_glosas else 0.0
        self._atualizar_kpis_offline(guias=len(guias_unicas), glosas=total_glosas, taxa=taxa)
    
        self._popular_chips_glosas(self.dados_extraidos_offline)
        self._mostrar_progresso_offline(False)
        self._atualizar_contador_offline()

    def validar_e_iniciar_offline(self, caminho):
        self.btn_copiar_offline.configure(state="disabled")
        self.btn_toggle_resumo_offline.configure(text="Resumo", state="disabled", fg_color="#203551", hover_color="#1A2A40")
        self.btn_copiar_critico.configure(state="disabled")
        self.btn_copiar_sem_critico.configure(state="disabled")
        self.btn_copiar_resumo_criticas.configure(state="disabled")
        self.btn_justificar_tecnicas.configure(state="disabled")
        self.btn_justificar_criticas.configure(state="disabled")
    
        self.ranking_glosas_offline_atual = []
        self._limpar_metadados_offline()
        if hasattr(self, "btn_ranking_glosas_offline"):
            self.btn_ranking_glosas_offline.configure(state="disabled")
        fonte_label = self._obter_fonte_offline_label(caminho)
        self.lbl_status_offline.configure(text=f"Lendo {fonte_label}...", text_color="#E67E22")
        self.btn_selecionar_offline.configure(state="disabled")
        self._mostrar_progresso_offline(True)
        target = self.processar_csv_thread_offline if self._arquivo_offline_e_csv(caminho) else self.processar_pdf_thread_offline
        self._executar_em_thread(target, caminho, on_error=self._tratar_erro_offline)

    def iniciar_selecao_manual_offline(self):
        caminho = filedialog.askopenfilename(
            title="Selecione o PDF ou CSV",
            filetypes=[("Arquivos suportados", "*.pdf;*.csv"), ("PDF", "*.pdf"), ("CSV", "*.csv")]
        )
        if caminho: self.validar_e_iniciar_offline(caminho)

    def abrir_novo_pdf_offline_acao(self):
        if hasattr(self, 'btn_selecionar_offline') and str(self.btn_selecionar_offline.cget("state")) == "disabled":
            self._mostrar_status_temporario("Conclua o processamento atual antes de abrir outro arquivo.", cor="#E67E22")
            return
        self.iniciar_selecao_manual_offline()

    def _atualizar_metadados_offline(self, meta=None):
        meta = meta or {}
        prestador = str(meta.get("prestador") or "N/A").strip() or "N/A"
        processo = str(meta.get("processo") or "N/A").strip() or "N/A"
        mes = str(meta.get("mes") or "N/A").strip() or "N/A"
        prestador_exibicao = prestador if len(prestador) <= 38 else prestador[:35] + "..."
    
        self._meta_cards_offline["prestador"].configure(
            text=f"Prestador: {prestador_exibicao}",
            text_color="#FFFFFF",
            font=("Segoe UI", 11, "bold"),
        )
        self._meta_cards_offline["processo"].configure(
            text=f"Processo: {processo}",
            text_color="#FFFFFF",
            font=("Segoe UI", 11, "bold"),
        )
        self._meta_cards_offline["mes"].configure(
            text=f"Mês: {mes}",
            text_color="#FFFFFF",
            font=("Segoe UI", 11, "bold"),
        )
    
        if not self.frame_meta_offline.winfo_ismapped():
            self.frame_meta_offline.pack(fill="x", pady=(0, 6), before=self.caixa_texto_offline)

    def _limpar_metadados_offline(self):
        if hasattr(self, "_meta_cards_offline"):
            self._meta_cards_offline["prestador"].configure(text="Prestador: -", text_color="#FFFFFF", font=("Segoe UI", 11, "bold"))
            self._meta_cards_offline["processo"].configure(text="Processo: -", text_color="#FFFFFF", font=("Segoe UI", 11, "bold"))
            self._meta_cards_offline["mes"].configure(text="Mês: -", text_color="#FFFFFF", font=("Segoe UI", 11, "bold"))
        if hasattr(self, "frame_meta_offline") and self.frame_meta_offline.winfo_ismapped():
            self.frame_meta_offline.pack_forget()

    def abrir_popup_ranking_glosas_offline(self):
        popup = ctk.CTkToplevel(self)
        popup.title("Ranking de Glosas")
        popup.geometry("620x560")
        popup.attributes("-topmost", True)
        popup.grab_set()
        self._tematizar_popup(popup)
    
        container = ctk.CTkFrame(popup, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
    
        topo = ctk.CTkFrame(container, fg_color="transparent")
        topo.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            topo,
            text="Ranking de Glosas",
            font=("Segoe UI", 22, "bold"),
            text_color=TEMA["texto_claro"],
        ).pack(side="left")
        ctk.CTkButton(
            topo,
            text="Fechar",
            width=90,
            height=34,
            command=popup.destroy,
            fg_color=TEMA["bg_surface_3"],
            hover_color=TEMA["azul_sidebar_hover"],
        ).pack(side="right")
    
        ctk.CTkLabel(
            container,
            text="Resumo das glosas detectadas no arquivo processado.",
            font=("Segoe UI", 12),
            text_color=TEMA["texto_secundario"],
        ).pack(anchor="w", pady=(0, 10))
    
        scroll = ctk.CTkScrollableFrame(container, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
    
        if not self.ranking_glosas_offline_atual:
            ctk.CTkLabel(
                scroll,
                text="Nenhuma glosa aplicada identificada.",
                font=("Segoe UI", 13),
                text_color=TEMA["texto_muted"],
            ).pack(pady=30)
            return
    
        for item in self.ranking_glosas_offline_atual:
            eh_critica = item["categoria"] == "CRITICA"
            cor_rotulo = "#FF9B8E" if eh_critica else "#7FB3FF"
            card = ctk.CTkFrame(
                scroll,
                fg_color=TEMA["bg_surface_2"],
                corner_radius=14,
                border_width=1,
                border_color="#E74C3C" if eh_critica else TEMA["borda"],
            )
            card.pack(fill="x", pady=5, padx=4)
            ctk.CTkLabel(
                card,
                text=f"TOP {item['posicao']}",
                font=("Segoe UI", 10, "bold"),
                text_color=cor_rotulo,
            ).pack(anchor="w", padx=12, pady=(10, 2))
            ctk.CTkLabel(
                card,
                text=f"Glosa {item['codigo']} - {item['descricao']}",
                justify="left",
                wraplength=520,
                font=("Segoe UI", 12, "bold"),
                text_color=TEMA["texto_claro"],
            ).pack(anchor="w", padx=12)
            ctk.CTkLabel(
                card,
                text=f"{item['quantidade']} ocorrencia(s) - {item['percentual']:.1f}%",
                font=("Segoe UI", 11),
                text_color=TEMA["texto_secundario"],
            ).pack(anchor="w", padx=12, pady=(4, 2))
            ctk.CTkLabel(
                card,
                text=item["categoria"],
                font=("Segoe UI", 11),
                text_color=cor_rotulo,
            ).pack(anchor="w", padx=12, pady=(0, 10))



    def abrir_popup_justificativas_tecnicas(self):
        if not hasattr(self, 'itens_tecnicos_offline') or not self.itens_tecnicos_offline:
            return

        self.popup_tecnico = ctk.CTkToplevel(self)
        self.popup_tecnico.title("Justificativas - Glosas Técnicas")
        self.popup_tecnico.geometry("820x760")
        self.popup_tecnico.grab_set()
        self._tematizar_popup(self.popup_tecnico)

        # --- Cabeçalho ---
        topo = ctk.CTkFrame(self.popup_tecnico, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(
            topo,
            text="Justificativas — Glosas Técnicas",
            font=("Segoe UI", 20, "bold"),
            text_color=TEMA["texto_claro"]
        ).pack(side="left")
        ctk.CTkButton(
            topo, text="Cancelar", width=100, height=32,
            fg_color="transparent", hover_color=TEMA["bg_surface_3"],
            border_width=1, border_color=TEMA["borda"],
            text_color=TEMA["texto_secundario"],
            command=self.popup_tecnico.destroy
        ).pack(side="right")

        # --- Painel de aplicação em lote ---
        f_lote = ctk.CTkFrame(
            self.popup_tecnico, fg_color=TEMA["bg_surface"],
            corner_radius=12, border_width=1, border_color=TEMA["borda"]
        )
        f_lote.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(
            f_lote,
            text="Aplicação em lote (técnica):",
            font=("Segoe UI", 12, "bold"), text_color=TEMA["texto_claro"]
        ).pack(anchor="w", pady=(10, 6), padx=12)
        f_lote_input = ctk.CTkFrame(f_lote, fg_color="transparent")
        f_lote_input.pack(fill="x", padx=12, pady=(0, 10))
        self.entry_master_tecnico = ctk.CTkEntry(
            f_lote_input, placeholder_text="Ex: execução técnica inadequada...",
            height=36, fg_color=TEMA["bg_surface_2"],
            border_color=TEMA["borda"], text_color=TEMA["texto_claro"]
        )
        self.entry_master_tecnico.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(
            f_lote_input, text="Aplicar Selecionadas", width=160, height=36,
            fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"],
            font=("Segoe UI", 12, "bold"),
            command=self.aplicar_justificativa_lote_tecnico
        ).pack(side="right")

        # --- Lista de itens ---
        scroll = ctk.CTkScrollableFrame(self.popup_tecnico, fg_color="transparent")
        scroll.pack(padx=20, pady=(0, 10), fill="both", expand=True)
        self.entradas_justificativa_tecnica = []

        for item in self.itens_tecnicos_offline:
            card = ctk.CTkFrame(
                scroll, fg_color=TEMA["bg_surface"],
                corner_radius=12, border_width=1, border_color=TEMA["borda"]
            )
            card.pack(fill="x", pady=6)
            card.grid_columnconfigure(1, weight=1)

            var_check = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(
                card, text="", variable=var_check, width=24
            ).grid(row=0, column=0, rowspan=3, padx=(12, 8), pady=12, sticky="ns")

            info = (
                f"Guia: {item['guia']} | Proc: {item['proc_cod']} - {item['proc_desc']}\n"
                f"Glosa: [{item['cod']}] {item['motivo_limpo'].upper()}"
            )
            ctk.CTkLabel(
                card, text=info, justify="left",
                font=("Segoe UI", 12, "bold"), text_color=TEMA["texto_claro"]
            ).grid(row=0, column=1, sticky="w", padx=(0, 12), pady=(12, 4))

            textos_prontos = self._obter_textos_prontos(item['cod'])
            entry = ctk.CTkEntry(
                card, placeholder_text="Ex: falha na execução...",
                fg_color=TEMA["bg_surface_2"],
                border_color=TEMA["borda"], text_color=TEMA["texto_claro"],
                height=34
            )
            if item.get('justificativa'):
                entry.insert(0, item['justificativa'].replace("pois ", "", 1))

            if textos_prontos:
                valores = ["Frases Sugeridas..."] + [txt['texto'] for txt in textos_prontos]
                def f_selecionar(val, e=entry):
                    if val != "Frases Sugeridas...":
                        e.delete(0, 'end'); e.insert(0, val)
                ctk.CTkOptionMenu(
                    card, values=valores, height=30,
                    fg_color=TEMA["bg_surface_2"],
                    button_color=TEMA["azul_primario"],
                    button_hover_color=TEMA["azul_hover"],
                    text_color=TEMA["texto_claro"],
                    dynamic_resizing=False, command=f_selecionar
                ).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 4))
                entry.grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=(0, 12))
            else:
                entry.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 12))

            self.entradas_justificativa_tecnica.append(
                {'item': item, 'entry': entry, 'check': var_check}
            )

        # --- Botão salvar ---
        ctk.CTkButton(
            self.popup_tecnico, text="Salvar Justificativas Técnicas",
            command=self.salvar_tecnicos_e_gerar_offline,
            height=46, font=("Segoe UI", 13, "bold"),
            fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"]
        ).pack(pady=(0, 16), padx=20, fill="x")

    def aplicar_justificativa_lote_tecnico(self):
        texto_lote = self.entry_master_tecnico.get().strip()
        if not texto_lote: return
        for obj in self.entradas_justificativa_tecnica:
            if obj['check'].get():
                obj['entry'].delete(0, 'end')
                obj['entry'].insert(0, texto_lote)

    def aplicar_justificativa_lote(self):
        texto_lote = self.entry_master.get().strip()
        if not texto_lote: return
        for obj in self.entradas_justificativa_offline:
            if obj['check'].get():
                obj['entry'].delete(0, 'end')
                obj['entry'].insert(0, texto_lote)

    # ------------------------------------------------------------------
    # Métodos de apoio que precisam viver no frame (usam widgets locais)
    # ------------------------------------------------------------------

    def _tematizar_popup(self, popup):
        """Delega para o app_master — evita depender de imports não disponíveis aqui."""
        if hasattr(self.app_master, '_tematizar_popup'):
            self.app_master._tematizar_popup(popup)
        else:
            try:
                popup.configure(fg_color="#0D1B2A")
            except Exception:
                pass

    def _popular_chips_glosas(self, dados_extraidos):
        """Calcula o ranking de glosas no frame offline (Sinalizadores visuais removidos)."""
        self.ranking_glosas_offline_atual = []

        glosas_vistas = {}
        ranking = {}
        for g in dados_extraidos:
            cod = g.get("cod", "")
            motivo = g.get("motivo_limpo", "")
            if not cod:
                continue
            if cod not in glosas_vistas:
                glosas_vistas[cod] = motivo
            if cod not in ranking:
                ranking[cod] = {"descricao": motivo, "qtd": 0}
            ranking[cod]["qtd"] += 1

        if not glosas_vistas:
            if hasattr(self, "btn_ranking_glosas_offline"):
                self.btn_ranking_glosas_offline.configure(state="disabled")
            return

        ranking_ordenado = sorted(
            ranking.items(),
            key=lambda item: (-item[1]["qtd"], 0 if self._eh_glosa_critica(item[0]) else 1, self._ordenar_codigo_glosa(item[0])),
        )
        total_glosas = sum(item["qtd"] for item in ranking.values())

        for pos, (codigo, dados) in enumerate(ranking_ordenado, start=1):
            pct = (dados["qtd"] / total_glosas * 100.0) if total_glosas else 0.0
            eh_critica = self._eh_glosa_critica(codigo)
            self.ranking_glosas_offline_atual.append(
                {
                    "posicao": pos,
                    "codigo": codigo,
                    "descricao": dados["descricao"],
                    "quantidade": dados["qtd"],
                    "percentual": pct,
                    "categoria": "CRITICA" if eh_critica else "GLOSA APLICADA",
                }
            )

        if hasattr(self, "btn_ranking_glosas_offline"):
            self.btn_ranking_glosas_offline.configure(
                state="normal" if self.ranking_glosas_offline_atual else "disabled"
            )
