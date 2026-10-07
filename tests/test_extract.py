"""Testes da etapa de extração (sem acessar a internet)."""

import zipfile
from datetime import date

import pytest

from anp_etl import extract


def test_semester_url_rules():
    base = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsas/ca"
    assert extract.semester_source(2026, 1)["url"] == f"{base}/ca-2026-01.zip"
    assert extract.semester_source(2022, 2)["url"] == f"{base}/ca-2022-02.zip"
    assert extract.semester_source(2022, 1)["url"] == f"{base}/precos-semestrais-ca.zip"  # exceção
    assert extract.semester_source(2021, 2)["url"] == f"{base}/ca-2021-02.csv"
    assert extract.semester_source(2010, 1)["label"] == "ca-2010-01"


@pytest.mark.parametrize("year, semester", [(2003, 1), (2024, 3)])
def test_semester_source_validates_input(year, semester):
    with pytest.raises(ValueError):
        extract.semester_source(year, semester)


def test_list_semesters_skips_unfinished_ones():
    today = date(2026, 10, 6)  # o 2º semestre de 2026 ainda não acabou
    labels = [s["label"] for s in extract.list_semester_sources(2025, 2026, today=today)]
    assert labels == ["ca-2025-01", "ca-2025-02", "ca-2026-01"]


def test_list_semesters_rejects_inverted_range():
    with pytest.raises(ValueError):
        extract.list_semester_sources(2026, 2025)


def test_last_four_weeks_sources_are_stamped_with_date():
    sources = extract.last_four_weeks_sources(today=date(2026, 10, 6))
    assert [s["label"] for s in sources] == [
        "ultimas-4-semanas-gasolina-etanol-2026-10-06",
        "ultimas-4-semanas-diesel-gnv-2026-10-06",
    ]
    assert all(s["url"].endswith(".csv") for s in sources)


def test_materialize_csv_unzips(tmp_path):
    downloaded = tmp_path / "x.download"
    with zipfile.ZipFile(downloaded, "w") as archive:
        archive.writestr("ca-2025-01.csv", "a;b\n1;2\n")
    target = tmp_path / "x.csv"

    extract._materialize_csv(downloaded, target)

    assert target.read_text() == "a;b\n1;2\n"
    assert not downloaded.exists()


def test_materialize_csv_rejects_html_error_pages(tmp_path):
    downloaded = tmp_path / "x.download"
    downloaded.write_text("<!DOCTYPE html><html>Erro</html>")
    with pytest.raises(ValueError, match="HTML"):
        extract._materialize_csv(downloaded, tmp_path / "x.csv")


def test_materialize_csv_rejects_empty_files(tmp_path):
    downloaded = tmp_path / "x.download"
    downloaded.write_bytes(b"")
    with pytest.raises(ValueError, match="vazio"):
        extract._materialize_csv(downloaded, tmp_path / "x.csv")
