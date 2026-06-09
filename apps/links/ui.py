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


class FrameLinksImportantes(ctk.CTkFrame):
    def __init__(self, master, app_master):
        super().__init__(master, fg_color="transparent")
        self.app_master = app_master

        pasta_base = getattr(app_master, 'pasta_dados', str(Path.home()))
        self.arq_db = os.path.join(pasta_base, 'links_importantes.sqlite3')
        self._init_db()

        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.pack(fill="x", padx=20, pady=(20, 6))
        ctk.CTkLabel(
            cabecalho,
            text="Links Importantes",
            font=("Segoe UI", 26, "bold"),
            text_color=TEMA["texto_claro"]
        ).pack(side="left")
        ctk.CTkButton(
            cabecalho,
            text="+ Novo Link",
            height=36,
            corner_radius=10,
            fg_color=TEMA["azul_primario"],
            hover_color=TEMA["azul_hover"],
            font=("Segoe UI", 13, "bold"),
            command=self._abrir_popup_novo
        ).pack(side="right")

        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=20, pady=(0, 10))
        self.entry_busca = ctk.CTkEntry(
            barra,
            placeholder_text="Buscar por titulo ou link...",
            height=34,
            corner_radius=8
        )
        self.entry_busca.pack(fill="x")
        self.entry_busca.bind("<KeyRelease>", lambda e: self._carregar_cards())

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self._carregar_cards()

    def _init_db(self):
        with conectar_sqlite(self.arq_db) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS links ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "titulo TEXT NOT NULL, "
                "url TEXT NOT NULL, "
                "criado_em TEXT, "
                "editado_em TEXT)"
            )
            conn.commit()

    def _normalizar_link(self, url):
        link = (url or "").strip()
        if not link:
            return ""
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9+\-.]*://', link):
            link = "https://" + link
        return link

    def _carregar_cards(self):
        for w in self.scroll.winfo_children():
            w.destroy()

        termo = self.entry_busca.get().strip().lower() if hasattr(self, 'entry_busca') else ""
        with conectar_sqlite(self.arq_db, row_factory=True) as conn:
            rows = conn.execute("SELECT * FROM links ORDER BY editado_em DESC, id DESC").fetchall()

        colunas = 2
        grade = ctk.CTkFrame(self.scroll, fg_color="transparent")
        grade.pack(fill="both", expand=True)
        grade.grid_columnconfigure((0, 1), weight=1)

        linha, col = 0, 0
        for row in rows:
            titulo = str(row['titulo'] or "")
            url = str(row['url'] or "")
            if termo and termo not in titulo.lower() and termo not in url.lower():
                continue

            card = ctk.CTkFrame(
                grade,
                fg_color=TEMA["bg_surface_2"],
                corner_radius=12,
                border_width=1,
                border_color=TEMA["borda"]
            )
            card.grid(row=linha, column=col, sticky="nsew", padx=8, pady=8)

            ctk.CTkLabel(
                card,
                text=titulo,
                font=("Segoe UI", 14, "bold"),
                text_color=TEMA["texto_claro"],
                wraplength=320,
                anchor="w",
                justify="left"
            ).pack(anchor="w", padx=14, pady=(14, 4))

            ctk.CTkLabel(
                card,
                text=url,
                font=("Segoe UI", 12),
                text_color=TEMA["texto_secundario"],
                wraplength=320,
                anchor="w",
                justify="left"
            ).pack(anchor="w", padx=14, pady=(0, 6))

            data_label = row['editado_em'] or row['criado_em'] or ""
            if data_label:
                ctk.CTkLabel(
                    card,
                    text=f"Editado: {data_label}",
                    font=("Segoe UI", 10),
                    text_color=TEMA["texto_muted"]
                ).pack(anchor="w", padx=14)

            btns = ctk.CTkFrame(card, fg_color="transparent")
            btns.pack(anchor="w", padx=10, pady=(6, 12))
            ctk.CTkButton(
                btns,
                text="Editar",
                width=64,
                height=28,
                fg_color=TEMA["azul_primario"],
                hover_color=TEMA["azul_hover"],
                command=lambda r=row: self._abrir_popup_editar(r)
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                btns,
                text="Abrir",
                width=64,
                height=28,
                fg_color="#1F8A5B",
                hover_color="#176746",
                command=lambda r=row: self._abrir_link(r['url'])
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                btns,
                text="Excluir",
                width=64,
                height=28,
                fg_color="#E74C3C",
                hover_color="#C0392B",
                command=lambda r=row: self._excluir(r['id'])
            ).pack(side="left", padx=4)

            col += 1
            if col >= colunas:
                col = 0
                linha += 1

        if linha == 0 and col == 0:
            ctk.CTkLabel(
                self.scroll,
                text="Nenhum link cadastrado ainda. Clique em '+ Novo Link' para começar.",
                font=("Segoe UI", 14),
                text_color=TEMA["texto_muted"]
            ).pack(pady=40)

    def _abrir_popup_novo(self):
        self._abrir_popup(None)

    def _abrir_popup_editar(self, row):
        self._abrir_popup(row)

    def _abrir_popup(self, row):
        popup = ctk.CTkToplevel(self.app_master)
        popup.title("Editar Link" if row else "Novo Link")
        popup.geometry("720x260")
        popup.attributes('-topmost', True)
        popup.grab_set()
        self.app_master._tematizar_popup(popup)

        ctk.CTkLabel(popup, text="Titulo:", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(18, 3))
        entry_titulo = ctk.CTkEntry(popup, height=36, corner_radius=8, font=("Segoe UI", 13))
        entry_titulo.pack(fill="x", padx=20)
        if row:
            entry_titulo.insert(0, row['titulo'])

        ctk.CTkLabel(popup, text="Link:", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(14, 3))
        entry_link = ctk.CTkEntry(popup, height=36, corner_radius=8, font=("Segoe UI", 13))
        entry_link.pack(fill="x", padx=20)
        if row:
            entry_link.insert(0, row['url'])

        ctk.CTkLabel(
            popup,
            text="Dica: se o link não começar com http:// ou https://, o app completa automaticamente.",
            font=("Segoe UI", 11),
            text_color=TEMA["texto_secundario"]
        ).pack(anchor="w", padx=20, pady=(8, 10))

        btns = ctk.CTkFrame(popup, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(0, 18))

        def salvar():
            titulo = entry_titulo.get().strip()
            url = self._normalizar_link(entry_link.get())
            if not titulo or not url:
                return
            agora = datetime.now().strftime('%d/%m/%Y %H:%M')
            with conectar_sqlite(self.arq_db) as conn:
                if row:
                    conn.execute(
                        "UPDATE links SET titulo=?, url=?, editado_em=? WHERE id=?",
                        (titulo, url, agora, row['id'])
                    )
                else:
                    conn.execute(
                        "INSERT INTO links (titulo, url, criado_em, editado_em) VALUES (?,?,?,?)",
                        (titulo, url, agora, agora)
                    )
                conn.commit()
            try:
                self.app_master._renderizar_links_sidebar()
            except Exception:
                pass
            popup.destroy()
            self._carregar_cards()

        ctk.CTkButton(
            btns,
            text="Salvar",
            height=36,
            fg_color=TEMA["azul_primario"],
            hover_color=TEMA["azul_hover"],
            font=("Segoe UI", 13, "bold"),
            command=salvar
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            btns,
            text="Cancelar",
            height=36,
            fg_color=TEMA["bg_surface_3"],
            hover_color=TEMA["azul_sidebar_hover"],
            command=popup.destroy
        ).pack(side="right", padx=4)

    def _abrir_link(self, url):
        link = self._normalizar_link(url)
        if not link:
            return
        if abrir_url_padrao(link):
            try:
                self.app_master.mostrar_toast("Link aberto no navegador!")
            except Exception:
                pass
        else:
            try:
                self.app_master.mostrar_toast("Falha ao abrir o link.", cor="#E74C3C")
            except Exception:
                pass

    def _excluir(self, link_id):
        with conectar_sqlite(self.arq_db) as conn:
            conn.execute("DELETE FROM links WHERE id=?", (link_id,))
            conn.commit()
        try:
            self.app_master._renderizar_links_sidebar()
        except Exception:
            pass
        self._carregar_cards()


# =====================================================================
# TELA: BLOCO DE NOTAS
# =====================================================================


