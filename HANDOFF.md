# SIA Auditoria Modular — Contexto do Projeto

> Documento de handoff para retomar o trabalho em outra ferramenta (ex:
> Antigravity) quando a sessão atual do Claude Code estiver perto do limite.
> Não é um changelog completo — é um mapa pra alguém (ou outro agente) sem
> contexto nenhum entender o projeto rápido.

## O que é

App Streamlit de auditoria odontológica (Hapvida) para o time de Contas /
Auditoria / CISO / Gestor. Principal função: subir PDFs/CSVs de glosas da
operadora, gerar automaticamente o texto de relatório (5302) e o texto de
retorno ao prestador, com um motor de regras que agrupa, prioriza e formata
as glosas.

## Stack

- **Frontend/app**: Streamlit (`app.py` como entrypoint, multi-page via `views/`)
- **Backend**: Supabase (Postgres + REST/PostgREST), acessado via `requests`
  puro em `shared/database.py` (sem SDK do Supabase)
- **Supabase project_id**: `eixmuuvwilchidaqbxqy`
- **Auth**: própria (não usa Supabase Auth) — tabela `usuarios`, hash bcrypt
  (com migração automática de um hash sha256 legado — ver seção Auth)
- **Testes**: pytest (`tests/`, só cobre `services/relatorio_5302/text_engine.py`
  por enquanto)
- **Deploy**: Streamlit Cloud (secrets via `st.secrets`, arquivo local em
  `.streamlit/secrets.toml`, não versionado)

## Estrutura de pastas

```
app.py                      # entrypoint: login, RBAC, montagem do menu
views/                      # uma página por arquivo (Streamlit multipage)
  0_Dashboard.py            # Home: Links Úteis + Último Alinhamento
  1_Configuracoes.py        # painel admin multi-aba (perfil, links, usuários,
                             #   glosas customizadas, textos prestador, permissões)
  2_Relatorio_5302.py       # tela principal: upload PDF/CSV -> motor de texto
  3_Calculadora.py          # calculadora rápida de % de glosa
  4_Producao.py             # análise de produção (ranking de procedimentos)
  5_Alinhamentos.py         # comunicados internos com "ciência obrigatória"
  6_Amostragem.py           # amostragem de guias pra auditoria (CIRURGIA capada 30%)
services/relatorio_5302/    # o motor de texto de verdade (ativo)
  parser_strategy.py        # extrai glosas de PDF/CSV
  glosa_matcher.py          # mapas cacheados (procedimentos, glosas, sub-glosas)
  text_engine.py            # gera Versão Resumida / Completa + mixa textos
                             #   de prestador. Arquivo mais crítico do projeto.
shared/database.py          # DatabaseManager — TODO acesso a Supabase passa
                             #   por aqui (REST cru, não SDK)
core/settings.py            # hierarquia de roles, módulos controlados
core/auth.py                # cookie de sessão (token assinado)
tests/test_text_engine.py   # suite pytest do motor de texto (14 casos)
CLAUDE.md                   # convenções de UI do projeto (leia antes de mexer)
```

### Pastas que NÃO fazem parte do app ativo (cuidado pra não confundir)

- `apps/` — app desktop legado (tkinter/customtkinter), outro projeto dentro
  do mesmo repo. Não é servido pelo Streamlit. Importa de `core/database.py`
  e `shared/text_engine.py` (também legados, não confundir com
  `shared/database.py` e `services/relatorio_5302/text_engine.py`, que são
  os ativos).
- `core/glass_design_system.py` — sistema de tema "glass" foi removido; hoje
  é só um wrapper vazio em cima de `st.dataframe`/`st.markdown`. Não usar em
  código novo (ver CLAUDE.md).

## Banco de dados (Supabase, schema `public`)

| Tabela | Propósito |
|---|---|
| `usuarios` | login próprio, `senha_hash` + `senha_algo` (bcrypt/legado), `senha_temporaria`, `role_interno`, `status` (Pendente/Ativo/Bloqueado) |
| `alinhamentos` | comunicados internos com ciência obrigatória; soft-delete via `excluido`/`motivo_exclusao`/`excluido_em`/`excluido_por` |
| `alinhamentos_lidos` / `alinhamentos_inativacoes_lidas` | confirmações de ciência |
| `textos_prestadores` | textos padrão por glosa/sub-glosa/procedimento, usados na mixagem de texto ao prestador |
| `glosas_padrao` / `glosas_customizadas` / `glosas_dicionario` | tabelas de referência (descrição oficial, tipo, correções gramaticais) |
| `tabela_procedimentos` | catálogo de procedimentos (código TUSS + descrição) |
| `analises_auditoria` | histórico de relatórios gerados (salvo manualmente, botão na tela) |
| `links_padrao` | links institucionais exibidos na Home, por categoria (gerenciado por Admin/Gestor) |
| `links` / `usuario_links` | links pessoais de cada usuário (sidebar) |
| `permissoes_modulos` | quais roles acessam quais módulos — **RLS desabilitado, ver Avisos** |
| `changelog` | não usado mais na Home (seção removida), função `carregar_changelog` ainda existe |

## Autenticação e segurança

