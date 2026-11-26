"""Fila operacional (beta): quem está em cada processo. Regras em core/fila_operacional.py."""
import hashlib

import pandas as pd
import streamlit as st

from core import fila_operacional as fila
from core.settings import carregar_excecoes_modulos_cache, carregar_permissoes_modulos_cache, tem_acesso_modulo

role = st.session_state.get("role_interno")
if not tem_acesso_modulo(
    carregar_permissoes_modulos_cache(), role, fila.MODULO,
    st.session_state.get("usuario_id"), carregar_excecoes_modulos_cache(),
):
    st.error("A Fila operacional está liberada só para usuários autorizados.")
    st.stop()

db = st.session_state.db
cache = fila.cache_da_fila()
login = str(st.session_state.get("usuario_sigo") or "").upper()
nome = str(st.session_state.get("auditor_nome") or login)

FILTROS = ["Todos", "Livres", "Meus", "Em andamento", "Concluídos"]


def _avisar(tipo: str, texto: str) -> None:
    st.session_state["_fila_aviso"] = (tipo, texto)


def _executar(acao, sucesso: str, processo: str, *args) -> None:
    """Callback dos botões: grava e deixa o aviso pro desenho seguinte."""
    try:
        gravou, atual = acao(db, cache, processo, *args)
    except Exception as erro:
        _avisar("error", f"Não foi possível gravar. Tente de novo. ({erro})")
        return
    if gravou:
        _avisar("success", sucesso)
    elif atual is None:
        _avisar("warning", f"O processo {processo} não está mais na fila.")
    elif acao is fila.assumir and atual.get("auditor_nome"):
        quando = fila.hora_brt(atual.get("assumido_em"))
        _avisar(
            "warning",
            f"O processo {processo} acabou de ser assumido por {atual['auditor_nome']}"
            f"{f', às {quando}' if quando else ''}. Escolha outro.",
        )
    else:
        _avisar("warning", f"O processo {processo} mudou enquanto você olhava. Confira a situação atual.")


def _salvar_observacoes(processo: str, antes: dict, marca: str) -> None:
    novos = {
        "obs_contas": (st.session_state[f"fila_obs_contas_{marca}"] or "").strip() or None,
        "obs_auditoria": (st.session_state[f"fila_obs_auditoria_{marca}"] or "").strip() or None,
        "sem_biometria": st.session_state[f"fila_sem_bio_{marca}"],
    }
    # grava só o que a pessoa mudou, pra não passar por cima do que outra anotou
    alterados = {k: v for k, v in novos.items() if v != antes.get(k)}
    if alterados:
        _executar(fila.salvar_observacoes, "Observações salvas.", processo, alterados, login)


def _pedir_motivo(processo: str | None) -> None:
    st.session_state["_fila_liberando"] = processo


def _confirmar_liberacao(processo: str) -> None:
    motivo = (st.session_state.get(f"fila_motivo_{processo}") or "").strip()
    if not motivo:
        _avisar("warning", "Informe o motivo pra liberar o processo.")
        return
    _pedir_motivo(None)
    _executar(fila.liberar, f"Processo {processo} voltou a ficar livre.", processo, motivo, login, nome)


def _liberacao(linha: dict) -> str:
    if not linha.get("liberado_motivo"):
        return ""
    return f"{linha.get('liberado_por')} ({fila.hora_brt(linha.get('liberado_em'))}): {linha['liberado_motivo']}"


def _tabela(linhas: list) -> pd.DataFrame:
    return pd.DataFrame([{
        "Processo": l["processo"],
        "Prestador": l.get("prestador"),
        "Cidade": l.get("cidade"),
        "UF": l.get("uf"),
        "Tipo": l.get("tipo"),
        "Proced": l.get("procedimentos"),
        "Guias": l.get("guias"),
        "Status": l.get("status") or fila.situacao(l),
        "Auditor": l.get("auditor_nome"),
        "Desde": fila.hora_brt(l.get("assumido_em")),
        "OBS Contas": l.get("obs_contas"),
        "OBS Auditoria": l.get("obs_auditoria"),
        "S/ biometria": l.get("sem_biometria"),
        "Última liberação": _liberacao(l),
    } for l in linhas]).astype({"Proced": "Int64", "Guias": "Int64", "S/ biometria": "Int64"})


