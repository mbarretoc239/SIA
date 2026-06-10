import html
import re

import pandas as pd
import streamlit as st

from core.glass_design_system import render_glass_table
from core.settings import NIVEL_HIERARQUIA, ROLES_CIENCIA_OBRIGATORIA
from shared.database import DatabaseManager

st.set_page_config(page_title="Alinhamentos", page_icon="", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar os alinhamentos.")
    st.stop()

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()
db = st.session_state.db

role = st.session_state.get("role_interno", "Contas")
nome = st.session_state.get("auditor_nome", "Usuário")
usuario_id = st.session_state.get("usuario_id")

CATEGORIAS = ["Geral", "Técnico", "Administrativo", "CAP"]
NIVEIS = ["Contas", "Auditor", "CISO", "Gestor"]

st.title(" Alinhamentos")
st.markdown("Histórico de decisões e alinhamentos internos da equipe.")

pode_gerenciar = role in ["Gestor", "Admin"]

if pode_gerenciar:
    aba_historico, aba_gerenciar = st.tabs(["Histórico", "Gerenciar"])
else:
    aba_historico, = st.tabs(["Histórico"])


def _status_html(ativo):
    if ativo:
        return "🟢 Ativo"
    return "🔴 Inativo"


def _titulo_html(titulo, ativo):
    if ativo:
        return str(titulo)
    return f"❌ {titulo} (INATIVO)"


def _conteudo_html(conteudo):
    texto = str(conteudo or "")
    m = re.match(r"^_(.*?)_\n\n(.*)$", texto, re.DOTALL)
    if m:
        return m.group(2)
    return texto


with aba_historico:
    alinhamentos = db.carregar_alinhamentos_visiveis(role)

    if not alinhamentos:
        st.info("Nenhum alinhamento disponível para o seu nível de acesso.")
    else:
        anos_disponiveis = sorted({
            pd.to_datetime(a["created_at"]).year for a in alinhamentos if a.get("created_at")
        }, reverse=True)

        col_cat, col_ano, col_busca = st.columns([1, 1, 2])
        with col_cat:
            categoria_filtro = st.selectbox("Categoria", ["Todas"] + CATEGORIAS)
        with col_ano:
            ano_filtro = st.selectbox("Ano", ["Todos"] + [str(a) for a in anos_disponiveis])
        with col_busca:
            busca = st.text_input("Pesquisar (título ou conteúdo)", placeholder="Ex: biometria, glosa 480...")

        filtrados = alinhamentos
        if categoria_filtro != "Todas":
            filtrados = [a for a in filtrados if a.get("categoria") == categoria_filtro]
        if ano_filtro != "Todos":
            filtrados = [a for a in filtrados if str(pd.to_datetime(a["created_at"]).year) == ano_filtro]
        if busca:
            busca_lower = busca.lower()
            filtrados = [
                a for a in filtrados
                if busca_lower in a.get("titulo", "").lower() or busca_lower in a.get("conteudo", "").lower()
            ]

        if not filtrados:
            st.info("Nenhum alinhamento encontrado com esses filtros.")
        else:
            df_visual = pd.DataFrame([
                {
                    "Status": _status_html(a.get("ativo", True)),
                    "Criado em": pd.to_datetime(a["created_at"]).date(),
                    "Título": _titulo_html(a.get("titulo", ""), a.get("ativo", True)),
                    "Deliberação": _conteudo_html(a.get("conteudo", "")),
                    "Categoria": a.get("categoria", "Geral"),
                    "Direcionado a": a.get("nivel_minimo", "Auditor"),
                }
                for a in filtrados
            ])
            st.dataframe(
                df_visual, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Criado em": st.column_config.DateColumn("Criado em", format="DD/MM/YYYY"),
                    "Título": st.column_config.TextColumn("Título", width="medium"),
                    "Deliberação": st.column_config.TextColumn("Deliberação", width="large"),
                }
            )


