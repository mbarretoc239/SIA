import openpyxl
import streamlit as st
import pandas as pd

from core.amostragem import (
    ORDEM_CRITICAS,
    REGRAS_AMOSTRAGEM,
    _norm,
    carregar_procedimentos_criticos,
    consolidar_por_guia,
    guias_com_proc_critico,
    marcar_amostra,
    renderizar_tabela_guias,
    selecionar_procedimentos_ignorados,
    gerenciar_procedimentos_ignorados,
)
from shared.database import DatabaseManager

st.set_page_config(page_title="Amostragem", page_icon="", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar esta ferramenta.")
    st.stop()

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()

# Colunas mínimas esperadas na planilha mensal da base IA (mesma que alimenta
# o PowerBI). Nomes normalizados via _norm (maiúsculo, sem acento).
COLUNAS_NECESSARIAS = {"NU_ORDEM", "NU_GUIA", "CD_PROCEDIMENTO", "DS_GRUPO", "LIBERACAO", "DT_CREATED_AT"}

SEED_PADRAO = 42
_is_admin = st.session_state.get("role_interno") == "Admin"


def _preparar_registros(arquivo) -> tuple[list, str, int]:
    """Lê a planilha mensal e devolve (registros_para_inserir, mes_referencia, total_bruto).

    Lê linha a linha via openpyxl (read_only) em vez de pandas.read_excel —
    a planilha tem ~500 mil linhas e carregar tudo num DataFrame de uma vez
    consome memória demais (gerou MemoryError em máquina com pouca RAM livre).

    Só mantém linhas com LIBERACAO == 'N' (é só isso que a amostragem usa).
    `mes_referencia` é derivado de DT_CREATED_AT (constante por arquivo,
    ex: planilha 'IA 07 2026' tem DT_CREATED_AT = 2026-07-01).
    """
    wb = openpyxl.load_workbook(arquivo, read_only=True, data_only=True)
    aba = "Planilha1" if "Planilha1" in wb.sheetnames else wb.sheetnames[0]
    ws = wb[aba]
    linhas = ws.iter_rows(values_only=True)

    header = [_norm(str(c)) for c in next(linhas)]
    idx = {nome: i for i, nome in enumerate(header)}
    faltantes = COLUNAS_NECESSARIAS - set(idx)
    if faltantes:
        raise ValueError(
            "Colunas não encontradas na planilha (aba '" + aba + "'): "
            + ", ".join(sorted(faltantes))
        )

    i_ordem, i_guia = idx["NU_ORDEM"], idx["NU_GUIA"]
    i_cd, i_grupo = idx["CD_PROCEDIMENTO"], idx["DS_GRUPO"]
    i_lib, i_dt = idx["LIBERACAO"], idx["DT_CREATED_AT"]

    registros = []
    mes_referencia = None
    total_bruto = 0
    for linha in linhas:
        if linha[i_ordem] is None:
            continue
        total_bruto += 1
        if mes_referencia is None and linha[i_dt] is not None:
            dt = linha[i_dt]
            mes_referencia = dt.strftime("%Y-%m") if hasattr(dt, "strftime") else str(dt)[:7]

        liberacao = str(linha[i_lib] or "").strip().upper()
        if liberacao != "N":
            continue

        registros.append({
            "nu_ordem": str(int(linha[i_ordem])),
            "nu_guia": str(linha[i_guia]).strip(),
            "cd_procedimento": str(linha[i_cd]).strip(),
            "ds_grupo": str(linha[i_grupo]).strip(),
            "liberacao": "N",
            "mes_referencia": None,
        })

    wb.close()

    if mes_referencia is None:
        raise ValueError("Não foi possível ler DT_CREATED_AT para determinar o mês de referência.")

    for registro in registros:
        registro["mes_referencia"] = mes_referencia

    return registros, mes_referencia, total_bruto


def _guias_para_df(guias: list) -> pd.DataFrame:
    """Converte o retorno do Supabase para o mesmo formato que
    parse_powerbi() produz, pra reaproveitar consolidar_por_guia/marcar_amostra."""
    if not guias:
        return pd.DataFrame()
    return pd.DataFrame({
        "Especialidade": [g["ds_grupo"] for g in guias],
        "CD_PROCEDIMENTO": [g["cd_procedimento"] for g in guias],
        "NU_GUIA": [g["nu_guia"] for g in guias],
        "Qtde": 1,
    })


# --------------------------------------------------------------------- UI ----

st.title("Amostragem de Guias")
st.caption(
    "Digite o número do processo — as guias com LIBERAÇÃO = N são buscadas "
    "automaticamente na base importada mensalmente. Prestador e percentuais "
    "continuam só no PowerBI."
)

aba_busca, aba_config = st.tabs(["Amostragem", "Configurações"])

with aba_config:
    gerenciar_procedimentos_ignorados(st.session_state.db, key_prefix="amostragem_beta")

    if _is_admin:
        with st.expander("Importar planilha mensal da base IA (Admin)", expanded=False):
            st.caption(
                "Sobe a planilha do mês (mesma que alimenta o PowerBI). Substitui "
                "os dados do mês detectado e mantém só os 2 meses mais recentes na base."
            )
            arquivo = st.file_uploader("Planilha mensal (.xlsx)", type=["xlsx"], key="upload_base_ia")
            if arquivo and st.button("Importar"):
                try:
                    with st.spinner("Lendo e importando (pode levar alguns minutos)..."):
                        registros, mes_referencia, total_bruto = _preparar_registros(arquivo)
                        if not registros:
                            st.warning("Nenhuma linha com LIBERAÇÃO = N encontrada nesta planilha.")
                        else:
                            total_inserido = st.session_state.db.importar_base_ia(registros, mes_referencia)
                            st.success(
                                f"Mês {mes_referencia}: {total_inserido} de {total_bruto} linha(s) "
                                f"(LIBERAÇÃO = N) importadas com sucesso."
                            )
                except ValueError as erro:
                    st.error(str(erro))

with aba_busca:
    processo_digitado = st.text_input("Número do processo", placeholder="Ex: 8202650447")
    buscar = st.button("Buscar guias")

    if buscar:
        st.session_state["_amostragem_beta_processo"] = processo_digitado.strip()

    processo_ativo = st.session_state.get("_amostragem_beta_processo", "")

    if not processo_ativo:
        st.info("Digite o número do processo e clique em Buscar guias.")
        st.stop()

    guias = st.session_state.db.buscar_guias_ia_por_processo(processo_ativo)
    df = _guias_para_df(guias)

    if df.empty:
        st.warning(
            f"Nenhuma guia com LIBERAÇÃO = N encontrada para o processo "
            f"'{processo_ativo}' na base importada. Confira o número ou se o "
            f"mês do processo ainda está entre os 2 meses mantidos na base."
        )
        st.stop()

    st.success(f"Processo {processo_ativo}: {len(df)} item(ns) com LIBERAÇÃO = N.")

    # --- Filtro opcional: procedimentos que não precisam ser analisados ---
    # (ex.: coroas provisórias). O procedimento some da contagem e do sorteio;
    # a guia continua listada mesmo que fique sem nenhum procedimento restante.
    # A seleção pode ser salva como padrão (por especialidade), aplicado
    # automaticamente nas próximas análises.
    codigos_excluidos = selecionar_procedimentos_ignorados(
        df, st.session_state.db, key_prefix=f"amostragem_beta_{processo_ativo}"
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
        if norm in ORDEM_CRITICAS:
            return (0, ORDEM_CRITICAS.index(norm))
        if especialidade_tem_critico.get(e):
            return (1, norm)
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
    st.caption("Clique no número da guia para copiar.")

    for esp in especialidades:
        df_esp_total = df[df["Especialidade"] == esp]
        df_esp_guias = df_guias[df_guias["Especialidade"] == esp].reset_index(drop=True)
        total_procs = int(df_esp_total["Qtde"].sum())
        total_guias = len(df_esp_guias)

        st.markdown(f"#### {esp}")
        st.caption(f"{total_guias} guia(s), {total_procs} proc(s)")

        with st.expander(f"Tabela completa — {total_guias} guia(s)", expanded=False):
            renderizar_tabela_guias(df_esp_guias, esp, objetivo=total_guias, guias_vistas=guias_vistas)

        if _norm(esp) in REGRAS_AMOSTRAGEM:
            df_amostra = marcar_amostra(df_esp_guias, esp, df_esp_total, seed=SEED_PADRAO)
            n_objetivo = len(df_amostra)
            # Prótese sempre audita 100% das guias (regra "todas") — a
            # "Sugestão de amostra" ficaria idêntica à "Tabela completa",
            # então some daqui especificamente pra essa especialidade (as
            # demais com regra "todas", como Implante, continuam mostrando
            # normalmente por enquanto).
            if _norm(esp) != "PROTESE":
                with st.expander(f"Sugestão de amostra — {n_objetivo} guia(s)", expanded=False):
                    renderizar_tabela_guias(
                        df_amostra.drop(columns=["Motivo"], errors="ignore"),
                        esp,
                        objetivo=n_objetivo,
                        guias_vistas=guias_vistas,
                    )
        elif especialidade_tem_critico.get(esp):
            # Especialidade fora das regras de amostragem, mas com
            # procedimento crítico presente: a "Sugestão de amostra" mostra
            # só as guias com esse procedimento, não as 100% da especialidade.
            df_criticas = guias_com_proc_critico(df_esp_guias, procedimentos_criticos)
            with st.expander(f"Sugestão de amostra — {len(df_criticas)} guia(s) com procedimento crítico", expanded=False):
                renderizar_tabela_guias(df_criticas, esp, objetivo=len(df_criticas), guias_vistas=guias_vistas)
        # Sem regra de amostragem e sem procedimento crítico presente: sem
        # seção de "Sugestão de amostra" (hoje mostraria 100% das guias,
        # igual à Tabela completa, sem utilidade nenhuma).
