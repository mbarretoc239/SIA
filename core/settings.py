import streamlit as st

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

# Hierarquia de roles para o sistema de Alinhamentos
NIVEL_HIERARQUIA = {
    "Contas": 1,
    "Auditor": 2,
    "CISO": 3,
    "Gestor": 4,
    "Admin": 4,
}

# Roles sujeitos ao pop-up obrigatório "Estou Ciente"
ROLES_CIENCIA_OBRIGATORIA = {"Contas", "Auditor", "CISO"}

# Módulos com acesso configurável por role (ver views/1_Configuracoes.py)
# Admin sempre tem acesso a todos, independente da configuração.
MODULOS_CONTROLADOS = {
    "relatorio_5302": "Relatório 5302",
    "calculadora_glosa": "Calculadora de Glosa",
    "producao": "Análise de Produção",
    "copia_rapida": "Cópia Rápida (Cabeçalhos)",
    "amostragem": "Amostragem",
    "produtividade": "Produtividade",
}

# Roles cujo acesso aos módulos acima é configurável
ROLES_PERMISSAO = ["Contas", "Auditor", "CISO", "Gestor"]


def tem_acesso_modulo(permissoes, role, modulo, usuario_id=None, excecoes=None):
    """Verifica se o usuário tem acesso ao módulo.

    Checa primeiro se há uma exceção individual (DatabaseManager.carregar_excecoes_modulos)
    para usuario_id+modulo — se houver, ela vale independente da role, inclusive Admin.
    Sem exceção, cai na regra por role (DatabaseManager.carregar_permissoes_modulos),
    onde Admin sempre tem acesso."""
    if usuario_id and excecoes:
        for e in excecoes:
            if e.get("usuario_id") == usuario_id and e.get("modulo") == modulo:
                return bool(e.get("habilitado"))
    if role == "Admin":
        return True
    for p in permissoes:
        if p.get("modulo") == modulo and p.get("role") == role:
            return bool(p.get("habilitado"))
    return False


@st.cache_data(ttl=60)
def carregar_permissoes_modulos_cache():
    """Versão cacheada (60s) de DatabaseManager.carregar_permissoes_modulos()
    -- pra checagens de acesso que rodam a cada rerun da página (ex: FAB da
    Amostragem), não só uma vez no carregamento (onde a versão sem cache é
    aceitável)."""
    from shared.database import DatabaseManager
    return DatabaseManager().carregar_permissoes_modulos()


@st.cache_data(ttl=60)
def carregar_excecoes_modulos_cache():
    """Mesma ideia de carregar_permissoes_modulos_cache(), pra exceções."""
    from shared.database import DatabaseManager
    return DatabaseManager().carregar_excecoes_modulos()
