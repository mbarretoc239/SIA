"""Textos de explicação da Lupita: veredito, principais sinais e descrição da radiografia.

Porta do que o artefato do navegador mostra (verdict, signalLi, measuresHtml), sem Streamlit.
"""
from __future__ import annotations

import math

import numpy as np

from core.lupita import motor as L
from core.lupita.catalogo import FEAT, GRUPOS_INFO

LIMIAR_SINAL = 0.08   # |contribuição| mínima pra uma medida aparecer em "principais sinais"
SINAIS_POR_LADO = 3


def nf(v: float, casas: int) -> str:
    """Número no formato brasileiro (vírgula decimal)."""
    return f"{v:.{casas}f}".replace(".", ",")


def pct(v: float) -> str:
    return f"{round(v * 100)}%"


def veredito(p: float, fora_do_padrao: bool = False) -> tuple[str, str]:
    """(texto, tom) com tom em {'ia', 'mid', 'real', 'fora'}. Fora do padrão tem prioridade."""
    if fora_do_padrao:
        return "Fora do padrão do treino", "fora"
    if p >= 0.90:
        return "Muito provavelmente IA", "ia"
    if p >= 0.70:
        return "Provavelmente IA", "ia"
    if p >= 0.55:
        return "Tende a ser IA", "ia"
    if p > 0.45:
        return "Inconclusivo", "mid"
    if p > 0.30:
        return "Tende a ser real", "real"
    if p > 0.10:
        return "Provavelmente real", "real"
    return "Muito provavelmente real", "real"


def percentual_texto(p: float) -> str:
    if p > 0.995:
        return ">99%"
    if p < 0.005:
        return "<1%"
    return f"{round(p * 100)}%"


def _tripla(chave: str, v: float, m1: float, m0: float) -> tuple[str, str, str]:
    casas = FEAT[chave]["casas"]
    if casas == 0:
        return ("sim" if v >= 0.5 else "não"), pct(m1), pct(m0)
    while casas < 4 and nf(m1, casas) == nf(m0, casas):
        casas += 1
    return nf(v, casas), nf(m1, casas), nf(m0, casas)


def sinais_principais(modelo: dict, medidas: dict) -> dict:
    """{'ia': [...], 'real': [...]}: até 3 medidas de cada lado que mais pesaram.

    Cada item: rotulo, grupo, contribuicao, frase, esta_imagem, media_ia, media_reais
    (as médias só existem em modelos treinados depois desta versão da tela).
    """
    chaves = modelo["chaves"]
    manter = np.array(modelo["manter"], dtype=bool)
    media, desvio = np.array(modelo["media"]), np.array(modelo["desvio"])
    X = L.matriz([medidas], chaves)[0]
    z = np.clip((X[manter] - media[manter]) / desvio[manter], -L.ZCLIP, L.ZCLIP)
    contrib = modelo["platt"][0] * np.array(modelo["w"])[1:] * z
    kept = [k for k, m in zip(chaves, manter) if m]
    idx_todas = {k: i for i, k in enumerate(chaves)}
    m_ia, m_real = modelo.get("media_ia"), modelo.get("media_real")

    itens = []
    for k, c, zz in zip(kept, contrib, z):
        info = FEAT[k]
        item = {"chave": k, "rotulo": info["rotulo"], "grupo": GRUPOS_INFO[info["grupo"]][0],
                "contribuicao": float(c), "frase": info["alto"] if zz >= 0 else info["baixo"]}
        if m_ia is not None and m_real is not None:
            i = idx_todas[k]
            v, a, b = _tripla(k, float(X[idx_todas[k]]), float(m_ia[i]), float(m_real[i]))
            item.update(esta_imagem=v, media_ia=a, media_reais=b)
        itens.append(item)
    ia = sorted((i for i in itens if i["contribuicao"] > LIMIAR_SINAL), key=lambda i: -i["contribuicao"])
    real = sorted((i for i in itens if i["contribuicao"] < -LIMIAR_SINAL), key=lambda i: i["contribuicao"])
    return {"ia": ia[:SINAIS_POR_LADO], "real": real[:SINAIS_POR_LADO]}


def descricao_radiografia(f: dict, largura: int, altura: int) -> list[tuple[str, str]]:
    """Linhas (título, texto) com o que as medidas dizem sobre a radiografia, em linguagem simples."""
    desvio_cor = max(0.0, 10 ** f["rColorDev"] - 0.001)
    cinza = ("escala de cinza pura" if desvio_cor < 0.012
             else f"tem cor (desvio médio de {nf(desvio_cor * 100, 1)}% entre canais)")
    pb = ("aspecto preto e branco, com mais da metade dos pixels nos extremos"
          if f["rExtremes"] > 0.5 else "tons contínuos de cinza")
    n = f["rNComp"]
    plural = "s" if n >= 1.5 else ""
    dentes = (f"{nf(n, 0)} estrutura{plural} densa{plural} alongada{plural} (candidatas a dentes), "
              f"largura média {pct(f['rWidth'])} e comprimento médio {pct(f['rLength'])} do lado maior da imagem"
              if n >= 1 else "nenhuma estrutura densa alongada detectada")
    return [
        ("Pixels", f"{largura}×{altura} ({nf(largura * altura / 1e6, 2)} MP)"),
        ("Escala de cinza", f"{cinza}; {pb}"),
        ("Intensidade", f"mediana {pct(f['rP50'])}; pretos em {pct(f['rP5'])} e brancos em {pct(f['rP95'])} "
                        f"(faixa de {pct(f['rRange'])})"),
        ("Densidade", f"baixa {pct(f['rFracDark'])} · média {pct(f['rFracMid'])} · alta {pct(f['rFracBright'])} da área"),
        ("Dentes (estimativa)", dentes),
        ("Inclinação", (f"eixo {nf(f['rTilt'] * 90, 0)}° da vertical; variação entre dentes {nf(f['rTiltSd'], 2)} "
                        "(0 = paralelos)") if n >= 1 else "–"),
        ("Pontas (raízes, estimativa)", (f"{nf(f['rRootSplit'], 1)} por estrutura densa, contando divisões nos "
                                         "terços de cima e de baixo") if n >= 1 else "–"),
    ]


def medias_por_classe(X: np.ndarray, y: np.ndarray) -> tuple[list[float], list[float]]:
    """Média de cada medida nas imagens de IA e nas reais do treino (pra comparar na tela)."""
    ia, real = X[y == 1].mean(axis=0), X[y == 0].mean(axis=0)
    return [float(v) if math.isfinite(v) else 0.0 for v in ia], [float(v) if math.isfinite(v) else 0.0 for v in real]
