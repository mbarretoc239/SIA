# SIA Auditoria Modular — Convenções de UI

## Tabelas

Use `st.dataframe` normalmente (com `column_config`, `on_select`,
`selection_mode`, etc). Não existe mais nenhum sistema de tema "glass" no
projeto — `core/glass_design_system.py` foi esvaziado e não deve ser usado
em código novo.

Para listas administráveis (editar/excluir um item), prefira:

1. Tabela somente-leitura (`st.dataframe`) com seleção de linha
   (`on_select="rerun", selection_mode="single-row"`) para escolher o item.
2. Um único formulário de edição, exibido separado da lista (guardado em
   `st.session_state`), que abre para o item selecionado ou para "Novo".
   Evite renderizar um formulário completo por item da lista — isso deixa a
   tela pesada e difícil de escanear.

Exemplo de referência: seção "Textos Padrões (Motor)" em
`views/1_Configuracoes.py` (lista + formulário único).
