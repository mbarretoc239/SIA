import streamlit as st
import pandas as pd

from shared.database import DatabaseManager

st.title(" Painel de Controle")
st.success("Conexão com o Banco de Dados Nuvem e Chaves de Criptografia carregadas com sucesso!")

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()
db = st.session_state.db

with st.container(border=True):
    st.markdown("###  Novidades do Sistema")
    novidades = db.carregar_changelog(limite=5)
    if not novidades:
        st.caption("Nenhuma novidade registrada ainda.")
    else:
        agora = pd.Timestamp.now(tz="UTC")
        for i, item in enumerate(novidades):
            data_item = pd.to_datetime(item["created_at"])
            badge = " 🆕" if (agora - data_item) <= pd.Timedelta(days=7) else ""
            st.markdown(f"**{item['titulo']}**{badge}")
            st.markdown(item["descricao"])
            st.caption(data_item.strftime("%d/%m/%Y"))
            if i < len(novidades) - 1:
                st.divider()

st.markdown("### Módulos Disponíveis")
col1, col2, col3 = st.columns(3)
with col1:
    st.info(" **Módulo Calculadora**\n\nFerramenta para cálculo rápido de porcentagem glosada sobre os valores cobrados.")
with col2:
    st.warning(" **Análise de Produção**\n\nExtração e ranqueamento dos procedimentos mais solicitados através de leitura de PDFs de pagamento.")
with col3:
    st.error(" **Relatório 5302**\n\nGeração automatizada de relatórios a partir de PDFs da operadora, com motor inteligente de texto.")
