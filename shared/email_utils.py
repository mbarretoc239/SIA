import smtplib
import streamlit as st
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

_DESTINATARIOS = ["matheus.cardoso@hapvida.com.br", "matheusb239@gmail.com"]


def enviar_reporte_bug(titulo: str, texto: str, autor: str, anexos: list) -> bool:
    """Envia um reporte de bug por e-mail com anexos de imagem opcionais.
    Retorna True se enviou com sucesso, False caso contrário (erro fica em st.session_state["_erro_envio_bug"])."""
    smtp_cfg = st.secrets.get("smtp", {})
    host = smtp_cfg.get("host", "smtp.gmail.com")
    port = int(smtp_cfg.get("port", 587))
    usuario = smtp_cfg.get("user", "")
    senha = smtp_cfg.get("password", "")

    if not usuario or not senha:
        st.session_state["_erro_envio_bug"] = "Envio de e-mail não configurado (smtp.user/smtp.password ausentes em secrets.toml)."
        return False

    msg = MIMEMultipart()
    msg["Subject"] = f"[SIA] Reporte de bug: {titulo}"
    msg["From"] = usuario
    msg["To"] = ", ".join(_DESTINATARIOS)

    corpo = (
        f"Reportado por: {autor}\n"
        f"Data/hora: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        f"{texto}"
    )
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    for anexo in anexos or []:
        try:
            imagem = MIMEImage(anexo.getvalue())
            imagem.add_header("Content-Disposition", "attachment", filename=anexo.name)
            msg.attach(imagem)
        except Exception:
            continue

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(usuario, senha)
            server.sendmail(usuario, _DESTINATARIOS, msg.as_string())
        return True
    except Exception as e:
        st.session_state["_erro_envio_bug"] = str(e)
        return False
