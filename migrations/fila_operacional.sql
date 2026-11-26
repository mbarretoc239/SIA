-- Fila operacional: substitui a planilha em que o time marca quem está em cada processo
-- (ver core/fila_operacional.py e views/11_Fila_Operacional.py).
--
-- Uma linha por processo. A trava contra duas pessoas no mesmo processo é o UPDATE
-- condicional "... where processo = X and auditor_nome is null": o Postgres trava a linha,
-- então só um dos dois cliques simultâneos encontra o processo livre.
--
-- RLS ligado e SEM policy pra anon: só a service_role (servidor do Streamlit) lê/grava.

create table if not exists fila_processos (
    processo        text primary key,
    prestador       text,
    cidade          text,
    uf              text,
    tipo            text,
    procedimentos   integer,
    guias           integer,
    status          text check (status in ('Consistido', 'Fechado', 'Calculado', 'Glosado')),
    auditor_nome    text,
    auditor_login   text,            -- nulo em marcação trazida da planilha
    assumido_em     timestamptz,
    concluido_em    timestamptz,
    obs_contas      text,
    obs_auditoria   text,
    sem_biometria   integer check (sem_biometria >= 0),
    publicado_por   text,
    publicado_em    timestamptz not null default now(),
    atualizado_em   timestamptz not null default now()
);

-- atualizado_em sempre pelo relógio do banco: é o que a busca "só o que mudou" usa
create or replace function fila_processos_marcar_atualizacao()
returns trigger language plpgsql set search_path = '' as $$
begin
    new.atualizado_em := now();
    return new;
end;
$$;

drop trigger if exists fila_processos_atualizacao on fila_processos;
create trigger fila_processos_atualizacao
    before insert or update on fila_processos
    for each row execute function fila_processos_marcar_atualizacao();

create index if not exists fila_processos_atualizado on fila_processos (atualizado_em);

alter table fila_processos enable row level security;

-- Última liberação: quem devolveu o processo à fila e por quê (ex.: direcionado a outra pessoa)
alter table fila_processos add column if not exists liberado_motivo text;
alter table fila_processos add column if not exists liberado_por text;
alter table fila_processos add column if not exists liberado_em timestamptz;
