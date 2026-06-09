import os
import re
import io
from tkinter import filedialog
import customtkinter as ctk
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill

from core.settings import TEMA

class FrameAnaliseRisco(ctk.CTkFrame):
    def __init__(self, master, app_master):
        super().__init__(master, fg_color="transparent")
        self.app_master = app_master
        
        self.ranking_risco_atual = []
        self.resumo_risco_atual = ''
        self.prestador_risco_atual = ''
        
        self.frame_analise_inicio = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_analise_relatorio = ctk.CTkFrame(self, fg_color="transparent")
        
        self.setup_tela_analise_inicio()
        self.setup_tela_analise_relatorio()
        
        # Start with inicio
        self.frame_analise_inicio.pack(fill='both', expand=True)

    def exibir_tela_conteudo(self, frame_alvo):
        for frame in (self.frame_analise_inicio, self.frame_analise_relatorio):
            if frame.winfo_ismapped():
                frame.pack_forget()
        frame_alvo.pack(fill='both', expand=True)

    def _criar_card_metrica(self, master, titulo, valor):
        card = ctk.CTkFrame(master, corner_radius=16, fg_color=TEMA['bg_surface'], border_width=1, border_color=TEMA['borda'])
        lbl_titulo = ctk.CTkLabel(card, text=titulo, font=('Segoe UI', 11, 'bold'), text_color=TEMA['texto_secundario'])
        lbl_titulo.pack(anchor='w', padx=14, pady=(12, 4))
        lbl_valor = ctk.CTkLabel(card, text=valor, font=('Segoe UI', 20, 'bold'), text_color=TEMA['texto_claro'], justify='left')
        lbl_valor.pack(anchor='w', padx=14, pady=(0, 12))
        card.lbl_valor = lbl_valor
        return card

    def setup_tela_analise_inicio(self):
        wrapper = ctk.CTkFrame(self.frame_analise_inicio, fg_color='transparent')
        wrapper.pack(fill='both', expand=True, padx=20, pady=20)
        header = ctk.CTkFrame(wrapper, fg_color='transparent')
        header.pack(fill='x', pady=(0, 16))
        ctk.CTkLabel(header, text='Analise de Risco Consolidada', font=('Segoe UI', 28, 'bold'), text_color=TEMA['texto_claro']).pack(anchor='w')
        ctk.CTkLabel(header, text='Selecione um ou mais PDFs de glosas do mesmo prestador para consolidar o risco por mes.', font=('Segoe UI', 14), text_color=TEMA['texto_secundario']).pack(anchor='w', pady=(4, 0))
        topo = ctk.CTkFrame(wrapper, corner_radius=18, fg_color=TEMA['bg_surface_2'], border_width=1, border_color=TEMA['borda'])
        topo.pack(fill='x', pady=(0, 14))
        acoes = ctk.CTkFrame(topo, fg_color='transparent')
        acoes.pack(fill='x', padx=18, pady=16)
        self.btn_selecionar_risco = ctk.CTkButton(acoes, text='Selecionar Lote de PDFs', command=self.iniciar_selecao_manual_risco, height=44, font=('Segoe UI', 14, 'bold'), fg_color=TEMA['azul_primario'], hover_color=TEMA['azul_hover'])
        self.btn_selecionar_risco.pack(side='left')
        ctk.CTkLabel(acoes, text='Use lotes do mesmo prestador para evitar consolidacao indevida.', font=('Segoe UI', 12), text_color=TEMA['texto_secundario']).pack(side='left', padx=14)
        self.lbl_status_risco = ctk.CTkLabel(topo, text='Pronto para analisar multiplos meses.', font=('Segoe UI', 12, 'italic'), text_color=TEMA['texto_secundario'])
        self.lbl_status_risco.pack(anchor='w', padx=18, pady=(0, 14))

    def setup_tela_analise_relatorio(self):
        wrapper = ctk.CTkFrame(self.frame_analise_relatorio, fg_color='transparent')
        wrapper.pack(fill='both', expand=True, padx=20, pady=20)
        header = ctk.CTkFrame(wrapper, fg_color='transparent')
        header.pack(fill='x', pady=(0, 16))
        self.lbl_titulo_relatorio = ctk.CTkLabel(header, text='Analise de Risco Consolidada', font=('Segoe UI', 28, 'bold'), text_color=TEMA['texto_claro'])
        self.lbl_titulo_relatorio.pack(anchor='w')
        self.lbl_subtitulo_relatorio_risco = ctk.CTkLabel(header, text='Resumo consolidado de glosas por prestador.', font=('Segoe UI', 14), text_color=TEMA['texto_secundario'])
        self.lbl_subtitulo_relatorio_risco.pack(anchor='w', pady=(4, 0))
        topo = ctk.CTkFrame(wrapper, corner_radius=18, fg_color=TEMA['bg_surface_2'], border_width=1, border_color=TEMA['borda'])
        topo.pack(fill='x', pady=(0, 14))
        acoes = ctk.CTkFrame(topo, fg_color='transparent')
        acoes.pack(fill='x', padx=18, pady=16)
        self.btn_grafico_risco = ctk.CTkButton(acoes, text='Ver Grafico', height=44, font=('Segoe UI', 13, 'bold'), fg_color='#E67E22', hover_color='#D35400')
        self.btn_grafico_risco.pack(side='left')
        self.btn_copiar_risco = ctk.CTkButton(acoes, text='Copiar Texto', height=44, font=('Segoe UI', 13, 'bold'), fg_color=TEMA['azul_primario'], hover_color=TEMA['azul_hover'])
        self.btn_copiar_risco.pack(side='left', padx=10)
        self.btn_word_risco = ctk.CTkButton(acoes, text='Export Word', height=44, font=('Segoe UI', 13, 'bold'), fg_color=TEMA['bg_surface_3'], hover_color=TEMA['azul_sidebar_hover'])
        self.btn_word_risco.pack(side='left')
        self.btn_excel_risco = ctk.CTkButton(acoes, text='Export Excel', height=44, font=('Segoe UI', 13, 'bold'), fg_color='#1F8A5B', hover_color='#176746')
        self.btn_excel_risco.pack(side='left', padx=10)
        ctk.CTkButton(acoes, text='Novo Lote', command=lambda: self.exibir_tela_conteudo(self.frame_analise_inicio), height=44, font=('Segoe UI', 13, 'bold'), fg_color='#7F8C8D', hover_color='#95A5A6').pack(side='left')
        badges = ctk.CTkFrame(topo, fg_color='transparent')
        badges.pack(fill='x', padx=18, pady=(0, 14))
        self.lbl_risco_sev = ctk.CTkLabel(badges, text='', font=('Segoe UI', 12, 'bold'), corner_radius=8, padx=12, pady=6)
        self.lbl_risco_sev.pack(side='left')
        self.lbl_risco_imp = ctk.CTkLabel(badges, text='', font=('Segoe UI', 12, 'bold'), corner_radius=8, padx=12, pady=6)
        self.lbl_risco_imp.pack(side='left', padx=(10, 0))
        stats = ctk.CTkFrame(wrapper, fg_color='transparent')
        stats.pack(fill='x', pady=(0, 14))
        stats.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.card_risco_prestador = self._criar_card_metrica(stats, 'Prestador', '-')
        self.card_risco_prestador.grid(row=0, column=0, sticky='nsew', padx=(0, 8))
        self.card_risco_pdf = self._criar_card_metrica(stats, 'PDFs', '0')
        self.card_risco_pdf.grid(row=0, column=1, sticky='nsew', padx=8)
        self.card_risco_total = self._criar_card_metrica(stats, 'Glosas aplicadas', '0')
        self.card_risco_total.grid(row=0, column=2, sticky='nsew', padx=8)
        self.card_risco_top = self._criar_card_metrica(stats, 'Top 1', '-')
        self.card_risco_top.grid(row=0, column=3, sticky='nsew', padx=(8, 0))
        conteudo = ctk.CTkFrame(wrapper, fg_color='transparent')
        conteudo.pack(fill='both', expand=True)
        painel_texto = ctk.CTkFrame(conteudo, corner_radius=18, fg_color=TEMA['bg_surface'], border_width=1, border_color=TEMA['borda'])
        painel_texto.pack(side='left', fill='both', expand=True, padx=(0, 10))
        ctk.CTkLabel(painel_texto, text='Resumo e analise', font=('Segoe UI', 15, 'bold'), text_color=TEMA['texto_claro']).pack(anchor='w', padx=16, pady=(14, 8))
        self.caixa_texto_risco = ctk.CTkTextbox(painel_texto, font=('Consolas', 13), wrap='word', fg_color=TEMA['bg_shell'], border_width=0)
        self.caixa_texto_risco.pack(fill='both', expand=True, padx=14, pady=(0, 14))
        painel_top = ctk.CTkFrame(conteudo, width=320, corner_radius=18, fg_color=TEMA['bg_surface'], border_width=1, border_color=TEMA['borda'])
        painel_top.pack(side='right', fill='y')
        painel_top.pack_propagate(False)
        ctk.CTkLabel(painel_top, text='Top 10 Glosas', font=('Segoe UI', 15, 'bold'), text_color=TEMA['texto_claro']).pack(anchor='w', padx=16, pady=(14, 8))
        self.scroll_top_risco = ctk.CTkScrollableFrame(painel_top, fg_color='transparent')
        self.scroll_top_risco.pack(fill='both', expand=True, padx=10, pady=(0, 10))

    def iniciar_selecao_manual_risco(self):
        caminhos = filedialog.askopenfilenames(title='Selecione os PDFs', filetypes=[('PDF', '*.pdf')])
        if caminhos:
            self.validar_e_iniciar_risco(list(caminhos))

    def validar_e_iniciar_risco(self, caminhos_pdf):
        if self.frame_analise_relatorio.winfo_ismapped():
            self.exibir_tela_conteudo(self.frame_analise_inicio)
        caminhos_unicos = self.app_master._deduplicar_caminhos_lote(caminhos_pdf)
        ignorados = len(caminhos_pdf) - len(caminhos_unicos)
        if not caminhos_unicos:
            self.lbl_status_risco.configure(text='Nenhum PDF valido selecionado.', text_color=TEMA['erro'])
            return
        mensagem = f'Calculando {len(caminhos_unicos)} arquivo(s)...'
        if ignorados > 0:
            mensagem = f'{ignorados} arquivo(s) duplicado(s) ignorado(s). ' + mensagem
        self.lbl_status_risco.configure(text=mensagem, text_color='#E67E22')
        self.btn_selecionar_risco.configure(state='disabled')
        self.app_master._executar_em_thread(self.processar_lote_risco_thread, caminhos_unicos, on_error=self._tratar_erro_risco)

    def _tratar_erro_risco(self, erro):
        self.lbl_status_risco.configure(text=f'Erro ao processar arquivos: {erro}', text_color=TEMA['erro'])
        self.btn_selecionar_risco.configure(state='normal')

    def processar_lote_risco_thread(self, caminhos):
        agregado_aplicadas = {}
        agregado_autorizadas = {}
        tot_aplicadas = 0
        tot_autorizadas = 0
        tot_producao = 0
        nome_final = 'Credenciado Não Identificado'
        dados_por_mes = {}
        arquivos_processaveis = []
        for caminho in caminhos:
            texto = self.app_master.extrair_texto_pdf(caminho)
            if not texto.strip():
                continue
            arquivos_processaveis.append({'caminho': caminho, 'texto': texto, 'nome_prestador': self.app_master._extrair_nome_prestador_risco(texto)})
            nome_lote = self.app_master._validar_prestadores_lote_risco(arquivos_processaveis)
            gl_ap, gl_aut, t_ap, t_aut, nome, t_prod, mes = self.app_master.extrair_dados_risco(texto, self.app_master.login_auditor)
            if nome != 'Credenciado Não Identificado':
                nome_final = nome
            if self.app_master._normalizar_nome_prestador_risco(nome_lote):
                nome_final = nome_lote
            tot_aplicadas += t_ap
            tot_autorizadas += t_aut
            tot_producao += t_prod
            for k, v in gl_ap.items():
                if k not in agregado_aplicadas:
                    agregado_aplicadas[k] = {'descricao': v['descricao'], 'qtd': 0}
                agregado_aplicadas[k]['qtd'] += v['qtd']
            for k, v in gl_aut.items():
                if k not in agregado_autorizadas:
                    agregado_autorizadas[k] = {'descricao': v['descricao'], 'qtd': 0}
                agregado_autorizadas[k]['qtd'] += v['qtd']
            if mes not in dados_por_mes:
                dados_por_mes[mes] = {'producao': 0, 'total_glosas': 0, 'glosas_dict': {}}
            dados_por_mes[mes]['producao'] += t_prod
            dados_por_mes[mes]['total_glosas'] += t_ap
            for k, v in gl_ap.items():
                if k not in dados_por_mes[mes]['glosas_dict']:
                    dados_por_mes[mes]['glosas_dict'][k] = {'descricao': v['descricao'], 'qtd': 0}
                dados_por_mes[mes]['glosas_dict'][k]['qtd'] += v['qtd']
        self.after(0, self.finalizar_processamento_lote_risco, caminhos, agregado_aplicadas, agregado_autorizadas, tot_aplicadas, tot_autorizadas, nome_final, tot_producao, dados_por_mes)

    def finalizar_processamento_lote_risco(self, caminhos, gl_ap, gl_aut, t_ap, t_aut, nome, t_prod, dados_por_mes):
        if t_ap == 0 and t_aut == 0 and (t_prod == 0):
            self.lbl_status_risco.configure(text='Nenhum dado válido encontrado.', text_color='#E74C3C')
            self.btn_selecionar_risco.configure(state='normal')
            return
        total_risco = sum((dados['qtd'] for cod, dados in gl_ap.items() if self.app_master._eh_glosa_critica(cod)))
        base_calculo = t_prod if t_prod > 0 else t_ap
        pct_producao = total_risco / base_calculo * 100 if base_calculo > 0 else 0
        pct_glosas = total_risco / t_ap * 100 if t_ap > 0 else 0
        texto_relatorio = self.app_master.gerar_texto_relatorio_risco(gl_ap, gl_aut, t_ap, t_aut, nome, pct_producao, pct_glosas, total_risco, t_prod, len(caminhos), dados_por_mes)
        self.exibir_relatorio_risco(texto_relatorio, gl_ap, gl_aut, t_ap, t_aut, self.app_master.login_auditor, nome, pct_producao, pct_glosas, total_risco, t_prod, len(caminhos), dados_por_mes)
        self.btn_selecionar_risco.configure(state='normal')
        self.lbl_status_risco.configure(text='Pronto para nova análise...', text_color='#D6E2F2')

    def exibir_relatorio_risco(self, texto_relatorio, glosas_aplicadas, glosas_autorizadas, total_aplicadas, total_autorizadas, login_auditor, nome_prestador, pct_producao, pct_glosas, total_risco, total_producao, qtd_arquivos, dados_por_mes):
        self.exibir_tela_conteudo(self.frame_analise_relatorio)
        gl_ord = sorted(glosas_aplicadas.items(), key=lambda x: x[1]['qtd'], reverse=True)
        top1 = gl_ord[0] if gl_ord else None
        self.ranking_risco_atual = []
        self.resumo_risco_atual = texto_relatorio
        self.prestador_risco_atual = nome_prestador
        self.lbl_titulo_relatorio.configure(text=f'Analise de Risco - {nome_prestador}')
        base_producao = str(total_producao) if total_producao > 0 else 'nao identificada'
        self.lbl_subtitulo_relatorio_risco.configure(text=f'{qtd_arquivos} PDF(s) analisado(s) | Base de producao: {base_producao}')
        self.card_risco_prestador.lbl_valor.configure(text=nome_prestador if len(nome_prestador) <= 28 else nome_prestador[:25] + '...')
        self.card_risco_pdf.lbl_valor.configure(text=str(qtd_arquivos))
        self.card_risco_total.lbl_valor.configure(text=str(total_aplicadas))
        if top1:
            top1_texto = f"{top1[0]} - {top1[1]['descricao']}"
            self.card_risco_top.lbl_valor.configure(text=top1_texto if len(top1_texto) <= 24 else top1_texto[:21] + '...')
        else:
            self.card_risco_top.lbl_valor.configure(text='Sem glosas')
        if total_risco == 0:
            self.lbl_risco_sev.configure(text='PRODUCAO: ZERO SUSPEITAS', fg_color='#2ECC71', text_color='white')
            self.lbl_risco_imp.configure(text='PERFIL DE GLOSAS: ZERO SUSPEITAS', fg_color='#2ECC71', text_color='white')
        else:
            if pct_producao >= 10:
                self.lbl_risco_sev.configure(text=f'PRODUÇÃO: SUSPEITA CRÍTICA ({pct_producao:.1f}%)', fg_color='#E74C3C', text_color='white')
            elif pct_producao >= 5:
                self.lbl_risco_sev.configure(text=f'PRODUCAO: SUSPEITA ALTA ({pct_producao:.1f}%)', fg_color='#E67E22', text_color='white')
            elif pct_producao >= 2:
                self.lbl_risco_sev.configure(text=f'PRODUCAO: SUSPEITA MODERADA ({pct_producao:.1f}%)', fg_color='#F1C40F', text_color='black')
            else:
                self.lbl_risco_sev.configure(text=f'PRODUCAO: SUSPEITA BAIXA ({pct_producao:.1f}%)', fg_color='#2ECC71', text_color='white')
            if pct_glosas >= 50:
                self.lbl_risco_imp.configure(text=f'PERFIL DE GLOSAS: ALTA CONCENTRACAO ({pct_glosas:.1f}%)', fg_color='#E74C3C', text_color='white')
            elif pct_glosas >= 20:
                self.lbl_risco_imp.configure(text=f'PERFIL DE GLOSAS: CONCENTRACAO SUSPEITA ({pct_glosas:.1f}%)', fg_color='#E67E22', text_color='white')
            else:
                self.lbl_risco_imp.configure(text=f'PERFIL DE GLOSAS: CONCENTRACAO DILUIDA ({pct_glosas:.1f}%)', fg_color='#F1C40F', text_color='black')
        self.caixa_texto_risco.delete('0.0', 'end')
        self.caixa_texto_risco.insert('0.0', texto_relatorio)
        for widget in self.scroll_top_risco.winfo_children():
            widget.destroy()
        if gl_ord:
            for pos, (codigo, dados) in enumerate(gl_ord[:10], start=1):
                pct = dados['qtd'] / total_aplicadas * 100.0 if total_aplicadas else 0.0
                rotulo = self.app_master._obter_categoria_glosa(codigo, contexto='risco')
                cor_rotulo, cor_borda = self.app_master._obter_cores_categoria_glosa(codigo)
                card = ctk.CTkFrame(self.scroll_top_risco, fg_color=TEMA['bg_surface_2'], corner_radius=14, border_width=1, border_color=cor_borda)
                card.pack(fill='x', pady=5, padx=2)
                ctk.CTkLabel(card, text=f'TOP {pos}', font=('Segoe UI', 10, 'bold'), text_color=cor_rotulo).pack(anchor='w', padx=12, pady=(10, 2))
                ctk.CTkLabel(card, text=f"Glosa {codigo} - {dados['descricao']}", justify='left', wraplength=250, font=('Segoe UI', 12, 'bold'), text_color=TEMA['texto_claro']).pack(anchor='w', padx=12)
                ctk.CTkLabel(card, text=f"{dados['qtd']} ocorrencia(s) - {pct:.1f}%", font=('Segoe UI', 11), text_color=TEMA['texto_secundario']).pack(anchor='w', padx=12, pady=(4, 2))
                ctk.CTkLabel(card, text=rotulo, font=('Segoe UI', 11), text_color=cor_rotulo).pack(anchor='w', padx=12, pady=(0, 10))
                self.ranking_risco_atual.append({'codigo': codigo, 'descricao': dados['descricao'], 'quantidade': dados['qtd'], 'percentual': pct, 'categoria': rotulo})
        else:
            vazio = ctk.CTkFrame(self.scroll_top_risco, fg_color=TEMA['bg_surface_2'], corner_radius=14, border_width=1, border_color=TEMA['borda'])
            vazio.pack(fill='x', pady=5, padx=2)
            ctk.CTkLabel(vazio, text='Nenhuma glosa aplicada identificada.', justify='left', wraplength=250, font=('Segoe UI', 12, 'bold'), text_color=TEMA['texto_secundario']).pack(anchor='w', padx=12, pady=14)
        self.btn_grafico_risco.configure(command=lambda: self.app_master.abrir_grafico_risco(glosas_aplicadas, nome_prestador), state='normal' if glosas_aplicadas else 'disabled')
        self.btn_copiar_risco.configure(command=lambda: self.app_master._copiar_texto(texto_relatorio))
        self.btn_word_risco.configure(command=lambda: self.app_master.exportar_word(glosas_aplicadas, total_aplicadas, nome_prestador, pct_producao, pct_glosas, total_risco, total_producao, qtd_arquivos, dados_por_mes))
        self.btn_excel_risco.configure(command=lambda: self.app_master.exportar_excel(glosas_aplicadas, glosas_autorizadas, total_aplicadas, total_autorizadas, login_auditor, nome_prestador, pct_producao, pct_glosas, total_risco, total_producao, qtd_arquivos, dados_por_mes))
