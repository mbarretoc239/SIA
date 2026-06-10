import streamlit as st

st.set_page_config(page_title="Calculadora de Glosa", page_icon="", layout="centered")

st.title(" Calculadora de Glosa")
st.markdown("Calcule rapidamente o percentual glosado através dos valores cobrados e pagos.")

# Funções auxiliares de formatação
def parse_moeda(valor_str):
    if not valor_str:
        return 0.0
    valor_str = str(valor_str).replace("R$", "").replace(" ", "")
    valor_str = valor_str.replace(".", "").replace(",", ".")
    try:
        return float(valor_str)
    except ValueError:
        return 0.0

def formatar_moeda(valor):
    # Formata de float para string tipo R$ 1.500,00
    try:
        formatado = f"R$ {valor:,.2f}"
        formatado = formatado.replace(",", "X").replace(".", ",").replace("X", ".")
        return formatado
    except:
        return "R$ 0,00"

with st.container():
    st.markdown("###  Entrada de Valores")
    
    col1, col2 = st.columns(2)
    with col1:
        v_cobrado_str = st.text_input("Valor Cobrado (R$)", placeholder="Ex: 1500,50")
    with col2:
        v_pago_str = st.text_input("Valor Pago (R$)", placeholder="Ex: 1200,00")

    if st.button("Calcular Glosa", type="primary", use_container_width=True):
        if not v_cobrado_str or not v_pago_str:
            st.warning("Preencha ambos os campos para calcular.")
        else:
            cobrado = parse_moeda(v_cobrado_str)
            pago = parse_moeda(v_pago_str)
            
            if cobrado <= 0:
                st.error("O valor cobrado deve ser maior que zero.")
            elif pago > cobrado:
                st.error("O valor pago não pode ser maior que o valor cobrado!")
            else:
                glosado = cobrado - pago
                pct_glosa = (glosado / cobrado) * 100
                pct_pago = 100 - pct_glosa
                
                st.divider()
                st.markdown("###  Resultado")
                
                if glosado == 0:
                    st.success("Sem glosas aplicadas! 100% pago.")
                else:
                    st.error(f"**Taxa de Glosa:** {pct_glosa:.1f}%")
                
                # Exibição visual com métricas
                c1, c2, c3 = st.columns(3)
                c1.metric("Cobrado", formatar_moeda(cobrado))
                c2.metric("Pago", formatar_moeda(pago), f"{pct_pago:.1f}%" if cobrado>0 else "")
                c3.metric("Glosado", formatar_moeda(glosado), f"-{pct_glosa:.1f}%" if glosado>0 else "")
                
                # Barra de progresso visual simulada com HTML
                st.markdown("#### Proporção Visual")
                st.markdown(f"""
                <div style="width: 100%; background-color: #ff4b4b; border-radius: 8px; overflow: hidden; display: flex; height: 24px;">
                    <div style="width: {pct_pago}%; background-color: #00cc96; height: 100%; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 12px;">
                        {pct_pago:.0f}% Pago
                    </div>
                </div>
                """, unsafe_allow_html=True)
