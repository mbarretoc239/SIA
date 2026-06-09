import csv
import os
import customtkinter as ctk

from core.settings import TEMA
from core.database import conectar_sqlite
from shared.utils import registrar_erro

class FrameGerenciadorGlosas(ctk.CTkFrame):
    def __init__(self, master, app_master):
        super().__init__(master, fg_color="transparent")
        self.app_master = app_master

        ctk.CTkLabel(self, text="Gerenciador de Glosas", font=("Segoe UI", 26, "bold"), text_color=TEMA["texto_claro"]).pack(pady=(20, 10), anchor="w", padx=20)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=10)

        painel_edicao = ctk.CTkFrame(container, fg_color="#31455C", corner_radius=10)
        painel_edicao.pack(fill="x", pady=(0, 15), ipadx=10, ipady=10)

        ctk.CTkLabel(painel_edicao, text="Adicionar ou Editar Texto da Glosa", font=("Segoe UI", 16, "bold"), text_color="white").pack(pady=(10, 5))

        linha_inputs = ctk.CTkFrame(painel_edicao, fg_color="transparent")
        linha_inputs.pack(pady=10)

        ctk.CTkLabel(linha_inputs, text="Codigo:", font=("Segoe UI", 12, "bold")).pack(side="left", padx=5)
        self.entry_cod = ctk.CTkEntry(linha_inputs, width=80, placeholder_text="Ex: 450")
        self.entry_cod.pack(side="left", padx=5)

        ctk.CTkLabel(linha_inputs, text="Nova Descricao:", font=("Segoe UI", 12, "bold")).pack(side="left", padx=5)
        self.entry_desc = ctk.CTkEntry(linha_inputs, width=450, placeholder_text="Ex: procedimento nao confere com historico")
        self.entry_desc.pack(side="left", padx=5)

        ctk.CTkButton(linha_inputs, text="Salvar / Substituir", fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"], command=self.salvar_glosa).pack(side="left", padx=15)

        ctk.CTkLabel(container, text="Glosas Ativas no Sistema (Clique em Editar para alterar):", font=("Segoe UI", 14, "bold"), text_color="#D6E2F2").pack(anchor="w", pady=(5, 5))
        self.scroll_lista = ctk.CTkScrollableFrame(container, fg_color="#1E2B3C")
        self.scroll_lista.pack(fill="both", expand=True)

        self.carregar_lista()

    def carregar_lista(self):
        for widget in self.scroll_lista.winfo_children():
            widget.destroy()

        def order_key(k):
            try: return int(k)
            except: return 999999

        for cod in sorted(self.app_master.mapa_glosas.keys(), key=order_key):
            desc = self.app_master.mapa_glosas[cod]
            f_item = ctk.CTkFrame(self.scroll_lista, fg_color="#31455C", corner_radius=5)
            f_item.pack(fill="x", pady=2, padx=5)
            ctk.CTkLabel(f_item, text=f"[{cod}]", font=("Segoe UI", 12, "bold"), text_color="#F39C12", width=50, anchor="w").pack(side="left", padx=10, pady=5)
            ctk.CTkLabel(f_item, text=desc.upper(), font=("Segoe UI", 12), text_color="white", anchor="w").pack(side="left", expand=True, fill="x")
            ctk.CTkButton(f_item, text="Editar", width=60, height=24, fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"], command=lambda c=cod, d=desc: self.preencher_edicao(c, d)).pack(side="right", padx=10)

    def preencher_edicao(self, cod, desc):
        self.entry_cod.delete(0, 'end')
        self.entry_cod.insert(0, cod)
        self.entry_desc.delete(0, 'end')
        self.entry_desc.insert(0, desc)

    def salvar_glosa(self):
        # Delegate saving logic to settings/configuracoes or app_master
        pass

class FrameConfiguracoes(ctk.CTkFrame):
    def __init__(self, master, app_master):
        super().__init__(master, fg_color="transparent")
        self.app_master = app_master

        ctk.CTkLabel(self, text="Configuracoes do Sistema", font=("Segoe UI", 26, "bold"), text_color=TEMA["texto_claro"]).pack(pady=(20, 10), anchor="w", padx=20)

        self.tabview = ctk.CTkTabview(self, width=800, height=500, fg_color="#1E2B3C", segmented_button_selected_color=TEMA["azul_primario"], segmented_button_selected_hover_color=TEMA["azul_hover"])
        self.tabview.pack(fill="both", expand=True, padx=20, pady=10)

        self.tab_glosas = self.tabview.add("Gerenciar Glosas")
        self.tab_procs = self.tabview.add("Gerenciar Procedimentos")
        self.tab_textos = self.tabview.add("Frases Rapidas")

        self.setup_tab_glosas()
        self.setup_tab_procs()
        self.setup_tab_textos()

    def setup_tab_glosas(self):
        painel_edicao = ctk.CTkFrame(self.tab_glosas, fg_color="#31455C", corner_radius=10)
        painel_edicao.pack(fill="x", pady=(0, 15), ipadx=10, ipady=10)

        ctk.CTkLabel(painel_edicao, text="Adicionar ou Editar Texto da Glosa", font=("Segoe UI", 16, "bold"), text_color="white").pack(pady=(10, 5))

        linha_inputs = ctk.CTkFrame(painel_edicao, fg_color="transparent")
        linha_inputs.pack(pady=10)

        ctk.CTkLabel(linha_inputs, text="Codigo:", font=("Segoe UI", 12, "bold")).pack(side="left", padx=5)
        self.entry_cod_glosa = ctk.CTkEntry(linha_inputs, width=80, placeholder_text="Ex: 450")
        self.entry_cod_glosa.pack(side="left", padx=5)

        ctk.CTkLabel(linha_inputs, text="Descricao:", font=("Segoe UI", 12, "bold")).pack(side="left", padx=5)
        self.entry_desc_glosa = ctk.CTkEntry(linha_inputs, width=430, placeholder_text="Ex: procedimento nao confere com historico")
        self.entry_desc_glosa.pack(side="left", padx=5)

        ctk.CTkButton(linha_inputs, text="Salvar", fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"], command=self.salvar_glosa).pack(side="left", padx=15)

        linha_flags = ctk.CTkFrame(painel_edicao, fg_color="transparent")
        linha_flags.pack(fill="x", padx=14, pady=(0, 10))
        self.var_glosa_critica = ctk.BooleanVar(value=False)
        self.var_glosa_tecnica = ctk.BooleanVar(value=False)
        
        ctk.CTkCheckBox(
            linha_flags,
            text="Marcar glosa como critica",
            variable=self.var_glosa_critica,
            onvalue=True,
            offvalue=False
        ).pack(side="left")

        ctk.CTkCheckBox(
            linha_flags,
            text="Marcar glosa como tecnica",
            variable=self.var_glosa_tecnica,
            onvalue=True,
            offvalue=False
        ).pack(side="left", padx=20)

        ctk.CTkLabel(self.tab_glosas, text="Glosas Ativas no Sistema (Clique em Editar para alterar):", font=("Segoe UI", 14, "bold"), text_color="#D6E2F2").pack(anchor="w", pady=(5, 5))
        self.scroll_glosas = ctk.CTkScrollableFrame(self.tab_glosas, fg_color="#1E2B3C")
        self.scroll_glosas.pack(fill="both", expand=True)

    def carregar_lista_glosas(self):
        for widget in self.scroll_glosas.winfo_children(): widget.destroy()

        def order_key(k):
            try: return int(k)
            except: return 999999

        for cod in sorted(self.app_master.mapa_glosas.keys(), key=order_key):
            desc = self.app_master.mapa_glosas[cod]
            f_item = ctk.CTkFrame(self.scroll_glosas, fg_color="#31455C", corner_radius=5)
            f_item.pack(fill="x", pady=2, padx=5)
            ctk.CTkLabel(f_item, text=f"[{cod}]", font=("Segoe UI", 12, "bold"), text_color="#F39C12", width=50, anchor="w").pack(side="left", padx=10, pady=5)
            ctk.CTkLabel(f_item, text=desc.upper(), font=("Segoe UI", 12), text_color="white", anchor="w").pack(side="left", expand=True, fill="x")
            
            eh_critica = False
            eh_tecnica = False
            if hasattr(self.app_master, '_eh_glosa_critica'):
                eh_critica = self.app_master._eh_glosa_critica(cod)
            if hasattr(self.app_master, '_eh_glosa_tecnica'):
                eh_tecnica = self.app_master._eh_glosa_tecnica(cod) and not eh_critica
            
            if eh_critica:
                ctk.CTkLabel(
                    f_item,
                    text="CRÍTICA",
                    font=("Segoe UI", 10, "bold"),
                    text_color="white",
                    fg_color="#C0392B",
                    corner_radius=10,
                    padx=8,
                    pady=3
                ).pack(side="right", padx=(0, 6))
                
            if eh_tecnica:
                ctk.CTkLabel(
                    f_item,
                    text="TÉCNICA",
                    font=("Segoe UI", 10, "bold"),
                    text_color="white",
                    fg_color="#D35400",
                    corner_radius=10,
                    padx=8,
                    pady=3
                ).pack(side="right", padx=(0, 6))
            
            if not eh_critica and not eh_tecnica:
                ctk.CTkLabel(
                    f_item,
                    text="PADRÃO",
                    font=("Segoe UI", 10, "bold"),
                    text_color="white",
                    fg_color="#2471A3",
                    corner_radius=10,
                    padx=8,
                    pady=3
                ).pack(side="right", padx=(0, 6))
            ctk.CTkButton(f_item, text="Editar", width=60, height=24, fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"], command=lambda c=cod, d=desc: self.preencher_edicao_glosa(c, d)).pack(side="right", padx=10)

    def preencher_edicao_glosa(self, cod, desc):
        self.entry_cod_glosa.delete(0, 'end')
        self.entry_cod_glosa.insert(0, cod)
        self.entry_desc_glosa.delete(0, 'end')
        self.entry_desc_glosa.insert(0, desc)
        if hasattr(self.app_master, '_eh_glosa_critica'):
            self.var_glosa_critica.set(self.app_master._eh_glosa_critica(cod))
        if hasattr(self.app_master, '_eh_glosa_tecnica'):
            self.var_glosa_tecnica.set(self.app_master._eh_glosa_tecnica(cod))

    def salvar_glosa(self):
        cod = self.entry_cod_glosa.get().strip()
        desc = self.entry_desc_glosa.get().strip().lower()
        critica = bool(self.var_glosa_critica.get())
        tecnica = bool(self.var_glosa_tecnica.get()) and not critica
        if not cod or not desc: return

        aprendidas = {}
        if hasattr(self.app_master, 'arq_glosas_aprendidas') and os.path.exists(self.app_master.arq_glosas_aprendidas):
            with open(self.app_master.arq_glosas_aprendidas, mode='r', encoding='utf-8') as f:
                for row in csv.DictReader(f, delimiter=';'):
                    codigo = (row.get('CODIGO') or '').strip()
                    if not codigo:
                        continue
                    aprendidas[codigo] = {
                        'descricao': (row.get('DESCRICAO') or '').strip().lower(),
                        'critica': self.app_master._interpretar_flag_critica(row.get('CRITICA')) if hasattr(self.app_master, '_interpretar_flag_critica') else False,
                        'tecnica': self.app_master._interpretar_flag_tecnica(row.get('TECNICA')) if hasattr(self.app_master, '_interpretar_flag_tecnica') else False
                    }

        aprendidas[cod] = {'descricao': desc, 'critica': critica, 'tecnica': tecnica}
        if hasattr(self.app_master, 'arq_glosas_aprendidas'):
            with open(self.app_master.arq_glosas_aprendidas, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['CODIGO', 'DESCRICAO', 'CRITICA', 'TECNICA'])
                def _order(v):
                    try: return int(v)
                    except: return 999999
                for k in sorted(aprendidas.keys(), key=_order):
                    writer.writerow([
                        k, 
                        aprendidas[k]['descricao'], 
                        self.app_master._serializar_flag_critica(aprendidas[k].get('critica')) if hasattr(self.app_master, '_serializar_flag_critica') else str(aprendidas[k].get('critica')),
                        self.app_master._serializar_flag_tecnica(aprendidas[k].get('tecnica')) if hasattr(self.app_master, '_serializar_flag_tecnica') else str(aprendidas[k].get('tecnica'))
                    ])

            if hasattr(self.app_master, 'carregar_bancos'):
                self.app_master.carregar_bancos()
            self.carregar_lista_glosas()
            self.entry_cod_glosa.delete(0, 'end')
            self.entry_desc_glosa.delete(0, 'end')
            self.var_glosa_critica.set(False)
            self.var_glosa_tecnica.set(False)

    def setup_tab_procs(self):
        painel_edicao = ctk.CTkFrame(self.tab_procs, fg_color="#31455C", corner_radius=10)
        painel_edicao.pack(fill="x", pady=(0, 15), ipadx=10, ipady=10)

        ctk.CTkLabel(painel_edicao, text="Adicionar ou Editar Texto de Procedimento", font=("Segoe UI", 16, "bold"), text_color="white").pack(pady=(10, 5))

        linha_inputs = ctk.CTkFrame(painel_edicao, fg_color="transparent")
        linha_inputs.pack(pady=10)

        ctk.CTkLabel(linha_inputs, text="Codigo:", font=("Segoe UI", 12, "bold")).pack(side="left", padx=5)
        self.entry_cod_proc = ctk.CTkEntry(linha_inputs, width=80, placeholder_text="Ex: 8100")
        self.entry_cod_proc.pack(side="left", padx=5)

        ctk.CTkLabel(linha_inputs, text="Descricao:", font=("Segoe UI", 12, "bold")).pack(side="left", padx=5)
        self.entry_desc_proc = ctk.CTkEntry(linha_inputs, width=450, placeholder_text="Ex: clareamento dentario")
        self.entry_desc_proc.pack(side="left", padx=5)

        ctk.CTkButton(linha_inputs, text="Salvar", fg_color="#2E86C1", hover_color="#21618C", command=self.salvar_proc).pack(side="left", padx=15)

        ctk.CTkLabel(self.tab_procs, text="Procedimentos Ativos no Sistema (Clique em Editar para alterar):", font=("Segoe UI", 14, "bold"), text_color="#D6E2F2").pack(anchor="w", pady=(5, 5))
        self.scroll_procs = ctk.CTkScrollableFrame(self.tab_procs, fg_color="#1E2B3C")
        self.scroll_procs.pack(fill="both", expand=True)

    def carregar_lista_procs(self):
        for widget in self.scroll_procs.winfo_children(): widget.destroy()

        def order_key(k):
            try: return int(k)
            except: return 999999

        for cod in sorted(self.app_master.mapa_procedimentos.keys(), key=order_key):
            desc = self.app_master.mapa_procedimentos[cod]
            f_item = ctk.CTkFrame(self.scroll_procs, fg_color="#31455C", corner_radius=5)
            f_item.pack(fill="x", pady=2, padx=5)
            ctk.CTkLabel(f_item, text=f"[{cod}]", font=("Segoe UI", 12, "bold"), text_color=TEMA["texto_claro"], width=60, anchor="w").pack(side="left", padx=10, pady=5)
            ctk.CTkLabel(f_item, text=desc.upper(), font=("Segoe UI", 12), text_color="white", anchor="w").pack(side="left", expand=True, fill="x")
            ctk.CTkButton(f_item, text="Editar", width=60, height=24, fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"], command=lambda c=cod, d=desc: self.preencher_edicao_proc(c, d)).pack(side="right", padx=10)

    def preencher_edicao_proc(self, cod, desc):
        self.entry_cod_proc.delete(0, 'end')
        self.entry_cod_proc.insert(0, cod)
        self.entry_desc_proc.delete(0, 'end')
        self.entry_desc_proc.insert(0, desc)

    def salvar_proc(self):
        cod = self.entry_cod_proc.get().strip()
        desc = self.entry_desc_proc.get().strip().lower()
        if not cod or not desc: return

        aprendidos = {}
        if hasattr(self.app_master, 'arq_proc_aprendidos') and os.path.exists(self.app_master.arq_proc_aprendidos):
            with open(self.app_master.arq_proc_aprendidos, mode='r', encoding='utf-8') as f:
                for row in csv.DictReader(f, delimiter=';'): aprendidos[row['CODIGO']] = row['DESCRICAO']

        aprendidos[cod] = desc
        if hasattr(self.app_master, 'arq_proc_aprendidos'):
            with open(self.app_master.arq_proc_aprendidos, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['CODIGO', 'DESCRICAO'])
                for k, v in aprendidos.items(): writer.writerow([k, v])

            if hasattr(self.app_master, 'carregar_bancos'):
                self.app_master.carregar_bancos()
            self.carregar_lista_procs()
            self.entry_cod_proc.delete(0, 'end')
            self.entry_desc_proc.delete(0, 'end')

    def carregar_listas(self):
        self.carregar_lista_glosas()
        self.carregar_lista_procs()
        self.carregar_lista_textos()

    def setup_tab_textos(self):
        painel_edicao = ctk.CTkFrame(self.tab_textos, fg_color="#31455C", corner_radius=10)
        painel_edicao.pack(fill="x", pady=(0, 15), ipadx=10, ipady=10)

        ctk.CTkLabel(painel_edicao, text="Adicionar Frase Rápida para Glosa", font=("Segoe UI", 16, "bold"), text_color="white").pack(pady=(10, 5))

        linha_inputs = ctk.CTkFrame(painel_edicao, fg_color="transparent")
        linha_inputs.pack(pady=10)

        ctk.CTkLabel(linha_inputs, text="Código Glosa:", font=("Segoe UI", 12, "bold")).pack(side="left", padx=5)
        self.entry_cod_texto = ctk.CTkEntry(linha_inputs, width=80, placeholder_text="Ex: 438")
        self.entry_cod_texto.pack(side="left", padx=5)

        ctk.CTkLabel(linha_inputs, text="Texto Rápido:", font=("Segoe UI", 12, "bold")).pack(side="left", padx=5)
        self.entry_desc_texto = ctk.CTkEntry(linha_inputs, width=450, placeholder_text="Ex: procedimento anterior apresenta falhas")
        self.entry_desc_texto.pack(side="left", padx=5)

        ctk.CTkButton(linha_inputs, text="Adicionar", fg_color="#2E86C1", hover_color="#21618C", command=self.salvar_texto).pack(side="left", padx=15)

        ctk.CTkLabel(self.tab_textos, text="Frases Cadastradas:", font=("Segoe UI", 14, "bold"), text_color="#D6E2F2").pack(anchor="w", pady=(5, 5))
        self.scroll_textos = ctk.CTkScrollableFrame(self.tab_textos, fg_color="#1E2B3C")
        self.scroll_textos.pack(fill="both", expand=True)

    def carregar_lista_textos(self):
        for widget in self.scroll_textos.winfo_children(): widget.destroy()

        try:
            with conectar_sqlite(self.app_master.arq_textos_db, row_factory=True) as conn:
                rows = conn.execute("SELECT id, glosa_codigo, texto FROM justificativas ORDER BY glosa_codigo ASC, id ASC").fetchall()
        except Exception:
            rows = []

        for row in rows:
            f_item = ctk.CTkFrame(self.scroll_textos, fg_color="#31455C", corner_radius=5)
            f_item.pack(fill="x", pady=2, padx=5)
            ctk.CTkLabel(f_item, text=f"[{row['glosa_codigo']}]", font=("Segoe UI", 12, "bold"), text_color=TEMA["texto_claro"], width=60, anchor="w").pack(side="left", padx=10, pady=5)
            ctk.CTkLabel(f_item, text=row['texto'], font=("Segoe UI", 12), text_color="white", anchor="w").pack(side="left", expand=True, fill="x")
            ctk.CTkButton(f_item, text="Excluir", width=60, height=24, fg_color="#E74C3C", hover_color="#C0392B", command=lambda i=row['id']: self.excluir_texto(i)).pack(side="right", padx=10)

    def salvar_texto(self):
        cod = self.entry_cod_texto.get().strip()
        texto = self.entry_desc_texto.get().strip()
        if not cod or not texto: return
        
        try:
            with conectar_sqlite(self.app_master.arq_textos_db) as conn:
                conn.execute("INSERT INTO justificativas (glosa_codigo, texto) VALUES (?, ?)", (cod, texto))
                conn.commit()
        except Exception as e:
            registrar_erro("Erro ao salvar texto", e)

        self.carregar_lista_textos()
        self.entry_desc_texto.delete(0, 'end')

    def excluir_texto(self, texto_id):
        try:
            with conectar_sqlite(self.app_master.arq_textos_db) as conn:
                conn.execute("DELETE FROM justificativas WHERE id = ?", (texto_id,))
                conn.commit()
        except Exception as e:
            registrar_erro("Erro ao excluir texto", e)
        self.carregar_lista_textos()
