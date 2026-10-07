"""Etapa L (Load): carrega o Parquet limpo no PostgreSQL de forma idempotente.

Idempotente = rodar duas vezes o mesmo arquivo dá o mesmo resultado (sem duplicar linhas).
Como funciona:
  1. COPY dos dados para uma tabela temporária (rápido, em lote)
  2. INSERT ... ON CONFLICT DO UPDATE na tabela final (o "upsert")
  3. Registro da execução na tabela de auditoria anp.etl_execucoes
"""

from __future__ import annotations

import io
import json
import logging
from contextlib import closing
from pathlib import Path

import pandas as pd
import psycopg2

from anp_etl import config
from anp_etl.transform import FINAL_COLUMNS, KEY_COLUMNS

log = logging.getLogger(__name__)

TABLE = "anp.precos_combustiveis"
UPDATE_COLUMNS = [c for c in FINAL_COLUMNS if c not in KEY_COLUMNS]

AUDIT_SQL = """
INSERT INTO anp.etl_execucoes
    (arquivo_origem, linhas_lidas, linhas_rejeitadas, duplicatas_removidas,
     linhas_validas, linhas_afetadas)
VALUES (%s, %s, %s, %s, %s, %s)
"""


def get_connection():
    conn = psycopg2.connect(config.warehouse_dsn())
    # Nossos dados e .sql têm acentos (SÃO PAULO, "Série"...): não dependa do padrão do servidor.
    conn.set_client_encoding("UTF8")
    return conn


def ensure_schema() -> None:
    """Executa os arquivos sql/*.sql em ordem. Eles usam IF NOT EXISTS, então são seguros."""
    sql_files = sorted(config.SQL_DIR.glob("*.sql"))
    if not sql_files:
        raise FileNotFoundError(f"Nenhum arquivo .sql encontrado em {config.SQL_DIR}")
    with closing(get_connection()) as conn, conn, conn.cursor() as cur:
        for sql_file in sql_files:
            log.info("Aplicando %s", sql_file.name)
            cur.execute(sql_file.read_text(encoding="utf-8"))


def load_parquet(parquet_path: str | Path) -> dict:
    """Carrega um Parquet limpo e devolve um resumo da carga."""
    path = Path(parquet_path)
    df = pd.read_parquet(path)

    stats_path = path.with_suffix(".stats.json")
    stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}

    # Datas em formato ISO para o COPY; nulos viram vazio (= NULL no CSV do Postgres)
    df["data_coleta"] = pd.to_datetime(df["data_coleta"]).dt.strftime("%Y-%m-%d")
    buffer = io.StringIO()
    df[FINAL_COLUMNS].to_csv(buffer, index=False, header=False)
    buffer.seek(0)

    columns = ", ".join(FINAL_COLUMNS)
    key = ", ".join(KEY_COLUMNS)
    assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in UPDATE_COLUMNS)
    # Só atualiza se algo mudou de fato (evita reescrever linhas idênticas)
    changed = " OR ".join(f"t.{c} IS DISTINCT FROM EXCLUDED.{c}" for c in UPDATE_COLUMNS)

    with closing(get_connection()) as conn, conn, conn.cursor() as cur:
        cur.execute(
            f"CREATE TEMP TABLE stg_precos (LIKE {TABLE} INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        cur.copy_expert(f"COPY stg_precos ({columns}) FROM STDIN WITH (FORMAT csv)", buffer)
        cur.execute(
            f"""
            INSERT INTO {TABLE} AS t ({columns})
            SELECT {columns} FROM stg_precos
            ON CONFLICT ({key}) DO UPDATE
               SET {assignments}, carregado_em = now()
             WHERE {changed}
            """
        )
        affected = cur.rowcount
        cur.execute(
            AUDIT_SQL,
            (
                stats.get("arquivo_origem", path.stem),
                stats.get("linhas_lidas", len(df)),
                stats.get("linhas_rejeitadas", 0),
                stats.get("duplicatas_removidas", 0),
                stats.get("linhas_validas", len(df)),
                affected,
            ),
        )

    summary = {
        "arquivo": path.stem,
        "linhas_no_arquivo": len(df),
        "linhas_inseridas_ou_alteradas": affected,
    }
    log.info("Load OK: %s", summary)
    return summary
