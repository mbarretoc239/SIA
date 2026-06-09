import os
import re
import csv
import unicodedata
from tkinter import filedialog
import customtkinter as ctk

from core.settings import TEMA

class FrameProducaoPrestador(ctk.CTkFrame):
    def __init__(self, master, app_master):
        super().__init__(master, fg_color="transparent")
        self.app_master = app_master
        
        self.ranking_producao_atual = []
        self.resumo_producao_atual = ''
        self.prestador_producao_atual = ''
        
        self.setup_ui()

    def setup_ui(self):
        wrapper = ctk.CTkFrame(self, fg_color='transparent')
        wrapper.pack(fill='both', expand=True, padx=20, pady=20)
        header = ctk.CTkFrame(wrapper, fg_color='transparent')
        header.pack(fill='x', pady=(0, 16))
        ctk.CTkLabel(header, text='Ranking de Producao do Prestador', font=('Segoe UI', 28, 'bold'), text_color=TEMA['texto_claro']).pack(anchor='w')
        ctk.CTkLabel(header, text='Envie um ou mais demonstrativos de pagamento para contar e ranquear os procedimentos mais produzidos do prestador.', font=('Segoe UI', 14), text_color=TEMA['texto_secundario']).pack(anchor='w', pady=(4, 0))
        topo = ctk.CTkFrame(wrapper, corner_radius=18, fg_color=TEMA['bg_surface_2'], border_width=1, border_color=TEMA['borda'])
        topo.pack(fill='x', pady=(0, 14))
        acoes = ctk.CTkFrame(topo, fg_color='transparent')
        acoes.pack(fill='x', padx=18, pady=16)
        self.btn_selecionar_producao = ctk.CTkButton(acoes, text='Selecionar Demonstrativos', command=self.iniciar_selecao_manual_producao, height=44, font=('Segoe UI', 14, 'bold'), fg_color=TEMA['azul_primario'], hover_color=TEMA['azul_hover'])
        self.btn_selecionar_producao.pack(side='left')
        ctk.CTkButton(acoes, text='Copiar Ranking', command=self.copiar_ranking_producao, height=44, font=('Segoe UI', 13, 'bold'), fg_color=TEMA['bg_surface_3'], hover_color=TEMA['azul_sidebar_hover']).pack(side='left', padx=10)
        ctk.CTkButton(acoes, text='Exportar CSV', command=self.exportar_csv_producao, height=44, font=('Segoe UI', 13, 'bold'), fg_color='#1F8A5B', hover_color='#176746').pack(side='left')
        self.lbl_status_producao = ctk.CTkLabel(topo, text='Aguardando demonstrativo(s) de pagamento...', font=('Segoe UI', 12, 'italic'), text_color=TEMA['texto_secundario'])
        self.lbl_status_producao.pack(anchor='w', padx=18, pady=(0, 14))
        stats = ctk.CTkFrame(wrapper, fg_color='transparent')
        stats.pack(fill='x', pady=(0, 14))
        stats.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.card_prestador = self._criar_card_metrica(stats, 'Prestador', '-')
        self.card_prestador.grid(row=0, column=0, sticky='nsew', padx=(0, 8))
        self.card_pdf = self._criar_card_metrica(stats, 'PDFs', '0')
        self.card_pdf.grid(row=0, column=1, sticky='nsew', padx=8)
        self.card_total_proc = self._criar_card_metrica(stats, 'Linhas lidas', '0')
        self.card_total_proc.grid(row=0, column=2, sticky='nsew', padx=8)
        self.card_top_proc = self._criar_card_metrica(stats, 'Top 1', '-')
        self.card_top_proc.grid(row=0, column=3, sticky='nsew', padx=(8, 0))
        conteudo = ctk.CTkFrame(wrapper, fg_color='transparent')
        conteudo.pack(fill='both', expand=True)
        painel_texto = ctk.CTkFrame(conteudo, corner_radius=18, fg_color=TEMA['bg_surface'], border_width=1, border_color=TEMA['borda'])
        painel_texto.pack(side='left', fill='both', expand=True, padx=(0, 10))
        ctk.CTkLabel(painel_texto, text='Resumo e ranking', font=('Segoe UI', 15, 'bold'), text_color=TEMA['texto_claro']).pack(anchor='w', padx=16, pady=(14, 8))
        self.caixa_texto_producao = ctk.CTkTextbox(painel_texto, font=('Consolas', 13), wrap='word', fg_color=TEMA['bg_shell'], border_width=0)
        self.caixa_texto_producao.pack(fill='both', expand=True, padx=14, pady=(0, 14))
        painel_top = ctk.CTkFrame(conteudo, width=320, corner_radius=18, fg_color=TEMA['bg_surface'], border_width=1, border_color=TEMA['borda'])
        painel_top.pack(side='right', fill='y')
        painel_top.pack_propagate(False)
        ctk.CTkLabel(painel_top, text='Top 10', font=('Segoe UI', 15, 'bold'), text_color=TEMA['texto_claro']).pack(anchor='w', padx=16, pady=(14, 8))
        self.scroll_top_producao = ctk.CTkScrollableFrame(painel_top, fg_color='transparent')
        self.scroll_top_producao.pack(fill='both', expand=True, padx=10, pady=(0, 10))

    def _criar_card_metrica(self, master, titulo, valor):
        card = ctk.CTkFrame(master, corner_radius=16, fg_color=TEMA['bg_surface'], border_width=1, border_color=TEMA['borda'])
        lbl_titulo = ctk.CTkLabel(card, text=titulo, font=('Segoe UI', 11, 'bold'), text_color=TEMA['texto_secundario'])
        lbl_titulo.pack(anchor='w', padx=14, pady=(12, 4))
        lbl_valor = ctk.CTkLabel(card, text=valor, font=('Segoe UI', 20, 'bold'), text_color=TEMA['texto_claro'], justify='left')
        lbl_valor.pack(anchor='w', padx=14, pady=(0, 12))
        card.lbl_valor = lbl_valor
        return card

    def validar_e_iniciar_producao(self, caminhos):
        caminhos = [c for c in caminhos if str(c).lower().endswith('.pdf')]
        caminhos = self.app_master._deduplicar_caminhos_lote(caminhos)
        if not caminhos:
            return
        self.btn_selecionar_producao.configure(state='disabled')
        self.lbl_status_producao.configure(text='Lendo demonstrativo(s) e consolidando produção...', text_color=TEMA['aviso'])
        self.caixa_texto_producao.delete('0.0', 'end')
        self.caixa_texto_producao.insert('0.0', 'Processando...')
        self.app_master._executar_em_thread(self.app_master._processar_demonstrativos_producao, caminhos, on_error=self._tratar_erro_producao, on_success=self._finalizar_producao)

    def iniciar_selecao_manual_producao(self):
        caminhos = filedialog.askopenfilenames(filetypes=[('PDF', '*.pdf')])
        if caminhos:
            self.validar_e_iniciar_producao(list(caminhos))

    def _tratar_erro_producao(self, erro):
        self.lbl_status_producao.configure(text=f'Erro ao processar demonstrativo(s): {erro}', text_color=TEMA['erro'])
        self.btn_selecionar_producao.configure(state='normal')

    def _finalizar_producao(self, dados):
        self.btn_selecionar_producao.configure(state='normal')
        self.ranking_producao_atual = []
        for widget in self.scroll_top_producao.winfo_children():
            widget.destroy()
        prestador = dados['prestador']
        ranking = dados['ranking']
        total = dados['total_linhas']
        top1 = ranking[0][0] if ranking else '—'
        self.card_prestador.lbl_valor.configure(text=prestador if len(prestador) <= 28 else prestador[:25] + '...')
        self.card_pdf.lbl_valor.configure(text=str(dados['qtd_pdfs']))
        self.card_total_proc.lbl_valor.configure(text=str(total))
        self.card_top_proc.lbl_valor.configure(text=top1 if len(top1) <= 24 else top1[:21] + '...')
        linhas = [f'Prestador: {prestador}', f"PDFs analisados: {dados['qtd_pdfs']}", f'Total de linhas/procedimentos identificados: {total}', '', 'Ranking dos procedimentos mais solicitados:']
        for pos, (procedimento, qtd) in enumerate(ranking, start=1):
            pct = qtd / total * 100.0 if total else 0.0
            valor = dados['valores'].get(procedimento, 0.0)
            linhas.append(f'{pos}. {procedimento} - {qtd} procedimento(s) ({pct:.1f}%) | Vl. pago somado: R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))
            self.ranking_producao_atual.append({'posicao': pos, 'procedimento': procedimento, 'quantidade': qtd, 'percentual': pct, 'valor_pago': valor})
        if dados['detalhes_pdf']:
            linhas.extend(['', 'Resumo por arquivo:'])
            for nome_arq, prest_pdf, lidas in dados['detalhes_pdf']:
                linhas.append(f'- {nome_arq}: {lidas} linha(s) validas | {prest_pdf}')
        resumo = '\n'.join(linhas)
        self.resumo_producao_atual = resumo
        self.prestador_producao_atual = prestador
        self.caixa_texto_producao.delete('0.0', 'end')
        self.caixa_texto_producao.insert('0.0', resumo)
        for pos, item in enumerate(self.ranking_producao_atual[:10], start=1):
            card = ctk.CTkFrame(self.scroll_top_producao, fg_color=TEMA['bg_surface_2'], corner_radius=14, border_width=1, border_color=TEMA['borda'])
            card.pack(fill='x', pady=5, padx=2)
            ctk.CTkLabel(card, text=f'TOP {pos}', font=('Segoe UI', 10, 'bold'), text_color='#7FB3FF').pack(anchor='w', padx=12, pady=(10, 2))
            ctk.CTkLabel(card, text=item['procedimento'], justify='left', wraplength=250, font=('Segoe UI', 12, 'bold'), text_color=TEMA['texto_claro']).pack(anchor='w', padx=12)
            ctk.CTkLabel(card, text=f"{item['quantidade']} procedimento(s) - {item['percentual']:.1f}%", font=('Segoe UI', 11), text_color=TEMA['texto_secundario']).pack(anchor='w', padx=12, pady=(4, 2))
            ctk.CTkLabel(card, text=f"R$ {item['valor_pago']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), font=('Segoe UI', 11), text_color='#9FD4B5').pack(anchor='w', padx=12, pady=(0, 10))
        self.lbl_status_producao.configure(text='Ranking gerado com sucesso!', text_color='#2ECC71')

    def copiar_ranking_producao(self):
        texto = self.resumo_producao_atual or self.caixa_texto_producao.get('0.0', 'end').strip()
        if texto:
            self.app_master._copiar_texto(texto)

    def exportar_csv_producao(self):
        if not self.ranking_producao_atual:
            self.lbl_status_producao.configure(text='Nenhum ranking disponivel para exportar.', text_color=TEMA['erro'])
            return
        caminho = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV', '*.csv')], initialfile='ranking_producao_prestador.csv')
        if not caminho:
            return
        with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['PRESTADOR', self.prestador_producao_atual])
            writer.writerow(['POSICAO', 'PROCEDIMENTO', 'QUANTIDADE', 'PERCENTUAL', 'VALOR_PAGO_SOMADO'])
            for item in self.ranking_producao_atual:
                writer.writerow([item['posicao'], item['procedimento'], item['quantidade'], f"{item['percentual']:.2f}", f"{item['valor_pago']:.2f}"])
        self.lbl_status_producao.configure(text='CSV exportado com sucesso!', text_color='#2ECC71')
