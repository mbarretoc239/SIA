import os
import customtkinter as ctk
from pathlib import Path
from PIL import Image, ImageTk

from core.settings import TEMA
from core.database import conectar_sqlite
from shared.utils import remover_arquivo_seguro

class FrameGaleriaHistorica(ctk.CTkFrame):
    def __init__(self, master, app_master, modo="todas"):
        super().__init__(master, fg_color="transparent")
        self.app_master = app_master
        self.modo = modo
        
        titulo = "Galeria do Acervo Visual" if modo == "todas" else "Pendencias de Imagens"
        ctk.CTkLabel(self, text=titulo, font=("Segoe UI", 26, "bold"), text_color=TEMA["texto_claro"]).pack(pady=(20, 10), anchor="w", padx=20)
        
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkButton(bar, text="Atualizar Galeria", command=self.carregar_imagens, fg_color=TEMA["bg_surface_3"], hover_color=TEMA["azul_sidebar_hover"], text_color=TEMA["texto_claro"]).pack(side="left")
        
        if modo == "todas":
            ctk.CTkButton(bar, text="Limpar Pendentes", command=self.excluir_pendentes, fg_color=TEMA["bg_surface_3"], hover_color=TEMA["azul_sidebar_hover"], text_color=TEMA["texto_claro"]).pack(side="left", padx=10)
            ctk.CTkButton(bar, text="Limpar Duplicadas", command=self.excluir_duplicadas, fg_color=TEMA["bg_surface_3"], hover_color=TEMA["azul_sidebar_hover"], text_color=TEMA["texto_claro"]).pack(side="left", padx=10)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=15, pady=10)
        self.carregar_imagens()

    def carregar_imagens(self):
        for widget in self.scroll.winfo_children():
            widget.destroy()
            
        pasta_base = getattr(self.app_master, 'pasta_dados', str(Path.home()))
        self.arq_db = os.path.join(pasta_base, 'imagens_forense', 'memoria_imagens.sqlite3')
        
        if not os.path.exists(self.arq_db):
            ctk.CTkLabel(self.scroll, text="Nenhuma imagem no historico ainda.").pack(pady=20)
            return

        with conectar_sqlite(self.arq_db, row_factory=True) as conn:
            if self.modo == "pendentes":
                rows = conn.execute("SELECT * FROM imagens WHERE status = 'pendente' ORDER BY id DESC LIMIT 80").fetchall()
            else:
                rows = conn.execute("SELECT * FROM imagens ORDER BY id DESC LIMIT 80").fetchall()

        colunas = 4
        linha_atual = ctk.CTkFrame(self.scroll, fg_color="transparent")
        linha_atual.pack(fill="x", pady=5)
        
        for i, row in enumerate(rows):
            if i > 0 and i % colunas == 0:
                linha_atual = ctk.CTkFrame(self.scroll, fg_color="transparent")
                linha_atual.pack(fill="x", pady=5)
                
            frame_item = ctk.CTkFrame(linha_atual, fg_color=TEMA["bg_surface_2"], corner_radius=10)
            frame_item.pack(side="left", padx=10, pady=10, fill="both", expand=True)
            
            try:
                caminho_thumb = row['thumbnail_arquivo'] or row['arquivo']
                img = Image.open(caminho_thumb)
                img.thumbnail((150, 150))
                tk_img = ImageTk.PhotoImage(img)
                lbl_img = ctk.CTkLabel(frame_item, image=tk_img, text="")
                lbl_img.image = tk_img
                lbl_img.pack(pady=(10, 5))
            except Exception:
                ctk.CTkLabel(frame_item, text="[Erro na Imagem]").pack(pady=20)
                
            guia = row['guia'] or 'Pendente'
            status = row['status'] or 'pendente'
            ctk.CTkLabel(frame_item, text=f"Guia: {guia}", font=("Segoe UI", 12, "bold"), text_color=TEMA["texto_claro"]).pack()
            ctk.CTkLabel(frame_item, text=f"Status: {status}", font=("Segoe UI", 10), text_color="#D6E2F2").pack()
            ctk.CTkLabel(frame_item, text=row['data_inclusao'].split()[0], font=("Segoe UI", 10), text_color="#D6E2F2").pack(pady=(0, 5))

            btns = ctk.CTkFrame(frame_item, fg_color='transparent')
            btns.pack(pady=(0, 10))
            ctk.CTkButton(btns, text='Editar', width=60, height=28, fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"], command=lambda r=row: self.editar_metadados(r)).pack(side='left', padx=4)
            ctk.CTkButton(btns, text='Excluir', width=60, height=28, fg_color=TEMA["bg_surface_3"], hover_color=TEMA["borda_forte"], text_color=TEMA["texto_claro"], command=lambda img_id=row['id']: self._excluir_e_recarregar(img_id)).pack(side='left', padx=4)

    def editar_metadados(self, row):
        popup = ctk.CTkToplevel(self.app_master)
        popup.title("Editar Imagem")
        popup.geometry("300x250")
        popup.attributes('-topmost', True)
        
        ctk.CTkLabel(popup, text="Guia da Imagem:", font=("Segoe UI", 12, "bold")).pack(pady=(15,5))
        e_guia = ctk.CTkEntry(popup, width=200)
        e_guia.insert(0, row['guia'] or "")
        e_guia.pack()
        
        ctk.CTkLabel(popup, text="Status:", font=("Segoe UI", 12, "bold")).pack(pady=(15,5))
        combo_status = ctk.CTkComboBox(popup, values=["pendente", "confirmada", "descartada"], width=200)
        combo_status.set(row['status'])
        combo_status.pack()
        
        def salvar():
            with conectar_sqlite(self.arq_db) as conn:
                conn.execute("UPDATE imagens SET guia = ?, status = ? WHERE id = ?", (e_guia.get().strip(), combo_status.get(), row['id']))
                conn.commit()
            popup.destroy()
            self.carregar_imagens()
            
        ctk.CTkButton(popup, text="Salvar Atualizacao", command=salvar, fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"]).pack(pady=20)
        
        if hasattr(self.app_master, '_tematizar_popup'):
            self.app_master._tematizar_popup(popup)

    def excluir_pendentes(self):
        with conectar_sqlite(self.arq_db) as conn:
            rows = conn.execute("SELECT arquivo, thumbnail_arquivo FROM imagens WHERE status = 'pendente'").fetchall()
            for r in rows:
                remover_arquivo_seguro(r[0])
                remover_arquivo_seguro(r[1])
            conn.execute("DELETE FROM imagens WHERE status = 'pendente'")
            conn.commit()
        self.carregar_imagens()

    def excluir_duplicadas(self):
        with conectar_sqlite(self.arq_db) as conn:
            rows = conn.execute("SELECT sha1, MIN(id) as keep_id FROM imagens GROUP BY sha1 HAVING COUNT(*) > 1").fetchall()
            for r in rows:
                sha1 = r[0]
                keep_id = r[1]
                dups = conn.execute("SELECT id, arquivo, thumbnail_arquivo FROM imagens WHERE sha1 = ? AND id != ?", (sha1, keep_id)).fetchall()
                for d in dups:
                    remover_arquivo_seguro(d[1])
                    remover_arquivo_seguro(d[2])
                    conn.execute("DELETE FROM imagens WHERE id = ?", (d[0],))
            conn.commit()
        self.carregar_imagens()

    def _excluir_e_recarregar(self, img_id):
        if not os.path.exists(self.arq_db):
            return
        with conectar_sqlite(self.arq_db, row_factory=True) as conn:
            row = conn.execute('SELECT * FROM imagens WHERE id = ?', (img_id,)).fetchone()
            if row:
                for campo in ('arquivo', 'thumbnail_arquivo'):
                    remover_arquivo_seguro(row[campo])
            conn.execute('DELETE FROM imagens WHERE id = ?', (img_id,))
            conn.commit()
        self.carregar_imagens()
