# Tarefa: zipar arquivos locais do SIA que estão fora do git

Estes arquivos estão no `.gitignore` do repositório SIA e só existem nesta máquina. Quero um backup deles para levar a outra máquina.

## O que fazer

1. Na raiz do repositório SIA, localize cada item da lista abaixo. Ignore o que não existir e me diga o que não foi encontrado.
2. Crie um `.zip` chamado `SIA_arquivos_locais_AAAA-MM-DD.zip`, preservando a estrutura de pastas relativa à raiz do repo.
3. Envie o zip para o meu Google Drive e me passe o link.
4. Antes de enviar, me mostre a lista final de arquivos e o tamanho total, e espere eu confirmar.

## Itens a incluir

**Segredos (sensíveis)**
- `.env`
- `.streamlit/secrets.toml`

**Ferramentas locais**
- `ferramentas/` (pasta inteira, Farol Mensal offline em Tkinter)
- `tests/test_farol_mensal_*.py`

**Scripts avulsos de dev/automação**
- `main.py`
- `automacao_hapvida.py`
- `dump.py`, `dump2.py`
- `find_*.py`
- `inativar_*.py`
- `parse_excel.py`
- `popular_fallback_turso.py`
- `bridge_test.py`
- `/test*.py` (somente na raiz, não os de `tests/`)
- `shoot*.py`
- `scratch/` e `temp/` e `temp_*`

**Documentação interna**
- `contexto_claude.md`
- `plano_*_claude.md`
- `CHANGELOG_GLOSAS.md`
- `.claude/` (pasta inteira)

**Dados reais (contêm dados de pacientes/prestadores)**
- `relatórios/` (pasta inteira)
- `IA *.xlsx`
- `*.pdf`, `*.csv`, `*.docx`, `*.jsonl`

**Bancos locais e backups**
- `*.db`, `*.sqlite3`, `*.bak`

## Cuidados

- Use `git status --ignored` para conferir o que está fora do git e me avisar se achar algo importante que não esteja nesta lista.
- Não inclua `venv/`, `.venv/`, `__pycache__/`, `.git/` nem `node_modules/`.
- O zip terá segredos e dados de pacientes. Envie para uma pasta privada do Drive, sem compartilhar por link público.
- Não imprima o conteúdo de `.env` nem de `secrets.toml` na conversa.
