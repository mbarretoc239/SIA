import streamlit as st
import pandas as pd
import io
from shared.database import DatabaseManager
from core.glass_design_system import render_glass_table
from services.relatorio_5302.glosa_matcher import carregar_mapa_subglosas, carregar_mapa_procedimentos

st.set_page_config(page_title="Configurações", page_icon="️", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar as configurações.")
    st.stop()

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()
db = st.session_state.db

role = st.session_state.get("role_interno", "Contas")
nome = st.session_state.get("auditor_nome", "Usuário")

st.title("️ Painel de Controle e Configurações")
st.markdown("Gerencie seu perfil, aprove cadastros da equipe e configure as regras do motor inteligente.")

# Define quais abas o usuário tem acesso
nomes_abas = []
nomes_abas.append("Meu Perfil")
nomes_abas.append("Meus Links Úteis")

if role == "Admin":
    nomes_abas.append("Aprovação da Equipe")

if role in ["Admin", "Gestor"]:
    nomes_abas.append("Permissões de Acesso")
    nomes_abas.append("Textos para Prestadores")
    nomes_abas.append("Links Home")
    nomes_abas.append("Tabelas Base e Glosas")

if role == "Admin":
    nomes_abas.append("Debug/Testes")

abas = st.tabs(nomes_abas)

# ==========================================
# ABA 1: MEU PERFIL (TODOS)
# ==========================================
with abas[0]:
    st.subheader("Informações da Conta")
    st.info(f"**Nome:** {nome}\n\n**Equipe original:** {st.session_state.get('equipe', 'N/A')}\n\n**Nível de Acesso (Role):** {role}")
    st.info(f"**Nome:** {nome}\n\n**Equipe original:** {st.session_state.get('equipe', 'N/A')}\n\n**Nível de Acesso (Role):** {role}")

# ==========================================
# ABA 2: LINKS ÚTEIS (TODOS)
# ==========================================
if "Meus Links Úteis" in nomes_abas:
    aba_idx = nomes_abas.index("Meus Links Úteis")
    with abas[aba_idx]:
        st.subheader("Meus Links e Atalhos Rápidos")
        st.markdown("Cadastre aqui os links que você mais usa. Eles aparecerão na barra lateral para acesso rápido!")
        
        col_head_1, col_head_2 = st.columns([1, 3])
        with col_head_1:
            st.write("")
            if st.button("➕ Adicionar Novo Link", type="primary", use_container_width=True, key="btn_add_meu_link"):
                st.session_state["meu_link_em_edicao"] = "NOVO"

        em_edicao = st.session_state.get("meu_link_em_edicao", None)
        if em_edicao:
            st.divider()
            st.subheader("Novo Link")
            with st.container(border=True):
                c1, c2 = st.columns([2, 3])
                with c1:
                    link_titulo = st.text_input("Título do Link", placeholder="Ex: Portal TUSS", key="ml_titulo")
                with c2:
                    link_url = st.text_input("URL (Endereço)", placeholder="Ex: https://...", key="ml_url")
                
                b1, b2, b3 = st.columns([2, 2, 8])
                if b1.button(" Salvar", type="primary", use_container_width=True, key="ml_salvar"):
                    if link_titulo and link_url:
                        if db.inserir_link_util(st.session_state.get("usuario_id", ""), link_titulo, link_url):
                            st.success("Link salvo com sucesso!")
                            st.session_state["meu_link_em_edicao"] = None
                            st.rerun()
                        else:
                            st.error("Erro ao salvar link.")
                    else:
                        st.warning("Preencha o título e a URL.")
                if b2.button("Cancelar", use_container_width=True, key="ml_cancelar"):
                    st.session_state["meu_link_em_edicao"] = None
                    st.rerun()
                    
        st.divider()
        st.markdown("### Links Cadastrados")
        
        meus_links = db.carregar_meus_links(st.session_state.get("usuario_id", ""))
        
        em_edicao_id = st.session_state.get("meu_link_editando_id", None)
        if em_edicao_id:
            link_alvo = next((l for l in meus_links if l.get('id') == em_edicao_id), None)
            if link_alvo:
                st.divider()
                st.subheader("Editar Título do Link")
                with st.container(border=True):
                    novo_tit = st.text_input("Novo Título", value=link_alvo.get("titulo", ""), key="ml_edit_tit")
                    c1, c2 = st.columns(2)
                    if c1.button("Salvar", type="primary", use_container_width=True):
                        if novo_tit:
                            if db.atualizar_titulo_link_util(link_alvo.get("id"), novo_tit):
                                st.session_state["meu_link_editando_id"] = None
                                st.rerun()
                    if c2.button("Cancelar", use_container_width=True):
                        st.session_state["meu_link_editando_id"] = None
                        st.rerun()
                st.divider()

        if not meus_links:
            st.info("Você ainda não possui links cadastrados.")
        else:
            for link in meus_links:
                with st.container(border=True):
                    col_btn, col_edit, col_del = st.columns([5, 1, 1])
                    with col_btn:
                        st.markdown(f"**{link.get('titulo')}** — [🔗 Acessar]({link.get('url')})")
                    with col_edit:
                        if st.button("Editar", key=f"edit_link_{link.get('id')}", use_container_width=True):
                            st.session_state["meu_link_editando_id"] = link.get('id')
                            st.rerun()
                    with col_del:
                        if st.button("Excluir", key=f"del_link_{link.get('id')}", use_container_width=True):
                            if db.deletar_link_util(link.get('id')):
                                st.rerun()

# ==========================================
# ABA 3: APROVAÇÃO DE EQUIPE (ADMIN)
# ==========================================
if "Aprovação da Equipe" in nomes_abas:
    aba_idx = nomes_abas.index("Aprovação da Equipe")
    with abas[aba_idx]:
        st.subheader("Fila de Moderação de Cadastros")
        
        usuarios = db.listar_usuarios()
        if not usuarios:
            st.warning("Nenhum usuário cadastrado no banco de dados ainda.")
        else:
            # Filtra apenas quem não é o próprio admin logado
            df_users = pd.DataFrame(usuarios)
            pendentes = df_users[df_users["status"] == "Pendente"]
            ativos = df_users[df_users["status"] == "Ativo"]
            
            st.markdown(f"**Cadastros Pendentes ({len(pendentes)})**")
            if pendentes.empty:
                st.success("A fila de aprovação está vazia!")
            else:
                for _, row in pendentes.iterrows():
                    with st.expander(f"⏳ {row['nome_completo']} ({row['usuario_sigo']})"):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            novo_status = st.selectbox("Status", ["Pendente", "Ativo", "Bloqueado"], key=f"s_{row['id']}")
                        with c2:
                            nova_equipe = st.selectbox("Equipe", ["Contas", "Auditoria", "CISO", "Gestor"], index=["Contas", "Auditoria", "CISO", "Gestor"].index(row['equipe']), key=f"e_{row['id']}")
                        with c3:
                            novo_role = st.selectbox("Role do Sistema", ["Contas", "Auditor", "CISO", "Gestor", "Admin"], index=["Contas", "Auditor", "CISO", "Gestor", "Admin"].index(row['role_interno']), key=f"r_{row['id']}")
                        
                        col_save, col_del = st.columns(2)
                        with col_save:
                            if st.button("Salvar Alteração", key=f"btn_{row['id']}", type="primary", use_container_width=True):
                                if db.atualizar_usuario_admin(row['id'], novo_status, novo_role, nova_equipe):
                                    st.success("Usuário atualizado com sucesso!")
                                    st.rerun()
                                else:
                                    st.error("Erro ao atualizar usuário no Supabase.")
                        with col_del:
                            if st.button("Excluir", key=f"btn_del_pend_{row['id']}", use_container_width=True):
                                if db.excluir_usuario(row['id'], role):
                                    st.success("Usuário excluído.")
                                    st.rerun()
                                else:
                                    st.error("Erro ao excluir usuário no Supabase.")
                                
            st.divider()
            st.markdown(f"**Usuários Ativos e Bloqueados ({len(ativos) + len(df_users[df_users['status'] == 'Bloqueado'])})**")
            render_glass_table(df_users[df_users["status"] != "Pendente"][["usuario_sigo", "nome_completo", "equipe", "role_interno", "status", "created_at"]])

            st.divider()
            st.markdown("**Excluir Usuário**")
            st.caption("Remove permanentemente o cadastro de um usuário.")
            df_del = df_users[df_users["status"] != "Pendente"].copy()
            if df_del.empty:
                st.info("Nenhum usuário ativo/bloqueado disponível para exclusão.")
            else:
                opcoes_del = {
                    f"{r['nome_completo']} ({r['usuario_sigo']})": r["id"]
                    for _, r in df_del.iterrows()
                }
                col_u_del, col_b_del = st.columns([3, 1])
                with col_u_del:
                    label_del = st.selectbox("Selecione o Usuário", list(opcoes_del.keys()), key="del_alvo_usuario")
                with col_b_del:
                    st.write("")
                    st.write("")
                    if st.button("Excluir Usuário", key="btn_del_usuario", type="primary", use_container_width=True):
                        alvo_id = opcoes_del[label_del]
                        if db.excluir_usuario(alvo_id, role):
                            st.success("Usuário excluído com sucesso.")
                            st.rerun()
                        else:
                            st.error("Não foi possível excluir o usuário. Verifique se você é Admin.")

            st.divider()
            st.markdown("**Redefinir senha de usuário**")
            st.caption("Define uma senha temporária. No próximo login, o usuário será obrigado a criar uma senha própria.")

            df_reset = df_users[df_users["status"] != "Pendente"].copy()
            if df_reset.empty:
                st.info("Nenhum usuário ativo disponível para reset.")
            else:
                opcoes_reset = {
                    f"{r['nome_completo']} ({r['usuario_sigo']})": r["id"]
                    for _, r in df_reset.iterrows()
                }
                col_u, col_s = st.columns([2, 2])
                with col_u:
                    label_alvo = st.selectbox("Usuário", list(opcoes_reset.keys()), key="reset_alvo")
                with col_s:
                    senha_temp = st.text_input(
                        "Senha temporária",
                        type="password",
                        key="reset_senha_temp",
                        help="Mínimo 6 chars, 1 Maiúscula, 1 Número, 1 Especial",
                    )

                if st.button("Redefinir senha", key="btn_reset_senha", type="primary"):
                    import re
                    if not senha_temp:
                        st.warning("Digite a senha temporária.")
                    elif len(senha_temp) < 6 or not re.search(r"[A-Z]", senha_temp) or not re.search(r"[0-9]", senha_temp) or not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", senha_temp):
                        st.error("A senha temporária não atende aos requisitos mínimos (6 chars, 1 Maiúscula, 1 Número, 1 Especial).")
                    else:
                        alvo_id = opcoes_reset[label_alvo]
                        if db.resetar_senha(alvo_id, senha_temp, atuante_role=role):
                            st.success(f"Senha redefinida. Passe a senha temporária para o usuário — ele será obrigado a trocá-la no próximo login.")
                        else:
                            st.error("Não foi possível redefinir a senha. Verifique se você é Admin e se a service_role está configurada.")

# ==========================================
# ABA: DEBUG/TESTES (ADMIN)
# ==========================================
if "Debug/Testes" in nomes_abas:
    aba_idx = nomes_abas.index("Debug/Testes")
    with abas[aba_idx]:
        st.subheader("Ferramentas de Teste")
        st.caption("Disponível apenas para Admin. Use para validar alinhamentos, popups de ciência e notificações ao vivo.")

        usuario_id_admin = st.session_state.get("usuario_id")

        # --- 1. Registrar alinhamento de teste ---
        st.markdown("### 1. Registrar Alinhamento de Teste")
        st.caption("Cria um alinhamento com prefixo [TESTE] — fácil de identificar e remover depois.")
        with st.form("form_alinhamento_teste", clear_on_submit=True):
            t_titulo = st.text_input("Título", value="Alinhamento de teste")
            t_conteudo = st.text_area("Conteúdo", value="Conteúdo de teste para validar o fluxo de notificação.", height=80)
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                t_categoria = st.selectbox("Categoria", ["Geral", "Técnico", "Administrativo", "CAP"], key="debug_categoria")
            with col_t2:
                t_nivel = st.selectbox("Nível mínimo", ["Contas", "Auditor", "CISO", "Gestor"], index=0, key="debug_nivel")

            if st.form_submit_button("Registrar Alinhamento de Teste", type="primary"):
                titulo_final = f"[TESTE] {t_titulo}" if not t_titulo.startswith("[TESTE]") else t_titulo
                if db.inserir_alinhamento(titulo_final, t_conteudo, t_categoria, t_nivel, usuario_id_admin):
                    st.success("Alinhamento de teste registrado!")
                    st.rerun()
                else:
                    st.error("Erro ao registrar alinhamento de teste.")

        st.divider()

        # --- 2. Testar notificação (popup "Estou Ciente") ---
        st.markdown("### 2. Testar Notificação ao Vivo")
        st.caption("Remove sua confirmação de ciência de um alinhamento, fazendo o popup \"Estou Ciente\" reaparecer em até 45s.")

        todos_alinhamentos = db.carregar_alinhamentos()
        if not todos_alinhamentos:
            st.info("Nenhum alinhamento cadastrado.")
        else:
            opcoes = {f"[{a.get('categoria', 'Geral')}] {a.get('titulo', '')}": a["id"] for a in todos_alinhamentos}
            escolha = st.selectbox("Alinhamento", list(opcoes.keys()), key="debug_notif_select")
            if st.button("Resetar minha ciência e forçar popup", type="primary"):
                aid_escolhido = opcoes[escolha]
                if db.remover_leitura_alinhamento(aid_escolhido, usuario_id_admin):
                    st.session_state.pop("_dialog_alinhamento_id", None)
                    st.session_state.pop("alinhamentos_pendentes", None)
                    st.success("Ciência removida! O popup deve aparecer na próxima checagem (até 45s).")
                else:
                    st.error("Erro ao remover a confirmação de ciência.")

        st.divider()

        # --- 3. Limpar alinhamentos de teste ---
        st.markdown("### 3. Limpar Alinhamentos de Teste")
        st.caption("Remove permanentemente os alinhamentos com prefixo [TESTE] (e suas confirmações de ciência associadas).")

        teste_alinhamentos = [a for a in todos_alinhamentos if a.get("titulo", "").startswith("[TESTE]")]
        if not teste_alinhamentos:
            st.info("Nenhum alinhamento de teste encontrado.")
        else:
            for a in teste_alinhamentos:
                with st.container(border=True):
                    col_info, col_del = st.columns([5, 1])
                    with col_info:
                        st.markdown(f"**{a.get('titulo')}** — {a.get('categoria', 'Geral')} — {a.get('nivel_minimo', 'Auditor')}")
                    with col_del:
                        if st.button("️ Excluir", key=f"del_teste_{a['id']}", use_container_width=True):
                            if db.excluir_alinhamento(a["id"]):
                                st.rerun()
                            else:
                                st.error("Erro ao excluir.")

# ==========================================
# ABA 3: TABELAS BASE E GLOSAS (ADMIN/GESTOR)
# ==========================================
if "Tabelas Base e Glosas" in nomes_abas:
    aba_idx = nomes_abas.index("Tabelas Base e Glosas")
    with abas[aba_idx]:
        st.subheader("Base de Conhecimento do Sistema")
        
        tab_interna1, tab_interna2, tab_interna3 = st.tabs(["Procedimentos (Supabase)", "Classificação de Glosas (Memória)", "Glosas Customizadas (Nuvem)"])
        
        with tab_interna1:
            st.markdown("Suba o arquivo TUSS para alimentar a tabela de procedimentos e valores.")
            arquivo_procedimentos = st.file_uploader("Arraste o CSV de Procedimentos (TUSS)", type=["csv"], key="csv_procs")
            if arquivo_procedimentos is not None:
                try:
                    df_proc = pd.read_csv(arquivo_procedimentos, sep=';', encoding='utf-8')
                    render_glass_table(df_proc.head())
                    if role == "Admin":
                        if st.button(" Subir TUSS para o Supabase", type="primary"):
                            with st.spinner("Enviando para o banco..."):
                                sucesso, erros = 0, 0
                                for _, row in df_proc.iterrows():
                                    cod = str(row.get('codigo_tuss', row.iloc[0]))
                                    desc = str(row.get('descricao', row.iloc[1]))
                                    val = float(row.get('valor_unitario', row.iloc[2] if len(row.columns)>2 else 0.0))
                                    if db.inserir_procedimento(cod, desc, val): sucesso += 1
                                    else: erros += 1
                                if erros == 0: st.success(f" {sucesso} procedimentos salvos!")
                                else: st.warning(f"{sucesso} salvos, {erros} falharam (duplicados?).")
                    else:
                        st.info("Apenas Administradores podem substituir a base inteira no banco de dados.")
                except Exception as e:
                    st.error(f"Erro ao ler CSV: {e}")
                    
        with tab_interna2:
            st.markdown("Navegue pelas glosas cadastradas no banco de dados.")
            rows = db._get("glosas_padrao?select=codigo,descricao,tipo_glosa,nivel,sub_glosa,descricao_sub_glosa&order=codigo")
            df_glosas = pd.DataFrame(rows)

            if not df_glosas.empty:
                filtro_tipo = st.selectbox("Filtrar por Tipo:", ["Todos"] + list(df_glosas["tipo_glosa"].dropna().unique()))
                if filtro_tipo != "Todos":
                    df_glosas = df_glosas[df_glosas["tipo_glosa"] == filtro_tipo]

            if not df_glosas.empty:
                render_glass_table(df_glosas)
            else:
                st.info("Nenhuma glosa cadastrada.")
                
        with tab_interna3:
            st.markdown("Pesquise glosas existentes para editar sua classificação, ou adicione novas.")
            
            # 1. Carrega todas as glosas (Base + Customizadas)
            rows = db._get("glosas_padrao?select=codigo,descricao,tipo_glosa,nivel,sub_glosa,descricao_sub_glosa")
            df_base = pd.DataFrame(rows).fillna("")
            
            criticas_base = {'438', '450', '463', '480'} # Fallback mínimo
            
            # Monta dicionário master
            dict_glosas = {}
            for _, row in df_base.iterrows():
                cod = str(row.get('codigo', "")).strip()
                desc = str(row.get('descricao', "")).strip()
                tipo = str(row.get('tipo_glosa', "Técnica")).strip()
                dict_glosas[cod] = {"codigo": cod, "descricao": desc, "tipo": tipo, "is_critica": (cod in criticas_base), "origem": "Base"}
                
            # Sobrepõe customizadas
            customizadas = db.carregar_glosas_customizadas()
            for cust in customizadas:
                cod = str(cust['codigo_glosa']).strip()
                dict_glosas[cod] = {
                    "codigo": cod,
                    "descricao": cust['descricao'],
                    "tipo": cust['tipo'],
                    "is_critica": bool(cust['is_critica']),
                    "origem": "Customizada"
                }
                
            # Controles Superiores
            col_head_1, col_head_2 = st.columns([1, 2])
            with col_head_1:
                st.write("")
                if st.button("➕ Adicionar Nova Glosa", type="primary", use_container_width=True):
                    st.session_state["glosa_em_edicao"] = "NOVA"
                    st.rerun()
            with col_head_2:
                busca = st.text_input("🔍 Pesquisar (Código ou Descrição):", placeholder="Ex: 438 ou 'procedimento não corresponde'")
                    
            # Filtro
            resultados = list(dict_glosas.values())
            if busca:
                b_low = busca.lower()
                resultados = [g for g in resultados if b_low in g['codigo'].lower() or b_low in g['descricao'].lower()]
                
            # Formulário de Edição/Adição (Modo Expander Flutuante)
            em_edicao = st.session_state.get("glosa_em_edicao", None)
            if em_edicao:
                st.divider()
                st.subheader("️ Editor de Glosa" if em_edicao != "NOVA" else " Nova Glosa")
                
                with st.container(border=True):
                    g_alvo = dict_glosas.get(em_edicao, {"codigo": "", "descricao": "", "tipo": "Técnica", "is_critica": False}) if em_edicao != "NOVA" else {"codigo": "", "descricao": "", "tipo": "Técnica", "is_critica": False}
                    
                    form_c1, form_c2 = st.columns([1, 4])
                    with form_c1:
                        f_cod = st.text_input("Código (Ex: 1001.1)", value=g_alvo["codigo"], disabled=(em_edicao != "NOVA"))
                    with form_c2:
                        f_desc = st.text_input("Descrição Oficial", value=g_alvo["descricao"])
                        
                    form_c3, form_c4 = st.columns([1, 1])
                    with form_c3:
                        f_tipo = st.selectbox("Tipo", ["Técnica", "Administrativa"], index=0 if g_alvo["tipo"]=="Técnica" else 1)
                    with form_c4:
                        st.write("")
                        st.write("")
                        f_crit = st.checkbox(" Glosa de Risco (Crítica)", value=g_alvo["is_critica"])
                        
                    b1, b2, b3 = st.columns([2, 2, 8])
                    if b1.button(" Salvar", type="primary", use_container_width=True):
                        if f_cod and f_desc:
                            db.upsert_glosa_customizada(f_cod, f_desc, f_crit, f_tipo, nome)
                            st.success("Glosa salva com sucesso na nuvem!")
                            st.session_state["glosa_em_edicao"] = None
                            st.rerun()
                        else:
                            st.error("Preencha o código e a descrição.")
                    if b2.button("Cancelar", use_container_width=True):
                        st.session_state["glosa_em_edicao"] = None
                        st.rerun()

            # Sub-glosas (somente ao editar uma glosa existente)
            if em_edicao != "NOVA":
                codigo_pai = em_edicao

                # Sub-glosas do banco (linhas com sub_glosa preenchido)
                rows = db._get("glosas_padrao?select=codigo,sub_glosa,descricao_sub_glosa")
                df_todas = pd.DataFrame(rows).fillna("")

                subs_csv = df_todas[
                    (df_todas["codigo"].astype(str).str.strip() == str(codigo_pai)) &
                    (df_todas["sub_glosa"].astype(str).str.strip() != "")
                ][["sub_glosa", "descricao_sub_glosa"]].copy()

                # Sub-glosas customizadas do Supabase (código "438.X")
                subs_custom = sorted(
                    [g for g in dict_glosas.values()
                     if g['codigo'].startswith(f"{codigo_pai}.") and g['origem'] == "Customizada"],
                    key=lambda x: x['codigo']
                )

                st.markdown("**Sub-Glosas**")

                if not subs_csv.empty:
                    st.caption(" Da base (CSV)")
                    for _, sg_row in subs_csv.iterrows():
                        num  = str(sg_row["sub_glosa"]).strip()
                        desc = str(sg_row["descricao_sub_glosa"]).strip()
                        sg_c1, sg_c2 = st.columns([1, 6])
                        sg_c1.markdown(f"Sub **{num}**")
                        sg_c2.markdown(desc if desc else "*sem descrição*")

                if subs_custom:
                    st.caption("️ Customizadas (Supabase)")
                    for sg in subs_custom:
                        sub_num = sg['codigo'].split('.')[-1]
                        sg_c1, sg_c2, sg_c3, sg_c4 = st.columns([1, 4, 2, 1])
                        sg_c1.markdown(f"Sub **{sub_num}**")
                        sg_c2.markdown(sg['descricao'])
                        badge = " Risco" if sg['is_critica'] else " Padrão"
                        sg_c3.markdown(f"{sg['tipo']} | {badge}")
                        if sg_c4.button("Editar", key=f"btn_edit_sub_{sg['codigo']}"):
                            st.session_state["glosa_em_edicao"] = sg['codigo']
                            st.rerun()

                if subs_csv.empty and not subs_custom:
                    st.caption("Nenhuma sub-glosa cadastrada.")

                with st.expander(" Adicionar Sub-Glosa Customizada"):
                    sg_c1, sg_c2, sg_c3 = st.columns([1, 1, 4])
                    with sg_c1:
                        st.text_input("Glosa", value=codigo_pai, disabled=True, key="nova_sg_pai")
                    with sg_c2:
                        sg_sub_num = st.text_input("Nº Sub Glosa", placeholder="Ex: 33", key="nova_sg_num")
                    with sg_c3:
                        sg_desc = st.text_input("Descrição", key="nova_sg_desc")
                    sg_cod = f"{codigo_pai}.{sg_sub_num.strip()}" if sg_sub_num.strip() else ""
                    sg_c4, sg_c5 = st.columns([2, 1])
                    with sg_c4:
                        sg_tipo = st.selectbox("Tipo", ["Técnica", "Administrativa"], key="nova_sg_tipo")
                    with sg_c5:
                        st.write("")
                        sg_crit = st.checkbox(" Crítica", key="nova_sg_crit")
                    if st.button(" Salvar Sub-Glosa", key="btn_salvar_nova_sg", type="primary"):
                        if sg_cod and sg_desc:
                            db.upsert_glosa_customizada(sg_cod, sg_desc, sg_crit, sg_tipo, nome)
                            st.success(f"Glosa {codigo_pai} | Sub {sg_sub_num.strip()} salva!")
                            st.rerun()
                        else:
                            st.error("Preencha o Nº da sub-glosa e a descrição.")

            st.divider()

            # Lista de Resultados
            st.markdown(f"**Resultados ({len(resultados)}):**")
            
            # Paginação simples para não travar a UI (mostra max 50)
            max_mostrar = 50
            for g in resultados[:max_mostrar]:
                with st.container(border=True):
                    rc1, rc2, rc3, rc4 = st.columns([1, 4, 2, 1])
                    rc1.markdown(f"**{g['codigo']}**")
                    rc2.markdown(g['descricao'])
                    badge_risco = " Risco" if g['is_critica'] else " Padrão"
                    rc3.markdown(f"{g['tipo']} | {badge_risco} | *{g['origem']}*")
                    if rc4.button("Editar", key=f"btn_edit_{g['codigo']}", use_container_width=True):
                        st.session_state["glosa_em_edicao"] = g['codigo']
                        st.rerun()
            
            if len(resultados) > max_mostrar:
                st.info(f"Mostrando 50 de {len(resultados)} resultados. Use a barra de pesquisa para refinar.")
            st.divider()
            st.markdown("#### ️ Manutenção do Banco de Dados (Supabase)")
            st.markdown("Para não lotar seu banco de dados, apague históricos antigos de auditoria.")
            col_meses, col_btn = st.columns([2, 1])
            with col_meses:
                meses_retencao = st.number_input("Tempo de retenção (meses):", min_value=1, max_value=60, value=6, step=1)
            with col_btn:
                st.write("")
                st.write("")
                if st.button(" Limpar Histórico Antigo", type="secondary", use_container_width=True):
                    with st.spinner(f"Limpando registros mais antigos que {meses_retencao} meses..."):
                        import requests
                        from datetime import datetime, timedelta
                        
                        url = st.secrets["supabase"]["url"].rstrip("/")
                        key = st.secrets["supabase"]["key"]
                        headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                        data_limite = (datetime.now() - timedelta(days=meses_retencao*30)).isoformat()
                        
                        try:
                            response = requests.delete(f"{url}/rest/v1/analises_auditoria?criado_em=lt.{data_limite}", headers=headers)
                            if response.status_code == 403:
                                st.error("Sem permissão de exclusão. Adicione uma política de DELETE para a role anon.")
                            else:
                                response.raise_for_status()
                                st.success(f"Limpeza concluída! Registros anteriores a {meses_retencao} meses foram apagados.")
                        except Exception as e:
                            st.error(f"Erro ao realizar a limpeza: {e}")

# ==========================================
# ABA 4: TEXTOS DOS PRESTADORES (GESTOR/ADMIN)
# ==========================================
if "Textos para Prestadores" in nomes_abas:
    aba_idx = nomes_abas.index("Textos para Prestadores")
    with abas[aba_idx]:
        st.subheader("Textos para os Prestadores")
        st.markdown("Cadastre os textos descritivos que aparecerão para as glosas no final do relatório.")
        
        # Carrega textos da base (não tem mais a gambiarra do link, mas por segurança filtramos)
        textos_brutos = db.carregar_textos_prestador()
        textos = [t for t in textos_brutos if t.get("glosas_relacionadas") != "__LINK__"]
        
        # Controles Superiores
        col_head_1, col_head_2 = st.columns([1, 2])
        with col_head_1:
            st.write("")
            if st.button("➕ Adicionar Novo Texto", type="primary", use_container_width=True, key="btn_add_txt"):
                st.session_state["texto_em_edicao"] = "NOVO"
        with col_head_2:
            busca_txt = st.text_input("🔍 Pesquisar (Título ou Glosa):", placeholder="Ex: 480 ou Falta Imagem...")
                
        # Filtro
        resultados_txt = textos
        if busca_txt:
            b_low = busca_txt.lower()
            resultados_txt = [t for t in textos if b_low in str(t.get('titulo', '')).lower() or b_low in str(t.get('glosas_relacionadas', '')).lower()]
            
        # Formulário de Edição/Adição
        em_edicao = st.session_state.get("texto_em_edicao", None)
        if em_edicao:
            st.divider()
            st.subheader("✏️ Editor de Texto" if em_edicao != "NOVO" else "✨ Novo Texto")
            
            with st.container(border=True):
                # Encontra o texto se estiver editando
                t_alvo = {"id": None, "titulo": "", "glosas_relacionadas": "", "texto": "", "sub_glosas_relacionadas": "", "procedimentos_relacionados": ""}
                if em_edicao != "NOVO":
                    for t in textos:
                        if t['id'] == em_edicao:
                            t_alvo = t
                            break
                            
                f_tit = st.text_input("Título (Identificador Interno)", value=t_alvo["titulo"])
                f_glo = st.text_input("Glosas Relacionadas (ex: 438, 450)", value=t_alvo["glosas_relacionadas"])

                # Filtros avançados: só carregam (3 chamadas REST) quando solicitado
                tem_filtros_salvos = bool(
                    str(t_alvo.get("sub_glosas_relacionadas") or "").strip() or
                    str(t_alvo.get("procedimentos_relacionados") or "").strip()
                )
                usar_filtros = st.checkbox(
                    "Restringir por sub-glosa ou procedimento específico",
                    value=tem_filtros_salvos,
                    help="Ative para que este texto só apareça em casos com a sub-glosa/procedimento escolhido. Deixe desmarcado para um texto geral."
                )

                label_to_valor_sub = {}
                f_sub_labels = []
                label_to_valor_proc = {}
                f_proc_labels = []

                if usar_filtros:
                    glosa_codes = [g.strip() for g in f_glo.split(',') if g.strip()]

                    mapa_subglosas = carregar_mapa_subglosas()
                    opcoes_sub = sorted(
                        [(f"{cod}.{sub}", f"{cod}.{sub} - {desc}") for (cod, sub), desc in mapa_subglosas.items() if cod in glosa_codes],
                        key=lambda x: x[0]
                    )
                    label_to_valor_sub = {lbl: val for val, lbl in opcoes_sub}
                    valor_to_label_sub = {val: lbl for val, lbl in opcoes_sub}
                    default_sub_vals = [v.strip() for v in str(t_alvo.get("sub_glosas_relacionadas", "")).split(',') if v.strip()]
                    default_sub_labels = [valor_to_label_sub[v] for v in default_sub_vals if v in valor_to_label_sub]

                    f_sub_labels = st.multiselect(
                        "Sub-Glosas Relacionadas",
                        options=list(label_to_valor_sub.keys()),
                        default=default_sub_labels,
                        help="Cascateia a partir das Glosas Relacionadas digitadas acima."
                    )

                    mapa_procedimentos = carregar_mapa_procedimentos()
                    opcoes_proc = sorted(
                        [(cod, f"{cod} - {desc}") for cod, desc in mapa_procedimentos.items()],
                        key=lambda x: x[1]
                    )
                    label_to_valor_proc = {lbl: val for val, lbl in opcoes_proc}
                    default_proc_vals = [v.strip() for v in str(t_alvo.get("procedimentos_relacionados", "")).split(',') if v.strip()]
                    default_proc_labels = [lbl for val, lbl in opcoes_proc if val in default_proc_vals]

                    f_proc_labels = st.multiselect(
                        "Procedimentos Relacionados",
                        options=[lbl for _, lbl in opcoes_proc],
                        default=default_proc_labels,
                        help="Digite parte do código ou nome para pesquisar nos 448 procedimentos."
                    )

                st.markdown("Use `{guia}` para a frase que exibe as guias, `{glosas}` para as descrições e `{procedimentos}` para os códigos.")
                f_txt = st.text_area("Texto Padrão ao Prestador", value=t_alvo["texto"], height=100)
                    
                b1, b2, b3 = st.columns([2, 2, 8])
                if b1.button(" Salvar", type="primary", use_container_width=True, key="btn_salvar_txt"):
                    if f_tit and f_glo and f_txt:
                        f_sub = ",".join(label_to_valor_sub[lbl] for lbl in f_sub_labels)
                        f_proc = ",".join(label_to_valor_proc[lbl] for lbl in f_proc_labels)
                        if em_edicao == "NOVO":
                            if db.inserir_texto_prestador(f_tit, f_glo, f_txt, nome, f_sub, f_proc):
                                st.success("Texto cadastrado com sucesso!")
                                st.session_state["texto_em_edicao"] = None
                                st.rerun()
                            else:
                                st.error("Erro ao salvar no banco.")
                        else:
                            if db.atualizar_texto_prestador(t_alvo['id'], f_tit, f_glo, f_txt, nome, f_sub, f_proc):
                                st.success("Texto atualizado com sucesso!")
                                st.session_state["texto_em_edicao"] = None
                                st.rerun()
                            else:
                                st.error("Erro ao atualizar no banco.")
                    else:
                        st.error("Preencha todos os campos obrigatórios.")
                        
                if b2.button("Cancelar", use_container_width=True, key="btn_canc_txt"):
                    st.session_state["texto_em_edicao"] = None
                    st.rerun()
            st.divider()

        # Lista de Resultados
        st.markdown(f"**Cadastrados ({len(resultados_txt)}):**")
        if not resultados_txt:
            st.info("Nenhum texto cadastrado ainda.")
        else:
            for t in resultados_txt:
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2, 2, 4, 3])
                    c1.markdown(f"**{t.get('titulo', 'Sem Título')}**")
                    c2.markdown(f" Glosas: `{t.get('glosas_relacionadas', '')}`")
                    with c3:
                        texto_curto = t.get('texto', '')[:40] + "..." if len(t.get('texto', '')) > 40 else t.get('texto', '')
                        st.markdown(f" *{texto_curto}*")
                        with st.expander("Ver Texto Completo"):
                            st.markdown(t.get('texto', ''))

                    sub_rel = str(t.get('sub_glosas_relacionadas') or '').strip()
                    proc_rel = str(t.get('procedimentos_relacionados') or '').strip()
                    if sub_rel or proc_rel:
                        detalhes = []
                        if sub_rel:
                            detalhes.append(f"Sub-glosas: `{sub_rel}`")
                        if proc_rel:
                            detalhes.append(f"Procedimentos: `{proc_rel}`")
                        st.caption(" | ".join(detalhes))

                    # Coluna de botões (Editar e Excluir)
                    b_edit, b_del = c4.columns([1, 1])
                    if b_edit.button("Editar", key=f"edit_txt_{t['id']}", use_container_width=True):
                        st.session_state["texto_em_edicao"] = t['id']
                        st.rerun()
                    if b_del.button("Excluir", key=f"del_txt_{t['id']}", use_container_width=True):
                        if db.deletar_texto_prestador(t['id']):
                            st.rerun()

