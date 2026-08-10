import smtplib
import streamlit as st
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

_DESTINATARIOS = ["matheus.cardoso@hapvida.com.br", "matheusb239@gmail.com"]


def _enviar_email(assunto: str, corpo: str, anexos: list = None, erro_key: str = "_erro_envio_email") -> bool:
    """Monta e envia um e-mail simples (texto + anexos de imagem opcionais)
    pros _DESTINATARIOS via SMTP. Retorna True se enviou, False caso
    contrário (erro fica em st.session_state[erro_key])."""
    smtp_cfg = st.secrets.get("smtp", {})
    host = smtp_cfg.get("host", "smtp.gmail.com")
    port = int(smtp_cfg.get("port", 587))
    usuario = smtp_cfg.get("user", "")
    senha = smtp_cfg.get("password", "")

    if not usuario or not senha:
        st.session_state[erro_key] = "Envio de e-mail não configurado (smtp.user/smtp.password ausentes em secrets.toml)."
        return False

    msg = MIMEMultipart()
    msg["Subject"] = assunto
    msg["From"] = usuario
    msg["To"] = ", ".join(_DESTINATARIOS)
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
        st.session_state[erro_key] = str(e)
        return False


def enviar_reporte_bug(titulo: str, texto: str, autor: str, anexos: list) -> bool:
    """Envia um reporte de bug por e-mail com anexos de imagem opcionais.
    Retorna True se enviou com sucesso, False caso contrário (erro fica em st.session_state["_erro_envio_bug"])."""
    corpo = (
        f"Reportado por: {autor}\n"
        f"Data/hora: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        f"{texto}"
    )
    return _enviar_email(f"[SIA] Reporte de bug: {titulo}", corpo, anexos, erro_key="_erro_envio_bug")


def notificar_esqueci_senha(usuario_sigo: str, nome_completo: str = "") -> bool:
    """Avisa que alguém clicou em 'Esqueci a senha' na tela de login. Tag
    '[SIA]' no assunto pro Power Automate identificar e repassar pro Teams
    (mesmo mecanismo já usado no FAROL: e-mail -> flow -> canal). Reset em
    si continua manual, em Configurações > Redefinir senha de usuário."""
    quem = f"{nome_completo} ({usuario_sigo})" if nome_completo else usuario_sigo
    corpo = (
        f"Pedido de redefinição de senha no SIA:\n\n"
        f"Usuário SIGO: {usuario_sigo}\n"
        + (f"Nome: {nome_completo}\n" if nome_completo else "Nome: (usuário não encontrado na base)\n")
        + f"Data/hora: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        f"Redefina em Configurações > Redefinir senha de usuário."
    )
    return _enviar_email(f"[SIA] Esqueci a senha - {quem}", corpo, erro_key="_erro_envio_esqueci_senha")


def notificar_novo_cadastro(nome_completo: str, usuario_sigo: str, equipe: str) -> bool:
    """Avisa por e-mail que um novo usuário se cadastrou e está aguardando
    aprovação. Falha de envio não deve travar o cadastro em si — quem chama
    trata o retorno False só pra log/aviso discreto, não como erro fatal."""
    corpo = (
        f"Novo cadastro aguardando aprovação no SIA:\n\n"
        f"Nome: {nome_completo}\n"
        f"Usuário SIGO: {usuario_sigo}\n"
        f"Equipe solicitada: {equipe}\n"
        f"Data/hora: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        f"Aprove em Configurações > Aprovação da Equipe."
    )
    return _enviar_email(f"[SIA] Novo cadastro pendente: {usuario_sigo}", corpo, erro_key="_erro_envio_cadastro")
