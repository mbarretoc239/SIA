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


@st.cache_data(ttl=60)
def carregar_alinhamentos_pendentes_cache(usuario_id, role):
    """Cache de 1min sobre DatabaseManager.carregar_alinhamentos_pendentes --
    substitui um fragment(run_every=15) que rodava sozinho a cada 15s em
    app.py, mesmo sem nenhuma interação do usuário (3 consultas por tick,
    10 pessoas com aba aberta 8h = ~57 mil consultas/dia só nisso, visto em
    2026-09-23 via pg_stat_user_tables, ver docs/turso_bloqueado_2026-09-23.md).
    Agora só é chamada como parte do rerun normal do Streamlit -- não refaz
    a consulta de novo antes de 1min, mesmo com vários reruns seguidos.

    Precisa de `.clear()` sempre que a lista de pendentes de alguém pode ter
    mudado: depois de marcar como lido/ciente (app.py::mostrar_alinhamento_dialog)
    e depois de criar/inativar/resetar ciência de um alinhamento
    (views/5_Alinhamentos.py) -- senão o próprio usuário veria o popup
    reaparecer com a lista antiga, ou um alinhamento novo demoraria até 1min
    pra aparecer pra quem já está com a tela aberta."""
    from shared.database import DatabaseManager
    return DatabaseManager().carregar_alinhamentos_pendentes(usuario_id, role)


@st.cache_data(ttl=300)
def carregar_meus_links_cache(usuario_id):
    """Cache de 5min sobre DatabaseManager.carregar_meus_links --
    app.py::398 chama isso no sidebar, SEM cache nenhum, em TODO rerun do
    app inteiro (não é um timer, é literalmente qualquer clique em
    qualquer tela, de qualquer usuário -- ainda mais frequente que o
    polling de alinhamentos que rodava a cada 15s). Achado em 2026-09-23
    via log de requisições (usuario_links foi a 4ª tabela mais lida do
    dia), ver docs/turso_bloqueado_2026-09-23.md. Precisa de `.clear()`
    depois de adicionar/editar/excluir um link (app.py e
    views/1_Configuracoes.py), senão a pessoa não veria a mudança na hora."""
    from shared.database import DatabaseManager
    return DatabaseManager().carregar_meus_links(usuario_id)


