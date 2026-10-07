-- Schema e tabelas do data warehouse.
-- Todos os comandos usam IF NOT EXISTS: pode rodar quantas vezes quiser.

CREATE SCHEMA IF NOT EXISTS anp;

-- Tabela principal: um preço por posto, por produto, por dia de coleta.
CREATE TABLE IF NOT EXISTS anp.precos_combustiveis (
    cnpj_revenda    VARCHAR(14)   NOT NULL,   -- só dígitos
    produto         TEXT          NOT NULL,   -- GASOLINA, ETANOL, DIESEL S10, GNV...
    data_coleta     DATE          NOT NULL,
    valor_venda     NUMERIC(8, 3) NOT NULL CHECK (valor_venda > 0),
    valor_compra    NUMERIC(8, 3),            -- só existe até ago/2020
    unidade_medida  TEXT,
    revenda         TEXT,
    bandeira        TEXT,
    regiao          VARCHAR(2),
    uf              VARCHAR(2),
    municipio       TEXT,
    bairro          TEXT,
    cep             VARCHAR(8),
    logradouro      TEXT,
    numero          TEXT,
    complemento     TEXT,
    arquivo_origem  TEXT,                     -- de qual arquivo a linha veio (rastreabilidade)
    carregado_em    TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (cnpj_revenda, produto, data_coleta)
);

CREATE INDEX IF NOT EXISTS idx_precos_data
    ON anp.precos_combustiveis (data_coleta);
CREATE INDEX IF NOT EXISTS idx_precos_uf_produto_data
    ON anp.precos_combustiveis (uf, produto, data_coleta);

-- Tabela de auditoria: uma linha por arquivo carregado.
CREATE TABLE IF NOT EXISTS anp.etl_execucoes (
    id                    BIGSERIAL PRIMARY KEY,
    arquivo_origem        TEXT        NOT NULL,
    linhas_lidas          INTEGER,
    linhas_rejeitadas     INTEGER,
    duplicatas_removidas  INTEGER,
    linhas_validas        INTEGER,
    linhas_afetadas       INTEGER,
    executado_em          TIMESTAMPTZ NOT NULL DEFAULT now()
);
