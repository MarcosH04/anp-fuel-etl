# Guia passo a passo (Windows, do zero)

Este guia assume que você **nunca usou Docker nem Airflow**. Ele explica o que cada ferramenta
faz, como instalar no Windows, como rodar o projeto, como conferir se funcionou e como publicar no
GitHub.

Tempo estimado: 1 a 2 horas na primeira vez (a maior parte é instalação e download de imagens).

---

## Parte 1 · Conceitos em 1 minuto

| Conceito | Em português claro |
|---|---|
| **ETL** | *Extract, Transform, Load*: pegar dados de uma fonte (**E**xtrair), arrumá-los (**T**ransformar) e guardá-los num destino (**L**oad/Carregar). |
| **Data warehouse** | Banco de dados feito para análise. Aqui é um PostgreSQL. |
| **Orquestração** | Um "gerente" que decide *quando* e *em que ordem* cada etapa roda, tenta de novo se falhar e mostra o histórico. É o papel do Airflow. |
| **DAG** | O "mapa de tarefas" do Airflow: quem roda primeiro, quem depende de quem. Sem ciclos (por isso *acíclico*). |
| **Idempotência** | Rodar a mesma carga 2 vezes dá o mesmo resultado, sem duplicar dados. Essencial: pipelines falham e são reexecutados. |
| **Upsert** | *Update + Insert*: se a linha já existe, atualiza; se não existe, insere. |
| **Parquet** | Formato de arquivo em colunas, compacto e rápido, padrão em engenharia de dados. |
| **Camadas raw / processed / gold** | *raw* = cópia fiel da fonte; *processed* = dado limpo; *gold* = visões prontas para análise (nossas views). |
| **Container (Docker)** | Uma "caixinha" com um programa e tudo que ele precisa. Funciona igual no seu PC, no do colega e no servidor. |

---

## Parte 2 · Ferramentas que você vai usar

| Ferramenta | Para que serve | Onde aparece no projeto |
|---|---|---|
| **WSL2 + Ubuntu** | Linux dentro do Windows. Docker e Airflow funcionam melhor assim. | Todos os comandos deste guia rodam no terminal Ubuntu |
| **Docker Desktop** | Roda os containers (Airflow, PostgreSQL). | `Dockerfile`, `docker-compose.yml` |
| **Git** | Controle de versão: histórico do seu código. | Pasta `.git` (criada por você) |
| **GitHub** | Site que hospeda seu repositório: sua vitrine para recrutadores. | Passo 11 |
| **VS Code** | Editor de código (com extensão WSL). | Para ler e editar os arquivos |
| **Python 3.12** | A linguagem do pipeline. | `src/anp_etl/` |
| **Pandas** | Biblioteca para manipular tabelas de dados. | `transform.py` |
| **PyArrow** | Permite ler/escrever Parquet. | `transform.py`, `load.py` |
| **requests** | Baixa arquivos da internet. | `extract.py` |
| **psycopg2** | Conversa com o PostgreSQL a partir do Python. | `load.py` |
| **PostgreSQL 16** | O banco de dados (data warehouse). | `sql/`, container `warehouse-db` |
| **Apache Airflow 2.10** | Orquestrador: agenda, executa e monitora o pipeline. | `dags/anp_fuel_prices.py` |
| **DBeaver** (opcional) | Programa visual para consultar o banco. | Parte 5 |
| **pytest** | Roda os testes automatizados. | `tests/` |
| **Ruff** | Verifica estilo e erros comuns no código (lint). | `pyproject.toml` |
| **GitHub Actions** | Roda testes automaticamente a cada push. | `.github/workflows/ci.yml` |

---

## Parte 3 · Instalando no Windows

Requisitos: Windows 10 (versão 2004+) ou 11, virtualização habilitada na BIOS e, de preferência,
**8 GB de RAM** ou mais (o Airflow é pesado).

### Passo 1 · WSL2 e Ubuntu

1. Abra o **PowerShell como administrador** (botão direito no menu Iniciar).
2. Execute:
   ```powershell
   wsl --install
   ```
3. Reinicie o computador quando pedido. Ao voltar, o Ubuntu abre sozinho e pede para você criar
   um **usuário e senha Linux** (a senha não aparece enquanto digita; é normal).

A partir daqui, **"terminal" significa o terminal do Ubuntu** (procure "Ubuntu" no menu Iniciar).

### Passo 2 · Docker Desktop

1. Baixe em <https://www.docker.com/products/docker-desktop/> e instale mantendo marcada a opção
   **"Use WSL 2 based engine"**.
