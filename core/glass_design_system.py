import streamlit as st
import pandas as pd
import os

def inject_glass_css(*args, **kwargs):
    pass

def glass_card(content_html: str, color: str = None) -> None:
    st.markdown(content_html, unsafe_allow_html=True)

def glass_banner(text: str, color: str = None, icon: str = "") -> None:
    st.info(f"{icon} {text}")

def render_glass_table(df, fmt: dict = None, max_height: int = 440, html_cols=None, footer_html: str = None, wrap_cols=None) -> None:
    st.dataframe(df, use_container_width=True, hide_index=True)

def show_login_form(title: str = "Acesso Restrito", subtitle: str = "Insira suas credenciais para continuar.", logo_path: str = None) -> tuple:
    st.markdown("<div style='height: 60px'></div>", unsafe_allow_html=True)
    _, col, _ = st.columns([1, 2, 1])
    with col:
        if logo_path and os.path.exists(logo_path):
            try:
                st.image(logo_path, width=160)
            except:
                pass
        st.title(title)
        st.write(subtitle)
        with st.form("glass_login_form"):
            user_name = st.text_input("Seu Nome")
            password  = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar", use_container_width=True)
    return user_name, password, submitted
