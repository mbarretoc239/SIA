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

from core.settings import TEMA, DB_NAME
from shared.utils import widget_existe, corrigir_mojibake, abrir_url_padrao, copiar_texto_clipboard


class FrameTextosPrestador(ctk.CTkFrame):
    def __init__(self, master, app_master):
        super().__init__(master, fg_color="transparent")
        self.app_master = app_master
        self._id_editando = None

        pasta_base = getattr(app_master, 'pasta_dados', str(Path.home()))
        self.arq_db = os.path.join(pasta_base, 'textos_prestador.sqlite3')
        self._init_db()

        # --- Cabeçalho ---
        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.pack(fill="x", padx=20, pady=(20, 6))
        ctk.CTkLabel(cabecalho, text="Textos para Prestador", font=("Segoe UI", 26, "bold"),
                     text_color=TEMA["texto_claro"]).pack(side="left")
        ctk.CTkButton(cabecalho, text="+ Novo Texto", height=36, corner_radius=10,
                      fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"],
                      font=("Segoe UI", 13, "bold"), command=self._abrir_popup_novo).pack(side="right")

        # --- Busca ---
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=20, pady=(0, 10))
        self.entry_busca = ctk.CTkEntry(barra, placeholder_text="Buscar por título ou conteúdo...",
                                        height=34, corner_radius=8)
        self.entry_busca.pack(fill="x")
        self.entry_busca.bind("<KeyRelease>", lambda e: self._carregar_cards())

        # --- Grid de Cards ---
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self._carregar_cards()

    def _init_db(self):
        with conectar_sqlite(self.arq_db) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS textos ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "titulo TEXT NOT NULL, "
                "conteudo TEXT NOT NULL DEFAULT '', "
                "criado_em TEXT, "
                "editado_em TEXT)"
            )
            conn.commit()

    def _carregar_cards(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        termo = self.entry_busca.get().strip().lower() if hasattr(self, 'entry_busca') else ""
        with conectar_sqlite(self.arq_db, row_factory=True) as conn:
            rows = conn.execute("SELECT * FROM textos ORDER BY editado_em DESC").fetchall()

        colunas = 2
        grade = ctk.CTkFrame(self.scroll, fg_color="transparent")
        grade.pack(fill="both", expand=True)
        grade.grid_columnconfigure((0, 1), weight=1)

        linha, col = 0, 0
        for row in rows:
            if termo and termo not in row['titulo'].lower() and termo not in row['conteudo'].lower():
                continue
            card = ctk.CTkFrame(grade, fg_color=TEMA["bg_surface_2"], corner_radius=12,
                                border_width=1, border_color=TEMA["borda"])
            card.grid(row=linha, column=col, sticky="nsew", padx=8, pady=8)

            ctk.CTkLabel(card, text=row['titulo'], font=("Segoe UI", 14, "bold"),
                         text_color=TEMA["texto_claro"], wraplength=320, anchor="w",
                         justify="left").pack(anchor="w", padx=14, pady=(14, 4))

            preview = row['conteudo'][:200] + ("..." if len(row['conteudo']) > 200 else "")
            ctk.CTkLabel(card, text=preview, font=("Segoe UI", 12),
                         text_color=TEMA["texto_secundario"], wraplength=320, anchor="w",
                         justify="left").pack(anchor="w", padx=14, pady=(0, 6))

            data_label = row['editado_em'] or row['criado_em'] or ""
            if data_label:
                ctk.CTkLabel(card, text=f"Editado: {data_label}",
                             font=("Segoe UI", 10), text_color=TEMA["texto_muted"]).pack(anchor="w", padx=14)

            btns = ctk.CTkFrame(card, fg_color="transparent")
            btns.pack(anchor="w", padx=10, pady=(6, 12))
            ctk.CTkButton(btns, text="Editar", width=64, height=28,
                          fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"],
                          command=lambda r=row: self._abrir_popup_editar(r)).pack(side="left", padx=4)
            ctk.CTkButton(btns, text="Copiar", width=64, height=28,
                          fg_color=TEMA["bg_surface_3"], hover_color=TEMA["azul_sidebar_hover"],
                          command=lambda r=row: self._copiar(r['conteudo'])).pack(side="left", padx=4)
            ctk.CTkButton(btns, text="Excluir", width=64, height=28,
                          fg_color="#E74C3C", hover_color="#C0392B",
                          command=lambda r=row: self._excluir(r['id'])).pack(side="left", padx=4)

            col += 1
            if col >= colunas:
                col = 0
                linha += 1

        if linha == 0 and col == 0:
            ctk.CTkLabel(self.scroll, text="Nenhum texto cadastrado ainda. Clique em '+ Novo Texto' para começar.",
                         font=("Segoe UI", 14), text_color=TEMA["texto_muted"]).pack(pady=40)

    def _abrir_popup_novo(self):
        self._abrir_popup(None)

    def _abrir_popup_editar(self, row):
        self._abrir_popup(row)

    def _abrir_popup(self, row):
        popup = ctk.CTkToplevel(self.app_master)
        popup.title("Editar Texto" if row else "Novo Texto")
        popup.geometry("680x520")
        popup.attributes('-topmost', True)
        popup.grab_set()
        self.app_master._tematizar_popup(popup)

        ctk.CTkLabel(popup, text="Título:", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(18, 3))
        entry_titulo = ctk.CTkEntry(popup, height=36, corner_radius=8, font=("Segoe UI", 13))
        entry_titulo.pack(fill="x", padx=20)
        if row:
            entry_titulo.insert(0, row['titulo'])

        ctk.CTkLabel(popup, text="Texto:", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(14, 3))
        txt = ctk.CTkTextbox(popup, font=("Segoe UI", 13), corner_radius=8,
                             fg_color=TEMA["bg_surface"], text_color=TEMA["texto_claro"])
        txt.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        if row:
            txt.insert("0.0", row['conteudo'])

        btns = ctk.CTkFrame(popup, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(0, 18))

        def salvar():
            titulo = entry_titulo.get().strip()
            conteudo = txt.get("0.0", "end").strip()
            if not titulo:
                return
            agora = datetime.now().strftime('%d/%m/%Y %H:%M')
            with conectar_sqlite(self.arq_db) as conn:
                if row:
                    conn.execute("UPDATE textos SET titulo=?, conteudo=?, editado_em=? WHERE id=?",
                                 (titulo, conteudo, agora, row['id']))
                else:
                    conn.execute("INSERT INTO textos (titulo, conteudo, criado_em, editado_em) VALUES (?,?,?,?)",
                                 (titulo, conteudo, agora, agora))
                conn.commit()
            popup.destroy()
            self._carregar_cards()

        ctk.CTkButton(btns, text="Salvar", height=36, fg_color=TEMA["azul_primario"],
                      hover_color=TEMA["azul_hover"], font=("Segoe UI", 13, "bold"),
                      command=salvar).pack(side="right", padx=4)
        ctk.CTkButton(btns, text="Cancelar", height=36, fg_color=TEMA["bg_surface_3"],
                      hover_color=TEMA["azul_sidebar_hover"],
                      command=popup.destroy).pack(side="right", padx=4)

    def _copiar(self, texto):
        copiar_texto_clipboard(texto, self.app_master)
        try:
            self.app_master.mostrar_toast("ðŸ“‹ Texto copiado!")
        except Exception:
            pass

    def _excluir(self, texto_id):
        with conectar_sqlite(self.arq_db) as conn:
            conn.execute("DELETE FROM textos WHERE id=?", (texto_id,))
            conn.commit()
        self._carregar_cards()


# =====================================================================
# TELA: LINKS IMPORTANTES
# =====================================================================


