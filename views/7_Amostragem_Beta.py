import html
from datetime import date

import streamlit as st
import pandas as pd
import streamlit.components.v1 as components

from core.amostragem import (
    _norm,
    carregar_regras_amostragem_cache,
    calcular_imagens_esperadas_guia,
    carregar_procedimentos_criticos,
    carregar_processos_turso,
    consolidar_por_guia,
    guia_100pct,
    guias_com_proc_critico,
    marcar_amostra,
    montar_lista_processos_mes,
    renderizar_botao_copiar_processo,
    renderizar_resumo_especialidades,
    renderizar_tabela_guias,
    selecionar_procedimentos_ignorados,
    gerenciar_procedimentos_ignorados,
)
from core.relatorio_5201 import (
    STATUS_CORES,
    carregar_dados_atuais,
    formatar_status_processo,
    obter_detalhe_glosas_prestador_cacheado,
    obter_risco_prestador_cacheado,
    status_processo,
)
from core.settings import (
    carregar_excecoes_modulos_cache,
    carregar_permissoes_modulos_cache,
    tem_acesso_modulo,
)
from services.relatorio_5302.glosa_matcher import carregar_mapa_procedimentos
from shared.database import DatabaseManager
from shared.ui import aplicar_filtro_numerico, filtro_numerico, pilula

