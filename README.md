# Научный клубок — Knowledge Graph for Mining & Metallurgy R&D

Превращает разнородный корпус горно-металлургических R&D-материалов (статьи, обзоры,
внутренние отчёты, патенты, материалы конференций, протоколы экспериментов — RU & EN) в
**единую проверяемую карту знаний** и отвечает на сложные инженерные вопросы вида
*материал + процесс + числовые условия + география + период*, например:

> «Какие методы обессоливания воды подходят для обогатительной фабрики, если вода содержит
> сульфаты/хлориды/Ca/Mg/Na по 200–300 мг/л, а требуемый сухой остаток ≤ 1000 мг/дм³?»

Каждый ответ несёт **источник + страницу + фрагмент + дату актуализации + гео (отеч./заруб.) +
числовые диапазоны + пробелы/противоречия**, и любое число можно открыть в первоисточнике.

> Полный архитектурно-бенчмарк-разбор (что реально подключено, измеренные числа, killer features,
> сценарий демо): **[`docs/hackathon_architecture_benchmarks_killer_features.md`](docs/hackathon_architecture_benchmarks_killer_features.md)**.

---

## Два профиля запуска

| | **embedded** (быстрый просмотр) | **server** (полный масштаб — как в демо) |
|---|---|---|
| `RUNTIME_PROFILE` | `embedded` | `server` |
| Граф | Kuzu (встроенный Cypher-файл) | **Neo4j 5.26** (bolt) |
| Векторы | qdrant-client (on-disk) | **Qdrant server** |
| Keyword | BM25 (in-process) | **OpenSearch 2.17** |
| Инфра | не нужен Docker | `docker compose` стек (`infra/`) |
| Данные | `make seed` (~89 узлов) / `make ingest` | реальный корпус → Neo4j (демо: **~152k узлов / 512k рёбер**) |

Подробнее: `docs/adr/0005-embedded-runtime-profile.md`, `docs/architecture.md`.

---

## Требования

