import streamlit as st
import re
from shared.database import DatabaseManager

# Configuração da Página principal (deve ser a primeira coisa)
st.set_page_config(
    page_title="SIA Web - Auditoria",
    page_icon="🛡️",
    layout="wide"
)

# Inicializa Banco de Dados sempre instanciando a classe nova
db = DatabaseManager()
st.session_state.db = db

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
        
        tab_entrar, tab_cadastrar = st.tabs(["🔒 Entrar", "📝 Cadastrar-se"])
        
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
                    nova_senha = st.text_input("Senha", type="password", help="Mínimo 6 chars, 1 Maiúscula, 1 Número, 1 Especial")
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
                                    st.success("✅ Aguarde aprovação do seu cadastro. Em breve será feito contato.")
                                else:
                                    st.error("Erro ao cadastrar. O usuário SIGO já existe?")

# --- CONTROLE DE ROTAS (RBAC) ---
if not st.session_state.get("logado", False):
    tela_login()
else:
    role = st.session_state.get("role_interno", "Contas")
    
    st.sidebar.title(f"Olá, {st.session_state.get('auditor_nome', 'Auditor')}")
    st.sidebar.caption(f"Cargo: {role}")
    
    # Construção Dinâmica do Menu baseada no Cargo
    paginas = []
    
    # Todos (Dashboard de Entrada/Bem vindo)
    paginas.append(st.Page("views/0_Dashboard.py", title="Painel Principal", icon="🏠"))
    
    # Permissões Módulos Clínicos (Auditor, CISO, Gestor, Admin)
    if role in ["Auditor", "CISO", "Gestor", "Admin"]:
        paginas.append(st.Page("views/2_Relatorio_5302.py", title="Relatório 5302", icon="📄"))
        paginas.append(st.Page("views/3_Calculadora.py", title="Calculadora de Glosa", icon="🧮"))
        paginas.append(st.Page("views/4_Producao.py", title="Análise de Produção", icon="📈"))
        
    # Todos podem ver a TELA de Configuração, mas o CONTEÚDO lá dentro se protege sozinho
    paginas.append(st.Page("views/1_Configuracoes.py", title="Configurações", icon="⚙️"))
    
    pg = st.navigation(paginas)
    pg.run()
    
    st.sidebar.divider()
    
    if role in ["Auditor", "CISO", "Gestor", "Admin"]:
        st.sidebar.markdown("**Cópia Rápida (Cabeçalhos)**")
        
        texto_com = "PROCESSO ANALISADO POR AMOSTRAGEM DAS ESPECIALIDADES CRÍTICAS"
        texto_sem = "PROCESSO SEM ESPECIALIDADES CRÍTICAS ANALISADO POR AMOSTRAGEM DO ENVIO DE IMAGENS"
        
        html_sidebar = f"""
        <script>
        function copyFast(txt, id, original_text) {{
            navigator.clipboard.writeText(txt).then(function() {{
                var btn = document.getElementById(id);
                btn.innerText = '✅ Copiado!';
                setTimeout(() => btn.innerText = original_text, 2000);
            }});
        }}
        </script>
        <div style="display: flex; flex-direction: column; gap: 8px;">
            <button id="btn_f1" onclick="copyFast(`{texto_com}`, 'btn_f1', '📋 Com especialidades')" style="background-color: #2b2b36; color: white; border: 1px solid rgba(250,250,250,0.2); padding: 0.4rem 0.6rem; border-radius: 0.4rem; cursor: pointer; font-family: sans-serif; font-size: 14px; text-align: left;">📋 Com especialidades</button>
            <button id="btn_f2" onclick="copyFast(`{texto_sem}`, 'btn_f2', '📋 Sem especialidades')" style="background-color: #2b2b36; color: white; border: 1px solid rgba(250,250,250,0.2); padding: 0.4rem 0.6rem; border-radius: 0.4rem; cursor: pointer; font-family: sans-serif; font-size: 14px; text-align: left;">📋 Sem especialidades</button>
        </div>
        """
        with st.sidebar:
            import streamlit.components.v1 as components
            components.html(html_sidebar, height=95)
            st.divider()
    if st.sidebar.button("Sair", use_container_width=True):
        # Limpa sessão
        st.session_state.clear()
        st.rerun()
