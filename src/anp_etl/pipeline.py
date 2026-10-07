"""Cola entre as etapas E, T e L.

Os imports ficam DENTRO das funções de propósito: o Airflow lê os arquivos da pasta dags/
a cada poucos segundos, e importar pandas toda vez deixaria isso lento. (Boa prática!)
"""

from __future__ import annotations


def init_warehouse() -> None:
    from anp_etl import load

    load.ensure_schema()


def run_extract(source: dict) -> str:
    from anp_etl import extract

    return extract.download_source(source)


def run_transform(raw_path: str) -> str:
    from anp_etl import transform

    return transform.transform_file(raw_path)


def run_load(parquet_path: str) -> dict:
    from anp_etl import load

    return load.load_parquet(parquet_path)


def run_all(source: dict) -> dict:
    """E -> T -> L de uma vez (usado pela linha de comando)."""
    return run_load(run_transform(run_extract(source)))