def _painel_do_processo(linha: dict) -> None:
    processo = linha["processo"]
    estado = fila.situacao(linha)
    quem = linha.get("auditor_nome") or "sem auditor informado"
    with st.container(border=True):
        st.markdown(f"**Processo {processo}** · {linha.get('prestador') or ''}")

        # processo de outra pessoa: só o aviso de com quem está, sem nenhuma ação
        if not fila.pode_mexer(linha, login):
            if estado == fila.CONCLUIDO:
                quando = fila.hora_brt(linha.get("concluido_em"))
                st.info(f"{linha['status']} por {quem}{f' ({quando})' if quando else ''}.")
            else:
                desde = fila.hora_brt(linha.get("assumido_em"))
                st.warning(f"Este processo já está com {quem}{f' desde {desde}' if desde else ''}.")
            return

        if linha.get("liberado_motivo"):
            st.caption("Última liberação")
            st.text(_liberacao(linha))

        if estado == fila.LIVRE:
            st.button(
                "Assumir", type="primary", key=f"fila_assumir_{processo}", on_click=_executar,
                args=(fila.assumir, f"Processo {processo} está com você.", processo, login, nome),
            )
        elif estado == fila.EM_ANDAMENTO:
            st.caption("Em andamento com você.")
            col_status, col_concluir, col_liberar = st.columns([2, 1, 1], vertical_alignment="bottom")
            status = col_status.selectbox(
                "Status", fila.STATUS_FINAIS, index=None, placeholder="Escolha ao terminar",
                key=f"fila_status_{processo}",
            )
            col_concluir.button(
                "Concluir", type="primary", disabled=status is None, use_container_width=True,
                key=f"fila_concluir_{processo}", on_click=_executar,
                args=(fila.concluir, f"Processo {processo} concluído.", processo, status, login),
            )
            col_liberar.button(
                "Liberar", use_container_width=True, key=f"fila_liberar_{processo}",
                on_click=_pedir_motivo, args=(processo,),
            )
            if st.session_state.get("_fila_liberando") == processo:
                with st.form(f"fila_liberacao_{processo}", border=False):
                    st.text_input(
                        "Motivo da liberação", key=f"fila_motivo_{processo}", max_chars=300,
                        placeholder="Ex.: processo direcionado para outra pessoa",
                    )
                    col_confirmar, col_cancelar, _ = st.columns([1, 1, 2])
                    col_confirmar.form_submit_button(
                        "Confirmar liberação", use_container_width=True,
                        on_click=_confirmar_liberacao, args=(processo,),
                    )
                    col_cancelar.form_submit_button(
                        "Cancelar", use_container_width=True, on_click=_pedir_motivo, args=(None,),
                    )
        else:
            quando = fila.hora_brt(linha.get("concluido_em"))
            st.info(f"{linha['status']} por {quem}{f' ({quando})' if quando else ''}.")
            if linha.get("auditor_nome"):
                st.button(
                    "Reabrir", key=f"fila_reabrir_{processo}", on_click=_executar,
                    args=(fila.reabrir, f"Processo {processo} reaberto.", processo, login),
                )

        if st.button("Abrir na Amostragem", key=f"fila_abrir_{processo}"):
            st.session_state["_amostragem_beta_processo"] = processo
            st.session_state["amostragem_processo_input"] = processo
            st.switch_page("views/7_Amostragem_Beta.py")

        # os campos são recriados quando outra pessoa muda uma observação, senão
        # o valor antigo continuaria na caixa e seria gravado por cima
        guardados = f"{linha.get('obs_contas')}|{linha.get('obs_auditoria')}|{linha.get('sem_biometria')}"
        marca = f"{processo}_{hashlib.md5(guardados.encode()).hexdigest()[:8]}"
        with st.form(f"fila_obs_{processo}", border=False):
            col_contas, col_auditoria, col_bio = st.columns([2, 2, 1])
            col_contas.text_input(
                "OBS Contas", value=linha.get("obs_contas") or "", key=f"fila_obs_contas_{marca}"
            )
            col_auditoria.text_input(
                "OBS Auditoria", value=linha.get("obs_auditoria") or "", key=f"fila_obs_auditoria_{marca}"
            )
            col_bio.number_input(
                "Qtd. sem biometria", min_value=0, step=1, value=linha.get("sem_biometria"),
                key=f"fila_sem_bio_{marca}",
            )
            st.form_submit_button(
                "Salvar observações", on_click=_salvar_observacoes, args=(processo, linha, marca)
            )


