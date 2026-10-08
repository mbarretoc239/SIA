"""Identidade visual (Hapvida +odonto): logo na barra lateral (versao clara ou escura conforme o tema), icone da
aba e faixa com as cores da marca no cabecalho. As cores do tema ficam em .streamlit/config.toml."""
from pathlib import Path

import streamlit as st

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
ICONE = str(_ASSETS / "icone.png")

# azul do texto, vermelho/laranja/laranja-claro/amarelo das petalas (cores do PDF da marca)
CORES = ["#1539aa", "#ff222b", "#ff4e05", "#ff8800", "#ffcc23"]

_FAIXA = (
    "<style>[data-testid='stHeader']{border-bottom:3px solid transparent;border-image:linear-gradient(90deg,"
    + ",".join(CORES) + ") 1;}</style>"
)


def _escuro() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:  # fora do Streamlit (testes) ou versao sem st.context.theme
        return False


def aplicar():
    """Chamar logo depois de st.set_page_config no entrypoint (app.py); vale pra todas as paginas."""
    try:
        logo = _ASSETS / ("logo_escuro.png" if _escuro() else "logo.png")
        st.logo(str(logo), size="large", icon_image=ICONE)
        st.html(_FAIXA)
    except Exception:  # a marca nunca deve derrubar a pagina
        pass
