"""Linha de comando para rodar o pipeline SEM o Airflow (ótimo para testar e depurar).

Exemplos:
    python -m anp_etl.cli init-db
    python -m anp_etl.cli semester --year 2025 --semester 1
    python -m anp_etl.cli last4weeks
    python -m anp_etl.cli url "https://.../arquivo.csv" --label meu-arquivo
"""

from __future__ import annotations

import argparse
import logging

from anp_etl import pipeline
from anp_etl.extract import last_four_weeks_sources, semester_source


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline ETL de preços de combustíveis (ANP)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="cria schema, tabelas e views no PostgreSQL")

    p_sem = sub.add_parser("semester", help="carrega um semestre inteiro")
    p_sem.add_argument("--year", type=int, required=True)
    p_sem.add_argument("--semester", type=int, choices=(1, 2), required=True)

    sub.add_parser("last4weeks", help="carrega os arquivos das últimas 4 semanas")

    p_url = sub.add_parser(
        "url", help="carrega qualquer CSV/ZIP da ANP por URL (ex.: arquivos mensais)"
    )
    p_url.add_argument("url")
    p_url.add_argument("--label", required=True, help="nome do arquivo na camada raw")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.command == "init-db":
        pipeline.init_warehouse()
        return

    if args.command == "semester":
        sources = [semester_source(args.year, args.semester)]
    elif args.command == "last4weeks":
        sources = last_four_weeks_sources()
    else:
        sources = [{"label": args.label, "url": args.url}]

    pipeline.init_warehouse()
    for source in sources:
        print(pipeline.run_all(source))


if __name__ == "__main__":
    main()
