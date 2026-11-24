"""Lupita: triagem de radiografias com chance de terem sido geradas por IA.

Prioridade de revisão, NÃO veredito. Acesso restrito (core/lupita/acesso.py).
Egress: nenhuma leitura de banco acontece fora das ações da tela e dos caches abaixo.
"""
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core.lupita import explicacao as E
from core.lupita import mini as M
from core.lupita import predicao as P
from core.lupita.acesso import usuario_liberado
from core.lupita.catalogo import FEATURES, GRUPOS_INFO
from core.lupita.dados import LeituraNaoPermitida, LupitaDadosErro, LupitaRepo, TETO_AMOSTRAS_TREINO

st.title("Lupita")
st.caption(
    "Estima a chance de uma radiografia ter sido gerada por IA (ChatGPT, Gemini). "
    "Serve para decidir o que vai primeiro para revisão. Resultado alto não é prova, "
    "e resultado baixo não prova que a imagem é real. O SynthID continua sendo a evidência forte."
)

SYNTHID_URL = M.SYNTHID_URL
ROTULO_UPLOAD = M.ROTULO_UPLOAD
_JS_COLAR = M.JS_COLAR
# Botão "Não sei ao certo": desligado por ora. Banco (coluna `incerto`), repositório e histórico seguem
# prontos; pra religar basta trocar para True.
PERMITE_INCERTA = False

usuario = st.session_state.get("usuario_sigo", "")
role = st.session_state.get("role_interno")
if not usuario_liberado(usuario, role):
    st.error("Acesso restrito.")
    st.stop()

repo = LupitaRepo(st.session_state.db, usuario, role)

st.link_button(
    "Conferir no SynthID Detector", SYNTHID_URL,
    help="Abre o portal do Google em outra aba. Antes de subir imagem de beneficiário lá, confirme com o "
         "jurídico/DPO (LGPD): a Lupita roda no servidor do SIA e não envia a imagem a terceiros.",
)


# ---- caches (compartilhados com o mini da Amostragem, em core/lupita/mini.py) --------------
_versao_ativa = M.versao_ativa
_modelo_da_versao = M.modelo_da_versao
_historico = M.historico
_limpar_caches_modelo = M.limpar_caches_modelo


try:
    versao = _versao_ativa(repo)
    linha_modelo = _modelo_da_versao(repo, versao) if versao else None
except LupitaDadosErro as erro:
    st.error(f"Não foi possível carregar o modelo: {erro}")
    st.stop()

aba_analisar, aba_historico, aba_modelo, aba_como = st.tabs(["Analisar", "Histórico", "Modelo", "Como funciona"])