st.set_page_config(page_title="Amostragem", page_icon="🦷", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar esta ferramenta.")
    st.stop()

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()

_role_pagina = st.session_state.get("role_interno", "Contas")
_usuario_id_pagina = st.session_state.get("usuario_id")
_permissoes_pagina = carregar_permissoes_modulos_cache()
_excecoes_pagina = carregar_excecoes_modulos_cache()
if not tem_acesso_modulo(_permissoes_pagina, _role_pagina, "amostragem", _usuario_id_pagina, _excecoes_pagina):
    st.error("Você não tem permissão para acessar este módulo.")
    st.stop()

# Operador que indica biometria facial feita (fluxo automático via app);
# qualquer outro operador = análise manual, sem biometria.
OPERADOR_BIOMETRIA = "CONN_APPOD_NEW"

SEED_PADRAO = 42


def _botao_flutuante_atalhos():
    """FAB único fixo no canto da tela: reúne o upload do 5302 e os atalhos
    de cópia num só popover -- dois FABs empilhados (versão anterior)
    atrapalhavam a visão da lista de especialidades atrás deles, além de
    depender de CSS frágil pra não colidir um com o outro."""
    role_fab = st.session_state.get("role_interno", "Contas")
    usuario_id_fab = st.session_state.get("usuario_id")
    # Versões cacheadas (60s) -- isso roda a cada rerun da página (buscar
    # processo, trocar de aba, etc.), não só uma vez, então sem cache virava
    # 2 consultas extra ao banco em toda interação da Amostragem.
    permissoes_fab = carregar_permissoes_modulos_cache()
    excecoes_fab = carregar_excecoes_modulos_cache()
    tem_acesso_5302 = tem_acesso_modulo(permissoes_fab, role_fab, "relatorio_5302", usuario_id_fab, excecoes_fab)

    st.markdown(
        """
        <style>
        /* Alvo via st.container(key=...) -- vira a classe .st-key-<nome> de
           verdade no DOM (Streamlit 1.3x+), mais confiável que tentar
           diferenciar popovers por ordem no DOM. */
        div.st-key-fab_container_atalhos div[data-testid="stPopover"] {
            position: fixed !important;
            bottom: 6px;
            left: 20px;
            z-index: 9999;
            width: fit-content !important;
            transition: left 0.2s ease;
        }
        div.st-key-fab_container_atalhos div[data-testid="stPopover"] > div {
            width: fit-content !important;
        }
        div.st-key-fab_container_atalhos div[data-testid="stPopover"] > div > button {
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
            div.st-key-fab_container_atalhos div[data-testid="stPopover"] > div > button {
                background-color: #13233A !important;
            }
        }
        /* Sidebar aberta cobre o canto esquerdo -- desloca o botão pra depois
           dela (Streamlit expõe o estado via aria-expanded no <section>). */
        body:has(section[data-testid="stSidebar"][aria-expanded="true"]) div.st-key-fab_container_atalhos div[data-testid="stPopover"] {
            left: 22rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    hoje = date.today()
    data_dia_1 = f"01/{hoje.month:02d}/{hoje.year}"
    itens = [
        (f"Data ({data_dia_1})", data_dia_1),
        ("C/ Especialidades Críticas", "PROCESSO ANALISADO POR AMOSTRAGEM DAS ESPECIALIDADES CRÍTICAS"),
        ("S/ Especialidades Críticas", "PROCESSO SEM ESPECIALIDADES CRÍTICAS ANALISADO POR AMOSTRAGEM DO ENVIO DE IMAGENS"),
    ]
    botoes_html = "\n".join(
        f'<button class="atalho-btn" data-val="{html.escape(valor)}">{html.escape(rotulo)}</button>'
        for rotulo, valor in itens
    )

    with st.container(key="fab_container_atalhos"):
        with st.popover("⚡ Atalhos"):
            if tem_acesso_5302:
                st.caption("Envia o relatório 5302 e já abre a tela dele com o arquivo carregado.")
                arquivo_fab = st.file_uploader(
                    "Relatório 5302 (.pdf ou .csv)", type=["pdf", "csv"], key="fab_upload_5302",
                )
                if arquivo_fab is not None:
                    st.session_state["_pendente_5302_bytes"] = arquivo_fab.getvalue()
                    st.session_state["_pendente_5302_name"] = arquivo_fab.name
                    st.switch_page("views/2_Relatorio_5302.py")
                st.divider()

            st.caption("Clique pra copiar.")
            components.html(
                f"""
                <style>
                    body {{ margin: 0; }}
                    .atalho-wrap {{ display: flex; flex-direction: column; gap: 6px; font-family: 'Source Sans Pro', sans-serif; }}
                    .atalho-btn {{
                        background: transparent;
                        border: 1px solid rgba(125,125,125,0.5);
                        border-radius: 6px;
                        padding: 8px 12px;
                        cursor: pointer;
                        font-size: 13px;
                        text-align: left;
                        color: #1f2937;
                    }}
                    .atalho-btn:hover {{ background: rgba(125,125,125,0.15); border-color: rgba(125,125,125,0.8); }}
                    .atalho-btn.copiado {{ background: #2e7d32; color: #fff; border-color: #43a047; }}
                    @media (prefers-color-scheme: dark) {{
                        .atalho-btn {{ color: #e6ecf5; border-color: rgba(255,255,255,0.25); }}
                        .atalho-btn:hover {{ background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.5); }}
                    }}
                </style>
                <div class="atalho-wrap">{botoes_html}</div>
                <script>
                    document.querySelectorAll('.atalho-btn').forEach(btn => {{
                        btn.addEventListener('click', () => {{
                            const val = btn.getAttribute('data-val');
                            navigator.clipboard.writeText(val).then(() => {{
                                const orig = btn.innerText;
                                btn.innerText = '✓ Copiado!';
                                btn.classList.add('copiado');
                                setTimeout(() => {{
                                    btn.innerText = orig;
                                    btn.classList.remove('copiado');
                                }}, 1100);
                            }});
                        }});
                    }});
                </script>
                """,
                height=32 * len(itens) + 16 * (len(itens) - 1) + 8,
            )


_botao_flutuante_atalhos()


def _guias_para_df(guias: list) -> pd.DataFrame:
    """Converte o retorno do Supabase pro formato esperado por
    consolidar_por_guia/marcar_amostra (Especialidade, CD_PROCEDIMENTO,
    NU_GUIA, LIBERACAO, Qtde)."""
    if not guias:
        return pd.DataFrame()
    return pd.DataFrame({
        "Especialidade": [g["ds_grupo"] for g in guias],
        "CD_PROCEDIMENTO": [g["cd_procedimento"] for g in guias],
        "NU_GUIA": [g["nu_guia"] for g in guias],
        "CD_OPERADOR_ATEND": [g.get("cd_operador_atend", "") for g in guias],
        "Qtde": 1,
    })


# --------------------------------------------------------------------- UI ----

st.title("Amostragem de Guias")
st.caption(
    "Após verificar processo no PowerBI, digite o número do processo abaixo. "
    "O sistema trará somente procedimentos que não foram liberados pela IA. "
    "Clique no número da guia, ele vai copiar automaticamente para poder colar no SIGO."
)

aba_busca, aba_config = st.tabs(["Amostragem", "Configurações"])

with aba_config:
    gerenciar_procedimentos_ignorados(st.session_state.db, key_prefix="amostragem_beta")

    if st.session_state.get("role_interno") == "Admin":
        st.caption(
            "O upload das planilhas mensais (base IA e imagem) foi centralizado em "
            "**Configurações → Importação de Planilhas**."
        )

with aba_busca:
    processo_digitado = st.text_input("Número do processo", placeholder="Ex: 8202650447")
    buscar = st.button("Buscar guias")

    if buscar:
        st.session_state["_amostragem_beta_processo"] = processo_digitado.strip()

    if st.session_state.get("role_interno") in ("Gestor", "Admin"):
        with st.expander("Lista de processos do mês"):
            with st.spinner("Carregando processos..."):
                df_processos = montar_lista_processos_mes(
                    carregar_processos_turso(), carregar_dados_atuais(), carregar_procedimentos_criticos()
                )

            if df_processos.empty:
                st.info("Nenhum processo encontrado na base do mês.")
            else:
                col_filtro_critica, col_filtro_status, col_filtro_execucao = st.columns(3)
                with col_filtro_critica:
                    filtro_critica = st.segmented_control(
                        "Crítica", ["Todos", "Somente críticas", "Sem críticas"],
                        default="Todos", key="lista_proc_filtro_critica",
                    )
                with col_filtro_status:
                    todos_status = sorted(df_processos["Status"].dropna().unique())
                    filtro_status = st.multiselect("Status", todos_status, key="lista_proc_filtro_status")
                with col_filtro_execucao:
                    todas_execucoes = sorted(df_processos["Execução"].dropna().unique())
                    filtro_execucao = st.multiselect("Execução", todas_execucoes, key="lista_proc_filtro_execucao")

                todas_especialidades = sorted({
                    e for lista in df_processos["Especialidades"].str.split(", ") for e in lista if e
                })
                filtro_especialidades = st.multiselect(
                    "Especialidade", todas_especialidades, key="lista_proc_filtro_esp",
                )

                col_filtro_pct, col_filtro_bio, col_filtro_guias, col_filtro_proc = st.columns(4)
                with col_filtro_pct:
                    filtro_pct = filtro_numerico("% Liberação IA", "lista_proc_filtro_pct")
                with col_filtro_bio:
                    filtro_bio = filtro_numerico("% Biometria", "lista_proc_filtro_bio")
                with col_filtro_guias:
                    filtro_guias = filtro_numerico("Total de Guias", "lista_proc_filtro_guias")
                with col_filtro_proc:
                    filtro_proc = filtro_numerico("Procedimentos", "lista_proc_filtro_proc")

                df_lista_filtrada = df_processos
                if filtro_critica == "Somente críticas":
                    df_lista_filtrada = df_lista_filtrada[df_lista_filtrada["Crítica"]]
                elif filtro_critica == "Sem críticas":
                    df_lista_filtrada = df_lista_filtrada[~df_lista_filtrada["Crítica"]]
                if filtro_status:
                    df_lista_filtrada = df_lista_filtrada[df_lista_filtrada["Status"].isin(filtro_status)]
                if filtro_execucao:
                    df_lista_filtrada = df_lista_filtrada[df_lista_filtrada["Execução"].isin(filtro_execucao)]
                if filtro_especialidades:
                    alvo = set(filtro_especialidades)
                    df_lista_filtrada = df_lista_filtrada[
                        df_lista_filtrada["Especialidades"].apply(
                            lambda s: bool(set(s.split(", ")) & alvo)
                        )
                    ]
                df_lista_filtrada = aplicar_filtro_numerico(df_lista_filtrada, "% Liberação IA", filtro_pct)
                df_lista_filtrada = aplicar_filtro_numerico(df_lista_filtrada, "% Biometria", filtro_bio)
                df_lista_filtrada = aplicar_filtro_numerico(df_lista_filtrada, "Total de Guias", filtro_guias)
                df_lista_filtrada = aplicar_filtro_numerico(df_lista_filtrada, "Procedimentos", filtro_proc)

                st.caption(f"{len(df_lista_filtrada)} de {len(df_processos)} processo(s) -- clique numa linha pra abrir.")
                evento_lista = st.dataframe(
                    df_lista_filtrada, use_container_width=True, hide_index=True,
                    on_select="rerun", selection_mode="single-row", key="lista_processos_tabela",
                )
                linhas_selecionadas = evento_lista.selection.get("rows") if evento_lista else []
                if linhas_selecionadas:
                    processo_clicado = str(df_lista_filtrada.iloc[linhas_selecionadas[0]]["Processo"])
                    if processo_clicado != st.session_state.get("_amostragem_beta_processo"):
                        st.session_state["_amostragem_beta_processo"] = processo_clicado
                        st.rerun()

    processo_ativo = st.session_state.get("_amostragem_beta_processo", "")

    if not processo_ativo:
        st.info("Digite o número do processo e clique em Buscar guias.")
        st.stop()

    with st.spinner("Buscando guias..."):
        guias = st.session_state.db.buscar_guias_ia_por_processo(processo_ativo)
    df = _guias_para_df(guias)

    if df.empty:
        st.warning(
            f"Nenhuma guia com LIBERAÇÃO = N encontrada para o processo "
            f"'{processo_ativo}' na base importada. Confira o número ou se o "
            f"mês do processo ainda está entre os 2 meses mantidos na base."
        )
        st.stop()

    total_guias_processo = guias[0].get("total_guias_processo") if guias else None

    # Status/auditor do processo no snapshot mais recente do REL5201 —
    # visível para todos os roles, pra ninguém se esbarrar auditando o
    # mesmo processo ao mesmo tempo. Tenta a busca direta (rápida, decifra
    # só esse processo) primeiro; cai pro carregamento completo (lento) só
    # se o processo ainda não tiver a coluna `ordem` preenchida -- meses
    # importados antes dessa otimização precisam ser reimportados pra
    # ganhar o caminho rápido.
    registro_direto = st.session_state.db.buscar_status_processo(processo_ativo)
    if registro_direto is not None:
        info_status = formatar_status_processo(registro_direto)
    else:
        info_status = status_processo(carregar_dados_atuais(), processo_ativo)

    # Total de guias: prefere o REL5201 (QT_GUIAS -- contagem oficial do
    # sistema) e só cai pro total_guias_processo da base IA (recalculado a
    # partir de um snapshot mensal, pode ficar defasado) se o processo ainda
    # não tiver match no REL5201 importado.
    qt_guias_rel = info_status.get("qt_guias") if info_status else None
    total_guias_exibir = qt_guias_rel if qt_guias_rel is not None else total_guias_processo
    texto_total_guias = str(total_guias_exibir) if total_guias_exibir is not None else "—"

    texto_risco_prestador = None
    prestador_ativo = None

    with st.container(border=True):
        renderizar_botao_copiar_processo(processo_ativo)
        st.caption(f"{len(df)} item(ns) sem liberação pela IA — {texto_total_guias} guia(s) no total do processo")

        if info_status is None:
            st.caption("Processo não encontrado no último relatório REL5201 importado (aba Produtividade).")
        else:
            col_status, col_auditor, col_tipo, col_pct = st.columns(4)

            cor_status = STATUS_CORES.get(info_status["status"], STATUS_CORES["_outro"])
            with col_status:
                st.markdown(
                    f"**Status:** {pilula(info_status['status_label'], cor_texto=cor_status)}",
                    unsafe_allow_html=True,
                )
            with col_auditor:
                auditor_texto = info_status["auditor"] or "—"
                desde = f" (desde {info_status['data_fmt']})" if info_status["data_fmt"] else ""
                st.markdown(f"**Auditor:** {auditor_texto}{desde}")
            with col_tipo:
                st.markdown(f"**Tipo de processo:** {info_status.get('execucao') or '—'}")
            with col_pct:
                pct_ia = info_status.get("pct_liberacao_ia")
                texto_pct = f"{pct_ia}%".replace(".", ",") if pct_ia is not None else "—"
                st.markdown(f"**Porcentagem de IA:** {texto_pct}")

            if info_status["situacao"] == "em_analise":
                st.caption("⚠️ Confira antes de duplicar o trabalho — processo já em análise.")

            # Risco do prestador (histórico de glosas em processos
            # anteriores dele -- não desse processo específico, que pode
            # nem ter passado pelo 5302 ainda). Só aparece se já houver
            # alguma glosa registrada no histórico pra esse prestador.
            prestador_ativo = info_status.get("prestador")
            if prestador_ativo:
                risco_prestador = obter_risco_prestador_cacheado(prestador_ativo)
                if risco_prestador["total_glosas"] > 0:
                    media = risco_prestador["media_glosas_por_processo"]
                    # Média de glosas por processo é a métrica principal --
                    # "% dos procedimentos" dilui demais em prestador de
                    # alto volume (ex: 126 glosas em 11 mil procedimentos =
                    # 1,1%, soa pouco, mas pode ser 1+ glosa por processo).
                    if media is not None:
                        trecho_media = f" (média de {str(media).replace('.', ',')} glosa(s) por processo)"
                    else:
                        trecho_media = ""
                    texto_risco_prestador = (
                        f"📋 Histórico do prestador: {risco_prestador['total_glosas']} glosa(s) registrada(s)"
                        f" em processos anteriores{trecho_media}."
                    )

    if texto_risco_prestador:
        with st.expander(texto_risco_prestador):
            pct_glosa = risco_prestador["pct_glosa"]
            if pct_glosa is not None:
                st.caption(
                    f"{risco_prestador['total_glosas']} glosa(s) em {risco_prestador['total_procedimentos']} "
                    f"procedimento(s) já vistos desse prestador ({str(pct_glosa).replace('.', ',')}%)."
                )

            detalhe = obter_detalhe_glosas_prestador_cacheado(prestador_ativo)
            por_glosa = detalhe.get("por_glosa", [])
            por_procedimento = detalhe.get("por_procedimento", [])
            por_mes = detalhe.get("por_mes", [])

            if por_mes:
                st.markdown("**Glosas por mês:**")
                st.dataframe(
                    pd.DataFrame(por_mes).rename(
                        columns={"mes_referencia": "Mês", "quantidade": "Glosas"}
                    ),
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Mês": st.column_config.Column(width="small"),
                        "Glosas": st.column_config.Column(width="small"),
                    },
                )

            if por_glosa:
                st.markdown("**Glosas mais frequentes** (código + justificativa):")
                st.dataframe(
                    pd.DataFrame(por_glosa).rename(columns={
                        "glosa": "Glosa", "justificativa": "Justificativa", "quantidade": "Ocorrências",
                    }),
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Glosa": st.column_config.Column(width="small"),
                        "Justificativa": st.column_config.Column(width="large"),
                        "Ocorrências": st.column_config.Column(width="small"),
                    },
                )

            if por_procedimento:
                # Descrição vem gravada na própria linha (fonte original --
                # 5310/5302), não de tabela_procedimentos: o REL5310 usa
                # código TUSS longo e o catálogo usa o código interno curto
                # do 5302, então cruzar os dois não funciona. Só cai pro
                # catálogo em linhas antigas que não tinham essa captura.
                mapa_procedimentos = carregar_mapa_procedimentos()
                df_procedimento = pd.DataFrame(por_procedimento)
                df_procedimento["Descrição"] = df_procedimento.apply(
                    lambda linha: linha.get("descricao") or mapa_procedimentos.get(linha.get("procedimento"), "—"),
                    axis=1,
                )
                st.markdown("**Procedimentos mais glosados:**")
                st.dataframe(
                    df_procedimento.rename(columns={"procedimento": "Procedimento", "quantidade": "Ocorrências"})[
                        ["Procedimento", "Descrição", "Ocorrências"]
                    ],
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Procedimento": st.column_config.Column(width="small"),
                        "Descrição": st.column_config.Column(width="large"),
                        "Ocorrências": st.column_config.Column(width="small"),
                    },
                )

            por_procedimento_glosa = detalhe.get("por_procedimento_glosa", [])
            if por_procedimento_glosa:
                # Cruzamento das duas tabelas acima: qual glosa pegou cada
                # procedimento -- as outras mostram cada dimensão isolada,
                # essa mostra a combinação (ex.: "480" pegou o procedimento X
                # 5 vezes e o Y 2 vezes, não só "480 aconteceu 7 vezes").
                st.markdown("**Glosas por procedimento:**")
                st.dataframe(
                    pd.DataFrame(por_procedimento_glosa).rename(columns={
                        "procedimento": "Procedimento", "descricao": "Descrição",
                        "glosa": "Glosa", "justificativa": "Justificativa", "quantidade": "Ocorrências",
                    })[["Procedimento", "Descrição", "Glosa", "Justificativa", "Ocorrências"]],
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Procedimento": st.column_config.Column(width="small"),
                        "Descrição": st.column_config.Column(width="medium"),
                        "Glosa": st.column_config.Column(width="small"),
                        "Justificativa": st.column_config.Column(width="medium"),
                        "Ocorrências": st.column_config.Column(width="small"),
                    },
                )

            if not por_glosa and not por_procedimento and not por_mes:
                st.caption("Sem detalhe disponível.")

    # Biometria por guia: computado do df ANTES do filtro de procedimentos
    # ignorados (é atributo de quem atendeu, não depende de quais
    # procedimentos entram ou não na análise). Guarda (qtd_com_biometria,
    # qtd_total_itens, qtd_com_operador_gravado) — o check só aparece quando
    # os dois primeiros batem (100%); se nenhum item tiver operador gravado
    # (guias importadas antes desta coluna existir), a célula fica em branco
    # em vez de mostrar "0/N" (que passaria a entender errada de "sem
    # biometria" quando na real é "dado ainda não disponível").
    def _biometria_guia(serie):
        valores = [str(v).strip() for v in serie]
        n_total = len(valores)
        n_bio = sum(v == OPERADOR_BIOMETRIA for v in valores)
        n_com_dado = sum(1 for v in valores if v)
        return (n_bio, n_total, n_com_dado)

    biometria_por_guia = (
        df.groupby("NU_GUIA")["CD_OPERADOR_ATEND"]
        .apply(_biometria_guia)
        .to_dict()
    )

    # Imagem por guia: vem de uma base separada (planilha própria, cadência
    # própria), cruzada por NU_GUIA. Guarda (qtd_com_imagem, qtd_total) —
    # aqui não existe "dado legado nulo" como na biometria (tem_imagem é
    # sempre um booleano real desde a importação), então guia ausente do
    # dict = sem nenhum registro de imagem ainda (célula em branco).
    imagem_registros = st.session_state.db.buscar_imagem_por_guias(df["NU_GUIA"].unique().tolist())
    imagem_por_guia = {}
    for reg in imagem_registros:
        n_ok, n_total = imagem_por_guia.get(reg["nu_guia"], (0, 0))
        n_total += 1
        if reg.get("tem_imagem"):
            n_ok += 1
        imagem_por_guia[reg["nu_guia"]] = (n_ok, n_total)

    # Nenhuma guia do processo tem registro de imagem -- sinal forte de que
    # a planilha de imagem (4016R) do mês não foi importada ainda, não que
    # o processo inteiro realmente não tem imagem nenhuma. Avisa antes de
    # qualquer filtro/aba "Sem Imagem" poder confundir as duas coisas.
    if df["NU_GUIA"].nunique() > 0 and not imagem_por_guia:
        st.warning(
            "⚠️ Nenhuma guia deste processo tem dado de imagem registrado. Pode ser que a "
            "planilha de imagem (4016R) do mês ainda não tenha sido importada em "
            "Configurações — confira antes de considerar que faltam imagens de verdade."
        )

    def _guia_confirmada_sem_imagem(nu_guia) -> bool:
        """True só quando HÁ dado de imagem pra essa guia e ele confirma que
        falta pelo menos uma -- nunca quando não há dado nenhum (info
        ausente do dict), que é justamente o caso "4016R não importada"."""
        info = imagem_por_guia.get(str(nu_guia))
        if not info:
            return False
        n_ok, n_total = info
        return n_total > 0 and n_ok < n_total

    # --- Filtros: procedimentos ignorados + Biometria/Imagem, agrupados num
    # único painel recolhido por padrão (não competem com o resultado abaixo).
    with st.expander("Filtros", expanded=False):
        # Procedimentos que não precisam ser analisados nesta guia (ex.:
        # coroas provisórias). O procedimento some da contagem e do sorteio;
        # a guia continua listada mesmo que fique sem nenhum procedimento
        # restante. A seleção pode ser salva como padrão (por especialidade),
        # aplicado automaticamente nas próximas análises.
        codigos_excluidos = selecionar_procedimentos_ignorados(
            df, st.session_state.db, key_prefix=f"amostragem_beta_{processo_ativo}"
        )

        st.divider()
        col_filtro_bio, col_filtro_img = st.columns(2)
        with col_filtro_bio:
            st.caption("Biometria")
            filtro_biometria = st.segmented_control(
                "Biometria", ["Todos", "Com", "Sem"],
                default="Todos", key=f"filtro_biometria_{processo_ativo}",
                label_visibility="collapsed",
            )
        with col_filtro_img:
            st.caption("Imagem")
            filtro_imagem = st.segmented_control(
                "Imagem", ["Todos", "Com", "Sem"],
                default="Todos", key=f"filtro_imagem_{processo_ativo}",
                label_visibility="collapsed",
            )

    # Regras de amostragem por especialidade, configuráveis por Admin/Gestor
    # em Configurações > Regras de Amostragem (cai pro padrão hardcoded se a
    # tabela estiver vazia -- ver carregar_regras_amostragem_cache). Carregada
    # aqui em cima (não só lá embaixo) porque também é usada para decidir se
    # uma guia esvaziada por procedimentos ignorados deve sumir da lista.
    REGRAS_AMOSTRAGEM, ORDEM_CRITICAS = carregar_regras_amostragem_cache()

    todas_guias = df[["Especialidade", "NU_GUIA"]].drop_duplicates()
    df = df[~df["CD_PROCEDIMENTO"].isin(codigos_excluidos)] if codigos_excluidos else df

    df_guias = consolidar_por_guia(df)
    if codigos_excluidos:
        df_guias = todas_guias.merge(df_guias, on=["Especialidade", "NU_GUIA"], how="left")
        df_guias["Procedimentos"] = df_guias["Procedimentos"].fillna("")
        df_guias["Qtde_procs"] = df_guias["Qtde_procs"].fillna(0).astype(int)
        df_guias["Procedimentos_qtd"] = df_guias["Procedimentos_qtd"].apply(
            lambda v: v if isinstance(v, list) else []
        )
        # Especialidade com regra "auditar todas" (IMPLANTE, PROTESE,
        # PROTESE ESPECIAL): guia some da lista inteira se sobrou sem nenhum
        # procedimento (só tinha o(s) ignorado(s)) — nas demais
        # especialidades a guia continua aparecendo mesmo vazia. Antes
        # checava só o nome "PROTESE" -- as outras especialidades "todas"
        # ficavam com a mesma guia vazia visível, sem nada pra auditar.
        vazia_regra_todas = df_guias["Especialidade"].apply(
            lambda e: REGRAS_AMOSTRAGEM.get(_norm(e), {}).get("tipo") == "todas"
        ) & (df_guias["Qtde_procs"] == 0)
        df_guias = df_guias[~vazia_regra_todas]
        df_guias = df_guias.sort_values(["Especialidade", "Procedimentos", "NU_GUIA"]).reset_index(drop=True)

    # Corrige o denominador do badge IMAGEM: a planilha 4016R às vezes traz
    # menos linhas do que o requisito do procedimento realmente pede (ex.:
    # RXIF pede 2 imagens, mas só veio 1 linha na planilha) -- nesse caso o
    # esperado pelo requisito passa a valer. Nunca diminui o total (se vieram
    # mais linhas reais que o esperado, o real prevalece) e nunca mexe no
    # numerador (n_ok continua sendo só o que realmente tem imagem anexada).
    # Só ajusta guia que já TEM algum registro de imagem -- guia ausente do
    # dict continua em branco (célula "—"), mesmo caso de sempre de "4016R
    # ainda não importada" pra essa guia, não vira "0/N confirmado".
    # df_guias é agrupado por (Especialidade, NU_GUIA) -- uma guia com
    # procedimentos de mais de uma especialidade aparece em mais de uma
    # linha aqui. O esperado de cada linha é só da fatia de procedimentos
    # daquela especialidade, então precisa SOMAR entre as linhas da mesma
    # guia antes de comparar com o total real -- usar max() direto no loop
    # descartava a exigência das outras especialidades da mesma guia.
    _esperado_por_guia = {}
    for _, _row_guia in df_guias.iterrows():
        _chave = str(_row_guia["NU_GUIA"])
        _esperado_por_guia[_chave] = (
            _esperado_por_guia.get(_chave, 0)
            + calcular_imagens_esperadas_guia(
                _row_guia["Procedimentos"], procs_qtd=_row_guia.get("Procedimentos_qtd")
            )
        )
    for _chave, _esperado in _esperado_por_guia.items():
        if _esperado > 0 and _chave in imagem_por_guia:
            _n_ok, _n_total = imagem_por_guia[_chave]
            imagem_por_guia[_chave] = (_n_ok, max(_n_total, _esperado))

    # --- Filtros de Biometria e Imagem ---
    # "Sem dado" (guia ainda não aparece na base de biometria/imagem) conta
    # como "não 100%" no filtro "Sem" — é o lado mais seguro pra auditoria
    # (não confirmado = trata como pendência). guia_100pct é a mesma função
    # usada pra decidir o ✓ do badge (core/amostragem.py) -- unificado pra
    # badge e filtro nunca discordarem sobre o que conta como "completo".
    def _aplicar_filtro_guia(df_in, mapa, filtro):
        if not filtro or filtro == "Todos":
            return df_in
        quer_com = filtro == "Com"

        def _passa(guia):
            resultado = guia_100pct(mapa.get(str(guia)))
            if resultado is None:
                return not quer_com
            return resultado == quer_com

        return df_in[df_in["NU_GUIA"].apply(_passa)]

    df_guias = _aplicar_filtro_guia(df_guias, biometria_por_guia, filtro_biometria)
    df_guias = _aplicar_filtro_guia(df_guias, imagem_por_guia, filtro_imagem)

    if df_guias.empty:
        st.info("Nenhuma guia bate com os filtros selecionados.")
        st.stop()

    # Mantém df (nível de item) em sincronia com as guias que sobraram após
    # os filtros — senão os totais de procedimentos no Resumo contariam
    # guias que os filtros já tiraram da lista.
    df = df[df["NU_GUIA"].isin(df_guias["NU_GUIA"])]

    guias_vistas = st.session_state.db.buscar_guias_vistas(df_guias["NU_GUIA"].unique().tolist())

    # REGRAS_AMOSTRAGEM/ORDEM_CRITICAS já carregadas lá em cima (antes do
    # bloco de filtros), reaproveitadas aqui.

    # Procedimentos cadastrados como críticos (tabela_procedimentos.critico) —
    # só importam pras especialidades fora de REGRAS_AMOSTRAGEM (Periodontia,
    # Odontopediatria, Radiologia Especial etc.): se uma guia dessas
    # especialidades tiver um desses procedimentos, ela sobe na lista e entra
    # garantida na "Sugestão de amostra", já que são casos raros que o
    # auditor corre risco de não perceber se ficarem escondidos lá embaixo.
    procedimentos_criticos = carregar_procedimentos_criticos()

    especialidades = df_guias["Especialidade"].unique().tolist()

    # Pra cada especialidade fora de REGRAS_AMOSTRAGEM, marca se tem pelo
    # menos uma guia com procedimento crítico nesta análise — decide tanto a
    # posição na lista quanto o conteúdo da "Sugestão de amostra" abaixo.
    especialidade_tem_critico = {}
    for esp in especialidades:
        if _norm(esp) in REGRAS_AMOSTRAGEM:
            continue
        df_esp_guias_check = df_guias[df_guias["Especialidade"] == esp]
        especialidade_tem_critico[esp] = not guias_com_proc_critico(df_esp_guias_check, procedimentos_criticos).empty

    def _peso_ordenacao(e):
        norm = _norm(e)
        # Procedimento crítico presente = topo absoluto, acima até das
        # especialidades já críticas — é justamente o caso raro que corre
        # risco de passar despercebido, então precisa ser o mais visível.
        if especialidade_tem_critico.get(e):
            return (0, norm)
        if norm in ORDEM_CRITICAS:
            return (1, ORDEM_CRITICAS.index(norm))
        return (2, norm)

    especialidades.sort(key=_peso_ordenacao)

    # --- Resumo ---
    resumo = []
    for esp in especialidades:
        df_esp_total = df[df["Especialidade"] == esp]
        df_esp_guias = df_guias[df_guias["Especialidade"] == esp].reset_index(drop=True)
        total_procs = int(df_esp_total["Qtde"].sum())
        total_guias = len(df_esp_guias)

        if _norm(esp) in REGRAS_AMOSTRAGEM:
            n_sugerido = len(marcar_amostra(df_esp_guias, esp, df_esp_total, seed=SEED_PADRAO))
        else:
            n_sugerido = len(guias_com_proc_critico(df_esp_guias, procedimentos_criticos))

        resumo.append({
            "Especialidade": esp,
            "Guias únicas": total_guias,
            "Total de procs": total_procs,
            "Amostra sugerida": n_sugerido,
        })

    st.markdown("### Resumo")
    renderizar_resumo_especialidades(resumo, df)

    # --- Detalhamento ---
    st.markdown("### Detalhamento por especialidade")

    for esp in especialidades:
        df_esp_total = df[df["Especialidade"] == esp]
        df_esp_guias = df_guias[df_guias["Especialidade"] == esp].reset_index(drop=True)
        total_procs = int(df_esp_total["Qtde"].sum())
        total_guias = len(df_esp_guias)

        def _renderizar(df_alvo, contagem_especialidade=False):
            # contagem_especialidade=True (só na aba "Sugestão de amostra"):
            # o contador conta qualquer guia da especialidade já vista, não
            # só as sorteadas -- se o auditor já revisou guias fora da
            # sugestão, isso conta pra bater a meta (pode passar de
            # `objetivo`, ex.: "6 de 5 ✓").
            renderizar_tabela_guias(
                df_alvo, esp, objetivo=len(df_alvo),
                guias_vistas=guias_vistas, biometria_por_guia=biometria_por_guia,
                imagem_por_guia=imagem_por_guia,
                guias_contagem=df_esp_guias["NU_GUIA"].tolist() if contagem_especialidade else None,
            )

        df_amostra_especial = None
        titulo_amostra = None

        if _norm(esp) in REGRAS_AMOSTRAGEM:
            df_amostra = marcar_amostra(df_esp_guias, esp, df_esp_total, seed=SEED_PADRAO)
            # Regra "todas" (auditar 100% das guias, ex.: Implante, Prótese,
            # Prótese Especial) — a "Sugestão de amostra" ficaria idêntica à
            # "Tabela completa", então não ganha aba própria pra nenhuma
            # especialidade com essa regra (checa o TIPO da regra, não o
            # nome -- antes só "PROTESE" era tratado, deixando a mesma aba
            # redundante aparecer pras outras especialidades "todas").
            if REGRAS_AMOSTRAGEM.get(_norm(esp), {}).get("tipo") != "todas":
                df_amostra_especial = df_amostra.drop(columns=["Motivo"], errors="ignore")
                titulo_amostra = f"Sugestão de amostra ({len(df_amostra_especial)})"
        elif especialidade_tem_critico.get(esp):
            # Especialidade fora das regras de amostragem, mas com
            # procedimento crítico presente: a "Sugestão de amostra" mostra
            # só as guias com esse procedimento, não as 100% da especialidade.
            df_amostra_especial = guias_com_proc_critico(df_esp_guias, procedimentos_criticos)
            titulo_amostra = f"Sugestão de amostra ({len(df_amostra_especial)} — proc. crítico)"
        # Sem regra de amostragem e sem procedimento crítico presente: sem
        # aba de "Sugestão de amostra" (hoje mostraria 100% das guias, igual
        # à Tabela completa, sem utilidade nenhuma).

        # "Sem Imagem": só guias com dado de imagem CONFIRMANDO falta (nunca
        # guia sem dado nenhum -- ver _guia_confirmada_sem_imagem e o aviso
        # de 4016R não importada logo acima). Só ganha aba própria se houver
        # pelo menos 1 guia nessa condição.
        df_sem_imagem = df_esp_guias[df_esp_guias["NU_GUIA"].apply(_guia_confirmada_sem_imagem)]

        # Cabeçalho do expander pintado de amarelo se a especialidade já é
        # crítica por definição (ORDEM_CRITICAS) OU tem procedimento crítico
        # presente — sinal visível sem precisar abrir pra ver a aba de amostra.
        titulo_expander = f"{esp} — {total_guias} guia(s), {total_procs} proc(s)"
        if _norm(esp) in ORDEM_CRITICAS or especialidade_tem_critico.get(esp, False):
            titulo_expander = f":orange[{titulo_expander}]"

        with st.expander(titulo_expander, expanded=False):
            abas = [(f"Tabela completa ({total_guias})", df_esp_guias, False)]
            if df_amostra_especial is not None:
                abas.append((titulo_amostra, df_amostra_especial, True))
            if len(df_sem_imagem) > 0:
                abas.append((f"Sem Imagem ({len(df_sem_imagem)})", df_sem_imagem, False))

            if len(abas) == 1:
                _renderizar(df_esp_guias)
            else:
                tabs_esp = st.tabs([titulo for titulo, _, _ in abas])
                for tab_esp, (_, df_aba, contagem_especialidade) in zip(tabs_esp, abas):
                    with tab_esp:
                        _renderizar(df_aba, contagem_especialidade)
