import pandas as pd
import streamlit as st

# Paleta compartilhada -- antes de criar uma cor nova numa tela nova,
# reaproveita uma destas. COR_SUCESSO/COR_PERIGO são as MESMAS já usadas em
# STATUS_CORES (core/relatorio_5201.py) pro status FECHADO/GLOSADO -- mesmo
# significado (bom/ruim) deve ser a mesma cor em qualquer tela do app.
COR_SUCESSO = "#22C55E"
COR_PERIGO = "#EF5350"
COR_NEUTRA_BG = "rgba(148, 163, 184, 0.18)"
COR_NEUTRA_TEXTO = "#94a3b8"
COR_TITULO = "#2C3E50"
COR_SUBTITULO = "#7F8C8D"


def fmt_num(n: int) -> str:
    """Formata inteiro com separador de milhar (pt-BR: ponto) -- padrão
    único de número em qualquer métrica do app, em vez de cada tela decidir
    se formata ou não (58238 é bem mais lento de ler que 58.238)."""
    return f"{n:,}".replace(",", ".")


def pilula(texto: str, cor_texto: str = None, cor_fundo: str = None) -> str:
    """HTML de uma "pílula" (badge arredondado) -- mesmo componente visual
    em qualquer tela que precise disso, em vez de cada uma inventar seu
    próprio <span> com cores diferentes. Neutro por padrão; passe cor_texto
    (e opcionalmente cor_fundo) pra variantes semânticas (ex: por status).
    Usar com unsafe_allow_html=True."""
    cor_texto = cor_texto or COR_NEUTRA_TEXTO
    cor_fundo = cor_fundo or COR_NEUTRA_BG
    return (
        f"<span style='background: {cor_fundo}; color: {cor_texto}; "
        f"padding: 2px 10px; border-radius: 999px; font-size: 0.8rem; "
        f"display: inline-block;'>{texto}</span>"
    )


_OPERADORES_NUMERICOS = {
    "Maior que": lambda serie, v: serie > v,
    "Menor que": lambda serie, v: serie < v,
    "Maior ou igual a": lambda serie, v: serie >= v,
    "Menor ou igual a": lambda serie, v: serie <= v,
    "Igual a": lambda serie, v: serie == v,
}


def filtro_numerico(label: str, key_prefix: str):
    """Filtro 'operador + valor' (>, >=, <, <=, =) pra coluna numérica --
    devolve (operador, valor) ou None quando "Todos" (sem filtro). Passar
    pra aplicar_filtro_numerico() junto com o DataFrame e a coluna alvo."""
    col_op, col_val = st.columns([1, 1])
    with col_op:
        operador = st.selectbox(
            label, ["Todos", *_OPERADORES_NUMERICOS.keys()], key=f"{key_prefix}_operador", width=140,
        )
    if operador == "Todos":
        return None
    with col_val:
        valor = st.number_input("Valor", key=f"{key_prefix}_valor", label_visibility="collapsed", width=140)
    return (operador, valor)


def aplicar_filtro_numerico(df: pd.DataFrame, coluna: str, filtro) -> pd.DataFrame:
    """Aplica o filtro devolvido por filtro_numerico() num DataFrame --
    linhas com valor nulo na coluna nunca passam (não há como comparar
    "sem dado" com um número)."""
    if filtro is None:
        return df
    operador, valor = filtro
    return df[_OPERADORES_NUMERICOS[operador](df[coluna], valor)]


def estilizar_botoes_exclusao():
    """Dá cor de perigo (vermelho) a qualquer st.button cuja key comece com
    'btn_excluir_' -- st.button só tem type primary/secondary/tertiary
    nativamente, sem uma variante de perigo. Usa a classe `st-key-<key>`
    que o Streamlit gera automaticamente pra todo widget com key definida.

    Chamar uma vez por página que tenha botão de exclusão (CSS injetado
    via st.markdown não persiste entre páginas do multipage app)."""
    st.markdown(
        """
        <style>
        div[class*="st-key-btn_excluir_"] button {
            background-color: #DC2626;
            color: white;
            border-color: #DC2626;
        }
        div[class*="st-key-btn_excluir_"] button:hover {
            background-color: #B91C1C;
            border-color: #B91C1C;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