# ---- Analisar -----------------------------------------------------------------------------
with aba_analisar:
    if not linha_modelo:
        st.warning("Ainda não há modelo ativo. Importe o JSON da Lupita ou treine na aba Modelo.")
    else:
        modelo = linha_modelo["modelo"]
        arquivo = st.file_uploader(ROTULO_UPLOAD, type=P.EXTENSOES_ACEITAS, accept_multiple_files=False)
        components.html(_JS_COLAR, height=0)
        dados = None
        if arquivo is not None:
            st.session_state.pop(M.CHAVE_IMAGEM_MINI, None)
            dados = arquivo.getvalue()
        elif st.session_state.get(M.CHAVE_IMAGEM_MINI):
            dados = st.session_state[M.CHAVE_IMAGEM_MINI]   # veio do botão "Ver detalhado" da Amostragem
            st.caption("Imagem enviada pelo mini da Amostragem. Para analisar outra, use o campo acima.")
        if dados is not None:
            if len(dados) > P.TAMANHO_MAXIMO_BYTES:
                st.error("Arquivo maior que 25 MB.")
            else:
                h = P.hash_imagem(dados)
                guardado = st.session_state.get("_lupita_resultado")
                if (not guardado or guardado["hash"] != h or guardado["versao"] != versao
                        or "sinais" not in guardado["res"]):
                    try:
                        with st.spinner("Medindo a imagem..."):
                            res = P.analisar(modelo, dados)
                    except (ValueError, RuntimeError) as erro:
                        st.error(f"Não foi possível analisar: {erro}")
                        st.stop()
                    try:
                        repo.registrar_analise(h, res["medidas"], res["prob"], res["fora_do_padrao"],
                                               res["grupos"], versao)
                        _historico.clear()
                    except LupitaDadosErro as erro:
                        st.warning(f"Análise feita, mas não foi possível registrar no histórico: {erro}")
                    guardado = {"hash": h, "versao": versao, "res": res, "rotulo": None}
                    st.session_state["_lupita_resultado"] = guardado
                res = guardado["res"]

                texto_v, tom = E.veredito(res["prob"], res["fora_do_padrao"])
                cor = {"ia": "red", "mid": "orange", "real": "green", "fora": "orange"}[tom]
                col_img, col_res = st.columns([1, 1.4])
                with col_img:
                    st.image(dados, use_container_width=True)
                with col_res:
                    st.markdown(f"### :{cor}[{texto_v}]")
                    st.metric("Chance de ser IA", E.percentual_texto(res["prob"]))
                    st.progress(min(1.0, max(0.0, res["prob"])))
                    if res["fora_do_padrao"]:
                        st.warning(
                            "Imagem fora do padrão do que o modelo já viu (foto de filme, foto de tela, "
                            "outra fonte). O percentual pode estar alto sem ser IA. Se for real, "
                            "confirme abaixo para entrar no treino."
                        )
                    st.caption("Estimativa estatística para priorizar a revisão, não uma prova.")

                st.subheader("Principais sinais")
                st.caption("As medidas que mais pesaram nesta imagem. O número é o peso da medida na conta do modelo.")
                col_ia, col_real = st.columns(2)
                for coluna, titulo, chave in ((col_ia, "Empurram para IA", "ia"),
                                              (col_real, "Empurram para real", "real")):
                    with coluna:
                        st.markdown(f"**{titulo}**")
                        itens = res["sinais"][chave]
                        if not itens:
                            st.caption("Nenhuma medida passou do peso mínimo deste lado.")
                        for it in itens:
                            sinal = "+" if it["contribuicao"] > 0 else "-"
                            st.markdown(f"**{it['rotulo']}** ({it['grupo']}) · {sinal}{E.nf(abs(it['contribuicao']), 2)}")
                            st.write(it["frase"].capitalize() + ".")
                            if "esta_imagem" in it:
                                st.caption(f"Esta imagem: {it['esta_imagem']} · média das IA: {it['media_ia']} · "
                                           f"média das reais: {it['media_reais']}")

                with st.expander("Peso por grupo de medidas"):
                    st.caption("Positivo empurra para IA, negativo para real.")
                    st.bar_chart(pd.Series(res["grupos"]).sort_values(), horizontal=True, height=260)

                with st.expander("Medidas desta radiografia"):
                    for titulo, texto in res["radiografia"]:
                        st.markdown(f"**{titulo}:** {texto}")
                    st.caption(
                        "Estimativas por processamento de imagem na versão reduzida (até 512 px). Contagem de "
                        "raízes, faces e distância a seio maxilar ou canal mandibular não são medidas aqui."
                    )

                st.divider()
                if PERMITE_INCERTA:
                    st.caption("Confirmação do auditor. “É IA” e “É real” entram no treino do próximo modelo; "
                               "“Não sei ao certo” fica registrada, mas fora do treino.")
                    b1, b2, b3, b4, _ = st.columns([1, 1, 1.4, 1, 1.6])
                else:
                    st.caption("Confirmação do auditor (entra no treino do próximo modelo)")
                    b1, b2, b4, _ = st.columns([1, 1, 1, 3])
                    b3 = None
                escolha = None
                if b1.button("É IA", use_container_width=True):
                    escolha = 1
                elif b2.button("É real", use_container_width=True):
                    escolha = 0
                elif b3 is not None and b3.button("Não sei ao certo", use_container_width=True):
                    escolha = "incerto"
                elif b4.button("Desfazer", use_container_width=True):
                    escolha = -1
                if escolha is not None:
                    try:
                        if escolha == "incerto":
                            repo.rotular(h, None, incerto=True)
                            guardado["rotulo"] = "incerto"
                        else:
                            novo = None if escolha == -1 else escolha
                            repo.rotular(h, novo)
                            guardado["rotulo"] = novo
                        _historico.clear()  # só quando algo mudou, nunca em todo rerun
                    except LupitaDadosErro as erro:
                        st.error(f"Não foi possível gravar a confirmação: {erro}")
                if guardado["rotulo"] == "incerto":
                    st.info("Marcada como incerta. Não entra no treino.")
                elif guardado["rotulo"] is not None:
                    st.success("Marcada como " + ("IA." if guardado["rotulo"] == 1 else "real."))

