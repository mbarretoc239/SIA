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


class FrameHistoricoRelatorios(ctk.CTkFrame):
    def __init__(self, master, app_master):
        super().__init__(master, fg_color="transparent")
        self.app_master = app_master

        ctk.CTkLabel(self, text="Histórico de Relatórios (60 dias)", font=("Segoe UI", 26, "bold"), text_color=TEMA["texto_claro"]).pack(pady=(20, 10), anchor="w", padx=20)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=20, pady=(0, 8))
        self.entry_busca_prestador = ctk.CTkEntry(
            bar, width=260, height=34, corner_radius=8,
            placeholder_text="Pesquisar prestador..."
        )
        self.entry_busca_prestador.pack(side="left", padx=(0, 8))

        self.entry_data_inicio = ctk.CTkEntry(
            bar, width=130, height=34, corner_radius=8,
            placeholder_text="Data inicial"
        )
        self.entry_data_inicio.pack(side="left", padx=4)

        self.entry_data_fim = ctk.CTkEntry(
            bar, width=130, height=34, corner_radius=8,
            placeholder_text="Data final"
        )
        self.entry_data_fim.pack(side="left", padx=4)

        ctk.CTkButton(
            bar, text="Filtrar", width=90, command=self.carregar_historico,
            fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"]
        ).pack(side="left", padx=(8, 4))
        ctk.CTkButton(
            bar, text="Limpar", width=90, command=self._limpar_filtros_historico,
            fg_color=TEMA["bg_surface_3"], hover_color=TEMA["azul_sidebar_hover"]
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            bar, text="Atualizar Histórico", command=self.carregar_historico,
            fg_color=TEMA["azul_primario"], hover_color=TEMA["azul_hover"]
        ).pack(side="right")

        self.lbl_resumo = ctk.CTkLabel(
            self,
            text="Pesquise por prestador e filtre por intervalo em DD/MM/AAAA.",
            font=("Segoe UI", 12),
            text_color=TEMA["texto_secundario"]
        )
        self.lbl_resumo.pack(fill="x", padx=20, pady=(0, 2), anchor="w")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=TEMA["bg_surface_2"])
        self.scroll.pack(fill="both", expand=True, padx=20, pady=10)

        for entry in (self.entry_busca_prestador, self.entry_data_inicio, self.entry_data_fim):
            entry.bind("<Return>", lambda _e: self.carregar_historico())

        self.carregar_historico()

    def _limpar_filtros_historico(self):
        for entry in (self.entry_busca_prestador, self.entry_data_inicio, self.entry_data_fim):
            entry.delete(0, 'end')
        self.carregar_historico()

    def _parse_data_filtro_historico(self, texto):
        texto = (texto or "").strip()
        if not texto:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(texto, fmt).date()
            except ValueError:
                continue
        raise ValueError("Use o formato DD/MM/AAAA nas datas.")

    def _parse_data_registro_historico(self, texto):
        texto = (texto or "").strip()
        if not texto:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
            try:
                return datetime.strptime(texto, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(texto)
        except ValueError:
            return None

    def _obter_filtros_historico(self):
        prestador = self.entry_busca_prestador.get().strip().lower()
        txt_inicio = self.entry_data_inicio.get().strip()
        txt_fim = self.entry_data_fim.get().strip()

        try:
            data_inicio = self._parse_data_filtro_historico(txt_inicio)
            data_fim = self._parse_data_filtro_historico(txt_fim)
        except ValueError as erro:
            self.lbl_resumo.configure(text=str(erro), text_color=TEMA["erro"])
            return None

        if data_inicio and data_fim and data_inicio > data_fim:
            self.lbl_resumo.configure(
                text="A data inicial nao pode ser maior que a data final.",
                text_color=TEMA["erro"]
            )
            return None

        return prestador, data_inicio, data_fim

    def _atualizar_resumo_historico(self, total, prestador="", data_inicio=None, data_fim=None, erro=False):
        if erro:
            return

        partes = [f"{total} relatorio(s) encontrado(s)"]
        if prestador:
            partes.append(f"prestador contendo '{prestador}'")
        if data_inicio and data_fim:
            partes.append(
                f"entre {data_inicio.strftime('%d/%m/%Y')} e {data_fim.strftime('%d/%m/%Y')}"
            )
        elif data_inicio:
            partes.append(f"a partir de {data_inicio.strftime('%d/%m/%Y')}")
        elif data_fim:
            partes.append(f"ate {data_fim.strftime('%d/%m/%Y')}")

        self.lbl_resumo.configure(
            text=" | ".join(partes),
            text_color=TEMA["texto_secundario"]
        )

    def carregar_historico(self):
        for widget in self.scroll.winfo_children():
            widget.destroy()

        filtros = self._obter_filtros_historico()
        if filtros is None:
            ctk.CTkLabel(
                self.scroll,
                text="Filtro de data invalido. Use DD/MM/AAAA.",
                text_color=TEMA["erro"]
            ).pack(pady=20)
            return

        prestador_busca, data_inicio, data_fim = filtros

        if not hasattr(self.app_master, 'arq_historico_db') or not os.path.exists(self.app_master.arq_historico_db):
            self._atualizar_resumo_historico(0, prestador_busca, data_inicio, data_fim)
            ctk.CTkLabel(self.scroll, text="Nenhum relatorio gerado ainda.", text_color="#D6E2F2").pack(pady=20)
            return

        with conectar_sqlite(self.app_master.arq_historico_db, row_factory=True) as conn:
            rows = conn.execute("SELECT * FROM historico ORDER BY id DESC").fetchall()

        filtrados = []
        for row in rows:
            nome_prestador = str(row['prestador'] or "")
            if prestador_busca and prestador_busca not in nome_prestador.lower():
                continue
            data_row = self._parse_data_registro_historico(str(row['data_criacao'] or ""))
            if data_row:
                data_row_date = data_row.date()
                if data_inicio and data_row_date < data_inicio:
                    continue
                if data_fim and data_row_date > data_fim:
                    continue
            filtrados.append(row)

        self._atualizar_resumo_historico(len(filtrados), prestador_busca, data_inicio, data_fim)

        if not filtrados:
            ctk.CTkLabel(
                self.scroll,
                text="Nenhum relatório encontrado para os filtros aplicados.",
                font=("Segoe UI", 13),
                text_color=TEMA["texto_muted"]
            ).pack(pady=30)
            return

        limite = 50
        truncado = len(filtrados) > limite
        filtrados_view = filtrados[:limite]

        for row in filtrados_view:
            card = ctk.CTkFrame(
                self.scroll,
                fg_color=TEMA["bg_surface"],
                corner_radius=12,
                border_width=1,
                border_color=TEMA["borda"]
            )
            card.pack(fill="x", pady=6, padx=4)

            topo_card = ctk.CTkFrame(card, fg_color="transparent")
            topo_card.pack(fill="x", padx=14, pady=(12, 4))

            ctk.CTkLabel(
                topo_card,
                text=str(row['prestador'] or "Prestador não informado"),
                font=("Segoe UI", 13, "bold"),
                text_color=TEMA["texto_claro"]
            ).pack(side="left")

            data_fmt = ""
            data_obj = self._parse_data_registro_historico(str(row['data_criacao'] or ""))
            if data_obj:
                data_fmt = data_obj.strftime("%d/%m/%Y %H:%M")

            ctk.CTkLabel(
                topo_card,
                text=data_fmt,
                font=("Segoe UI", 11),
                text_color=TEMA["texto_muted"]
            ).pack(side="right")

            info_line = f"Processo: {row['processo'] or 'N/A'}   |   Mês: {row['mes_ref'] or 'N/A'}"
            ctk.CTkLabel(
                card,
                text=info_line,
                font=("Segoe UI", 11),
                text_color=TEMA["texto_secundario"]
            ).pack(anchor="w", padx=14, pady=(0, 8))

            texto_rel = str(row['texto_relatorio'] or "")
            if texto_rel:
                preview = texto_rel[:200].replace("\n", " ")
                if len(texto_rel) > 200:
                    preview += "..."
                ctk.CTkLabel(
                    card,
                    text=preview,
                    font=("Segoe UI", 11),
                    text_color=TEMA["texto_secundario"],
                    justify="left",
                    wraplength=700
                ).pack(anchor="w", padx=14, pady=(0, 8))

            def _copiar(t=texto_rel):
                try:
                    self.app_master.clipboard_clear()
                    self.app_master.clipboard_append(t)
                except Exception:
                    pass

            ctk.CTkButton(
                card,
                text="Copiar Relatório",
                width=140, height=30,
                fg_color=TEMA["azul_primario"],
                hover_color=TEMA["azul_hover"],
                font=("Segoe UI", 11, "bold"),
                command=_copiar
            ).pack(anchor="e", padx=14, pady=(0, 12))

        if truncado:
            ctk.CTkLabel(
                self.scroll,
                text="Exibindo os 50 registros mais recentes. Refine os filtros para ver mais antigos.",
                font=("Segoe UI", 12, "italic"),
                text_color=TEMA["aviso"]
            ).pack(pady=20)

