# Научный клубок — SOTA-граф знаний для R&D в горном деле и металлургии

Платформа графа знаний, которая превращает разнородный корпус R&D-документов по
горному делу и металлургии (статьи, обзоры, внутренние отчёты, патенты,
конференц-презентации, протоколы экспериментов — на русском и английском) в
**единую, evidence-first, проверяемую карту знаний** и отвечает на сложные
инженерные вопросы, например:

> «Какие методы обессоливания воды подходят для обогатительной фабрики, если вода
> содержит сульфаты/хлориды/Ca/Mg/Na по 200–300 мг/л, а требуемый сухой остаток
> ≤1000 мг/дм³?»

Каждый ответ несёт **источники, уверенность, дату актуализации, географию
(отечественная/зарубежная практика), числовые диапазоны и пробелы/противоречия**.

## Архитектура

Монорепозиторий (`apps/*`, `packages/*`, `infra/*`) с конвейером
ingestion → extraction → граф знаний → retrieval → агент → API → UI.

| Слой | Целевой стек (docker) | **Запускаемый embedded по умолчанию** |
|---|---|---|
| Граф (Cypher) | Neo4j + APOC/GDS | **Kuzu** (встроенный Cypher) |
| Векторный поиск | Qdrant server | **qdrant-client** (локально/на диске) |
| Полнотекстовый поиск | OpenSearch | **BM25** (в процессе) |
| Эмбеддинги | — | **fastembed** multilingual-MiniLM (384d, RU/EN) |
| Парсинг документов | Docling Serve | pypdf / pdfplumber / python-docx / python-pptx |
| LLM | — | **OpenRouter, только OSS** (Qwen2.5 / DeepSeek-V3 / Mistral) |
| Агент | LangGraph | LangGraph |
| API / UI | FastAPI / React+Vite | FastAPI / React+Vite |

**Embedded-профиль** (по умолчанию, `RUNTIME_PROFILE=embedded`) запускает всю
систему без Docker-демона — см. `docs/adr/0005-embedded-runtime-profile.md`.
**Серверный профиль** использует docker-compose-стек в `infra/`.

## Возможности

- **Приём документов (ingestion)** — парсинг PDF/DOCX/PPTX/XLSX (RU/EN), чанкинг,
  извлечение сущностей/связей/измерений правилами + OSS-LLM с evidence-спанами,
  нормализация единиц (pint), разрешение сущностей, evidence-first upsert;
  возобновляемо, ~1.3 с/док.
- **Граф знаний** — 33+ доменных меток, декларативная схема рёбер,
  детерминированные ID, provenance/версионирование, сгенерированная
  LinkML-онтология + миграции Neo4j.
- **Retrieval** — структурные графовые шаблоны + вектор (fastembed→Qdrant) +
  ключевые слова (BM25) + гибридное слияние RRF + GraphRAG community summaries.
- **Агент (LangGraph)** — parse → retrieve → access-filter → синтез обоснованного,
  **цитируемого** литобзорного ответа с уверенностью, таблицами, пробелами,
  противоречиями.
- **Верификация** — анализ пробелов (9 типов) + детекция противоречий; каждый
  ответ evidence-first с источником/уверенностью/географией.
- **Домен** — RU↔EN таксономия (218 терминов), числовые ограничения
  (≤1000 мг/дм³ …), отечественная/зарубежная практика, сравнительные таблицы,
  дашборды покрытия.
- **Управление (governance)** — JWT-аутентификация + RBAC (6 ролей) + построчный
  доступ, аудит-лог, экспертное курирование (правка/слияние/история, защищённая
  переиндексация), уведомления, экспорт Markdown/JSON-LD, SHACL-схемы,
  FAIR-метаданные.
- **UI** — рабочее пространство React/Vite: чат + граф *клубок* (d3-force),
  покрытие, пробелы и ревью, глоссарий, инспектор доказательств.

## Проверено end-to-end

- Все **4 обязательных приёмочных запроса** проходят (`make demo`; отчёт в
  `docs/eval/domain_science_ball_report.md`) — с паритетом RU/EN, числовыми
  фильтрами, географией, противоречиями и доказательствами.
- **Реальный корпус**: 60 документов → 19.7k узлов / 57k связей; гибридный индекс
  по 3.1k чанков; gap-скан нашёл 88 пробелов + 292 противоречия; OSS-LLM
  DeepSeek-V3 отвечает на все четыре запроса на реальных данных
  (`docs/eval/demo_report.md`).
- **Adversarial-ревью** (мультиагентное), исправлено 15 багов корректности с
  регрессионными тестами (`docs/eval/adversarial_review_findings.md`).
- ~100 тестов проходят, ruff чист.

## Лицензирование (только OSS)

По правилам хакатона каждый компонент под разрешённой OSS-лицензией
(Apache-2.0 / MIT / GPL-семейство). Это включает **LLM** (только Apache-2.0 / MIT
модели — без Llama/Gemma). См. `docs/LICENSES.md` и
`docs/adr/0006-oss-llm-and-licensing.md`. Лицензия проекта: **Apache-2.0**.

## Быстрый старт (embedded, без Docker)

```bash
make bootstrap            # uv sync --all-packages (+ зависимости фронтенда)
cp .env.example .env      # впишите свой OPENROUTER_API_KEY
make check                # линт + проверка форматирования + тесты
make ingest N=20          # распарсить и извлечь 20 документов корпуса в граф
make seed                 # заполнить демо-граф
make api                  # API-шлюз на :8000  (GET /api/v1/admin/health)
make frontend             # React-UI на :3000
make demo                 # прогнать 4 приёмочных запроса end-to-end
```

## Быстрый старт (Docker, серверный профиль)

Поднимает **весь стек** — инфру (Neo4j, Qdrant, OpenSearch, Postgres, Redis,
MinIO, Authentik, Docling) **и** сервисы приложения (api-gateway, agent-service,
ingestion-service, frontend) — из `infra/docker-compose.yml`.

```bash
cp .env.example .env      # впишите свой OPENROUTER_API_KEY
make up                   # = docker compose -f infra/docker-compose.yml up -d
make init-db              # миграция графа + индексация чанков (заполнить граф)
# → фронтенд на :3000, API-шлюз на :8000  (GET /api/v1/admin/health)

make ps                   # статус контейнеров
make logs                 # логи стека
make down                 # остановить стек
```

> **Примечание:** голый `docker compose up` из корня репозитория не найдёт конфиг —
> compose-файл лежит в `infra/`, поэтому используйте `make up` (или
> `docker compose -f infra/docker-compose.yml up -d`). `make up` запускает
> сервисы; данные наполняет именно `make init-db` (иначе граф пустой). Усиленный
> production-оверлей: `make deploy-prod`.

## Структура репозитория (§6.1)

```
apps/        api-gateway agent-service ingestion-service graph-service
             search-service extraction-service curation-service frontend
packages/    kg_common kg_schema kg_extractors kg_retrievers kg_eval
infra/       docker-compose.yml neo4j/ qdrant/ opensearch/ dagster/ helm/
docs/        adr/ conventions/ domain/ eval/  + план задач и гайды
third_party/ вендоренные OSS-репозитории (только для изучения; в .gitignore)
```

Полная карта — в `docs/architecture.md`, план задач — в
`docs/FULL_SYSTEM_TASKS_science_ball.md` (прогресс: `python scripts/mark_tasks.py stats`).
