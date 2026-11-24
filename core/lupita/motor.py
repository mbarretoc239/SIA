"""Motor da Lupita no SIA: 56 medidas da imagem + regressão logística L2 + Platt.

Cópia de detector_sintetico/lupa_local.py (port do artefato "Lupa Forense" do navegador), sem a
linha de comando e lendo a imagem de bytes (nada vai a disco). Paridade com o navegador conferida
nas 8 radiografias reais do SIGO do pacote de referência (diferença ~0); só imagens acima de 512 px
mudam um pouco, pelo filtro de redução (LANCZOS aqui).

Dependências: numpy, scipy, pillow.
"""
from __future__ import annotations

import io
import math
import re

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage

VERSAO_MEDIDAS = 1

GRUPOS = {
    "freq": ["fSlope", "fHM", "fML", "fTail", "fPeak", "fAniso"],
    "noise": ["nStd", "nKurt", "nQ10", "nSpread", "nSig", "nCC"],
    "edges": ["gMean", "gRatio", "gSharp", "gOrient"],
    "texture": ["tLBP", "tVarCV", "tSmooth", "tEnt"],
    "compress": ["mBlock", "mEmpty"],
    "color": ["cSat", "cSatSd", "cColorful", "cDark", "cBright", "cContrast", "cMean", "cChanCorr"],
    "radio": ["rColorDev", "rP5", "rP50", "rP95", "rRange", "rExtremes", "rFracDark", "rFracMid", "rFracBright",
              "rToothBone", "rNComp", "rAreaMax", "rElong", "rWidth", "rLength", "rTilt", "rTiltSd", "rRootSplit"],
    "file": ["aLogMP", "aAspect", "aDiv64", "aBpp", "aIsPng", "aIsJpeg", "aExifCam", "aAiMeta"],
}
GRUPOS_PADRAO = [g for g in GRUPOS if g != "file"]
PISO_DESVIO = {"rColorDev": 0.15, "cDark": 0.1, "cBright": 0.1}
ZCLIP = 5.0
LAMBDAS = [0.3, 1, 3, 10, 30, 100]
PADROES_IA = [
    r"trainedAlgorithmicMedia|compositeWithTrainedAlgorithmicMedia", r"midjourney", r"dall[-·.\s]?e",
    r"openai|chatgpt", r"stable[\s-]?diffusion", r"firefly", r"comfyui", r"automatic1111|a1111", r"novelai",
    r"leonardo\.ai|leonardo ai", r"ideogram", r"gemini|made with google ai|google ai",
]


