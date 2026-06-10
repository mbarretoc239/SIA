"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          GLASS DESIGN SYSTEM — Dark Blue Glassmorphism for Streamlit         ║
║                        Versão 1.0 • 2026-05-26                               ║
╚══════════════════════════════════════════════════════════════════════════════╝

Como usar em qualquer app Streamlit:
─────────────────────────────────────
    from glass_design_system import inject_glass_css

    def main():
        inject_glass_css()          # ← primeira chamada da main()
        # ... resto do seu app ...

Personalização:
───────────────
    inject_glass_css(
        accent_color    = "#4a9eff",   # azul padrão — troque por qualquer cor
        gradient_start  = "#0d1b3e",   # início do fundo
        gradient_end    = "#060d1f",   # fim do fundo
        font_import     = True,        # False se não quiser importar Inter do Google
    )

Requisitos:
───────────
    pip install streamlit
    (extra_streamlit_components — só necessário se usar CookieManager)
"""

import html as html_lib

import streamlit as st
import streamlit.components.v1 as components


# ══════════════════════════════════════════════════════════════════════════════
# TOKENS DE DESIGN — edite aqui para personalizar
# ══════════════════════════════════════════════════════════════════════════════

COLORS = {
    # Fundos
    "bg_start":       "#0d1b3e",   # gradiente do fundo — topo
    "bg_end":         "#060d1f",   # gradiente do fundo — base
    "header_bg":      "rgba(3, 16, 31, 0.80)",

    # Accent (cor principal — botões, bordas de foco, highlights)
    "accent":         "#4a9eff",   # azul elétrico
    "accent_light":   "#5aafff",   # versão mais clara

    # Superfícies glass
    "glass_weak":     "rgba(255,255,255,0.07)",   # tabelas, file uploader
    "glass_mid":      "rgba(255,255,255,0.13)",   # inputs, botões, métricas
    "glass_strong":   "rgba(255,255,255,0.19)",   # hover/focus

    # Textos
    "text_primary":   "rgba(255,255,255,0.88)",
    "text_muted":     "rgba(255,255,255,0.55)",
    "text_label":     "rgba(255,255,255,0.75)",

    # Orbs (esferas de fundo animadas)
    "orb1": "rgba(30, 100, 255, 0.45)",
    "orb2": "rgba(15, 75,  200, 0.40)",
    "orb3": "rgba(0,  150, 255, 0.35)",

    # Estados
    "success":  "rgba(30, 180, 100, 0.18)",
    "success_b": "rgba(60, 220, 130, 0.35)",
}

RADII = {
    "pill":   "28px",   # inputs, botões
    "card":   "16px",   # métricas, cards
    "medium": "12px",   # popovers, tabelas, alertas
    "small":  "8px",    # tags multiselect
}

BLUR = {
    "strong": "blur(24px)",
    "mid":    "blur(16px)",
    "weak":   "blur(8px)",
}

SHADOWS = {
    "input": """0 2px 12px rgba(0,0,0,0.2),
                inset 0 1px 0 rgba(255,255,255,0.18),
                inset 0 -1px 0 rgba(0,0,0,0.1)""",
    "input_focus": """0 8px 24px rgba(0,0,0,0.2),
                      inset 0 1px 0 rgba(255,255,255,0.25),
                      inset 0 0 12px rgba(255,255,255,0.05),
                      0 0 0 3px rgba(74,158,255,0.25)""",
    "metric": """0 12px 32px rgba(0,0,0,0.25),
                 inset 0 2px 3px rgba(255,255,255,0.25),
                 inset 0 -2px 5px rgba(0,0,0,0.2),
                 inset 1px 0 2px rgba(255,255,255,0.08)""",
    "metric_hover": """0 16px 40px rgba(0,0,0,0.35),
                       inset 0 2px 4px rgba(255,255,255,0.3),
                       inset 0 -2px 5px rgba(0,0,0,0.2),
                       inset 1px 0 2px rgba(255,255,255,0.1)""",
    "button": """0 2px 12px rgba(0,0,0,0.2),
                 inset 0 1px 0 rgba(255,255,255,0.18),
                 inset 0 -1px 0 rgba(0,0,0,0.1)""",
    "popover": "0 16px 48px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.12)",
}

TRANSITIONS = {
    "elastic": "all 0.4s cubic-bezier(0.25, 1, 0.5, 1)",
    "fast":    "all 0.2s ease",
    "ripple":  "800ms cubic-bezier(0.25, 0.46, 0.45, 0.94)",
}


# ══════════════════════════════════════════════════════════════════════════════
# FUNÇÃO PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def inject_glass_css(
    accent_color:   str = "#4a9eff",
    gradient_start: str = "#0d1b3e",
    gradient_end:   str = "#060d1f",
    font_import:    bool = True,
):
    """
    Injeta o design system Glass Dark Blue no app Streamlit atual.

    Parâmetros:
        accent_color    Cor principal (botões, bordas de foco, destaques).
        gradient_start  Cor do topo do fundo gradiente.
        gradient_end    Cor da base do fundo gradiente.
        font_import     Se True, importa a fonte Inter do Google Fonts.
    """

    font_rule = f"@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');" if font_import else ""

    st.markdown(f"""
    <style>
    {font_rule}

    /* ── Fonte global ───────────────────────────────────────────────────── */
    html, body, button, input, select, textarea, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    }}

    /* ── Scrollbar Customizada ──────────────────────────────────────────── */
    ::-webkit-scrollbar                {{ width: 10px; height: 10px; }}
    ::-webkit-scrollbar-track         {{ background: rgba(6, 13, 31, 0.6); }}
    ::-webkit-scrollbar-thumb         {{ background: rgba(30, 80, 160, 0.5); border-radius: 10px;
                                         border: 2px solid rgba(6, 13, 31, 0.8);
                                         transition: background 0.3s ease; }}
    ::-webkit-scrollbar-thumb:hover   {{ background: rgba(45, 120, 255, 0.8); }}
    html {{ scroll-behavior: smooth; }}

    /* ── Fundo Gradiente ────────────────────────────────────────────────── */
    .stApp            {{ background: transparent !important; }}
    .block-container  {{ background: transparent !important;
                         padding-top: 2rem !important;
                         padding-bottom: 1rem !important; }}

    /* ── Header ────────────────────────────────────────────────────────── */
    header[data-testid="stHeader"] {{
        background: rgba(3, 16, 31, 0.80) !important;
        backdrop-filter: blur(20px) !important;
        border-bottom: 1px solid rgba(255,255,255,0.07) !important;
    }}

    /* ── Textos ─────────────────────────────────────────────────────────── */
    h1, h2, h3, h4, h5, h6              {{ color: white !important; font-weight: 700 !important; }}
    p, span, li, div, label             {{ color: rgba(255,255,255,0.88) !important; }}
    small, [data-testid="stCaptionContainer"] p {{ color: rgba(255,255,255,0.55) !important; }}

    /* ── Formulário (container) ─────────────────────────────────────────── */
    [data-testid="stForm"] {{
        background: rgba(255,255,255,0.09) !important;
        backdrop-filter: blur(24px) !important;
        -webkit-backdrop-filter: blur(24px) !important;
        border-radius: 28px !important;
        border: 1px solid rgba(255,255,255,0.18) !important;
        box-shadow: 0 12px 48px rgba(0,0,0,0.3),
                    inset 0 1px 0 rgba(255,255,255,0.35),
                    inset 0 -1px 0 rgba(255,255,255,0.05) !important;
        padding: 28px 32px !important;
    }}

    /* ── Labels dos Inputs ──────────────────────────────────────────────── */
    [data-testid="stTextInput"] label,
    [data-testid="stNumberInput"] label,
    [data-testid="stSelectbox"] label,
    [data-testid="stMultiSelect"] label,
    [data-testid="stTextArea"] label {{
        font-size: 13px !important;
        font-weight: 600 !important;
        color: rgba(255,255,255,0.75) !important;
        letter-spacing: 0.3px !important;
        margin-bottom: 4px !important;
    }}

    /* ── Text Input — wrapper externo recebe glass shape ───────────────── */
    [data-testid="stTextInput"] [data-baseweb="input"],
    [data-testid="stNumberInput"] > div:last-child {{
        background: rgba(255,255,255,0.13) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border: none !important;
        outline: none !important;
        border-radius: 28px !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.2),
                    inset 0 1px 0 rgba(255,255,255,0.18),
                    inset 0 -1px 0 rgba(0,0,0,0.1) !important;
        transition: all 0.4s cubic-bezier(0.25, 1, 0.5, 1) !important;
        overflow: hidden !important;
    }}

    /* ── Text Input — elemento interno transparente ─────────────────────── */
    [data-testid="stNumberInput"] [data-baseweb="input"],
    [data-testid="stTextInput"] [data-baseweb="base-input"],
    [data-testid="stNumberInput"] [data-baseweb="base-input"] {{
        background: transparent !important;
        backdrop-filter: none !important;
        -webkit-backdrop-filter: none !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        overflow: hidden !important;
        width: 100% !important;
    }}

    /* ── Text Input — focus ─────────────────────────────────────────────── */
    [data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
    [data-testid="stNumberInput"] > div:last-child:focus-within {{
        background: rgba(255,255,255,0.19) !important;
        transform: scale(1.02) !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.2),
                    inset 0 1px 0 rgba(255,255,255,0.25),
                    inset 0 0 12px rgba(255,255,255,0.05),
                    0 0 0 3px {accent_color}40 !important;
    }}

    /* ── <input> em si — transparente dentro do wrapper ────────────────── */
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input {{
        background: transparent !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        color: white !important;
        padding: 12px 20px !important;
        font-size: 15px !important;
    }}
    input::placeholder       {{ color: rgba(255,255,255,0.38) !important; }}
    input:focus              {{ outline: none !important; box-shadow: none !important;
                                border: none !important; }}

    /* ── Botão de olho da senha ─────────────────────────────────────────── */
    [data-testid="stTextInput"] [data-baseweb="base-input"] {{
        position: relative !important;
        border-radius: 0 !important;
        width: 100% !important;
        overflow: hidden !important;
        background: transparent !important;
    }}
    [data-testid="stTextInput"] input[type="password"] {{
        padding-right: 44px !important;
        width: 100% !important;
    }}
    [data-testid="stTextInput"] button,
    [data-testid="stTextInput"] button:hover,
    [data-testid="stTextInput"] button:focus,
    [data-testid="stTextInput"] button:active {{
        position: absolute !important; right: 10px !important; top: 50% !important;
        transform: translateY(-50%) !important; background: transparent !important;
        border: none !important; box-shadow: none !important;
        color: rgba(255,255,255,0.45) !important; cursor: pointer !important;
    }}

    /* ── Ocultar hint e olho nativo ─────────────────────────────────────── */
    [data-testid="InputInstructions"], small[data-testid="InputInstructions"] {{
        display: none !important;
    }}
    input[type="password"]::-ms-reveal,
    input[type="password"]::-ms-clear,
    input::-webkit-credentials-auto-fill-button,
    input::-webkit-contacts-auto-fill-button    {{ display: none !important; }}

    /* ── Botões +/- do Number Input ─────────────────────────────────────── */
    [data-testid="stNumberInput"] button {{
        background: transparent !important; border: none !important;
        box-shadow: none !important; color: rgba(255,255,255,0.6) !important;
        border-radius: 0 !important; backdrop-filter: none !important;
    }}
    [data-testid="stNumberInput"] button:hover {{
        background: rgba(255,255,255,0.1) !important;
        color: white !important; transform: translateY(0) !important;
    }}

    /* ── Selectbox e Multiselect (Outer Wrapper) ────────────────────────── */
    [data-testid="stSelectbox"] > div:last-child,
    [data-testid="stMultiSelect"] > div:last-child {{
        background: rgba(255,255,255,0.13) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border: none !important;
        border-radius: 28px !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.2),
                    inset 0 1px 0 rgba(255,255,255,0.18),
                    inset 0 -1px 0 rgba(0,0,0,0.1) !important;
        transition: all 0.4s cubic-bezier(0.25, 1, 0.5, 1) !important;
        overflow: hidden !important;
    }}
    [data-testid="stSelectbox"] > div:last-child:focus-within,
    [data-testid="stMultiSelect"] > div:last-child:focus-within {{
        background: rgba(255,255,255,0.19) !important;
        transform: scale(1.02) !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.2),
                    inset 0 1px 0 rgba(255,255,255,0.25),
                    inset 0 0 12px rgba(255,255,255,0.05),
                    0 0 0 3px {accent_color}40 !important;
    }}
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div {{
        background: transparent !important; border: none !important;
        box-shadow: none !important; color: white !important;
    }}

    /* ── Tags do Multiselect ────────────────────────────────────────────── */
    [data-testid="stMultiSelect"] span[data-baseweb="tag"] {{
        background: rgba(255,255,255,0.18) !important;
        backdrop-filter: blur(8px) !important; border: none !important;
        border-radius: 12px !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.15), inset 0 1px 0 rgba(255,255,255,0.2) !important;
        color: white !important;
    }}
    [data-testid="stMultiSelect"] span {{ color: white !important; }}

    /* ── Dropdown Popover — opções (estilo; glass aplicado via JS) ──────── */
    [data-baseweb="popover"] [role="option"] {{
        color: rgba(255,255,255,0.85) !important;
        border-radius: 8px !important;
        transition: background 0.18s ease !important;
    }}
    [data-baseweb="popover"] [role="option"]:hover        {{ background: rgba(255,255,255,0.10) !important; color: white !important; }}
    [data-baseweb="popover"] [aria-selected="true"]       {{ background: {accent_color}2e !important; color: white !important; }}

    /* ── Textarea ───────────────────────────────────────────────────────── */
    [data-testid="stTextArea"] textarea {{
        background: rgba(255,255,255,0.13) !important;
        backdrop-filter: blur(16px) !important;
        border: 1px solid rgba(255,255,255,0.14) !important;
        border-radius: 16px !important;
        color: white !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.18) !important;
        transition: all 0.4s cubic-bezier(0.25, 1, 0.5, 1) !important;
    }}
    [data-testid="stTextArea"] textarea:focus {{
        background: rgba(255,255,255,0.18) !important;
        border-color: {accent_color}80 !important;
        box-shadow: 0 0 0 3px {accent_color}30 !important;
        outline: none !important;
    }}

    /* ── Botões — Liquid Glass Apple-style ──────────────────────────────── */
    button[kind="primary"], button[kind="secondary"],
    [data-testid="baseButton-secondary"], [data-testid="baseButton-primary"],
    [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"],
    [data-testid="baseButton-secondaryFormSubmit"], [data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stFormSubmitButton"] > button,
    [data-testid="stFileUploader"] button,
    .stButton > button {{
        position: relative !important;
        overflow: hidden !important;
        background: rgba(255,255,255,0.13) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border: none !important;
        border-radius: 28px !important;
        color: white !important;
        font-weight: 500 !important;
        letter-spacing: 0.2px !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.2),
                    inset 0 1px 0 rgba(255,255,255,0.18),
                    inset 0 -1px 0 rgba(0,0,0,0.1) !important;
        transition: all 0.2s ease !important;
    }}
    button[kind="primary"]:hover, button[kind="secondary"]:hover,
    [data-testid="baseButton-secondary"]:hover, [data-testid="baseButton-primary"]:hover,
    [data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseButton-primary"]:hover,
    [data-testid="stFormSubmitButton"] > button:hover,
    [data-testid="stFileUploader"] button:hover, .stButton > button:hover {{
        background: rgba(255,255,255,0.20) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25),
                    inset 0 1px 0 rgba(255,255,255,0.25),
                    inset 0 -1px 0 rgba(0,0,0,0.1) !important;
    }}
    button[kind="primary"]:active, button[kind="secondary"]:active,
    [data-testid="baseButton-secondary"]:active, [data-testid="baseButton-primary"]:active,
    [data-testid="stBaseButton-secondary"]:active, [data-testid="stBaseButton-primary"]:active,
    [data-testid="stFormSubmitButton"] > button:active,
    [data-testid="stFileUploader"] button:active, .stButton > button:active {{
        background: rgba(255,255,255,0.08) !important;
        transform: translateY(0px) !important;
    }}

    /* ── File Uploader ──────────────────────────────────────────────────── */
    [data-testid="stFileUploader"] > section {{
        background: rgba(255,255,255,0.07) !important;
        border: 1px dashed rgba(255,255,255,0.25) !important;
        border-radius: 12px !important;
    }}

    /* ── Métricas — Liquid Glass 3D ─────────────────────────────────────── */
    [data-testid="stMetric"] {{
        background: rgba(255,255,255,0.13) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border-radius: 16px !important;
        border: none !important;
        box-shadow: 0 12px 32px rgba(0,0,0,0.25),
                    inset 0 2px 3px rgba(255,255,255,0.25),
                    inset 0 -2px 5px rgba(0,0,0,0.2),
                    inset 1px 0 2px rgba(255,255,255,0.08) !important;
        padding: 20px 24px !important;
        min-height: 110px !important;
        position: relative !important;
        overflow: hidden !important;
        transition: all 0.4s cubic-bezier(0.25, 1, 0.5, 1) !important;
    }}
    [data-testid="stMetric"]::before {{
        content: '' !important;
        position: absolute !important; top: -50% !important; left: -50% !important;
        width: 200% !important; height: 200% !important;
        background: radial-gradient(circle at 50% 50%, rgba(255,255,255,0.1), transparent 50%) !important;
        opacity: 0 !important;
        transition: opacity 0.4s ease !important;
        pointer-events: none !important;
    }}
    [data-testid="stMetric"]:hover {{
        transform: translateY(-4px) !important;
        background: rgba(255,255,255,0.16) !important;
        box-shadow: 0 16px 40px rgba(0,0,0,0.35),
                    inset 0 2px 4px rgba(255,255,255,0.3),
                    inset 0 -2px 5px rgba(0,0,0,0.2),
                    inset 1px 0 2px rgba(255,255,255,0.1) !important;
    }}
    [data-testid="stMetric"]:hover::before {{
        opacity: 1 !important;
        animation: liquidDistortion 4s ease-in-out infinite alternate !important;
    }}
    @keyframes liquidDistortion {{
        0%   {{ transform: translate(0, 0) scale(1); }}
        100% {{ transform: translate(20px, 25px) scale(1.15); }}
    }}
    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"]    {{ position: relative !important; z-index: 1 !important; }}
    [data-testid="stMetricLabel"] p  {{ color: rgba(255,255,255,0.65) !important; font-size: 13px !important; }}
    [data-testid="stMetricValue"]    {{ color: white !important; font-weight: 700 !important;
                                        font-size: clamp(14px, 1.5vw, 24px) !important;
                                        white-space: normal !important; word-break: break-word !important; }}
    [data-testid="stMetricDelta"]    {{ color: rgba(255,255,255,0.7) !important; }}
    [data-testid="stMetricDelta"] svg {{ fill: rgba(255,255,255,0.7) !important; }}

    /* ── Abas ───────────────────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {{
        background: rgba(255,255,255,0.06) !important;
        border-radius: 12px !important; padding: 4px 5px !important;
        border: 1px solid rgba(255,255,255,0.12) !important; gap: 3px !important;
    }}
    .stTabs [data-baseweb="tab"] {{
        position: relative !important; overflow: hidden !important;
        background: transparent !important; border-radius: 9px !important;
        color: rgba(255,255,255,0.55) !important; border: none !important;
        font-weight: 500 !important; padding: 8px 18px !important;
    }}
    .stTabs [data-baseweb="tab"]:hover   {{ background: rgba(255,255,255,0.08) !important; color: rgba(255,255,255,0.9) !important; }}
    .stTabs [aria-selected="true"]       {{ background: rgba(255,255,255,0.17) !important;
                                            backdrop-filter: blur(8px) !important; color: white !important;
                                            box-shadow: inset 0 1px 0 rgba(255,255,255,0.4), 0 2px 8px rgba(0,0,0,0.1) !important; }}
    .stTabs [data-baseweb="tab-highlight"],
    .stTabs [data-baseweb="tab-border"]  {{ display: none !important; }}

    /* ── Alertas ────────────────────────────────────────────────────────── */
    [data-testid="stAlert"] {{
        border-radius: 12px !important;
        backdrop-filter: blur(14px) !important;
        -webkit-backdrop-filter: blur(14px) !important;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.15) !important;
    }}
    [data-testid="stAlert"][data-baseweb="notification"]:not([kind="positive"]) {{
        background: rgba(255,255,255,0.10) !important;
        border: 1px solid rgba(255,255,255,0.18) !important;
    }}
    [data-testid="stAlert"][kind="positive"],
    div[data-testid="stAlert"].st-success {{
        background: rgba(30, 180, 100, 0.18) !important;
        border: 1px solid rgba(60, 220, 130, 0.35) !important;
    }}
    [data-testid="stAlert"] p,
    [data-testid="stAlert"] span,
    [data-testid="stAlert"] div  {{ color: rgba(255,255,255,0.92) !important; }}

    /* ── Radio ──────────────────────────────────────────────────────────── */
    [data-testid="stRadio"] label {{ color: rgba(255,255,255,0.85) !important; }}

    /* ── Divider ────────────────────────────────────────────────────────── */
    hr {{ border-color: rgba(255,255,255,0.10) !important; }}

    /* ── Sidebar ────────────────────────────────────────────────────────── */
    [data-testid="stSidebar"] {{
        background: rgba(255, 255, 255, 0.02) !important;
        backdrop-filter: blur(40px) saturate(140%) !important;
        -webkit-backdrop-filter: blur(40px) saturate(140%) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.06) !important;
        box-shadow: 4px 0 24px rgba(0, 0, 0, 0.1) !important;
    }}

    /* ── Links de Navegação (st.page_link na Sidebar) ───────────────────── */
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {{
        background: rgba(255,255,255,0.13) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border: none !important;
        border-radius: 28px !important;
        transition: all 0.3s cubic-bezier(0.25, 1, 0.5, 1) !important;
        padding: 8px 16px !important;
        margin-bottom: 8px !important;
        text-decoration: none !important;
        box-shadow: 
            inset 1px 1px 2px rgba(255, 255, 255, 0.3),
            inset -1px -1px 2px rgba(0, 0, 0, 0.1),
            0 4px 12px rgba(0, 0, 0, 0.2) !important;
    }}
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] p {{
        font-weight: 500 !important;
        color: rgba(255,255,255,0.85) !important;
        margin: 0 !important;
        font-size: 14.5px !important;
    }}
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {{
        background: rgba(255,255,255,0.20) !important;
        transform: translateY(-1px) !important;
        box-shadow: 
            inset 1px 1px 3px rgba(255, 255, 255, 0.4),
            inset -1px -1px 3px rgba(0, 0, 0, 0.15),
            0 6px 16px rgba(0, 0, 0, 0.3) !important;
    }}
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover p {{
        color: white !important;
    }}

    /* Página ativa */
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][data-active="true"],
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"] {{
        background: rgba(255,255,255,0.25) !important;
        box-shadow: 
            inset 1px 1px 3px rgba(255, 255, 255, 0.5),
            inset -1px -1px 3px rgba(0, 0, 0, 0.2),
            0 8px 20px rgba(0, 0, 0, 0.4) !important;
    }}
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][data-active="true"] p,
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"] p {{
        color: white !important;
        font-weight: 600 !important;
    }}

    /* ── Expander ───────────────────────────────────────────────────────── */
    [data-testid="stExpander"] details {{
        background: rgba(255,255,255,0.13) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border: none !important;
        border-radius: 28px !important;
        box-shadow: 
            inset 1px 1px 2px rgba(255, 255, 255, 0.3),
            inset -1px -1px 2px rgba(0, 0, 0, 0.1),
            0 4px 12px rgba(0, 0, 0, 0.2) !important;
        overflow: hidden !important;
    }}
    [data-testid="stExpander"] summary {{
        padding: 8px 16px !important;
        color: white !important;
    }}
    [data-testid="stExpander"] summary:hover {{
        background: rgba(255,255,255,0.20) !important;
    }}

    /* ── DataFrame / DataEditor (Glide Data Grid) ─────────────────────────
       O grid é desenhado em <canvas>. Colocando uma cor sólida escura no
       wrapper PRINCIPAL (não no > div interno), o canvas herda essa cor em
       vez de cair no transparente padrão e aparecer branco. ─────────────── */
    [data-testid="stDataFrame"],
    [data-testid="stDataEditor"] {{
        background-color: #03101f !important;
        border-radius: 16px !important;
        border: 1px solid rgba(255,255,255,0.14) !important;
        box-shadow: 0 8px 32px rgba(0,0,0,0.5),
                    inset 0 1px 0 rgba(255,255,255,0.18) !important;
        padding: 4px !important;
    }}

    [data-testid="stDataFrame"] > div,
    [data-testid="stDataEditor"] > div {{
        background: transparent !important;
        border: none !important;
    }}

    /* O grid em si é pintado em <canvas> pelo glide-data-grid com cores
       fixas (fundo branco, texto preto), ignorando CSS de background.
       Invertendo as cores do canvas (branco→preto, preto→branco) e
       desfazendo a rotação de matiz resultante, o fundo fica escuro e o
       texto claro, mantendo aproximadamente as cores de destaque (azul de
       seleção etc.). */
    [data-testid="stDataFrame"] canvas,
    [data-testid="stDataEditor"] canvas {{
        filter: invert(1) hue-rotate(180deg) !important;
    }}

    /* Overlay de edição de célula (input/textarea sobre o canvas), que
       continua com fundo branco do navegador. */
    [data-testid="stDataFrame"] [class*="editor"] input,
    [data-testid="stDataEditor"] [class*="editor"] input,
    [data-testid="stDataFrame"] [class*="editor"] textarea,
    [data-testid="stDataEditor"] [class*="editor"] textarea {{
        background-color: #0c1b2d !important;
        color: #ffffff !important;
    }}

    /* Toolbar flutuante (busca/download/expandir) que aparece no hover */
    [data-testid="stElementToolbar"] {{
        background: rgba(14, 31, 61, 0.92) !important;
        backdrop-filter: blur(12px) !important;
        border-radius: 8px !important;
    }}
    [data-testid="stElementToolbar"] button svg {{
        fill: rgba(255,255,255,0.75) !important;
    }}

    /* ── Animação de entrada (login form) ───────────────────────────────── */
    @keyframes loginEntry {{
        0%   {{ opacity: 0; transform: translateY(28px); filter: blur(4px); }}
        100% {{ opacity: 1; transform: translateY(0);    filter: blur(0); }}
    }}
    body.first-load [data-testid="stForm"] {{
        animation: loginEntry 550ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }}

    /* ── Ripple Effect (CSS) ────────────────────────────────────────────── */
    .ripple-effect {{
        position: absolute; border-radius: 50%; transform: scale(0);
        animation: ripple-anim 800ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
        background: rgba(255, 255, 255, 0.15); pointer-events: none;
    }}
    @keyframes ripple-anim {{ to {{ transform: scale(4); opacity: 0; }} }}

    /* ── Orbs Flutuantes (Fundo) ────────────────────────────────────────── */
    .orb-container {{
        position: fixed; top: 0; left: 0;
        width: 100vw; height: 100vh;
        z-index: -1; pointer-events: none; overflow: hidden;
        background: linear-gradient(160deg, {gradient_start} 0%, {gradient_end} 100%);
    }}
    .orb {{ position: absolute; border-radius: 50%; mix-blend-mode: screen; }}
    .orb-1 {{
        width: 90vw; height: 90vw; top: -30vh; left: -20vw;
        background: radial-gradient(circle at center, rgba(30,100,255,0.45) 0%, rgba(30,100,255,0.15) 40%, rgba(30,100,255,0) 70%);
        animation: float1 25s infinite ease-in-out alternate;
    }}
    .orb-2 {{
        width: 80vw; height: 80vw; bottom: -20vh; right: -20vw;
        background: radial-gradient(circle at center, rgba(15,75,200,0.40) 0%, rgba(15,75,200,0.15) 40%, rgba(15,75,200,0) 70%);
        animation: float2 32s infinite ease-in-out alternate-reverse;
    }}
    .orb-3 {{
        width: 60vw; height: 60vw; top: 40vh; left: 30vw;
        background: radial-gradient(circle at center, rgba(0,150,255,0.35) 0%, rgba(0,150,255,0) 70%);
        animation: float3 22s infinite ease-in-out alternate;
    }}
    @keyframes float1 {{ 0% {{ transform: translate(0,0) scale(1); }} 100% {{ transform: translate(12vw,15vh) scale(1.15); }} }}
    @keyframes float2 {{ 0% {{ transform: translate(0,0) scale(1); }} 100% {{ transform: translate(-15vw,-10vh) scale(1.1); }} }}
    @keyframes float3 {{ 0% {{ transform: translate(0,0) scale(1); }} 100% {{ transform: translate(18vw,-15vh) scale(1.2); }} }}

    </style>

    <!-- Orbs de fundo (injetadas como HTML junto com o CSS) -->
    <div class="orb-container">
        <div class="orb orb-1"></div>
        <div class="orb orb-2"></div>
        <div class="orb orb-3"></div>
    </div>
    """, unsafe_allow_html=True)

    # ── JavaScript: animação de entrada + ripple + glass nos dropdowns ─────
    components.html(f"""
    <script>
    (function() {{
        const doc = window.parent.document;

        // ── Animação de entrada (só roda uma vez por sessão do browser) ──
        if (!sessionStorage.getItem('glass_ds_loaded')) {{
            doc.body.classList.add('first-load');
            sessionStorage.setItem('glass_ds_loaded', '1');
        }}

        // ── Glass nos dropdowns BaseUI (MutationObserver) ─────────────────
        // O Styletron injeta backgrounds opacos inline nos filhos do popover.
        // CSS puro não sobrescreve inline styles, então usamos JS.
        function stylePopover(el) {{
            el.style.background           = 'rgba(10,22,54,0.72)';
            el.style.backdropFilter       = 'blur(24px)';
            el.style.webkitBackdropFilter = 'blur(24px)';
            el.style.border               = '1px solid rgba(255,255,255,0.15)';
            el.style.borderRadius         = '12px';
            el.style.boxShadow            = '0 16px 48px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.12)';
            el.style.overflow             = 'hidden';
            // Zera backgrounds opacos dos filhos, mas preserva [data-baseweb="menu"]
            Array.from(el.querySelectorAll('*')).forEach(function(child) {{
                var bw = child.getAttribute('data-baseweb');
                if (!bw || bw !== 'menu') {{
                    child.style.background      = 'transparent';
                    child.style.backgroundColor = 'transparent';
                }}
            }});
        }}

        var popoverObserver = new MutationObserver(function(mutations) {{
            mutations.forEach(function(m) {{
                m.addedNodes.forEach(function(node) {{
                    if (node.nodeType !== 1) return;
                    if (node.getAttribute && node.getAttribute('data-baseweb') === 'popover') {{
                        stylePopover(node);
                    }}
                    var inner = node.querySelectorAll && node.querySelectorAll('[data-baseweb="popover"]');
                    if (inner) inner.forEach(stylePopover);
                }});
            }});
        }});
        popoverObserver.observe(doc.body, {{ childList: true, subtree: true }});

        // ── Ripple Effect nos botões ─────────────────────────────────────
        doc.addEventListener('mousedown', function(e) {{
            var target = e.target.closest(
                '.stButton > button, [data-testid="stFormSubmitButton"] > button, .stTabs [data-baseweb="tab"]'
            );
            if (!target) return;
            var circle   = doc.createElement('span');
            var diameter = Math.max(target.clientWidth, target.clientHeight);
            var radius   = diameter / 2;
            var rect     = target.getBoundingClientRect();
            circle.style.cssText = [
                'position:absolute', 'border-radius:50%', 'pointer-events:none',
                'width:' + diameter + 'px', 'height:' + diameter + 'px',
                'left:' + (e.clientX - rect.left - radius) + 'px',
                'top:' + (e.clientY - rect.top - radius) + 'px',
            ].join(';');
            circle.classList.add('ripple-effect');
            target.appendChild(circle);
            circle.addEventListener('animationend', function() {{ circle.remove(); }});
        }});
    }})();
    </script>
    """, height=0)


# ══════════════════════════════════════════════════════════════════════════════
# UTILITÁRIOS EXTRAS (opcionais)
# ══════════════════════════════════════════════════════════════════════════════

def glass_card(content_html: str, color: str = "rgba(255,255,255,0.13)") -> None:
    """
    Renderiza um card glass com conteúdo HTML customizado.

    Exemplo:
        glass_card('<h3>Título</h3><p>Conteúdo do card</p>')
    """
    st.markdown(f"""
    <div style="
        background: {color};
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border-radius: 16px;
        border: 1px solid rgba(255,255,255,0.14);
        box-shadow: 0 12px 32px rgba(0,0,0,0.25),
                    inset 0 2px 3px rgba(255,255,255,0.25),
                    inset 0 -2px 5px rgba(0,0,0,0.2);
        padding: 20px 24px;
        margin-bottom: 16px;
    ">
        {content_html}
    </div>
    """, unsafe_allow_html=True)


def glass_banner(text: str, color: str = "#4a9eff", icon: str = "ℹ️") -> None:
    """
    Exibe um banner/alerta glass com cor customizada.

    Exemplos:
        glass_banner("Operação concluída!", color="#1eb464", icon="✅")
        glass_banner("Atenção: verifique os dados.", color="#e0c040", icon="⚠️")
    """
    import re
    # Extrai RGB da cor hex para criar versão semi-transparente
    if color.startswith("#"):
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        bg    = f"rgba({r},{g},{b},0.12)"
        border = f"rgba({r},{g},{b},0.35)"
    else:
        bg = border = color

    st.markdown(f"""
    <div style="
        background: {bg};
        border: 1px solid {border};
        border-radius: 12px;
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        box-shadow: 0 4px 20px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.15);
        padding: 12px 18px;
        margin-bottom: 12px;
        color: rgba(255,255,255,0.92);
        font-size: 14px;
        display: flex; align-items: center; gap: 10px;
    ">
        <span style="font-size:18px">{icon}</span>
        <span>{text}</span>
    </div>
    """, unsafe_allow_html=True)


def render_glass_table(df, fmt: dict = None, max_height: int = 440, html_cols=None, footer_html: str = None, wrap_cols=None) -> None:
    """
    Renderiza uma tabela somente-leitura com o visual glass (header escuro fixo,
    linhas com hover, ordenação por coluna e filtro por valores via dropdown).

    Use para QUALQUER exibição de tabela (não editável). Não use
    st.dataframe/st.data_editor — o canvas do glide-data-grid não respeita o
    tema dark e sempre renderiza com fundo branco.

    Para tabelas editáveis, use esta função para a visualização e controles
    nativos (st.checkbox/st.text_input dentro de st.expander, um por linha)
    para a edição — veja o padrão em views/2_Relatorio_5302.py
    ("1. Auditoria e Justificativas").

    Parâmetros:
        df          DataFrame a exibir.
        fmt         dict opcional {coluna: "{:.2f}%"} para formatar valores numéricos.
        max_height  altura máxima da tabela (px) antes de rolar.
        html_cols   colunas cujo conteúdo já é HTML (não será escapado).
        footer_html HTML opcional exibido em uma barra de rodapé.
        wrap_cols   colunas que devem quebrar linha (texto longo) em vez de
                    truncar em uma linha só.

    Exemplo:
        render_glass_table(df, fmt={"Reaj. (%)": "{:.4f}%"})
    """
    df_display = df.copy()
    df_display = df_display.fillna('-')
    if fmt:
        for col, fmt_str in fmt.items():
            if col in df_display.columns:
                df_display[col] = df_display[col].apply(
                    lambda x: fmt_str.format(x) if x != '-' and isinstance(x, (int, float)) else (str(x) if x != '-' else '-')
                )

    _html_cols = set(html_cols) if html_cols else set()
    _wrap_cols = set(wrap_cols) if wrap_cols else set()
    n_cols = len(df_display.columns)
    headers_html = ''.join(
        f'<th class="hd" onclick="sortBy({i})">'
        f'{html_lib.escape(str(col))}'
        f'<span class="arr" onclick="event.stopPropagation();openFilter({i},this.closest(\'th\'))">&#9662;</span></th>'
        for i, col in enumerate(df_display.columns)
    )

    def _cell(col, v):
        cls = ' class="wrap"' if col in _wrap_cols else ''
        content = str(v) if col in _html_cols else html_lib.escape(str(v))
        return f'<td{cls}>{content}</td>'

    rows_html = ''.join(
        f'<tr style="--delay: {i};" data-orig="{i}">' +
        ''.join(_cell(col, v) for col, v in zip(df_display.columns, row)) +
        '</tr>'
        for i, (_, row) in enumerate(df_display.iterrows())
    )

    n = len(df_display)
    table_h = min(44 + 39 * n, max_height)
    footer_extra = 48 if footer_html else 0
    # O <thead> é sticky no topo do .wrap, então o dropdown de filtro sempre abre
    # ali (independente de quantas linhas a tabela tem) — só precisa de espaço
    # extra quando a própria tabela é mais baixa que essa área (cabeçalho + dropdown)
    _dd_clearance = 44 + 3 + 260 + 16
    iframe_h = max(table_h, _dd_clearance) + footer_extra

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:transparent;font-family:-apple-system,'Inter',sans-serif;overflow:visible}}
.wrap{{background:rgba(255,255,255,0.07);border-radius:12px;overflow-x:auto;overflow-y:auto;
       max-height:{max_height}px;border:1px solid rgba(255,255,255,0.14);
       box-shadow:0 8px 32px rgba(0,0,0,0.3),inset 0 1px 0 rgba(255,255,255,0.18);
       scrollbar-width:thin;scrollbar-color:rgba(255,255,255,0.22) transparent}}
.wrap::-webkit-scrollbar{{width:5px;height:5px}}
.wrap::-webkit-scrollbar-thumb{{background:rgba(255,255,255,0.22);border-radius:3px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
.hd{{position:sticky;top:0;z-index:3;padding:10px 12px;text-align:left;cursor:pointer;
     font-size:11px;font-weight:600;letter-spacing:.5px;text-transform:uppercase;
     color:rgba(255,255,255,0.6);background:rgba(4,13,32,0.99);
     border-bottom:1px solid rgba(255,255,255,0.13);white-space:nowrap;user-select:none}}
.hd:hover{{background:rgba(15,30,60,0.99)}}
.hd.on{{color:#5aafff}}
.hd.srt{{color:#a78bfa}}
.arr{{margin-left:4px;font-size:9px;opacity:.45;vertical-align:middle}}
.hd.on .arr{{opacity:1;color:#5aafff}}
.hd.srt .arr{{opacity:1;color:#a78bfa}}
td{{padding:9px 12px;color:rgba(255,255,255,0.88);border-bottom:1px solid rgba(255,255,255,0.05);white-space:nowrap}}
td.wrap{{white-space:normal;word-break:break-word;min-width:160px;max-width:380px;line-height:1.5}}
tbody tr:last-child td{{border-bottom:none}}
tbody tr:hover{{background:rgba(255,255,255,0.04)}}
.dd{{position:fixed;background:rgba(5,14,36,0.98);backdrop-filter:blur(28px);
     -webkit-backdrop-filter:blur(28px);border:1px solid rgba(255,255,255,0.18);
     border-radius:10px;padding:8px;z-index:9999;min-width:220px;
     box-shadow:0 16px 48px rgba(0,0,0,0.7),inset 0 1px 0 rgba(255,255,255,0.1);
     display:flex;flex-direction:column;max-height:260px}}
.ds{{background:rgba(255,255,255,0.09);border:1px solid rgba(255,255,255,0.14);border-radius:6px;
     color:white;padding:6px 10px;font-size:12px;outline:none;margin-bottom:6px;
     font-family:inherit;width:100%}}
.ds::placeholder{{color:rgba(255,255,255,0.32)}}
.ds:focus{{background:rgba(255,255,255,0.14);border-color:rgba(255,255,255,0.32)}}
.dl{{overflow-y:auto;flex:1;scrollbar-width:thin;scrollbar-color:rgba(255,255,255,0.18) transparent}}
.di{{display:flex;align-items:center;gap:8px;padding:5px 6px;border-radius:6px;cursor:pointer;
     color:rgba(255,255,255,0.85);font-size:12px;white-space:nowrap}}
.di:hover{{background:rgba(255,255,255,0.08)}}
.di input{{accent-color:#4a9eff;cursor:pointer;flex-shrink:0}}
.sep{{height:1px;background:rgba(255,255,255,0.10);margin:4px 0}}
</style></head><body>
<div class="wrap"><table id="t">
  <thead><tr>{headers_html}</tr></thead>
  <tbody>{rows_html}</tbody>
</table></div>
{f'''<div style="background:rgba(37,99,235,0.15);border-top:1px solid rgba(255,255,255,0.10);
  border-radius:0 0 8px 8px;padding:10px 16px;display:flex;gap:28px;flex-wrap:wrap;margin-top:4px">
  {footer_html}</div>''' if footer_html else ''}
<script>
var F={{}};
var NC={n_cols};
function vals(ci){{
  var s=new Set();
  document.querySelectorAll('#t tbody tr').forEach(function(r){{
    var c=r.querySelectorAll('td')[ci];
    if(c)s.add(c.textContent.trim());
  }});
  return Array.from(s).sort(function(a,b){{return a.localeCompare(b,undefined,{{numeric:true}})}});
}}
function apply(){{
  document.querySelectorAll('#t tbody tr').forEach(function(r){{
    var cs=r.querySelectorAll('td'),ok=true;
    Object.keys(F).forEach(function(ci){{
      var c=cs[parseInt(ci)];
      if(c&&!F[ci].has(c.textContent.trim()))ok=false;
    }});
    r.style.display=ok?'':'none';
  }});
  document.querySelectorAll('.hd').forEach(function(h,i){{h.classList.toggle('on',!!F[i]);}});
}}
function openFilter(ci,th){{
  var ex=document.getElementById('_dd');
  if(ex){{var prev=ex.dataset.col;ex.remove();if(prev==ci)return;}}
  var vs=vals(ci),cur=F[ci]||null;
  var rect=th.getBoundingClientRect();
  var dd=document.createElement('div');
  dd.className='dd';dd.id='_dd';dd.dataset.col=ci;
  dd.style.cssText='top:'+(rect.bottom+3)+'px;left:'+Math.min(rect.left,window.innerWidth-230)+'px';
  var si=document.createElement('input');si.className='ds';si.placeholder='Buscar...';dd.appendChild(si);
  var dl=document.createElement('div');dl.className='dl';
  function mkItem(lbl,chk,cls,onChg){{
    var lab=document.createElement('label');lab.className='di';
    var cb=document.createElement('input');cb.type='checkbox';cb.className=cls;cb.checked=chk;
    cb.onchange=function(){{onChg(cb.checked);}};
    lab.appendChild(cb);lab.appendChild(document.createTextNode(' '+lbl));
    return lab;
  }}
  dl.appendChild(mkItem('(Selecionar tudo)',!cur,'ai',function(v){{
    dl.querySelectorAll('.vi').forEach(function(c){{c.checked=v;}});
    if(v)delete F[ci]; else F[ci]=new Set(vs); apply();
  }}));
  var sp=document.createElement('div');sp.className='sep';dl.appendChild(sp);
  vs.forEach(function(val){{
    var item=mkItem(val,!cur||cur.has(val),'vi',function(){{
      var sel=new Set();
      dl.querySelectorAll('.vi').forEach(function(c){{if(c.checked)sel.add(c.dataset.val);}});
      if(sel.size===vs.length){{delete F[ci];dl.querySelector('.ai').checked=true;}}
      else{{F[ci]=sel;dl.querySelector('.ai').checked=false;}}
      apply();
    }});
    item.querySelector('.vi').dataset.val=val;dl.appendChild(item);
  }});
  si.oninput=function(){{
    var q=si.value.toLowerCase();
    Array.from(dl.children).slice(2).forEach(function(it){{
      it.style.display=it.textContent.toLowerCase().includes(q)?'':'none';
    }});
  }};
  dd.appendChild(dl);document.body.appendChild(dd);si.focus();
}}
document.addEventListener('mousedown',function(e){{
  if(!e.target.closest('#_dd')&&!e.target.closest('.hd')){{
    var ex=document.getElementById('_dd');if(ex)ex.remove();
  }}
}});
var SORT={{ci:-1,dir:0}};
function parseVal(s){{
  var t=String(s).trim();
  var dm=t.match(/^(\\d{{2}})\\/(\\d{{2}})\\/(\\d{{4}})$/);
  if(dm)return parseInt(dm[3]+dm[2]+dm[1],10);
  var n=parseFloat(t.replace(/[R$%+\\s]/g,'').replace(/,/g,''));
  return isNaN(n)?t:n;
}}
function sortBy(ci){{
  if(SORT.ci===ci){{SORT.dir=(SORT.dir+1)%3;}}else{{SORT.ci=ci;SORT.dir=1;}}
  var tb=document.querySelector('#t tbody');
  var rows=Array.from(tb.querySelectorAll('tr'));
  if(SORT.dir===0){{
    rows.sort(function(a,b){{return parseInt(a.dataset.orig)-parseInt(b.dataset.orig);}});
  }}else{{
    rows.sort(function(a,b){{
      var av=parseVal((a.querySelectorAll('td')[ci]||{{}}).textContent||'');
      var bv=parseVal((b.querySelectorAll('td')[ci]||{{}}).textContent||'');
      if(typeof av==='number'&&typeof bv==='number')return SORT.dir===1?av-bv:bv-av;
      return SORT.dir===1?String(av).localeCompare(String(bv)):String(bv).localeCompare(String(av));
    }});
  }}
  rows.forEach(function(r){{tb.appendChild(r);}});
  document.querySelectorAll('.hd').forEach(function(h,i){{
    h.classList.toggle('srt',i===SORT.ci&&SORT.dir>0);
  }});
}}
</script>
</body></html>"""

    try:
        st.iframe(html, height=iframe_h)
    except (AttributeError, TypeError):
        components.html(html, height=iframe_h, scrolling=False)


