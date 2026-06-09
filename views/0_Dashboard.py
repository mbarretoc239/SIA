import streamlit as st

st.title("🏠 Painel de Controle")
st.success("Conexão com o Banco de Dados Nuvem e Chaves de Criptografia carregadas com sucesso!")

st.markdown("### Módulos Disponíveis")
col1, col2, col3 = st.columns(3)
with col1:
    st.info("🧮 Módulo Calculadora (Em breve)")
with col2:
    st.warning("📊 Análise de Risco (Em breve)")
with col3:
    st.error("📄 Relatório 5302 (Em breve)")
