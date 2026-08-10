import html
import smtplib
import time
import streamlit as st
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

_DESTINATARIOS = ["matheus.cardoso@hapvida.com.br", "matheusb239@gmail.com"]
# O canal do Teams ("Notificações do SIA - Auditoria Odonto") rejeita e-mail
# vindo do Gmail (remetente fora da organização Hapvida) -- não dá pra
# mandar direto pro endereço do canal. Todo assunto aqui já sai com a tag
# "[SIA]"; roteamento pro Teams é via Power Automate (mesmo mecanismo do
# FAROL): um flow lê a caixa matheus.cardoso@hapvida.com.br, filtra por essa
# tag e posta no canal como usuário da organização.


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
    # HTML em vez de plain: o flow do Power Automate que repassa pro Teams
    # ignora quebra de linha simples (\n) e colapsa tudo numa linha só --
    # mesmo problema (e mesma correção) já usada no FAROL.
    corpo_html = html.escape(corpo).replace("\n", "<br>")
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))

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


_ULTIMO_PEDIDO_ESQUECI_SENHA = {}  # usuario_sigo (lower) -> timestamp do ultimo aviso enviado
_INTERVALO_ESQUECI_SENHA_SEG = 5 * 60


def pode_notificar_esqueci_senha(usuario_sigo: str) -> bool:
    """Rate-limit de 1 pedido por SIGO a cada 5 min -- a tela de login não
    exige autenticação, então sem isso dava pra martelar o botão e floodar
    e-mail/Teams. Dict em memória de módulo (não st.session_state, que é
    por sessão/navegador e seria trivial de burlar dando F5)."""
    chave = usuario_sigo.strip().lower()
    agora = time.monotonic()
    ultimo = _ULTIMO_PEDIDO_ESQUECI_SENHA.get(chave)
    if ultimo is not None and (agora - ultimo) < _INTERVALO_ESQUECI_SENHA_SEG:
        return False
    _ULTIMO_PEDIDO_ESQUECI_SENHA[chave] = agora
    return True


def notificar_esqueci_senha(usuario_sigo: str, nome_completo: str = "") -> bool:
    """Avisa que alguém clicou em 'Esqueci a senha' na tela de login. Reset
    em si continua manual, em Configurações > Redefinir senha de usuário.
    Chame pode_notificar_esqueci_senha() antes, pra respeitar o rate-limit."""
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
