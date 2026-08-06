# Categorias de Glosas — Textos ao Prestador (versão final)

> Documento de continuidade: se a conversa não continuar, use este arquivo
> como ponto de partida — ele reflete o estado mais recente e completo da
> reorganização combinada até agora.

**Bloco fixo (igual para todas as categorias, escrito uma única vez no sistema):**

> Caro prestador,
> [texto específico da categoria — abaixo]
> A não conformidade poderá resultar em glosas. Consulte o demonstrativo de pagamento para mais detalhes sobre o item glosado. Em caso de dúvidas, acionar o suporte: 4002-2722.

---

## Categoria A

**Texto:** O critério de validação da GTO física não foi atendido para este procedimento.

**Glosas:** 401, 402, 403, 404, 405, 422 (422.1), 444

---

## Categoria B

**Texto:** O procedimento não atendeu ao critério de validação de imagem exigido.

**Glosas:** 410 (410.1, 410.2, 410.3), 420, 446 (446.1, 446.2), 414 (414.1, 414.2, 414.3, 414.4, 414.5, 414.6), 457 (457.1, 457.2, 457.3, 457.4), 476 (476.1, 476.2, 476.3, 476.4, 476.5, 476.6, 476.7, 476.8, 476.9), 475 (475.1, 475.2, 475.3, 475.4, 475.5)

---

## Categoria C

**Texto:** A imagem enviada não evidenciou a indicação clínica ou a realização do procedimento.

**Glosas:** 443 (443.2, 443.4, 443.5, 443.6, 443.8, 443.9, 443.10, 443.11, 443.12, 443.13, 443.15, 443.16, 443.17, 443.18, 443.20, 443.22, 443.24, 443.26), 449 (449.1, 449.2, 449.3, 449.6, 449.7, 449.8), 445 (445.2, 445.3, 445.4, 445.5, 445.8, 445.9, 445.10, 445.11, 445.12, 445.14, 445.15, 445.16, 445.17, 445.18, 445.19, 445.21, 445.24, 445.25, 445.29), 452 (452.1, 452.3, 452.8)

---

## Categoria D

**Texto:** O procedimento executado não atendeu aos critérios técnicos da especialidade.

**Glosas:** 438 (438.3, 438.4, 438.5, 438.9, 438.10, 438.12, 438.17, 438.23, 438.25, 438.26, 438.28, 438.29, 438.30, 438.31), 459 (459.1, 459.2, 459.3, 459.4), 448 (448.1, 448.2, 448.3, 448.4, 448.5, 448.6), 440, 447, 430 (430.1), 437

---

## Categoria E

**Texto:** A justificativa clínica apresentada foi insuficiente para comprovar a necessidade do procedimento.

**Glosas:** 421 (421.1, 421.2, 421.3, 421.4, 421.5)

---

## Categoria F

**Texto:** A cobrança não atendeu aos critérios administrativos, de faturamento ou de correspondência com o procedimento efetivamente realizado.

**Glosas:** 454 (454.1), 461 (461.1, 461.2, 461.3, 461.4, 461.5, 461.6, 461.7, 461.9), 477 (477.1), 480 (480.1), 406, 458, 460, 470, 481, 450 (450.1, 450.2), 463, 466, 5, 10, 12, 13, 23, 27, 30, 34, 35, 43, 44, 50, 51, 63, 65, 67, 69

---

## Categoria G — Procedimentos de urgência

**Texto:** O atendimento não atendeu ao critério exigido da especialidade de urgência.

**Glosas:** 417, 413, 461.8, 469 (469.1, 469.2), 473.5, 473.7

---

## Categoria H — Documentação pendente

**Texto:** O documento exigido para este procedimento não atendeu ao critério de validação exigido.

**Glosas:** 422.2, 462, 467, 472 (472.1, 472.2, 472.3, 472.4, 472.5, 472.6, 472.7, 472.8, 472.9, 472.11, 472.12), 473.1, 473.2, 473.3, 473.4, 473.6

---

## Fontes

- `Orientação Prestador 3 (1).csv` — planilha original (185 linhas, 45 glosas, todas categorizadas em A-H).
- `Book 20(Nova planila 2 ).csv` — planilha adicional (18 glosas administrativas/cadastrais). A glosa **46** ("Imagem em histórico de beneficiários distintos", sem texto na fonte) foi descartada a pedido do usuário. As demais 17 foram incorporadas à Categoria F.
- Ver também `Catalogo_Glosas_Textos_Prestador.md` (catálogo completo original, glosa por glosa, com os textos integrais antes da compactação — mantido apenas localmente, não versionado neste repositório).

## Checagem de completude

Todas as 185 linhas da planilha original foram conferidas linha a linha contra
esta estrutura (script de verificação) — **0 faltando, 0 duplicadas, 0
inválidas**. Isso inclui 22 "glosas-mãe" (textos genéricos que existem além
das subglosas específicas) e 5 itens que haviam ficado órfãos numa etapa
anterior da reorganização (450, 450.1, 450.2, 463, 466).

## Pendências em aberto (para revisar quando retomar)

1. Confirmar se os códigos **34** e **43** da "Nova Planilha 2" são de fato
   duplicatas de **454** e **458** (mesmos títulos, sistema de numeração
   diferente) — se forem, podem ser removidos por já estarem cobertos.
2. Nenhum texto de categoria foi ainda validado formalmente para subir em
   `textos_prestadores` no Supabase — falta decidir o formato de importação.
