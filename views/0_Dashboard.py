import streamlit as st

st.title("🏠 Painel de Controle")
st.success("Conexão com o Banco de Dados Nuvem e Chaves de Criptografia carregadas com sucesso!")

st.markdown("### Módulos Disponíveis")
col1, col2, col3 = st.columns(3)
with col1:
    st.info("🧮 **Módulo Calculadora**\n\nFerramenta para cálculo rápido de porcentagem glosada sobre os valores cobrados.")
with col2:
    st.warning("📈 **Análise de Produção**\n\nExtração e ranqueamento dos procedimentos mais solicitados através de leitura de PDFs de pagamento.")
with col3:
    st.error("📄 **Relatório 5302**\n\nGeração automatizada de relatórios a partir de PDFs da operadora, com motor inteligente de texto.")