- **Docker** + compose v2 (для server-профиля).
- **[uv](https://docs.astral.sh/uv/)** (Python 3.13), **Node 20 + pnpm** (фронтенд).
- Ключ **OpenRouter** (OSS-only модели, ADR-0006).

```bash
make bootstrap          # uv sync --all-packages (+ frontend deps)
cp .env.example .env    # впишите OPENROUTER_API_KEY; выберите RUNTIME_PROFILE
```

---

## Вариант A — embedded (за 1 команду, без Docker)

```bash
make demo-up            # seed граф + поднять API (:8000)   → infra/demo/up.sh
# или пошагово:
make ingest N=50        # распарсить+извлечь 50 документов корпуса в KG
make index              # построить векторный + keyword индексы из графа
make api                # API gateway на :8000  (GET /api/v1/admin/health)
make frontend           # React UI на :3000
make demo               # прогнать 4 приёмочных запроса end-to-end
```

## Вариант B — server (полный стек, реальный масштаб)

### 1) Поднять инфраструктуру

```bash
make up                 # docker compose -f infra/docker-compose.yml up -d
make ps                 # статус контейнеров (neo4j/qdrant/opensearch/postgres/valkey/minio/authentik)
make logs               # хвост логов
```

Сервисы стека: Neo4j 5.26, Qdrant, OpenSearch 2.17, Postgres 16, Valkey (Redis-совместимый),
MinIO, authentik (SSO), docling-serve, api-gateway, agent-service, ingestion-service, frontend.
Все с healthcheck'ами и именованными volume'ами (данные переживают перезапуск).

### 2) Запустить API на server-профиле

```bash
RUNTIME_PROFILE=server \
  NEO4J_URI=bolt://localhost:7687 QDRANT_URL=http://localhost:6333 \
  OPENSEARCH_URL=http://localhost:9200 \
  uv run uvicorn api_gateway.main:app --host 0.0.0.0 --port 8000
```

> В контейнере вместо `localhost` используйте `host.docker.internal` (см. «Демо-контейнер» ниже).

---

## Инициализация данными (быстро, в несколько потоков)

Ядро качества — **корпус в графе**. Ingest реально распараллелен: CLI использует
`ProcessPoolExecutor(max_workers=--workers)` (`apps/ingestion-service/.../cli.py`), поэтому
инициализация масштабируется по ядрам.

### Параллельный ingest (рекомендуется)

```bash
# embedded (в Kuzu):
uv run python -m ingestion_service.cli ingest \
  --data-dir <путь_к_корпусу> \
  --workers "$(nproc)" \      # ← многопроцессный ingest по числу ядер
  --llm --llm-chunks 3 \      # small-OSS-модель на ≤3 чанка/док (без --llm = только правила, быстрее)
  --max-mb 40                 # пропускать файлы крупнее N МБ
# затем индексы:
uv run python -m ingestion_service.cli index      # вектор (Qdrant) + keyword (OpenSearch/BM25)
```

Флаги `ingest`: `--data-dir --limit --workers --llm --llm-chunks --max-mb --shuffle --seed
--keep-seed`. Ingest **идемпотентен и возобновляем** (dedup по хешу документа) — можно
докидывать документы волнами.

### Server-профиль: наполнение Neo4j + Qdrant + OpenSearch

```bash
# (а) если есть встроенный Kuzu-граф — перенести его в Neo4j:
make init-db                                   # migrate_kuzu_to_neo4j.py + index_chunks_server.py

# (б) или наполнить с нуля из корпуса (так и построен демо-граф на 152k узлов):
uv run python scripts/ingest_corpus_server.py  # batch rule+LLM ingest прямо в Neo4j
uv run python scripts/index_chunks_server.py   # :Chunk → Qdrant (векторы) + OpenSearch (keyword)
uv run python scripts/propagate_geography.py   # Document→Evidence→Measurement: country/practice_type/дата
                                               # (включает гео/временные фильтры на фактах)
```

Восстановление/починка индексов (частые операции):

```bash
uv run python scripts/reindex_opensearch.py    # пересобрать ТОЛЬКО OpenSearch keyword-индекс
                                               # (нужно после рестарта, если kg_chunks-индекс потерян → 404)
uv run python scripts/qdrant_reembed.py        # переэмбеддить все :Chunk текущей моделью
                                               # (обязательно при смене EMBEDDING_MODEL — см. ниже)
```

> ⚠ **Смена embedding-модели ≠ правка строки.** Векторный поиск сравнивает запрос с уже
> проиндексированными векторами; другая модель (даже той же размерности 384) даёт несопоставимые
> векторы. После смены `EMBEDDING_MODEL` **обязателен** `qdrant_reembed.py`.

### Проверка

```bash
make demo                                       # 4 приёмочных запроса → docs/eval/domain_science_ball_report.md
curl -s localhost:8000/api/v1/admin/health
curl -s localhost:8000/api/v1/admin/stats -H 'X-Role: admin'   # counts.nodes / rels по типам
```

---

## Модели (OSS-only, ADR-0006, набор Q2-2026)

Единый источник — `packages/kg_common/.../config.py` (переопределяется `LLM_MODEL_*` env).

| Роль | Модель | Лицензия |
|---|---|---|
| Извлечение / fast / preprocess | `qwen/qwen3.6-35b-a3b` | Apache-2.0 |
| Синтез ответа (`/query`) | `deepseek/deepseek-v4-flash` | MIT |
| Синтез — quality / deep-research supervisor | `z-ai/glm-5.2` | MIT |
| Embeddings (Qdrant, 384d, RU+EN) | `ibm-granite/granite-embedding-97m-multilingual-r2` | Apache-2.0 |
| Reranker | `cross-encoder/ettin-reranker-1b-v1` | Apache-2.0 |
| Мультимодальный (опционально) | `minimax/minimax-m3` | ⚠ MiniMax-Community — **только опционально** |

**Исключены** (лицензия не подходит §7.5): Llama (Community), Gemma, NVIDIA Nemotron (OpenMDW).
Подробности: `docs/LICENSES.md`, `docs/adr/0006-oss-llm-and-licensing.md`.

---

## Порты

| API | UI | Neo4j | Qdrant | OpenSearch | Postgres | Redis | MinIO | authentik |
|---|---|---|---|---|---|---|---|---|
| 8000 | 3000 | 7474/7687 | 6333 | 9200 | 5432 | 6379 | 9000/9001 | 9100 |

---

## Демо-контейнер (как поднят живой стенд)

API-gateway крутится контейнером на server-профиле, обращаясь к внешним Neo4j/Qdrant/OpenSearch
через `host.docker.internal`. Секреты — только через `--env-file`, не в командной строке:

```bash
docker run -d --name sciball-api -p 8001:8000 \
  --add-host host.docker.internal:host-gateway \
  --env-file secrets.env \      # OPENROUTER_API_KEY, JWT_SECRET
  --env-file overlay.env \      # RUNTIME_PROFILE=server, NEO4J_URI/QDRANT_URL/OPENSEARCH_URL=host.docker.internal, LLM_MODEL_*
  sciball-api-full
```

---

## Разработка

```bash
make dev        # API + фронтенд параллельно (embedded)
make check      # ruff lint + format-check + pytest (воспроизводит CI)
make test       # pytest;  make type — mypy;  make fe-build — прод-сборка фронта
make gap-scan   # пробелы + противоречия по графу
```

## Структура репозитория

```
apps/        api-gateway agent-service ingestion-service graph-service
             search-service extraction-service curation-service frontend
packages/    kg_common kg_schema kg_extractors kg_retrievers kg_eval
infra/       docker-compose.yml neo4j/ qdrant/ opensearch/ dagster/ helm/ demo/
scripts/     ingest_corpus_server · index_chunks_server · reindex_opensearch ·
             qdrant_reembed · migrate_kuzu_to_neo4j · propagate_geography
docs/        architecture.md · adr/ · domain/ · eval/ · hackathon_architecture_benchmarks_killer_features.md
```

## Лицензия

Проект — **Apache-2.0** (`LICENSE`, `NOTICE`). Все зависимости и модели — под лицензиями,
разрешёнными правилами §7.5 (Apache-2.0 / MIT / GPL-семейство). См. `docs/LICENSES.md`.