if pode_gerenciar:
    with aba_gerenciar:
        st.markdown("**Novo Alinhamento**")
        with st.form("novo_alinhamento", clear_on_submit=True):
            f_titulo = st.text_input("Título / Assunto")
            f_conteudo = st.text_area("Conteúdo / Deliberação", height=120)
            col_cat, col_nivel = st.columns(2)
            with col_cat:
                f_categoria = st.selectbox("Categoria", CATEGORIAS, key="novo_categoria")
            with col_nivel:
                f_nivel = st.selectbox("Nível mínimo (quem recebe e precisa confirmar ciência)", NIVEIS, index=1, key="novo_nivel")

            if st.form_submit_button("Publicar Alinhamento", type="primary"):
                if not f_titulo or not f_conteudo:
                    st.warning("Preencha título e conteúdo.")
                else:
                    if db.inserir_alinhamento(f_titulo, f_conteudo, f_categoria, f_nivel, usuario_id):
                        st.success("Alinhamento publicado com sucesso!")
                        st.rerun()
                    else:
                        st.error("Erro ao publicar o alinhamento.")

        st.divider()
        st.markdown("**Todos os Alinhamentos**")

        todos_base = db.carregar_alinhamentos()
        anos_disponiveis = sorted({
            pd.to_datetime(a["created_at"]).year for a in todos_base if a.get("created_at")
        }, reverse=True)

        col_cat2, col_ano2, col_busca2 = st.columns([1, 1, 2])
        with col_cat2:
            categoria_filtro2 = st.selectbox("Categoria", ["Todas"] + CATEGORIAS, key="gerenciar_categoria")
        with col_ano2:
            ano_filtro2 = st.selectbox("Ano", ["Todos"] + [str(a) for a in anos_disponiveis], key="gerenciar_ano")
        with col_busca2:
            busca2 = st.text_input("Pesquisar", placeholder="Ex: biometria, glosa 480...", key="gerenciar_busca")

        todos = todos_base
        if categoria_filtro2 != "Todas":
            todos = [a for a in todos if a.get("categoria") == categoria_filtro2]
        if ano_filtro2 != "Todos":
            todos = [a for a in todos if str(pd.to_datetime(a["created_at"]).year) == ano_filtro2]
        if busca2:
            busca2_lower = busca2.lower()
            todos = [
                a for a in todos
                if busca2_lower in a.get("titulo", "").lower() or busca2_lower in a.get("conteudo", "").lower()
            ]

        if not todos:
            st.info("Nenhum alinhamento cadastrado.")
        else:
            usuarios_ativos = db.carregar_usuarios_ativos()
            leituras = db.carregar_todas_leituras()
            leituras_por_alinhamento = {}
            for l in leituras:
                leituras_por_alinhamento.setdefault(l["alinhamento_id"], {})[l["usuario_id"]] = l["lido_em"]

            for a in todos:
                aid = a["id"]
                status_label = "Ativo" if a.get("ativo", True) else "Inativo"
                data_atual = pd.to_datetime(a["created_at"]).date()
                titulo_exp = f"[{a.get('categoria', 'Geral')}] {data_atual.strftime('%d/%m/%Y')} — {a.get('titulo', '')} — {status_label}"
                with st.expander(titulo_exp):
                    e_titulo = st.text_input("Título / Assunto", value=a.get("titulo", ""), key=f"titulo_{aid}")
                    e_conteudo = st.text_area("Conteúdo / Deliberação", value=a.get("conteudo", ""), height=120, key=f"conteudo_{aid}")

                    col_cat3, col_nivel3, col_data3, col_ativo3 = st.columns([1, 1, 1, 0.7])
                    with col_cat3:
                        idx_cat = CATEGORIAS.index(a.get("categoria")) if a.get("categoria") in CATEGORIAS else 0
                        e_categoria = st.selectbox("Categoria", CATEGORIAS, index=idx_cat, key=f"categoria_{aid}")
                    with col_nivel3:
                        idx_nivel = NIVEIS.index(a.get("nivel_minimo")) if a.get("nivel_minimo") in NIVEIS else 1
                        e_nivel = st.selectbox("Nível mínimo", NIVEIS, index=idx_nivel, key=f"nivel_{aid}")
                    with col_data3:
                        e_data = st.date_input("Criado em", value=data_atual, format="DD/MM/YYYY", key=f"data_{aid}")
                    with col_ativo3:
                        st.write("")
                        st.write("")
                        e_ativo = st.checkbox("Ativo", value=a.get("ativo", True), key=f"ativo_{aid}")

                    nivel_min_valor = NIVEL_HIERARQUIA.get(a.get("nivel_minimo", "Auditor"), 1)
                    obrigados = [
                        u for u in usuarios_ativos
                        if u.get("role_interno") in ROLES_CIENCIA_OBRIGATORIA
                        and NIVEL_HIERARQUIA.get(u.get("role_interno"), 1) >= nivel_min_valor
                    ]
                    if obrigados:
                        leituras_item = leituras_por_alinhamento.get(aid, {})
                        confirmaram = [u for u in obrigados if u["id"] in leituras_item]
                        pendentes_ciencia = [u for u in obrigados if u["id"] not in leituras_item]

                        st.markdown("**Status de Ciência**")
                        st.progress(len(confirmaram) / len(obrigados))
                        st.caption(f"{len(confirmaram)}/{len(obrigados)} confirmaram a ciência")

                        with st.expander(f"Ver detalhes ({len(obrigados)} pessoas)"):
                            df_ciencia = pd.DataFrame([
                                {
                                    "Usuário": u["nome_completo"],
                                    "Status": "✅ Confirmou" if u["id"] in leituras_item else "⏳ Pendente",
                                    "Lido em": pd.to_datetime(leituras_item[u["id"]]).strftime("%d/%m/%Y %H:%M") if u["id"] in leituras_item else "—",
                                }
                                for u in pendentes_ciencia + confirmaram
                            ])
                            st.dataframe(df_ciencia, use_container_width=True, hide_index=True)

                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        if st.button("Salvar Alterações", key=f"salvar_{aid}", type="primary", use_container_width=True):
                            nova_data = e_data.strftime("%Y-%m-%d") if e_data != data_atual else None
                            sucesso_dados = db.atualizar_alinhamento(aid, e_titulo, e_conteudo, e_categoria, e_nivel, nova_data)
                            sucesso_status = db.toggle_ativo_alinhamento(aid, e_ativo) if e_ativo != a.get("ativo", True) else True
                            if sucesso_dados and sucesso_status:
                                st.success("Alinhamento atualizado!")
                                st.rerun()
                            else:
                                st.error("Erro ao atualizar o alinhamento.")
                    with col_b2:
                        toggle_label = "Desativar" if a.get("ativo", True) else "Reativar"
                        if st.button(toggle_label, key=f"toggle_{aid}", use_container_width=True):
                            if db.toggle_ativo_alinhamento(aid, not a.get("ativo", True)):
                                st.rerun()
                            else:
                                st.error("Erro ao alterar status.")
