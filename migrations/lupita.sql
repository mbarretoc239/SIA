-- Lupita: triagem de imagens geradas por IA (acesso restrito, ver core/lupita/acesso.py).
--
-- Guarda só números: as 56 medidas de cada imagem e o hash SHA-256 do arquivo.
-- A imagem em si NUNCA é gravada. Nomes de arquivo do JSON de origem também não.
--
-- RLS ligado e SEM policy pra anon: só a service_role (servidor do Streamlit) lê/grava,
-- sempre via core/lupita/dados.py, que confere o usuário liberado antes de cada chamada.
--
-- Egress: o app lê (a) a versão do modelo ativo, cacheada, (b) o histórico com `limit`
-- e sem as colunas pesadas, (c) as amostras só quando um liberado clica em "Retreinar".

create table if not exists lupita_modelos (
    id          bigserial primary key,
    versao      integer      not null unique,
    ativo       boolean      not null default false,
    modelo      jsonb        not null,   -- pesos, média, desvio, Platt, limiar "fora do padrão"
    metricas    jsonb,                   -- validação cruzada (auc, acerto, n_ia, n_reais, ...)
    origem      text,
    criado_por  text,
    criado_em   timestamptz  not null default now()
);

-- no máximo um modelo ativo
create unique index if not exists lupita_modelos_um_ativo
    on lupita_modelos (ativo) where ativo;

create table if not exists lupita_imagens (
    id              bigserial primary key,
    hash_imagem     text unique,          -- SHA-256 do arquivo; nulo nas amostras importadas
    medidas         real[]       not null, -- 56 valores, na ordem de core/lupita/predicao.CHAVES_TODAS
    versao_medidas  smallint     not null default 1,
    rotulo          smallint     check (rotulo in (0, 1)),   -- 1 = IA, 0 = real; nulo = não confirmado
    lote            text,                  -- lote de upload (validação cruzada por lote)
    origem          text         not null default 'upload' check (origem in ('importacao', 'upload')),
    score           real,                  -- probabilidade de IA no momento da análise
    fora_padrao     boolean,
    contrib         jsonb,                 -- contribuição por grupo (só pra tela de detalhe)
    modelo_versao   integer,
    usuario         text,
    rotulado_por    text,
    rotulado_em     timestamptz,
    criado_em       timestamptz  not null default now(),
    constraint lupita_medidas_56 check (array_length(medidas, 1) = 56)
);

create index if not exists lupita_imagens_rotulo on lupita_imagens (rotulo) where rotulo is not null;
create index if not exists lupita_imagens_criado on lupita_imagens (criado_em desc) where origem = 'upload';

-- "Não sei ao certo": o auditor olhou e não tem certeza. Fica com rotulo nulo (logo FORA do treino,
-- que só lê rotulo is not null) e incerto = true, pra não ser confundida com "ainda não revisada".
alter table lupita_imagens add column if not exists incerto boolean not null default false;

alter table lupita_modelos enable row level security;
alter table lupita_imagens enable row level security;
