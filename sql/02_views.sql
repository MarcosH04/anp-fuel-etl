-- Views analíticas (camada "gold"): respondem perguntas de negócio sem repetir SQL.

-- 1) Preço médio semanal por estado e produto
CREATE OR REPLACE VIEW anp.vw_preco_medio_semanal_uf AS
SELECT
    date_trunc('week', data_coleta)::date AS semana,
    uf,
    produto,
    round(avg(valor_venda), 3) AS preco_medio,
    min(valor_venda)           AS preco_minimo,
    max(valor_venda)           AS preco_maximo,
    count(*)                   AS n_coletas
FROM anp.precos_combustiveis
GROUP BY 1, 2, 3;

-- 2) Preço médio mensal por município e produto
CREATE OR REPLACE VIEW anp.vw_preco_medio_mensal_municipio AS
SELECT
    date_trunc('month', data_coleta)::date AS mes,
    uf,
    municipio,
    produto,
    round(avg(valor_venda), 3) AS preco_medio,
    count(*)                   AS n_coletas
FROM anp.precos_combustiveis
GROUP BY 1, 2, 3, 4;

-- 3) Vale mais a pena abastecer com etanol ou gasolina? (regra dos 70%)
--    Se o preço do etanol for até 70% do da gasolina, o etanol compensa.
CREATE OR REPLACE VIEW anp.vw_paridade_etanol_gasolina_uf AS
WITH medias AS (
    SELECT
        date_trunc('month', data_coleta)::date AS mes,
        uf,
        avg(valor_venda) FILTER (WHERE produto ILIKE 'ETANOL%') AS etanol,
        avg(valor_venda) FILTER (
            WHERE produto ILIKE 'GASOLINA%' AND produto NOT ILIKE '%ADITIVADA%'
        ) AS gasolina
    FROM anp.precos_combustiveis
    GROUP BY 1, 2
)
SELECT
    mes,
    uf,
    round(etanol, 3)   AS preco_etanol,
    round(gasolina, 3) AS preco_gasolina,
    round(etanol / NULLIF(gasolina, 0), 3) AS razao_etanol_gasolina,
    CASE WHEN etanol / NULLIF(gasolina, 0) <= 0.70
         THEN 'ETANOL' ELSE 'GASOLINA' END AS compensa_abastecer_com
FROM medias
WHERE etanol IS NOT NULL AND gasolina IS NOT NULL;
