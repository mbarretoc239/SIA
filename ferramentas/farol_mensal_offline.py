"""Farol Mensal offline -- mesma classificação S/N/PAR/REVISAR do SIA
(views/9_Farol_Mensal.py), rodando 100% local: sem Turso, sem Supabase, sem
internet nenhuma. Motivo: evitar bater de novo no limite de leitura do Turso
(ver docs/turso_bloqueado_2026-09-23.md) rodando o Farol repetidamente
dentro do app pra experimentar filtro.

Reusa INTEGRALMENTE a lógica do SIA (core/farol_mensal.py,
services/farol_mensal/, core/amostragem.py, core/relatorio_5201.py) -- só
troca a ENTRADA (arquivos escolhidos aqui) pelo que lá vem do Turso/Supabase.
Nada aqui duplica regra de classificação.

Precisa de 2 arquivos sempre reimportados no SIA (mesmos que você já tem no
PC pra importar em Configurações):
  - REL5201 do mês (.xlsx ou .csv)
  - Planilha mensal da base IA (.xlsx)
E de um JSON com as regras de crítica + catálogo de procedimentos, que não
muda todo mês -- gere/atualize com:
    python scripts/exportar_dados_farol_offline.py
(esse script PRECISA de rede/Supabase; o Farol offline em si não precisa
mais depois que o JSON existe).

Uso:
    python ferramentas/farol_mensal_offline.py
"""
import io
import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core.amostragem import preparar_registros_base_ia, preparar_registros_5310  # noqa: E402
from core.farol_mensal import (  # noqa: E402
    CRITICA_COM,
    CRITICA_SEM,
    CRITICA_TODOS,
    DIGITADOR_NAO,
    DIGITADOR_SIM,
    DIGITADOR_TODOS,
    EXECUCOES_DISPONIVEIS,
    MODALIDADE_SEMPRE_EXCLUIDA,
    FiltrosFarol,
    agregar_glosas_5310,
    agregar_processos_farol,
    aplicar_filtros,
    montar_base_farol,
    montar_operacional,
    opcoes_especialidades,
    resumo_farol,
    separar_para_cruzamento,
)
from core.relatorio_5201 import ler_relatorio_5201  # noqa: E402
from services.farol_mensal.erros import ColunasFaltandoError  # noqa: E402
from services.farol_mensal.processamento import (  # noqa: E402
    ABAS_SAIDA,
    _com_ordem_numerica,
    abas_de_ocorrencias,
    carregar_ocorrencias,
    cruzar,
)

JSON_PADRAO = Path(__file__).resolve().parent / "dados_farol_offline.json"
_OPERADORES = ["Maior que", "Menor que", "Maior ou igual a", "Menor ou igual a", "Igual a"]


class _ArquivoBinario(io.BytesIO):
    """Shim pra ler_relatorio_5201: ela decide csv/xlsx por `.name`, que um
    caminho puro (str) não tem. Carrega o arquivo inteiro em memória -- a
    5201 tem milhares de linhas, não centenas de milhares (diferente da base
    IA, que é lida via openpyxl read_only direto do caminho, sem esse shim)."""

    def __init__(self, caminho: str):
        with open(caminho, "rb") as f:
            super().__init__(f.read())
        self.name = Path(caminho).name