# ---------------------------------------------------------------- utilidades
def _corr(a: np.ndarray, b: np.ndarray, se_degenerado: float = 0.0) -> float:
    a = a.astype(np.float64).ravel() - a.mean()
    b = b.astype(np.float64).ravel() - b.mean()
    d = math.sqrt(float((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d > 1e-12 else se_degenerado


def _quantil_hist(hist: np.ndarray, total: float, q: float) -> int:
    acumulado = np.cumsum(hist)
    indice = int(np.searchsorted(acumulado, q * total, side="left"))
    return min(indice, len(hist) - 1)


def _entropia_bits(hist: np.ndarray) -> float:
    total = hist.sum()
    if not total:
        return 0.0
    p = hist[hist > 0] / total
    return float(-(p * np.log2(p)).sum())


def _reta(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float]:
    n = len(xs)
    if n == 0:
        return 0.0, 0.0
    sx, sy, sxx, sxy = xs.sum(), ys.sum(), (xs * xs).sum(), (xs * ys).sum()
    den = n * sxx - sx * sx
    inclinacao = (n * sxy - sx * sy) / den if abs(den) > 1e-12 else 0.0
    return float(inclinacao), float((sy - inclinacao * sx) / n)


def _arredondar(x: np.ndarray) -> np.ndarray:
    """Arredonda como Math.round do JavaScript (0,5 sobe)."""
    return np.floor(x + 0.5)


# ---------------------------------------------------------------- medidas por recorte
def medidas_espectro(Y: np.ndarray) -> dict:
    n = Y.shape[0]
    nb = n // 2
    janela = 0.5 - 0.5 * np.cos(2 * np.pi * (np.arange(n) + 0.5) / n)
    F = np.fft.fft2((Y - Y.mean()) * janela[:, None] * janela[None, :])
    freq = np.fft.fftfreq(n)
    fv, fu = np.meshgrid(freq, freq, indexing="ij")
    raio = np.sqrt(fu * fu + fv * fv)
    valido = raio < 0.5
    valido[0, 0] = False
    faixa = np.minimum(nb - 1, np.floor(raio / 0.5 * nb)).astype(int)
    potencia = (F.real ** 2 + F.imag ** 2)
    log_p = np.log10(potencia + 1e-9)

    b = faixa[valido]
    contagem = np.bincount(b, minlength=nb).astype(np.float64)
    soma_p = np.bincount(b, weights=potencia[valido], minlength=nb)
    soma_l = np.bincount(b, weights=log_p[valido], minlength=nb)
    media_l = np.divide(soma_l, contagem, out=np.zeros(nb), where=contagem > 0)
    media_p = np.divide(soma_p, contagem, out=np.zeros(nb), where=contagem > 0)
    centro = (np.arange(nb) + 0.5) / n

    def selecionar(lo: float, hi: float) -> np.ndarray:
        return np.nonzero((contagem > 0) & (centro >= lo) & (centro < hi))[0]

    f = {}
    s = selecionar(0.02, 0.45)
    f["fSlope"] = _reta(np.log10(centro[s]), media_l[s])[0]

    def energia(lo: float, hi: float) -> float:
        s = selecionar(lo, hi)
        return float(media_p[s].mean()) if len(s) else 1e-9

    e_baixa, e_media, e_alta = energia(0.02, 0.08), energia(0.08, 0.25), energia(0.25, 0.5)
    f["fHM"] = math.log10((e_alta + 1e-9) / (e_media + 1e-9))
    f["fML"] = math.log10((e_media + 1e-9) / (e_baixa + 1e-9))
    s = selecionar(0.05, 0.38)
    inclinacao, intercepto = _reta(np.log10(centro[s]), media_l[s])
    t = selecionar(0.43, 0.5)
    f["fTail"] = float((media_l[t] - (intercepto + inclinacao * np.log10(centro[t]))).mean()) if len(t) else 0.0

    residuo = (log_p - media_l[faixa])[valido & (raio >= 0.05)]
    k = min(20, residuo.size)
    f["fPeak"] = float(np.sort(residuo)[-k:].mean()) if k else 0.0
    angulo = np.abs(np.arctan2(fv, fu)) % (np.pi / 2)
    angulo = np.where(angulo > np.pi / 4, np.pi / 2 - angulo, angulo)
    longe = valido & (raio >= 0.1)
    eixo, diagonal = longe & (angulo < np.pi / 12), longe & (angulo >= np.pi / 6)
    f["fAniso"] = float(log_p[eixo].mean() - log_p[diagonal].mean()) if eixo.any() and diagonal.any() else 0.0
    return f


def _passa_alta(canal: np.ndarray) -> np.ndarray:
    saida = np.zeros_like(canal)
    soma = sum(canal[1 + dy:canal.shape[0] - 1 + dy, 1 + dx:canal.shape[1] - 1 + dx]
               for dy in (-1, 0, 1) for dx in (-1, 0, 1))
    saida[1:-1, 1:-1] = canal[1:-1, 1:-1] - soma / 9
    return saida


def medidas_recorte(rgb: np.ndarray) -> dict:
    """Medidas de um recorte quadrado n×n (RGB uint8)."""
    n = rgb.shape[0]
    R, G, B = (rgb[..., i].astype(np.float32) for i in range(3))
    Y = 0.299 * R + 0.587 * G + 0.114 * B
    f = medidas_espectro(Y.astype(np.float64))

    # ruído
    rR, rG, rB = _passa_alta(R), _passa_alta(G), _passa_alta(B)
    rY = 0.299 * rR + 0.587 * rG + 0.114 * rB
    miolo = rY[1:-1, 1:-1].astype(np.float64)
    m2, m4 = float((miolo ** 2).mean()), float((miolo ** 4).mean())
    f["nStd"] = math.log10(math.sqrt(m2) + 0.01)
    f["nKurt"] = math.log10(m4 / (m2 * m2) if m2 > 1e-6 else 3)
    nbx = (n - 2) // 8
    blocos_y = Y[1:1 + nbx * 8, 1:1 + nbx * 8].reshape(nbx, 8, nbx, 8).astype(np.float64)
    blocos_r = rY[1:1 + nbx * 8, 1:1 + nbx * 8].reshape(nbx, 8, nbx, 8).astype(np.float64)
    media_bloco = blocos_y.mean(axis=(1, 3)).ravel()
    desvio_bloco = np.sqrt(np.maximum(0, (blocos_r ** 2).mean(axis=(1, 3)) - blocos_r.mean(axis=(1, 3)) ** 2)).ravel()
    q10, q90 = np.quantile(desvio_bloco, [0.1, 0.9])
    f["nQ10"] = math.log10(q10 + 0.02)
    f["nSpread"] = math.log10((q90 + 0.02) / (q10 + 0.02))
    f["nSig"] = _corr(media_bloco, desvio_bloco)
    f["nCC"] = (_corr(rR[1:-1, 1:-1], rG[1:-1, 1:-1]) + _corr(rG[1:-1, 1:-1], rB[1:-1, 1:-1])) / 2

    # bordas (Sobel)
    Yd = Y.astype(np.float64)
    c = lambda dy, dx: Yd[1 + dy:n - 1 + dy, 1 + dx:n - 1 + dx]  # noqa: E731
    gx = c(-1, 1) + 2 * c(0, 1) + c(1, 1) - c(-1, -1) - 2 * c(0, -1) - c(1, -1)
    gy = c(1, -1) + 2 * c(1, 0) + c(1, 1) - c(-1, -1) - 2 * c(-1, 0) - c(-1, 1)
    mag = np.sqrt(gx * gx + gy * gy)
    total = mag.size
    hist = np.bincount(np.minimum(2047, mag.astype(np.int64)).ravel(), minlength=2048)
    f["gMean"] = math.log10(float(mag.mean()) + 0.1)
    f["gRatio"] = math.log10((_quantil_hist(hist, total, 0.99) + 1) / (_quantil_hist(hist, total, 0.5) + 1))
    f["gSharp"] = math.log10(float((mag > 120).sum()) / total + 0.001)
    forte = mag > 20
    if forte.sum() >= 50:
        ang = np.arctan2(gy[forte], gx[forte])
        ang = np.where(ang < 0, ang + np.pi, ang)
        orient = np.bincount(np.minimum(17, np.floor(ang / np.pi * 18).astype(int)), weights=mag[forte], minlength=18)
        f["gOrient"] = _entropia_bits(orient) / math.log2(18)
    else:
        f["gOrient"] = 1.0

    # textura
    Yr = np.clip(_arredondar(Y), 0, 255).astype(np.int32)
    centro = Yr[1:-1, 1:-1]
    viz = lambda dy, dx: Yr[1 + dy:n - 1 + dy, 1 + dx:n - 1 + dx]  # noqa: E731
    lbp = ((viz(-1, -1) >= centro) * 1 | (viz(-1, 0) >= centro) * 2 | (viz(-1, 1) >= centro) * 4
           | (viz(0, 1) >= centro) * 8 | (viz(1, 1) >= centro) * 16 | (viz(1, 0) >= centro) * 32
           | (viz(1, -1) >= centro) * 64 | (viz(0, -1) >= centro) * 128)
    f["tLBP"] = _entropia_bits(np.bincount(lbp.ravel(), minlength=256)) / 8
    nb16 = n // 16
    b16 = Yd[:nb16 * 16, :nb16 * 16].reshape(nb16, 16, nb16, 16)
    variancias = np.maximum(0, (b16 ** 2).mean(axis=(1, 3)) - b16.mean(axis=(1, 3)) ** 2).ravel()
    vm = variancias.mean()
    f["tVarCV"] = math.log10((variancias.std() / vm if vm > 1e-9 else 0) + 0.1)
    f["tSmooth"] = float((variancias < 4).mean())
    h256 = np.bincount(Yr.ravel(), minlength=256)
    f["tEnt"] = _entropia_bits(h256) / 8

    # compressão
    dh = np.abs(np.diff(Yd, axis=1))
    dv = np.abs(np.diff(Yd, axis=0))
    borda_h = (np.arange(n - 1) % 8) == 7
    soma_b = dh[:, borda_h].sum() + dv[borda_h, :].sum()
    cont_b = dh[:, borda_h].size + dv[borda_h, :].size
    soma_i = dh[:, ~borda_h].sum() + dv[~borda_h, :].sum()
    cont_i = dh[:, ~borda_h].size + dv[~borda_h, :].size
    f["mBlock"] = math.log10((soma_b / cont_b + 0.05) / (soma_i / cont_i + 0.05))
    acum = np.cumsum(h256)
    lo = int(np.searchsorted(acum, n * n * 0.01, side="left"))
    hi = int(np.searchsorted(acum, n * n * 0.99, side="left"))
    vazios = int((h256[lo + 1:hi] == 0).sum())
    f["mEmpty"] = vazios / (hi - lo + 1) if hi - lo >= 20 else 0.0
    return f


# ---------------------------------------------------------------- medidas globais e de radiografia
def medidas_globais(rgb: np.ndarray) -> dict:
    r, g, b = (rgb[..., i].astype(np.float64).ravel() for i in range(3))
    mx, mn = np.maximum(np.maximum(r, g), b), np.minimum(np.minimum(r, g), b)
    sat = np.divide(mx - mn, mx, out=np.zeros_like(mx), where=mx > 0)
    rg, yb = r - g, 0.5 * (r + g) - b
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return {
        "cSat": float(sat.mean()),
        "cSatSd": float(sat.std()),
        "cColorful": (math.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * math.sqrt(rg.mean() ** 2 + yb.mean() ** 2)) / 100,
        "cDark": math.log10(float((mx <= 3).mean()) + 0.001),
        "cBright": math.log10(float((mn >= 252).mean()) + 0.001),
        "cContrast": float(y.std()) / 255,
        "cMean": float(y.mean()) / 255,
        "cChanCorr": (_corr(r, g, 1.0) + _corr(g, b, 1.0)) / 2,
    }


def _suavizar_caixa(src: np.ndarray, iteracoes: int) -> np.ndarray:
    a = src.astype(np.float32)
    for _ in range(iteracoes):
        p = np.pad(a, ((0, 0), (1, 1)), mode="edge")
        a = (p[:, :-2] + p[:, 1:-1] + p[:, 2:]) / 3
        p = np.pad(a, ((1, 1), (0, 0)), mode="edge")
        a = (p[:-2] + p[1:-1] + p[2:]) / 3
    return a


def _otsu3(hist: np.ndarray, total: int) -> tuple[int, int]:
    P = np.concatenate([[0.0], np.cumsum(hist, dtype=np.float64)])
    Sx = np.concatenate([[0.0], np.cumsum(np.arange(256) * hist, dtype=np.float64)])
    media_total = Sx[256] / total
    t1 = np.arange(1, 254)[:, None]
    t2 = np.arange(2, 255)[None, :]
    with np.errstate(divide="ignore", invalid="ignore"):
        w0 = P[t1 + 1] / total
        m0 = Sx[t1 + 1] / P[t1 + 1]
        c1 = P[t2 + 1] - P[t1 + 1]
        c2 = total - P[t2 + 1]
        m1 = (Sx[t2 + 1] - Sx[t1 + 1]) / c1
        m2 = (Sx[256] - Sx[t2 + 1]) / c2
        v = w0 * (m0 - media_total) ** 2 + (c1 / total) * (m1 - media_total) ** 2 + (c2 / total) * (m2 - media_total) ** 2
    valido = (t2 > t1) & (w0 > 0) & (c1 > 0) & (c2 > 0)
    v = np.where(valido, v, -np.inf)
    if not np.isfinite(v).any():
        return 85, 170
    i, j = np.unravel_index(int(np.argmax(v)), v.shape)
    return int(t1[i, 0]), int(t2[0, j])


def medidas_radiografia(rgb: np.ndarray) -> dict:
    h, w = rgb.shape[:2]
    total = w * h
    r, g, b = (rgb[..., i].astype(np.float64) for i in range(3))
    Y = np.floor(0.299 * r + 0.587 * g + 0.114 * b + 0.5).clip(0, 255).astype(np.int64)
    f = {"rColorDev": math.log10(float(((np.abs(r - g) + np.abs(g - b)) * 0.5).mean()) / 255 + 0.001)}
    hist = np.bincount(Y.ravel(), minlength=256)
    q = lambda p: _quantil_hist(hist, total, p) / 255  # noqa: E731
    f["rP5"], f["rP50"], f["rP95"] = q(0.05), q(0.5), q(0.95)
    f["rRange"] = f["rP95"] - f["rP5"]
    f["rExtremes"] = float(hist[:20].sum() + hist[236:].sum()) / total

    sm = _suavizar_caixa(Y, 3)
    hs = np.bincount(np.clip(_arredondar(sm), 0, 255).astype(np.int64).ravel(), minlength=256)
    t1, t2 = _otsu3(hs, total)
    classe = np.where(sm <= t1, 0, np.where(sm <= t2, 1, 2))
    for k, nome in enumerate(("rFracDark", "rFracMid", "rFracBright")):
        f[nome] = float((classe == k).mean())
    media_classe = lambda k: float(sm[classe == k].mean()) / 255 if (classe == k).any() else 0.0  # noqa: E731
    f["rToothBone"] = media_classe(2) - media_classe(1)

    rotulos, quantidade = ndimage.label(sm > t2)  # vizinhança de 4, como no original
    dim = max(w, h)
    componentes = []
    if quantidade:
        areas = np.bincount(rotulos.ravel(), minlength=quantidade + 1)
        objetos = ndimage.find_objects(rotulos)
        for ident in range(1, quantidade + 1):
            if areas[ident] < total * 0.004:
                continue
            fatia = objetos[ident - 1]
            ys, xs = np.nonzero(rotulos[fatia] == ident)
            ys = ys + fatia[0].start
            xs = xs + fatia[1].start
            componentes.append((ident, fatia, xs.astype(np.float64), ys.astype(np.float64)))
    f["rAreaMax"] = max((len(xs) / total for _, _, xs, _ in componentes), default=0.0)

    dentes = []
    for ident, fatia, xs, ys in componentes:
        cx, cy = xs.mean(), ys.mean()
        m20, m02 = (xs * xs).mean() - cx * cx, (ys * ys).mean() - cy * cy
        m11 = (xs * ys).mean() - cx * cy
        d = math.sqrt(((m20 - m02) / 2) ** 2 + m11 * m11)
        tr = (m20 + m02) / 2
        l1, l2 = tr + d, max(1e-6, tr - d)
        alongamento = min(20.0, math.sqrt(l1 / l2))
        if alongamento < 1.5:
            continue
        theta = 0.5 * math.atan2(2 * m11, m20 - m02)
        dentes.append((ident, fatia, len(xs), alongamento, theta, 4 * math.sqrt(l1) / dim, 4 * math.sqrt(l2) / dim))
    f["rNComp"] = float(len(dentes))
    if not dentes:
        f.update(rElong=0.0, rWidth=0.0, rLength=0.0, rTilt=0.5, rTiltSd=1.0, rRootSplit=0.0)
        return f

    def pontas(mascara: np.ndarray) -> int:
        ocupado = mascara.any(axis=0).astype(np.int8)
        bordas = np.diff(np.concatenate([[0], ocupado, [0]]))
        inicios, fins = np.nonzero(bordas == 1)[0], np.nonzero(bordas == -1)[0]
        return int(((fins - inicios) >= 3).sum())

    soma_w = sum(dn[2] for dn in dentes)
    el = wid = comp = incl = cr = sr = div = 0.0
    for ident, fatia, area, alongamento, theta, comprimento, largura in dentes:
        el += area * math.log10(alongamento)
        wid += area * largura
        comp += area * comprimento
        incl += area * abs(math.pi / 2 - abs(theta)) / (math.pi / 2)
        cr += area * math.cos(2 * theta)
        sr += area * math.sin(2 * theta)
        mascara = rotulos[fatia] == ident
        terco = max(1, mascara.shape[0] // 3)
        div += area * max(pontas(mascara[:terco]), pontas(mascara[-terco:]))
    f.update(rElong=el / soma_w, rWidth=wid / soma_w, rLength=comp / soma_w, rTilt=incl / soma_w,
             rTiltSd=1 - math.sqrt(cr * cr + sr * sr) / soma_w, rRootSplit=div / soma_w)
    return f


# ---------------------------------------------------------------- arquivo e extração completa
def medidas_arquivo(dados: bytes, imagem: Image.Image) -> dict:
    w, h = imagem.size
    texto = dados[:262_144].decode("latin-1") + dados[-65_536:].decode("latin-1")
    try:
        exif = imagem.getexif()
        tem_camera = bool(exif.get(0x010F) or exif.get(0x0110))
    except Exception:  # EXIF corrompido não deve derrubar a extração
        tem_camera = False
    return {
        "aLogMP": math.log2(w * h / 1e6),
        "aAspect": math.log2(w / h),
        "aDiv64": 1.0 if w % 64 == 0 and h % 64 == 0 else 0.0,
        "aBpp": math.log10(len(dados) / (w * h)),
        "aIsPng": 1.0 if dados[:4] == b"\x89PNG" else 0.0,
        "aIsJpeg": 1.0 if dados[:2] == b"\xff\xd8" else 0.0,
        "aExifCam": 1.0 if tem_camera else 0.0,
        "aAiMeta": 1.0 if any(re.search(p, texto, re.IGNORECASE) for p in PADROES_IA) else 0.0,
    }


def _posicoes_recorte(w: int, h: int, lado: int) -> list[tuple[int, int]]:
    posicoes, vistos = [], set()
    for fx, fy in [(0.5, 0.5), (0.2, 0.25), (0.8, 0.3), (0.35, 0.8)]:
        x = max(0, min(w - lado, int(_arredondar(np.array(fx * (w - lado) / 8))) * 8))
        y = max(0, min(h - lado, int(_arredondar(np.array(fy * (h - lado) / 8))) * 8))
        if (x, y) not in vistos:
            vistos.add((x, y))
            posicoes.append((x, y))
    return posicoes


def abrir_rgb_fundo_branco(dados: bytes) -> Image.Image:
    with Image.open(io.BytesIO(dados)) as bruta:
        bruta.load()
        imagem = ImageOps.exif_transpose(bruta)
        if imagem.mode in ("RGBA", "LA", "P"):
            imagem = imagem.convert("RGBA")
            fundo = Image.new("RGBA", imagem.size, (255, 255, 255, 255))
            imagem = Image.alpha_composite(fundo, imagem)
        if imagem.mode in ("I;16", "I;16L", "I;16B", "I"):
            m = np.asarray(imagem, dtype=np.float64)
            m = (m - m.min()) / max(1e-9, m.max() - m.min()) * 255
            imagem = Image.fromarray(m.astype(np.uint8))
        return imagem.convert("RGB")


def extrair_medidas(dados: bytes) -> dict:
    """Todas as medidas de uma imagem (bytes do arquivo) -> dict nome -> valor."""
    try:
        imagem = abrir_rgb_fundo_branco(dados)
    except (OSError, ValueError, Image.DecompressionBombError) as erro:
        raise RuntimeError(f"Não foi possível abrir a imagem: {erro}") from erro
    w, h = imagem.size
    if min(w, h) < 64:
        raise ValueError("imagem com menos de 64 px de lado")
    lado = 256
    if min(w, h) < 256:
        lado = 64
        while lado * 2 <= min(w, h):
            lado *= 2
    rgb = np.asarray(imagem)
    por_recorte = [medidas_recorte(rgb[y:y + lado, x:x + lado]) for x, y in _posicoes_recorte(w, h, lado)]
    medidas = {k: float(np.mean([m[k] for m in por_recorte])) for k in por_recorte[0]}
    escala = min(1.0, 512 / max(w, h))
    reduzida = imagem.resize((max(8, round(w * escala)), max(8, round(h * escala))), Image.Resampling.LANCZOS)
    rgb_reduzida = np.asarray(reduzida)
    medidas.update(medidas_globais(rgb_reduzida))
    medidas.update(medidas_radiografia(rgb_reduzida))
    medidas.update(medidas_arquivo(dados, imagem))
    return {k: (v if math.isfinite(v) else 0.0) for k, v in medidas.items()}


# ---------------------------------------------------------------- modelo
def _sigmoide(t: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(t, -30, 30)))


def ajustar_logistica(X: np.ndarray, y: np.ndarray, lam: float, pisos: np.ndarray) -> dict:
    """Regressão logística L2 (Newton), classes com o mesmo peso total, z-scores cortados em ±5."""
    media = X.mean(axis=0)
    desvio = np.maximum(X.std(axis=0), pisos)
    manter = desvio > 1e-9
    Z = np.clip((X[:, manter] - media[manter]) / desvio[manter], -ZCLIP, ZCLIP)
    Z = np.hstack([np.ones((len(Z), 1)), Z])
    n, n1 = len(y), int(y.sum())
    pesos = np.where(y == 1, n / (2 * n1), n / (2 * (n - n1)))
    w = np.zeros(Z.shape[1])
    for _ in range(60):
        p = _sigmoide(Z @ w)
        g = Z.T @ (pesos * (y - p))
        H = (Z * (pesos * p * (1 - p))[:, None]).T @ Z
        g[1:] -= lam * w[1:]
        H[np.arange(1, len(w)), np.arange(1, len(w))] += lam
        H[0, 0] += 1e-6
        passo = np.clip(np.linalg.solve(H, g), -3, 3)
        w += passo
        if np.abs(passo).max() < 1e-6:
            break
    return {"media": media, "desvio": desvio, "manter": manter, "w": w}


def logito(modelo: dict, X: np.ndarray) -> np.ndarray:
    m = modelo["manter"]
    Z = np.clip((X[:, m] - modelo["media"][m]) / modelo["desvio"][m], -ZCLIP, ZCLIP)
    return modelo["w"][0] + Z @ modelo["w"][1:]


def _dobras(y: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    dobra = np.zeros(len(y), dtype=int)
    for classe in (0, 1):
        indices = np.nonzero(y == classe)[0]
        rng.shuffle(indices)
        dobra[indices] = np.arange(len(indices)) % k
    return dobra


def logitos_fora_da_dobra(X, y, lam, k, repeticoes, semente, pisos) -> np.ndarray:
    rng = np.random.default_rng(semente)
    acumulado = np.zeros(len(y))
    for _ in range(repeticoes):
        dobra = _dobras(y, k, rng)
        for d in range(k):
            teste = dobra == d
            modelo = ajustar_logistica(X[~teste], y[~teste], lam, pisos)
            acumulado[teste] += logito(modelo, X[teste])
    return acumulado / repeticoes


def perda_log_balanceada(l: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(_sigmoide(l), 1e-9, 1 - 1e-9)
    return float((-np.log(p[y == 1]).mean() - np.log(1 - p[y == 0]).mean()) / 2)


def auc(scores: np.ndarray, y: np.ndarray) -> float:
    from scipy.stats import rankdata
    n1, n0 = int(y.sum()), int(len(y) - y.sum())
    if not n1 or not n0:
        return float("nan")
    return float((rankdata(scores)[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def ajustar_platt(l: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    n, n1 = len(y), int(y.sum())
    pesos = np.where(y == 1, n / (2 * n1), n / (2 * (n - n1)))
    a, b = 1.0, 0.0
    for _ in range(50):
        p = _sigmoide(a * l + b)
        r, q = pesos * (y - p), pesos * p * (1 - p)
        g0, g1 = (r * l).sum(), r.sum()
        h00, h01, h11 = (q * l * l).sum() + 1e-6 + 1e-3, (q * l).sum(), q.sum() + 1e-6
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:
            break
        da, db = (h11 * g0 - h01 * g1) / det, (-h01 * g0 + h00 * g1) / det
        a, b = a + da, b + db
        if abs(da) + abs(db) < 1e-7:
            break
    return float(min(2.0, max(0.05, a))), float(b)


def treinar(X: np.ndarray, y: np.ndarray, chaves: list[str], semente: int = 7) -> dict:
    y = y.astype(np.float64)
    n1, n0 = int(y.sum()), int(len(y) - y.sum())
    if n1 < 6 or n0 < 6:
        raise ValueError(f"São necessárias pelo menos 6 imagens de cada classe (há {n1} de IA e {n0} reais).")
    pisos = np.array([PISO_DESVIO.get(k, 0.02) for k in chaves])
    k = max(2, min(5, n1, n0))
    melhor = min(LAMBDAS, key=lambda lam: perda_log_balanceada(
        logitos_fora_da_dobra(X, y, lam, k, 1, semente, pisos), y))
    oof = logitos_fora_da_dobra(X, y, melhor, k, 3, semente + 14, pisos)
    a, b = ajustar_platt(oof, y)
    calibrado = a * oof + b
    modelo = ajustar_logistica(X, y, melhor, pisos)
    z = np.clip((X[:, modelo["manter"]] - modelo["media"][modelo["manter"]]) / modelo["desvio"][modelo["manter"]],
                -ZCLIP, ZCLIP)
    ood = np.sort((z ** 2).mean(axis=1))
    limiar_ood = float(ood[min(len(ood) - 1, int(0.975 * len(ood)))] * 1.3 + 0.2)
    previsto = calibrado > 0
    return {
        "versao_medidas": VERSAO_MEDIDAS, "chaves": chaves, "lambda": melhor, "platt": [a, b],
        "limiar_ood": limiar_ood, "media": modelo["media"].tolist(), "desvio": modelo["desvio"].tolist(),
        "manter": modelo["manter"].tolist(), "w": modelo["w"].tolist(),
        "validacao_cruzada": {
            "auc": auc(calibrado, y), "acerto": float((previsto == (y == 1)).mean()),
            "fpr_reais": float(previsto[y == 0].mean()), "recall_ia": float(previsto[y == 1].mean()),
            "n_ia": n1, "n_reais": n0,
        },
    }


def probabilidade(modelo_salvo: dict, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Probabilidade de IA e indicador 'fora do padrão do treino' para cada linha de X."""
    modelo = {"media": np.array(modelo_salvo["media"]), "desvio": np.array(modelo_salvo["desvio"]),
              "manter": np.array(modelo_salvo["manter"], dtype=bool), "w": np.array(modelo_salvo["w"])}
    a, b = modelo_salvo["platt"]
    m = modelo["manter"]
    z = np.clip((X[:, m] - modelo["media"][m]) / modelo["desvio"][m], -ZCLIP, ZCLIP)
    return _sigmoide(a * logito(modelo, X) + b), (z ** 2).mean(axis=1) > modelo_salvo["limiar_ood"]


def chaves_dos_grupos(grupos: list[str]) -> list[str]:
    desconhecidos = set(grupos) - set(GRUPOS)
    if desconhecidos:
        raise ValueError(f"Grupos desconhecidos: {', '.join(sorted(desconhecidos))}. Opções: {', '.join(GRUPOS)}")
    return [k for g in grupos for k in GRUPOS[g]]


def matriz(medidas: list[dict], chaves: list[str]) -> np.ndarray:
    return np.array([[m.get(k, 0.0) for k in chaves] for m in medidas], dtype=np.float64)
