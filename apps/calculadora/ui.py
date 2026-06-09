import customtkinter as ctk
from core.settings import TEMA

class FrameCalculadora(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.setup_ui()

    def setup_ui(self):
        wrapper = ctk.CTkFrame(self, fg_color='transparent')
        wrapper.pack(expand=True, fill='both', padx=40, pady=30)
        hero = ctk.CTkFrame(wrapper, fg_color='transparent')
        hero.pack(expand=True)
        ctk.CTkLabel(hero, text='Calculadora de Glosa', font=('Segoe UI', 34, 'bold'), text_color=TEMA['texto_claro']).pack(pady=(10, 6))
        ctk.CTkLabel(hero, text='Calcule rapidamente o percentual glosado com um layout mais claro e profissional.', font=('Segoe UI', 14), text_color='#8FA9C9').pack(pady=(0, 24))
        card = ctk.CTkFrame(hero, corner_radius=24, fg_color='#0B1A31', border_width=1, border_color='#17365F')
        card.pack(padx=20, pady=8)
        card_top = ctk.CTkFrame(card, fg_color='transparent')
        card_top.pack(fill='x', padx=28, pady=(24, 10))
        chip = ctk.CTkLabel(card_top, text='CÁLCULO RÁPIDO', font=('Segoe UI', 11, 'bold'), text_color='#7FB3FF', fg_color='#102746', corner_radius=999, padx=12, pady=6)
        chip.pack(anchor='w', pady=(0, 14))
        ctk.CTkLabel(card_top, text='Valor Cobrado (R$)', font=('Segoe UI', 12, 'bold'), text_color='#D6E2F2').pack(anchor='w', pady=(0, 6))
        self.entry_cobrado = ctk.CTkEntry(card_top, placeholder_text='Ex: 1.500,50', height=50, width=360, corner_radius=14, fg_color='#102746', border_color='#29558E', text_color='#F3F7FF', placeholder_text_color='#6E89AB')
        self.entry_cobrado.pack(fill='x', pady=(0, 16))
        self.entry_cobrado.bind('<FocusOut>', lambda e: self._formatar_moeda_entry(self.entry_cobrado))
        ctk.CTkLabel(card_top, text='Valor Pago (R$)', font=('Segoe UI', 12, 'bold'), text_color='#D6E2F2').pack(anchor='w', pady=(0, 6))
        self.entry_pago = ctk.CTkEntry(card_top, placeholder_text='Ex: 1.200,00', height=50, width=360, corner_radius=14, fg_color='#102746', border_color='#29558E', text_color='#F3F7FF', placeholder_text_color='#6E89AB')
        self.entry_pago.pack(fill='x', pady=(0, 22))
        self.entry_pago.bind('<FocusOut>', lambda e: self._formatar_moeda_entry(self.entry_pago))
        frame_btns = ctk.CTkFrame(card_top, fg_color='transparent')
        frame_btns.pack(fill='x')
        ctk.CTkButton(frame_btns, text='Calcular Porcentagem', command=self.calcular_glosa, height=52, corner_radius=14, font=('Segoe UI', 15, 'bold'), fg_color='#4C86F7', hover_color='#3B73E0').pack(side='left', expand=True, fill='x', padx=(0, 8))
        ctk.CTkButton(frame_btns, text='🗑️ Limpar', command=self._limpar_calculadora, height=52, corner_radius=14, font=('Segoe UI', 13, 'bold'), fg_color='#2C3E50', hover_color='#34495E', width=100).pack(side='right')
        result_card = ctk.CTkFrame(card, corner_radius=18, fg_color='#0F223D', border_width=1, border_color='#17365F')
        result_card.pack(fill='x', padx=28, pady=(12, 14))
        ctk.CTkLabel(result_card, text='Resultado', font=('Segoe UI', 11, 'bold'), text_color='#7E99BD').pack(anchor='w', padx=18, pady=(16, 6))
        self.lbl_resultado_calc = ctk.CTkLabel(result_card, text='Aguardando cálculo...', font=('Segoe UI', 14), text_color='#D6E2F2')
        self.lbl_resultado_calc.pack(anchor='w', padx=18, pady=(0, 6))
        self.lbl_destaque_calc = ctk.CTkLabel(result_card, text='', font=('Segoe UI', 30, 'bold'), text_color='#F3F7FF')
        self.lbl_destaque_calc.pack(anchor='w', padx=18, pady=(0, 8))
        self.frame_barra_calc = ctk.CTkFrame(result_card, height=14, fg_color='#1A2A3F', corner_radius=7)
        self.barra_pago = ctk.CTkFrame(self.frame_barra_calc, height=14, fg_color='#27AE60', corner_radius=7)
        self.barra_glosado = ctk.CTkFrame(self.frame_barra_calc, height=14, fg_color='#E74C3C', corner_radius=7)
        self.frame_breakdown_calc = ctk.CTkFrame(result_card, fg_color='transparent')
        self._breakdown_labels = {}
        breakdown_config = [('cobrado', '💰 Cobrado', '#3498DB'), ('pago', '✅ Pago', '#27AE60'), ('glosado', '❌ Glosado', '#E74C3C')]
        for col, (key, titulo, cor) in enumerate(breakdown_config):
            mini = ctk.CTkFrame(self.frame_breakdown_calc, corner_radius=8, fg_color='#0B1A31', border_width=1, border_color=cor)
            mini.grid(row=0, column=col, padx=6, pady=6, sticky='nsew')
            self.frame_breakdown_calc.grid_columnconfigure(col, weight=1)
            ctk.CTkLabel(mini, text=titulo, font=('Segoe UI', 10, 'bold'), text_color='#8899AA').pack(anchor='w', padx=10, pady=(8, 2))
            lbl = ctk.CTkLabel(mini, text='R$ 0,00', font=('Segoe UI', 16, 'bold'), text_color='white')
            lbl.pack(anchor='w', padx=10, pady=(0, 8))
            self._breakdown_labels[key] = lbl
        ctk.CTkFrame(result_card, height=8, fg_color='transparent').pack()

    def _formatar_moeda_entry(self, entry):
        try:
            raw = entry.get().replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
            valor = float(raw)
            formatado = f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
            entry.delete(0, 'end')
            entry.insert(0, formatado)
        except (ValueError, Exception):
            pass

    def _limpar_calculadora(self):
        self.entry_cobrado.delete(0, 'end')
        self.entry_pago.delete(0, 'end')
        self.lbl_resultado_calc.configure(text='Aguardando cálculo...', text_color='#D6E2F2')
        self.lbl_destaque_calc.configure(text='')
        self.frame_barra_calc.pack_forget()
        self.frame_breakdown_calc.pack_forget()

    def calcular_glosa(self):
        try:
            str_cobrado = self.entry_cobrado.get().replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
            str_pago = self.entry_pago.get().replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
            v_cobrado = float(str_cobrado)
            v_pago = float(str_pago)
            if v_cobrado == 0:
                self.lbl_resultado_calc.configure(text='O valor cobrado não pode ser zero.', text_color='#E74C3C')
                self.lbl_destaque_calc.configure(text='')
                self.frame_barra_calc.pack_forget()
                self.frame_breakdown_calc.pack_forget()
                return
            v_glosa = v_cobrado - v_pago
            pct_glosa = v_glosa / v_cobrado * 100
            pct_pago = 100 - pct_glosa
            if v_glosa < 0:
                self.lbl_resultado_calc.configure(text='Erro: Pago maior que cobrado.', text_color='#E74C3C')
                self.lbl_destaque_calc.configure(text='')
                self.frame_barra_calc.pack_forget()
                self.frame_breakdown_calc.pack_forget()
            elif v_glosa == 0:
                self.lbl_resultado_calc.configure(text='Sem glosas aplicadas.', text_color='#2ECC71')
                self.lbl_destaque_calc.configure(text='0.0%', text_color='#2ECC71')
                self._mostrar_breakdown_calc(v_cobrado, v_pago, v_glosa, 0)
                self._mostrar_barra_calc(100, 0)
            else:
                self.lbl_resultado_calc.configure(text=f'Valor Glosado: R$ {v_glosa:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'), text_color='white')
                self.lbl_destaque_calc.configure(text=f'Glosa: {pct_glosa:.1f}%', text_color='#E74C3C')
                self._mostrar_breakdown_calc(v_cobrado, v_pago, v_glosa, pct_glosa)
                self._mostrar_barra_calc(pct_pago, pct_glosa)
        except ValueError:
            self.lbl_resultado_calc.configure(text='Erro: Digite apenas números válidos.', text_color='#E74C3C')
            self.lbl_destaque_calc.configure(text='')
            self.frame_barra_calc.pack_forget()
            self.frame_breakdown_calc.pack_forget()

    def _formatar_brl(self, valor):
        return f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

    def _mostrar_breakdown_calc(self, cobrado, pago, glosado, pct):
        if not self.frame_breakdown_calc.winfo_ismapped():
            self.frame_breakdown_calc.pack(fill='x', padx=18, pady=(4, 4))
        self._breakdown_labels['cobrado'].configure(text=self._formatar_brl(cobrado))
        self._breakdown_labels['pago'].configure(text=self._formatar_brl(pago))
        pct_str = f' ({pct:.1f}%)' if pct > 0 else ''
        self._breakdown_labels['glosado'].configure(text=f'{self._formatar_brl(glosado)}{pct_str}')

    def _mostrar_barra_calc(self, pct_pago, pct_glosado):
        if not self.frame_barra_calc.winfo_ismapped():
            self.frame_barra_calc.pack(fill='x', padx=18, pady=(4, 8))
        self.barra_pago.place_forget()
        self.barra_glosado.place_forget()
        pct_pago_safe = max(0, min(100, pct_pago))
        pct_glosado_safe = max(0, min(100, pct_glosado))
        if pct_pago_safe > 0:
            self.barra_pago.place(relx=0, rely=0, relwidth=pct_pago_safe / 100, relheight=1.0)
        if pct_glosado_safe > 0:
            self.barra_glosado.place(relx=pct_pago_safe / 100, rely=0, relwidth=pct_glosado_safe / 100, relheight=1.0)
