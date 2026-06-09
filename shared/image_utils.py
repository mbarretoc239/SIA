import io
import hashlib
from datetime import datetime
from PIL import Image

def _agora_str():
    return datetime.now().strftime('%d/%m/%Y %H:%M:%S')

def sha1_imagem(imagem_pil):
    buff = io.BytesIO()
    imagem_pil.convert('RGB').save(buff, format='PNG')
    return hashlib.sha1(buff.getvalue()).hexdigest()

def resize_equilibrio(imagem_pil, max_lado=1600):
    img = imagem_pil.convert('RGB')
    w, h = img.size
    maior = max(w, h)
    if maior <= max_lado: return img
    fator = max_lado / float(maior)
    nw = max(1, int(w * fator))
    nh = max(1, int(h * fator))
    return img.resize((nw, nh), Image.Resampling.LANCZOS)

def thumb(imagem_pil, lado=256):
    img = imagem_pil.convert('RGB').copy()
    img.thumbnail((lado, lado), Image.Resampling.LANCZOS)
    return img

def salvar_webp(imagem_pil, caminho, quality=82):
    caminho = str(caminho)
    imagem_pil.convert('RGB').save(caminho, format='WEBP', quality=quality, method=6)
