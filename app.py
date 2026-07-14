import streamlit as st
import re
import time
from shared.database import DatabaseManager

# Configuração da Página principal (deve ser a primeira coisa)
st.set_page_config(
    page_title="SIA Web - Auditoria",
    page_icon="️",
    layout="wide"
)

# Injeta o Design System Liquid Glass
from core.glass_design_system import inject_glass_css
inject_glass_css()

# Inicializa Banco de Dados sempre instanciando a classe nova
db = DatabaseManager()
st.session_state.db = db

# Inicializa o controlador de cookies
from streamlit_cookies_controller import CookieController
cookie_controller = CookieController()

# Processa pendências de cookies ANTES de renderizar a tela
if "_set_auth_cookie" in st.session_state:
    _token = st.session_state.pop("_set_auth_cookie")
    cookie_controller.set("sia_auth", _token, max_age=28800)

if "_remove_auth_cookie" in st.session_state:
    st.session_state.pop("_remove_auth_cookie")
    cookie_controller.remove("sia_auth")


def _expirar_cookie_sessao():
    """Expira o cookie 'sia_auth' via JS direto (document.cookie).

    cookie_controller.remove() depende de um round-trip com o componente
    iframe que nem sempre se completa antes do rerun, deixando o cookie
    antigo no navegador e fazendo o auto-login reativar a conta anterior.
    Um <script> injetado via components.html executa de forma síncrona ao
    ser parseado pelo navegador, sem depender desse round-trip.
    """
    import streamlit.components.v1 as components
    components.html(
        "<script>document.cookie = 'sia_auth=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax';</script>",
        height=0,
    )

@st.dialog("Aviso do Sistema", width="large")
def mostrar_alinhamento_dialog(alinhamento, usuario_id):
    is_inativacao = not alinhamento.get("ativo", True)
    
    st.caption(f"Categoria: {alinhamento.get('categoria', 'Geral')}")
    
    if is_inativacao:
        st.error("⚠️ **AVISO DE REVOGAÇÃO DE REGRA**")
        st.markdown(f"~~{alinhamento['titulo']}~~")
        st.markdown(alinhamento["conteudo"])
        st.warning(f"**Motivo da Inativação:**\n{alinhamento.get('justificativa_inativacao', 'Sem justificativa fornecida.')}")
        st.divider()
        if st.button("Estou ciente de que esta regra NÃO vale mais", type="primary", use_container_width=True):
            db.marcar_inativacao_lida(alinhamento["id"], usuario_id)
            st.session_state["alinhamentos_pendentes"].pop(0)
            st.rerun()
    else:
        st.subheader(alinhamento["titulo"])
        st.markdown(alinhamento["conteudo"])
        st.divider()
        if st.button("Estou Ciente", type="primary", use_container_width=True):
            db.marcar_alinhamento_lido(alinhamento["id"], usuario_id)
            st.session_state["alinhamentos_pendentes"].pop(0)
            st.rerun()


def validar_senha(senha):
    if len(senha) < 6: return False, "A senha deve ter pelo menos 6 caracteres."
    if not re.search(r"[A-Z]", senha): return False, "A senha deve conter pelo menos uma letra maiúscula."
    if not re.search(r"[0-9]", senha): return False, "A senha deve conter pelo menos um número."
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", senha): return False, "A senha deve conter pelo menos um caractere especial."
    return True, ""