# ---- Histórico ----------------------------------------------------------------------------
with aba_historico:
    try:
        linhas = _historico(repo)
    except LupitaDadosErro as erro:
        linhas = []
        st.error(f"Não foi possível ler o histórico: {erro}")
    if not linhas:
        st.info("Nenhuma análise ainda.")
    else:
        df = pd.DataFrame(linhas)
        df["Quando"] = pd.to_datetime(df["criado_em"], utc=True).dt.tz_convert("America/Sao_Paulo").dt.strftime("%d/%m/%Y %H:%M")
        df["Chance de IA"] = (df["score"] * 100).round(0)
        df["Fora do padrão"] = df["fora_padrao"].map({True: "Sim", False: "Não"}).fillna("")
        df["Confirmação"] = df["rotulo"].map({1.0: "IA", 0.0: "Real"}).fillna("Pendente")
        if "incerto" in df.columns:  # cache antigo (até 5 min) ainda pode vir sem essa coluna
            df.loc[df["incerto"].fillna(False).astype(bool), "Confirmação"] = "Incerta"
        df["Imagem"] = df["hash_imagem"].str[:10]
        st.dataframe(
            df[["Quando", "Imagem", "Chance de IA", "Fora do padrão", "Confirmação", "usuario"]]
            .rename(columns={"usuario": "Usuário"}),
            hide_index=True, use_container_width=True,
            column_config={"Chance de IA": st.column_config.NumberColumn(format="%d%%")},
        )
        st.caption("Últimas 50 análises. A imagem em si nunca é guardada: só as medidas e o código (hash) do arquivo.")

# ---- Modelo -------------------------------------------------------------------------------
with aba_modelo:
    if linha_modelo and linha_modelo.get("metricas"):
        m = linha_modelo["metricas"]
        st.write(f"Modelo ativo: versão {linha_modelo['versao']} ({linha_modelo.get('origem') or 'sem origem'})")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Acerto (validação cruzada)", f"{m['acerto'] * 100:.0f}%")
        c2.metric("AUC", f"{m['auc']:.3f}")
        c3.metric("Reais acusadas por engano", f"{m['fpr_reais'] * 100:.1f}%")
        c4.metric("IA detectadas", f"{m['recall_ia'] * 100:.0f}%")
        st.caption(
            f"Treinado com {m['n_ia']} de IA e {m['n_reais']} reais. Os números são otimistas: imagens do "
            "mesmo lote de upload ficam parecidas. Funciona bem em radiografia digital do SIGO e mal fora dela. "
            "Print e recompressão derrubam as medidas que dependem do tamanho."
        )

    st.divider()
    st.subheader("Retreinar")
    st.caption(
        "Lê todas as imagens já confirmadas (IA ou real) e grava uma nova versão do modelo. "
        f"A leitura gasta tráfego do banco (teto de {TETO_AMOSTRAS_TREINO:,} amostras), então só roda quando você clica."
        .replace(",", ".")
    )
    if st.button("Ver o que seria lido"):
        try:
            st.session_state["_lupita_contagem"] = repo.contar_rotuladas()
        except LupitaDadosErro as erro:
            st.error(str(erro))
    contagem = st.session_state.get("_lupita_contagem")
    if contagem:
        total = contagem["ia"] + contagem["reais"]
        st.write(f"{contagem['ia']} de IA e {contagem['reais']} reais confirmadas, "
                 f"cerca de {repo.estimar_mb_treino(total):.1f} MB de tráfego.")
        if contagem["ia"] < 6 or contagem["reais"] < 6:
            st.info("São necessárias pelo menos 6 imagens de cada classe.")
        elif total > TETO_AMOSTRAS_TREINO:
            st.error("Acima do teto de leitura. Retreine com o script local.")
        else:
            ok = st.checkbox("Entendi que isso lê todas as amostras e ativa o novo modelo")
            if st.button("Retreinar agora", type="primary", disabled=not ok):
                try:
                    with st.spinner("Lendo amostras e treinando..."):
                        medidas, rotulos = repo.amostras_treino()
                        novo = P.treinar_de_linhas(medidas, rotulos)
                        nova_versao = repo.salvar_modelo(novo, origem="retreino na tela")
                    _limpar_caches_modelo()
                    st.session_state.pop("_lupita_contagem", None)
                    st.success(f"Modelo versão {nova_versao} ativado.")
                    st.rerun()
                except (LupitaDadosErro, LeituraNaoPermitida, ValueError) as erro:
                    st.error(f"Não foi possível retreinar: {erro}")

