"""Identidade visual (Hapvida +odonto): logo na barra lateral (versao clara ou escura conforme o tema), icone da
aba e faixa com as cores da marca no cabecalho. As cores do tema ficam em .streamlit/config.toml."""
from pathlib import Path

import streamlit as st

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
ICONE = str(_ASSETS / "icone.png")

# azul do texto, vermelho/laranja/laranja-claro/amarelo das petalas (cores do PDF da marca)
CORES = ["#1539aa", "#ff222b", "#ff4e05", "#ff8800", "#ffcc23"]

# st.logo(size="large") e o maior tamanho nativo e ainda fica pequeno na barra lateral; o CSS abaixo aumenta so o
# logo da barra lateral aberta (depende dos data-testid do Streamlit (na barra lateral o logo e stSidebarLogo, nao stLogo); se mudarem, ajustar os seletores).
_FAIXA = (
    "<style>[data-testid='stHeader']{border-bottom:3px solid transparent;border-image:linear-gradient(90deg,"
    + ",".join(CORES) + ") 1;}"
    "[data-testid='stSidebarHeader']{height:auto;min-height:6rem;padding-top:1rem;padding-bottom:0.5rem;}"
    "[data-testid='stSidebarLogo']{height:5rem !important;max-width:100% !important;width:auto !important;"
    "object-fit:contain;}</style>"
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
