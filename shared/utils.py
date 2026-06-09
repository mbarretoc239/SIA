import sys
import ctypes
from PIL import ImageTk
import logging
import re
import os
import webbrowser
import pyperclip

logger = logging.getLogger("sia")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())

def registrar_erro(contexto, erro=None):
    try:
        if erro is None:
            logger.exception(contexto)
        else:
            logger.exception("%s: %s", contexto, erro)
    except Exception:
        pass

def corrigir_mojibake(texto):
    if not isinstance(texto, str) or not texto:
        return texto

    candidatos = [texto]
    atual = texto

    for _ in range(3):
        if not any(marca in atual for marca in ("Ã", "Â", "â", "")):
            break
        try:
            convertido = atual.encode("latin-1").decode("utf-8")
        except UnicodeError:
            break
        if convertido == atual:
            break
        candidatos.append(convertido)
        atual = convertido

    def pontuacao(valor):
        ruins = len(re.findall(r"[ÃÂâ]", valor))
        boas = len(re.findall(r"[áéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ]", valor))
        return (ruins, -boas, len(valor))

    return min(candidatos, key=pontuacao)

def copiar_texto_clipboard(texto, widget_fallback=None):
    texto = "" if texto is None else str(texto)
    try:
        pyperclip.copy(texto)
        return True
    except Exception as erro:
        registrar_erro("Falha ao copiar texto com pyperclip", erro)
        if widget_fallback is not None:
            try:
                widget_fallback.clipboard_clear()
                widget_fallback.clipboard_append(texto)
                widget_fallback.update_idletasks()
                return True
            except Exception as erro_fallback:
                registrar_erro("Falha ao copiar texto com clipboard do Tk", erro_fallback)
    return False

def abrir_url_padrao(url):
    try:
        if hasattr(os, "startfile"):
            os.startfile(url)
        else:
            webbrowser.open(url)
        return True
    except Exception as erro:
        registrar_erro(f"Falha ao abrir URL: {url}", erro)
        try:
            webbrowser.open(url)
            return True
        except Exception as erro_web:
            registrar_erro(f"Falha no fallback do navegador: {url}", erro_web)
    return False

def widget_existe(widget):
    try:
        return widget is not None and widget.winfo_exists()
    except Exception:
        return False

def after_seguro(widget, delay_ms, callback, *args):
    if not widget_existe(widget):
        return None
    try:
        return widget.after(delay_ms, callback, *args)
    except Exception as erro:
        registrar_erro("Falha ao agendar callback no Tk", erro)
        return None

def remover_arquivo_seguro(caminho):
    try:
        if caminho and os.path.exists(caminho):
            os.remove(caminho)
            return True
    except Exception as erro:
        registrar_erro(f"Falha ao remover arquivo: {caminho}", erro)
    return False

def _eh_transparente(valor):
    return valor in ("transparent", "Transparent", None)

def _primeira_cor(valor, fallback=None):
    if isinstance(valor, (list, tuple)) and valor:
        return valor[0]
    return valor if valor is not None else fallback

def _texto_menor(widget):
    try:
        font = widget.cget("font")
        if isinstance(font, tuple) and len(font) >= 2:
            return int(font[1]) <= 12
    except Exception:
        pass
    return False

def caminho_recurso(caminho_relativo):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(sys.argv[0]) or ".")
    return os.path.join(base_path, caminho_relativo)

def configurar_app_id_windows(app_id="matheusbarreto.sia.v5"):
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

def aplicar_icone_janela(janela, nome_icone="SIA4.ico"):
    caminho_icone = caminho_recurso(nome_icone)
    if not os.path.exists(caminho_icone):
        return None
    try:
        janela.iconbitmap(caminho_icone)
    except Exception:
        pass
    try:
        janela.wm_iconbitmap(caminho_icone)
    except Exception:
        pass
    try:
        icone_img = ImageTk.PhotoImage(file=caminho_icone)
        janela.iconphoto(True, icone_img)
        janela._sia_icon_ref = icone_img
    except Exception:
        pass
    return caminho_icone