def tela_login():
    st.markdown("<h1 style='text-align: center; color: #2C3E50;'>SIA Auditoria Modular</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #7F8C8D;'>Plataforma centralizada de gestão em auditoria odontológica.</p>", unsafe_allow_html=True)
    
    col_vazia1, col_login, col_vazia2 = st.columns([1, 2, 1])
    
    with col_login:
        st.write("") 
        
        tab_entrar, tab_cadastrar = st.tabs([" Entrar", " Cadastrar-se"])
        
        with tab_entrar:
            with st.container(border=True):
                st.subheader("Login Seguradora")
                usuario = st.text_input("Usuário SIGO", key="login_usr")
                senha = st.text_input("Senha", type="password", key="login_pwd")
                
                if st.button("Entrar no Sistema", use_container_width=True, type="primary"):
                    if not usuario or not senha:
                        st.warning("Preencha o usuário e a senha.")
                    else:
                        # Fallback Admin de Emergência (credenciais em st.secrets["admin_emergencia"])
                        _adm = st.secrets.get("admin_emergencia", {})
                        if usuario == _adm.get("usuario", "") and senha == _adm.get("senha", ""):
                            st.session_state["logado"] = True
                            st.session_state["auditor_nome"] = "Administrador"
                            st.session_state["role_interno"] = "Admin"
                            st.session_state["usuario_id"] = "000-000-000"
                            st.session_state["equipe"] = "Gestor"
                            
                            from core.auth import criar_token_sessao
                            token = criar_token_sessao("000-000-000", "Administrador", "Admin", "Gestor")
                            st.session_state["_set_auth_cookie"] = token
                            
                            st.rerun()
                        else:
                            with st.spinner("Autenticando..."):
                                user_data = db.autenticar_usuario(usuario, senha)
                                if user_data:
                                    if user_data["status"] == "Pendente":
                                        st.warning("Seu cadastro está em análise. Aguarde aprovação da gestão.")
                                    elif user_data["status"] == "Bloqueado":
                                        st.error("Conta bloqueada. Contate o administrador.")
                                    else:
                                        st.session_state["logado"] = True
                                        # Extrai apenas o primeiro nome
                                        primeiro_nome = user_data["nome_completo"].split()[0]
                                        st.session_state["auditor_nome"] = primeiro_nome
                                        st.session_state["role_interno"] = user_data["role_interno"]
                                        st.session_state["equipe"] = user_data["equipe"]
                                        st.session_state["usuario_id"] = user_data["id"]
                                        # Flag de senha temporária (bloqueia acesso ao app até trocar)
                                        st.session_state["senha_temporaria"] = bool(user_data.get("senha_temporaria", False))

                                        from core.auth import criar_token_sessao
                                        token = criar_token_sessao(user_data["id"], primeiro_nome, user_data["role_interno"], user_data["equipe"])
                                        st.session_state["_set_auth_cookie"] = token

                                        st.rerun()
                                else:
                                    st.error("Usuário ou senha incorretos.")

        with tab_cadastrar:
            with st.container(border=True):
                st.subheader("Novo Cadastro")
                st.markdown("Crie sua conta para acessar os relatórios e análises.")
                
                novo_usr = st.text_input("Usuário SIGO", help="Mesmo login utilizado no sistema da empresa")
                novo_nome = st.text_input("Nome Completo")
                nova_equipe = st.selectbox("Qual sua equipe?", ["Contas", "Auditoria", "CISO", "Gestor"])
                
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    nova_senha = st.text_input("Senha", type="password")
                with col_s2:
                    confirma_senha = st.text_input("Confirmar Senha", type="password")
                
                if st.button("Solicitar Acesso", use_container_width=True):
                    if not novo_usr or not novo_nome or not nova_senha:
                        st.warning("Preencha todos os campos obrigatórios.")
                    elif nova_senha != confirma_senha:
                        st.error("As senhas não coincidem.")
                    else:
                        valido, msg_erro = validar_senha(nova_senha)
                        if not valido:
                            st.error(msg_erro)
                        else:
                            with st.spinner("Registrando..."):
                                # No futuro, o ideal é checar se usuario_sigo já existe antes do insert
                                if db.criar_usuario(novo_usr, novo_nome, nova_senha, nova_equipe):
                                    st.success(" Aguarde aprovação do seu cadastro. Em breve será feito contato.")
                                else:
                                    st.error("Erro ao cadastrar. O usuário SIGO já existe?")

