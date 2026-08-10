import streamlit as st
import pandas as pd

from core.amostragem import (
    ORDEM_CRITICAS,
    REGRAS_AMOSTRAGEM,
    _norm,
    carregar_procedimentos_criticos,
    carregar_processos_turso,
    consolidar_por_guia,
    guias_com_proc_critico,
    marcar_amostra,
    montar_lista_processos_mes,
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
from core.settings import tem_acesso_modulo
from services.relatorio_5302.glosa_matcher import carregar_mapa_procedimentos
from shared.database import DatabaseManager
from shared.ui import aplicar_filtro_numerico, filtro_numerico, pilula

st.set_page_config(page_title="Amostragem", page_icon="🦷", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar esta ferramenta.")
    st.stop()

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()

# Operador que indica biometria facial feita (fluxo automático via app);
# qualquer outro operador = análise manual, sem biometria.
OPERADOR_BIOMETRIA = "CONN_APPOD_NEW"

SEED_PADRAO = 42


def _botao_flutuante_upload_5302():
    """FAB fixo no canto da tela: sobe o relatório 5302 sem sair da
    Amostragem pra clicar na sidebar + upload separado. O arquivo vai pro
    session_state e a navegação usa switch_page -- o Relatório 5302 lê esse
    'pendente' como fallback quando o file_uploader nativo dele tá vazio
    (ver views/2_Relatorio_5302.py)."""
    role_fab = st.session_state.get("role_interno", "Contas")
    usuario_id_fab = st.session_state.get("usuario_id")
    permissoes_fab = st.session_state.db.carregar_permissoes_modulos()
    excecoes_fab = st.session_state.db.carregar_excecoes_modulos()
    if not tem_acesso_modulo(permissoes_fab, role_fab, "relatorio_5302", usuario_id_fab, excecoes_fab):
        return

    st.markdown(
        """
        <style>
        div[data-testid="stPopover"] {
            position: fixed;
            bottom: 20px;
            left: 20px;
            z-index: 9999;
        }
        div[data-testid="stPopover"] > div > button {
            border-radius: 999px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.4);
            padding: 2px 12px;
            font-size: 0.8rem;
            min-height: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.popover("📤 Subir 5302"):
        st.caption("Envia o relatório 5302 e já abre a tela dele com o arquivo carregado.")
        arquivo_fab = st.file_uploader(
            "Relatório 5302 (.pdf ou .csv)", type=["pdf", "csv"], key="fab_upload_5302",
        )
        if arquivo_fab is not None:
            st.session_state["_pendente_5302_bytes"] = arquivo_fab.getvalue()
            st.session_state["_pendente_5302_name"] = arquivo_fab.name
            st.switch_page("views/2_Relatorio_5302.py")


_botao_flutuante_upload_5302()


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

                col_filtro_pct, col_filtro_guias, col_filtro_proc = st.columns(3)
                with col_filtro_pct:
                    filtro_pct = filtro_numerico("% Liberação IA", "lista_proc_filtro_pct")
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
    texto_total_guias = str(total_guias_exibir) if total_guias_exibir else "—"

    texto_risco_prestador = None
    prestador_ativo = None

    with st.container(border=True):
        st.markdown(f"**Processo:** {processo_ativo}")
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

    todas_guias = df[["Especialidade", "NU_GUIA"]].drop_duplicates()
    df = df[~df["CD_PROCEDIMENTO"].isin(codigos_excluidos)] if codigos_excluidos else df

    df_guias = consolidar_por_guia(df)
    if codigos_excluidos:
        df_guias = todas_guias.merge(df_guias, on=["Especialidade", "NU_GUIA"], how="left")
        df_guias["Procedimentos"] = df_guias["Procedimentos"].fillna("")
        df_guias["Qtde_procs"] = df_guias["Qtde_procs"].fillna(0).astype(int)
        # Prótese: guia some da lista inteira se sobrou sem nenhum
        # procedimento (só tinha o(s) ignorado(s)) — nas demais
        # especialidades a guia continua aparecendo mesmo vazia.
        vazia_protese = (df_guias["Especialidade"].apply(_norm) == "PROTESE") & (df_guias["Qtde_procs"] == 0)
        df_guias = df_guias[~vazia_protese]
        df_guias = df_guias.sort_values(["Especialidade", "Procedimentos", "NU_GUIA"]).reset_index(drop=True)

    # --- Filtros de Biometria e Imagem ---
    # "Sem dado" (guia ainda não aparece na base de biometria/imagem) conta
    # como "não 100%" no filtro "Sem" — é o lado mais seguro pra auditoria
    # (não confirmado = trata como pendência).
    def _guia_100pct(info):
        if not info:
            return None
        n_ok, n_total = info[0], info[1]
        n_com_dado = info[2] if len(info) > 2 else n_total
        if n_total == 0 or n_com_dado == 0:
            return None
        return n_ok == n_total

    def _aplicar_filtro_guia(df_in, mapa, filtro):
        if not filtro or filtro == "Todos":
            return df_in
        quer_com = filtro == "Com"

        def _passa(guia):
            resultado = _guia_100pct(mapa.get(str(guia)))
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
    st.dataframe(pd.DataFrame(resumo), use_container_width=True, hide_index=True)

    # --- Detalhamento ---
    st.markdown("### Detalhamento por especialidade")

    for esp in especialidades:
        df_esp_total = df[df["Especialidade"] == esp]
        df_esp_guias = df_guias[df_guias["Especialidade"] == esp].reset_index(drop=True)
        total_procs = int(df_esp_total["Qtde"].sum())
        total_guias = len(df_esp_guias)

        def _tabela_completa():
            renderizar_tabela_guias(
                df_esp_guias, esp, objetivo=total_guias,
                guias_vistas=guias_vistas, biometria_por_guia=biometria_por_guia,
                imagem_por_guia=imagem_por_guia,
            )

        df_amostra_especial = None
        titulo_amostra = None

        if _norm(esp) in REGRAS_AMOSTRAGEM:
            df_amostra = marcar_amostra(df_esp_guias, esp, df_esp_total, seed=SEED_PADRAO)
            # Prótese sempre audita 100% das guias (regra "todas") — a
            # "Sugestão de amostra" ficaria idêntica à "Tabela completa",
            # então não ganha aba própria pra essa especialidade (as demais
            # com regra "todas", como Implante, continuam mostrando normalmente).
            if _norm(esp) != "PROTESE":
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

        # Cabeçalho do expander pintado de amarelo se a especialidade já é
        # crítica por definição (ORDEM_CRITICAS) OU tem procedimento crítico
        # presente — sinal visível sem precisar abrir pra ver a aba de amostra.
        titulo_expander = f"{esp} — {total_guias} guia(s), {total_procs} proc(s)"
        if _norm(esp) in ORDEM_CRITICAS or especialidade_tem_critico.get(esp, False):
            titulo_expander = f":orange[{titulo_expander}]"

        with st.expander(titulo_expander, expanded=False):
            if df_amostra_especial is not None:
                tab_completa, tab_amostra = st.tabs([f"Tabela completa ({total_guias})", titulo_amostra])
                with tab_completa:
                    _tabela_completa()
                with tab_amostra:
                    renderizar_tabela_guias(
                        df_amostra_especial, esp, objetivo=len(df_amostra_especial),
                        guias_vistas=guias_vistas, biometria_por_guia=biometria_por_guia,
                        imagem_por_guia=imagem_por_guia,
                    )
            else:
                _tabela_completa()
