# Imagem do Airflow + as dependências do nosso projeto.
FROM apache/airflow:2.10.5

# Permite "from anp_etl import ..." dentro das DAGs (a pasta src/ é montada em /opt/airflow/src)
ENV PYTHONPATH="/opt/airflow/src" \
    PYTHONDONTWRITEBYTECODE=1

# Pastas de dados criadas com o dono certo (o usuário "airflow"), senão o volume fica sem permissão
RUN mkdir -p /opt/airflow/data/raw /opt/airflow/data/processed

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