def show_login_form(
    title: str = "Acesso Restrito",
    subtitle: str = "Insira suas credenciais para continuar.",
    logo_path: str = None,
) -> tuple:
    """
    Renderiza um formulário de login centralizado com estilo glass.
    Retorna (user_name, password, submitted).

    Exemplo:
        user_name, password, submitted = show_login_form(title="Meu App")
        if submitted:
            if password == "senha":
                st.session_state["role"] = "user"
                st.rerun()
    """
    import os
    st.markdown("<div style='height: 60px'></div>", unsafe_allow_html=True)
    _, col, _ = st.columns([1, 2, 1])
    with col:
        if logo_path and os.path.exists(logo_path):
            try:
                st.image(logo_path, width=160)
            except:
                pass
        st.title(title)
        st.write(subtitle)
        with st.form("glass_login_form"):
            user_name = st.text_input("Seu Nome")
            password  = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar", use_container_width=True)
    return user_name, password, submitted


# ══════════════════════════════════════════════════════════════════════════════
# DEMO (executar direto: python glass_design_system.py → abre app de teste)
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    st.set_page_config(page_title="Glass Design System — Demo", layout="wide")

    inject_glass_css()

    st.title("Glass Design System")
    st.write("Demonstração de todos os componentes estilizados.")

    st.header("Métricas")
    c1, c2, c3 = st.columns(3)
    c1.metric("Valor Base", "R$ 1.234.567,00")
    c2.metric("Com Reajuste", "R$ 1.357.023,70", "+R$ 122.456,70 (+9.92%)")
    c3.metric("Impacto Operação", "+0.0034%", "no total da rede")

    st.header("Inputs")
    col1, col2, col3 = st.columns(3)
    with col1: st.text_input("Nome do Prestador")
    with col2: st.selectbox("UF", ["CE", "SP", "RJ", "MG"])
    with col3: st.number_input("Percentual (%)", value=3.25, step=0.01)

    st.header("Botões e Alertas")
    c1, c2, c3 = st.columns(3)
    c1.button("Calcular Reajuste", type="primary", use_container_width=True)
    c2.button("Exportar PDF", use_container_width=True)
    c3.button("Sair", use_container_width=True)

    glass_banner("Processamento concluído com sucesso!", color="#1eb464", icon="✅")
    glass_banner("Atenção: 2 meses sem índice cadastrado.", color="#e0c040", icon="⚠️")

    st.header("Abas")
    t1, t2, t3 = st.tabs(["Calculadora", "Configurações", "Dados"])
    with t1: st.write("Conteúdo da aba 1")
    with t2: st.write("Conteúdo da aba 2")
    with t3: st.write("Conteúdo da aba 3")

    glass_card("<h3 style='margin:0 0 8px 0'>Card Customizado</h3><p style='margin:0;color:rgba(255,255,255,0.7)'>Use glass_card() para qualquer conteúdo HTML dentro de um card glassmorphism.</p>")
