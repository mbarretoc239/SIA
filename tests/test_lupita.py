"""Lupita: acesso restrito, travas de egress, motor e paridade com o navegador.

Os testes de paridade usam o pacote de referência da Lupita (imagens reais do SIGO NÃO ficam no
repositório). Rode com LUPITA_REFERENCIA=<pasta lupita_pacote> para ativá-los; sem isso são pulados.
"""
import io
import json
import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from core.lupita import dados as D
from core.lupita import motor as L
from core.lupita import predicao as P
from core.lupita.acesso import AcessoNegado, exigir_acesso, usuario_liberado

RAIZ = Path(__file__).resolve().parent.parent


def _repo(usuario="MATHBC", role=None, usuario_id="u-ok"):
    db = MagicMock()
    db.supabase_url = "https://exemplo.supabase.co"
    db._admin_headers.return_value = {"apikey": "srv", "Authorization": "Bearer srv", "Prefer": "return=minimal"}
    return D.LupitaRepo(db, usuario, role, usuario_id)


def _resposta(corpo, status=200, headers=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = corpo
    r.text = json.dumps(corpo)
    r.headers = headers or {}
    return r


# ---------------------------------------------------------------- acesso (módulo "lupita" em Permissões)
EXCECOES = [
    {"usuario_id": "u-ok", "modulo": "lupita", "habilitado": True},
    {"usuario_id": "u-bloq", "modulo": "lupita", "habilitado": False},
    {"usuario_id": "u-outro-modulo", "modulo": "amostragem", "habilitado": True},
]
PERMISSOES = [{"modulo": "lupita", "role": "Gestor", "habilitado": True},
              {"modulo": "lupita", "role": "CISO", "habilitado": False}]


@pytest.fixture(autouse=True)
def _permissoes_falsas():
    with patch("core.lupita.acesso._carregar_permissoes", return_value=(PERMISSOES, EXCECOES)):
        yield


def test_excecao_individual_libera():
    assert usuario_liberado("X", "Auditor", "u-ok")


@pytest.mark.parametrize("uid", [None, "", "u-nao-existe", "u-outro-modulo"])
def test_sem_excecao_do_modulo_nao_libera(uid):
    assert not usuario_liberado("X", "Auditor", uid)
    with pytest.raises(AcessoNegado):
        exigir_acesso("X", "Auditor", uid)


def test_liberacao_por_funcao():
    assert usuario_liberado("X", "Gestor", "u-qualquer")
    assert not usuario_liberado("X", "CISO", "u-qualquer")   # linha com habilitado=False
    assert not usuario_liberado("X", "Contas", "u-qualquer")  # sem linha: fechado


@pytest.mark.parametrize("role", ["Admin", "ADMIN", " admin "])
def test_admin_liberado_pelo_cargo(role):
    assert usuario_liberado("QUALQUER", role)
    exigir_acesso("QUALQUER", role)


def test_excecao_bloquear_vale_ate_para_admin():
    assert not usuario_liberado("X", "Admin", "u-bloq")


@pytest.mark.parametrize("role", ["Auditor", "Contas", "", None])
def test_outros_cargos_nao_liberam_sozinhos(role):
    assert not usuario_liberado("OUTRO", role)


def test_banco_de_permissoes_fora_do_ar_so_admin_passa():
    with patch("core.lupita.acesso._carregar_permissoes", side_effect=ConnectionError("fora")):
        assert usuario_liberado("X", "Admin", "u-ok")
        assert not usuario_liberado("X", "Auditor", "u-ok")
        assert not usuario_liberado("X", "Gestor", None)


def test_modulo_aparece_em_configuracoes():
    from core.settings import MODULOS_CONTROLADOS
    assert "lupita" in MODULOS_CONTROLADOS


def test_repo_de_admin_chega_ao_banco():
    repo = _repo("QUALQUER", "Admin")
    with patch("core.lupita.dados.requests.get", return_value=_resposta([])) as get:
        repo.versao_ativa()
    assert get.called


def test_repo_de_usuario_nao_liberado_nao_chega_ao_banco():
    repo = _repo("OUTRO", usuario_id="u-nao-existe")
    with patch("core.lupita.dados.requests") as req:
        with pytest.raises(AcessoNegado):
            repo.versao_ativa()
        with pytest.raises(AcessoNegado):
            repo.registrar_analise("h", [0.0] * 56, 0.5, False, {}, 1)
        with pytest.raises(AcessoNegado):
            repo.amostras_treino()
    assert not req.get.called and not req.post.called and not req.patch.called


# ---------------------------------------------------------------- egress
def test_leitura_sem_select_estrela_e_com_limit():
    for select, limite in [("*", 1), ("a,*", 1), ("", 1), ("a", 0), ("a", None)]:
        with pytest.raises(D.LeituraNaoPermitida):
            D._validar_leitura(select, limite, 1000)
    with pytest.raises(D.LeituraNaoPermitida):
        D._validar_leitura("a", 5000, 1000)


def test_ler_manda_limit_e_colunas():
    repo = _repo()
    with patch("core.lupita.dados.requests.get", return_value=_resposta([])) as get:
        repo.versao_ativa()
    params = get.call_args.kwargs["params"]
    assert params["limit"] == "1" and params["select"] == "versao"


def test_historico_nao_traz_colunas_pesadas_e_tem_teto():
    repo = _repo()
    with patch("core.lupita.dados.requests.get", return_value=_resposta([])) as get:
        repo.historico(limite=99999)
    params = get.call_args.kwargs["params"]
    assert "medidas" not in params["select"] and "contrib" not in params["select"]
    assert int(params["limit"]) <= 200


def test_escritas_pedem_return_minimal():
    repo = _repo()
    with patch("core.lupita.dados.requests.post", return_value=_resposta([], 201)) as post:
        repo.registrar_analise("h", [0.0] * 56, 0.5, False, {}, 1)
    assert "return=minimal" in post.call_args.kwargs["headers"]["Prefer"]
    with patch("core.lupita.dados.requests.patch", return_value=_resposta([], 204)) as patch_:
        repo.rotular("h", 1)
    assert "return=minimal" in patch_.call_args.kwargs["headers"]["Prefer"]


def test_treino_pagina_e_respeita_teto():
    repo = _repo()
    pagina = [{"rotulo": 1, "medidas": [0.0] * 56}] * 1000
    with patch("core.lupita.dados.requests.get", return_value=_resposta(pagina)) as get:
        medidas, rotulos = repo.amostras_treino(teto=2500)
    assert len(medidas) == 2500 and get.call_count == 3
    with pytest.raises(D.LeituraNaoPermitida):
        repo.amostras_treino(teto=D.TETO_AMOSTRAS_TREINO + 1)


def test_codigo_nao_usa_select_estrela():
    fonte = (RAIZ / "core" / "lupita" / "dados.py").read_text(encoding="utf-8")
    assert not re.search(r"select=\*|\"select\":\s*\"\*\"", fonte)


def test_app_nao_importa_lupita_no_topo():
    """Nada da Lupita pode rodar/ler banco em todo rerun do app inteiro."""
    for linha in (RAIZ / "app.py").read_text(encoding="utf-8").splitlines():
        assert not re.match(r"(from|import)\s+core\.lupita", linha)


def test_view_so_le_banco_por_cache_ou_acao():
    fonte = (RAIZ / "views" / "10_Lupita.py").read_text(encoding="utf-8")
    mini = (RAIZ / "core" / "lupita" / "mini.py").read_text(encoding="utf-8")
    assert "@st.cache_data" in mini and "@st.cache_resource" in mini   # caches vivem em mini.py
    assert "M.versao_ativa" in fonte and "M.modelo_da_versao" in fonte
    assert "repo.amostras_treino()" in fonte and "disabled=not ok" in fonte


# ---------------------------------------------------------------- motor
def _png_ruido(lado=128, semente=1) -> bytes:
    rng = np.random.default_rng(semente)
    arr = rng.integers(0, 256, (lado, lado, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG")
    return buf.getvalue()


def test_chaves():
    assert len(P.CHAVES_TODAS) == 56 and len(set(P.CHAVES_TODAS)) == 56


def test_extrai_56_medidas_de_bytes():
    m = L.extrair_medidas(_png_ruido())
    assert set(m) == set(P.CHAVES_TODAS) and all(np.isfinite(v) for v in m.values())


def test_imagem_pequena_e_recusada():
    with pytest.raises(ValueError, match="64 px"):
        L.extrair_medidas(_png_ruido(48))


def test_arquivo_invalido_vira_runtimeerror():
    with pytest.raises(RuntimeError):
        L.extrair_medidas(b"nao e imagem")


def _modelo_sintetico():
    rng = np.random.default_rng(0)
    n = 80
    y = np.array([1] * 40 + [0] * 40)
    X = rng.normal(0, 1, (n, 56)) + y[:, None] * 1.5
    return P.treinar_de_linhas(X.tolist(), y.tolist())


def test_treino_e_analise_ponta_a_ponta():
    modelo = _modelo_sintetico()
    assert modelo["grupos"] == P.GRUPOS_MODELO and len(modelo["chaves"]) == 38
    res = P.analisar(modelo, _png_ruido())
    assert 0.0 <= res["prob"] <= 1.0 and len(res["medidas"]) == 56
    assert set(res["grupos"]) <= set(P.NOMES_GRUPOS.values())


def test_treino_exige_6_de_cada_classe():
    with pytest.raises(ValueError, match="pelo menos 6"):
        P.treinar_de_linhas([[0.0] * 56] * 8, [1, 1, 1, 0, 0, 0, 0, 0])


# ---------------------------------------------------------------- paridade com o navegador
_REF = os.environ.get("LUPITA_REFERENCIA")
precisa_ref = pytest.mark.skipif(not _REF, reason="defina LUPITA_REFERENCIA=<pasta lupita_pacote>")


@precisa_ref
def test_paridade_radiografias_sigo_com_o_navegador():
    ref = json.loads((Path(_REF) / "referencia" / "medidas_referencia.json").read_text(encoding="utf-8"))
    sigo = [i for i in ref["imagens"] if "sigo_real" in i["arquivo"]]
    assert len(sigo) == 8
    for im in sigo:
        dados = (Path(_REF) / "referencia" / "imagens" / Path(im["arquivo"]).name).read_bytes()
        got = L.extrair_medidas(dados)
        for k, esperado in im["medidas"].items():
            assert got[k] == pytest.approx(esperado, rel=1e-3, abs=1e-4), (im["arquivo"], k)


@precisa_ref
def test_referencia_imagem_pequena_demais_e_recusada():
    dados = (Path(_REF) / "referencia" / "imagens" / "07_sintetica_muito_pequena_48x48.png").read_bytes()
    with pytest.raises(ValueError, match="64 px"):
        L.extrair_medidas(dados)


# ---------------------------------------------------------------- explicações
def test_catalogo_bate_com_o_motor():
    from core.lupita.catalogo import FEATURES, GRUPOS_INFO
    assert [f[0] for f in FEATURES] == P.CHAVES_TODAS
    assert set(GRUPOS_INFO) == set(L.GRUPOS)
    assert all(f[1] in GRUPOS_INFO and f[2] and f[3] and f[4] for f in FEATURES)


@pytest.mark.parametrize("p,texto,tom", [
    (0.95, "Muito provavelmente IA", "ia"), (0.90, "Muito provavelmente IA", "ia"),
    (0.75, "Provavelmente IA", "ia"), (0.60, "Tende a ser IA", "ia"),
    (0.50, "Inconclusivo", "mid"), (0.35, "Tende a ser real", "real"),
    (0.20, "Provavelmente real", "real"), (0.05, "Muito provavelmente real", "real"),
])
def test_veredito_faixas(p, texto, tom):
    from core.lupita import explicacao as E
    assert E.veredito(p) == (texto, tom)


def test_fora_do_padrao_tem_prioridade_no_veredito():
    from core.lupita import explicacao as E
    assert E.veredito(0.99, fora_do_padrao=True) == ("Fora do padrão do treino", "fora")


def test_percentual_texto_extremos():
    from core.lupita import explicacao as E
    assert E.percentual_texto(0.999) == ">99%" and E.percentual_texto(0.001) == "<1%"
    assert E.percentual_texto(0.874) == "87%"


def test_numero_em_formato_brasileiro():
    from core.lupita import explicacao as E
    assert E.nf(1.5, 2) == "1,50" and E.pct(0.256) == "26%"


def test_analise_traz_sinais_com_comparacao_e_descricao():
    modelo = _modelo_sintetico()
    assert len(modelo["media_ia"]) == len(modelo["chaves"]) == len(modelo["media_real"])
    res = P.analisar(modelo, _png_ruido())
    assert len(res["radiografia"]) == 7 and res["largura"] == res["altura"] == 128
    for lado in ("ia", "real"):
        assert len(res["sinais"][lado]) <= 3
        for s in res["sinais"][lado]:
            assert s["frase"] and {"esta_imagem", "media_ia", "media_reais"} <= set(s)
    assert all(s["contribuicao"] > 0 for s in res["sinais"]["ia"])
    assert all(s["contribuicao"] < 0 for s in res["sinais"]["real"])


def test_modelo_antigo_sem_medias_ainda_explica():
    modelo = _modelo_sintetico()
    modelo.pop("media_ia"), modelo.pop("media_real")
    res = P.analisar(modelo, _png_ruido())
    assert all("esta_imagem" not in s for s in res["sinais"]["ia"] + res["sinais"]["real"])


# ---------------------------------------------------------------- tela: atalho e colar
def test_tela_tem_atalho_synthid_e_colagem():
    fonte = (RAIZ / "views" / "10_Lupita.py").read_text(encoding="utf-8")
    mini = (RAIZ / "core" / "lupita" / "mini.py").read_text(encoding="utf-8")
    assert 'SYNTHID_URL = "https://synthid.com"' in mini and "st.link_button" in fonte
    # o ouvinte de colagem só age no uploader cujo rótulo traz esse marcador
    assert "cole com Ctrl+V" in mini.split("ROTULO_UPLOAD =")[1].split("\n")[0]
    assert "indexOf('cole com Ctrl+V')" in mini
    assert "components.html(_JS_COLAR" in fonte


# ---------------------------------------------------------------- "Não sei ao certo"
def test_incerta_grava_rotulo_nulo_e_flag():
    repo = _repo()
    with patch("core.lupita.dados.requests.patch", return_value=_resposta([], 204)) as patch_:
        repo.rotular("h", 1, incerto=True)   # mesmo que venha rotulo, incerta prevalece
    corpo = patch_.call_args.kwargs["json"]
    assert corpo["rotulo"] is None and corpo["incerto"] is True
    assert corpo["rotulado_por"] == "MATHBC" and corpo["rotulado_em"]


def test_rotular_normal_limpa_incerta_e_desfazer_zera_tudo():
    repo = _repo()
    with patch("core.lupita.dados.requests.patch", return_value=_resposta([], 204)) as patch_:
        repo.rotular("h", 0)
        corpo = patch_.call_args.kwargs["json"]
        assert corpo["rotulo"] == 0 and corpo["incerto"] is False and corpo["rotulado_por"] == "MATHBC"
        repo.rotular("h", None)
        corpo = patch_.call_args.kwargs["json"]
        assert corpo["rotulo"] is None and corpo["incerto"] is False
        assert corpo["rotulado_por"] is None and corpo["rotulado_em"] is None


def test_treino_le_so_rotulo_nao_nulo_entao_incerta_fica_de_fora():
    repo = _repo()
    with patch("core.lupita.dados.requests.get",
               return_value=_resposta([{"rotulo": 1, "medidas": [0.0] * 56}])) as get:
        repo.amostras_treino(teto=1000)
    assert get.call_args.kwargs["params"]["rotulo"] == "not.is.null"
    fonte = (RAIZ / "core" / "lupita" / "dados.py").read_text(encoding="utf-8")
    assert "rotulo,medidas" in fonte and "incerto" not in fonte.split("def amostras_treino")[1].split("def inserir")[0]


def test_historico_traz_flag_incerto_sem_colunas_pesadas():
    repo = _repo()
    with patch("core.lupita.dados.requests.get", return_value=_resposta([])) as get:
        repo.historico()
    sel = get.call_args.kwargs["params"]["select"]
    assert "incerto" in sel and "medidas" not in sel and "contrib" not in sel


def test_tela_tem_botao_nao_sei_ao_certo():
    fonte = (RAIZ / "views" / "10_Lupita.py").read_text(encoding="utf-8")
    assert "Não sei ao certo" in fonte and "incerto=True" in fonte and '"Incerta"' in fonte


def test_botao_incerta_esta_desligado_por_ora():
    fonte = (RAIZ / "views" / "10_Lupita.py").read_text(encoding="utf-8")
    assert "PERMITE_INCERTA = False" in fonte
    assert "if PERMITE_INCERTA:" in fonte and "b3 is not None" in fonte