2. Abra o Docker Desktop → **Settings → Resources → WSL Integration** → ative o **Ubuntu** →
   *Apply & restart*.
3. No terminal Ubuntu, teste:
   ```bash
   docker --version
   docker compose version
   ```

**Limite de memória (recomendado).** O WSL2 pode consumir toda a RAM. Crie o arquivo
`C:\Users\SEU_USUARIO\.wslconfig` com:
```ini
[wsl2]
memory=6GB
processors=4
```
Depois, no PowerShell: `wsl --shutdown` e abra o Docker Desktop de novo. (Se seu PC tem 8 GB,
use `memory=5GB`.)

### Passo 3 · Git, Python e utilitários (dentro do Ubuntu)

```bash
sudo apt update && sudo apt install -y git unzip python3-venv python3-pip
git config --global user.name "Seu Nome"
git config --global user.email "seu-email@exemplo.com"
```
Use o mesmo e-mail da sua conta do GitHub.

### Passo 4 · VS Code

1. Instale o VS Code em <https://code.visualstudio.com/>.
2. Instale a extensão **WSL** (da Microsoft). Depois, no terminal Ubuntu, `code .` abre o VS Code
   conectado ao Linux.

### Passo 5 · DBeaver (opcional)

Instale o **DBeaver Community** em <https://dbeaver.io/download/>. Usaremos para ver as tabelas.

---

## Parte 4 · Rodando o projeto

### Passo 6 · Colocar o projeto no Linux

Baixe o arquivo `anp-fuel-etl.zip` (ele vai para a pasta *Downloads* do Windows) e rode no Ubuntu:

```bash
mkdir -p ~/projetos && cd ~/projetos
cp /mnt/c/Users/SEU_USUARIO/Downloads/anp-fuel-etl.zip .
unzip anp-fuel-etl.zip
cd anp-fuel-etl
code .
```

> ⚠️ **Mantenha o projeto dentro do Linux (`~/projetos`)**, não em `/mnt/c/...`. Em `/mnt/c` o
> Docker fica muito lento e surgem erros de permissão.

### Passo 7 · Conhecer o código

Abra os arquivos nesta ordem. Todos têm comentários explicando o "porquê".

| Arquivo | Leia para entender |
|---|---|
| `src/anp_etl/config.py` | Onde ficam URLs, pastas e regras de qualidade |
| `src/anp_etl/extract.py` | Como descobrimos a URL de cada semestre e baixamos/descompactamos |
| `src/anp_etl/transform.py` | A limpeza: nomes de colunas, números brasileiros (`6,29`), datas, CNPJ, rejeições, duplicatas |
| `src/anp_etl/load.py` | `COPY` + upsert + auditoria (idempotência) |
| `sql/01_schema.sql`, `sql/02_views.sql` | Tabelas e views |
| `dags/anp_fuel_prices.py` | As duas DAGs do Airflow |
| `docker-compose.yml` | Os 5 containers e como se conectam |
| `tests/` | Como testar a transformação sem acessar a internet |

### Passo 8 · Rodar os testes (sem Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

pytest -q          # deve mostrar: 24 passed
ruff check .       # deve mostrar: All checks passed!
```

Testes passando antes de subir o ambiente = você sabe que o código está sadio.

### Passo 9 · Subir o Airflow e o PostgreSQL

```bash
cp .env.example .env          # configurações locais (não vão para o GitHub)
docker compose build          # constrói a imagem (demora na 1ª vez)
docker compose up airflow-init   # cria as tabelas internas e o usuário; termina sozinho
docker compose up -d          # sobe tudo em segundo plano
docker compose ps             # todos devem estar "running" ou "healthy"
```

1. Abra **http://localhost:8080** → login `airflow` / `airflow`.
2. Você verá duas DAGs, **pausadas** (de propósito). Na `anp_incremental_semanal`, ligue o botão
   de pausa e clique em **▶ → Trigger DAG**.
3. Clique no nome da DAG → aba **Graph**. Cada quadrado é uma tarefa; verde = sucesso. Clique em
   uma tarefa → **Logs** para ver o que ela fez (linhas lidas, rejeitadas, etc.).

**Carga histórica:** na `anp_backfill_historico`, use **▶ → Trigger DAG w/ config** e informe,
por exemplo:
```json
{"start_year": 2024, "end_year": 2026}
```
Isso cria uma tarefa por semestre encerrado (2024-1, 2024-2, 2025-1, 2025-2, 2026-1), duas rodando por vez.
Cada arquivo tem dezenas de MB, então leva alguns minutos.

#### Cobrindo o "buraco" de jul–set/2026

O último semestre publicado é o de jan–jun/2026, e o arquivo de "últimas 4 semanas" cobre só o
final. Para o intervalo do meio, a ANP publica **arquivos mensais** (com nomes irregulares). Copie
o link de cada mês na [página da ANP](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/serie-historica-de-precos-de-combustiveis)
e carregue pela linha de comando (com o `.venv` ativo do Passo 8):

```bash
export PYTHONPATH=src
python -m anp_etl.cli url \
  "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsan/2026/09-dados-abertos-precos-2026-09-gasolina-etanol.csv" \
  --label mensal-2026-09-gasolina-etanol
