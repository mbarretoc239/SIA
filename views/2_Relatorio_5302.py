import streamlit as st
import pandas as pd

from core.settings import tem_acesso_modulo
from shared.database import DatabaseManager
from services.relatorio_5302.parser_strategy import processar_csv, processar_pdf
from services.relatorio_5302.text_engine import gerar_texto, mixar_textos_inteligente

st.set_page_config(page_title="Relatório 5302", page_icon="", layout="wide")

if not st.session_state.get("logado", False):
    st.warning("Você precisa fazer login na página inicial para acessar esta ferramenta.")
    st.stop()

if "db" not in st.session_state:
    st.session_state.db = DatabaseManager()

_role = st.session_state.get("role_interno", "Contas")
_permissoes = st.session_state.db.carregar_permissoes_modulos()
if not tem_acesso_modulo(_permissoes, _role, "relatorio_5302"):
    st.error("Você não tem permissão para acessar este módulo.")
    st.stop()



def salvar_no_supabase(arquivo_origem, texto_gerado, df_final, meta):
    import requests
    if df_final is None or df_final.empty:
        raise ValueError("Não há glosas para salvar. O processo será ignorado.")
        
    url = st.secrets["supabase"]["url"].rstrip("/")
    key = st.secrets["supabase"]["key"]
    
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    # 1. Verifica duplicatas pelo número do processo (se houver número)
    processo_id = meta.get("processo", "Desconhecido")
    if processo_id != "Desconhecido":
        check_res = requests.get(
            f"{url}/rest/v1/analises_auditoria?select=id&processo=eq.{processo_id}&limit=1",
            headers=headers
        )
        if check_res.ok and len(check_res.json()) > 0:
            raise ValueError(f"O processo {processo_id} já consta no banco de dados!")
    
    # 2. Salva se passou na checagem
    data = {
        "arquivo_origem": arquivo_origem,
        "processo": processo_id,
        "prestador": meta.get("prestador", "Desconhecido"),
        "data_producao": meta.get("producao", "Desconhecida"),
        "texto_gerado": texto_gerado,
        "glosas_json": df_final.fillna("").to_dict(orient="records")
    }
    
    response = requests.post(f"{url}/rest/v1/analises_auditoria", headers=headers, json=data)
    if response.status_code == 403:
        raise ValueError("Permissão negada (Erro 403). Verifique as políticas de RLS no Supabase.")
    response.raise_for_status()

def limpar_banco_supabase(meses=6):
    import requests
    from datetime import datetime, timedelta
    
    url = st.secrets["supabase"]["url"].rstrip("/")
    key = st.secrets["supabase"]["key"]
    
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    
    # Calcula data limite
    data_limite = (datetime.now() - timedelta(days=meses*30)).isoformat()
    
    # RLS: a role anon deve ter permissão de DELETE, caso contrário falha.
    # Adicionaremos essa nota para o usuário.
    response = requests.delete(
        f"{url}/rest/v1/analises_auditoria?criado_em=lt.{data_limite}",
        headers=headers
    )
    if response.status_code == 403:
        raise ValueError("Sem permissão de exclusão. Adicione uma política de DELETE para a role anon.")
    response.raise_for_status()

st.title(" Gerador Offline - Relatório 5302")
st.markdown("Faça o upload do PDF da operadora para iniciar a análise inteligente e extração de glosas. **Tudo ocorre na memória RAM.**")

pdf_file = st.file_uploader("Arraste o arquivo PDF ou CSV aqui", type=["pdf", "csv"])