# ==========================================
# ABA 5: PERMISSÕES DE ACESSO (ADMIN/GESTOR)
# ==========================================
if "Permissões de Acesso" in nomes_abas:
    aba_idx = nomes_abas.index("Permissões de Acesso")
    with abas[aba_idx]:
        from core.settings import MODULOS_CONTROLADOS, ROLES_PERMISSAO

        st.subheader("Acesso aos Módulos por Função")
        st.markdown("Marque quais funções podem acessar cada módulo. **Admin** sempre tem acesso a tudo, independente da configuração abaixo.")

        permissoes_atuais = db.carregar_permissoes_modulos()
        mapa_permissoes = {(p["modulo"], p["role"]): bool(p["habilitado"]) for p in permissoes_atuais}

        with st.form("form_permissoes"):
            header_cols = st.columns([3] + [1] * len(ROLES_PERMISSAO))
            header_cols[0].markdown("**Módulo**")
            for i, r in enumerate(ROLES_PERMISSAO):
                header_cols[i + 1].markdown(f"**{r}**")

            valores = {}
            for modulo, label in MODULOS_CONTROLADOS.items():
                cols = st.columns([3] + [1] * len(ROLES_PERMISSAO))
                cols[0].markdown(label)
                for i, r in enumerate(ROLES_PERMISSAO):
                    valores[(modulo, r)] = cols[i + 1].checkbox(
                        label=f"{label} - {r}",
                        value=mapa_permissoes.get((modulo, r), False),
                        key=f"perm_{modulo}_{r}",
                        label_visibility="collapsed",
                    )

            if st.form_submit_button("Salvar Permissões", type="primary"):
                erros = 0
                for (modulo, r), habilitado in valores.items():
                    if mapa_permissoes.get((modulo, r), False) != habilitado:
                        if not db.atualizar_permissao_modulo(modulo, r, habilitado):
                            erros += 1
                if erros == 0:
                    st.success("Permissões atualizadas!")
                    st.rerun()
                else:
                    st.error(f"{erros} permissões falharam ao salvar.")

