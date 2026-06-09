from core.database import conectar_sqlite
from pathlib import Path
import customtkinter as ctk
import tkinter as tk
import os
import time
import io
import json
import sqlite3
import threading
from datetime import datetime
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageGrab

from core.settings import TEMA, DB_NAME
from shared.utils import widget_existe, corrigir_mojibake, abrir_url_padrao, copiar_texto_clipboard, registrar_erro


class FrameBlocoNotas(ctk.CTkFrame):
    def __init__(self, master, app_master):
        super().__init__(master, fg_color='transparent')
        self.app_master = app_master
        self._nota_atual_id = None
        self._imagens_nota = []   # lista de (path_str, tk_img)
        self._salvando = False

        pasta_base = getattr(app_master, 'pasta_dados', str(Path.home()))
        self.pasta_imgs = os.path.join(pasta_base, 'notas_imagens')
        os.makedirs(self.pasta_imgs, exist_ok=True)
        self.arq_db = os.path.join(pasta_base, 'bloco_notas.sqlite3')
        self._init_db()

        # ---- Layout dois painéis ----
        self.painel_esq = ctk.CTkFrame(self, fg_color=TEMA["bg_sidebar"], width=230, corner_radius=0)
        self.painel_esq.pack(side="left", fill="y")
        self.painel_esq.pack_propagate(False)

        self.painel_dir = ctk.CTkFrame(self, fg_color="transparent")
        self.painel_dir.pack(side="left", fill="both", expand=True)

        self._montar_painel_esquerdo()
        self._montar_painel_direito()
        self._carregar_lista()

    def _init_db(self):
        with conectar_sqlite(self.arq_db) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS notas ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "titulo TEXT NOT NULL DEFAULT 'Sem título', "
                "conteudo TEXT NOT NULL DEFAULT '', "
                "imagens_json TEXT NOT NULL DEFAULT '[]', "
                "criado_em TEXT, "
                "editado_em TEXT)"
            )
            conn.commit()

    # ---- Painel Esquerdo (lista) ----
    def _montar_painel_esquerdo(self):
        topo = ctk.CTkFrame(self.painel_esq, fg_color="transparent")
        topo.pack(fill="x", padx=8, pady=(14, 6))
        ctk.CTkLabel(topo, text="📝 Notas", font=("Segoe UI", 16, "bold"),
                     text_color=TEMA["texto_claro"]).pack(side="left")
        ctk.CTkButton(topo, text="+", width=32, height=32, corner_radius=8,
                      fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"],
                      font=("Segoe UI", 16, "bold"),
                      command=self._nova_nota).pack(side="right")

        self.scroll_lista = ctk.CTkScrollableFrame(self.painel_esq, fg_color="transparent")
        self.scroll_lista.pack(fill="both", expand=True, padx=4, pady=4)

    def _carregar_lista(self):
        for w in self.scroll_lista.winfo_children():
            w.destroy()
        with conectar_sqlite(self.arq_db, row_factory=True) as conn:
            notas = conn.execute("SELECT id, titulo, editado_em FROM notas ORDER BY editado_em DESC").fetchall()
        for nota in notas:
            item = ctk.CTkButton(
                self.scroll_lista,
                text=f"{nota['titulo']}\n{nota['editado_em'] or ''}",
                anchor="w", height=54, corner_radius=8,
                fg_color=TEMA["azul_sidebar_hover"] if nota['id'] == self._nota_atual_id else "transparent",
                hover_color=TEMA["azul_sidebar_hover"],
                text_color=TEMA["texto_claro"],
                font=("Segoe UI", 11),
                command=lambda n=nota: self._abrir_nota(n['id'])
            )
            item.pack(fill="x", padx=4, pady=2)

    # ---- Painel Direito (editor) ----
    def _montar_painel_direito(self):
        # Barra de título + timestamps
        barra_topo = ctk.CTkFrame(self.painel_dir, fg_color=TEMA["bg_surface"], corner_radius=0, height=50)
        barra_topo.pack(fill="x")
        barra_topo.pack_propagate(False)

        self.entry_titulo = ctk.CTkEntry(barra_topo, placeholder_text="Título da nota...",
                                         font=("Segoe UI", 15, "bold"), height=36, border_width=0,
                                         fg_color="transparent")
        self.entry_titulo.pack(side="left", fill="x", expand=True, padx=14, pady=7)

        self.lbl_timestamps = ctk.CTkLabel(barra_topo, text="", font=("Segoe UI", 10),
                                           text_color=TEMA["texto_muted"])
        self.lbl_timestamps.pack(side="right", padx=14)

        # Barra de ações
        barra_acoes = ctk.CTkFrame(self.painel_dir, fg_color=TEMA["bg_surface_2"], height=38)
        barra_acoes.pack(fill="x")
        barra_acoes.pack_propagate(False)

        ctk.CTkButton(barra_acoes, text="💾 Salvar", width=100, height=28,
                      fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"],
                      font=("Segoe UI", 12, "bold"), command=self._salvar_nota).pack(side="left", padx=8, pady=5)
        ctk.CTkButton(barra_acoes, text="🖼️ Colar Imagem", width=130, height=28,
                      fg_color=TEMA["bg_surface_3"], hover_color=TEMA["azul_sidebar_hover"],
                      font=("Segoe UI", 12), command=self._colar_imagem).pack(side="left", padx=4, pady=5)
        ctk.CTkButton(barra_acoes, text="🗑️ Excluir Nota", width=120, height=28,
                      fg_color="#E74C3C", hover_color="#C0392B",
                      font=("Segoe UI", 12), command=self._excluir_nota).pack(side="right", padx=8, pady=5)

        # Ãrea principal (texto + imagens)
        self.frame_editor = ctk.CTkScrollableFrame(self.painel_dir, fg_color=TEMA["bg_shell"])
        self.frame_editor.pack(fill="both", expand=True)

        self.txt_nota = ctk.CTkTextbox(self.frame_editor, font=("Segoe UI", 13),
                                       fg_color="transparent", text_color=TEMA["texto_claro"],
                                       wrap="word", activate_scrollbars=False)
        self.txt_nota.pack(fill="both", expand=True, padx=14, pady=10)

        # Ãrea de imagens coladas (abaixo do texto)
        self.frame_imgs = ctk.CTkFrame(self.frame_editor, fg_color="transparent")
        self.frame_imgs.pack(fill="x", padx=14, pady=(0, 14))

        # Bind Ctrl+V global para colar imagem quando esta tela estiver visível
        self.txt_nota.bind("<Control-v>", self._on_ctrl_v)
        self.txt_nota.bind("<Control-V>", self._on_ctrl_v)

        self._mostrar_placeholder()

    def _mostrar_placeholder(self):
        self.entry_titulo.configure(state="disabled")
        self.txt_nota.configure(state="disabled")
        self.lbl_timestamps.configure(text="Selecione ou crie uma nota")

    def _limpar_editor(self):
        self.txt_nota.configure(state="normal")
        self.txt_nota.delete("0.0", "end")
        self.entry_titulo.configure(state="normal")
        self.entry_titulo.delete(0, "end")
        self._limpar_imagens_exibidas()

    def _limpar_imagens_exibidas(self):
        for w in self.frame_imgs.winfo_children():
            w.destroy()
        self._imagens_nota = []

    def _nova_nota(self):
        self._nota_atual_id = None
        self._limpar_editor()
        self.lbl_timestamps.configure(text="Nova nota â€” ainda não salva")
        self.entry_titulo.focus()

    def _abrir_nota(self, nota_id):
        self._nota_atual_id = nota_id
        with conectar_sqlite(self.arq_db, row_factory=True) as conn:
            row = conn.execute("SELECT * FROM notas WHERE id=?", (nota_id,)).fetchone()
        if not row:
            return
        self._limpar_editor()
        self.entry_titulo.insert(0, row['titulo'])
        self.txt_nota.insert("0.0", row['conteudo'])
        ts = f"Criado: {row['criado_em'] or '?'}  |  Editado: {row['editado_em'] or '?'}"
        self.lbl_timestamps.configure(text=ts)

        # Carregar imagens
        import json as _json
        try:
            imgs = _json.loads(row['imagens_json'] or '[]')
        except Exception:
            imgs = []
        for path in imgs:
            self._exibir_imagem_no_editor(path)

        self._carregar_lista()

    def _salvar_nota(self):
        titulo = self.entry_titulo.get().strip() or "Sem título"
        conteudo = self.txt_nota.get("0.0", "end").strip()
        agora = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        import json as _json
        imgs_json = _json.dumps([p for p, _ in self._imagens_nota])

        with conectar_sqlite(self.arq_db) as conn:
            if self._nota_atual_id:
                conn.execute(
                    "UPDATE notas SET titulo=?, conteudo=?, imagens_json=?, editado_em=? WHERE id=?",
                    (titulo, conteudo, imgs_json, agora, self._nota_atual_id)
                )
            else:
                cur = conn.execute(
                    "INSERT INTO notas (titulo, conteudo, imagens_json, criado_em, editado_em) VALUES (?,?,?,?,?)",
                    (titulo, conteudo, imgs_json, agora, agora)
                )
                self._nota_atual_id = cur.lastrowid
            conn.commit()

        self.lbl_timestamps.configure(text=f"Salvo em: {agora}")
        self._carregar_lista()
        try:
            self.app_master.mostrar_toast("💾 Nota salva!")
        except Exception:
            pass

    def _excluir_nota(self):
        if not self._nota_atual_id:
            return
        with conectar_sqlite(self.arq_db) as conn:
            conn.execute("DELETE FROM notas WHERE id=?", (self._nota_atual_id,))
            conn.commit()
        self._nota_atual_id = None
        self._limpar_editor()
        self._mostrar_placeholder()
        self._carregar_lista()

    def _on_ctrl_v(self, event):
        try:
            clip = ImageGrab.grabclipboard()
            if isinstance(clip, Image.Image):
                self._salvar_e_exibir_imagem(clip)
                return "break"   # impede colar texto padrão
        except Exception:
            pass
        return None   # deixa Tk colar texto normalmente

    def _colar_imagem(self):
        try:
            clip = ImageGrab.grabclipboard()
            if isinstance(clip, Image.Image):
                self._salvar_e_exibir_imagem(clip)
            elif isinstance(clip, list) and clip:
                img = Image.open(clip[0])
                self._salvar_e_exibir_imagem(img)
            else:
                self.app_master.mostrar_toast("Nenhuma imagem na área de transferência.", cor="#E74C3C")
        except Exception as e:
            registrar_erro("Erro ao colar imagem no bloco de notas", e)

    def _salvar_e_exibir_imagem(self, img_pil):
        nome = f"nota_img_{int(time.time()*1000)}.png"
        caminho = os.path.join(self.pasta_imgs, nome)
        img_pil.save(caminho, "PNG")
        self._exibir_imagem_no_editor(caminho)

    def _exibir_imagem_no_editor(self, caminho):
        try:
            img = Image.open(caminho)
            img.thumbnail((480, 480), Image.Resampling.LANCZOS)
            tk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            bloco = ctk.CTkFrame(self.frame_imgs, fg_color=TEMA["bg_surface_2"], corner_radius=8)
            bloco.pack(anchor="w", pady=6)
            lbl = ctk.CTkLabel(bloco, image=tk_img, text="")
            lbl.image = tk_img
            lbl.pack(padx=8, pady=8)

            def remover(c=caminho, b=bloco):
                self._imagens_nota = [(p, t) for p, t in self._imagens_nota if p != c]
                b.destroy()

            ctk.CTkButton(bloco, text="✖ Remover imagem", width=130, height=24,
                          fg_color="#E74C3C", hover_color="#C0392B",
                          font=("Segoe UI", 11), command=remover).pack(pady=(0, 6))
            self._imagens_nota.append((caminho, tk_img))
        except Exception as e:
            registrar_erro("Erro ao exibir imagem no bloco de notas", e)

# =====================================================================
# TELA DE HISTORICO DE RELATORIOS V5
# =====================================================================


