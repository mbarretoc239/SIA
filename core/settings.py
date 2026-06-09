import os
import sys

# ==========================================
# CONSTANTES DE DADOS EMBUTIDOS
# ==========================================

# ==========================================
# TEMA VISUAL SIA v5
# ==========================================
TEMA = {
    "bg_app": "#081120",
    "bg_shell": "#0B1526",
    "bg_surface": "#0F1B2D",
    "bg_surface_2": "#13233A",
    "bg_surface_3": "#182C47",
    "bg_sidebar": "#0A1424",
    "bg_overlay": "#101B2E",

    "azul_primario": "#4F8CFF",
    "azul_secundario": "#3B76E6",
    "azul_hover": "#2F63C7",
    "azul_sidebar": "#11233D",
    "azul_sidebar_hover": "#1A3153",
    "azul_fundo": "#081120",
    "azul_fundo_escuro": "#050B15",

    "branco": "#F8FAFC",
    "branco_suave": "#D7E3F4",
    "branco_card": "#0F1B2D",

    "texto_claro": "#F8FAFC",
    "texto_escuro": "#E8EEF8",
    "texto_secundario": "#91A4C2",
    "texto_muted": "#6F84A5",

    "laranja": "#F59E0B",
    "laranja_hover": "#D98708",

    "erro": "#EF5350",
    "sucesso": "#22C55E",
    "aviso": "#38BDF8",
    "borda": "#223652",
    "borda_forte": "#2F4B70"
}

# Configurações de Banco de Dados
DB_NAME = "sia_auditoria.db"

# Funções auxiliares de configuração
def caminho_recurso(caminho_relativo):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(sys.argv[0]) or ".")
    return os.path.join(base_path, caminho_relativo)