```
Repita para `...-diesel-gnv.csv` e para cada mês. Como a carga é idempotente, não há problema se um
período se sobrepuser a outro.

### Passo 10 · Conferir os dados no banco

**Pelo terminal:**
```bash
docker compose exec warehouse-db psql -U warehouse -d anp
```

**Pelo DBeaver:** *Nova conexão → PostgreSQL* com host `localhost`, porta `5433`, banco `anp`,
usuário `warehouse`, senha `warehouse`.

Consultas para começar:

```sql
-- 1) Confira os nomes reais dos produtos (as views usam esses nomes)
SELECT produto, count(*) FROM anp.precos_combustiveis GROUP BY 1 ORDER BY 2 DESC;

-- 2) Auditoria: o que cada execução carregou
SELECT * FROM anp.etl_execucoes ORDER BY id DESC;

-- 3) Gasolina em Minas Gerais, semana a semana
SELECT * FROM anp.vw_preco_medio_semanal_uf
WHERE uf = 'MG' AND produto ILIKE 'GASOLINA%'
ORDER BY semana DESC LIMIT 10;

-- 4) Etanol ou gasolina? (razão <= 0,70 => etanol compensa)
SELECT * FROM anp.vw_paridade_etanol_gasolina_uf ORDER BY mes DESC, uf;

-- 5) Municípios mineiros com a gasolina mais barata nos últimos 30 dias
SELECT municipio, round(avg(valor_venda), 2) AS preco_medio, count(*) AS coletas
FROM anp.precos_combustiveis
WHERE uf = 'MG' AND produto ILIKE 'GASOLINA%' AND data_coleta >= current_date - 30
GROUP BY municipio HAVING count(*) >= 10
ORDER BY preco_medio LIMIT 10;
```

**Prove a idempotência** (ótimo para mostrar em entrevista): dispare a mesma DAG de novo e veja
que `linhas_afetadas` na tabela de auditoria cai para perto de zero e a contagem de linhas não
cresce.

**Para desligar:** `docker compose down` (mantém os dados) ou `docker compose down -v`
(apaga tudo, inclusive o banco; use para recomeçar do zero).

---

## Parte 5 · Publicar no GitHub

### Passo 11 · Criar o repositório e enviar

1. Crie uma conta em <https://github.com> (se ainda não tiver).
2. **New repository** → nome `anp-fuel-etl`, **Public**, **sem** README/.gitignore/licença
   (o projeto já tem os seus).
3. Antes de enviar, troque os marcadores:
   - `LICENSE`: troque `SEU NOME` pelo seu nome.
   - `README.md` e este guia: troque `SEU_USUARIO` pelo seu usuário do GitHub. No VS Code, use
     **Ctrl+Shift+H** (substituir em todos os arquivos).
4. No terminal, dentro da pasta do projeto:
   ```bash
   git init
   git add .
   git status        # CONFIRA: .env e a pasta data/ NÃO podem aparecer na lista
   git commit -m "feat: pipeline ETL de precos de combustiveis da ANP"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/anp-fuel-etl.git
   git push -u origin main
   ```
5. Na hora do `push`, o GitHub não aceita senha comum. Use um **Personal Access Token**
   (GitHub → Settings → Developer settings → Tokens, com permissão `repo`) no lugar da senha, ou
   instale o GitHub CLI e rode `gh auth login`.
6. Abra a aba **Actions** do repositório: o CI deve rodar e ficar verde ✅. O selo no topo do
   README passa a funcionar.

### Deixe o repositório com cara de profissional

- Tire **prints** da tela do Airflow (aba *Graph* com tudo verde) e de uma consulta no DBeaver;
  salve em `docs/images/` e inclua no README com `![Graph](docs/images/graph.png)`.
- Preencha *About* do repositório (descrição + tópicos: `data-engineering`, `airflow`, `etl`,
  `postgresql`, `python`, `docker`, `anp`).
- Faça commits pequenos e com mensagens claras quando evoluir o projeto.

### Texto sugerido para o LinkedIn

> Construí um pipeline de dados de ponta a ponta com dados abertos da ANP: extração de CSVs
> semestrais e semanais, limpeza com Pandas (encoding, números e datas no formato brasileiro,
> deduplicação, portão de qualidade), carga idempotente em PostgreSQL com upsert e tabela de
> auditoria, orquestração com Airflow (Dynamic Task Mapping) e ambiente 100% em Docker, com
> testes e CI no GitHub Actions. Código e arquitetura no link 👇
> `#DataEngineering #Airflow #Python #PostgreSQL #Docker`

