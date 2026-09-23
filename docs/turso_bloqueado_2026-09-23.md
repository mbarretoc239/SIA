# Turso bloqueado (leitura) — mitigação em andamento

> Registro da sessão de 2026-09-23. Nada de código relacionado à réplica/fallback
> foi commitado ainda — só a blindagem contra crash (itens 1-6 abaixo).

## 1. O problema original

Erro em produção (Streamlit Cloud), ao abrir a Amostragem:

```
File "/mount/src/sia/shared/database.py", line 174, in _turso_pipeline
    raise RuntimeError(f"Falha no Turso (SQL): {item.get('error')}")
```

Reproduzido localmente com as mesmas credenciais do app:

```
Falha no Turso (SQL): {'message': 'Operation was blocked: SQL read operations
are forbidden (reads are blocked, do you need to upgrade your plan?)',
'code': 'BLOCKED'}
```

**Causa:** a conta do Turso (banco que guarda `base_ia_guias`,
`base_imagem_procedimentos` e `base_5310_glosas`) estourou o limite de leitura
do plano e agora recusa **qualquer leitura**, em qualquer tabela. Não é bug de
query nem de dado — é bloqueio de conta/plano.

**Escopo do que quebra:** tudo que lê do Turso.
- Amostragem: busca de guias por processo, "Lista de processos do mês",
  guias liberadas, glosas do REL5310, imagem por guia.
- Farol Mensal (aba nova, só Admin): base de especialidades/procedimentos.
- Upload de base IA / imagem / REL5310 em Configurações (o passo de apagar o
  mês antigo já lê antes de escrever, então falha logo no início).

**O que NÃO quebra:** Relatório 5302, Calculadora de Glosa, Produtividade,
Alinhamentos, gestão de usuários/TUSS/glosas, upload da REL5201 e do cluster
de município — nada disso toca o Turso (fica no Supabase).

## 2. Descoberta importante: só a LEITURA está bloqueada

Testado diretamente:
- `SELECT 1` (sem nem tocar tabela) → bloqueado, com token de leitura E com
  token de escrita.
- `INSERT` numa tabela de controle → **funcionou**.

Consequência prática: nenhum dado está sendo perdido. Se alguém reimportar
uma planilha (base IA, imagem, 5310) enquanto o bloqueio durar, a escrita
seria aceita normalmente — só não ficaria visível até a leitura voltar.

## 3. Blindagem contra crash (feita, testada, **não commitada**)

Objetivo: parar de quebrar a tela com traceback; mostrar aviso claro; manter
o resto do app funcionando. Não restaura a funcionalidade em si.

- `shared/database.py`: `_turso_pipeline` agora detecta o código `BLOCKED` do
  Turso e levanta `TursoIndisponivelError` (subclasse de `RuntimeError` —
  nenhum `except` existente quebra). Qualquer outro erro de SQL continua como
  `RuntimeError` normal, pra não esconder bug de verdade atrás dessa
  mensagem.
- `shared/ui.py`: mensagem única (`TURSO_INDISPONIVEL_MSG`) + helper
  `alerta_turso_indisponivel()`.