# Módulos com acesso configurável por role (ver views/1_Configuracoes.py)
# Admin sempre tem acesso a todos, independente da configuração.
MODULOS_CONTROLADOS = {
    "relatorio_5302": "Relatório 5302",
    "calculadora_glosa": "Calculadora de Glosa",
    "producao": "Análise de Produção",
    "copia_rapida": "Cópia Rápida (Cabeçalhos)",
    "amostragem": "Amostragem",
    "produtividade": "Produtividade",
    # Sub-recursos dentro de um módulo -- mesma mecânica (permissão por role +
    # exceção por usuário), só que travando uma PARTE da tela em vez do
    # módulo inteiro. Hoje só tem esse; outros pontos hoje hardcoded pra
    # Gestor/Admin (ver views/7_Amostragem_Beta.py e views/8_Produtividade.py)
    # podem virar entradas aqui do mesmo jeito, se precisar de exceção por
    # usuário no futuro.
    "amostragem_lista_processos": "Amostragem — Lista de processos do mês",
    # Sem linha em permissoes_modulos só o Admin acessa (ver tem_acesso_modulo);
    # liberar pra outra role/usuário é em Configurações > Permissões.
    "farol_mensal": "Farol Mensal",
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


@st.cache_data(ttl=60)
def buscar_ultimo_alinhamento_visivel_cache(role):
    """Cache de 60s sobre DatabaseManager.buscar_ultimo_alinhamento_visivel
    -- a Home (views/0_Dashboard.py) chamava a versão sem cache/sem limit
    no topo do arquivo, em todo rerun (achado em 2026-09-23, ver
    docs/turso_bloqueado_2026-09-23.md). TTL curto pelo mesmo motivo de
    carregar_alinhamentos_pendentes_cache: um alinhamento novo precisa
    aparecer rápido pra quem está com a Home aberta."""
    from shared.database import DatabaseManager
    return DatabaseManager().buscar_ultimo_alinhamento_visivel(role)


# --- Tela de Alinhamentos (views/5_Alinhamentos.py) ---
# As leituras abaixo rodavam sem cache no corpo da tela, e o Streamlit roda
# todas as abas a cada clique: um gestor disparava 6 consultas por
# interação. Em 2026-09-24, um deploy com a tela aberta gerou 73 leituras de
# alinhamentos_historico_status em 5min (a página reconectando a cada ~3s).
# TTL longo porque toda escrita em alinhamentos acontece dentro do app e
# chama limpar_caches_alinhamentos() -- o TTL é só rede de segurança.


@st.cache_data(ttl=1800)
def carregar_alinhamentos_visiveis_cache(role):
    from shared.database import DatabaseManager
    return DatabaseManager().carregar_alinhamentos_visiveis(role)


@st.cache_data(ttl=1800)
def carregar_alinhamentos_cache():
    """Todos os não excluídos (aba Gerenciar, e a aba de testes em Configurações)."""
    from shared.database import DatabaseManager
    return DatabaseManager().carregar_alinhamentos()


@st.cache_data(ttl=1800)
def carregar_alinhamentos_excluidos_cache():
    from shared.database import DatabaseManager
    return DatabaseManager().carregar_alinhamentos_excluidos()


@st.cache_data(ttl=1800)
def carregar_historico_status_alinhamentos_cache():
    from shared.database import DatabaseManager
    return DatabaseManager().carregar_historico_status_alinhamentos()


@st.cache_data(ttl=300)
def contar_leituras_por_alinhamento_cache():
    """Badge "X/Y cientes" da aba Gerenciar. Muda a cada "Estou Ciente"
    (app.py limpa na hora); TTL menor cobre confirmações feitas por fora
    disso (ex.: cadastro de usuário novo marcando tudo como lido)."""
    from shared.database import DatabaseManager
    return DatabaseManager().contar_leituras_por_alinhamento()


def limpar_caches_alinhamentos():
    """Chamar depois de qualquer escrita em alinhamentos (publicar, editar,
    inativar, reativar, excluir, restaurar, disparar ciência de novo). Limpa
    pra todos os usuários -- escrita em alinhamento é rara, e um comunicado
    novo precisa aparecer pra todo mundo na hora."""
    carregar_alinhamentos_visiveis_cache.clear()
    carregar_alinhamentos_cache.clear()
    carregar_alinhamentos_excluidos_cache.clear()
    carregar_historico_status_alinhamentos_cache.clear()
    contar_leituras_por_alinhamento_cache.clear()
    buscar_ultimo_alinhamento_visivel_cache.clear()
    carregar_alinhamentos_pendentes_cache.clear()


@st.cache_data(ttl=3600)
def listar_links_padrao_cache(incluir_inativos=False, role=None):
    """Cache de 1h sobre DatabaseManager.listar_links_padrao -- a Home
    (views/0_Dashboard.py) chamava a versão sem cache no topo do arquivo,
    em todo rerun da página mais visitada do app (achado em 2026-09-23,
    ver docs/turso_bloqueado_2026-09-23.md). Só muda quando um link é
    editado em Configurações, que já chama `.clear()` logo depois."""
    from shared.database import DatabaseManager
    return DatabaseManager().listar_links_padrao(incluir_inativos, role)


@st.cache_data(ttl=60)
def listar_usuarios_cache():
    """Cache de 60s sobre DatabaseManager.listar_usuarios -- usado em 3
    lugares (Configurações, Alinhamentos) sem cache nenhum. TTL curto
    porque a fila de aprovação de cadastro (Configurações) precisa
    refletir rápido um novo usuário pendente; os pontos que mudam a
    tabela já chamam `.clear()`."""
    from shared.database import DatabaseManager
    return DatabaseManager().listar_usuarios()


@st.cache_data(ttl=3600)
def carregar_textos_prestador_cache():
    """Cache de 1h sobre DatabaseManager.carregar_textos_prestador --
    catálogo pequeno e global de "Textos Padrões ao Prestador", lido sem
    cache toda vez que alguém gera um texto no Relatório 5302 (views/2_
    Relatorio_5302.py), uma das ações mais comuns do app (10 pessoas,
    várias vezes/dia cada). Só muda quando alguém edita em Configurações
    (views/1_Configuracoes.py), que já chama `.clear()` logo após
    inserir/atualizar/excluir."""
    from shared.database import DatabaseManager
    return DatabaseManager().carregar_textos_prestador()
