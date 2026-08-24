import streamlit as st
import pdfplumber
import re
import unicodedata
import pandas as pd
import io

from core.relatorio_5201 import carregar_dados_atuais
from core.settings import tem_acesso_modulo
from shared.database import DatabaseManager
from shared.ui import fmt_num

st.set_page_config(page_title="Análise de Produção", page_icon="🦷", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar esta ferramenta.")
    st.stop()

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()

_role = st.session_state.get("role_interno", "Contas")
_usuario_id = st.session_state.get("usuario_id")
_permissoes = st.session_state.db.carregar_permissoes_modulos()
_excecoes = st.session_state.db.carregar_excecoes_modulos()
if not tem_acesso_modulo(_permissoes, _role, "producao", _usuario_id, _excecoes):
    st.error("Você não tem permissão para acessar este módulo.")
    st.stop()

st.title("Análise de produção do prestador")
st.caption("Envie um ou mais demonstrativos pdf para contar e ranquear os procedimentos mais realizados pelo prestador.")

# Funções de Backend adaptadas para in-memory (BytesIO)
def extrair_nome_prestador(texto):
    m = re.search(r"Nome:\s*(.+)", texto)
    return m.group(1).strip() if m else "Prestador não identificado"

def extrair_linhas_demonstrativo(pdf_file):
    linhas = []
    with pdfplumber.open(pdf_file) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            for linha in texto.splitlines():
                lin = re.sub(r"\s+", " ", linha).strip()
                if lin:
                    linhas.append(lin)
    return linhas

def extrair_procedimento(linha):
    linha = re.sub(r"\s+", " ", (linha or "").strip())
    if not linha or "DEMONSTRATIVO DE PAGAMENTO" in linha.upper():
        return None
    if not re.search(r"\d{2}/\d{2}/\d{4}", linha):
        return None
    
    linha_regex = unicodedata.normalize("NFKD", linha).encode("ascii", "ignore").decode("ascii")
    linha_regex = re.sub(r"\s+", " ", linha_regex).strip()
    
    padrao = re.compile(r"\d{2}/\d{2}/\d{4}\s+\d+\s+(\d{3,4})\s*([A-Za-z0-9/\-\.\(\) ]+?)\s+\d{1,2}\s+\d{1,2}(?:\s+[A-Z]{1,4})?\s+[\d\.,]+\s+[\d\.,]+\s+[\d\.,]+\s*$")
    m = padrao.search(linha_regex)
    if not m:
        return None
        
    codigo = m.group(1).strip()
    codigo_normalizado = str(int(codigo)) if codigo.isdigit() else codigo
    descricao = re.sub(r"\s+", " ", (m.group(2) or "").strip())
    
    if len(descricao) < 3:
        return None
        
    nums = re.findall(r"[\d\.]+,[0-9]{2}", linha_regex)
    valor_pago = 0.0
    if len(nums) >= 2:
        try:
            valor_pago = float(nums[-2].replace(".", "").replace(",", "."))
        except:
            pass
            
    return {"codigo": codigo_normalizado, "descricao": descricao, "valor_pago": valor_pago}

def norm_prest(nome):
    return unicodedata.normalize('NFKD', nome).encode('ascii', 'ignore').decode('ascii').upper().strip()

def processar_arquivos(uploaded_files):
    contador = {}
    valores = {}
    total_linhas = 0
    prestadores = []
    detalhes_pdf = []
    grupos_prestador = []
    
    for arquivo in uploaded_files:
        linhas = extrair_linhas_demonstrativo(arquivo)
        if not linhas:
            continue
            
        prestador = extrair_nome_prestador("\n".join(linhas[:20]))
        prestadores.append(prestador)
        
        prest_norm = norm_prest(prestador)
        if prest_norm:
            grupo_existente = next((g for g in grupos_prestador if norm_prest(g['nome']) == prest_norm), None)
            if grupo_existente is None:
                grupos_prestador.append({'nome': prestador, 'arquivos': [arquivo.name]})
            else:
                grupo_existente['arquivos'].append(arquivo.name)
                
        lidas_pdf = 0
        for linha in linhas:
            item = extrair_procedimento(linha)
            if not item: continue
            
            chave = f"{item['codigo']} - {item['descricao']}"
            contador[chave] = contador.get(chave, 0) + 1
            valores[chave] = valores.get(chave, 0.0) + item.get("valor_pago", 0.0)
            total_linhas += 1
            lidas_pdf += 1
            
        detalhes_pdf.append((arquivo.name, prestador, lidas_pdf))
        
    if len(grupos_prestador) > 1:
        descricoes = [f"{g['nome']} ({len(g['arquivos'])} arquivo(s))" for g in grupos_prestador[:3]]
        return None, f"Foram enviados arquivos de múltiplos prestadores: {'; '.join(descricoes)}. Envie apenas os demonstrativos de um prestador por vez."
        
    if not contador:
        return None, "Nenhuma linha de procedimento foi identificada."
        
    prestador_final = grupos_prestador[0]['nome'] if grupos_prestador else prestadores[0]
    ranking = sorted(contador.items(), key=lambda kv: (-kv[1], kv[0]))

    return {
        "prestador": prestador_final,
        "qtd_fontes": len(uploaded_files),
        "rotulo_fontes": "Total de PDFs",
        "rotulo_resumo_fontes": "PDFs analisados",
        "total_linhas": total_linhas,
        "ranking": ranking,
        "valores": valores,
        "detalhes_pdf": detalhes_pdf,
        "aviso_valor": None,
    }, None


def montar_dados_processos_manual(lista_processos: list):
    """Mesma estrutura de saída de processar_arquivos(), mas a partir de
    processos buscados manualmente na base (ver buscar_procedimentos_processo)
    em vez de PDFs. `lista_processos`: [{"processo", "prestador", "itens"
    (cd_procedimento/nu_guia crus do Turso), "descricoes" (codigo ->
    descricao/valor_unitario de tabela_procedimentos)}, ...]."""
    contador = {}
    valores = {}
    total_linhas = 0
    detalhes_pdf = []

    for p in lista_processos:
        lidas = 0
        for item in p["itens"]:
            codigo = str(item.get("cd_procedimento", "")).strip()
            if not codigo:
                continue
            info = p["descricoes"].get(codigo)
            descricao = info["descricao"] if info else "Descrição não cadastrada"
            valor_unitario = float(info["valor_unitario"]) if info and info.get("valor_unitario") is not None else 0.0

            chave = f"{codigo} - {descricao}"
            contador[chave] = contador.get(chave, 0) + 1
            valores[chave] = valores.get(chave, 0.0) + valor_unitario
            total_linhas += 1
            lidas += 1
        detalhes_pdf.append((p["processo"], p["prestador"], lidas))

    if not contador:
        return None, "Nenhum procedimento encontrado nos processos adicionados."

    prestador_final = next(
        (p["prestador"] for p in lista_processos if p["prestador"] != "Prestador não identificado"),
        lista_processos[0]["prestador"],
    )
    ranking = sorted(contador.items(), key=lambda kv: (-kv[1], kv[0]))

    return {
        "prestador": prestador_final,
        "qtd_fontes": len(lista_processos),
        "rotulo_fontes": "Total de Processos",
        "rotulo_resumo_fontes": "Processos analisados",
        "total_linhas": total_linhas,
        "ranking": ranking,
        "valores": valores,
        "detalhes_pdf": detalhes_pdf,
        "aviso_valor": (
            "Valor de TABELA (tabela_procedimentos), não o valor efetivamente pago -- "
            "esse só vem do demonstrativo de pagamento em PDF."
        ),
    }, None

def _renderizar_resultado(dados: dict, key_prefix: str):
    """Renderiza Visão Geral + Top 10 + Resumo Copiável + CSV -- mesmo
    formato pros dois modos de entrada (upload de PDF ou busca por
    processo), já que ambos produzem a mesma estrutura de `dados` (ver
    processar_arquivos / montar_dados_processos_manual)."""
    st.success("Análise concluída com sucesso!")

    if dados.get("aviso_valor"):
        st.info(dados["aviso_valor"])

    # Métricas principais
    st.markdown("### Visão Geral")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Prestador", dados["prestador"][:20] + "..." if len(dados["prestador"]) > 20 else dados["prestador"])
    c2.metric(dados["rotulo_fontes"], fmt_num(dados["qtd_fontes"]))
    c3.metric("Procedimentos Lidos", fmt_num(dados["total_linhas"]))
    top1 = dados["ranking"][0][0] if dados["ranking"] else "-"
    c4.metric("Top 1", top1[:20] + "..." if len(top1) > 20 else top1)

    st.divider()

    rotulo_valor = "Vl. de tabela somado" if dados.get("aviso_valor") else "Vl. pago somado"
    coluna_valor_csv = "Valor de Tabela (R$)" if dados.get("aviso_valor") else "Valor Pago (R$)"

    # Construir Resumo em Texto
    linhas_resumo = [
        f"Prestador: {dados['prestador']}",
        f"{dados['rotulo_resumo_fontes']}: {dados['qtd_fontes']}",
        f"Total de linhas/procedimentos: {dados['total_linhas']}",
        "",
        "Ranking dos procedimentos mais solicitados:"
    ]

    ranking_para_csv = []

    col_lista, col_resumo = st.columns([1.2, 1.8])

    with col_lista:
        st.markdown("### Top 10 Produzidos")
        for pos, (procedimento, qtd) in enumerate(dados["ranking"][:10], 1):
            pct = (qtd / dados["total_linhas"]) * 100
            valor = dados["valores"].get(procedimento, 0.0)

            st.info(f"**{pos}. {procedimento}**\n\n{qtd} proc. ({pct:.1f}%) | {rotulo_valor}: R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    for pos, (procedimento, qtd) in enumerate(dados["ranking"], 1):
        pct = (qtd / dados["total_linhas"]) * 100
        valor = dados["valores"].get(procedimento, 0.0)
        linhas_resumo.append(f"{pos}. {procedimento} - {qtd} proc(s) ({pct:.1f}%) | {rotulo_valor}: R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        ranking_para_csv.append({
            "Posição": pos,
            "Procedimento": procedimento,
            "Quantidade": qtd,
            "Percentual (%)": f"{pct:.2f}",
            coluna_valor_csv: f"{valor:.2f}"
        })

    if dados["detalhes_pdf"]:
        linhas_resumo.extend(["", "Resumo por fonte:"])
        for arq, prest, lidas in dados["detalhes_pdf"]:
            linhas_resumo.append(f"- {arq}: {lidas} valida(s) | {prest}")

    texto_resumo = "\n".join(linhas_resumo)

    with col_resumo:
        st.markdown("### Resumo Copiável")
        st.text_area("Texto para anexar:", texto_resumo, height=400, key=f"{key_prefix}_texto_resumo")

        df_csv = pd.DataFrame(ranking_para_csv)
        csv_data = df_csv.to_csv(index=False, sep=";").encode("utf-8-sig")

        st.download_button(
            label=" Exportar Ranking Completo em CSV",
            data=csv_data,
            file_name="ranking_producao.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"{key_prefix}_download_csv",
        )


# UI
tab_pdf, tab_processo = st.tabs(["Upload de PDF", "Buscar por processo"])

with tab_pdf:
    uploaded_files = st.file_uploader("Faça upload do arquivo aqui", type=["pdf"], accept_multiple_files=True)

    if uploaded_files:
        if st.button("Processar Produção", type="primary"):
            with st.spinner(f"Processando {len(uploaded_files)} arquivo(s)..."):
                dados, erro = processar_arquivos(uploaded_files)
                if erro:
                    st.error(erro)
                else:
                    st.session_state["_producao_dados_pdf"] = dados

        if "_producao_dados_pdf" in st.session_state:
            _renderizar_resultado(st.session_state["_producao_dados_pdf"], key_prefix="pdf")

with tab_processo:
    st.caption(
        "Busca os procedimentos direto da base (só ficam os 2 meses mais recentes). "
        "O valor mostrado é o de tabela, não o valor efetivamente pago -- isso só vem do "
        "demonstrativo de pagamento em PDF."
    )
    if "producao_processos_manual" not in st.session_state:
        st.session_state["producao_processos_manual"] = []

    col_input, col_btn = st.columns([3, 1])
    with col_input:
        novo_processo = st.text_input(
            "Número do processo", key="producao_novo_processo", placeholder="Ex: 8202655958",
        )
    with col_btn:
        st.write("")
        adicionar = st.button("Adicionar processo", key="producao_btn_adicionar", use_container_width=True)

    if adicionar:
        processo_limpo = novo_processo.strip()
        processos_atuais = st.session_state["producao_processos_manual"]
        if not processo_limpo:
            st.warning("Digite o número do processo.")
        elif any(p["processo"] == processo_limpo for p in processos_atuais):
            st.warning(f"Processo {processo_limpo} já foi adicionado.")
        else:
            with st.spinner(f"Buscando processo {processo_limpo}..."):
                itens_raw = st.session_state.db.buscar_procedimentos_processo(processo_limpo)
            if not itens_raw:
                st.error(
                    f"Processo {processo_limpo} não encontrado na base (só ficam os 2 meses mais "
                    "recentes de base_ia_guias -- se for de um mês mais antigo, use o upload de PDF)."
                )
            else:
                codigos = [str(i["cd_procedimento"]) for i in itens_raw]
                descricoes = st.session_state.db.buscar_descricoes_procedimentos(codigos)

                df_rel = carregar_dados_atuais()
                prestador_novo = "Prestador não identificado"
                if not df_rel.empty and "ORDEM" in df_rel.columns and "PRESTADOR" in df_rel.columns:
                    linha_rel = df_rel[df_rel["ORDEM"].astype(str) == processo_limpo]
                    if not linha_rel.empty and str(linha_rel["PRESTADOR"].iloc[0]).strip():
                        prestador_novo = str(linha_rel["PRESTADOR"].iloc[0]).strip()

                prestador_existente = next(
                    (p["prestador"] for p in processos_atuais if p["prestador"] != "Prestador não identificado"),
                    None,
                )
                if (
                    prestador_existente
                    and prestador_novo != "Prestador não identificado"
                    and norm_prest(prestador_existente) != norm_prest(prestador_novo)
                ):
                    st.error(
                        f"Esse processo é de **{prestador_novo}**, mas os já adicionados são de "
                        f"**{prestador_existente}**. Remova os processos atuais antes de trocar de prestador."
                    )
                else:
                    processos_atuais.append({
                        "processo": processo_limpo,
                        "prestador": prestador_novo,
                        "itens": itens_raw,
                        "descricoes": descricoes,
                    })
                    st.success(f"Processo {processo_limpo} adicionado ({len(itens_raw)} item(ns)).")
                    st.rerun()

    processos_atuais = st.session_state["producao_processos_manual"]
    if processos_atuais:
        st.markdown(f"**Processos adicionados ({len(processos_atuais)})**")
        for p in processos_atuais:
            pc1, pc2, pc3, pc4 = st.columns([2, 4, 1.5, 1])
            pc1.markdown(f"**{p['processo']}**")
            pc2.markdown(p["prestador"])
            pc3.markdown(f"{len(p['itens'])} item(ns)")
            if pc4.button("Remover", key=f"remover_processo_{p['processo']}", use_container_width=True):
                st.session_state["producao_processos_manual"] = [
                    x for x in processos_atuais if x["processo"] != p["processo"]
                ]
                st.rerun()

        st.divider()
        dados, erro = montar_dados_processos_manual(processos_atuais)
        if erro:
            st.error(erro)
        else:
            _renderizar_resultado(dados, key_prefix="processo")
    else:
        st.info("Adicione ao menos um processo pra ver a análise.")
