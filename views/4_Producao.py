import streamlit as st
import pdfplumber
import re
import unicodedata
import pandas as pd
import io

from core.settings import tem_acesso_modulo
from shared.database import DatabaseManager

st.set_page_config(page_title="Análise de Produção", page_icon="", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar esta ferramenta.")
    st.stop()

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()

_role = st.session_state.get("role_interno", "Contas")
_permissoes = st.session_state.db.carregar_permissoes_modulos()
if not tem_acesso_modulo(_permissoes, _role, "producao"):
    st.error("Você não tem permissão para acessar este módulo.")
    st.stop()

st.title("Análise de Produção")
st.markdown("Envie um ou mais demonstrativos pdf para contar e ranquear os procedimentos mais realizados pelo prestador.")

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
        "qtd_pdfs": len(uploaded_files),
        "total_linhas": total_linhas,
        "ranking": ranking,
        "valores": valores,
        "detalhes_pdf": detalhes_pdf
    }, None

# UI
uploaded_files = st.file_uploader("Faça upload do arquivo aqui", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    if st.button("Processar Produção", type="primary"):
        with st.spinner(f"Processando {len(uploaded_files)} arquivo(s)..."):
            dados, erro = processar_arquivos(uploaded_files)
            
            if erro:
                st.error(erro)
            else:
                st.success("Análise concluída com sucesso!")
                
                # Métricas principais
                st.markdown("### Visão Geral")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Prestador", dados["prestador"][:20] + "..." if len(dados["prestador"]) > 20 else dados["prestador"])
                c2.metric("Total de PDFs", dados["qtd_pdfs"])
                c3.metric("Procedimentos Lidos", dados["total_linhas"])
                top1 = dados["ranking"][0][0] if dados["ranking"] else "-"
                c4.metric("Top 1", top1[:20] + "..." if len(top1) > 20 else top1)
                
                st.divider()
                
                # Construir Resumo em Texto
                linhas_resumo = [
                    f"Prestador: {dados['prestador']}",
                    f"PDFs analisados: {dados['qtd_pdfs']}",
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
                        
                        st.info(f"**{pos}. {procedimento}**\n\n{qtd} proc. ({pct:.1f}%) | Soma Pago: R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                        
                for pos, (procedimento, qtd) in enumerate(dados["ranking"], 1):
                    pct = (qtd / dados["total_linhas"]) * 100
                    valor = dados["valores"].get(procedimento, 0.0)
                    linhas_resumo.append(f"{pos}. {procedimento} - {qtd} proc(s) ({pct:.1f}%) | Vl. pago somado: R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    ranking_para_csv.append({
                        "Posição": pos,
                        "Procedimento": procedimento,
                        "Quantidade": qtd,
                        "Percentual (%)": f"{pct:.2f}",
                        "Valor Pago (R$)": f"{valor:.2f}"
                    })
                    
                if dados["detalhes_pdf"]:
                    linhas_resumo.extend(["", "Resumo por arquivo:"])
                    for arq, prest, lidas in dados["detalhes_pdf"]:
                        linhas_resumo.append(f"- {arq}: {lidas} valida(s) | {prest}")
                        
                texto_resumo = "\n".join(linhas_resumo)
                
                with col_resumo:
                    st.markdown("### Resumo Copiável")
                    st.text_area("Texto para anexar:", texto_resumo, height=400)
                    
                    df_csv = pd.DataFrame(ranking_para_csv)
                    csv_data = df_csv.to_csv(index=False, sep=";").encode("utf-8-sig")
                    
                    st.download_button(
                        label=" Exportar Ranking Completo em CSV",
                        data=csv_data,
                        file_name="ranking_producao.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