def _limpar_lista_par(caminho: str) -> set:
    """1ª aba, 3 primeiras colunas (Execução/Processo/Prestador -- mesmo
    layout da lista PAR mensal, ver views/1_Configuracoes.py). Devolve só os
    números de processo (str), ignorando linha sem processo preenchido."""
    import pandas as pd

    df = pd.read_excel(caminho, sheet_name=0).iloc[:, :3]
    df.columns = ["EXECUCAO", "PROCESSO", "PRESTADOR"]
    processos = df["PROCESSO"].apply(lambda v: str(int(v)) if pd.notna(v) else None)
    return set(processos.dropna())


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Farol Mensal offline")
        self.geometry("980x860")

        self.caminho_5201 = tk.StringVar()
        self.caminho_ia = tk.StringVar()
        self.caminho_5310 = tk.StringVar()
        self.caminho_par = tk.StringVar()
        self.caminho_json = tk.StringVar(value=str(JSON_PADRAO) if JSON_PADRAO.exists() else "")
        self.caminho_ocorrencias = tk.StringVar()
        self.aba_ocorrencias = tk.StringVar()
        self.incluir_compulsorio = tk.BooleanVar(value=False)
        self.gerar_operacional = tk.BooleanVar(value=False)

        self.filtro_critica = tk.StringVar(value=CRITICA_TODOS)
        self.filtro_digitador = tk.StringVar(value=DIGITADOR_TODOS)
        self.op_liberacao = tk.StringVar(value=_OPERADORES[0])
        self.val_liberacao = tk.StringVar()
        self.op_biometria = tk.StringVar(value=_OPERADORES[0])
        self.val_biometria = tk.StringVar()

        self.base = None
        self.mapa_offline = None
        self.ordens_par: set = set()
        self.resultado = None
        self.operacional_df = None

        self._montar_ui()

    # --- UI ---

    def _montar_ui(self):
        pad = {"padx": 8, "pady": 4}

        f_arquivos = ttk.LabelFrame(self, text="1. Arquivos")
        f_arquivos.pack(fill="x", **pad)
        self._linha_arquivo(f_arquivos, "REL5201 (obrigatório)", self.caminho_5201,
                             [("Planilhas", "*.xlsx *.csv")])
        self._linha_arquivo(f_arquivos, "Base IA mensal (obrigatório)", self.caminho_ia,
                             [("Excel", "*.xlsx")])
        self._linha_arquivo(f_arquivos, "REL5310 (opcional)", self.caminho_5310,
                             [("Excel", "*.xlsx")])
        self._linha_arquivo(f_arquivos, "Lista PAR (opcional)", self.caminho_par,
                             [("Excel", "*.xlsx")])
        self._linha_arquivo(f_arquivos, "Regras críticas (JSON)", self.caminho_json,
                             [("JSON", "*.json")])
        ttk.Button(f_arquivos, text="1. Carregar base", command=self._carregar_base).pack(pady=6)
        self.lbl_status_base = ttk.Label(f_arquivos, text="")
        self.lbl_status_base.pack(pady=(0, 6))

        f_ocorrencias = ttk.LabelFrame(self, text="2. Ocorrências do mês anterior (5307)")
        f_ocorrencias.pack(fill="x", **pad)
        self._linha_arquivo(f_ocorrencias, "Planilha 5307 (obrigatório p/ resultado)",
                             self.caminho_ocorrencias, [("Planilhas", "*.xlsx *.csv")],
                             on_escolher=self._ao_escolher_ocorrencias)
        linha_aba = ttk.Frame(f_ocorrencias)
        linha_aba.pack(fill="x", padx=8, pady=2)
        ttk.Label(linha_aba, text="Aba:").pack(side="left")
        self.combo_aba = ttk.Combobox(linha_aba, textvariable=self.aba_ocorrencias, state="readonly", width=30)
        self.combo_aba.pack(side="left", padx=4)
        ttk.Checkbutton(
            f_ocorrencias, text="Incluir no SIM os fechamentos compulsórios",
            variable=self.incluir_compulsorio,
        ).pack(anchor="w", padx=8, pady=2)

        f_filtros = ttk.LabelFrame(self, text="3. Filtros")
        f_filtros.pack(fill="x", **pad)

        linha1 = ttk.Frame(f_filtros)
        linha1.pack(fill="x", padx=8, pady=2)
        ttk.Label(linha1, text="Especialidade:").pack(side="left")
        for valor in (CRITICA_TODOS, CRITICA_COM, CRITICA_SEM):
            ttk.Radiobutton(linha1, text=valor, value=valor, variable=self.filtro_critica,
                             command=self._atualizar_estado_extras).pack(side="left", padx=4)

        linha2 = ttk.Frame(f_filtros)
        linha2.pack(fill="x", padx=8, pady=2)
        ttk.Label(linha2, text="Aceitar também estas especialidades (só em 'Sem críticas'):").pack(anchor="w")
        self.lista_extras = tk.Listbox(linha2, selectmode="multiple", height=4, exportselection=False)
        self.lista_extras.pack(fill="x", pady=2)

        linha3 = ttk.Frame(f_filtros)
        linha3.pack(fill="x", padx=8, pady=2)
        self.lista_status = self._bloco_multiselect(linha3, "Status")
        self.lista_execucao = self._bloco_multiselect(linha3, "Execução")
        self.lista_modalidade = self._bloco_multiselect(linha3, "Modalidade")

        linha4 = ttk.Frame(f_filtros)
        linha4.pack(fill="x", padx=8, pady=2)
        ttk.Label(linha4, text="Login de digitador?").pack(side="left")
        for valor in (DIGITADOR_TODOS, DIGITADOR_SIM, DIGITADOR_NAO):
            ttk.Radiobutton(linha4, text=valor, value=valor, variable=self.filtro_digitador).pack(side="left", padx=4)

        linha5 = ttk.Frame(f_filtros)
        linha5.pack(fill="x", padx=8, pady=2)
        ttk.Label(linha5, text="% Liberação IA:").pack(side="left")
        ttk.Combobox(linha5, textvariable=self.op_liberacao, values=_OPERADORES, state="readonly", width=16).pack(side="left", padx=4)
        ttk.Entry(linha5, textvariable=self.val_liberacao, width=8).pack(side="left")
        ttk.Label(linha5, text="     % Biometria:").pack(side="left")
        ttk.Combobox(linha5, textvariable=self.op_biometria, values=_OPERADORES, state="readonly", width=16).pack(side="left", padx=4)
        ttk.Entry(linha5, textvariable=self.val_biometria, width=8).pack(side="left")

        ttk.Checkbutton(
            f_filtros, text="Gerar aba Operacional (crítico/APP fora do FAROL e fora da lista PAR)",
            variable=self.gerar_operacional,
        ).pack(anchor="w", padx=8, pady=4)

        ttk.Button(f_filtros, text="2. Classificar e gerar resultado", command=self._classificar).pack(pady=6)

        f_resultado = ttk.LabelFrame(self, text="4. Resultado")
        f_resultado.pack(fill="both", expand=True, **pad)
        colunas = ("balde", "processos", "procedimentos", "pct")
        self.tabela = ttk.Treeview(f_resultado, columns=colunas, show="headings", height=8)
        for col, titulo in zip(colunas, ("Balde", "Processos", "Procedimentos", "% do mês")):
            self.tabela.heading(col, text=titulo)
            self.tabela.column(col, width=160, anchor="center")
        self.tabela.pack(fill="both", expand=True, padx=8, pady=4)
        self.lbl_resumo = ttk.Label(f_resultado, text="", justify="left")
        self.lbl_resumo.pack(anchor="w", padx=8, pady=4)
        ttk.Button(f_resultado, text="Salvar Excel...", command=self._salvar_excel).pack(pady=6)

        self._atualizar_estado_extras()

    def _bloco_multiselect(self, pai, titulo) -> tk.Listbox:
        frame = ttk.Frame(pai)
        frame.pack(side="left", fill="both", expand=True, padx=4)
        ttk.Label(frame, text=titulo).pack(anchor="w")
        lista = tk.Listbox(frame, selectmode="multiple", height=5, exportselection=False)
        lista.pack(fill="both", expand=True)
        return lista

    def _linha_arquivo(self, pai, rotulo, variavel, tipos, on_escolher=None):
        linha = ttk.Frame(pai)
        linha.pack(fill="x", padx=8, pady=2)
        ttk.Label(linha, text=rotulo, width=32).pack(side="left")
        ttk.Entry(linha, textvariable=variavel).pack(side="left", fill="x", expand=True, padx=4)

        def _escolher():
            caminho = filedialog.askopenfilename(filetypes=tipos + [("Todos", "*.*")])
            if caminho:
                variavel.set(caminho)
                if on_escolher:
                    on_escolher(caminho)

        ttk.Button(linha, text="Selecionar...", command=_escolher).pack(side="left")

    def _atualizar_estado_extras(self):
        self.lista_extras.config(state="normal" if self.filtro_critica.get() == CRITICA_SEM else "disabled")

    def _ao_escolher_ocorrencias(self, caminho):
        try:
            abas = abas_de_ocorrencias(caminho) if caminho.lower().endswith(".xlsx") else []
        except Exception as erro:
            messagebox.showerror("Ocorrências", f"Não foi possível ler as abas: {erro}")
            return
        self.combo_aba["values"] = abas
        if abas:
            self.aba_ocorrencias.set(abas[0])
        else:
            self.aba_ocorrencias.set("")

    # --- Ações ---

    def _carregar_base(self):
        if not self.caminho_5201.get() or not self.caminho_ia.get():
            messagebox.showwarning("Faltou arquivo", "REL5201 e Base IA são obrigatórios.")
            return
        if not self.caminho_json.get() or not Path(self.caminho_json.get()).exists():
            messagebox.showwarning(
                "Faltou o JSON de regras",
                "Rode 'python scripts/exportar_dados_farol_offline.py' (precisa de rede, uma vez só) "
                "e selecione o arquivo gerado em ferramentas/dados_farol_offline.json.",
            )
            return
        try:
            self.mapa_offline = json.loads(Path(self.caminho_json.get()).read_text(encoding="utf-8"))
            df_5201 = ler_relatorio_5201(_ArquivoBinario(self.caminho_5201.get()))

            registros_ia, mes_ia, total_bruto_ia = preparar_registros_base_ia(self.caminho_ia.get())
            processos_ia = agregar_processos_farol(registros_ia, mes_referencia=mes_ia)

            glosas_5310 = {}
            if self.caminho_5310.get():
                registros_5310, mes_5310, total_bruto_5310, nao_cruzados = preparar_registros_5310(
                    self.caminho_5310.get(), mapa_procedimentos=self.mapa_offline.get("mapa_procedimentos", {}),
                )
                glosas_5310 = agregar_glosas_5310(registros_5310)

            self.ordens_par = _limpar_lista_par(self.caminho_par.get()) if self.caminho_par.get() else set()

            self.base = montar_base_farol(
                df_5201, processos_ia, glosas_5310,
                self.mapa_offline.get("especialidades_criticas", []),
                set(self.mapa_offline.get("procedimentos_criticos", [])),
            )
        except ColunasFaltandoError as erro:
            messagebox.showerror("Coluna faltando", str(erro))
            return
        except Exception as erro:
            messagebox.showerror("Erro ao carregar", str(erro))
            return

        if self.base.df.empty:
            messagebox.showinfo("Vazio", "Nenhum processo encontrado no REL5201.")
            return

        self.lista_status.delete(0, "end")
        for valor in sorted(v for v in self.base.df["STATUS"].unique() if v):
            self.lista_status.insert("end", valor)
        self.lista_execucao.delete(0, "end")
        presentes = set(self.base.df["EXECUCAO"])
        for valor in [e for e in EXECUCOES_DISPONIVEIS if e in presentes] or EXECUCOES_DISPONIVEIS:
            self.lista_execucao.insert("end", valor)
        self.lista_modalidade.delete(0, "end")
        for valor in sorted(m for m in self.base.df["MODALIDADE"].unique() if m and m != MODALIDADE_SEMPRE_EXCLUIDA):
            self.lista_modalidade.insert("end", valor)
        self.lista_extras.delete(0, "end")
        for valor in opcoes_especialidades(self.base.df):
            self.lista_extras.insert("end", valor)

        self.lbl_status_base.config(
            text=(
                f"REL5201 de {self.base.mes_5201 or '—'} · Base IA de {self.base.mes_ia or '—'} · "
                f"{self.base.total_processos_mes} processos, {self.base.total_procedimentos_mes} procedimentos no mês"
                + (f" · {len(self.ordens_par)} processo(s) na lista PAR" if self.ordens_par else "")
            )
        )

    def _valor_numerico_filtro(self, operador_var, valor_var):
        texto = valor_var.get().strip()
        if not texto:
            return None
        try:
            return (operador_var.get(), float(texto.replace(",", ".")))
        except ValueError:
            raise ValueError(f"Valor inválido: '{texto}'")

    def _selecionados(self, listbox: tk.Listbox) -> tuple:
        return tuple(listbox.get(i) for i in listbox.curselection())

    def _classificar(self):
        if self.base is None:
            messagebox.showwarning("Falta carregar", "Carregue a base primeiro (passo 1).")
            return
        if not self.caminho_ocorrencias.get():
            messagebox.showwarning("Faltou arquivo", "A planilha de ocorrências (5307) é obrigatória pro resultado.")
            return
        try:
            filtros = FiltrosFarol(
                critica=self.filtro_critica.get(),
                especialidades_extras=self._selecionados(self.lista_extras) if self.filtro_critica.get() == CRITICA_SEM else (),
                liberacao_ia=self._valor_numerico_filtro(self.op_liberacao, self.val_liberacao),
                biometria=self._valor_numerico_filtro(self.op_biometria, self.val_biometria),
                status=self._selecionados(self.lista_status),
                digitador=self.filtro_digitador.get(),
                execucao=self._selecionados(self.lista_execucao),
                modalidade=self._selecionados(self.lista_modalidade),
            )
        except ValueError as erro:
            messagebox.showerror("Filtro inválido", str(erro))
            return

        df_filtrado = aplicar_filtros(self.base.df, filtros)
        if df_filtrado.empty:
            messagebox.showinfo("Vazio", "Nenhum processo com esses filtros.")
            return
        producao, sem_dado = separar_para_cruzamento(df_filtrado)

        try:
            aba = self.aba_ocorrencias.get() or None
            agregado, info = carregar_ocorrencias(
                self.caminho_ocorrencias.get(), aba, self.incluir_compulsorio.get(),
            )
        except ColunasFaltandoError as erro:
            messagebox.showerror("Coluna faltando", str(erro))
            return
        except Exception as erro:
            messagebox.showerror("Erro nas ocorrências", str(erro))
            return

        self.resultado = cruzar(producao, agregado, sem_dado, par_forcado=self.ordens_par)

        self.operacional_df = None
        if self.gerar_operacional.get():
            ordens_s = set(self.resultado.planilhas["S - Vai pro Farol"]["ORDEM"].astype(str))
            self.operacional_df = montar_operacional(self.base.df, ordens_no_farol=ordens_s, ordens_par=self.ordens_par)

        self._mostrar_resultado(info)

    def _mostrar_resultado(self, info_ocorrencias):
        resumo = resumo_farol(self.resultado, self.base.total_processos_mes, self.base.total_procedimentos_mes)
        self.tabela.delete(*self.tabela.get_children())
        nomes = {chave: nome for chave, nome in ABAS_SAIDA}
        for chave, dados in resumo.items():
            self.tabela.insert("", "end", values=(
                nomes[chave], dados["processos"], dados["procedimentos"], f"{dados['pct_procedimentos_mes']:.1f}%",
            ))
        if self.operacional_df is not None:
            self.tabela.insert("", "end", values=(
                "Operacional (fora do Farol)", len(self.operacional_df), "—", "—",
            ))

        texto = (
            f"{info_ocorrencias.total_processos} ocorrência(s) lidas · "
            f"{self.resultado.percentual_sem_ocorrencia:.0f}% sem ocorrência correspondente · "
            f"{self.resultado.automaticos_100} processo(s) por 100% liberado pela IA"
        )
        if self.ordens_par:
            texto += f" · {len(self.ordens_par)} processo(s) forçados PAR pela lista"
        self.lbl_resumo.config(text=texto)
        if self.resultado.percentual_sem_ocorrencia >= 70:
            messagebox.showwarning(
                "Muita ocorrência não encontrada",
                f"{self.resultado.percentual_sem_ocorrencia:.0f}% dos processos ficaram sem ocorrência "
                "correspondente. Confira se a planilha 5307 é a do período certo.",
            )

    def _salvar_excel(self):
        if self.resultado is None:
            messagebox.showwarning("Nada pra salvar", "Classifique antes de salvar (passo 3).")
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")], initialfile="farol_mes_vigente.xlsx",
        )
        if not caminho:
            return
        import pandas as pd

        try:
            with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
                for _, nome_aba in ABAS_SAIDA:
                    _com_ordem_numerica(self.resultado.planilhas[nome_aba]).to_excel(writer, sheet_name=nome_aba, index=False)
                if self.operacional_df is not None:
                    self.operacional_df.to_excel(writer, sheet_name="Operacional", index=False)
        except Exception as erro:
            messagebox.showerror("Erro ao salvar", str(erro))
            return
        messagebox.showinfo("Salvo", f"Arquivo salvo em:\n{caminho}")


if __name__ == "__main__":
    App().mainloop()