@st.fragment(run_every=fila.INTERVALO_SEGUNDOS)
def painel() -> None:
    try:
        cache.sincronizar(db)
    except Exception:
        st.warning("Não consegui atualizar a fila agora. A lista pode estar desatualizada.")

    aviso = st.session_state.pop("_fila_aviso", None)
    if aviso:
        getattr(st, aviso[0])(aviso[1])

    linhas = cache.linhas()
    if not linhas:
        st.info("Nenhum processo na fila.")
        return

    meus_abertos = sum(1 for l in linhas if fila.e_dono(l, login) and fila.situacao(l) == fila.EM_ANDAMENTO)
    concluidos = sum(1 for l in linhas if fila.situacao(l) == fila.CONCLUIDO)

    col_filtro, col_busca = st.columns([3, 2], vertical_alignment="bottom")
    filtro = col_filtro.segmented_control("Mostrar", FILTROS, default="Todos", key="fila_filtro") or "Todos"
    busca = col_busca.text_input("Buscar processo ou prestador", key="fila_busca").strip().lower()
    st.caption(
        f"{concluidos} de {len(linhas)} concluído(s) · você tem {meus_abertos} em andamento · "
        "clique numa linha pra ver as ações."
    )

    por_situacao = {"Livres": fila.LIVRE, "Em andamento": fila.EM_ANDAMENTO, "Concluídos": fila.CONCLUIDO}
    if filtro == "Meus":
        linhas = [l for l in linhas if fila.e_dono(l, login)]
    elif filtro in por_situacao:
        linhas = [l for l in linhas if fila.situacao(l) == por_situacao[filtro]]
    if busca:
        linhas = [l for l in linhas if busca in f"{l['processo']} {l.get('prestador') or ''}".lower()]

    # os meus em andamento no topo; o resto como na planilha (mais procedimentos primeiro)
    linhas.sort(key=lambda l: (
        not (fila.e_dono(l, login) and fila.situacao(l) == fila.EM_ANDAMENTO),
        -(l.get("procedimentos") or 0),
        l["processo"],
    ))

    if linhas:
        ordem = [l["processo"] for l in linhas]
        # a seleção da tabela é um índice de linha: se a ordem muda, a tabela é recriada
        # pra um índice antigo nunca apontar pra outro processo
        marca = hashlib.md5("|".join(ordem).encode()).hexdigest()[:10]
        evento = st.dataframe(
            _tabela(linhas), use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row", key=f"fila_tabela_{marca}",
        )
        escolhidas = evento.selection.get("rows") if evento else []
        if escolhidas and escolhidas[0] < len(ordem):
            st.session_state["_fila_selecionado"] = ordem[escolhidas[0]]
    else:
        st.info("Nenhum processo neste filtro.")

    selecionado = cache.obter(st.session_state.get("_fila_selecionado", ""))
    if selecionado:
        _painel_do_processo(selecionado)


st.title("Fila operacional")
st.caption(f"Versão beta. A lista se atualiza sozinha a cada {fila.INTERVALO_SEGUNDOS} segundos.")

if role == "Admin":
    with st.expander("Publicar processos"):
        arquivo = st.file_uploader("Planilha no formato do time (.xlsx)", type=["xlsx"], key="fila_arquivo")
        if arquivo:
            try:
                registros, avisos = fila.ler_planilha(arquivo)
            except Exception as erro:
                st.error(f"Não consegui ler a planilha. {erro}")
            else:
                st.caption(f"{len(registros)} processo(s) lido(s). Quem já está na fila não é alterado.")
                for texto_aviso in avisos[:10]:
                    st.warning(texto_aviso)
                if len(avisos) > 10:
                    st.caption(f"Mais {len(avisos) - 10} aviso(s) não exibido(s).")
                if st.button("Publicar na fila", type="primary", disabled=not registros):
                    try:
                        novos = db.inserir_fila([{**r, "publicado_por": login} for r in registros])
                        cache.sincronizar(db, completa=True)
                    except Exception as erro:
                        st.error(f"Não foi possível publicar. {erro}")
                    else:
                        st.success(f"{novos} processo(s) novo(s) na fila.")

painel()
