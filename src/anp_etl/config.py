"""Configurações centrais do projeto.

Tudo que pode mudar entre o seu computador, o Docker e o GitHub Actions é lido de
variáveis de ambiente. Assim o código não muda, só o ambiente.
"""

from __future__ import annotations

import os
from pathlib import Path

# src/anp_etl/config.py -> parents[2] é a raiz do projeto
# (dentro do container, a raiz é /opt/airflow)
ROOT_DIR = Path(__file__).resolve().parents[2]

# Camadas do "data lake" local:
#   raw       = arquivo exatamente como veio da ANP (nunca editamos)
#   processed = dados limpos em Parquet, prontos para carregar no banco
DATA_DIR = Path(os.getenv("ANP_DATA_DIR", ROOT_DIR / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SQL_DIR = Path(os.getenv("ANP_SQL_DIR", ROOT_DIR / "sql"))

# --- Fonte de dados: ANP, Série Histórica de Preços de Combustíveis ---------------
BASE_URL = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc"
SEMESTER_BASE_URL = f"{BASE_URL}/dsas/ca"  # ca = combustíveis automotivos

# Arquivos "quatro últimas semanas": URL fixa, atualizada toda semana pela ANP.
LAST_4_WEEKS_URLS = {
    "gasolina-etanol": f"{BASE_URL}/qus/ultimas-4-semanas-gasolina-etanol.csv",
    "diesel-gnv": f"{BASE_URL}/qus/ultimas-4-semanas-diesel-gnv.csv",
}

# Alguns sites bloqueiam o User-Agent padrão do Python; identificamos o projeto.
USER_AGENT = "Mozilla/5.0 (compatible; anp-fuel-etl/1.0)"
HTTP_TIMEOUT = (10, 300)  # (segundos para conectar, segundos para ler)

# --- Regras de qualidade -------------------------------------------------------------
PRICE_MIN = 0.5  # R$/litro (ou R$/m³ no GNV): abaixo disso é erro de digitação
PRICE_MAX = 50.0
MAX_REJECTED_RATIO = 0.20  # se mais de 20% das linhas forem rejeitadas, o arquivo falha


def warehouse_dsn() -> str:
    """Monta a string de conexão do PostgreSQL (o "data warehouse")."""
    explicit = os.getenv("WAREHOUSE_DSN")
    if explicit:
        return explicit
    # Padrões pensados para rodar o código no seu PC, fora do Docker.
    # Dentro do Docker, o docker-compose.yml sobrescreve essas variáveis.
    host = os.getenv("WAREHOUSE_HOST", "localhost")
    port = os.getenv("WAREHOUSE_PORT", "5433")
    dbname = os.getenv("WAREHOUSE_DB", "anp")
    user = os.getenv("WAREHOUSE_USER", "warehouse")
    password = os.getenv("WAREHOUSE_PASSWORD", "warehouse")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"
