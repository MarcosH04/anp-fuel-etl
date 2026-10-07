"""Etapa E (Extract): descobre as URLs e baixa os arquivos da ANP para a camada raw."""

from __future__ import annotations

import logging
import shutil
import zipfile
from datetime import date
from pathlib import Path

import requests

from anp_etl import config

log = logging.getLogger(__name__)

# Uma "fonte" é só um dicionário simples: {"label": nome-do-arquivo, "url": endereço}.
# Dicionários simples trafegam bem entre as tarefas do Airflow (XCom).
Source = dict[str, str]


def semester_source(year: int, semester: int) -> Source:
    """URL do arquivo semestral de combustíveis automotivos.

    A ANP mudou o formato ao longo do tempo, então existem 3 regras:
      * até 2021-2: arquivo .csv
      * 2022-1: caso especial, nome fora do padrão (.zip)
      * a partir de 2022-2: arquivo .zip contendo o .csv
    """
    if semester not in (1, 2):
        raise ValueError("semester deve ser 1 ou 2")
    if year < 2004:
        raise ValueError("a série histórica começa em 2004")

    label = f"ca-{year}-{semester:02d}"
    if (year, semester) == (2022, 1):
        url = f"{config.SEMESTER_BASE_URL}/precos-semestrais-ca.zip"
    elif (year, semester) >= (2022, 2):
        url = f"{config.SEMESTER_BASE_URL}/{label}.zip"
    else:
        url = f"{config.SEMESTER_BASE_URL}/{label}.csv"
    return {"label": label, "url": url}


def list_semester_sources(
    start_year: int, end_year: int, today: date | None = None
) -> list[Source]:
    """Lista os semestres JÁ ENCERRADOS entre start_year e end_year.

    Semestres em andamento ainda não têm arquivo semestral publicado; para eles
    use a carga semanal (últimas 4 semanas).
    """
    if start_year > end_year:
        raise ValueError("start_year não pode ser maior que end_year")
    today = today or date.today()
    sources: list[Source] = []
    for year in range(start_year, end_year + 1):
        for semester in (1, 2):
            semester_end = date(year, 6, 30) if semester == 1 else date(year, 12, 31)
            if semester_end < today:
                sources.append(semester_source(year, semester))
    return sources


def last_four_weeks_sources(today: date | None = None) -> list[Source]:
    """Arquivos das 4 últimas semanas (gasolina+etanol e diesel+GNV).

    Colocamos a data no nome para guardar uma cópia por execução na camada raw.
    """
    stamp = (today or date.today()).isoformat()
    return [
        {"label": f"ultimas-4-semanas-{name}-{stamp}", "url": url}
        for name, url in config.LAST_4_WEEKS_URLS.items()
    ]


def download_source(source: Source, raw_dir: Path | None = None) -> str:
    """Baixa a fonte para raw_dir e devolve o caminho do CSV resultante."""
    raw_dir = Path(raw_dir) if raw_dir else config.RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)

    target = raw_dir / f"{source['label']}.csv"
    partial = raw_dir / f"{source['label']}.download"

    log.info("Baixando %s", source["url"])
    headers = {"User-Agent": config.USER_AGENT}
    with requests.get(
        source["url"], headers=headers, stream=True, timeout=config.HTTP_TIMEOUT
    ) as response:
        if response.status_code == 404:
            raise FileNotFoundError(
                f"A ANP não tem este arquivo (404): {source['url']}. "
                "Se for um semestre recente, use a carga semanal."
            )
        response.raise_for_status()
        with open(partial, "wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                fh.write(chunk)

    _materialize_csv(partial, target)
    log.info("Arquivo raw salvo em %s (%.1f MB)", target, target.stat().st_size / 1e6)
    return str(target)


def _materialize_csv(downloaded: Path, target: Path) -> None:
    """Transforma o download em um CSV: descompacta se for ZIP, valida se for CSV."""
    if zipfile.is_zipfile(downloaded):
        with zipfile.ZipFile(downloaded) as archive:
            csv_names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                raise ValueError("O ZIP baixado não contém nenhum .csv")
            if len(csv_names) > 1:
                log.warning(
                    "O ZIP tem %d CSVs; usando o primeiro: %s", len(csv_names), csv_names[0]
                )
            with archive.open(csv_names[0]) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
        downloaded.unlink()
    else:
        with open(downloaded, "rb") as fh:
            head = fh.read(512).lstrip().lower()
        # Sites do governo às vezes respondem 200 com uma página HTML de erro.
        if head.startswith((b"<!doctype", b"<html")):
            raise ValueError("O servidor devolveu uma página HTML em vez de um CSV")
        downloaded.replace(target)

    if target.stat().st_size == 0:
        raise ValueError("O arquivo baixado está vazio")
