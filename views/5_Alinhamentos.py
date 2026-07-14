import re

import pandas as pd
import streamlit as st

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
st.markdown("Histórico de alinhamentos internos.")

pode_gerenciar = role in ["Gestor", "Admin"]

if pode_gerenciar:
    aba_historico, aba_gerenciar, aba_excluidos = st.tabs(["Histórico", "Gerenciar", "Excluídos"])
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


def _obrigados_ciencia(alinhamento, usuarios_ativos):
    """Usuários que precisam confirmar ciência deste alinhamento (role sujeito
    a ciência obrigatória e hierarquia >= nível-alvo do alinhamento)."""
    nivel_min_valor = NIVEL_HIERARQUIA.get(alinhamento.get("nivel_minimo", "Auditor"), 1)
    return [
        u for u in usuarios_ativos
        if u.get("role_interno") in ROLES_CIENCIA_OBRIGATORIA
        and NIVEL_HIERARQUIA.get(u.get("role_interno"), 1) >= nivel_min_valor
    ]


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
            # Agrupa por público-alvo (nivel_minimo). A seção do próprio nível
            # do usuário vem aberta por padrão; as demais (níveis abaixo, que
            # cargos mais altos também enxergam) ficam colapsadas para não
            # poluir a visão de quem acumula vários níveis.
            por_nivel = {}
            for a in filtrados:
                por_nivel.setdefault(a.get("nivel_minimo", "Auditor"), []).append(a)

            niveis_presentes = [n for n in NIVEIS if n in por_nivel]

            for nivel in niveis_presentes:
                itens_nivel = por_nivel[nivel]
                aberto_por_padrao = (nivel == role)
                with st.expander(f"{nivel} ({len(itens_nivel)})", expanded=aberto_por_padrao):
                    df_visual = pd.DataFrame([
                        {
                            "Status": _status_html(a.get("ativo", True)),
                            "Criado em": pd.to_datetime(a["created_at"]).date(),
                            "Título": _titulo_html(a.get("titulo", ""), a.get("ativo", True)),
                            "Deliberação": _conteudo_html(a.get("conteudo", "")),
                            "Categoria": a.get("categoria", "Geral"),
                        }
                        for a in itens_nivel
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
        todos_base = db.carregar_alinhamentos()  # exclui excluídos por padrão
        anos_disponiveis2 = sorted({
            pd.to_datetime(a["created_at"]).year for a in todos_base if a.get("created_at")
        }, reverse=True)

        col_add, col_busca2, col_cat2, col_ano2 = st.columns([1.5, 3, 1.3, 1])

        with col_add:
            st.write("")
            if st.button("➕ Novo Alinhamento", type="primary", use_container_width=True, key="btn_novo_alinh"):
                st.session_state["alinhamento_em_edicao"] = "NOVO"
                st.rerun()
        with col_busca2:
            busca2 = st.text_input("Pesquisar", placeholder="Ex: biometria, glosa 480...", key="gerenciar_busca")
        with col_cat2:
            categoria_filtro2 = st.selectbox("Categoria", ["Todas"] + CATEGORIAS, key="gerenciar_categoria")
        with col_ano2:
            ano_filtro2 = st.selectbox("Ano", ["Todos"] + [str(a) for a in anos_disponiveis2], key="gerenciar_ano")

        # Carregados uma vez, usados tanto no formulário (ciência detalhada do
        # item selecionado) quanto na lista (mini indicador por linha).
        usuarios_ativos = db.carregar_usuarios_ativos()
        leituras = db.carregar_todas_leituras()
        leituras_por_alinhamento = {}
        for l in leituras:
            leituras_por_alinhamento.setdefault(l["alinhamento_id"], {})[l["usuario_id"]] = l["lido_em"]

        # ------------------------------------------------------------
        # Formulário único: Novo ou Editar (nunca os dois ao mesmo tempo,
        # nunca um formulário por item da lista).
        # ------------------------------------------------------------
        em_edicao = st.session_state.get("alinhamento_em_edicao")
        if em_edicao:
            st.divider()
            st.subheader("Editar Alinhamento" if em_edicao != "NOVO" else "Novo Alinhamento")

            with st.container(border=True):
                a_alvo = {"id": None, "titulo": "", "conteudo": "", "categoria": CATEGORIAS[0], "nivel_minimo": NIVEIS[1], "created_at": None}
                if em_edicao != "NOVO":
                    for a in todos_base:
                        if a["id"] == em_edicao:
                            a_alvo = a
                            break

                e_titulo = st.text_input("Título / Assunto", value=a_alvo.get("titulo", ""), key="edit_alinh_titulo")
                e_conteudo = st.text_area("Conteúdo / Deliberação", value=a_alvo.get("conteudo", ""), height=140, key="edit_alinh_conteudo")

                col_c1, col_c2, col_c3 = st.columns(3)
                with col_c1:
                    idx_cat = CATEGORIAS.index(a_alvo.get("categoria")) if a_alvo.get("categoria") in CATEGORIAS else 0
                    e_categoria = st.selectbox("Categoria", CATEGORIAS, index=idx_cat, key="edit_alinh_categoria")
                with col_c2:
                    idx_nivel = NIVEIS.index(a_alvo.get("nivel_minimo")) if a_alvo.get("nivel_minimo") in NIVEIS else 1
                    e_nivel = st.selectbox("Nível mínimo (quem recebe e precisa confirmar ciência)", NIVEIS, index=idx_nivel, key="edit_alinh_nivel")
                with col_c3:
                    e_data = None
                    if em_edicao != "NOVO" and a_alvo.get("created_at"):
                        data_original = pd.to_datetime(a_alvo["created_at"]).date()
                        e_data = st.date_input("Criado em", value=data_original, format="DD/MM/YYYY", key="edit_alinh_data")

                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("Salvar", type="primary", use_container_width=True, key="btn_salvar_alinh"):
                        if not e_titulo or not e_conteudo:
                            st.warning("Preencha título e conteúdo.")
                        elif em_edicao == "NOVO":
                            if db.inserir_alinhamento(e_titulo, e_conteudo, e_categoria, e_nivel, usuario_id):
                                st.success("Alinhamento publicado!")
                                st.session_state["alinhamento_em_edicao"] = None
                                st.rerun()
                            else:
                                st.error("Erro ao publicar o alinhamento.")
                        else:
                            data_original = pd.to_datetime(a_alvo["created_at"]).date() if a_alvo.get("created_at") else None
                            nova_data = e_data.strftime("%Y-%m-%d") if (e_data and e_data != data_original) else None
                            if db.atualizar_alinhamento(em_edicao, e_titulo, e_conteudo, e_categoria, e_nivel, nova_data):
                                st.success("Alinhamento atualizado!")
                                st.session_state["alinhamento_em_edicao"] = None
                                st.rerun()
                            else:
                                st.error("Erro ao atualizar o alinhamento.")
                with col_b2:
                    if st.button("Cancelar", use_container_width=True, key="btn_cancelar_alinh"):
                        st.session_state["alinhamento_em_edicao"] = None
                        st.rerun()

                if em_edicao != "NOVO":
                    obrigados = _obrigados_ciencia(a_alvo, usuarios_ativos)
                    if obrigados:
                        leituras_item = leituras_por_alinhamento.get(em_edicao, {})
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

            st.divider()

        # ------------------------------------------------------------
        # Lista (Action Cards): informação à esquerda, ações à direita.
        # Uma linha fina por item, sem formulário embutido.
        # ------------------------------------------------------------
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

        st.markdown(f"**{len(todos)} alinhamento(s)**")
        if not todos:
            st.info("Nenhum alinhamento encontrado com esses filtros.")

        for a in todos:
            aid = a["id"]
            ativo = a.get("ativo", True)
            data_fmt = pd.to_datetime(a["created_at"]).strftime("%d/%m/%Y") if a.get("created_at") else "—"

            obrigados = _obrigados_ciencia(a, usuarios_ativos)
            leituras_item = leituras_por_alinhamento.get(aid, {})
            ciencia_label = ""
            if obrigados:
                confirmaram_n = len([u for u in obrigados if u["id"] in leituras_item])
                ciencia_label = f" · {confirmaram_n}/{len(obrigados)} cientes"

            col_info, col_status, col_edit, col_del = st.columns([4, 1.8, 1, 1])
            with col_info:
                titulo_txt = a.get("titulo", "") if ativo else f"~~{a.get('titulo', '')}~~"
                st.markdown(f"**{titulo_txt}**")
                st.caption(f"{data_fmt} · {a.get('categoria', 'Geral')} · {a.get('nivel_minimo', 'Auditor')}{ciencia_label}")
                with st.expander("Ler texto completo"):
                    st.markdown(_conteudo_html(a.get("conteudo", "")))
            with col_status:
                if ativo:
                    st.caption("🟢 Ativo")
                    with st.popover("Inativar", use_container_width=True):
                        st.markdown(f"Inativar **{a.get('titulo', '')}**?")
                        motivo_inativ = st.text_area("Justificativa (obrigatória)", key=f"motivo_inativ_{aid}", height=80)
                        if st.button("Confirmar inativação", key=f"conf_inativ_{aid}", type="primary", use_container_width=True):
                            if not motivo_inativ.strip():
                                st.warning("Justificativa obrigatória.")
                            elif db.toggle_ativo_alinhamento(aid, False, justificativa=motivo_inativ.strip()):
                                st.rerun()
                            else:
                                st.error("Erro ao inativar.")
                else:
                    st.caption("🔴 Inativo")
                    if st.button("Reativar", key=f"reativ_{aid}", use_container_width=True):
                        if db.toggle_ativo_alinhamento(aid, True):
                            st.rerun()
                        else:
                            st.error("Erro ao reativar.")
            with col_edit:
                if st.button("Editar", key=f"edit_alinh_{aid}", use_container_width=True):
                    st.session_state["alinhamento_em_edicao"] = aid
                    st.rerun()
            with col_del:
                with st.popover("Excluir", use_container_width=True):
                    st.markdown(f"Excluir **{a.get('titulo', '')}**?")
                    st.caption("O alinhamento vai para a área \"Excluídos\" — nada é apagado de fato.")
                    motivo_excl = st.text_area("Motivo da exclusão (obrigatório)", key=f"motivo_excl_{aid}", height=80)
                    if st.button("Confirmar exclusão", key=f"conf_excl_{aid}", type="primary", use_container_width=True):
                        if not motivo_excl.strip():
                            st.warning("Motivo obrigatório.")
                        elif db.excluir_alinhamento_com_motivo(aid, motivo_excl, usuario_id):
                            st.rerun()
                        else:
                            st.error("Erro ao excluir.")
            st.divider()


if pode_gerenciar:
    with aba_excluidos:
        st.markdown("Alinhamentos excluídos, com motivo e responsável. Restaurar devolve o item para a lista de gerenciamento.")

        excluidos = db.carregar_alinhamentos_excluidos()
        if not excluidos:
            st.info("Nenhum alinhamento excluído.")
        else:
            usuarios_map = {u["id"]: u.get("nome_completo", "?") for u in db.listar_usuarios()}

            for a in excluidos:
                aid = a["id"]
                col_info, col_act = st.columns([6, 1.4])
                with col_info:
                    st.markdown(f"**{a.get('titulo', '')}**")
                    data_orig = pd.to_datetime(a["created_at"]).strftime("%d/%m/%Y") if a.get("created_at") else "—"
                    data_excl = pd.to_datetime(a["excluido_em"]).strftime("%d/%m/%Y %H:%M") if a.get("excluido_em") else "—"
                    quem_excluiu = usuarios_map.get(a.get("excluido_por"), "Desconhecido")
                    st.caption(f"Criado em {data_orig} · {a.get('categoria', 'Geral')} · {a.get('nivel_minimo', 'Auditor')}")
                    st.caption(f"Excluído por {quem_excluiu} em {data_excl}")
                    st.caption(f"Motivo: {a.get('motivo_exclusao') or '—'}")
                with col_act:
                    st.write("")
                    if st.button("↩️ Restaurar", key=f"restaurar_{aid}", use_container_width=True):
                        if db.restaurar_alinhamento(aid):
                            st.success("Restaurado.")
                            st.rerun()
                        else:
                            st.error("Erro ao restaurar.")
                st.divider()
