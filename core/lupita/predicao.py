"""Análise de uma imagem e treino do modelo, sem tocar em banco nem em Streamlit."""
from __future__ import annotations

import hashlib
import io
from collections import defaultdict

import numpy as np
from PIL import Image

from core.lupita import explicacao as E
from core.lupita import motor as L

# Ordem fixa das 56 medidas (é a ordem do array `medidas` no banco).
CHAVES_TODAS: list[str] = [k for g in L.GRUPOS for k in L.GRUPOS[g]]

# Grupos ligados por padrão: os 5 do modelo de referência (38 medidas, acerto 96%, AUC 0,988).
# Compressão, Cor e Arquivo ficam de fora (ver seção 7.1 da documentação da Lupita): print e
# recompressão derrubam essas medidas, e o tamanho da imagem não pode virar parâmetro.
GRUPOS_MODELO = ["freq", "noise", "edges", "texture", "radio"]

NOMES_GRUPOS = {"freq": "Frequências", "noise": "Ruído", "edges": "Bordas", "texture": "Textura",
                "compress": "Compressão", "color": "Cor", "radio": "Radiografia", "file": "Arquivo"}

EXTENSOES_ACEITAS = ["png", "jpg", "jpeg", "bmp", "tif", "tiff", "webp"]
TAMANHO_MAXIMO_BYTES = 25 * 1024 * 1024


def hash_imagem(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def medidas_em_lista(medidas: dict) -> list[float]:
    """dict de medidas -> lista de 56 floats na ordem de CHAVES_TODAS (o que vai pro banco)."""
    return [round(float(medidas.get(k, 0.0)), 6) for k in CHAVES_TODAS]


def lista_em_medidas(valores) -> dict:
    return dict(zip(CHAVES_TODAS, valores))


def analisar(modelo: dict, dados: bytes) -> dict:
    """Mede a imagem e aplica o modelo.

    Devolve {'prob', 'fora_do_padrao', 'grupos': {nome: contribuição}, 'medidas': [56 floats]}.
    Contribuição de cada medida = a·w·z (a = Platt); somada por grupo. Positiva empurra pra IA.
    """
    if modelo.get("versao_medidas") != L.VERSAO_MEDIDAS:
        raise ValueError("O modelo foi treinado com outra versão das medidas. Treine de novo.")
    medidas = L.extrair_medidas(dados)
    X = L.matriz([medidas], modelo["chaves"])
    prob, fora = L.probabilidade(modelo, X)
    manter = np.array(modelo["manter"], dtype=bool)
    media, desvio = np.array(modelo["media"]), np.array(modelo["desvio"])
    z = np.clip((X[0, manter] - media[manter]) / desvio[manter], -L.ZCLIP, L.ZCLIP)
    contrib = modelo["platt"][0] * np.array(modelo["w"])[1:] * z
    chaves = np.array(modelo["chaves"])[manter]
    grupo_de = {k: g for g in L.GRUPOS for k in L.GRUPOS[g]}
    soma: dict[str, float] = defaultdict(float)
    for k, c in zip(chaves, contrib):
        soma[NOMES_GRUPOS.get(grupo_de.get(k, ""), "Outros")] += float(c)
    largura, altura = _tamanho(dados)
    return {"prob": float(prob[0]), "fora_do_padrao": bool(fora[0]), "grupos": dict(soma),
            "medidas": medidas_em_lista(medidas), "largura": largura, "altura": altura,
            "sinais": E.sinais_principais(modelo, medidas),
            "radiografia": E.descricao_radiografia(medidas, largura, altura)}


def _tamanho(dados: bytes) -> tuple[int, int]:
    """Largura e altura como a Lupita enxerga (com a rotação do EXIF), lendo só o cabeçalho."""
    with Image.open(io.BytesIO(dados)) as im:
        w, h = im.size
        try:
            if im.getexif().get(0x0112) in (5, 6, 7, 8):
                w, h = h, w
        except Exception:  # EXIF corrompido não pode derrubar a análise
            pass
    return w, h


def treinar_de_linhas(medidas_listas: list[list[float]], rotulos: list[int],
                      grupos: list[str] | None = None) -> dict:
    """Treina a partir de linhas já lidas (cada uma com as 56 medidas na ordem de CHAVES_TODAS)."""
    grupos = grupos or GRUPOS_MODELO
    chaves = L.chaves_dos_grupos(grupos)
    X = L.matriz([lista_em_medidas(v) for v in medidas_listas], chaves)
    y = np.array([1.0 if r else 0.0 for r in rotulos])
    modelo = L.treinar(X, y, chaves)
    modelo["grupos"] = grupos
    modelo["media_ia"], modelo["media_real"] = E.medias_por_classe(X, y)
    return modelo