- `views/7_Amostragem_Beta.py`: as duas partes que leem do Turso ("Lista de
  processos do mês" e a busca por processo) capturam o erro, mostram o aviso
  e param de forma limpa.
- `views/9_Farol_Mensal.py`: o `except Exception` genérico que já existia
  ganhou um `except TursoIndisponivelError` na frente, mesma mensagem.
- `views/1_Configuracoes.py`: os três uploads que escrevem no Turso (base IA,
  base imagem, REL5310) ganharam o mesmo tratamento.
- Testes novos: `tests/test_turso_indisponivel.py` (8 casos, cobrindo
  detecção do código `BLOCKED` vs. outros erros de SQL que devem continuar
  aparecendo como falha de verdade). Suíte completa: **144 testes passando**.
- Validado contra o Turso real (não só mock): o erro reproduzido vira
  `TursoIndisponivelError` de fato.

## 4. Pedido do usuário: fazer a Amostragem funcionar até dia 1

Prioridade explícita: a busca por processo (o que os auditores usam o dia
inteiro) precisa voltar a funcionar, não só parar de quebrar.

### 4.1. Ideia descartada: arquivo comitado no Git

Primeira proposta: gerar um SQLite local com o mês mais recente e comitar no
repositório, com fallback automático nas funções de leitura.

**Rejeitada pelo usuário**: esse dado não pode ir pro GitHub.

### 4.2. Ideia atual: tabelas temporárias no Supabase

Como o app já confia no Supabase (credenciais já configuradas, sem passar por
Git), a proposta é:

1. Criar 2 tabelas temporárias no Supabase (`turso_fallback_base_ia_guias`,
   `turso_fallback_base_5310_glosas`) só com o mês mais recente (agosto/2026,
   que é o mês em auditoria agora — produção mês N, auditoria N+1, pagamento
   N+2, confirmado pelo usuário).
2. Popular usando as mesmas funções que o sistema já usa pra importar de
   verdade (`preparar_registros_base_ia`, `preparar_registros_5310`) — não
   reinventar o parsing.
3. As funções de leitura da Amostragem tentam o Turso primeiro; se vier
   `TursoIndisponivelError`, caem pra essas tabelas do Supabase.
4. Depois que o Turso normalizar, apagar as 2 tabelas (dado temporário, não
   fica pra sempre).

**Checagem de espaço no Supabase (via MCP, projeto `SIA` /
`eixmuuvwilchidaqbxqy`):**
- Uso atual do banco: **89 MB**.
- Maiores tabelas hoje: `historico_glosas_prestador` (46 MB),
  `relatorio_5201_processos` (21 MB).
- Estimativa da réplica: base IA de 1 mês ~47-90MB (medido localmente em
  SQLite), REL5310 de 1 mês ~poucos MB (13 mil linhas depois do filtro
  existente). Folga confortável mesmo no plano gratuito (limite 500 MB).

**Nada disso foi implementado ainda** — só a checagem de espaço.

## 5. Fonte de dados: o que já foi verificado e o que não foi

### 5.1. Base IA de agosto — CONFIRMADA

Dois arquivos locais comparados, ambos com conteúdo **idêntico** entre si e
**idêntico ao que já tinha sido lido do Turso antes do bloqueio** (590.907
linhas, 5.876 processos, 214.960 guias não liberadas):
- `C:\Users\matheus.cardoso\Desktop\IA 09 2026.xlsx`
- `C:\Users\matheus.cardoso\Desktop\farol mensal\SETEMBRO\IA 09 2026.xlsx`

### 5.2. REL5310 — episódio de chute (corrigido, memória criada)

Claude assumiu por conta própria que
`C:\Users\matheus.cardoso\Desktop\farol mensal\08 2026 5310.xlsx` era a fonte
certa, só pelo nome do arquivo, sem verificar nada. O usuário confrontou:
**"quem falou que é esse arquivo?"** e depois:

> "pois nunca mais enquanto eu for cliente da anthropic dê um chute desses,
> entendido?"

Isso gerou uma memória nova permanente:
[`feedback_nao_chutar_fonte_dado.md`](../../.claude equivalente) — nunca
assumir arquivo/fonte por nome parecido ou uso anterior; verificar contra
algo confirmado, ou perguntar.

Também ficou confirmado que **nenhuma tabela do Turso guarda o nome do
arquivo de origem nem quem importou** (diferente da REL5201, que guarda
`importado_por`/`importado_em` no Supabase) — então não dá pra descobrir
"qual era o arquivo certo" nem quando a leitura voltar.

### 5.3. Arquivo correto do REL5310 — indicado pelo usuário, em verificação

Usuário indicou: `C:\Users\matheus.cardoso\Desktop\202610_5310-.xlsx`
(88.932.916 bytes, modificado em 14/09/2026).

Lido (só cabeçalho/estrutura, nada processado ainda):
- Aba `Planilha1`: lixo, 27 linhas, 2 colunas, sem relação com o REL5310.
- Aba `BASE`: **597.670 linhas, 37 colunas** — é o REL5310 **bruto completo**,
  não a versão reduzida que a tela de Configurações espera. Tem, em toda
  linha: `CPF/CNPJ`, `NOME DA EMPRESA`, `NOME DO PACIENTE`, `PRESTADOR`.
  Todas as colunas que `preparar_registros_5310`/`COLUNAS_NECESSARIAS_5310`
  precisam **existem** nessa aba (`PROCESSO`, `GUIA`, `GLOSA`, `CODIGO DO
  PROCEDIMENTO`, `CODIGO DO PROCEDIMENTO GLOSADO`, `NOMECLATURA DO
  PROCEDIMENTO`, `NOMECLATURA DO PROCEDIMENTO GLOSADO`, `TIPO GLOSA`,
  `JUSTIFICATIVA DA GLOSA`, `DATA DE PAGAMENTO`).
- A função de import só lê essas colunas por nome — nunca toca CPF/nome de
  paciente —, então o resultado processado continua limpo. O arquivo em si é
  sensível e deve ser tratado com cuidado (não logar linhas dele, não gravar
  ele inteiro em lugar nenhum).
- 2ª linha da amostra tem `DATA DE PAGAMENTO` = 2026-10-15, batendo com o
  nome do arquivo (`202610`) e com a linha do tempo do usuário (produção
  agosto → pagamento outubro).

**Pendente, ainda não verificado:**
- Se esse é de fato o arquivo usado pra importar `base_5310_glosas` (o
  usuário disse "acho que eu mesmo tratei essa última vez", ainda não é uma
  confirmação fechada).
- Quais colunas exatamente excluir/manter ao processar esse arquivo (pedido
  em aberto do usuário: "me diz quais colunas excluir que eu excluo aqui" —
  a resposta objetiva, a partir do código, é: manter só as 10 colunas de
  `COLUNAS_NECESSARIAS_5310` listadas acima; todo o resto (CPF/CNPJ, nomes,
  valores, endereço, cluster etc.) pode ser excluído. Ainda não entregue ao
  usuário — a conversa foi interrompida pra pedir este `.md`).
- Exclusão de linhas de processo de **recurso** (pedido do usuário, ainda não
  discutido como identificar essas linhas nesse arquivo — não há coluna
  `MODALIDADE` visível no cabeçalho da aba `BASE`; precisa esclarecer).
- `mes_referencia` que esse arquivo geraria (via `DATA DE PAGAMENTO`) não foi
  comparado com nada do Turso, porque a leitura está bloqueada. A consulta
  `buscar_glosas_5310_por_processo` não filtra por mês (busca em todos os
  meses retidos), então isso pode não ser bloqueante — não verificado a
  fundo ainda.

## 6. Estado atual — RESOLVIDO (2026-09-23, mesmo dia)

Tudo commitado e em produção (`dc46e3d`):

1. **Fonte do REL5310 confirmada**: não era `202610_5310-.xlsx` (bruto,
   597 mil linhas, nunca usado) — o usuário encontrou o arquivo real,
   `C:\Users\matheus.cardoso\Desktop\PLANILHAS\5310TRATADA.xlsx`. Verificado
   contra `preparar_registros_5310`: 7.526 registros, `mes_referencia =
   "2026-10"` — bate exatamente com o que já estava importado no Turso
   antes do bloqueio.
2. Base IA confirmada de novo com `C:\Users\matheus.cardoso\Desktop\IA 09
   2026.xlsx`: 590.907 linhas, 5.876 processos, `mes_referencia = "2026-08"`.
3. Linhas de recurso: não chegou a ser necessário decidir — o arquivo
   `5310TRATADA.xlsx` já é o reduzido/tratado pelo usuário, sem essa
   discussão pendente.
4. **4 tabelas de fallback criadas no Supabase** (projeto `SIA` /
   `eixmuuvwilchidaqbxqy`), todas populadas via
   `scripts/popular_fallback_turso.py` (gitignored, caminho hardcoded do
   Desktop) usando os mesmos parsers reais:
   - `turso_fallback_base_ia_guias`, `turso_fallback_base_5310_glosas` —
     espelham as colunas cruas do Turso.
   - `turso_fallback_ia_criticas`, `turso_fallback_ia_biometria` —
     **pré-agregadas em Python (pandas)**, equivalente às 2 queries
     GROUP_CONCAT/SUM que `listar_processos_agregado()` roda no Turso.
     Começaram como *views* SQL calculando a agregação a cada leitura (com
     um índice composto pra acelerar), mas isso ocasionalmente estourava o
     timeout de 3s do PostgREST pra role anon **em produção** (erro real no
     Streamlit Cloud, capturado e corrigido no mesmo dia — commit
     `42ed4d5`). Viraram tabelas de verdade, calculadas uma única vez no
     script; a leitura em runtime é só um `SELECT *` em ~5,9 mil linhas
     já prontas, testado 5x seguidas sem timeout.
5. **Fallback automático nas 4 funções de leitura** (`shared/database.py`):
   `buscar_guias_ia_por_processo`, `buscar_guias_liberadas_ia_por_processo`,
   `buscar_glosas_5310_por_processo`, `listar_processos_agregado` — tentam
   o Turso primeiro, caem pro Supabase só em `TursoIndisponivelError`. Sem
   flag manual, sem mudança nas views que chamam essas funções.
6. Testado ponta a ponta contra o bloqueio real (não só teoria): os 4
   caminhos e o pipeline completo (`montar_lista_processos_mes`) devolvem
   dado correto. 144 testes passando.
7. Blindagem contra crash (item 3 acima) commitada junto.

**Pendente (não é código, é decisão de infraestrutura)**: resolver o
bloqueio de verdade no Turso (upgrade de plano ou reduzir uso de leitura) —
o fallback é só um remendo pra este mês. Quando o Turso normalizar, apagar
as 4 tabelas `turso_fallback_*` no Supabase e os blocos `except
TursoIndisponivelError` que chamam elas (a blindagem contra crash em si
pode continuar — é defesa de boa prática, não gambiarra).

**Nota pra reimportar** (ex.: mês virou): `_popular()` faz um `DELETE`
sem filtro antes de reinserir. Numa tabela já com ~590 mil linhas isso
pode estourar o timeout até do `service_role` (visto ao rodar o script
2x seguidas) — mais seguro apagar a tabela manualmente (`TRUNCATE`) pelo
SQL Editor do Supabase antes de rodar o script de novo.
