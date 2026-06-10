# SIA Auditoria Modular — Convenções de UI

## Tabelas: nunca usar `st.dataframe` / `st.data_editor`

O `st.dataframe`/`st.data_editor` (Streamlit 1.57) renderiza a grade em
`<canvas>` (glide-data-grid). O canvas **não** respeita o tema dark/glass do
app via CSS — sempre aparece com fundo branco, independente de
`config.toml`, tema do navegador ou overrides de `--gdg-*`. Já foi tentado e
não funciona (ver histórico do projeto irmão "calculadora gestão").

**Regra:** qualquer tabela nova ou existente deve usar
`render_glass_table()` de `core/glass_design_system.py`.

```python
from core.glass_design_system import render_glass_table

render_glass_table(df)  # somente leitura, com sort + filtro por coluna
render_glass_table(df, fmt={"Coluna (%)": "{:.4f}%"}, max_height=320)
```

### Tabelas editáveis

`render_glass_table` é somente leitura (renderiza em iframe via
`components.html`, não suporta widgets interativos do Streamlit dentro).
Para edição, separe visualização e edição:

1. `render_glass_table(df_visual)` com as colunas somente-leitura.
2. Abaixo, um `st.expander` por linha com `st.checkbox` / `st.text_input`
   para os campos editáveis, mais botão "Remover".
3. Botão "+ Adicionar linha manual" para inserir linhas novas.
4. Use um `_id` (uuid) estável por linha como sufixo de `key=` dos widgets —
   nunca o índice posicional, pois remover uma linha desloca os índices e
   causa colisão de `key` com valores antigos no `session_state`.

Exemplo de referência completo: seção "1. Auditoria e Justificativas" em
`views/2_Relatorio_5302.py`.
