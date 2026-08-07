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


def pilula(texto: str) -> str:
    """HTML de uma "pílula" neutra (badge arredondado) -- mesmo componente
    visual em qualquer tela que precise disso, em vez de cada uma inventar
    seu próprio <span> com cores diferentes. Usar com unsafe_allow_html=True."""
    return (
        f"<span style='background: {COR_NEUTRA_BG}; color: {COR_NEUTRA_TEXTO}; "
        f"padding: 2px 10px; border-radius: 999px; font-size: 0.8rem; "
        f"display: inline-block;'>{texto}</span>"
    )


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
