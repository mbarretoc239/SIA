import re

import pandas as pd
import streamlit as st

from shared.database import DatabaseManager

st.title("Início")

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()
db = st.session_state.db

role = st.session_state.get("role_interno", "Contas")

# Último alinhamento visível para o role do usuário logado
st.markdown("### Último alinhamento")
alinhamentos_visiveis = db.carregar_alinhamentos_visiveis(role)
if not alinhamentos_visiveis:
    st.info("Nenhum alinhamento disponível para o seu nível de acesso.")
else:
    ultimo = alinhamentos_visiveis[0]
    with st.container(border=True):
        titulo = ultimo.get("titulo", "")
        if not ultimo.get("ativo", True):
            titulo = f"{titulo} (INATIVO)"
        st.markdown(f"**{titulo}**")

        conteudo = str(ultimo.get("conteudo") or "")
        m = re.match(r"^_(.*?)_\n\n(.*)$", conteudo, re.DOTALL)
        if m:
            conteudo = m.group(2)
        st.markdown(conteudo)

        data_criacao = pd.to_datetime(ultimo["created_at"]).strftime("%d/%m/%Y") if ultimo.get("created_at") else ""
        st.caption(f"{ultimo.get('categoria', 'Geral')} · Direcionado a {ultimo.get('nivel_minimo', 'Auditor')} · {data_criacao}")

    st.page_link("views/5_Alinhamentos.py", label="Ver todos os alinhamentos")

# Links úteis (institucionais) - agrupados por categoria
links_padrao = db.listar_links_padrao()
with st.expander("Links úteis", expanded=False):
    if not links_padrao:
        st.caption("Nenhum link cadastrado ainda.")
    else:
        agrupados = {}
        for l in links_padrao:
            agrupados.setdefault(l.get("categoria") or "Geral", []).append(l)
        for categoria in sorted(agrupados.keys()):
            with st.container(border=True):
                st.markdown(f"**{categoria}**")
                itens = agrupados[categoria]
                cols = st.columns(min(3, max(1, len(itens))))
                for i, link in enumerate(itens):
                    with cols[i % len(cols)]:
                        st.link_button(link.get("titulo") or "(sem título)", url=link.get("url", ""), use_container_width=True)
