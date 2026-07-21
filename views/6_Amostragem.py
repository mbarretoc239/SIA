import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from core.settings import tem_acesso_modulo
from shared.database import DatabaseManager
from core.amostragem import (
    ORDEM_CRITICAS,
    _norm,
    parse_powerbi,
    consolidar_por_guia,
    marcar_amostra,
    renderizar_tabela_guias,
    selecionar_procedimentos_ignorados,
    gerenciar_procedimentos_ignorados,
)

st.set_page_config(page_title="Amostragem", page_icon="", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar esta ferramenta.")
    st.stop()

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()


# --------------------------------------------------------------------- UI ----

st.title("Amostragem de Guias")
st.markdown(
    "Cole as guias por especialidade selecionadas no powerBI"
)

_is_admin = st.session_state.get("role_interno") == "Admin"

aba_busca, aba_config = st.tabs(["Amostragem", "Configurações"])

with aba_config:
    gerenciar_procedimentos_ignorados(st.session_state.db, key_prefix="amostragem")

with aba_busca:
    # Versão da key do text_area: usada para "resetar" o widget no clique do Limpar
    # (Streamlit não limpa widget só removendo do session_state após render).
    if "texto_powerbi_v" not in st.session_state:
        st.session_state["texto_powerbi_v"] = 0
    # Seed da amostra. Cliques no "Gerar amostra" geram um novo seed aleatório.
    if "seed_amostra" not in st.session_state:
        st.session_state["seed_amostra"] = 42

    texto = st.text_area(
        "Texto copiado do PowerBI",
        height=200,
        key=f"texto_powerbi_v{st.session_state['texto_powerbi_v']}",
        placeholder=(
            "CRITICIDADE\tDS_GRUPO\tCD_PROCEDIMENTO\tNU_GUIA\tLIBERAÇÃO\tQtde itens\n"
            "SIM\tCIRURGIA\t5010\t26996546\tS\t1\n"
            "SIM\tCIRURGIA\t5030\t27294440\tS\t1\n..."
        ),
    )

    if _is_admin:
        col_limpar, col_gerar, col_seed, _ = st.columns([1, 1, 1, 2])
        with col_limpar:
            limpar = st.button("Limpar", use_container_width=True)
        with col_gerar:
            gerar_amostra = st.button("Gerar amostra", use_container_width=True)
        with col_seed:
            seed = st.number_input(
                "Seed do sorteio",
                min_value=0,
                max_value=9999,
                value=int(st.session_state["seed_amostra"]),
                step=1,
                help="Trocar o seed gera outra amostra aleatória.",
            )
            st.session_state["seed_amostra"] = int(seed)
    else:
        col_limpar, col_gerar, _ = st.columns([1, 1, 3])
        with col_limpar:
            limpar = st.button("Limpar", use_container_width=True)
        with col_gerar:
            gerar_amostra = st.button("Gerar amostra", use_container_width=True)
        seed = int(st.session_state["seed_amostra"])

    if limpar:
        st.session_state["texto_powerbi_v"] += 1
        st.session_state["limpar_marcas_pendente"] = True
        st.rerun()

    if st.session_state.pop("limpar_marcas_pendente", False):
        components.html(
            "<script>"
            "Object.keys(localStorage).filter(k => k.startsWith('amostragem_guia_vista_'))"
            ".forEach(k => localStorage.removeItem(k));"
            "</script>",
            height=0,
        )

    if gerar_amostra:
        import random
        novo = random.randint(0, 9999)
        if novo == int(st.session_state["seed_amostra"]):
            novo = (novo + 1) % 10000
        st.session_state["seed_amostra"] = novo
        st.rerun()

    if not texto.strip():
        st.info("Cole o texto e o resultado aparece aqui.")
        st.stop()

    df = parse_powerbi(texto)

    if df.empty:
        st.warning(
            "Nenhuma linha válida encontrada. Esperado: TSV com colunas "
            "(DS_GRUPO ou Especialidade), CD_PROCEDIMENTO, NU_GUIA, LIBERAÇÃO, Qtde itens. "
            "O cabeçalho pode vir junto ou não. Linhas com NU_GUIA vazio são ignoradas."
        )
        st.stop()

    # --- Filtro opcional: procedimentos que não precisam ser analisados ---
    # (ex.: coroas provisórias). O procedimento some da contagem e do sorteio;
    # a guia continua listada mesmo que fique sem nenhum procedimento restante.
    # A seleção pode ser salva como padrão (por especialidade), aplicado
    # automaticamente nas próximas análises.
    codigos_excluidos = selecionar_procedimentos_ignorados(
        df, st.session_state.db, key_prefix=f"amostragem_v{st.session_state['texto_powerbi_v']}"
    )

    todas_guias = df[["Especialidade", "NU_GUIA"]].drop_duplicates()
    df = df[~df["CD_PROCEDIMENTO"].isin(codigos_excluidos)] if codigos_excluidos else df

    df_guias = consolidar_por_guia(df)
    if codigos_excluidos:
        df_guias = todas_guias.merge(df_guias, on=["Especialidade", "NU_GUIA"], how="left")
        df_guias["Procedimentos"] = df_guias["Procedimentos"].fillna("")
        df_guias["Qtde_procs"] = df_guias["Qtde_procs"].fillna(0).astype(int)

    guias_vistas = st.session_state.db.buscar_guias_vistas(df_guias["NU_GUIA"].unique().tolist())

    especialidades = df_guias["Especialidade"].unique().tolist()
    especialidades.sort(
        key=lambda e: (
            ORDEM_CRITICAS.index(_norm(e)) if _norm(e) in ORDEM_CRITICAS else 999,
            _norm(e),
        )
    )

    # --- Resumo ---
    resumo = []
    for esp in especialidades:
        df_esp_total = df[df["Especialidade"] == esp]
        df_esp_guias = df_guias[df_guias["Especialidade"] == esp].reset_index(drop=True)
        total_procs = int(df_esp_total["Qtde"].sum())
        total_guias = len(df_esp_guias)
        df_amostra_resumo = marcar_amostra(df_esp_guias, esp, df_esp_total, seed=int(seed))
        resumo.append({
            "Especialidade": esp,
            "Guias únicas": total_guias,
            "Total de procs": total_procs,
            "Amostra sugerida": len(df_amostra_resumo),
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

        df_amostra = marcar_amostra(df_esp_guias, esp, df_esp_total, seed=int(seed))
        n_objetivo = len(df_amostra)

        st.markdown(f"#### {esp}")
        st.caption(f"{total_guias} guia(s), {total_procs} proc(s)")

        with st.expander(f"Tabela completa — {total_guias} guia(s)", expanded=False):
            renderizar_tabela_guias(df_esp_guias, esp, objetivo=n_objetivo, guias_vistas=guias_vistas)

        with st.expander(f"Sugestão de amostra — {n_objetivo} guia(s)", expanded=False):
            renderizar_tabela_guias(
                df_amostra.drop(columns=["Motivo"], errors="ignore"),
                esp,
                objetivo=n_objetivo,
                guias_vistas=guias_vistas,
            )
