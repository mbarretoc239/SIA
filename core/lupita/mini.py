"""Lupita em miniatura: botão flutuante com análise rápida (usado na tela de Amostragem).

Também guarda o que a página completa (views/10_Lupita.py) compartilha com o mini: carregadores com cache,
o ouvinte de Ctrl+V e os textos. Regras de egress valem aqui também:
  * nada toca o banco enquanto não houver imagem enviada (o corpo do popover roda a cada rerun da Amostragem);
  * versão e modelo vêm dos mesmos caches da página completa.
"""
from __future__ import annotations

import requests
import streamlit as st
import streamlit.components.v1 as components

from core.lupita import explicacao as E
from core.lupita import predicao as P
from core.lupita.acesso import usuario_liberado
from core.lupita.dados import LupitaDadosErro, LupitaRepo

SYNTHID_URL = "https://synthid.com"   # portal SynthID Detector (Google)
ROTULO_UPLOAD = "Radiografia (arraste, clique ou cole com Ctrl+V)"
PAGINA_COMPLETA = "views/10_Lupita.py"
CHAVE_RESULTADO = "_lupita_resultado"        # resultado da análise (compartilhado com a página completa)
CHAVE_IMAGEM_MINI = "_lupita_do_mini"        # bytes enviados do mini para a página completa abrir já com a imagem
_COR = {"ia": "red", "mid": "orange", "real": "green", "fora": "orange"}

# Colar com Ctrl+V: o st.file_uploader não trata colagem, então este ouvinte vive na página (não no iframe)
# e entrega a imagem colada ao uploader da Lupita. Só age se o uploader da Lupita estiver na tela
# (reconhecido pelo rótulo), então não mexe em uploaders de outras telas.
JS_COLAR = """
<script>
(function () {
  const pai = window.parent;
  const doc = pai.document;
  if (pai.__lupitaColar) { doc.removeEventListener('paste', pai.__lupitaColar, true); }
  const ouvinte = function (e) {
    const alvo = e.target;
    if (alvo && (alvo.tagName === 'TEXTAREA' || alvo.isContentEditable ||
        (alvo.tagName === 'INPUT' && alvo.type !== 'file'))) return;
    const caixa = Array.from(doc.querySelectorAll('[data-testid="stFileUploader"]'))
      .find(function (c) { return (c.textContent || '').indexOf('cole com Ctrl+V') >= 0; });
    if (!caixa) return;
    const entrada = caixa.querySelector('input[type="file"]');
    const itens = (e.clipboardData && e.clipboardData.items) || [];
    for (let i = 0; i < itens.length; i++) {
      if (itens[i].kind === 'file' && itens[i].type.indexOf('image/') === 0) {
        const arq = itens[i].getAsFile();
        if (!arq || !entrada) return;
        const ext = (itens[i].type.split('/')[1] || 'png').replace('jpeg', 'jpg');
        const novo = new pai.File([arq], 'colada_' + Date.now() + '.' + ext, { type: itens[i].type });
        const lista = new pai.DataTransfer();
        lista.items.add(novo);
        entrada.files = lista.files;
        entrada.dispatchEvent(new pai.Event('change', { bubbles: true }));
        e.preventDefault();
        return;
      }
    }
  };
  pai.__lupitaColar = ouvinte;
  doc.addEventListener('paste', ouvinte, true);
})();
</script>
"""


# ---- caches (único jeito de a tela tocar o banco sem custo por rerun) ----------------------
@st.cache_data(ttl=600, show_spinner=False)
def versao_ativa(_repo):
    return _repo.versao_ativa()


@st.cache_resource(show_spinner="Carregando o modelo...")
def modelo_da_versao(_repo, versao):
    return _repo.modelo_da_versao(versao)


@st.cache_data(ttl=300, show_spinner=False)
def historico(_repo):
    return _repo.historico(50)


def limpar_caches_modelo():
    versao_ativa.clear()
    modelo_da_versao.clear()


# ---- análise -------------------------------------------------------------------------------
def analisar_e_registrar(repo: LupitaRepo, modelo: dict, versao: int, dados: bytes):
    """Mede a imagem e tenta registrar no histórico. Devolve (guardado, aviso|None).

    Falha de rede ao registrar NÃO esconde o resultado: vira aviso. Erros da própria medição sobem."""
    h = P.hash_imagem(dados)
    res = P.analisar(modelo, dados)
    aviso = None
    try:
        repo.registrar_analise(h, res["medidas"], res["prob"], res["fora_do_padrao"], res["grupos"], versao)
        historico.clear()
    except (LupitaDadosErro, requests.RequestException) as erro:
        aviso = f"Análise feita, mas não foi possível registrar no histórico: {erro}"
    return {"hash": h, "versao": versao, "res": res, "rotulo": None}, aviso


