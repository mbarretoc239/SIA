"""Estilo dos graficos (Altair) na identidade da marca: uma cor por funcao, grade discreta, fundo transparente,
claro e escuro escolhidos (nao invertidos). Usar com st.altair_chart(..., theme=None) para o Streamlit nao
sobrescrever as cores."""
import streamlit as st

CLARO = {
    "texto": "#0b0b0b", "texto2": "#52514e", "mudo": "#898781", "grade": "#e1e0d9", "base": "#c3c2b7",
    "superficie": "#ffffff", "series": ["#2b52c8", "#eb6834", "#1baf7a"],
    "sequencial": ["#dbe3fb", "#a9bcf3", "#6b8cf2", "#2b52c8", "#1539aa"],
}
ESCURO = {
    "texto": "#ffffff", "texto2": "#c3c2b7", "mudo": "#898781", "grade": "#2c2c2a", "base": "#383835",
    "superficie": "#0e1117", "series": ["#6b8cf2", "#d95926", "#199e70"],
    "sequencial": ["#16296b", "#1f3f9e", "#3a5fd0", "#7f9bf3", "#c3d0fa"],
}


def tema() -> dict:
    try:
        return ESCURO if st.context.theme.type == "dark" else CLARO
    except Exception:  # fora do Streamlit (testes) ou versao sem st.context.theme
        return CLARO


def estilo(grafico, t: dict, altura: int | None = None):
    """Fundo transparente, sem contorno de vista, grade e eixos discretos."""
    if altura:
        grafico = grafico.properties(height=altura)
    return (
        grafico.properties(background="transparent")
        .configure_view(stroke=None)
        .configure_axis(
            gridColor=t["grade"], gridWidth=1, domainColor=t["base"], tickColor=t["base"],
            labelColor=t["mudo"], titleColor=t["texto2"], labelFontSize=12, titleFontSize=12,
            labelFont="system-ui, Segoe UI, sans-serif", titleFont="system-ui, Segoe UI, sans-serif",
        )
        .configure_legend(labelColor=t["texto2"], titleColor=t["texto2"], labelFontSize=12, symbolType="square",
                          orient="top", title=None)
    )