- Hash de senha: **bcrypt** (novo padrão). Existe hash sha256+salt estático
  legado (`senha_algo='sha256_v5'`) — no login, se detectar hash legado,
  regrava automaticamente pra bcrypt (transparente, sem forçar reset).
- Reset de senha (por Admin): `DatabaseManager.resetar_senha()` usa
  `service_role` (chave privilegiada, só em `st.secrets`, nunca sai do
  servidor) e checa `role_interno == 'Admin'` antes de qualquer escrita.
  Marca `senha_temporaria=true` — próximo login força tela de troca
  obrigatória antes de liberar o resto do app.
- Hierarquia de roles (`core/settings.py::NIVEL_HIERARQUIA`): Contas(1) <
  Auditor(2) < CISO(3) < Gestor(4) = Admin(4). Quem tem nível maior enxerga
  conteúdo (ex: alinhamentos) dos níveis abaixo também.
- `st.secrets` esperado: `supabase.url`, `supabase.key` (anon),
  `supabase.service_role`, `seguranca.fernet_key`, `admin_emergencia.usuario`/`senha`.

## Convenções de UI (resumo — ver CLAUDE.md completo)

- **Tabelas**: usar `st.dataframe` normal. Não existe mais sistema "glass" —
  se ver `render_glass_table`/`inject_glass_css` sendo importado em código
  novo, é sinal de código desatualizado.
- **Listas administráveis (editar/excluir item)**: preferir lista compacta
  (Action Cards: info à esquerda, ações à direita) + **um único** formulário
  de edição guardado em `st.session_state` (não um formulário por item).
  Referências: "Textos Padrões (Motor)" em `1_Configuracoes.py`, e o
  redesenho recente de `5_Alinhamentos.py`.

## Como rodar localmente

```powershell
pip install -r requirements.txt -r requirements-dev.txt
streamlit run app.py
pytest   # roda a suite do motor de texto
```

Precisa de `.streamlit/secrets.toml` preenchido (não versionado).

## O que foi feito nesta sessão (mais recente primeiro)

1. Redesenho de `5_Alinhamentos.py`: Action Cards, exclusão com motivo
   obrigatório (soft-delete), aba "Excluídos" (Gestor/Admin), agrupamento do
   Histórico por nível-alvo (só o próprio nível vem aberto por padrão).
2. Limpeza do CLAUDE.md (removida a regra obsoleta de "glass table").
3. Home (`0_Dashboard.py`): removidas seções "Novidades" e "Módulos
   Disponíveis"; Links Úteis virou expander; nova seção "Último Alinhamento".
4. Cadastro de 22 links institucionais em `links_padrao` (SharePoint, RH,
   Power BI, Service Desk, planilhas de controle, etc).
5. Reset de senha por Admin com troca obrigatória no próximo login
   (`senha_temporaria`, `service_role`).
6. Migração de hash de senha pra bcrypt com rehash automático no login.
7. Suite pytest para `text_engine.py` (14 casos).
8. Vários ajustes no motor de texto do Relatório 5302 (`text_engine.py`):
   ordenação Crítica → Adm/Técnica → Automática → glosa 480; compactação por
   tipo/quantidade de categorias; merge de glosas diferentes no mesmo
   procedimento+guia; dedup de listas de guias repetidas; glosa 480 sem
   descrição redundante; precedência de Crítica sobre Automática na
   classificação do parser.
9. UX do Relatório 5302: seleção em massa de glosas por código
   (marcar/desmarcar), glosas Automáticas vêm marcadas por padrão, fix de
   bugs de state ao trocar de PDF/editar justificativa/copiar texto.

## Pendências conhecidas / próximos passos

- **`permissoes_modulos` com RLS desabilitado** — exposta a leitura/escrita
  via chave `anon` pública. Não corrigido ainda (corrigir errado pode travar
  o app; precisa definir políticas antes de habilitar RLS). Ver advisory do
  Supabase MCP (`get_advisors`).
- Organizar `views/2_Relatorio_5302.py` (quase 350 linhas, mistura UI/RBAC/
  chamada de DB/geração de texto) — cogitado, não iniciado.
- Audit log (histórico de ações admin, visível só por Admin) — cogitado, não
  iniciado.
- Notificações via Power Automate (Teams/e-mail) quando um alinhamento novo
  é publicado — cogitado, não iniciado. Precisa da URL do webhook do
  Power Automate antes de implementar.
- Planilha "Orientação ao Prestador 2.0" foi analisada (ver conversa) — os
  textos hoje são "por procedimento" disfarçados de "por glosa", altamente
  redundantes entre linhas. Reescrita recomendada antes de importar pro
  `textos_prestadores`. Não implementado ainda.

## Arquivos pra ler primeiro se for continuar em outra ferramenta

1. `CLAUDE.md` — convenções, leia antes de tocar em qualquer view.
2. `shared/database.py` — toda a superfície de acesso a dados.
3. `services/relatorio_5302/text_engine.py` — o motor mais crítico e mais
   editado do projeto; tem `tests/test_text_engine.py` cobrindo os
   principais comportamentos.
4. `views/2_Relatorio_5302.py` — tela mais usada do app.
5. Este arquivo (`HANDOFF.md`) — pra não perder o fio da meada.
