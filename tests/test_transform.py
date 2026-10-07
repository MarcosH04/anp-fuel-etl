"""Testes da etapa de transformação. Usam dados de exemplo no layout oficial da ANP."""

import json

import pandas as pd
import pytest

from anp_etl import config, transform

HEADER = (
    "Regiao - Sigla;Estado - Sigla;Municipio;Revenda;CNPJ da Revenda;Nome da Rua;Numero Rua;"
    "Complemento;Bairro;Cep;Produto;Data da Coleta;Valor de Venda;Valor de Compra;"
    "Unidade de Medida;Bandeira"
)


def make_csv(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


GOOD_ROW_1 = (
    "SE;MG;PATOS DE MINAS;POSTO EXEMPLO A;12.345.678/0001-95;RUA A;100;;CENTRO;38700-000;"
    "GASOLINA;28/09/2026;6,29;;R$ / litro;BRANCA"
)
GOOD_ROW_2 = (
    "SE;mg;Patos de Minas;POSTO EXEMPLO B;98.765.432/0001-10;RUA B;200;LOJA 1;Jardim;38700001;"
    "ETANOL;28/09/2026;4,19;;R$ / litro;IPIRANGA"
)


def run(csv_text: str, tmp_path, name="amostra"):
    path = tmp_path / f"{name}.csv"
    path.write_text(csv_text, encoding="utf-8")
    df = transform.read_raw_csv(path)
    return transform.transform_dataframe(df, source_name=name)


# ---------------------------------------------------------------- nomes de colunas
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Regiao - Sigla", "regiao_sigla"),
        ("Município", "municipio"),
        ("CNPJ da Revenda", "cnpj_da_revenda"),
        ("﻿Regiao - Sigla", "regiao_sigla"),  # BOM no início do arquivo
        ("ï»¿Regiao - Sigla", "regiao_sigla"),  # BOM lido como latin-1
    ],
)
def test_normalize_column_name(raw, expected):
    assert transform.normalize_column_name(raw) == expected


# ---------------------------------------------------------------- caminho feliz
def test_transform_cleans_and_types_columns(tmp_path):
    df, stats = run(make_csv(GOOD_ROW_1, GOOD_ROW_2), tmp_path)

    assert list(df.columns) == transform.FINAL_COLUMNS
    assert stats == {
        "arquivo_origem": "amostra",
        "linhas_lidas": 2,
        "linhas_rejeitadas": 0,
        "duplicatas_removidas": 0,
        "linhas_validas": 2,
    }

    gasolina = df[df["produto"] == "GASOLINA"].iloc[0]
    assert gasolina["valor_venda"] == pytest.approx(6.29)
    assert gasolina["cnpj_revenda"] == "12345678000195"  # só dígitos
    assert gasolina["cep"] == "38700000"
    assert gasolina["data_coleta"] == pd.Timestamp("2026-09-28")
    assert pd.isna(gasolina["valor_compra"])

    etanol = df[df["produto"] == "ETANOL"].iloc[0]
    assert etanol["uf"] == "MG"  # maiúsculo
    assert etanol["municipio"] == "PATOS DE MINAS"


def test_thousands_separator_and_numeric_price():
    series = pd.Series(["1.234,56", "6,29", "5.89", "abc", None])
    parsed = transform._parse_decimal(series)
    assert parsed.iloc[0] == pytest.approx(1234.56)
    assert parsed.iloc[1] == pytest.approx(6.29)
    assert parsed.iloc[2] == pytest.approx(5.89)
    assert pd.isna(parsed.iloc[3]) and pd.isna(parsed.iloc[4])


def test_cnpj_loses_leading_zero_is_restored():
    series = pd.Series(["1234567000195", "12", None], dtype="string")  # 13 dígitos, curto, nulo
    padded = transform._pad_digits(series, width=14, min_len=13)
    assert padded.iloc[0] == "01234567000195"
    assert padded.iloc[1] == "12"  # curto demais: não inventamos zeros (será rejeitado)
    assert pd.isna(padded.iloc[2])


def test_iso_dates_are_accepted_as_fallback():
    parsed = transform._parse_date(pd.Series(["28/09/2026", "2026-09-29", "lixo"]))
    assert parsed.iloc[0] == pd.Timestamp("2026-09-28")
    assert parsed.iloc[1] == pd.Timestamp("2026-09-29")
    assert pd.isna(parsed.iloc[2])


# ---------------------------------------------------------------- rejeições e duplicatas
def test_invalid_rows_are_rejected_and_counted(tmp_path):
    def variant(cnpj: str) -> str:
        """Cópia da linha boa com outro CNPJ (para não virar duplicata da chave primária)."""
        return GOOD_ROW_1.replace("12.345.678/0001-95", cnpj)

    bad_price = variant("11.111.111/0001-11").replace("6,29", "abc")
    zero_price = variant("22.222.222/0001-22").replace("6,29", "0,00")
    bad_cnpj = variant("123")
    bad_date = variant("33.333.333/0001-33").replace("28/09/2026", "31/02/2026")
    df, stats = run(make_csv(GOOD_ROW_2, bad_price, zero_price, bad_cnpj, bad_date), tmp_path)

    assert stats["linhas_lidas"] == 5
    assert stats["linhas_rejeitadas"] == 4
    assert stats["linhas_validas"] == 1
    assert len(df) == 1


def test_duplicates_on_primary_key_keep_last(tmp_path):
    older = GOOD_ROW_1
    newer = GOOD_ROW_1.replace("6,29", "6,49")
    df, stats = run(make_csv(older, newer), tmp_path)

    assert stats["duplicatas_removidas"] == 1
    assert len(df) == 1
    assert df.iloc[0]["valor_venda"] == pytest.approx(6.49)


def test_missing_required_column_raises_helpful_error(tmp_path):
    csv_text = "Produto;Valor de Venda\nGASOLINA;6,29\n"
    path = tmp_path / "ruim.csv"
    path.write_text(csv_text, encoding="utf-8")
    with pytest.raises(ValueError, match="Colunas obrigatórias ausentes"):
        transform.transform_dataframe(transform.read_raw_csv(path), "ruim")


def test_quality_gate_fails_when_too_many_rows_rejected():
    stats = {
        "arquivo_origem": "x",
        "linhas_lidas": 100,
        "linhas_rejeitadas": 50,
        "duplicatas_removidas": 0,
        "linhas_validas": 50,
    }
    with pytest.raises(ValueError, match="rejeitadas"):
        transform.check_quality(stats)

    stats.update(linhas_rejeitadas=5, linhas_validas=95)
    transform.check_quality(stats)  # não levanta erro


# ---------------------------------------------------------------- arquivo ponta a ponta
def test_transform_file_handles_latin1_and_writes_parquet_and_stats(tmp_path):
    row = GOOD_ROW_1.replace("PATOS DE MINAS", "SÃO PAULO")
    text = make_csv(row, GOOD_ROW_2).replace("Municipio", "Município")
    raw_path = tmp_path / "ca-2025-01.csv"
    raw_path.write_bytes(text.encode("latin-1"))  # codificação antiga, comum em dados públicos

    out = transform.transform_file(raw_path, out_dir=tmp_path / "processed")

    df = pd.read_parquet(out)
    assert len(df) == 2
    assert "SÃO PAULO" in set(df["municipio"])
    assert (df["arquivo_origem"] == "ca-2025-01").all()

    stats = json.loads((tmp_path / "processed" / "ca-2025-01.stats.json").read_text("utf-8"))
    assert stats["linhas_validas"] == 2


def test_price_limits_come_from_config():
    assert config.PRICE_MIN < config.PRICE_MAX
