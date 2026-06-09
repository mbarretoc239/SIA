import streamlit as st
import pandas as pd
import io
from shared.database import DatabaseManager

st.set_page_config(page_title="Configurações", page_icon="⚙️", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar as configurações.")
    st.stop()

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()
db = st.session_state.db

role = st.session_state.get("role_interno", "Contas")
nome = st.session_state.get("auditor_nome", "Usuário")

st.title("⚙️ Painel de Controle e Configurações")
st.markdown("Gerencie seu perfil, aprove cadastros da equipe e configure as regras do motor inteligente.")

# Define quais abas o usuário tem acesso
nomes_abas = ["👤 Meu Perfil", "🔗 Meus Links Úteis"]

if role == "Admin":
    nomes_abas.append("🛡️ Aprovação de Equipe")
    
if role in ["Admin", "Gestor"]:
    nomes_abas.append("📚 Tabelas Base e Glosas")
    nomes_abas.append("🤖 Textos Padrões (Motor)")

abas = st.tabs(nomes_abas)

# ==========================================
# ABA 1: MEU PERFIL (TODOS)
# ==========================================
with abas[0]:
    st.subheader("Informações da Conta")
    st.info(f"**Nome:** {nome}\n\n**Equipe original:** {st.session_state.get('equipe', 'N/A')}\n\n**Nível de Acesso (Role):** {role}")
    st.markdown("*(A alteração de senha individual estará disponível em breve).*")

# ==========================================
# ABA 2: LINKS ÚTEIS (TODOS)
# ==========================================
if "🔗 Meus Links Úteis" in nomes_abas:
    aba_idx = nomes_abas.index("🔗 Meus Links Úteis")
    with abas[aba_idx]:
        st.subheader("Meus Links e Atalhos Rápidos")
        st.markdown("Cadastre aqui os links que você mais usa. Eles aparecerão na barra lateral para acesso rápido!")
        
        with st.form("form_novo_link", clear_on_submit=True):
            c1, c2, c3 = st.columns([2, 3, 1])
            with c1:
                link_titulo = st.text_input("Título do Link", placeholder="Ex: Portal TUSS")
            with c2:
                link_url = st.text_input("URL (Endereço)", placeholder="Ex: https://...")
            with c3:
                st.write("")
                st.write("")
                submeteu = st.form_submit_button("Salvar Link", type="primary", use_container_width=True)
            
            if submeteu:
                if link_titulo and link_url:
                    # Usamos a tabela de textos_prestadores para salvar os links (gambiarra oficial)
                    if db.inserir_texto_prestador(link_titulo, "__LINK__", link_url, st.session_state.get("usuario_id", "")):
                        st.success("Link salvo com sucesso!")
                        st.rerun()
                    else:
                        st.error("Erro ao salvar link.")
                else:
                    st.warning("Preencha o título e a URL.")
                    
        st.divider()
        st.markdown("### Links Cadastrados")
        
        textos_db = db.carregar_textos_prestador()
        meus_links = [t for t in textos_db if t.get("glosas_relacionadas") == "__LINK__" and t.get("updated_by") == st.session_state.get("usuario_id", "")]
        
        if not meus_links:
            st.info("Você ainda não possui links cadastrados.")
        else:
            for link in meus_links:
                with st.container(border=True):
                    col_btn, col_del = st.columns([6, 1])
                    with col_btn:
                        st.markdown(f"**{link.get('titulo')}** — [{link.get('texto')}]({link.get('texto')})")
                    with col_del:
                        if st.button("🗑️ Excluir", key=f"del_link_{link.get('id')}", use_container_width=True):
                            if db.deletar_texto_prestador(link.get('id')):
                                st.rerun()

# ==========================================
# ABA 3: APROVAÇÃO DE EQUIPE (ADMIN)
# ==========================================
if "🛡️ Aprovação de Equipe" in nomes_abas:
    aba_idx = nomes_abas.index("🛡️ Aprovação de Equipe")
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
                        
                        if st.button("Salvar Alteração", key=f"btn_{row['id']}", type="primary"):
                            if db.atualizar_usuario_admin(row['id'], novo_status, novo_role, nova_equipe):
                                st.success("Usuário atualizado com sucesso!")
                                st.rerun()
                            else:
                                st.error("Erro ao atualizar usuário no Supabase.")
                                
            st.divider()
            st.markdown(f"**Usuários Ativos e Bloqueados ({len(ativos) + len(df_users[df_users['status'] == 'Bloqueado'])})**")
            st.dataframe(df_users[df_users["status"] != "Pendente"][["usuario_sigo", "nome_completo", "equipe", "role_interno", "status", "created_at"]], use_container_width=True)

# ==========================================
# ABA 3: TABELAS BASE E GLOSAS (ADMIN/GESTOR)
# ==========================================
if "📚 Tabelas Base e Glosas" in nomes_abas:
    aba_idx = nomes_abas.index("📚 Tabelas Base e Glosas")
    with abas[aba_idx]:
        st.subheader("Base de Conhecimento do Sistema")
        
        tab_interna1, tab_interna2, tab_interna3 = st.tabs(["Procedimentos (Supabase)", "Classificação de Glosas (Memória)", "Glosas Customizadas (Nuvem)"])
        
        with tab_interna1:
            st.markdown("Suba o arquivo TUSS para alimentar a tabela de procedimentos e valores.")
            arquivo_procedimentos = st.file_uploader("Arraste o CSV de Procedimentos (TUSS)", type=["csv"], key="csv_procs")
            if arquivo_procedimentos is not None:
                try:
                    df_proc = pd.read_csv(arquivo_procedimentos, sep=';', encoding='utf-8')
                    st.dataframe(df_proc.head())
                    if role == "Admin":
                        if st.button("📤 Subir TUSS para o Supabase", type="primary"):
                            with st.spinner("Enviando para o banco..."):
                                sucesso, erros = 0, 0
                                for _, row in df_proc.iterrows():
                                    cod = str(row.get('codigo_tuss', row.iloc[0]))
                                    desc = str(row.get('descricao', row.iloc[1]))
                                    val = float(row.get('valor_unitario', row.iloc[2] if len(row.columns)>2 else 0.0))
                                    if db.inserir_procedimento(cod, desc, val): sucesso += 1
                                    else: erros += 1
                                if erros == 0: st.success(f"✅ {sucesso} procedimentos salvos!")
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

            st.dataframe(df_glosas, use_container_width=True)
                
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
                
            # Barra de pesquisa
            with st.form("busca_glosa_form", border=False):
                col_inp, col_btn = st.columns([6, 1])
                with col_inp:
                    busca_val = st.text_input(
                        "🔍 Pesquisar Glosa (Código ou Descrição):",
                        value=st.session_state.get("busca_glosa", ""),
                        placeholder="Ex: 438 ou 'procedimento não corresponde'"
                    )
                with col_btn:
                    st.write(""); st.write("")
                    submitted = st.form_submit_button("🔍 Buscar", use_container_width=True, type="primary")
                if submitted:
                    st.session_state["busca_glosa"] = busca_val

            busca = st.session_state.get("busca_glosa", "")

            if st.button("➕ Adicionar Nova Glosa", type="secondary"):
                st.session_state["glosa_em_edicao"] = "NOVA"
                st.rerun()
                    
            # Filtro
            resultados = list(dict_glosas.values())
            if busca:
                b_low = busca.lower()
                resultados = [g for g in resultados if b_low in g['codigo'].lower() or b_low in g['descricao'].lower()]
                
            # Formulário de Edição/Adição (Modo Expander Flutuante)
            em_edicao = st.session_state.get("glosa_em_edicao", None)
            if em_edicao:
                st.divider()
                st.subheader("✏️ Editor de Glosa" if em_edicao != "NOVA" else "✨ Nova Glosa")
                
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
                        f_crit = st.checkbox("🔥 Glosa de Risco (Crítica)", value=g_alvo["is_critica"])
                        
                    b1, b2, b3 = st.columns([2, 2, 8])
                    if b1.button("💾 Salvar", type="primary", use_container_width=True):
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
                    st.caption("📋 Da base (CSV)")
                    for _, sg_row in subs_csv.iterrows():
                        num  = str(sg_row["sub_glosa"]).strip()
                        desc = str(sg_row["descricao_sub_glosa"]).strip()
                        sg_c1, sg_c2 = st.columns([1, 6])
                        sg_c1.markdown(f"Sub **{num}**")
                        sg_c2.markdown(desc if desc else "*sem descrição*")

                if subs_custom:
                    st.caption("☁️ Customizadas (Supabase)")
                    for sg in subs_custom:
                        sub_num = sg['codigo'].split('.')[-1]
                        sg_c1, sg_c2, sg_c3, sg_c4 = st.columns([1, 4, 2, 1])
                        sg_c1.markdown(f"Sub **{sub_num}**")
                        sg_c2.markdown(sg['descricao'])
                        badge = "🔥 Risco" if sg['is_critica'] else "✅ Padrão"
                        sg_c3.markdown(f"{sg['tipo']} | {badge}")
                        if sg_c4.button("Editar", key=f"btn_edit_sub_{sg['codigo']}"):
                            st.session_state["glosa_em_edicao"] = sg['codigo']
                            st.rerun()

                if subs_csv.empty and not subs_custom:
                    st.caption("Nenhuma sub-glosa cadastrada.")

                with st.expander("➕ Adicionar Sub-Glosa Customizada"):
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
                        sg_crit = st.checkbox("🔥 Crítica", key="nova_sg_crit")
                    if st.button("💾 Salvar Sub-Glosa", key="btn_salvar_nova_sg", type="primary"):
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
                    badge_risco = "🔥 Risco" if g['is_critica'] else "✅ Padrão"
                    rc3.markdown(f"{g['tipo']} | {badge_risco} | *{g['origem']}*")
                    if rc4.button("Editar", key=f"btn_edit_{g['codigo']}", use_container_width=True):
                        st.session_state["glosa_em_edicao"] = g['codigo']
                        st.rerun()
            
            if len(resultados) > max_mostrar:
                st.info(f"Mostrando 50 de {len(resultados)} resultados. Use a barra de pesquisa para refinar.")
            st.divider()
            st.markdown("#### 🗄️ Manutenção do Banco de Dados (Supabase)")
            st.markdown("Para não lotar seu banco de dados, apague históricos antigos de auditoria.")
            col_meses, col_btn = st.columns([2, 1])
            with col_meses:
                meses_retencao = st.number_input("Tempo de retenção (meses):", min_value=1, max_value=60, value=6, step=1)
            with col_btn:
                st.write("")
                st.write("")
                if st.button("🧹 Limpar Histórico Antigo", type="secondary", use_container_width=True):
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
if "🤖 Textos Padrões (Motor)" in nomes_abas:
    aba_idx = nomes_abas.index("🤖 Textos Padrões (Motor)")
    with abas[aba_idx]:
        st.subheader("Textos para os Prestadores")
        st.markdown("Cadastre os textos descritivos que aparecerão para as glosas no final do relatório.")
        
        # Carrega textos da base (ignorando os links)
        textos_brutos = db.carregar_textos_prestador()
        textos = [t for t in textos_brutos if t.get("glosas_relacionadas") != "__LINK__"]
        
        # Controles Superiores
        c_busca, c_add = st.columns([4, 1])
        with c_busca:
            busca_txt = st.text_input("🔍 Pesquisar Texto (Título ou Glosa):")
        with c_add:
            st.write("")
            st.write("")
            if st.button("➕ Adicionar Novo", type="primary", use_container_width=True, key="btn_add_txt"):
                st.session_state["texto_em_edicao"] = "NOVO"
                
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
                t_alvo = {"id": None, "titulo": "", "glosas_relacionadas": "", "texto": ""}
                if em_edicao != "NOVO":
                    for t in textos:
                        if t['id'] == em_edicao:
                            t_alvo = t
                            break
                            
                f_tit = st.text_input("Título (Identificador Interno)", value=t_alvo["titulo"])
                f_glo = st.text_input("Glosas Relacionadas (ex: 438, 450)", value=t_alvo["glosas_relacionadas"])
                
                st.markdown("Use `{guia}` para a frase que exibe as guias, `{glosas}` para as descrições e `{procedimentos}` para os códigos.")
                f_txt = st.text_area("Texto Padrão ao Prestador", value=t_alvo["texto"], height=100)
                    
                b1, b2, b3 = st.columns([2, 2, 8])
                if b1.button("💾 Salvar", type="primary", use_container_width=True, key="btn_salvar_txt"):
                    if f_tit and f_glo and f_txt:
                        if em_edicao == "NOVO":
                            if db.inserir_texto_prestador(f_tit, f_glo, f_txt, nome):
                                st.success("Texto cadastrado com sucesso!")
                                st.session_state["texto_em_edicao"] = None
                                st.rerun()
                            else:
                                st.error("Erro ao salvar no banco.")
                        else:
                            if db.atualizar_texto_prestador(t_alvo['id'], f_tit, f_glo, f_txt, nome):
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
                    c1, c2, c3, c4 = st.columns([2, 2, 4, 2])
                    c1.markdown(f"**{t.get('titulo', 'Sem Título')}**")
                    c2.markdown(f"🎯 Glosas: `{t.get('glosas_relacionadas', '')}`")
                    c3.markdown(f"📝 *{t.get('texto', '')[:60]}...*")
                    
                    # Coluna de botões (Editar e Excluir)
                    b_edit, b_del = c4.columns([1, 1])
                    if b_edit.button("✏️", key=f"edit_txt_{t['id']}", help="Editar"):
                        st.session_state["texto_em_edicao"] = t['id']
                        st.rerun()
                    if b_del.button("❌", key=f"del_txt_{t['id']}", help="Excluir Definitivamente"):
                        if db.deletar_texto_prestador(t['id']):
                            st.rerun()