_CSS = """
<style>
/* Segundo botão flutuante, ao lado do "⚡ Atalhos" (mesmo estilo; deslocado pra direita dele). */
div.st-key-fab_container_lupita div[data-testid="stPopover"] {
    position: fixed !important;
    bottom: 6px;
    left: calc(22rem + 9rem);
    z-index: 9999;
    width: fit-content !important;
    transition: left 0.2s ease;
}
div.st-key-fab_container_lupita div[data-testid="stPopover"] > div { width: fit-content !important; }
div.st-key-fab_container_lupita div[data-testid="stPopover"] > div > button {
    width: fit-content !important;
    border-radius: 999px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.4);
    padding: 8px 20px;
    font-size: 0.95rem;
    min-height: 0;
    background-color: #f0f2f6 !important;
    opacity: 1 !important;
}
@media (prefers-color-scheme: dark) {
    div.st-key-fab_container_lupita div[data-testid="stPopover"] > div > button {
        background-color: #13233A !important;
    }
}
/* Corpo do popover: nunca passa da altura da tela (rola por dentro) e as colunas não empilham. */
div.st-key-lupita_corpo { max-height: 70vh; overflow-y: auto; overflow-x: hidden; }
div.st-key-lupita_corpo [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 0.5rem; }
div.st-key-lupita_corpo [data-testid="stColumn"] { min-width: 0 !important; }
body:has([data-testid="stExpandSidebarButton"]) div.st-key-fab_container_lupita div[data-testid="stPopover"] {
    left: calc(20px + 9rem);
}
</style>
"""


def botao_flutuante_lupita(db, usuario: str, role, usuario_id=None) -> None:
    """Botão "Lupita" ao lado de "Atalhos". Não faz nada para quem não tem acesso."""
    if not usuario_liberado(usuario, role, usuario_id):
        return
    st.markdown(_CSS, unsafe_allow_html=True)
    repo = LupitaRepo(db, usuario, role, usuario_id)
    with st.container(key="fab_container_lupita"):
        with st.popover("🔍 Lupita"):
            with st.container(key="lupita_corpo"):
                _corpo(repo)


def _corpo(repo: LupitaRepo) -> None:
    arquivo = st.file_uploader(ROTULO_UPLOAD, type=P.EXTENSOES_ACEITAS, key="mini_lupita_upload")
    components.html(JS_COLAR, height=0)
    if arquivo is None:
        st.caption("Chance de a radiografia ter sido gerada por IA. Priorização, não prova.")
        st.link_button("Conferir no SynthID", SYNTHID_URL, use_container_width=True,
                       help="Abre o portal do Google em outra aba. Confirme com o jurídico/DPO antes de subir "
                            "imagem de beneficiário lá (LGPD).")
        return

    dados = arquivo.getvalue()
    if len(dados) > P.TAMANHO_MAXIMO_BYTES:
        st.error("Arquivo maior que 25 MB.")
        return

    try:
        versao = versao_ativa(repo)
        linha_modelo = modelo_da_versao(repo, versao) if versao else None
    except (LupitaDadosErro, requests.RequestException) as erro:
        st.error(f"Não foi possível carregar o modelo: {erro}")
        return
    if not linha_modelo:
        st.warning("Ainda não há modelo ativo.")
        return

    h = P.hash_imagem(dados)
    guardado = st.session_state.get(CHAVE_RESULTADO)
    if not guardado or guardado["hash"] != h or guardado["versao"] != versao or "sinais" not in guardado["res"]:
        try:
            with st.spinner("Medindo a imagem..."):
                guardado, aviso = analisar_e_registrar(repo, linha_modelo["modelo"], versao, dados)
        except (ValueError, RuntimeError) as erro:
            st.error(f"Não foi possível analisar: {erro}")
            return
        st.session_state[CHAVE_RESULTADO] = guardado
        if aviso:
            st.warning(aviso)
    res = guardado["res"]

    texto_v, tom = E.veredito(res["prob"], res["fora_do_padrao"])
    col_img, col_res = st.columns([1, 1.5])
    with col_img:
        st.image(dados, use_container_width=True)   # miniatura do que foi analisado
    with col_res:
        st.markdown(f"### :{_COR[tom]}[{E.percentual_texto(res['prob'])}]")
        st.markdown(f"**:{_COR[tom]}[{texto_v}]**")
    st.progress(min(1.0, max(0.0, res["prob"])))
    if res["fora_do_padrao"]:
        st.caption("Fora do padrão do que o modelo já viu: o percentual pode estar alto sem ser IA.")

    c1, c2, c3 = st.columns(3)
    escolha = None
    if c1.button("É IA", key="mini_lupita_ia", use_container_width=True):
        escolha = 1
    elif c2.button("É real", key="mini_lupita_real", use_container_width=True):
        escolha = 0
    elif c3.button("Desfazer", key="mini_lupita_desfazer", use_container_width=True):
        escolha = -1
    if escolha is not None:
        try:
            novo = None if escolha == -1 else escolha
            repo.rotular(h, novo)
            guardado["rotulo"] = novo
            historico.clear()  # só quando algo mudou, nunca em todo rerun
        except (LupitaDadosErro, requests.RequestException) as erro:
            st.error(f"Não foi possível gravar a confirmação: {erro}")
    if guardado["rotulo"] is not None:
        st.success("Marcada como " + ("IA." if guardado["rotulo"] == 1 else "real."))
    else:
        st.caption("Sua confirmação entra no treino do próximo modelo.")

    d1, d2 = st.columns(2)
    if d1.button("Ver detalhado", key="mini_lupita_detalhe", use_container_width=True):
        st.session_state[CHAVE_RESULTADO] = guardado
        st.session_state[CHAVE_IMAGEM_MINI] = dados
        st.switch_page(PAGINA_COMPLETA)
    d2.link_button("SynthID", SYNTHID_URL, use_container_width=True,
                   help="Abre o portal do Google em outra aba. Confirme com o jurídico/DPO antes de subir "
                        "imagem de beneficiário lá (LGPD).")
