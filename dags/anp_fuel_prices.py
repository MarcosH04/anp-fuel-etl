"""DAGs do pipeline de preços de combustíveis da ANP.

Uma DAG (Directed Acyclic Graph) é o "mapa de tarefas" que o Airflow executa.
Aqui existem duas:

  1. anp_backfill_historico  -> manual: carrega semestres antigos (você escolhe o intervalo)
  2. anp_incremental_semanal -> automática: todo sábado, carrega as últimas 4 semanas

As duas usam as mesmas tarefas: extract -> transform -> load.
O .expand() cria uma tarefa por arquivo (Dynamic Task Mapping), rodando em paralelo.

Boa prática: as tarefas passam só CAMINHOS de arquivo entre si (via XCom), nunca DataFrames.
"""

import pendulum
from airflow.decorators import dag, task
from airflow.models.param import Param

from anp_etl import pipeline
from anp_etl.extract import last_four_weeks_sources, list_semester_sources

TZ = "America/Sao_Paulo"

DEFAULT_ARGS = {
    "owner": "data-eng",
    "retries": 2,  # falhas de rede acontecem: tenta de novo antes de desistir
    "retry_delay": pendulum.duration(minutes=2),
}


# --- Tarefas compartilhadas -------------------------------------------------------------
@task
def init_warehouse() -> None:
    """Cria schema/tabelas/views no PostgreSQL (idempotente)."""
    pipeline.init_warehouse()


@task
def extract(source: dict) -> str:
    """E: baixa o arquivo da ANP para a camada raw. Devolve o caminho do CSV."""
    return pipeline.run_extract(source)


@task
def transform(raw_path: str) -> str:
    """T: limpa e padroniza. Devolve o caminho do Parquet."""
    return pipeline.run_transform(raw_path)


@task
def load(parquet_path: str) -> dict:
    """L: carrega no PostgreSQL com upsert. Devolve um resumo da carga."""
    return pipeline.run_load(parquet_path)


# --- DAG 1: carga histórica (manual) --------------------------------------------------------
@dag(
    dag_id="anp_backfill_historico",
    description="Carga histórica semestral de preços de combustíveis (ANP). Disparo manual.",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz=TZ),
    catchup=False,
    default_args=DEFAULT_ARGS,
    params={
        "start_year": Param(2024, type="integer", minimum=2004, description="Ano inicial"),
        "end_year": Param(2025, type="integer", minimum=2004, description="Ano final"),
    },
    max_active_tasks=2,  # no máximo 2 tarefas ao mesmo tempo: poupa memória do seu PC
    tags=["anp", "etl", "backfill"],
)
def anp_backfill_historico():
    @task
    def plan_sources(**context) -> list[dict]:
        params = context["params"]
        return list_semester_sources(int(params["start_year"]), int(params["end_year"]))

    ready = init_warehouse()
    sources = plan_sources()
    raw_files = extract.expand(source=sources)
    parquet_files = transform.expand(raw_path=raw_files)
    load.expand(parquet_path=parquet_files)

    ready >> sources


# --- DAG 2: carga incremental (automática, todo sábado) --------------------------------------
@dag(
    dag_id="anp_incremental_semanal",
    description="Carga semanal: arquivos das últimas 4 semanas (gasolina, etanol, diesel, GNV).",
    schedule="0 8 * * 6",  # sábado, 08:00 (horário de São Paulo)
    start_date=pendulum.datetime(2026, 1, 1, tz=TZ),
    catchup=False,
    default_args=DEFAULT_ARGS,
    max_active_runs=1,
    tags=["anp", "etl", "incremental"],
)
def anp_incremental_semanal():
    @task
    def plan_sources() -> list[dict]:
        return last_four_weeks_sources()

    ready = init_warehouse()
    sources = plan_sources()
    raw_files = extract.expand(source=sources)
    parquet_files = transform.expand(raw_path=raw_files)
    load.expand(parquet_path=parquet_files)

    ready >> sources


anp_backfill_historico()
anp_incremental_semanal()
