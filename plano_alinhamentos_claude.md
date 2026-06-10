# Plano: Sistema de Alinhamentos Internos

Substitui a planilha "Alinhamento (3).xlsx" (abas Técnico/Administrativo/CAP)
por uma base pesquisável dentro do app, com pop-up obrigatório de ciência
para alinhamentos novos.

## Estrutura de Banco (Supabase)

### 1. `alinhamentos`
| Campo | Tipo | Notas |
|---|---|---|
| `id` | uuid/serial | PK |
| `titulo` | text | "Assunto/Dúvida" da planilha |
| `conteudo` | text | "Deliberação" da planilha |
| `categoria` | text | `Técnico`, `Administrativo`, `CAP`, `Geral` |
| `nivel_minimo` | text | `Contas`, `Auditor`, `CISO`, `Gestor` |
| `autor_id` | uuid | FK -> usuarios |
| `ativo` | bool | default `true` |
| `created_at` | timestamp | default now() |

### 2. `alinhamentos_lidos`
| Campo | Tipo | Notas |
|---|---|---|
| `id` | uuid/serial | PK |
| `alinhamento_id` | uuid/int | FK -> alinhamentos |
| `usuario_id` | uuid | FK -> usuarios |
| `lido_em` | timestamp | default now() |

## Hierarquia de Roles

```python
NIVEL_HIERARQUIA = {"Contas": 1, "Auditor": 2, "CISO": 3, "Gestor": 4, "Admin": 4}
```

- **Visibilidade (tela de histórico):** `nivel(role_usuario) >= nivel(alinhamento.nivel_minimo)`
  Ex: alinhamento com `nivel_minimo="Contas"` → todos veem.
  Alinhamento com `nivel_minimo="Auditor"` → Auditor/CISO/Gestor/Admin veem, Contas não.

- **Pop-up obrigatório "Estou Ciente":**
  - Aplica-se **apenas** a roles `Contas`, `Auditor`, `CISO`.
  - **Gestor e Admin nunca são bloqueados** (mesmo que não tenham criado o alinhamento).
  - Condição: `ativo=true` E `nivel(role_usuario) >= nivel(alinhamento.nivel_minimo)`
    E não existe registro em `alinhamentos_lidos` para `(alinhamento_id, usuario_id)`.

## Regras de Interface (Streamlit)

### 1. Pop-up bloqueante (`app.py`)
Logo após login manual **e** após auto-login via cookie, antes de montar
`st.navigation`: busca alinhamentos pendentes (regra acima) para o usuário.
Se houver, exibe `st.dialog` central com título/conteúdo + botão "Estou
Ciente" → grava em `alinhamentos_lidos` e libera o app. Resultado cacheado
em `st.session_state` para não bater no banco a cada rerun.

### 2. Tela dedicada `views/5_Alinhamentos.py`
Disponível para todos (conteúdo se autoprotege, como `1_Configuracoes.py`).

- **Aba "Histórico"** (todos): `render_glass_table` com filtro por
  `categoria` e busca textual. Status visual: ativo = verde, inativo =
  vermelho com título riscado. Filtrado pela regra de visibilidade por
  nível.
- **Aba "Gerenciar"** (Gestor/Admin): criar novo (`titulo`, `conteudo`,
  `categoria`, `nivel_minimo`), editar, ativar/desativar com um clique.
  Autor já nasce marcado como "lido" no próprio registro criado.

## Migração dos dados históricos

> **Tudo vai para o Supabase — nada fica hardcoded no app.** A migração é
> um script one-off (lê o `.xlsx` com `openpyxl`, insere via
> `DatabaseManager`/API REST), rodado uma vez localmente e depois
> descartado (não precisa ser commitado), igual ao padrão do
> `temp_dump.py`. A partir daí, `views/5_Alinhamentos.py` lê tudo
> dinamicamente das tabelas.

- Importar as ~220 linhas das abas Técnico/Administrativo/CAP da planilha
  para `alinhamentos`:
  - `titulo` <- Assunto/Dúvida, `conteudo` <- Deliberação
  - `categoria` <- nome da aba (Técnico/Administrativo/CAP)
  - `nivel_minimo` <- `"Auditor"` (default; ajuste manual posterior)
  - `ativo` <- `true` (default; revisão manual posterior do que ainda vale)
- Inserir em `alinhamentos_lidos` um registro para **cada usuário existente**
  e cada alinhamento importado, para não disparar pop-up retroativo.
- "Orientação ao Prestador" fica de fora por agora (puxa de
  `textos_prestadores`/`mensagens_padrao` futuramente).

## Novos métodos em `shared/database.py`
- `carregar_alinhamentos()`
- `carregar_alinhamentos_visiveis(role)`
- `carregar_alinhamentos_pendentes(usuario_id, role)`
- `inserir_alinhamento(titulo, conteudo, categoria, nivel_minimo, autor_id)`
- `atualizar_alinhamento(id, titulo, conteudo, categoria, nivel_minimo)`
- `toggle_ativo_alinhamento(id, ativo)`
- `marcar_alinhamento_lido(alinhamento_id, usuario_id)`