# --- AUTO LOGIN (Via Cookies) ---
if not st.session_state.get("logado", False):
    # Após um logout, a remoção do cookie no navegador (via componente
    # iframe) leva alguns reruns para se efetivar. Durante essa janela,
    # ignoramos o auto-login para não relogar o usuário com o cookie
    # ainda em trânsito de remoção.
    skip_autologin = st.session_state.get("_skip_autologin", 0)
    if skip_autologin > 0:
        st.session_state["_skip_autologin"] = skip_autologin - 1
    else:
        token = cookie_controller.get("sia_auth")
        if token:
            from core.auth import decifrar_token_sessao
            dados = decifrar_token_sessao(token)
            if dados:
                st.session_state["logado"] = True
                st.session_state["usuario_id"] = dados.get("id")
                st.session_state["auditor_nome"] = dados.get("nome")
                st.session_state["role_interno"] = dados.get("role")
                st.session_state["equipe"] = dados.get("equipe")
                st.rerun()

def tela_trocar_senha_obrigatoria():
    """Tela exibida logo apos o login quando o usuario tem senha_temporaria=True.
    Bloqueia acesso ao restante do app ate que ele defina uma senha propria."""
    st.markdown("<h1 style='text-align: center; color: #2C3E50;'>Redefinir senha</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #7F8C8D;'>Sua senha foi redefinida por um administrador. Escolha uma nova senha para continuar.</p>", unsafe_allow_html=True)

    col_v1, col_form, col_v2 = st.columns([1, 2, 1])
    with col_form:
        with st.container(border=True):
            nova = st.text_input("Nova senha", type="password", key="reset_nova")
            confirma = st.text_input("Confirmar nova senha", type="password", key="reset_confirma")

            if st.button("Salvar nova senha", use_container_width=True, type="primary"):
                if not nova or not confirma:
                    st.warning("Preencha os dois campos.")
                elif nova != confirma:
                    st.error("As senhas não coincidem.")
                else:
                    valido, msg_erro = validar_senha(nova)
                    if not valido:
                        st.error(msg_erro)
                    else:
                        uid = st.session_state.get("usuario_id")
                        if db.trocar_senha_propria(uid, nova):
                            st.session_state["senha_temporaria"] = False
                            st.success("Senha atualizada. Redirecionando...")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Erro ao atualizar a senha. Tente novamente.")

            if st.button("Sair", use_container_width=True):
                # Logout limpo mantendo o mesmo padrao do resto do app
                for k in ["logado", "usuario_id", "auditor_nome", "role_interno", "equipe", "senha_temporaria"]:
                    st.session_state.pop(k, None)
                st.session_state["_remove_auth_cookie"] = True
                st.session_state["_skip_autologin"] = 2
                _expirar_cookie_sessao()
                st.rerun()


# --- CONTROLE DE ROTAS (RBAC) ---
if not st.session_state.get("logado", False):
    tela_login()
elif st.session_state.get("senha_temporaria", False):
    tela_trocar_senha_obrigatoria()
