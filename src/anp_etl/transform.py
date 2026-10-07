"""Etapa T (Transform): limpa e padroniza os dados brutos da ANP.

Entrada : CSV bruto (separador ";", decimal com vírgula, datas dd/mm/aaaa).
Saída   : Parquet limpo + um JSON com estatísticas de qualidade.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path

import pandas as pd

from anp_etl import config

log = logging.getLogger(__name__)

# Nome da coluna na ANP (depois de normalizar) -> nome da coluna no nosso banco.
COLUMN_MAP = {
    "regiao_sigla": "regiao",
    "estado_sigla": "uf",
    "municipio": "municipio",
    "revenda": "revenda",
    "cnpj_da_revenda": "cnpj_revenda",
    "nome_da_rua": "logradouro",
    "numero_rua": "numero",
    "complemento": "complemento",
    "bairro": "bairro",
    "cep": "cep",
    "produto": "produto",
    "data_da_coleta": "data_coleta",
    "valor_de_venda": "valor_venda",
    "valor_de_compra": "valor_compra",
    "unidade_de_medida": "unidade_medida",
    "bandeira": "bandeira",
}

FINAL_COLUMNS = [
    "cnpj_revenda",
    "produto",
    "data_coleta",
    "valor_venda",
    "valor_compra",
    "unidade_medida",
    "revenda",
    "bandeira",
    "regiao",
    "uf",
    "municipio",
    "bairro",
    "cep",
    "logradouro",
    "numero",
    "complemento",
    "arquivo_origem",
]
# Chave primária da tabela: um posto tem no máximo um preço por produto por dia.
KEY_COLUMNS = ["cnpj_revenda", "produto", "data_coleta"]
# Sem estas colunas o arquivo não faz sentido: falhamos cedo, com mensagem clara.
REQUIRED_COLUMNS = ["cnpj_revenda", "produto", "data_coleta", "valor_venda", "uf", "municipio"]
UPPERCASE_COLUMNS = ["regiao", "uf", "municipio", "produto", "bandeira"]
NON_TEXT_COLUMNS = {"data_coleta", "valor_venda", "valor_compra", "arquivo_origem"}
TEXT_COLUMNS = [c for c in FINAL_COLUMNS if c not in NON_TEXT_COLUMNS]


# --------------------------------------------------------------------------------------
# Leitura
# --------------------------------------------------------------------------------------
def normalize_column_name(name: str) -> str:
    """'Município - Sigla' -> 'municipio_sigla' (sem acento, minúsculo, com underscore)."""
    name = name.replace("ï»¿", "").lstrip("﻿")  # resíduos de BOM (marca de UTF-8)
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _detect_separator(path: Path, encoding: str) -> str:
    with open(path, encoding=encoding, errors="replace") as fh:
        header = fh.readline()
    return ";" if header.count(";") >= header.count(",") else ","


def read_raw_csv(path: str | Path) -> pd.DataFrame:
    """Lê o CSV como texto puro (dtype=str). Convertemos os tipos nós mesmos, depois."""
    path = Path(path)
    for encoding in ("utf-8-sig", "latin-1"):
        sep = _detect_separator(path, encoding)
        try:
            df = pd.read_csv(path, sep=sep, dtype=str, encoding=encoding, on_bad_lines="warn")
        except UnicodeDecodeError:
            log.warning("Arquivo não está em %s; tentando a próxima codificação", encoding)
            continue
        log.info("Lido %s: %d linhas (encoding=%s, sep=%r)", path.name, len(df), encoding, sep)
        return df
    raise RuntimeError(f"Não foi possível decodificar {path}")  # latin-1 não falha, por segurança


# --------------------------------------------------------------------------------------
# Conversões de tipo
# --------------------------------------------------------------------------------------
def _as_bool(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(bool)


def _parse_decimal(series: pd.Series) -> pd.Series:
    """'6,29' -> 6.29 ; '1.234,56' -> 1234.56 ; texto inválido -> NaN."""
    text = series.astype("string").str.strip()
    has_comma = _as_bool(text.str.contains(",", regex=False))
    brazilian = text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    text = text.where(~has_comma, brazilian)
    return pd.to_numeric(text, errors="coerce").astype("float64")


def _parse_date(series: pd.Series) -> pd.Series:
    """Aceita dd/mm/aaaa (padrão da ANP) e, como plano B, aaaa-mm-dd."""
    text = series.astype("string").str.strip().str.slice(0, 10)
    parsed = pd.to_datetime(text, format="%d/%m/%Y", errors="coerce")
    missing = parsed.isna() & text.notna()
    if missing.any():
        iso = pd.to_datetime(text[missing], format="%Y-%m-%d", errors="coerce")
        parsed = parsed.fillna(iso)
    return parsed


def _pad_digits(series: pd.Series, width: int, min_len: int) -> pd.Series:
    """Mantém só dígitos e recompõe zeros à esquerda perdidos (ex.: Excel come o zero do CNPJ)."""
    digits = series.str.replace(r"\D", "", regex=True).replace("", pd.NA)
    padded = digits.str.zfill(width)
    return padded.where(_as_bool(digits.str.len() >= min_len), digits)


# --------------------------------------------------------------------------------------
# Transformação principal (função "pura": recebe DataFrame, devolve DataFrame + estatísticas)
# --------------------------------------------------------------------------------------
def transform_dataframe(raw: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, dict]:
    df = raw.copy()
    df.columns = [normalize_column_name(c) for c in df.columns]
    df = df.rename(columns=COLUMN_MAP)
    df = df.loc[:, ~df.columns.duplicated()]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Colunas obrigatórias ausentes: {missing}. Colunas encontradas: {list(df.columns)}. "
            "A ANP pode ter mudado o layout do arquivo."
        )

    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[FINAL_COLUMNS].copy()
    rows_read = len(df)

    # Texto: tira espaços e transforma "" em nulo
    for col in TEXT_COLUMNS:
        df[col] = df[col].astype("string").str.strip().replace("", pd.NA)
    for col in UPPERCASE_COLUMNS:
        df[col] = df[col].str.upper()

    df["cnpj_revenda"] = _pad_digits(df["cnpj_revenda"], width=14, min_len=13)
    df["cep"] = _pad_digits(df["cep"], width=8, min_len=7)

    # Números e datas
    df["valor_venda"] = _parse_decimal(df["valor_venda"])
    df["valor_compra"] = _parse_decimal(df["valor_compra"])  # só existe até ago/2020
    df.loc[~df["valor_compra"].between(config.PRICE_MIN, config.PRICE_MAX), "valor_compra"] = float(
        "nan"
    )
    df["data_coleta"] = _parse_date(df["data_coleta"])

    # Regras de qualidade: o que não passa é rejeitado (e contado!)
    valid = (
        _as_bool(df["cnpj_revenda"].str.len() == 14)
        & _as_bool(df["produto"].notna())
        & _as_bool(df["data_coleta"].notna())
        & _as_bool(df["valor_venda"].between(config.PRICE_MIN, config.PRICE_MAX))
    )
    rejected = int((~valid).sum())
    df = df.loc[valid].copy()

    # Deduplicação pela chave primária (mantém a última ocorrência)
    before = len(df)
    df = df.drop_duplicates(subset=KEY_COLUMNS, keep="last")
    duplicates = before - len(df)

    df = df.assign(arquivo_origem=source_name).reset_index(drop=True)

    stats = {
        "arquivo_origem": source_name,
        "linhas_lidas": int(rows_read),
        "linhas_rejeitadas": rejected,
        "duplicatas_removidas": int(duplicates),
        "linhas_validas": int(len(df)),
    }
    return df, stats


def check_quality(stats: dict) -> None:
    """Portão de qualidade: se o arquivo está muito ruim, a tarefa FALHA em vez de carregar lixo."""
    if stats["linhas_lidas"] == 0:
        raise ValueError(f"{stats['arquivo_origem']}: arquivo sem linhas de dados")
    if stats["linhas_validas"] == 0:
        raise ValueError(f"{stats['arquivo_origem']}: nenhuma linha válida após a limpeza")
    ratio = stats["linhas_rejeitadas"] / stats["linhas_lidas"]
    if ratio > config.MAX_REJECTED_RATIO:
        raise ValueError(
            f"{stats['arquivo_origem']}: {ratio:.1%} das linhas foram rejeitadas "
            f"(limite {config.MAX_REJECTED_RATIO:.0%}). Verifique o layout do arquivo."
        )


def transform_file(raw_path: str | Path, out_dir: str | Path | None = None) -> str:
    """CSV bruto -> Parquet limpo (+ JSON de estatísticas). Devolve o caminho do Parquet."""
    raw_path = Path(raw_path)
    out_dir = Path(out_dir) if out_dir else config.PROCESSED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = read_raw_csv(raw_path)
    clean, stats = transform_dataframe(raw, source_name=raw_path.stem)
    check_quality(stats)

    out_path = out_dir / f"{raw_path.stem}.parquet"
    clean.to_parquet(out_path, index=False)
    out_path.with_suffix(".stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("Transform OK: %s", stats)
    return str(out_path)
