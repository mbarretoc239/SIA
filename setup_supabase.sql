-- Script de Inicialização de Banco de Dados: SIA Web (Supabase)
-- Rode isso no 'SQL Editor' do painel do seu Supabase

-- 1. Cria a Tabela de Configuração e Valores de Procedimentos
-- Aqui o 'valor' será salvo criptografado caso decida, ou limpo se não for tão sensível
CREATE TABLE IF NOT EXISTS tabela_procedimentos (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    codigo_tuss VARCHAR(20) NOT NULL UNIQUE,
    descricao TEXT NOT NULL,
    valor_unitario NUMERIC(10,2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Tabela de Histórico de Auditorias/Glosas
CREATE TABLE IF NOT EXISTS historico_glosas (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    auditor_id UUID REFERENCES auth.users(id), -- Relaciona com o sistema de Login do Supabase
    codigo_glosa VARCHAR(10) NOT NULL,
    paciente_nome_criptografado TEXT NOT NULL, -- Dados SENSÍVEIS (Criptografados via Fernet)
    numero_guia_criptografado TEXT,
    justificativa_texto TEXT,
    valor_glosado NUMERIC(10,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Habilitar a Segurança por Linhas (Row Level Security - RLS)
ALTER TABLE historico_glosas ENABLE ROW LEVEL SECURITY;

-- 4. Criar Política: Cada auditor só enxerga/altera as glosas que ele mesmo processou (Isolamento)
-- Pode ser removido depois se você quiser que todos os auditores vejam todas as produções.
CREATE POLICY "Auditores gerenciam as próprias glosas"
    ON historico_glosas
    FOR ALL
    USING (auth.uid() = auditor_id);
