import streamlit as st

from shared.database import DatabaseManager

st.title(" Painel de Controle")

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()
db = st.session_state.db

# Links úteis (institucionais) - agrupados por categoria
links_padrao = db.listar_links_padrao()
if links_padrao:
    st.markdown("### Links úteis")
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