else:
    role = st.session_state.get("role_interno", "Contas")
    permissoes = db.carregar_permissoes_modulos()

    # --- ALINHAMENTOS PENDENTES (pop-up obrigatório "Estou Ciente", com checagem ao vivo) ---
    from core.settings import ROLES_CIENCIA_OBRIGATORIA

    if role in ROLES_CIENCIA_OBRIGATORIA:
        @st.fragment(run_every=15)
        def _checar_alinhamentos_pendentes():
            pendentes = db.carregar_alinhamentos_pendentes(st.session_state.get("usuario_id"), role)
            st.session_state["alinhamentos_pendentes"] = pendentes
            
            if pendentes:
                id_e_status = f"{pendentes[0]['id']}_{pendentes[0].get('ativo')}"
                if st.session_state.get("_dialog_alinhamento_id") != id_e_status:
                    st.session_state["_dialog_alinhamento_id"] = id_e_status
                    mostrar_alinhamento_dialog(pendentes[0], st.session_state.get("usuario_id"))

        _checar_alinhamentos_pendentes()

    # Construção Dinâmica do Menu baseada no Cargo
    paginas = []
    
    # Todos (Dashboard de Entrada/Bem vindo)
    paginas.append(st.Page("views/0_Dashboard.py", title="Início"))
    
    # Amostragem: visível para todos os logados
    paginas.append(st.Page("views/6_Amostragem.py", title="Amostragem"))

    # Permissões Módulos Clínicos (configurável por role em Configurações)
    from core.settings import tem_acesso_modulo
    if tem_acesso_modulo(permissoes, role, "relatorio_5302"):
        paginas.append(st.Page("views/2_Relatorio_5302.py", title="Relatório 5302"))
    if tem_acesso_modulo(permissoes, role, "calculadora_glosa"):
        paginas.append(st.Page("views/3_Calculadora.py", title="Calculadora de Glosa"))
    if tem_acesso_modulo(permissoes, role, "producao"):
        paginas.append(st.Page("views/4_Producao.py", title="Análise de Produção"))

    # Alinhamentos: visível para todos, conteúdo se ajusta por nível dentro da tela
    paginas.append(st.Page("views/5_Alinhamentos.py", title="Alinhamentos"))

    # Todos podem ver a TELA de Configuração, mas o CONTEÚDO lá dentro se protege sozinho
    paginas.append(st.Page("views/1_Configuracoes.py", title="Configurações"))
    
    # Registra as páginas sem exibir o menu padrão no topo
    pg = st.navigation(paginas, position="hidden")
    
    st.sidebar.divider()
    st.sidebar.title(f"Olá, {st.session_state.get('auditor_nome', 'Auditor')}")
    st.sidebar.caption(f"Cargo: {role}")
    st.sidebar.divider()
    
    # Renderiza o menu manualmente para garantir a ordem
    for p in paginas:
        st.sidebar.page_link(p, label=p.title)
        
    st.sidebar.divider()
    
    # Expansível de Links Úteis (Disponível para todos)
    with st.sidebar.expander(" Links", expanded=False):
        meus_links = db.carregar_meus_links(st.session_state.get("usuario_id", ""))
        
        if meus_links:
            for link in meus_links:
                st.link_button(f" {link.get('titulo')}", url=link.get('url'), use_container_width=True)
        else:
            st.caption("Nenhum link cadastrado.")
            
        st.page_link("views/1_Configuracoes.py", label=" Adicionar Link")
        
    pg.run()
    
    st.sidebar.divider()
    
    if tem_acesso_modulo(permissoes, role, "copia_rapida"):
        st.sidebar.markdown("**Cópia Rápida (Cabeçalhos)**")
        
        texto_com = "PROCESSO ANALISADO POR AMOSTRAGEM DAS ESPECIALIDADES CRÍTICAS"
        texto_sem = "PROCESSO SEM ESPECIALIDADES CRÍTICAS ANALISADO POR AMOSTRAGEM DO ENVIO DE IMAGENS"
        
        html_sidebar = f"""
        <style>
            .native-btn {{
                background: #f0f2f6;
                border: 1px solid #c9cdd4;
                border-radius: 4px;
                color: #31333F;
                font-family: "Source Sans Pro", sans-serif;
                font-size: 14px;
                padding: 0.5rem 1rem;
                cursor: pointer;
                width: 100%;
                margin-bottom: 5px;
            }}
            .native-btn:hover {{
                border-color: #ff4b4b;
                color: #ff4b4b;
            }}
        </style>
        <script>
        function copyFast(txt, id, original_text) {{
            navigator.clipboard.writeText(txt).then(function() {{
                var btn = document.getElementById(id);
                btn.innerText = ' Copiado!';
                setTimeout(() => btn.innerText = original_text, 2000);
            }});
        }}
        </script>
        <div style="display: flex; flex-direction: column; gap: 8px;">
            <button id="btn_f1" class="native-btn" onclick="copyFast(`{texto_com}`, 'btn_f1', ' Com especialidades')"> Com especialidades</button>
            <button id="btn_f2" class="native-btn" onclick="copyFast(`{texto_sem}`, 'btn_f2', ' Sem especialidades')"> Sem especialidades</button>
        </div>
        """
        with st.sidebar:
            import streamlit.components.v1 as components
            components.html(html_sidebar, height=95)
            st.divider()
    
    if st.sidebar.button("Sair", use_container_width=True):
        st.session_state.clear()
        st.session_state["_skip_autologin"] = 3
        st.session_state["_remove_auth_cookie"] = True
        st.rerun()