# ---- Como funciona ------------------------------------------------------------------------
with aba_como:
    st.markdown(
        "A Lupita mede **56 características** da imagem (espectro de frequências, ruído, bordas, textura, "
        "compressão, cor, formato dos dentes e dados do arquivo) e combina as que entram no modelo numa "
        "**regressão logística** treinada com imagens reais do SIGO e imagens geradas por IA. O resultado é "
        "uma probabilidade. Não há rede neural nem GPU, e a imagem não sai do servidor do SIA."
    )

    st.subheader("Grupos de medidas")
    usados = set(((linha_modelo or {}).get("modelo") or {}).get("grupos") or [])
    acerto = {"radio": "94% (AUC 0,969)", "noise": "92% (AUC 0,961)", "color": "91% (AUC 0,962)",
              "freq": "90% (AUC 0,948)", "file": "90% (AUC 0,954)", "edges": "81% (AUC 0,897)",
              "texture": "80% (AUC 0,864)", "compress": "44% (AUC 0,599)"}
    contagem = {g: sum(1 for f in FEATURES if f[1] == g) for g in GRUPOS_INFO}
    tabela = pd.DataFrame([{
        "Grupo": nome, "O que mede": desc, "Medidas": contagem[gid],
        "No modelo": "Sim" if gid in usados else "Não", "Acerto sozinho": acerto[gid],
    } for gid, (nome, desc, _) in GRUPOS_INFO.items()])
    st.dataframe(tabela, hide_index=True, use_container_width=True)
    st.caption("Acerto de cada grupo sozinho, medido pela equipe da Lupita com 2.310 imagens "
               "(558 de IA e 1.752 reais).")

    st.markdown("**Por que três grupos ficam de fora**")
    st.markdown(
        "- **Compressão:** sozinha acerta 44%, abaixo de um sorteio. Não distingue nada.\n"
        "- **Cor:** acerta muito, mas por atalho. As radiografias reais do SIGO são em cinza e as de IA têm cor, "
        "então o modelo aprenderia “tem cor, logo é IA”. Uma radiografia real azulada chegou a receber mais de 99%.\n"
        "- **Arquivo:** acerta pelo viés da coleta. As imagens de IA do treino vieram de print de tela, que deixa "
        "formato, tamanho e ausência de metadados típicos. No SIGO esse padrão não existe."
    )

    st.subheader("Como ler o percentual")
    st.dataframe(pd.DataFrame([
        ("90% ou mais", "Muito provavelmente IA"), ("70% a 90%", "Provavelmente IA"),
        ("55% a 70%", "Tende a ser IA"), ("45% a 55%", "Inconclusivo"),
        ("30% a 45%", "Tende a ser real"), ("10% a 30%", "Provavelmente real"),
        ("10% ou menos", "Muito provavelmente real"),
    ], columns=["Chance de IA", "Texto"]), hide_index=True, use_container_width=True)
    st.caption("Quando a imagem foge do que o modelo viu no treino, o texto vira “Fora do padrão do treino” "
               "e o percentual continua visível.")

    st.subheader("O que a Lupita não faz")
    st.markdown(
        "- **Não é veredito.** Resultado alto manda a imagem para a frente da fila de revisão. Resultado baixo não "
        "prova que a imagem é real. O SynthID continua sendo a evidência forte: use o botão “Conferir no SynthID "
        "Detector” no topo da tela.\n"
        "- **Print e recompressão** derrubam as medidas que dependem do tamanho. Por isso o tamanho da imagem não "
        "vira parâmetro.\n"
        "- **Imagem fora do banco** (filme, foto de tela, outras fontes) pode sair com percentual alto sem ser IA. "
        "Nesses casos aparece o aviso de fora do padrão, e a confirmação “É real” faz a imagem entrar no treino.\n"
        "- **Metadados do arquivo** (EXIF, C2PA) não entram no cálculo. O SIGO gera uma imagem nova no envio, o que "
        "apaga esses dados, e a ausência deles não indica nada.\n"
        "- **Os números de desempenho são otimistas:** imagens do mesmo lote de upload ficam parecidas. "
        "Funciona bem em radiografia digital do SIGO e mal fora dela."
    )

    st.subheader("Glossário")
    st.dataframe(pd.DataFrame([
        ("Medida", "Um número calculado da imagem, como o ruído fino."),
        ("Grupo", "Conjunto de medidas da mesma família (Frequências, Ruído...)."),
        ("Validação cruzada", "Prever cada imagem com um modelo que não a viu, para estimar o desempenho real."),
        ("AUC", "Capacidade de separar as classes: 0,5 é sorteio e 1 é perfeito."),
        ("Calibração (Platt)", "Ajuste que transforma a conta do modelo em uma probabilidade mais honesta."),
        ("Fora do padrão", "Imagem muito diferente do que o treino viu; o percentual vale menos."),
        ("Lote", "Imagens enviadas juntas. Imagens do mesmo lote são parecidas e deixam os testes otimistas."),
    ], columns=["Termo", "Significado"]), hide_index=True, use_container_width=True)

    with st.expander("Catálogo das 56 medidas"):
        st.dataframe(pd.DataFrame([{
            "Grupo": GRUPOS_INFO[f[1]][0], "Medida": f[2], "Quando o valor é baixo": f[3], "Quando é alto": f[4],
        } for f in FEATURES]), hide_index=True, use_container_width=True, height=420)
