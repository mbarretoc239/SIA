-- Histórico de inativação/reativação de alinhamentos.
-- Hoje toggle_ativo_alinhamento grava a justificativa só em
-- alinhamentos.justificativa_inativacao, que é zerada ao reativar (sem
-- rastro de quem/quando/motivo anterior). Esta tabela guarda cada evento
-- permanentemente, sem tocar na linha de alinhamentos.

CREATE TABLE IF NOT EXISTS alinhamentos_historico_status (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    alinhamento_id uuid NOT NULL REFERENCES alinhamentos(id) ON DELETE CASCADE,
    tipo text NOT NULL CHECK (tipo IN ('inativacao', 'reativacao')),
    justificativa text,
    usuario_id uuid REFERENCES usuarios(id),
    usuario_nome text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alinhamentos_historico_status_alinhamento
    ON alinhamentos_historico_status (alinhamento_id, created_at DESC);

-- Sem RLS aqui de propósito: alinhamentos e alinhamentos_lidos também não
-- têm (acessadas com a chave anon via self.headers em shared/database.py).
-- Se alinhamentos tiver RLS/policy própria no projeto, espelhar aqui.