if pdf_file is not None:
    if "dados_pdf" not in st.session_state or st.session_state.get("pdf_name") != pdf_file.name:
        with st.spinner("Analisando arquivo em memória..."):
            if pdf_file.name.lower().endswith(".csv"):
                glosas, meta = processar_csv(pdf_file)
            else:
                glosas, meta = processar_pdf(pdf_file)
            st.session_state["dados_pdf"] = glosas
            st.session_state["meta_pdf"] = meta
            st.session_state["pdf_name"] = pdf_file.name

    dados = st.session_state.get("dados_pdf", [])
    meta = st.session_state.get("meta_pdf", {"processo": "Desconhecido", "prestador": "Desconhecido", "producao": "Desconhecida"})
    
    if dados:
        st.success(f"Análise concluída! {len(dados)} glosas detectadas. Prestador: **{meta.get('prestador')}** | Processo: **{meta.get('processo')}** | Produção: **{meta.get('producao')}**")
        
        st.markdown("### 1. Auditoria e Justificativas")
        st.markdown("Todas as glosas vêm marcadas em **Incluir no Relatório**. Use a seleção em massa abaixo para marcar/desmarcar várias por código de uma vez, ou edite linha a linha na tabela.")

        if "df_glosas_state" not in st.session_state or st.session_state.get("origem_glosas") != pdf_file.name:
            st.session_state.df_glosas_state = pd.DataFrame(dados).copy()
            st.session_state.origem_glosas = pdf_file.name
            st.session_state.editor_version = 0

        def _sync_edicoes_editor():
            """Persiste edições da tabela em df_glosas_state assim que ocorrem.
            Sem isso, cliques em Marcar/Desmarcar (que incrementam a versão da key
            e descartam o `edited_rows`) perdem alterações da coluna Justificativa
            digitadas logo antes."""
            key_ed = f"glosas_editor_v{st.session_state.editor_version}"
            delta = st.session_state.get(key_ed)
            if not delta:
                return
            df_alvo = st.session_state.df_glosas_state
            for row_idx, changes in (delta.get("edited_rows") or {}).items():
                for col, val in changes.items():
                    if col in df_alvo.columns and 0 <= row_idx < len(df_alvo):
                        df_alvo.iat[row_idx, df_alvo.columns.get_loc(col)] = val

        codigos_unicos = sorted(
            st.session_state.df_glosas_state['Glosa'].astype(str).unique(),
            key=lambda x: (int(x) if x.isdigit() else 9999, x)
        )

        col_sel, col_mark, col_unmark = st.columns([5, 1, 1])
        with col_sel:
            sel_codigos = st.multiselect(
                "Selecionar por código de glosa:",
                codigos_unicos,
                key=f"sel_massa_v{st.session_state.editor_version}",
                placeholder="Escolha um ou mais códigos…",
            )
        with col_mark:
            st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
            if st.button("Marcar", use_container_width=True, key="btn_marcar_massa", disabled=not sel_codigos):
                mask = st.session_state.df_glosas_state['Glosa'].astype(str).isin(sel_codigos)
                st.session_state.df_glosas_state.loc[mask, 'Incluir no Relatório'] = True
                st.session_state.editor_version += 1
                st.rerun()
        with col_unmark:
            st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
            if st.button("Desmarcar", use_container_width=True, key="btn_desmarcar_massa", disabled=not sel_codigos):
                mask = st.session_state.df_glosas_state['Glosa'].astype(str).isin(sel_codigos)
                st.session_state.df_glosas_state.loc[mask, 'Incluir no Relatório'] = False
                st.session_state.editor_version += 1
                st.rerun()

        col_config = {
            "Incluir no Relatório": st.column_config.CheckboxColumn("Incluir", width="small", default=True),
            "Justificativa": st.column_config.TextColumn("Justificativa", width="large", required=False),
            "Procedimento": st.column_config.TextColumn("Procedimento", width="medium"),
            "Descrição Oficial": st.column_config.TextColumn("Descrição", width="medium"),
            "Guia": st.column_config.TextColumn("Guia", width="small"),
            "Cód. Procedimento": st.column_config.TextColumn("Cód", width="small"),
            "Tipo": st.column_config.TextColumn("Tipo", width="small"),
        }

        df_editado = st.data_editor(
            st.session_state.df_glosas_state,
            use_container_width=True,
            num_rows="dynamic",
            column_config=col_config,
            column_order=["Incluir no Relatório", "Tipo", "Guia", "Cód. Procedimento", "Procedimento", "Glosa", "Descrição Oficial", "Justificativa"],
            key=f"glosas_editor_v{st.session_state.editor_version}",
            on_change=_sync_edicoes_editor,
        )

        # Fallback: também persiste no fim do rerun caso o callback nao tenha rodado
        st.session_state.df_glosas_state = df_editado

        st.markdown("### 2. Motor de Texto Offline")
        col1, col2 = st.columns([1, 2])
        
        with col1:
            opcao_agrupamento = st.radio(
                "Nível de Detalhe:",
                ["Versão Resumida (Agrupada)", "Versão Completa (Detalhada)"],
                index=1
            )
            
            opcao_filtro = st.radio(
                "Filtro de Glosas:",
                ["Todas selecionadas na tabela", "Somente Glosas Críticas"]
            )
            
            opcao_prefixo = st.radio(
                "Cabeçalho do Relatório:",
                [
                    "Nenhum Cabeçalho",
                    "c/ Especialidades Críticas",
                    "s/ Especialidades Críticas (Apenas Imagens)"
                ]
            )
            
            btn_gerar = st.button("Gerar Texto", type="primary", use_container_width=True)
            
        with col2:
            if btn_gerar:
                st.session_state["mostrar_texto"] = True
                
            if st.session_state.get("mostrar_texto", False):
                # O tipo de geracao passado dita a regra interna
                tipo = opcao_agrupamento
                
                # Vamos injetar "Só Glosas Críticas" como flag temporaria na hora de chamar
                if "Somente" in opcao_filtro:
                    tipo = "Só Glosas Críticas"
                    
                df_final = df_editado[df_editado['Incluir no Relatório'] == True].copy()
                if "Somente" in opcao_filtro:
                    df_final = df_final[df_final['Tipo'] == 'Crítica']
                
                texto_gerado = gerar_texto(df_final, tipo, meta)
                
                # Limpa prefixos caso a funcao os tenha gerado
                texto_gerado = texto_gerado.replace("PROCESSO ANALISADO POR AMOSTRAGEM DAS ESPECIALIDADES CRÍTICAS///\\n", "")
                texto_gerado = texto_gerado.replace("PROCESSO ANALISADO POR AMOSTRAGEM DAS ESPECIALIDADES CRÍTICAS///\n", "")
                texto_gerado = texto_gerado.replace("PROCESSO ANALISADO POR AMOSTRAGEM DAS ESPECIALIDADES CRÍTICAS/// ", "")
                
                texto_pronto = texto_gerado
                if "Nenhuma glosa" not in texto_gerado:
                    if "c/ Especialidades" in opcao_prefixo:
                        texto_pronto = "PROCESSO ANALISADO POR AMOSTRAGEM DAS ESPECIALIDADES CRÍTICAS/// " + texto_gerado
                    elif "s/ Especialidades" in opcao_prefixo:
                        texto_pronto = "PROCESSO SEM ESPECIALIDADES CRÍTICAS ANALISADO POR AMOSTRAGEM DO ENVIO DE IMAGENS/// " + texto_gerado
                    
                # Key versionada pelas opções: quando qualquer filtro muda e o
                # texto gerado é diferente, o widget reseta com o novo valor;
                # edições manuais dentro da mesma combinação de opções são preservadas.
                key_texto_final = f"texto_final_v_{opcao_agrupamento}_{opcao_filtro}_{opcao_prefixo}"
                texto_editado = st.text_area(
                    "Texto Final (Pronto para copiar):",
                    texto_pronto,
                    height=180,
                    key=key_texto_final,
                )

                col_btn_copy, col_btn_save, _ = st.columns([2, 3, 5])
                with col_btn_copy:
                    # Botão de Copiar via Componente HTML — lê o valor ATUAL do
                    # textarea via window.parent.document (em vez de embutir o
                    # texto no HTML), assim uma edição feita logo antes do clique
                    # já é copiada, mesmo sem rerun.
                    import streamlit.components.v1 as components
                    components.html("""
                    <script>
                    function copyText() {
                        let texto = '';
                        try {
                            const doc = window.parent.document;
                            const textareas = doc.querySelectorAll('textarea');
                            for (const ta of textareas) {
                                const lbl = (ta.getAttribute('aria-label') || '').toLowerCase();
                                if (lbl.includes('pronto para copiar')) {
                                    texto = ta.value;
                                    break;
                                }
                            }
                        } catch (e) { texto = ''; }
                        if (!texto) {
                            document.getElementById('btn_copiar').innerText = ' Erro ao copiar';
                            return;
                        }
                        navigator.clipboard.writeText(texto).then(function() {
                            document.getElementById('btn_copiar').innerText = ' Copiado!';
                            setTimeout(function() {
                                document.getElementById('btn_copiar').innerText = ' Copiar Texto';
                            }, 2000);
                        });
                    }
                    </script>
                    <button id="btn_copiar" onclick="copyText()" style="background-color: #FF4B4B; color: white; border: none; padding: 0.5rem 1rem; border-radius: 0.3rem; cursor: pointer; font-family: sans-serif; font-weight: 500; width: 100%;"> Copiar Texto</button>
                    """, height=65)

                with col_btn_save:
                    if "Nenhuma glosa" not in texto_gerado:
                        if st.button(" Salvar Análise no Supabase", use_container_width=True):
                            with st.spinner("Salvando na nuvem..."):
                                try:
                                    salvar_no_supabase(st.session_state.get("pdf_name", "Desconhecido"), texto_editado, df_final, meta)
                                    st.success("Análise salva com sucesso no banco de dados!")
                                except Exception as e:
                                    st.error(f"Erro ao salvar no banco. A tabela 'analises_auditoria' foi criada no Supabase? Detalhe: {e}")
                
                st.markdown("###  Textos Adicionais ao Prestador")
                if "Nenhuma glosa" not in texto_gerado:
                    glosas_presentes = set(df_final['Glosa'].unique())

                    sub_glosas_presentes = set()
                    for _, row in df_final.iterrows():
                        sub_cod = str(row.get('Cód. Sub-Glosa', '') or '').strip()
                        if sub_cod:
                            sub_glosas_presentes.add(f"{row['Glosa']}.{sub_cod}")

                    procedimentos_presentes = set(str(p) for p in df_final['Cód. Procedimento'].unique())

                    from shared.database import DatabaseManager
                    if "db" not in st.session_state:
                        st.session_state.db = DatabaseManager()

                    textos_db = st.session_state.db.carregar_textos_prestador()

                    candidatos = []
                    for txt in textos_db:
                        glosas_relacionadas = set([g.strip() for g in str(txt.get('glosas_relacionadas', '')).split(',') if g.strip()])
                        glosas_cobertas = glosas_relacionadas & glosas_presentes
                        if not glosas_cobertas:
                            continue

                        sub_glosas_relacionadas = set([s.strip() for s in str(txt.get('sub_glosas_relacionadas') or '').split(',') if s.strip()])
                        if sub_glosas_relacionadas and not (sub_glosas_relacionadas & sub_glosas_presentes):
                            continue

                        procedimentos_relacionados = set([p.strip() for p in str(txt.get('procedimentos_relacionados') or '').split(',') if p.strip()])
                        if procedimentos_relacionados and not (procedimentos_relacionados & procedimentos_presentes):
                            continue

                        is_especifico = bool(sub_glosas_relacionadas) or bool(procedimentos_relacionados)
                        candidatos.append((txt.get('texto', '').strip(), glosas_cobertas, is_especifico))

                    # Glosas já atendidas por algum texto específico (sub-glosa/procedimento)
                    glosas_com_especifico = set()
                    for _, glosas_cobertas, is_especifico in candidatos:
                        if is_especifico:
                            glosas_com_especifico |= glosas_cobertas

                    # Textos gerais só entram se cobrirem alguma glosa sem texto específico
                    textos_sugeridos = [
                        texto for texto, glosas_cobertas, is_especifico in candidatos
                        if is_especifico or not glosas_cobertas.issubset(glosas_com_especifico)
                    ]
                    
                    if textos_sugeridos:
                        texto_mixado = mixar_textos_inteligente(textos_sugeridos)
                        st.text_area("Mensagem Combinada (Copie e cole):", texto_mixado, height=150)
                        
                        texto_seguro_mixado = texto_mixado.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
                        components.html(f"""
                        <script>
                        function copyTextMix() {{
                            navigator.clipboard.writeText(`{texto_seguro_mixado}`).then(function() {{
                                document.getElementById('btn_copiar_mix').innerText = ' Copiado!';
                                setTimeout(() => document.getElementById('btn_copiar_mix').innerText = ' Copiar Mensagem', 2000);
                            }});
                        }}
                        </script>
                        <button id="btn_copiar_mix" onclick="copyTextMix()" style="background-color: #FF4B4B; color: white; border: none; padding: 0.5rem 1rem; border-radius: 0.3rem; cursor: pointer; font-family: sans-serif; font-weight: 500;"> Copiar Mensagem</button>
                        """, height=65)
                    else:
                        st.info("Nenhum texto adicional mapeado para as glosas detectadas.")
            else:
                st.info(" Selecione os filtros ao lado e clique em Gerar Texto.")
            
    else:
        st.warning("Nenhuma glosa identificada neste documento com os padrões atuais.")