---

## Parte 6 · Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `docker: command not found` no Ubuntu | Integração WSL do Docker desligada | Docker Desktop → Settings → Resources → WSL Integration → ativar Ubuntu |
| Airflow lento ou containers reiniciando | Pouca memória | Ajuste o `.wslconfig` (Passo 2) e feche programas pesados |
| `port is already allocated` (8080 ou 5433) | Outro programa usa a porta | Pare o outro programa ou mude a porta em `docker-compose.yml` / `.env` |
| `airflow-init` termina com erro | Banco do Airflow ainda subindo | Rode `docker compose up airflow-init` de novo |
| DAG não aparece na tela | Erro de sintaxe/import na DAG | `docker compose exec airflow-scheduler airflow dags list-import-errors` |
| Tarefa `extract` falha com **404** | Semestre ainda não publicado | Use a carga semanal ou os arquivos mensais (Passo 9) |
| Tarefa `extract` falha com **timeout/conexão** | Site da ANP lento ou fora do ar | O Airflow tenta 2 vezes; se persistir, tente mais tarde |
| `transform` falha: **"Colunas obrigatórias ausentes"** | A ANP mudou o layout | A mensagem lista as colunas encontradas; ajuste `COLUMN_MAP` em `transform.py` |
| `transform` falha: **"% das linhas foram rejeitadas"** | Arquivo fora do padrão | Abra o CSV em `data/raw`, veja o formato e ajuste `transform.py` |
| Permissão negada em arquivos | Projeto em `/mnt/c/...` | Mova o projeto para `~/projetos` (Passo 6) |
| Quer recomeçar do zero | — | `docker compose down -v` e suba de novo |

---

## Parte 7 · Antes de divulgar: checklist da primeira execução

O código foi validado com dados de exemplo no layout oficial da ANP, com o Airflow 2.10.5 e com
PostgreSQL 16, mas **nunca baixou os arquivos reais** da ANP (o ambiente em que foi desenvolvido
não alcança o gov.br). Por isso, na sua primeira execução, confira:

- [ ] A DAG `anp_incremental_semanal` terminou verde (as duas tarefas `extract` baixaram).
- [ ] `SELECT produto, count(*) FROM anp.precos_combustiveis GROUP BY 1;` mostra os produtos
      esperados (gasolina, etanol, diesel, GNV). Se os nomes forem diferentes de `GASOLINA*` e
      `ETANOL*`, ajuste o `ILIKE` em `sql/02_views.sql`.
- [ ] `SELECT * FROM anp.etl_execucoes;` mostra `linhas_rejeitadas` baixo (poucos %).
- [ ] Um semestre antigo (ex.: 2024) carrega pela DAG de backfill.

Se algo falhar, **isso é normal e faz parte do trabalho de engenharia de dados**: leia o log da
tarefa, ajuste e registre a correção em um commit. Documentar um problema real que você resolveu
vale mais em uma entrevista do que um projeto que "nunca quebra".

---

## Parte 8 · Para evoluir o projeto

Em ordem sugerida de dificuldade:

1. **Cruzar com o INMET (clima)** e ver se temperatura/chuva se relacionam com o preço do etanol.
2. **Cruzar com o IPCA do IBGE** (API SIDRA) para analisar preço real vs. nominal.
3. **dbt**: mover as views para modelos dbt (`staging` → `marts`), com testes e documentação.
4. **Great Expectations / Soda**: validações declarativas, com alerta no Slack/e-mail.
5. **Metabase ou Superset**: dashboard sobre as views, com print no README.
6. **Airflow Connections**: tirar senhas de variáveis de ambiente.
7. **Nuvem**: S3 + RDS (ou BigQuery), infraestrutura com **Terraform**, CI/CD com deploy.