# ==========================================
# ABA: LINKS PADRÃO (ADMIN/GESTOR)
# ==========================================
if "Links Home" in nomes_abas:
    aba_idx = nomes_abas.index("Links Home")
    with abas[aba_idx]:
        st.subheader("Links institucionais exibidos na Home")
        st.caption("Todos os usuários logados enxergam esses links no Painel Principal, agrupados por categoria.")

        col_head_1, col_head_2 = st.columns([1, 3])
        with col_head_1:
            st.write("")
            if st.button("➕ Adicionar Novo Link", type="primary", use_container_width=True, key="btn_add_link_padrao"):
                st.session_state["link_padrao_em_edicao"] = "NOVO"
                
        todos_links = db.listar_links_padrao(incluir_inativos=True)

        em_edicao = st.session_state.get("link_padrao_em_edicao", None)
        if em_edicao:
            st.divider()
            st.subheader("Editor de Link" if em_edicao != "NOVO" else "Novo Link")
            with st.container(border=True):
                l_alvo = {"id": None, "titulo": "", "url": "", "categoria": "Geral", "ordem": 100, "ativo": True}
                if em_edicao != "NOVO":
                    for l in todos_links:
                        if l['id'] == em_edicao:
                            l_alvo = l
                            break
                            
                fc1, fc2, fc3, fc4 = st.columns([3, 4, 2, 1])
                with fc1:
                    lp_titulo = st.text_input("Título", value=l_alvo.get("titulo", ""), placeholder="Ex: SharePoint Auditoria")
                with fc2:
                    lp_url = st.text_input("URL", value=l_alvo.get("url", ""), placeholder="https://...")
                with fc3:
                    lp_categoria = st.text_input("Categoria", value=l_alvo.get("categoria", "Geral"))
                with fc4:
                    lp_ordem = st.number_input("Ordem", min_value=1, value=int(l_alvo.get("ordem", 100)), step=10)
                lp_ativo = st.checkbox("Ativo", value=bool(l_alvo.get("ativo", True)))
                
                b1, b2, b3 = st.columns([2, 2, 8])
                if b1.button(" Salvar", type="primary", use_container_width=True, key="btn_salvar_lp"):
                    if not lp_titulo or not lp_url:
                        st.warning("Título e URL são obrigatórios.")
                    elif not lp_url.startswith(("http://", "https://")):
                        st.error("URL deve começar com http:// ou https://.")
                    else:
                        if em_edicao == "NOVO":
                            if db.inserir_link_padrao(lp_titulo, lp_url, lp_categoria, lp_ordem, atuante_role=role):
                                st.success("Link adicionado!")
                                st.session_state["link_padrao_em_edicao"] = None
                                st.rerun()
                            else:
                                st.error("Erro ao salvar.")
                        else:
                            if db.atualizar_link_padrao(l_alvo["id"], lp_titulo, lp_url, lp_categoria, lp_ordem, lp_ativo, atuante_role=role):
                                st.success("Link atualizado!")
                                st.session_state["link_padrao_em_edicao"] = None
                                st.rerun()
                            else:
                                st.error("Erro ao atualizar.")
                if b2.button("Cancelar", use_container_width=True, key="btn_canc_lp"):
                    st.session_state["link_padrao_em_edicao"] = None
                    st.rerun()

        st.divider()
        st.markdown("**Links cadastrados**")
        if not todos_links:
            st.info("Nenhum link cadastrado ainda.")
        else:
            for l in todos_links:
                with st.container(border=True):
                    lc1, lc2, lc3, lc4 = st.columns([4, 3, 2, 3])
                    status = "🟢 Ativo" if l.get('ativo', True) else "🔴 Inativo"
                    lc1.markdown(f"**{l.get('titulo', 'Sem Título')}**")
                    lc2.markdown(f"[🔗 Acessar Link]({l.get('url', '')})")
                    lc3.markdown(f"{l.get('categoria', 'Geral')} ({l.get('ordem', 100)}) | {status}")
                    
                    b_edit, b_del = lc4.columns([1, 1])
                    if b_edit.button("Editar", key=f"lp_edit_{l['id']}", use_container_width=True):
                        st.session_state["link_padrao_em_edicao"] = l['id']
                        st.rerun()
                    if b_del.button("Excluir", key=f"lp_del_{l['id']}", use_container_width=True):
                        if db.deletar_link_padrao(l["id"], atuante_role=role):
                            st.rerun()
                        else:
                            st.error("Erro ao excluir.")
