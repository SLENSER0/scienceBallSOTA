# Полномасштабная научная Knowledge-Graph система — полный план задач

## Как пользоваться

- Разделы 1–20 — по подсистемам; 21 — репозитории для клонирования/вендоринга; 22 — Definition of Done; 23 — сквозные задачи; 24 — доменная адаптация «Научный клубок» под горно-металлургические R&D; 25 — confidence-of-absence для extractor-recall-aware анализа пробелов.
- Порядок выполнения ориентируйся на roadmap §16 дизайн-документа (Phase 0→9), но зависимости между разделами указаны внутри задач.
- Для каждой подсистемы указаны затрагиваемые сервисы/пакеты (структура `apps/*`, `packages/*`, `infra/*` из §6.1) и OSS-репозитории.

## Оглавление

1. [1. Монорепо, конвенции и инструментарий](#1-монорепо-конвенции-и-инструментарий)
2. [2. Инфраструктура и DevOps](#2-инфраструктура-и-devops)
3. [3. Доменная онтология и Neo4j knowledge graph](#3-доменная-онтология-и-neo4j-knowledge-graph)
4. [4. Векторный и keyword-поиск: Qdrant + OpenSearch](#4-векторный-и-keyword-поиск-qdrant--opensearch)
5. [5. Document ingestion: Docling Serve](#5-document-ingestion-docling-serve)
6. [6. KG extraction (правила + ML + LLM)](#6-kg-extraction-правила--ml--llm)
7. [7. Нормализация единиц и величин](#7-нормализация-единиц-и-величин)
8. [8. Entity resolution (Splink)](#8-entity-resolution-splink)
9. [9. Оркестрация пайплайнов (Dagster)](#9-оркестрация-пайплайнов-dagster)
10. [10. Метаданные, lineage и governance (DataHub/OpenMetadata)](#10-метаданные-lineage-и-governance-datahubopenmetadata)
11. [11. GraphRAG (community summaries)](#11-graphrag-community-summaries)
12. [12. Retrieval strategy и fusion](#12-retrieval-strategy-и-fusion)
13. [13. LangGraph Agent Service](#13-langgraph-agent-service)
14. [14. FastAPI API Gateway](#14-fastapi-api-gateway)
15. [15. Gap analysis и contradiction detection](#15-gap-analysis-и-contradiction-detection)
16. [16. Curation workflow и decision history](#16-curation-workflow-и-decision-history)
17. [17. Frontend — все экраны и graph-визуализация](#17-frontend--все-экраны-и-graph-визуализация)
18. [18. Observability и evaluation](#18-observability-и-evaluation)
19. [19. Security, RBAC, аутентификация и hardening](#19-security-rbac-аутентификация-и-hardening)
20. [20. Интеграции лабораторных систем и materials data](#20-интеграции-лабораторных-систем-и-materials-data)
21. [21. Репозитории для клонирования и вендоринга](#21-репозитории-для-клонирования-и-вендоринга)
22. [22. Definition of Done — критерии полной готовности](#22-definition-of-done--критерии-полной-готовности)
23. [23. Сквозные и недостающие задачи](#23-сквозные-и-недостающие-задачи)
24. [24. «Научный клубок» — доменная адаптация под горно-металлургические R&D](#24-научный-клубок--доменная-адаптация-под-горно-металлургические-rd)
25. [25. Confidence-of-absence: extractor-recall-aware анализ пробелов](#25-confidence-of-absence-extractor-recall-aware-анализ-пробелов)

---


## 1. Монорепо, конвенции и инструментарий

Раздел покрывает создание greenfield-монорепозитория по структуре §6.1 (`apps/*`, `packages/*`, `infra/*`), настройку всего Python- и Frontend-инструментария (uv/poetry, ruff, mypy, pytest, eslint, prettier, pre-commit), управление конфигурацией и секретами (pydantic-settings, `.env.example`, секрет-менеджмент), базовый CI на GitHub Actions (lint/type/test) и contribution-конвенции. Соответствует §16 Phase 0 в части «create repo structure» и «configure ruff/mypy/pytest/eslint/prettier». Docker Compose, Neo4j-constraints и seed-скрипты из Phase 0 относятся к разделам инфраструктуры/схемы и здесь только резервируются каталогами.

Зависимости: этот раздел базовый — от него зависят все остальные (все `apps/*` и `packages/*` наследуют tooling и config, определённые здесь). Внешних зависимостей от других разделов нет.

---

### 1.1 Инициализация репозитория и корневая структура каталогов (§6.1)

- [x] Инициализировать git-репозиторий в корне `/Users/basil/science_ball_v2` (`git init`, ветка по умолчанию `main`); зафиксировать первый коммит с корневым `README.md`.
- [x] Создать корневой `README.md` с описанием проекта «SOTA Knowledge Graph», кратким деревом каталогов из §6.1 и quick-start (`make bootstrap`, `make up`, `make dev`).
- [x] Создать корневой `.gitignore` (Python: `__pycache__/`, `.venv/`, `*.pyc`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`; Node: `node_modules/`, `dist/`, `.turbo/`; env: `.env`, `.env.*` кроме `.env.example`; данные: `data/`, `*.log`, `.DS_Store`; артефакты MinIO/Neo4j монтирования).
- [x] Создать корневой `.gitattributes` (нормализация `* text=auto eol=lf`, бинарные маски для `*.pdf`, `*.png`).
- [x] Создать каталоги `apps/` со всеми сервисами из §6.1: `apps/api-gateway/`, `apps/agent-service/`, `apps/ingestion-service/`, `apps/graph-service/`, `apps/search-service/`, `apps/extraction-service/`, `apps/curation-service/`, `apps/frontend/`.
- [x] Создать каталоги `packages/` из §6.1: `packages/kg_schema/`, `packages/kg_extractors/`, `packages/kg_retrievers/`, `packages/kg_eval/`, `packages/kg_common/`.
- [x] Создать каталоги `infra/` из §6.1: `infra/docker-compose.yml` (пустая заготовка-плейсхолдер), `infra/helm/`, `infra/dagster/`, `infra/neo4j/`, `infra/opensearch/`, `infra/qdrant/` (с `.gitkeep` в пустых).
- [x] Создать вспомогательные корневые каталоги: `docs/` (для ADR и конвенций), `scripts/` (утилиты/seed), `third_party/` (vendored OSS), `.github/` (CI и шаблоны).
- [x] Добавить в каждый сервис/пакет минимальный `README.md` с назначением из §6.1 (одна-две строки на компонент) и указанием порта (для `apps/*`: api-gateway 8000, agent-service 8010, ingestion-service 8020 по §13.1).

**Критерий приёмки:** команда `find apps packages infra -maxdepth 1 -type d` выводит ровно набор каталогов из §6.1; `git status` чистый после первого коммита; каждый из 8 `apps/*`, 5 `packages/*` и 6 `infra/*` каталогов существует и содержит `README.md`/`.gitkeep`.

---

### 1.2 Python-workspace и менеджер зависимостей (uv/poetry)

- [x] Выбрать `uv` как основной менеджер (быстрее, нативный workspace); зафиксировать решение в `docs/adr/0001-python-package-manager.md` (ADR с альтернативой poetry и обоснованием).
- [x] Создать корневой `pyproject.toml` с секцией `[tool.uv.workspace]` и `members = ["apps/*", "packages/*"]`, объявить общий `requires-python = ">=3.12"`.
- [x] Создать в каждом Python-пакете (`packages/kg_common`, `kg_schema`, `kg_extractors`, `kg_retrievers`, `kg_eval`) свой `pyproject.toml` с `[project]` (name `kg-common` и т.д.), `version = "0.1.0"`, build-backend `hatchling`, и src-layout (`packages/<pkg>/src/<pkg>/__init__.py`).
- [x] Создать в каждом Python-сервисе (`apps/api-gateway`, `apps/agent-service`, `apps/ingestion-service`, `apps/graph-service`, `apps/search-service`, `apps/extraction-service`, `apps/curation-service`) `pyproject.toml` с зависимостью на локальные пакеты через `tool.uv.sources` (`kg-common = { workspace = true }` и т.п.).
- [x] Зафиксировать общий набор runtime-зависимостей из §13.2 (`fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `neo4j`, `qdrant-client`, `opensearch-py`, `langgraph`, `langchain-core`, `llama-index`, `llama-index-graph-stores-neo4j`, `llama-index-vector-stores-qdrant`, `haystack-ai`, `pandas`, `polars`, `duckdb`, `splink`, `gliner`, `sentence-transformers`, `fastembed`, `pint`, `pymatgen`, `networkx`, `orjson`, `structlog`, `opentelemetry-sdk`, `mlflow`, `ragas`, `deepeval`), распределив их по соответствующим `apps/*`/`packages/*` (напр. `neo4j` в graph-service/kg_retrievers, `qdrant-client`/`opensearch-py` в search-service).
- [x] Объявить dev-группу зависимостей (`[dependency-groups] dev`) с `ruff`, `mypy`, `pytest`, `pytest-cov`, `pytest-asyncio`, `types-*`-stubs, `pre-commit` на корневом уровне.
- [x] Сгенерировать `uv.lock` командой `uv lock` и закоммитить его; проверить воспроизводимость через `uv sync --frozen`.
- [x] Создать target `make bootstrap`, выполняющий `uv sync --all-packages` (установка всех members workspace в единый `.venv`).

**Критерий приёмки:** `uv sync --frozen` успешно ставит окружение с нуля; `uv run python -c "import kg_common, kg_schema, kg_extractors, kg_retrievers, kg_eval"` завершается без ошибок; `uv.lock` присутствует в git.

---

### 1.3 Пакеты-заготовки `packages/*`

- [x] `packages/kg_common`: создать модули-заготовки `config.py` (Settings, см. §1.6), `logging.py` (structlog setup, см. §1.12), `dto.py` (базовые Pydantic DTO), `telemetry.py` (OpenTelemetry init), `__init__.py` с реэкспортом; добавить `py.typed` маркер.
- [x] В `packages/kg_common/.../dto.py` объявить Pydantic-DTO с полями строго по контрактам дизайна: `GraphNode` (`id`, `label`, `type` ∈ {Material, Experiment, ProcessingRegime, Property, Equipment, Paper, Claim, Lab, Person, Gap}, `confidence?`, `evidenceCount?`, `verified?`, `missingFields?`, `properties?`), `GraphEdge` (`id`, `source`, `target`, `label`, `type`, `confidence?`, `evidenceCount?`, `inferred?`, `contradicted?`, `evidenceIds?`), `GraphResponse` (`nodes`, `edges`, `layoutHints?`, `queryContext?`) — по §5.3; `EvidenceRef` (`evidence_id`, `source_id`, `doc_id?`, `page?`, `span_start?`, `span_end?`, `confidence`) и `EntityMention` (`text`, `canonical_id?`, `entity_type?`, `confidence`) — по §7.3; тип-объединение `ChatStreamEvent` (`token|tool_start|tool_end|evidence|graph|table|gap|error`) — по §5.3. Обеспечить парность имён полей с TS-типами фронтенда (camelCase-алиасы через `Field(alias=...)` + `populate_by_name`).
- [x] `packages/kg_schema`: заготовка под Pydantic + LinkML определения (§8) — модуль `labels.py`, `relationships.py`, `evidence.py` (пока с `# TODO §8` и заглушечными классами), `py.typed`.
- [x] `packages/kg_extractors`: заготовка под LlamaIndex/GLiNER/materials-экстракторы (§9.2 Step 4) — пакетный `__init__.py`, подкаталоги `llm/`, `gliner/`, `materials/` с `__init__.py`, `py.typed`.
- [x] `packages/kg_retrievers`: заготовка под graph/vector/hybrid retrievers (§10) — модули-заглушки `graph.py`, `vector.py`, `hybrid.py`, `py.typed`.
- [x] `packages/kg_eval`: заготовка под evaluation harness (§15) — модули `golden.py`, `metrics.py`, `runner.py` (заглушки), `py.typed`.
- [x] Для каждого пакета создать `tests/` с одним smoke-тестом `test_import.py`, проверяющим импорт публичного API пакета.
- [x] Настроить экспорт версии пакета (`__version__`) и проверить, что `uv run python -m build`/`uv build` собирает wheel для каждого пакета без ошибок.

**Критерий приёмки:** `uv run pytest packages/` проходит (smoke-импорты зелёные); каждый `packages/*` имеет `src/<pkg>/`, `py.typed`, `tests/` и собирается в wheel через `uv build`.

---

### 1.4 Сервисы-заготовки `apps/*` (backend)

- [x] Для каждого backend-сервиса (`api-gateway`, `agent-service`, `ingestion-service`, `graph-service`, `search-service`, `extraction-service`, `curation-service`) создать src-layout `apps/<svc>/src/<svc_pkg>/` с `__init__.py`, `main.py`, `py.typed`.
- [x] В `apps/api-gateway/src/.../main.py` создать FastAPI-приложение с health-endpoint `GET /api/v1/admin/health` (возвращает `{"status":"ok"}`) и `GET /api/v1/admin/metrics`-заглушкой (по §6.2), подключить `uvicorn` запуск на порту 8000.
- [x] В `apps/agent-service`, `apps/ingestion-service` создать минимальные FastAPI-приложения с `GET /health` на портах 8010 и 8020 соответственно (§13.1).
- [x] Для `graph-service`, `search-service`, `extraction-service`, `curation-service` создать заготовки-модули с `def create_app()`/сервисным классом и smoke-тестом (эти сервисы могут быть библиотечными/worker без публичного порта на этом этапе).
- [x] Создать в каждом сервисе `Dockerfile` (multi-stage: базовый `python:3.12-slim`, `uv sync --frozen`, запуск через `uvicorn`), совместимый с `build: ./apps/<svc>` из §13.1 (реальный compose — раздел инфраструктуры, здесь только Dockerfile-заготовки).
- [x] Создать в каждом сервисе `tests/test_health.py`, использующий `fastapi.testclient`/`httpx` для проверки health-роутов (там где есть FastAPI-app).
- [x] Прописать в `pyproject.toml` каждого сервиса console-script/entrypoint (`[project.scripts]`) для локального запуска, напр. `api-gateway = "api_gateway.main:run"`.

**Критерий приёмки:** `uv run pytest apps/api-gateway apps/agent-service apps/ingestion-service` зелёный; локальный запуск `uv run uvicorn api_gateway.main:app` отвечает 200 на `GET /api/v1/admin/health`; `docker build ./apps/api-gateway` собирается успешно.

---

### 1.5 Ruff (lint + format)

- [x] Добавить в корневой `pyproject.toml` секцию `[tool.ruff]` (`line-length = 100`, `target-version = "py312"`, `src = ["apps", "packages"]`).
- [x] Настроить `[tool.ruff.lint]` с набором правил: `E`, `F`, `W`, `I` (isort), `N`, `UP`, `B`, `C4`, `SIM`, `TCH`, `RUF`; задать `per-file-ignores` для `tests/*` (`S101` и т.п.).
- [x] Включить `[tool.ruff.format]` (замена black; `quote-style = "double"`) и удалить необходимость в отдельном black.
- [x] Настроить isort-совместимость через `[tool.ruff.lint.isort]` с `known-first-party = ["kg_common","kg_schema","kg_extractors","kg_retrievers","kg_eval"]`.
- [x] Прогнать `uv run ruff check .` и `uv run ruff format --check .` на всей кодовой базе-заготовке; устранить нарушения так, чтобы вывод был чистым.
- [x] Добавить make-targets `make lint` (`ruff check`) и `make fmt` (`ruff format`).

**Критерий приёмки:** `uv run ruff check .` завершается кодом 0 без findings; `uv run ruff format --check .` не предлагает изменений.

---

### 1.6 Mypy (статическая типизация)

- [ ] Добавить `[tool.mypy]` в корневой `pyproject.toml`: `python_version = "3.12"`, `strict = true`, `mypy_path = ["packages/kg_common/src", ...]` или через namespace-пакеты, `plugins = ["pydantic.mypy"]`.
- [ ] Настроить `pydantic.mypy` плагин (`[tool.pydantic-mypy] init_forbid_extra = true`, `warn_required_dynamic_aliases = true`).
- [ ] Добавить `[[tool.mypy.overrides]]` с `ignore_missing_imports = true` для внешних библиотек без стабов (`neo4j`, `qdrant_client`, `gliner`, `pymatgen`, `splink`, `haystack`, `llama_index`, `reagraph`-нет).
- [ ] Убедиться, что все пакеты содержат `py.typed`, чтобы mypy проверял их как типизированные.
- [ ] Прогнать `uv run mypy apps packages` и добиться нулевого числа ошибок на заготовках.
- [ ] Добавить make-target `make type` (`mypy apps packages`).

**Критерий приёмки:** `uv run mypy apps packages` печатает `Success: no issues found`.

---

### 1.7 Pytest (тестовый фреймворк)

- [x] Добавить `[tool.pytest.ini_options]` в корневой `pyproject.toml`: `testpaths = ["apps","packages"]`, `addopts = "-ra --strict-markers --cov=. --cov-report=term-missing"`, `asyncio_mode = "auto"`.
- [x] Настроить `[tool.coverage.run]`/`[tool.coverage.report]` (source по `apps`+`packages`, `fail_under = 60` на старте, omit для `tests/*` и `__init__.py`).
- [x] Создать корневой `conftest.py` с общими фикстурами (напр. `settings` из test `.env`, фейковые клиенты) и регистрацией маркеров (`unit`, `integration`, `slow`).
- [x] Обеспечить наличие smoke/health-тестов из §1.3 и §1.4, чтобы `pytest` собирал ненулевой набор тестов.
- [x] Прогнать `uv run pytest -q` — все тесты зелёные, покрытие не падает ниже `fail_under`.
- [x] Добавить make-targets `make test` (`pytest`) и `make test-cov`.

**Критерий приёмки:** `uv run pytest -q` завершается кодом 0, собирает ≥1 тест на каждый пакет/сервис с FastAPI-app, coverage ≥ порога.

---

### 1.8 Frontend-инструментарий (`apps/frontend`): TypeScript, ESLint, Prettier, Vite

- [x] Инициализировать `apps/frontend/package.json` (name `frontend`, `type: module`, `private: true`) с `pnpm` как менеджером пакетов; создать `pnpm-workspace.yaml` в корне репо (`packages: ["apps/frontend"]`) на случай будущих JS-пакетов.
- [x] Установить frontend-зависимости из §14.1: `react`, `react-dom`, `typescript`, `vite`, `@tanstack/react-query`, `@tanstack/react-router`, `zustand`, `zod`, `react-hook-form`, `tailwindcss`, `lucide-react`, `reagraph`, `sigma`, `graphology`, `cytoscape`, `react-force-graph`, `@xyflow/react`, `echarts`, `echarts-for-react`, `react-markdown`, `remark-gfm`; devDeps: `eslint`, `prettier`, `@typescript-eslint/*`, `eslint-plugin-react`, `eslint-plugin-react-hooks`, `eslint-config-prettier`, `vitest`.
- [x] Инициализировать `shadcn/ui` (§14.1) — создать `components.json`, базовый `tailwind.config.ts`, `postcss.config.js` и стиль-энтрипоинт `src/styles/globals.css`.
- [x] Создать `apps/frontend/tsconfig.json` (`strict: true`, `moduleResolution: bundler`, `jsx: react-jsx`, path-aliases `@/*`).
- [x] Создать `apps/frontend/vite.config.ts` с dev-сервером на порту 3000 (соответствует `ports: ["3000:3000"]` из §13.1) и proxy `/api` на `http://localhost:8000`.
- [x] Создать минимальный React-скелет: `src/main.tsx`, `src/App.tsx` (health-ping на `/api/v1/admin/health`), провайдеры `QueryClientProvider` и router-заготовку; проверить `pnpm build`.
- [x] Настроить ESLint (`eslint.config.js`, flat-config): `@typescript-eslint`, `react`, `react-hooks`, интеграция с `eslint-config-prettier`; правило запрета неиспользуемых импортов.
- [x] Настроить Prettier (`.prettierrc.json`: `printWidth: 100`, `singleQuote: true`, `semi: true`, `trailingComma: all`) и `.prettierignore` (`dist`, `node_modules`, `pnpm-lock.yaml`).
- [x] Добавить npm-скрипты в `package.json`: `dev`, `build`, `preview`, `lint` (`eslint .`), `format` (`prettier --check .`), `typecheck` (`tsc --noEmit`), `test` (`vitest run`).
- [x] Создать `apps/frontend/Dockerfile` (node-base, `pnpm install --frozen-lockfile`, `pnpm build`, serve) под `build: ./apps/frontend` из §13.1.
- [x] Добавить make-targets `make fe-lint`, `make fe-build`, `make fe-test`.

**Критерий приёмки:** `pnpm --dir apps/frontend install --frozen-lockfile` ставит зависимости; `pnpm --dir apps/frontend lint`, `... typecheck`, `... build` завершаются успешно; `prettier --check .` не находит нарушений форматирования.

---

### 1.9 Конфигурация и секреты (pydantic-settings, `.env.example`, секрет-менеджмент)

- [x] Реализовать в `packages/kg_common/src/kg_common/config.py` класс `Settings(BaseSettings)` на `pydantic-settings` с секциями/префиксами по сервисам: Neo4j (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`), Qdrant (`QDRANT_URL`), OpenSearch (`OPENSEARCH_URL`, `OPENSEARCH_USER`, `OPENSEARCH_PASSWORD`), Postgres (`POSTGRES_DSN`), Redis (`REDIS_URL`), MinIO (`MINIO_ENDPOINT`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_BUCKET`), Docling (`DOCLING_SERVE_URL`), Dagster (`DAGSTER_URL`), LLM/embeddings (`LLM_API_BASE`, `LLM_API_KEY`, `EMBEDDING_MODEL`), observability (`OTEL_EXPORTER_OTLP_ENDPOINT`, `MLFLOW_TRACKING_URI`, `LANGSMITH_API_KEY`), а также `APP_ENV` и `LOG_LEVEL` (используются логированием/телеметрией из §1.12).
- [x] Настроить `model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="ignore")`; секреты типизировать `SecretStr`.
- [x] Реализовать `@lru_cache`-фабрику `get_settings()` и re-export из `kg_common`.
- [x] Создать корневой `.env.example`, перечисляющий ВСЕ переменные и порты из §13.1 с дефолтами локального compose (`NEO4J_AUTH=neo4j/password` → `NEO4J_USER=neo4j`/`NEO4J_PASSWORD=password`, `NEO4J_PLUGINS=["apoc"]`, `POSTGRES_USER=kg`/`POSTGRES_PASSWORD=kg`/`POSTGRES_DB=kg_app`, `MINIO_ROOT_USER=minio`/`MINIO_ROOT_PASSWORD=minio123`, `OPENSEARCH_INITIAL_ADMIN_PASSWORD=adminadminadmin`, `discovery.type=single-node`, `plugins.security.disabled=true`, `DOCLING_SERVE_ENABLE_UI=1`; полный набор портов сервисов §13.1: frontend 3000, api 8000, agent 8010, ingestion 8020, docling 5001, neo4j 7474/7687, qdrant 6333/6334, opensearch 9200, postgres 5432, redis 6379, minio 9000/9001, dagster 3001) — без реальных секретов.
- [x] Написать тест `packages/kg_common/tests/test_config.py`, который загружает `.env.example` и подтверждает, что `Settings` валидируется без ошибок и все обязательные поля покрыты (защита от «забыл переменную»).
- [x] Задокументировать секрет-менеджмент в `docs/secrets.md`: локально — `.env` (в `.gitignore`); в проде — HashiCorp Vault / Docker/K8s secrets; описать соглашение о путях Vault (`secret/kg/<env>/<service>`) и запрет коммита реальных секретов.
- [x] Добавить в pre-commit hook детектор секретов (`detect-secrets` или `gitleaks`) со scan корня.
- [x] Добавить `make check-env`, проверяющий что все ключи из `.env.example` присутствуют (diff по ключам с локальным `.env`).

**Критерий приёмки:** `uv run pytest packages/kg_common/tests/test_config.py` проходит; `.env.example` содержит каждую переменную, используемую в `Settings` и в §13.1; gitleaks/detect-secrets не находит секретов в репозитории.

---

### 1.10 Pre-commit hooks

- [x] Создать `.pre-commit-config.yaml` с хуками: `ruff` (`ruff check --fix`), `ruff-format`, `mypy` (на изменённые файлы), стандартные `pre-commit-hooks` (`end-of-file-fixer`, `trailing-whitespace`, `check-yaml`, `check-json`, `check-merge-conflict`, `check-added-large-files`), `gitleaks`/`detect-secrets`.
- [x] Добавить локальный хук для frontend: `prettier --check` и `eslint` на файлах `apps/frontend/**`.
- [x] Добавить хук `commitizen`/`conventional-pre-commit` для валидации сообщений коммитов по Conventional Commits (см. §1.13).
- [x] Закрепить версии хуков (`rev:`), выполнить `uv run pre-commit install` и `pre-commit install --hook-type commit-msg`.
- [x] Прогнать `uv run pre-commit run --all-files` и добиться, чтобы все хуки прошли (allowlist/исправления по мере необходимости).
- [x] Добавить make-target `make pre-commit` (`pre-commit run --all-files`).

**Критерий приёмки:** `uv run pre-commit run --all-files` завершается со статусом Passed по всем хукам; попытка коммита с невалидным сообщением или секретом блокируется хуком.

---

### 1.11 Makefile / Taskfile (автоматизация задач)

- [x] Создать корневой `Makefile` с фонемами и целями: `bootstrap` (uv sync + pnpm install), `up`/`down` (docker compose из `infra/`), `dev` (параллельный запуск api+frontend), `lint`, `fmt`, `type`, `test`, `test-cov`, `fe-lint`, `fe-build`, `fe-test`, `pre-commit`, `check` (агрегирует lint+type+test), `clean`.
- [x] Обеспечить, что `make check` — единая команда, воспроизводящая проверки CI локально (lint + format-check + mypy + pytest + frontend lint/build).
- [x] Добавить `.PHONY` для всех целей и `help`-цель, печатающую список задач с описаниями (self-documenting Makefile).
- [x] (Опционально) Продублировать ключевые задачи в `Taskfile.yml` для кроссплатформенности; зафиксировать выбор Make vs Task в `docs/adr/0002-task-runner.md`.
- [x] Проверить каждую цель Makefile «в холодном» окружении (после `make clean`).

**Критерий приёмки:** `make help` выводит все цели с описаниями; `make check` на чистом чекауте проходит все проверки и завершается кодом 0.

---

### 1.12 Общие библиотеки: логирование и телеметрия (structlog, OpenTelemetry)

- [x] Реализовать `packages/kg_common/src/kg_common/logging.py`: конфигурация `structlog` (JSON-рендер в проде, консоль в dev), инъекция `request_id`/`trace_id`, уровень из `Settings.LOG_LEVEL`.
- [x] Реализовать `telemetry.py`: инициализация OpenTelemetry SDK (`opentelemetry-sdk`), OTLP-экспортер по `OTEL_EXPORTER_OTLP_ENDPOINT`, ресурсные атрибуты (`service.name` = имя сервиса) — заготовка под §16 Phase 9 «add OpenTelemetry traces».
- [x] Добавить хелпер `setup_observability(service_name)` для вызова из `main.py` каждого сервиса.
- [x] Написать тесты, что логгер выдаёт структурированную запись с обязательными полями и что `setup_observability` не падает без коллектора (graceful no-op).

**Критерий приёмки:** импорт и вызов `kg_common.logging.configure()` + `setup_observability("api-gateway")` работает в smoke-тесте; лог-запись содержит `event`, `level`, `service`, `timestamp`.

---

### 1.13 Contribution-конвенции и документация процессов

- [x] Создать `CONTRIBUTING.md`: правила ветвления (trunk-based / feature-branches), запрет прямых пушей в `main`, требование `make check` перед PR, стиль кода (ruff/prettier), политика тестов (новый код — с тестами).
- [x] Задать конвенцию сообщений коммитов Conventional Commits в `docs/conventions/commits.md` (типы `feat|fix|docs|refactor|test|chore|ci|build`, scope = имя сервиса/пакета) и связать с хуком из §1.10.
- [x] Создать `CODEOWNERS` (`.github/CODEOWNERS`) с ответственными по областям (`/apps/api-gateway/`, `/packages/kg_schema/` и т.д.).
- [x] Создать шаблоны GitHub: `.github/pull_request_template.md` (чеклист: тесты, lint, docs, ADR при архитектурных решениях) и `.github/ISSUE_TEMPLATE/{bug,feature}.md`.
- [x] Создать каталог `docs/adr/` с `0000-template.md` (MADR-формат) и завести ADR из §1.2/§1.11 (`0001`, `0002`).
- [x] Создать `docs/architecture.md` с деревом монорепо (§6.1), картой сервисов/портов (§13.1) и ссылкой на дизайн-документ как source of truth.
- [x] Добавить `LICENSE` (согласовать лицензию проекта) и `SECURITY.md` (процедура репорта уязвимостей).
- [x] Описать конвенцию именования пакетов/модулей (snake_case для Python `kg_*`, kebab-case для dist-имён) в `docs/conventions/naming.md`.
- [x] Создать корневой `.editorconfig` (`charset=utf-8`, `end_of_line=lf`, `insert_final_newline=true`, `trim_trailing_whitespace=true`, `indent_style=space`, `max_line_length=100` — согласовано с ruff `line-length=100` и prettier `printWidth=100`) для единообразия редакторов по всему монорепо (Python + TS).
- [x] Завести ADR `docs/adr/0003-core-technology-stack.md`, фиксирующий выбор целевого стека по §4.1/§21 (Neo4j, Qdrant, OpenSearch, LangGraph, Reagraph, LlamaIndex PropertyGraphIndex, Splink, Dagster, DataHub/OpenMetadata) и рассмотренные-отклонённые альтернативы: графовые БД (ArangoDB, Memgraph, TypeDB), graph-UI (AntV G6, Graphin, React Flow), lineage (Airbyte, Apache Atlas) — со ссылкой на каталог §1.14.
- [x] Задокументировать в `docs/conventions/api-contracts.md` конвенцию синхронизации контрактов backend↔frontend: FastAPI экспортирует OpenAPI-схему, TS-типы фронтенда (§5.3 `GraphResponse`/`GraphNode`/`GraphEdge`/`ChatStreamEvent`) и Pydantic-DTO (`kg_common.dto`, §7.3) держатся в паритете (кодогенерация типов из OpenAPI либо ревью-чеклист); нарушение паритета ловится в CI/PR-чеклисте.

**Критерий приёмки:** присутствуют `CONTRIBUTING.md`, `CODEOWNERS`, PR/issue-шаблоны, `.editorconfig`, ≥4 ADR-файла (template + 3 решения `0001`–`0003`), `docs/conventions/api-contracts.md` и `docs/architecture.md` с актуальным деревом §6.1; ссылки в документах ведут на существующие пути.

---

### 1.14 Вендоринг/клонирование OSS-репозиториев (§22)

- [x] Установить конвенцию вендоринга в `third_party/README.md`: способ (git submodule для reference-форков; pin по конкретному commit/tag), запрет модификации кода in-place без обёртки, каталог `third_party/<name>/`.
- [x] Создать `scripts/vendor.sh`, который клонирует/обновляет reference-репозитории по pinned-ревизиям (идемпотентно) и вызывается из `make vendor`.
- [x] Зафиксировать в `third_party/CATALOG.md` полный перечень OSS-репозиториев из §22 с git-URL и указанием, в каком разделе плана они используются (чтобы тяжёлый вендоринг делали профильные разделы, а здесь — только каталог и механизм). Обязательные записи каталога:
  - LangGraph — `https://github.com/langchain-ai/langgraph` (agent-service);
  - LlamaIndex — `https://github.com/run-llama/llama_index` (kg_extractors/kg_retrievers); LlamaIndex Property Graph Index docs — `https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/`;
  - Microsoft GraphRAG — `https://github.com/microsoft/graphrag` (retrieval Mode C);
  - Neo4j LLM Graph Builder — `https://github.com/neo4j-labs/llm-graph-builder` (internal reference/fork, §21 optional);
  - Haystack — `https://github.com/deepset-ai/haystack`; Hayhooks — `https://github.com/deepset-ai/hayhooks`;
  - Docling — `https://github.com/docling-project/docling`; Docling Serve — `https://github.com/docling-project/docling-serve`; Marker — `https://github.com/datalab-to/marker`; Unstructured — `https://github.com/Unstructured-IO/unstructured`;
  - Neo4j — `https://github.com/neo4j/neo4j`; Neo4j GraphQL — `https://github.com/neo4j/graphql`; APOC — `https://github.com/neo4j-contrib/neo4j-apoc-procedures`; GDS — `https://github.com/neo4j/graph-data-science`; Qdrant — `https://github.com/qdrant/qdrant`; OpenSearch — `https://github.com/opensearch-project/OpenSearch`; ArangoDB — `https://github.com/arangodb/arangodb`; Memgraph — `https://github.com/memgraph/memgraph`; TypeDB — `https://github.com/typedb/typedb` (последние три — альтернативы graph DB из §22, reference-only);
  - Reagraph — `https://github.com/reaviz/reagraph`; Cytoscape.js — `https://github.com/cytoscape/cytoscape.js`; Sigma.js — `https://github.com/jacomyal/sigma.js`; Graphology — `https://github.com/graphology/graphology`; React Force Graph — `https://github.com/vasturiano/react-force-graph`; AntV G6 — `https://github.com/antvis/G6`; Graphin — `https://github.com/antvis/Graphin`; React Flow — `https://github.com/xyflow/xyflow`; Apache ECharts — `https://github.com/apache/echarts`;
  - Splink — `https://github.com/moj-analytical-services/splink`; Dedupe — `https://github.com/dedupeio/dedupe`; OpenRefine — `https://github.com/OpenRefine/OpenRefine`;
  - Dagster — `https://github.com/dagster-io/dagster`; DataHub — `https://github.com/datahub-project/datahub`; OpenMetadata — `https://github.com/open-metadata/OpenMetadata`; Marquez — `https://github.com/MarquezProject/marquez`; MLflow — `https://github.com/mlflow/mlflow`; DVC — `https://github.com/iterative/dvc`; lakeFS — `https://github.com/treeverse/lakeFS`; Airbyte — `https://github.com/airbytehq/airbyte`; Apache Atlas — `https://github.com/apache/atlas`;
  - MatKG — `https://github.com/olivettigroup/MatKG`; MatBERT — `https://github.com/lbnlp/MatBERT`; MatEntityRecognition — `https://github.com/CederGroupHub/MatEntityRecognition`; Matscholar — `https://github.com/materialsintelligence/matscholar`; Propnet — `https://github.com/materialsintelligence/propnet`; Materials Project API — `https://github.com/materialsproject/api`; pymatgen — `https://github.com/materialsproject/pymatgen`;
  - eLabFTW — `https://github.com/elabftw/elabftw`; openBIS — `https://github.com/openbis`;
  - §21-only опциональные (упомянуты в дизайне вне §22, отслеживать в каталоге): Superset — `https://github.com/apache/superset` (dashboards); Protégé — `https://github.com/protegeproject/protege` и LinkML — `https://github.com/linkml/linkml` (ontology governance для `kg_schema`, §6.1/§8).
- [x] Клонировать как reference-форк (submodule) минимально необходимое для старта: `neo4j-labs/llm-graph-builder` в `third_party/llm-graph-builder` (internal reference per §21) и добавить его в `.gitmodules`.
- [x] Добавить в `.gitignore`/CI-исключения тяжёлые submodule-каталоги, чтобы lint/mypy/pytest НЕ сканировали `third_party/*` (исключить в `[tool.ruff]`, `[tool.mypy]`, `testpaths`).

**Критерий приёмки:** `make vendor` идемпотентно инициализирует submodules; `third_party/CATALOG.md` перечисляет все репозитории §22 с корректными git-URL; инструменты lint/type/test игнорируют `third_party/`.

---

### 1.15 CI на GitHub Actions (lint / type / test)

- [x] Создать `.github/workflows/ci.yml`, триггеры `push` (в `main`) и `pull_request`; concurrency-group для отмены устаревших ранов.
- [x] Job `python-quality`: setup Python 3.12, установка `uv` (`astral-sh/setup-uv` с кэшем), `uv sync --frozen`, шаги `ruff check .`, `ruff format --check .`, `mypy apps packages`, `pytest --cov` с загрузкой coverage-артефакта.
- [x] Job `frontend-quality`: setup Node + `pnpm` (с кэшем), `pnpm --dir apps/frontend install --frozen-lockfile`, шаги `eslint`, `prettier --check`, `tsc --noEmit`, `vitest run`, `pnpm build`.
- [x] Job `secrets-scan`: запуск `gitleaks`/`detect-secrets` на diff.
- [x] Job `pre-commit`: `pre-commit run --all-files` (гарантирует паритет локальных и CI-проверок).
- [x] Настроить матрицу/кэширование зависимостей (`uv` cache, pnpm store) для ускорения; ограничить `timeout-minutes`.
- [x] Настроить в репозитории branch protection на `main`: required status checks = `python-quality`, `frontend-quality`, `secrets-scan`; запрет merge при красном CI (задокументировать в `CONTRIBUTING.md`).
- [x] Добавить status-badge CI в корневой `README.md`.
- [x] Не выполнять клонирование `third_party/*` submodules в CI по умолчанию (`submodules: false`), кроме отдельного nightly-job при необходимости.

**Критерий приёмки:** тестовый PR запускает workflow; jobs `python-quality`, `frontend-quality`, `secrets-scan`, `pre-commit` зелёные; CI падает при внесении lint/type/test-ошибки (проверено «negative»-коммитом); в `README.md` виден CI-бейдж.

---

### 1.16 Итоговый gate соответствия §16 Phase 0 (в части tooling)

- [ ] Свести чек-лист Phase 0 §16 «create repo structure» и «configure ruff/mypy/pytest/eslint/prettier» и подтвердить, что каждый пункт закрыт задачами §1.1–§1.15.
- [ ] Прогнать `make check` end-to-end на чистом клоне (fresh `git clone` → `make bootstrap` → `make check`) и зафиксировать зелёный результат в `docs/phase0-tooling-signoff.md`.
- [ ] Убедиться, что `.env.example` покрывает весь стек §13.1 и что FastAPI health-endpoint (`GET /api/v1/admin/health`) отвечает — как предпосылка к acceptance «API health checks pass» из Phase 0.
- [ ] Зафиксировать версии всего toolchain (Python, uv, node, pnpm, ruff, mypy, pytest) в `docs/toolchain-versions.md` и в `.tool-versions`/`mise.toml` для воспроизводимости.

**Критерий приёмки:** на свежем клоне последовательность `git clone → make bootstrap → make check` проходит без ошибок; `docs/phase0-tooling-signoff.md` содержит вывод команд-подтверждений; все пункты tooling-части §16 Phase 0 отмечены выполненными.


---


## 2. Инфраструктура и DevOps

Раздел покрывает полную инфраструктуру запуска системы: полный Docker Compose-стек из §13.1, Dockerfile на каждый backend/frontend-сервис из §6.1, Helm-чарты и K8s-манифесты для прод, сети/тома/health checks/resource limits/restart policies, автоматическую инициализацию хранилищ, бэкап и восстановление всех stateful-компонентов, разделение local vs prod профилей, управление секретами в проде, CI/CD и observability-инфраструктуру.

Все артефакты этого раздела живут в директории `infra/` из структуры §6.1 (`infra/docker-compose.yml`, `infra/helm/`, `infra/dagster/`, `infra/neo4j/`, `infra/opensearch/`, `infra/qdrant/`), а Dockerfile — внутри каждого пакета `apps/*`.

Зависимости: раздел «Knowledge graph schema» (Cypher-constraints из §8.4 для init Neo4j), раздел «Ingestion и indexing pipeline» (Dagster-jobs, которые деплоятся сервисом `dagster`), раздел «Backend plan» (health-endpoints `/api/v1/admin/health`, `/api/v1/admin/metrics` из §6.2), раздел «Метаданные/lineage/governance» (DataHub/OpenMetadata из Phase 8). Секции, которые пишут код сервисов, поставляют содержимое образов; данный раздел поставляет их упаковку и оркестрацию.

### 2.1 Базовая структура репозитория и инструментарий

- [ ] Создать monorepo-структуру каталогов строго по §6.1: `apps/{api-gateway,agent-service,ingestion-service,graph-service,search-service,extraction-service,curation-service,frontend}`, `packages/{kg_schema,kg_extractors,kg_retrievers,kg_eval,kg_common}`, `infra/{helm,dagster,neo4j,opensearch,qdrant}` и `infra/docker-compose.yml`.
- [ ] Инициализировать git-репозиторий, добавить `.gitignore` (Python `__pycache__`, `.venv`, `node_modules`, `dist`, `.env`, `*.dump`, `*.snapshot`, локальные тома `infra/volumes/`).
- [ ] Добавить корневой `README.md` с командой быстрого старта (`docker compose up`) и матрицей портов всех 12+ сервисов из §13.1.
- [ ] Настроить Python-тулинг на уровне monorepo: `pyproject.toml` с конфигурацией `ruff`, `mypy`, `pytest`; единая версия Python (3.12+) закреплена в `.python-version`.
- [ ] Настроить frontend-тулинг: `eslint`, `prettier` в `apps/frontend`; `package.json` с lint/format-скриптами.
- [ ] Добавить `pre-commit` конфиг (`.pre-commit-config.yaml`) с хуками `ruff`, `ruff-format`, `mypy`, `eslint`, проверкой отсутствия секретов (`detect-secrets`).
- [ ] Создать корневой `Makefile` с целями: `up`, `down`, `logs`, `ps`, `init-db`, `seed`, `backup`, `restore`, `test`, `lint`, `fmt` — каждая цель вызывает соответствующий compose/скрипт.
- [ ] Добавить в `Makefile` дополнительные цели: `worker` (запуск RQ/Celery воркера), `demo` (поднять стек + загрузить демо-набор §19), `deploy-prod` (`docker compose ... prod` / `helm upgrade`), `dr-test` (прогон backup→wipe→restore), `smoke` (compose-smoke health-check).

**Критерий приёмки:** дерево каталогов совпадает с §6.1 (проверяется скриптом-линтером структуры); `make lint` и `pre-commit run --all-files` проходят на пустом скелете без ошибок.

### 2.2 Конфигурация окружения и профили (local vs prod)

- [ ] Создать `.env.example` со ВСЕМИ переменными для 12 сервисов §13.1: `NEO4J_AUTH`, `NEO4J_URI`, `NEO4J_PLUGINS`, `QDRANT_URL`, `OPENSEARCH_URL`, `OPENSEARCH_INITIAL_ADMIN_PASSWORD`, `POSTGRES_USER/PASSWORD/DB/HOST/PORT`, `REDIS_URL`, `MINIO_ROOT_USER/PASSWORD`, `MINIO_ENDPOINT`, `DOCLING_SERVE_URL`, `DAGSTER_HOME`, `LLM_API_KEY`, `EMBEDDING_MODEL`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `MLFLOW_TRACKING_URI`.
- [ ] Дополнить `.env.example` переменными смежных подсистем: `CELERY_BROKER_URL`/`RQ_REDIS_URL` (= `REDIS_URL`) для воркера быстрых фоновых задач UI/API из §1; `LLM_API_BASE`, `RERANKER_MODEL` (cross-encoder из §10.2); трейсинг агента `LANGCHAIN_TRACING_V2`, `LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT` (§15.3, опционально); governance-эндпоинты `DATAHUB_GMS_URL` / `OPENMETADATA_HOST_PORT` (Phase 8); `NEO4J_PLUGINS: '["apoc","graph-data-science"]'` (§10.4 Mode D graph algorithms).
- [ ] Реализовать типизированную загрузку конфигурации через `pydantic-settings` в `packages/kg_common/config.py` (single source of truth для всех сервисов), c валидацией обязательных переменных на старте.
- [ ] Разделить профили через Docker Compose overrides: `infra/docker-compose.yml` (base) + `infra/docker-compose.local.yml` (dev: bind-mounts исходников, hot-reload, открытые порты, dev-пароли) + `infra/docker-compose.prod.yml` (prod: собранные образы из registry, без bind-mount, closed-порты, секреты из внешнего источника).
- [ ] Определить Compose `profiles` для опциональных сервисов (`observability`, `governance`, `fallback-parsers`), чтобы `docker compose --profile observability up` поднимал Prometheus/Grafana/OTel-collector отдельно.
- [ ] Задокументировать в `infra/README.md` разницу local vs prod, список профилей и переменных, порядок запуска.

**Критерий приёмки:** `docker compose --env-file .env.example -f infra/docker-compose.yml -f infra/docker-compose.local.yml config` валидируется без ошибок; отсутствие обязательной переменной приводит к явной ошибке валидации `pydantic-settings` при старте сервиса.

### 2.3 Dockerfile для каждого сервиса

- [ ] `apps/api-gateway/Dockerfile` — multi-stage Python build (builder + slim runtime), non-root user, `uvicorn[standard]` как entrypoint на порт 8000, установка зависимостей из §13.2 (`fastapi`, `uvicorn`, `pydantic`, `neo4j`, `qdrant-client`, `opensearch-py`, `structlog`, `orjson`).
- [ ] `apps/agent-service/Dockerfile` — Python runtime на порт 8010, зависимости LangGraph-стека (`langgraph`, `langchain-core`, `llama-index`, `llama-index-graph-stores-neo4j`, `llama-index-vector-stores-qdrant`, `haystack-ai`).
- [ ] `apps/ingestion-service/Dockerfile` — Python runtime на порт 8020, зависимости парсинга/извлечения (`gliner`, `sentence-transformers`, `fastembed`, `pint`, `pymatgen`, `pandas`, `polars`, `duckdb`, `splink`).
- [ ] `apps/graph-service/Dockerfile`, `apps/search-service/Dockerfile`, `apps/extraction-service/Dockerfile`, `apps/curation-service/Dockerfile` — по одному Dockerfile на сервис §6.1 с соответствующими зависимостями (`kg_retrievers`, `kg_extractors`, `kg_schema` из `packages/`).
- [ ] `apps/frontend/Dockerfile` — multi-stage Node build (`npm ci` + `vite build`) → раздача статикой через nginx (или Node preview) на порт 3000; отдельный `nginx.conf` с проксированием `/api` на `api:8000`.
- [ ] `infra/dagster/Dockerfile` — образ Dagster на порт 3001 с установленным кодом пайплайнов ingestion (зависит от раздела Ingestion), `DAGSTER_HOME` смонтирован в том; один образ обслуживает и `dagster-webserver`, и `dagster-daemon`.
- [ ] Общий базовый образ: создать `infra/docker/base.python.Dockerfile` с зафиксированной версией Python и системными библиотеками (для `pymatgen`/`duckdb`), от которого наследуются Python-сервисы, чтобы не дублировать установку. Локальные пакеты `packages/*` устанавливаются как editable/wheel во все Python-образы.
- [ ] Воркер быстрых фоновых задач (§1) переиспользует образ `api-gateway`/`agent-service` с другим entrypoint (`rq worker` / `celery -A ... worker`) — отдельный Dockerfile не требуется.
- [ ] Для каждого Python-Dockerfile добавить `.dockerignore`, кэширование слоёв зависимостей (COPY requirements → install → COPY code), закрепление зависимостей через lock-файл (`uv.lock`/`requirements.txt` с хэшами).
- [ ] Каждый образ содержит встроенный `HEALTHCHECK` (Python-сервисы — `curl -f http://localhost:PORT/api/v1/admin/health` или `/healthz`; frontend — проверка отдачи index).

**Критерий приёмки:** `docker build` каждого из 8 apps-сервисов + `infra/dagster` завершается успешно; итоговые образы запускаются под non-root пользователем (`docker inspect` показывает `User != root`); `docker image ls` показывает slim runtime-слои без build-инструментов.

### 2.4 Полный Docker Compose-стек (local)

- [ ] Реализовать `infra/docker-compose.yml` со всеми 12 сервисами §13.1: `frontend` (3000), `api` (8000), `agent` (8010), `ingestion` (8020), `docling` (5001), `neo4j` (7474/7687), `qdrant` (6333/6334), `opensearch` (9200), `postgres` (5432), `redis` (6379), `minio` (9000/9001), `dagster` (3001).
- [ ] Добавить в стек оставшиеся сервисы §6.1 (`graph-service`, `search-service`, `extraction-service`, `curation-service`) с портами по конвенции §13.1 (8030/8040/8050/8060), собираемые из соответствующих `apps/*/Dockerfile`.
- [ ] Добавить сервис `worker` (RQ или Celery) для быстрых фоновых задач UI/API из §1 (НЕ Dagster): образ = образ `api-gateway`/`agent-service` с командой-воркером, `depends_on: redis (service_healthy)`, `BROKER_URL=redis://redis:6379`; масштабируется числом реплик.
- [ ] Обеспечить запуск `dagster-daemon` (отдельный сервис или второй процесс образа `dagster`), так как daemon обязателен для schedules/sensors — он используется backup-расписанием (§2.7) и ingestion-сенсорами (раздел Ingestion); без него schedule не срабатывает.
- [ ] Прописать `image` для внешних компонентов строго по §13.1: `quay.io/docling-project/docling-serve:latest`, `neo4j:2026.05-community`, `qdrant/qdrant:latest`, `opensearchproject/opensearch:latest`, `postgres:16`, `redis:7`, `minio/minio`. Зафиксировать `:latest` на конкретные digest/тэги для воспроизводимости.
- [ ] Настроить `depends_on` с `condition: service_healthy` согласно графу зависимостей §13.1: `api` → postgres, redis, neo4j, qdrant, opensearch; `agent` → api, neo4j, qdrant, opensearch; `ingestion` → docling, dagster, minio.
- [ ] Прописать `environment`/`env_file: .env` для каждого сервиса: `NEO4J_AUTH: neo4j/password`, `NEO4J_PLUGINS: '["apoc"]'` (+ `graph-data-science`), `discovery.type: single-node` и `plugins.security.disabled: "true"` для OpenSearch, `OPENSEARCH_INITIAL_ADMIN_PASSWORD`, `POSTGRES_USER/PASSWORD/DB=kg/kg/kg_app`, `MINIO_ROOT_USER/PASSWORD=minio/minio123`, `MINIO server /data --console-address ':9001'`, `DOCLING_SERVE_ENABLE_UI: "1"`.
- [ ] Реализовать `infra/docker-compose.local.yml` override: bind-mount исходников `./apps/*/src`, `command` с `--reload` для uvicorn, `vite dev` для frontend, экспонирование всех портов на host.

**Критерий приёмки:** `docker compose up` (Phase 0 acceptance) поднимает все сервисы, все health checks зелёные; frontend открывается на :3000; `GET /api/v1/admin/health` возвращает 200; Neo4j Browser доступен на :7474; MinIO console на :9001; Dagster UI на :3001; `worker` и `dagster-daemon` в статусе running.

### 2.5 Сети, тома, health checks, resource limits, restart policies

- [ ] Определить именованные Docker-сети: `kg-frontend-net` (frontend↔api) и `kg-backend-net` (api/agent/ingestion↔хранилища); хранилища не публикуют порты в prod-override.
- [ ] Определить именованные volumes для всех stateful-сервисов: `neo4j-data`, `neo4j-logs`, `neo4j-plugins`, `qdrant-storage`, `opensearch-data`, `postgres-data`, `redis-data`, `minio-data`, `dagster-home`.
- [ ] Прописать `healthcheck` для каждого сервиса: neo4j (`cypher-shell "RETURN 1"`), qdrant (`GET /healthz`), opensearch (`GET /_cluster/health`), postgres (`pg_isready`), redis (`redis-cli ping`), minio (`GET /minio/health/ready`), docling (`GET /health`), dagster (`GET /server_info`), api/agent/ingestion (`/api/v1/admin/health`).
- [ ] Задать `deploy.resources.limits` (cpus/memory) и `reservations` для каждого сервиса; для тяжёлых (neo4j, opensearch, ingestion с моделями) выставить память с запасом (например neo4j `NEO4J_dbms_memory_heap_max__size`, opensearch `OPENSEARCH_JAVA_OPTS=-Xms/-Xmx`).
- [ ] Задать `restart: unless-stopped` для всех долгоживущих сервисов; для job-подобных (init-контейнеры) — `restart: "no"`.
- [ ] Настроить логирование: `logging.driver: json-file` с `max-size`/`max-file` (ротация), чтобы тома логов не переполняли диск.

**Критерий приёмки:** `docker compose ps` показывает статус `healthy` для всех сервисов; `docker compose stop` + `docker compose up` сохраняет данные Neo4j/Postgres/Qdrant/MinIO (тома персистентны); превышение resource limits приводит к throttling/OOM только у целевого контейнера, стек не падает целиком.

### 2.6 Автоматическая инициализация хранилищ (init/seed)

- [ ] Создать init-скрипт Neo4j `infra/neo4j/init.cypher` и сервис `neo4j-init` (одноразовый контейнер `depends_on neo4j healthy`), применяющий constraints/indexes из §8.4 через `cypher-shell` (зависимость от раздела «Knowledge graph schema»): uniqueness-constraints (`material_id`, `experiment_id`, `evidence_id`, `document_id`, `property_id`, `equipment_id`), fulltext-индекс `entity_name_index`, индексы `measurement_value_index`/`processing_temperature_index`/`processing_time_index` и опциональный vector index `entity_embedding_index` (1024, cosine).
- [ ] Создать `infra/qdrant/init.py` (или entrypoint) — создание коллекций для chunk-эмбеддингов с нужной размерностью вектора и метрикой (cosine), идемпотентно; payload-схема по §9.2 (`doc_id`, `chunk_id`, `entity_ids`, `material_ids`, `property_ids`, `processing_operation`, `temperature_c`, `time_h`, `source_type`, `confidence`, `review_status`).
- [ ] Создать `infra/opensearch/init.sh` — создание индексов и mapping для keyword-поиска по chunks (BM25-анализаторы, facets, numeric ranges, highlight fields из §9.2 Step 8), template для index-паттернов.
- [ ] Настроить миграции Postgres (Alembic) в `apps/api-gateway`: init-контейнер `postgres-migrate` применяет схему приложения на старте; таблицы по §3.1/§6.2/§12.3: пользователи и роли, сессии/сообщения чата, настройки UI и feature flags, задачи ревью (review queue), статусы ingest-job, audit logs, `Decision`/`CurationEvent` (before/after JSON).
- [ ] Создать `infra/minio/init.sh` — через `mc` создать бакеты `kg-raw`, `kg-parsed`, `backups` с политиками доступа и раскладкой ключей по §9.2 (`kg-raw/documents/{doc_id}/original.pdf`, `kg-parsed/documents/{doc_id}/docling.json|document.md|tables/table_*.json`).
- [ ] Реализовать seed-скрипт `infra/seed/seed.py` (Phase 0): загрузка 10 seed-документов + пример графа Neo4j, чтобы Reagraph рендерил sample graph.
- [ ] Обернуть всю инициализацию в `make init-db` и `make seed`, идемпотентные при повторном запуске.

**Критерий приёмки:** после `make up && make init-db && make seed` в Neo4j присутствуют constraints (`SHOW CONSTRAINTS`) и sample-граф; в Qdrant есть коллекция; в OpenSearch есть индекс; в MinIO есть 3 бакета (`kg-raw`, `kg-parsed`, `backups`); повторный вызов `make init-db` не выдаёт ошибок дублирования.

### 2.7 Бэкап и восстановление

- [ ] Реализовать `infra/backup/neo4j_backup.sh` — Neo4j dump (`neo4j-admin database dump neo4j --to-path=...`) в volume/бакет `backups`, с таймстампом в имени.
- [ ] Реализовать `infra/backup/qdrant_backup.sh` — создание Qdrant snapshots через API (`POST /collections/{name}/snapshots`) и выгрузку файлов снапшотов в бакет `backups`.
- [ ] Реализовать `infra/backup/postgres_backup.sh` — `pg_dump` (custom format) базы `kg_app` в бакет `backups`.
- [ ] Реализовать `infra/backup/opensearch_backup.sh` — регистрация snapshot repository (fs/S3-MinIO) и снятие snapshot всех индексов.
- [ ] Реализовать `infra/backup/minio_backup.sh` — репликация/`mc mirror` бакетов `kg-raw` и `kg-parsed` в архивное хранилище/бакет `backups`.
- [ ] Реализовать единый оркестратор `infra/backup/backup_all.sh` (вызывается `make backup`) — последовательный вызов всех пяти скриптов с логом и кодом возврата; ретеншн-политика (удаление бэкапов старше N дней).
- [ ] Реализовать зеркальные restore-скрипты `infra/backup/restore/*.sh` для каждого компонента (Neo4j `neo4j-admin database load`, Qdrant snapshot recovery, `pg_restore`, OpenSearch snapshot restore, `mc mirror` обратно).
- [ ] Настроить Dagster schedule (требует `dagster-daemon`, §2.4) или cron-сервис в prod-профиле для регулярного `backup_all.sh` (например ежедневно), с выгрузкой в MinIO/S3.

**Критерий приёмки:** сценарий disaster recovery проходит end-to-end: `make backup` → удаление всех volumes → `make up` → restore-скрипты → данные (граф, векторы, Postgres-таблицы, файлы MinIO) восстановлены и совпадают по контрольным запросам (число узлов Neo4j, число точек Qdrant, число документов в бакете) с состоянием до бэкапа.

### 2.8 Kubernetes / Helm-чарты для прод

- [ ] Создать umbrella Helm-чарт `infra/helm/science-kg/` с `Chart.yaml`, `values.yaml` (dev/staging/prod overlays через отдельные `values-*.yaml`) и subchart-зависимостями.
- [ ] Написать Helm-темплейты `Deployment` + `Service` для stateless-сервисов (`api-gateway`, `agent-service`, `ingestion-service`, `graph-service`, `search-service`, `extraction-service`, `curation-service`, `frontend`) с параметризованными image tag, replicas, resources, env.
- [ ] Написать `Deployment` для воркера быстрых фоновых задач (RQ/Celery, §1) с `HorizontalPodAutoscaler` (по длине очереди/CPU) и подключением к Redis.
- [ ] Задеплоить Dagster в кластер через официальный dagster Helm-subchart: `dagster-webserver` + `dagster-daemon` + user-code gRPC deployment, с run storage в Postgres и `DAGSTER_HOME`.
- [ ] Написать `StatefulSet` + `PersistentVolumeClaim` + headless `Service` для stateful-компонентов (Neo4j, Qdrant, OpenSearch, Postgres, Redis, MinIO), либо подключить официальные Helm-subcharts (Bitnami/community) как зависимости с закреплёнными версиями.
- [ ] Реализовать `livenessProbe`/`readinessProbe`/`startupProbe` в темплейтах на основе тех же health-endpoints, что и в Compose (§2.5).
- [ ] Настроить `Ingress` (nginx-ingress/traefik) с TLS для frontend и `/api/*`, `HorizontalPodAutoscaler` для api/agent, `PodDisruptionBudget` для критичных сервисов.
- [ ] Вынести конфигурацию в `ConfigMap` (несекретные env) и `Secret` (пароли/ключи) с ссылками через `envFrom`.
- [ ] Реализовать Helm-hook Job для init/миграций (Neo4j constraints, Alembic, создание бакетов MinIO, init коллекций Qdrant/индексов OpenSearch) — аналог init-сервисов §2.6, запускается на `post-install`/`post-upgrade`.
- [ ] Добавить `NetworkPolicy` (изоляция backend-хранилищ от внешнего трафика) и `ResourceQuota`/`LimitRange` на namespace.
- [ ] Реализовать CronJob для бэкапов (§2.7) в кластере, пишущий в S3/MinIO.

**Критерий приёмки:** `helm lint infra/helm/science-kg` проходит без ошибок; `helm template -f values-prod.yaml` рендерит валидные манифесты (`kubeval`/`kubeconform` зелёные); установка в kind/minikube поднимает под'ы всех сервисов (включая worker, dagster-webserver/daemon) в `Running`/`Ready`, health-probes проходят, frontend доступен через Ingress.

### 2.9 Управление секретами в проде

- [ ] Запретить хранение секретов в git и образах: `detect-secrets` в pre-commit (§2.1) + проверка в CI; `.env` в `.gitignore`.
- [ ] Интегрировать external secrets в K8s: `ExternalSecret` (External Secrets Operator) или Sealed Secrets, подтягивающие значения из Vault/cloud secret manager в `Secret`, на которые ссылаются Deployment'ы.
- [ ] Параметризовать в `values-prod.yaml` источники секретов (пути в Vault) вместо plaintext-значений; dev-values допускают inline dev-пароли.
- [ ] Заменить дефолтные dev-креды (`neo4j/password`, `minio/minio123`, `adminadminadmin`, `kg/kg`) на генерируемые сильные секреты в prod; задокументировать ротацию.
- [ ] Управлять auth-секретами RBAC (Phase 9): JWT signing key, OIDC client secret, `LLM_API_KEY`, `LANGSMITH_API_KEY` — только через `Secret`/external secret, без хардкода в образах.
- [ ] Настроить чтение секретов сервисами через env/mounted files (`pydantic-settings`), без хардкода; поддержать `_FILE`-суффикс для секретов из файлов.

**Критерий приёмки:** в prod-манифестах нет ни одного plaintext-секрета (проверяется `helm template | grep`-скриптом и CI-джобой); под'ы стартуют, получив секреты из внешнего провайдера; смена секрета в Vault + rollout обновляет значение в под'ах.

### 2.10 CI/CD

- [ ] Настроить CI-пайплайн (`.github/workflows/ci.yml` или аналог): job'ы `lint` (ruff/mypy/eslint), `test` (pytest + frontend-тесты), `build` (docker build всех образов), `compose-smoke` (поднять стек, дождаться health, дёрнуть `/api/v1/admin/health` и упасть при не-200).
- [ ] Настроить сборку и публикацию образов в container registry с тегами по git SHA и semver; кэш слоёв (buildx cache).
- [ ] Настроить CD-пайплайн: `helm upgrade --install` в staging на merge в main, ручной approve для prod (blue-green/rolling).
- [ ] Добавить job проверки инфраструктурных манифестов: `docker compose config`, `helm lint`, `kubeconform`, hadolint для Dockerfile, trivy-скан образов на уязвимости.
- [ ] Настроить зависимость выката от прохождения init/migrations (Helm-hook Job должен завершиться успешно до маршрутизации трафика).
- [ ] Добавить CI-джобу `dr-test` (Phase 9): на ephemeral-стеке прогнать `backup_all.sh` → wipe volumes → restore-скрипты → сверить контрольные метрики (интеграционная проверка бэкапа/восстановления §2.7).

**Критерий приёмки:** PR не мёржится без зелёных `lint`/`test`/`build`/`compose-smoke`; успешный merge публикует образы с корректными тегами и деплоит в staging; `trivy`/`hadolint`-джобы фейлят пайплайн на критичных находках; `dr-test` проходит на ephemeral-стеке.

### 2.11 Observability-инфраструктура

- [ ] Добавить в стек (профиль `observability`) OpenTelemetry Collector, принимающий OTLP от сервисов (`OTEL_EXPORTER_OTLP_ENDPOINT`), с экспортом в трейс/метрик-бэкенд (Jaeger/Tempo + Prometheus).
- [ ] Добавить Prometheus со scrape-конфигом на `/api/v1/admin/metrics` всех backend-сервисов и Grafana с преднастроенными дашбордами (латентность API, длительность ingestion-jobs, состояние Neo4j/Qdrant/OpenSearch).
- [ ] Развернуть MLflow-сервис (`MLFLOW_TRACKING_URI`) с бэкендом Postgres + artifact-store MinIO для eval-метрик (зависимость от раздела eval/§13.2 `mlflow`).
- [ ] Интегрировать просмотр трейсов агента (Phase 9 «add LangGraph trace viewer integration», §15.3): LangSmith (`LANGCHAIN_TRACING_V2`/`LANGSMITH_API_KEY`) ИЛИ LangGraph-трейсы через OTLP в общий трейс-бэкенд; env-driven, отключаемо.
- [ ] Настроить централизованный сбор логов (structlog JSON → Loki/агрегатор) и связку trace_id↔log.
- [ ] Прокинуть все observability-компоненты в Helm-чарт как опциональные (`values` флаги enable/disable) и в Compose-профиль.

**Критерий приёмки:** при поднятом профиле `observability` трейс запроса `POST /api/v1/graph/query` виден end-to-end (api→agent→neo4j) в трейс-бэкенде; Grafana-дашборд показывает метрики со всех сервисов; MLflow-эксперимент создаётся и доступен по UI; трейс шага агента виден в LangSmith/трейс-вьювере.

### 2.12 Вендоринг OSS-инфраструктурных зависимостей

- [ ] Зафиксировать/вендорить инфраструктурные OSS из §22, потребляемые как образы или плагины: Docling Serve (`https://github.com/docling-project/docling-serve`), Neo4j APOC (`https://github.com/neo4j-contrib/neo4j-apoc-procedures`), Neo4j Graph Data Science (`https://github.com/neo4j/graph-data-science`), Qdrant (`https://github.com/qdrant/qdrant`), OpenSearch (`https://github.com/opensearch-project/OpenSearch`), Dagster (`https://github.com/dagster-io/dagster`), MLflow (`https://github.com/mlflow/mlflow`).
- [ ] Для Phase 8 (governance) добавить деплой DataHub (`https://github.com/datahub-project/datahub`) ИЛИ OpenMetadata (`https://github.com/open-metadata/OpenMetadata`) как отдельный compose-профиль/Helm-subchart `governance` (окончательный выбор — в разделе governance).
- [ ] (Опционально, профиль `fallback-parsers`, митигейшн риска §18) Подготовить fallback-парсеры Marker (`https://github.com/datalab-to/marker`) и/или Unstructured (`https://github.com/Unstructured-IO/unstructured`) как альтернативу Docling при плохом парсинге PDF; не требуются для базового стека.
- [ ] Плагины Neo4j (APOC + GDS) монтировать в volume `neo4j-plugins` и включать через `NEO4J_PLUGINS` без ручного копирования (задокументировать версии, совместимые с `neo4j:2026.05-community`).
- [ ] Закрепить версии всех внешних образов и OSS-плагинов в `infra/versions.env` (single source), чтобы `latest` из §13.1 не приводил к дрейфу (`docling-serve`, `neo4j`, `qdrant`, `opensearch`, `postgres:16`, `redis:7`, `minio`, `dagster`, APOC, GDS).
- [ ] (Опционально, §21) Учесть подключение Superset (дашборды) и Haystack Hayhooks (деплой RAG-пайплайнов) как отдельные опциональные профили; не требуются для MVP.

**Критерий приёмки:** все внешние образы тянутся по зафиксированным dig/tag; Neo4j стартует с активными APOC и GDS (`RETURN apoc.version()`, `RETURN gds.version()` возвращают значения); governance-профиль поднимается опционально и не требуется для базового `docker compose up`.

### 2.13 Документация развёртывания, single-VM демо и operational runbooks (Phase 9)

- [ ] Написать `docs/deployment.md` (или раздел prod в `infra/README.md`): пошаговый прод-деплой через Helm, требования к кластеру, обязательные env/секреты, порядок init/миграций, стратегия rollout/rollback.
- [ ] Описать и проверить single-VM-развёртывание для демо: `docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up` на одной VM — удовлетворяет Phase 9 acceptance «full demo can be run locally or on VM».
- [ ] Реализовать команду `make demo` / demo-профиль: поднять стек + загрузить демонстрационный набор 20–50 документов (§19) + прогнать топовый query flow «что делали по X при Y и эффект на Z», gap scan (missing baseline/unit/equipment) и evidence inspector.
- [ ] Написать DR-runbook (`infra/backup/README.md`): порядок восстановления каждого компонента, контрольные проверки, целевые RTO/RPO, ретеншн-политика.
- [ ] Написать operational runbook: чтение `/api/v1/admin/health` и `/api/v1/admin/metrics`, ротация секретов, масштабирование, разбор частых сбоев (OOM neo4j/opensearch, недоступность docling/dagster, застрявшая очередь worker).

**Критерий приёмки:** по `docs/deployment.md` незнакомый инженер разворачивает прод в kind/на VM без устного сопровождения; `make demo` на чистой VM даёт рабочую систему с графом, ответами с evidence и gap-дашбордом (Phase 9 «full demo can be run locally or on VM»); DR-runbook воспроизводимо восстанавливает стек после полной потери томов.


---


## 3. Доменная онтология и Neo4j knowledge graph

Этот раздел покрывает полную реализацию доменной онтологии (LinkML + Pydantic) и хранилища знаний на Neo4j: все labels (§8.1) и relationships (§8.2), evidence-first модель узлов (§8.3), constraints/indexes/fulltext/vector index (§8.4), плагины APOC и GDS, схему миграций и версионирование схемы, provenance/версии/confidence на узлах и рёбрах, детерминированные ID и `MERGE`-правила (§9.7 = step 6/7 pipeline).

Затрагиваемые пакеты и сервисы (структура §6.1):
- `packages/kg_schema/` — LinkML + Pydantic определения онтологии, source of truth.
- `packages/kg_common/` — общие DTO, config, id-utils, logging.
- `apps/graph-service/` — Cypher templates, graph DTOs, schema validation, `/api/v1/graph/schema`.
- `infra/neo4j/` — конфигурация Neo4j, plugins, конфиги индексов, migration scripts.

OSS для клонирования/вендоринга (§22):
- Neo4j: `https://github.com/neo4j/neo4j` (образ `neo4j:2026.05-community`).
- Neo4j APOC: `https://github.com/neo4j-contrib/neo4j-apoc-procedures`.
- Neo4j Graph Data Science (GDS): `https://github.com/neo4j/graph-data-science`.
- LinkML tooling: `https://github.com/linkml/linkml` (генерация Pydantic/JSON-Schema/docs).
- Neo4j LLM Graph Builder (референс схемы/паттернов, форк по §21): `https://github.com/neo4j-labs/llm-graph-builder`.
- Materials-словари для seed онтологии: MatKG `https://github.com/olivettigroup/MatKG`, pymatgen `https://github.com/materialsproject/pymatgen`, Propnet `https://github.com/materialsintelligence/propnet`, Matscholar `https://github.com/materialsintelligence/matscholar`.
- Materials Project API (catalog IDs для canonical keys §3.8/§7.3): `https://github.com/materialsproject/api`.
- Neo4j GraphQL (опциональный GraphQL-proxy к графу, §6.2 «GraphQL proxy if needed»): `https://github.com/neo4j/graphql`.
- Neo4j migrations runner (michael-simons) — кандидат для механизма миграций §3.15: `https://github.com/michael-simons/neo4j-migrations`.
- Protégé в связке с LinkML для governance онтологии (опционально §21).

Зависимости от других разделов:
- Раздел «Инфраструктура / Docker Compose» (§13.1) — контейнер `neo4j` уже поднят с `NEO4J_AUTH=neo4j/password`, порты `7474/7687`, `NEO4J_PLUGINS='["apoc"]'`.
- Раздел «Ingestion pipeline» (§9) — потребитель `MERGE`-правил и deterministic ID при graph upsert (Step 7).
- Раздел «Retrieval» (§10) — потребитель fulltext/vector/property индексов и graph proximity.
- Раздел «Extraction» (§9.4) — потребитель Pydantic extraction schemas из `kg_schema`.
- Раздел «Metadata/lineage» (§16 Phase 8) — ExtractorRun/GapScanRun как provenance-узлы.

---

### 3.1 Bootstrap пакета `packages/kg_schema` и тулинга онтологии

- [ ] Создать пакет `packages/kg_schema/` с `pyproject.toml`, `src/kg_schema/__init__.py`, `README.md`, каталогами `linkml/`, `generated/`, `enums/`, `tests/`.
- [ ] Добавить зависимости в `pyproject.toml`: `linkml`, `linkml-runtime`, `pydantic>=2`, `pydantic-settings` (согласовать с §13.2).
- [ ] Настроить тулинг качества как в Phase 0: `ruff`, `mypy` (strict для `kg_schema`), `pytest`; добавить `Makefile`/`taskfile` таргеты `schema-gen`, `schema-validate`, `schema-test`.
- [ ] Зафиксировать версии LinkML и генераторов в lock-файле; закоммитить `linkml --version` в CI-лог для воспроизводимости.
- [ ] Создать `packages/kg_schema/linkml/CHANGELOG.md` для истории изменений онтологии.

**Критерий приёмки:** `pip install -e packages/kg_schema` проходит; `python -c "import kg_schema"` без ошибок; `ruff check` и `mypy` по пакету — зелёные.

---

### 3.2 LinkML-схема доменной онтологии (materials / regimes / properties / equipment / experiments)

Реализует §4.2 п.1 (domain schema / ontology-lite) и покрывает все доменные классы из §8.1.

- [x] Создать корневой LinkML-schema файл `packages/kg_schema/linkml/kg_ontology.yaml` с `id`, `name`, `version`, `default_prefix`, `prefixes` (в т.ч. `kg`, `schema`, `qudt`, `linkml`), `default_range: string`.
- [x] Определить общий тип идентификатора: slot `id` (identifier, pattern под deterministic ID §3.8) во всех классах-сущностях.
- [x] Описать LinkML-класс `Material` (slots: `canonical_name`, `name`, `aliases`, `material_class`, `formula`) и подкласс `Alloy` (slots: `alloy_system`, `designation`, `base_element`).
- [x] Описать классы `ChemicalElement` (symbol, atomic_number — засеять из pymatgen periodic table) и `Composition` (slots: список долей элементов, `basis: wt%|at%`).
- [x] Описать классы `ProcessingRegime` (slots: `operation`, `temperature_c`, `time_h`, `atmosphere`, `cooling_rate`), `ProcessingStep` (order, operation), `Parameter` (name, value, unit).
- [x] Описать классы `Property` (slots: `canonical_name`, `symbol`, `property_class`, `default_unit`), `Measurement` (slots из §9.5: `value_raw`, `value`, `unit`, `value_normalized`, `normalized_unit`, `normalization_method`, `condition`, `baseline_value`, `effect_direction`), `Unit` (symbol, dimension, qudt_uri).
- [x] Описать классы `Equipment`, `Method`, `Lab`, `ResearchTeam`, `Person`, `Project`, `Dataset`.
- [x] Описать классы структуры документа/эксперимента: `Document`, `Paper`, `Section`, `Paragraph`, `Table`, `Figure`, `Chunk`, `Experiment`, `Sample`.
- [x] Описать классы знаний/провенанса: `Evidence`, `Claim`, `Finding`, `Gap`, `Contradiction`, `Decision`, `CurationEvent`, а также run-классы `ExtractorRun`, `GapScanRun` (используются в §8.2).
- [x] Определить LinkML-enums: `MaterialClass`, `PropertyClass`, `ProcessingOperation`, `Atmosphere`, `EffectDirection {increase, decrease, no_change}`, `ReviewStatus {pending, accepted, rejected, corrected}`, `SourceType {paragraph, table_cell, figure_caption, metadata, manual}`, `GapType` (все 9 типов из §11.1: `missing_property_value, missing_baseline, missing_processing_parameter, missing_equipment, missing_unit, unverified_claim, contradictory_measurements, low_coverage_material, orphan_entity`), `MatchDecision {auto_merge, review_needed, separate}`.
- [x] Определить enum-ы курирования из §12.3: `CurationAction {accept, reject, correct, merge, split, alias_add, schema_change}` и `CurationTargetType {node, edge, evidence, schema}` (используются в §3.7 моделью `CurationEvent`).
- [x] Свести словарь `GapType` (§11.1) с набором правил gap_analyzer (§7.4 Node 8: `missing_source_span, low_confidence_entity_resolution, conflicting_measurements, unverified_critical_claim`) к единому каноническому enum и задокументировать соответствие §11.1↔§7.4, чтобы gap-скан (§11) и enum не расходились.
- [x] Замапить property-vocabulary и processing-vocabulary на внешние словари (Propnet/Matscholar/MatKG) через `exact_mappings`/`close_mappings` в slot-определениях.
- [x] Указать в каждом slot `range`, `required`, `multivalued`, `description`; для числовых — `minimum_value`/`maximum_value` (например `confidence` в `[0,1]`).
- [x] Прогнать `linkml-lint packages/kg_schema/linkml/kg_ontology.yaml` — 0 ошибок.

**Критерий приёмки:** `linkml-convert`/`gen-json-schema packages/kg_schema/linkml/kg_ontology.yaml` завершается без ошибок; схема содержит все 33 доменных класса из §8.1 плюс `ExtractorRun`/`GapScanRun`; все enum из §11.1 (9 типов `GapType`)/§8.3/§9.6/§12.3 присутствуют; `linkml-lint` — clean.

---

### 3.3 Генерация Pydantic-моделей и доменные extraction schemas

Реализует §6.1 (`kg_schema/ Pydantic + LinkML`) и §9.4 (extraction schemas).

- [ ] Настроить генерацию Pydantic v2 моделей: `gen-pydantic packages/kg_schema/linkml/kg_ontology.yaml > packages/kg_schema/generated/models.py`; закоммитить как generated-артефакт с header «DO NOT EDIT».
- [ ] Настроить генерацию JSON Schema (`gen-json-schema`) в `packages/kg_schema/generated/kg_ontology.schema.json` для валидации на границах API.
- [ ] Реализовать `schema-gen` таргет, который перегенерирует Pydantic+JSONSchema и падает в CI, если generated-файлы разошлись с LinkML (git diff check).
- [ ] Написать ручные Pydantic extraction-модели из §9.4 в `packages/kg_schema/src/kg_schema/extraction.py`: `ProcessingRegimeExtract`, `MeasurementExtract`, `ExperimentExtract` (точно по полям §9.4, `confidence: float = Field(ge=0, le=1)`, обязательное `evidence_text`).
- [ ] Добавить валидатор `no source span → no graph fact`: pydantic-validator, отклоняющий extraction-объект без непустого `evidence_text`.
- [ ] Экспортировать публичный API пакета в `__init__.py`: все node-модели, extraction-модели, enums, id-utils.
- [ ] Добавить unit-тесты round-trip: валидный dict → Pydantic → dict; невалидный (`confidence=1.5`, пустой `evidence_text`) → `ValidationError`.

**Критерий приёмки:** `make schema-gen` идемпотентен (повторный запуск не меняет git-статус); `pytest packages/kg_schema/tests` зелёный; импорт `from kg_schema.extraction import ExperimentExtract` работает; попытка создать `MeasurementExtract(confidence=1.5)` бросает `ValidationError`.

---

### 3.4 Каталог node labels (§8.1)

- [x] Создать `packages/kg_schema/src/kg_schema/labels.py` с `StrEnum NodeLabel`, содержащим ровно все 33 label из §8.1: `Document, Paper, Section, Paragraph, Table, Figure, Chunk, Evidence, Claim, Finding, Experiment, Sample, Material, Alloy, ChemicalElement, Composition, ProcessingRegime, ProcessingStep, Parameter, Equipment, Lab, ResearchTeam, Person, Property, Measurement, Unit, Method, Dataset, Project, Decision, CurationEvent, Gap, Contradiction`.
- [x] Добавить служебные provenance-labels `ExtractorRun` и `GapScanRun` (появляются в §8.2) в отдельный `RunLabel` enum.
- [x] Ввести super-label `:Entity`, применяемый ко всем resolvable-сущностям (`Material, Alloy, Property, Equipment, Lab, Person, ResearchTeam, ProcessingRegime, Method, ChemicalElement`), так как `(:Chunk)-[:MENTIONS]->(:Entity)`, `(:Gap)-[:ABOUT]->(:Entity)` и vector index работают по `:Entity` (§8.2/§8.4). Определить множество `ENTITY_LABELS`.
- [x] Задать таблицу `LABEL_TO_ID_PREFIX` (например `Material→material`, `Experiment→exp`, `Evidence→ev`, `Document→doc`, `Property→property`) для deterministic ID (§3.8).
- [x] Написать тест-консистентность: множество классов LinkML-схемы == множество `NodeLabel` (плюс run-labels), иначе тест падает.

**Критерий приёмки:** `set(NodeLabel) - linkml_classes == set()` и наоборот в тесте; каждый `NodeLabel` имеет запись в `LABEL_TO_ID_PREFIX`; для каждого label из `ENTITY_LABELS` в LinkML есть класс.

---

### 3.5 Каталог relationships (§8.2)

- [x] Создать `packages/kg_schema/src/kg_schema/relationships.py` со `StrEnum RelType`, содержащим все rel-типы из §8.2: `HAS_SECTION, HAS_CHUNK, MENTIONS, FROM_CHUNK, FROM_TABLE, SUPPORTS, EXTRACTED_BY, REPORTS, USES_SAMPLE, HAS_MATERIAL, HAS_COMPOSITION, CONTAINS_ELEMENT, PROCESSED_BY, HAS_STEP, HAS_PARAMETER, USED_EQUIPMENT, PERFORMED_BY, PART_OF, MEMBER_OF, MEASURED, OF_PROPERTY, HAS_UNIT, SUPPORTED_BY, ABOUT_MATERIAL, ABOUT_PROPERTY, ABOUT_REGIME, CONTRADICTS, ABOUT, DETECTED_BY, AFFECTS, CHANGED`.
- [x] Для каждого rel-типа задать сигнатуру `(from_label, rel, to_label)` как декларативную таблицу `EDGE_SCHEMA` (например `(Chunk, MENTIONS, Entity)`, `(Measurement, OF_PROPERTY, Property)`, `(Claim, CONTRADICTS, Claim)`).
- [x] Пометить симметричность/направленность (например `CONTRADICTS` — логически симметричный, хранить как один направленный edge + правило чтения обоих направлений).
- [x] Разрешить расхождение источника `MEASURED`: §8.2 определяет `(:Experiment)-[:MEASURED]->(:Measurement)`, а шаблоны запросов/gap (§7.4/§11.2) обходят `(:Sample)-[:MEASURED]->(:Measurement)`. Зафиксировать в `EDGE_SCHEMA` каноническую сигнатуру (и, при необходимости, дополнительное ребро `Sample→MEASURED`), чтобы upsert (§3.8), read-шаблоны (§3.16) и gap-скан (§11) были консистентны; задокументировать выбор в `docs/graph_model.md`.
- [x] Определить обязательные свойства рёбер (provenance §3.7): `confidence`, `extractor_run_id`, `created_at`, `schema_version`, где применимо.
- [x] Написать тест: все `from_label`/`to_label` в `EDGE_SCHEMA` присутствуют в `NodeLabel`/`ENTITY_LABELS`; каждый `RelType` встречается в `EDGE_SCHEMA` минимум один раз.

**Критерий приёмки:** тест валидности `EDGE_SCHEMA` зелёный; `set(RelType)` покрывает все рёбра из §8.2 без пропусков и лишних; utility `is_valid_edge(from_label, rel, to_label)` возвращает `True` для всех строк §8.2 и `False` для не описанных комбинаций.

---

### 3.6 Evidence-first модель узлов (§8.3)

Реализует §4.2 п.2 и §17 п.1 (evidence-first graph).

- [x] Определить LinkML/Pydantic класс `Evidence` строго по §8.3 со slots: `id (ev:uuid)`, `source_type (enum SourceType)`, `doc_id`, `page`, `table_id`, `row_index`, `col_index`, `char_start`, `char_end`, `text`, `extractor`, `model`, `confidence (0..1)`, `created_at`, `reviewed_by (nullable)`, `review_status (enum ReviewStatus, default pending)`.
- [x] Реализовать инвариант «no source span → no graph fact»: любой factual node/edge (Measurement, Claim, факт-ребро) должен иметь минимум один `SUPPORTED_BY`/`SUPPORTS` линк на `Evidence`; написать Cypher-валидатор, находящий нарушителей.
- [x] Реализовать привязки evidence из §8.2: `(:Evidence)-[:FROM_CHUNK]->(:Chunk)`, `(:Evidence)-[:FROM_TABLE]->(:Table)`, `(:Evidence)-[:SUPPORTS]->(:Claim)`, `(:Evidence)-[:EXTRACTED_BY]->(:ExtractorRun)`, `(:Measurement)-[:SUPPORTED_BY]->(:Evidence)`, `(:Claim)-[:SUPPORTED_BY]->(:Evidence)`.
- [x] Реализовать `evidence_locator` DTO в `kg_common`, однозначно указывающий на span (doc_id + page + char_start/char_end или table_id + row/col) для Evidence Inspector (§5.2.6) и endpoint `GET /api/v1/evidence/{evidence_id}`.
- [x] Добавить property на Evidence `review_status` с индексом (см. §3.11) для review queue (§12).
- [x] Написать тесты: создание Measurement без Evidence отклоняется upsert-слоем; Evidence с `table_cell` требует `table_id/row_index/col_index`; Evidence с `paragraph` требует `char_start<char_end`.

**Критерий приёмки:** Cypher-запрос «`MATCH (m:Measurement) WHERE NOT (m)-[:SUPPORTED_BY]->(:Evidence) RETURN count(m)`» возвращает `0` на валидном графе; все поля §8.3 присутствуют в модели `Evidence`; локатор восстанавливает исходный span в тесте.

---

### 3.7 Provenance, версионирование и confidence на узлах и рёбрах

Реализует §1 (evidence graph: источник, confidence, extractor/model version, review status) и §17 п.8 (versioned decisions).

- [x] Определить обязательный provenance-mixin для всех factual узлов и рёбер: `created_at`, `updated_at`, `created_by`, `extractor`, `model`, `extractor_run_id`, `confidence (0..1)`, `review_status`, `schema_version`, `source_doc_ids`.
- [x] Реализовать модель `ExtractorRun` (id, extractor_name, model, version, params_hash, started_at, finished_at, input_doc_ids, code_git_sha) и связь `(:Evidence)-[:EXTRACTED_BY]->(:ExtractorRun)`.
- [x] Реализовать модель `GapScanRun` (id, `gap_rules`/scan_type, params_hash, started_at, finished_at, input_scope/target_properties, code_git_sha) и связь `(:Gap)-[:DETECTED_BY]->(:GapScanRun)` (§8.2) как provenance для gap-нод (§16 Phase 8).
- [x] Реализовать версионирование фактов «preserve previous versions» (§9.7): при изменении reviewed/factual свойств не перезаписывать, а создавать версию — паттерн `version: int` + `valid_from/valid_to` + `superseded_by` (или history-узлы `:FactVersion`), выбрать один и задокументировать в `packages/kg_schema/docs/versioning.md`.
- [x] Реализовать инвариант «never overwrite reviewed fields automatically» (§9.7): upsert-слой блокирует автозапись в поля, где `review_status IN [accepted, corrected]`, если не передан `force_curation=true` с `curation_event_id`.
- [x] Реализовать модели curation-провенанса: `Decision` и `CurationEvent` строго по §12.3 (`id`, `action: CurationAction`, `actor_id`, `target_type: CurationTargetType`, `target_id`, `before: json`, `after: json`, `reason`, `created_at`) и рёбра `(:Decision)-[:AFFECTS]->(:Entity)`, `(:CurationEvent)-[:CHANGED]->(:Entity)` для decision history (§12.3) и merge/split history в Entity Detail (§5.2.4).
- [x] Ввести edge-level provenance: у factual рёбер (`MEASURED`, `SUPPORTED_BY`, `ABOUT_*`, `PROCESSED_BY`, `MENTIONS`) хранить `confidence`, `extractor_run_id`, `created_at`, `schema_version`.
- [x] Хранить на factual-рёбрах массив `evidence_ids` (id связанных `Evidence`), чтобы обслуживать `GET /api/v1/evidence/by-edge/{edge_id}` (§6.2) и заполнять `GraphEdge.evidenceIds`/`evidenceCount` во фронтенд-payload (§5.3); согласовать с `SUPPORTED_BY`/`SUPPORTS` линками §3.6.
- [x] Реализовать confidence-политики: агрегирование confidence при multi-evidence фактах (например max / noisy-OR) как чистую функцию в `kg_common`, покрыть тестами.
- [x] Написать Cypher-репорты provenance-полноты: доля узлов/рёбер без `extractor_run_id`, без `confidence`, без `schema_version`.

**Критерий приёмки:** каждый factual узел и ребро в seed-графе имеет `confidence`, `extractor_run_id`, `schema_version`, `created_at` (Cypher-репорт показывает 100% покрытие); попытка авто-перезаписи `accepted`-поля без `curation_event_id` отклоняется тестом; изменение факта создаёт новую версию, старая остаётся достижима.

---

### 3.8 Детерминированные ID и `MERGE`-правила (§9.7 / pipeline step 6–7)

Реализует upsert rules §9.7: deterministic IDs, `MERGE` by canonical id, store extraction run id.

- [x] Реализовать `packages/kg_common/src/kg_common/ids.py` с чистыми функциями генерации deterministic ID вида `<prefix>:<slug-or-hash>` (например `material:al-cu-2024`, `property:hardness`, `exp:<hash>`, `ev:<uuid5>`), совместимо с примерами §6.2/§8.3/§9.6.
- [x] Задать канонические ключи для ID по типам: `Material` — нормализованный canonical_name/alloy designation; `Property` — canonical property vocab; `Equipment/Lab/Person` — normalized name; `ProcessingRegime` — (operation, temperature_c, time_h, atmosphere) хеш; `Measurement`/`Evidence` — `uuid5` от (doc_id, span, extractor_run).
- [x] Реализовать нормализацию строк для ключей (lowercase, unicode NFKC, схлопывание пробелов/дефисов) как единую функцию `canonical_key()`, покрыть тестами на алиасах из §9.6 (`Al-Cu 2024`, `AA2024`, `2024 aluminum alloy` → один candidate_id при merge, но каждый исходный mention сохраняется).
- [x] Реализовать Cypher `MERGE`-шаблоны в `apps/graph-service/cypher/upsert/` по одному на тип узла, использующие `MERGE (n:Label {id:$id}) ON CREATE SET ... ON MATCH SET ...`, с раздельными наборами `ON CREATE` / `ON MATCH` (не трогать reviewed поля на MATCH, §3.7).
- [x] Реализовать `MERGE`-шаблоны рёбер по `EDGE_SCHEMA` (§3.5) с `MERGE`-ключом на паре узлов + типе, установкой `extractor_run_id`, `confidence`, `created_at`.
- [x] Обеспечить идемпотентность upsert: повторный прогон того же extraction-батча не создаёт дубли узлов/рёбер (проверяется counts до/после).
- [x] Интегрировать `store extraction run id`: каждый upsert-вызов принимает `extractor_run_id`, пишет `EXTRACTED_BY`/edge-property.
- [x] Замапить entity-resolution выход §9.6 (`candidate_id`, `decision`) на upsert: `auto_merge` → merge под canonical id; `review_needed` → создать mention-узел + review task; `separate` → отдельный id. Задокументировать в `docs/merge_rules.md`.
- [x] Реализовать graph-level merge/split сущностей для endpoint-ов `POST /api/v1/entities/merge` и `POST /api/v1/entities/{entity_id}/aliases` (§6.2): перелинковка рёбер на canonical id (например `apoc.refactor.mergeNodes`), дозапись алиасов в `aliases`/`aliases_text` (§3.12), запись `CurationEvent`(action=merge/split/alias_add, §3.7) и сохранение merge/split history (§16 Phase 3 «merge history is preserved», §5.2.4). Не сливать пары, помеченные `separate`.
- [x] (Опц.) Использовать `apoc.merge.node`/`apoc.merge.relationship` там, где label/тип определяется динамически из `NodeLabel`/`EDGE_SCHEMA`, сохраняя раздельные `ON CREATE`/`ON MATCH` семантики и защиту reviewed-полей (§3.7).
- [x] Написать property-based тест детерминизма: одинаковый вход → идентичный id всегда; разный порядок mentions не влияет на id.

**Критерий приёмки:** двойной прогон одного extraction-батча даёт неизменные `count(nodes)`/`count(relationships)` (идемпотентность); `canonical_key("Al-Cu 2024")==canonical_key("AA2024 alloy")` в соответствии с тестовым словарём; каждый upsert-ребро имеет `extractor_run_id`; unit-тесты `ids.py` зелёные.

---

### 3.9 Развёртывание Neo4j и плагины APOC / GDS

Реализует §13.1 и §21 (must-have Neo4j, GDS/APOC).

- [ ] Зафиксировать сервис `neo4j` (образ `neo4j:2026.05-community`, порты `7474/7687`) в `infra/docker-compose.yml` (согласовать с разделом инфраструктуры), env `NEO4J_AUTH=neo4j/password`.
- [ ] Подключить APOC: `NEO4J_PLUGINS='["apoc"]'` (уже в §13.1); при необходимости APOC-extended — примонтировать jar из `neo4j-apoc-procedures` release в `/plugins`.
- [ ] Подключить GDS plugin: добавить `graph-data-science` в `NEO4J_PLUGINS` или примонтировать jar из релиза `neo4j/graph-data-science`, совместимый с версией Neo4j; настроить `dbms.security.procedures.unrestricted=gds.*,apoc.*` и `dbms.security.procedures.allowlist`.
- [ ] Настроить память/лимиты для GDS в `infra/neo4j/neo4j.conf` (`server.memory.heap`, `server.memory.pagecache`, `gds.*` лимиты) под dev-профиль.
- [ ] Настроить persistent volumes для `data/`, `plugins/`, `import/`, `logs/`; добавить healthcheck (bolt `RETURN 1`).
- [ ] Написать smoke-скрипт `infra/neo4j/verify_plugins.cypher`: `RETURN apoc.version()` и `RETURN gds.version()` возвращают версии без ошибок.
- [ ] Задокументировать процедуру бэкапа/восстановления (`neo4j-admin database dump/load`) в `infra/neo4j/README.md`.

**Критерий приёмки:** `docker compose up neo4j` поднимает контейнер, healthcheck green; `CALL apoc.help("apoc")` и `CALL gds.list()` выполняются без ошибок; `RETURN apoc.version(), gds.version()` возвращают непустые версии.

---

### 3.10 Constraints и uniqueness (§8.4)

- [x] Создать миграционный файл `infra/neo4j/migrations/0001_constraints.cypher` со всеми uniqueness-constraints из §8.4: `material_id`, `experiment_id`, `evidence_id`, `document_id`, `property_id`, `equipment_id` (каждый `IF NOT EXISTS ... REQUIRE n.id IS UNIQUE`).
- [x] Расширить constraints на все остальные типы узлов с deterministic id (`Paper, Section, Chunk, Table, Figure, Claim, Finding, Sample, Alloy, Composition, ProcessingRegime, ProcessingStep, Parameter, Lab, ResearchTeam, Person, Measurement, Unit, Method, Dataset, Project, Decision, CurationEvent, Gap, Contradiction, ExtractorRun, GapScanRun`) — `REQUIRE n.id IS UNIQUE`.
- [x] Добавить existence-constraints (Enterprise, опционально/при доступности) или Pydantic-уровень валидацию для обязательных полей: `Evidence.review_status`, `Measurement.value_normalized` при наличии value, `n.schema_version`.
- [x] Реализовать генератор constraints из `NodeLabel` каталога (§3.4), чтобы список не рассинхронизировался с онтологией; сгенерированный `.cypher` — часть миграции.
- [x] Написать тест: попытка создать два узла `:Material {id:"material:x"}` бросает constraint violation.

**Критерий приёмки:** после применения миграции `SHOW CONSTRAINTS` содержит uniqueness-constraint для каждого label из §3.4; вставка дубликата id падает; количество constraints == количеству labels-сущностей.

---

### 3.11 Property / range / composite indexes (§8.4)

- [x] Создать `infra/neo4j/migrations/0002_indexes.cypher` c индексами из §8.4: `measurement_value_index` FOR `(m:Measurement) ON (m.value_normalized)`, `processing_temperature_index` FOR `(r:ProcessingRegime) ON (r.temperature_c)`, `processing_time_index` FOR `(r:ProcessingRegime) ON (r.time_h)`.
- [x] Добавить range-index для числовых фильтров из §6.2/§9.8 запросов: `ProcessingRegime.time_h`, `Measurement.value_normalized`, `Measurement.confidence`.
- [x] Добавить индексы под фильтры review/curation: `Evidence.review_status`, `Gap.type`, `Claim.review_status`, `*.created_at` (для date_from/date_to фильтров §6.2).
- [x] Добавить composite index под ключевой запрос `material_regime_property` (§6.2): например `(:ProcessingRegime) ON (r.operation, r.temperature_c, r.time_h)`.
- [x] Добавить lookup/point индексы под `id`-джойны там, где нет constraint (constraint уже создаёт backing index — не дублировать).
- [x] Задокументировать соответствие «endpoint/запрос → используемый индекс» в `infra/neo4j/docs/index_plan.md`; проверить `PROFILE` ключевого запроса, что используется NodeIndexSeek, а не AllNodesScan.

**Критерий приёмки:** `SHOW INDEXES` содержит все индексы §8.4 + добавленные; `PROFILE` для примера запроса `material_regime_property` (§6.2) показывает index seek без full scan; все индексы в состоянии `ONLINE`.

---

### 3.12 Fulltext index (§8.4)

- [x] Создать в `infra/neo4j/migrations/0003_fulltext.cypher` fulltext-индекс `entity_name_index` FOR `(n:Material|Property|Equipment|Lab|Person|ProcessingRegime) ON EACH [n.name, n.canonical_name, n.aliases_text]` (точно по §8.4).
- [x] Обеспечить наличие поля `aliases_text` (склеенные алиасы) на всех entity-узлах при upsert (§3.8), чтобы fulltext-поиск ловил синонимы из entity resolution (§9.6).
- [x] Реализовать в `apps/graph-service` функцию поиска через `db.index.fulltext.queryNodes('entity_name_index', $q)` для endpoint `GET /api/v1/entities/search?q=&type=&limit=` (§6.2).
- [x] Добавить fulltext-индекс по тексту evidence/claim (`Evidence.text`, `Claim.text`) для keyword-fallback и Evidence Inspector.
- [x] Написать тест: поиск по алиасу `AA2024` находит узел `Material` с canonical `Al-Cu 2024` (после того как alias записан в `aliases_text`).

**Критерий приёмки:** `SHOW INDEXES` показывает `entity_name_index` типа FULLTEXT в состоянии `ONLINE`; `CALL db.index.fulltext.queryNodes('entity_name_index','AA2024')` возвращает ожидаемый Material; поиск через `/api/v1/entities/search` возвращает результат по алиасу.

---

### 3.13 Vector index для node embeddings (§8.4)

- [x] Создать `infra/neo4j/migrations/0004_vector.cypher` с `CREATE VECTOR INDEX entity_embedding_index ... FOR (n:Entity) ON (n.embedding) OPTIONS { indexConfig: { vector.dimensions: 1024, vector.similarity_function: 'cosine' } }` (точно по §8.4).
- [x] Гарантировать, что super-label `:Entity` (§3.4) навешивается на все embeddable-сущности при upsert, иначе индекс не покроет узлы.
- [x] Согласовать размерность `1024` с embedding-моделью раздела retrieval/indexing (§9.8/§10); задокументировать выбранную модель и dim в `infra/neo4j/docs/embeddings.md`; если dim отличается — синхронно обновить миграцию.
- [x] Реализовать батч-джобу записи node embeddings в `n.embedding` (источник — entity descriptions / graph neighborhood summaries §9.8) с идемпотентным upsert по id.
- [x] Реализовать запрос ближайших сущностей `CALL db.index.vector.queryNodes('entity_embedding_index', $k, $vec)` в graph-service для «similar materials/entities» (Mode D §10.1).
- [x] Написать тест: после записи embeddings для 3 материалов vector-query к вектору одного из них возвращает его же первым (self-nearest).

**Критерий приёмки:** `SHOW INDEXES` показывает `entity_embedding_index` типа VECTOR, `ONLINE`, dim=1024, cosine; `db.index.vector.queryNodes` возвращает top-k без ошибок; self-nearest тест проходит.

---

### 3.14 GDS: проекции, node embeddings, community, centrality

Реализует §10.1 Mode D (graph algorithms) и §17 (similar materials, important labs, clusters), §11 (missing links).

- [ ] Реализовать хелперы GDS-projection в `apps/graph-service/gds/`: `gds.graph.project` (или cypher-projection) для подграфов material-property-experiment и для entity-similarity.
- [ ] Реализовать node embeddings через GDS FastRP (`gds.fastRP.write`) или node2vec, записываемые в `n.embedding` (dim=1024) для vector index (§3.13) — согласовать источник embeddings (GDS vs text-model) и зафиксировать выбор.
- [ ] Реализовать community detection (`gds.louvain` / `gds.leiden`) с записью `community_id` на узлы — вход для GraphRAG community summaries (Mode C §10.1) и graph proximity `same community` (§10.3).
- [ ] Реализовать centrality (`gds.pageRank` / `gds.betweenness`) для «important labs/teams» (§17) с записью score-property.
- [ ] Реализовать similarity (`gds.nodeSimilarity` / KNN) для «similar materials» и кандидатов missing-link (§11 contradiction/gap inputs).
- [ ] Обернуть каждую GDS-процедуру как параметризуемый job в graph-service с логированием run-id (provenance §3.7) и очисткой in-memory graph после расчёта.
- [ ] Написать интеграционный тест на seed-графе: louvain даёт ≥1 непустую community; pageRank возвращает конечные значения для всех узлов проекции.

**Критерий приёмки:** `gds.graph.project` создаёт именованный граф; FastRP пишет `embedding` длины 1024 на `:Entity`; louvain пишет `community_id`; pageRank/nodeSimilarity выполняются на seed-графе без ошибок; in-memory графы освобождаются (`gds.graph.list` пуст после job).

---

### 3.15 Схема миграций графа и версионирование схемы

Реализует §17 п.8 и требование «версионируются все извлечения и решения» (§23).

- [ ] Выбрать и внедрить механизм миграций Neo4j (например `neo4j-migrations` от michael-simons или собственный runner) в `infra/neo4j/migrations/`; задокументировать выбор в `infra/neo4j/README.md`.
- [ ] Организовать нумерованные миграции `NNNN_description.cypher` (constraints, indexes, fulltext, vector — из §3.10–3.13) как упорядоченный, идемпотентный набор.
- [ ] Реализовать узел-синглтон `(:SchemaVersion {version, applied_at, checksum, linkml_version})` и обновлять его при каждой применённой миграции; хранить историю применённых миграций (`:AppliedMigration` узлы с checksum).
- [ ] Проставлять `schema_version` на все создаваемые узлы/рёбра (§3.7), значение берётся из текущей `SchemaVersion`.
- [ ] Реализовать команду `migrate up` (применить недостающие) и `migrate status` (показать применённые/ожидающие); интегрировать в CI и в Phase 0 bootstrap.
- [ ] Обеспечить связь версии онтологии `kg_ontology.yaml` (§3.2) и `schema_version` графа: bump онтологии → новая миграция + запись `linkml_version`.
- [ ] Реализовать guard: приложение при старте проверяет, что `SchemaVersion.version` совпадает с ожидаемой, иначе fail-fast с понятной ошибкой.
- [ ] Написать тест миграций на чистой БД: `migrate up` из нуля создаёт все constraints/indexes; повторный `migrate up` — no-op (идемпотентность); `migrate status` показывает 0 pending.

**Критерий приёмки:** на пустом Neo4j `migrate up` создаёт все constraints/indexes (§3.10–3.13) и узел `SchemaVersion`; повторный запуск ничего не меняет; `MATCH (v:SchemaVersion) RETURN v.version` возвращает текущую версию; app fail-fast при mismatch подтверждён тестом.

---

### 3.16 graph-service: schema API, DTO-валидация и graph payload

Реализует §6.1 (`graph-service`: Cypher templates, graph DTOs, schema validation) и endpoint `GET /api/v1/graph/schema` (§6.2).

- [ ] Реализовать в `apps/graph-service` слой graph-DTO, конвертирующий Neo4j-узлы/рёбра в frontend graph payload для Reagraph (§5.3: `nodes[]`, `edges[]` с `type`, `confidence`, `label`).
- [ ] Реализовать в `apps/graph-service/cypher/query/` канонические read-шаблоны (§6.1 «Cypher templates»), в т.ч. `material_regime_property` (§7.4), используя ТОЛЬКО рёбра §8.2; отреконсилить пример §7.4 (`USED_IN`/`HAS_SAMPLE`, `(:Sample)-[:MEASURED]->`) с каноническим `EDGE_SCHEMA` (§3.5), т.к. этих типов нет в §8.2. Выполнять read только в readonly-транзакции с `LIMIT` и allowlist labels/rel (§7.4/§20).
- [ ] Реализовать graph-traversal endpoint-ы, возвращающие `GraphResponse` (§5.3): `POST /api/v1/graph/query`, `POST /api/v1/graph/expand`, `POST /api/v1/graph/path`, `POST /api/v1/graph/subgraph`, `GET /api/v1/entities/{entity_id}/neighbors?depth=&types=` — traversal-логика может делегироваться в retrieval (§10), но сборка payload и валидация сигнатур (`EDGE_SCHEMA`) — здесь.
- [ ] Обеспечить, что graph-payload builder заполняет полный контракт §5.3 и visual-кодировки §5.2.3: у `GraphNode` — `confidence`, `evidenceCount` (размер узла), `verified` (из `review_status`/lock icon), `missingFields` (hollow node), `properties`; у `GraphEdge` — `type`, `confidence` (opacity), `evidenceCount` (толщина), `inferred` (dashed), `contradicted` (red, из `CONTRADICTS`), `evidenceIds` (§3.7). Замапить `type` на допустимое множество §5.3 (подмножество `NodeLabel`)/`RelType`.
- [ ] Реализовать `GET /api/v1/graph/schema`: отдаёт машиночитаемое описание labels (§8.1), relationships (§8.2 с сигнатурами из `EDGE_SCHEMA`), enum и версию схемы (`SchemaVersion`) — источник берётся из `kg_schema`, не хардкодится.
- [ ] Реализовать валидацию входящих upsert-DTO против `kg_schema` (Pydantic/JSON Schema §3.3) перед записью в граф; отклонять невалидные payload с 422.
- [ ] Реализовать проверку соответствия рёбер `EDGE_SCHEMA` (§3.5) на уровне сервиса: запрет создания ребра с неописанной сигнатурой `(from,rel,to)`.
- [ ] Обеспечить единый source of truth: labels/rels/enums для graph-service, extraction-service и frontend `/graph/schema` берутся из `packages/kg_schema` (без дублирования констант).
- [ ] Написать контрактные тесты: ответ `/api/v1/graph/schema` содержит все 33 label и все rel-типы §8.2; невалидный edge отклоняется; graph payload проходит JSON-schema фронтенда (§5.3).

**Критерий приёмки:** `GET /api/v1/graph/schema` возвращает полный список labels/relationships/enums, совпадающий с `kg_schema` (контрактный тест); попытка upsert ребра с неописанной сигнатурой возвращает ошибку; graph payload валиден против фронтенд-контракта §5.3 и заполняет visual-encoding поля §5.2.3 (`verified`/`missingFields`/`inferred`/`contradicted`/`evidenceIds`); read-шаблон `material_regime_property` использует только рёбра §8.2 (тест против allowlist).

---

### 3.17 Seed-граф, bootstrap-скрипт и end-to-end smoke-тесты

Реализует Phase 0 задачи «create initial graph labels/relations», «create example seed script», acceptance «Neo4j has sample graph».

- [x] Написать seed-скрипт `infra/neo4j/seed/seed_graph.py`, создающий репрезентативный мини-граф (пример из §6.2: `Material Al-Cu 2024` → `ProcessingRegime aging 180°C 2h` → `Measurement Vickers hardness 148 HV` c `Evidence`, `Experiment`, `Paper`, `Lab`, `Gap missing_baseline`).
- [x] Использовать в seed именно deterministic ID и `MERGE`-шаблоны (§3.8), чтобы seed был идемпотентен и служил тестом upsert-слоя.
- [x] Проставить в seed полный provenance (`confidence`, `extractor_run_id`, `schema_version`, `review_status`) и связать `Evidence` (evidence-first §3.6).
- [x] Добавить в seed примеры `Gap`, `Contradiction`, `Claim CONTRADICTS Claim` для проверки §11/§17 узлов.
- [x] Засеять контролируемые словари как canonical-узлы: `Property`/`Method`/`ProcessingOperation` из Propnet/Matscholar/MatKG (с mappings §3.2) и `ChemicalElement` из pymatgen periodic table — общий словарь для extraction (§9.4) и entity resolution (§9.6/Phase 3 «build property vocabulary»), с deterministic ID (§3.8).
- [x] Написать e2e smoke-тест: применить миграции → seed → выполнить canonical запрос `material_regime_property` (§6.2) и убедиться, что возвращается measurement с evidence_ids; убедиться, что fulltext находит материал по алиасу, а vector-index работает после записи embeddings.
- [x] Интегрировать применение миграций + seed + smoke в CI (GitHub Actions/pytest job), поднимающий Neo4j через docker compose.
- [x] Написать validation-скрипт целостности графа: 0 factual-узлов без Evidence, 0 узлов без `id`, 0 рёбер с невалидной сигнатурой, 0 узлов без `schema_version`.

**Критерий приёмки:** `python infra/neo4j/seed/seed_graph.py` идемпотентен (повторный запуск не меняет counts); e2e smoke-тест зелёный (canonical query возвращает 148 HV с evidence_ids; fulltext по `AA2024` находит материал; vector self-nearest проходит); validation-скрипт возвращает 0 нарушений; Reagraph рендерит seed-граф (Phase 0 acceptance).

---

### 3.18 Документация онтологии и developer guide

- [x] Сгенерировать HTML/Markdown документацию онтологии из LinkML (`gen-doc`) в `packages/kg_schema/docs/` (классы, slots, enums, mappings).
- [x] Написать `docs/graph_model.md`: диаграмма labels/relationships (§8.1/§8.2), правила evidence-first (§8.3), provenance/versioning (§3.7), deterministic ID + MERGE (§3.8).
- [x] Написать `docs/operations.md`: как запускать миграции, seed, GDS-jobs, бэкап/восстановление, проверять плагины.
- [x] Добавить cheat-sheet ключевых Cypher (constraints, fulltext query, vector query, GDS calls) для новых разработчиков.

**Критерий приёмки:** `gen-doc` создаёт документацию без ошибок и покрывает все классы/slots; `docs/graph_model.md` и `docs/operations.md` присутствуют и ссылаются на актуальные пути миграций/скриптов; ссылки/команды в docs проверены запуском.


---


## 4. Векторный и keyword-поиск: Qdrant + OpenSearch

Раздел покрывает полную реализацию поисковой подсистемы: production-grade dense/sparse/multivector-поиск в **Qdrant** и full-text/BM25/faceted-поиск в **OpenSearch**, объединённые в hybrid retrieval по формуле §10.2. Пишутся клиенты-обёртки в `packages/kg_retrievers/`, которые реализуют интерфейс, совместимый с текущим in-process `HybridIndex` (`src/kg/search/index.py`), чтобы заменить встроенный индекс без изменения контрактов API/агента, и добавляется Reindex API.

**Ключевые внешние зависимости и OSS (клонировать / вендорить / брать как образ, git-URL из §22):**
- Qdrant (server + reference): `https://github.com/qdrant/qdrant`, docker-образ `qdrant/qdrant:latest` (порты `6333` REST, `6334` gRPC — см. §13.1).
- OpenSearch (server + reference): `https://github.com/opensearch-project/OpenSearch`, docker-образ `opensearchproject/opensearch:latest` (порт `9200` — см. §13.1).
- Python-клиенты и модели эмбеддингов (§13.2): `qdrant-client`, `opensearch-py`, `fastembed`, `sentence-transformers`, `llama-index-vector-stores-qdrant`.
- Для community summaries (Mode C) — reference Microsoft GraphRAG: `https://github.com/microsoft/graphrag`.

**Зависимости от других разделов:**
- Раздел инфраструктуры/монорепо (структура §6.1, `infra/docker-compose.yml`, `infra/qdrant/`, `infra/opensearch/`) — сервисы Qdrant/OpenSearch должны существовать до интеграции.
- Раздел Neo4j-схемы (§8) — типы узлов/рёбер (`Evidence`, `Measurement`, `Experiment`, `Material`, `Property`, `Chunk`, `Table`, `Claim`) и id-конвенции (`material:*`, `property:*`, `chunk:*`, `ev:*`).
- Раздел ingestion/indexing pipeline (§9, Step 8 indexing) — источник chunks/claims/table rows/entity descriptions/community summaries и payload-схемы (в задании обозначена как §9.8; в дизайне это payload-схема в §9.2 Step 8).
- Раздел agent/API (§6.2, §7.5 Node 6 `hybrid_retrieval`) — потребители поиска: endpoints `/api/v1/search/*`, agent tool `hybrid_search`.

---

### 4.1 Инфраструктура: сервисы Qdrant и OpenSearch, конфиг, health-checks

- [x] Добавить в `infra/docker-compose.yml` (или корневой `docker-compose.yml`) сервис `qdrant` (образ `qdrant/qdrant:latest`, порты `6333:6333`, `6334:6334`, volume `./data/qdrant:/qdrant/storage`) согласно §13.1.
- [x] Добавить сервис `opensearch` (образ `opensearchproject/opensearch:latest`, порт `9200:9200`, env `discovery.type=single-node`, `plugins.security.disabled=true`, `OPENSEARCH_INITIAL_ADMIN_PASSWORD`, volume `./data/opensearch:/usr/share/opensearch/data`) согласно §13.1.
- [x] Прописать `depends_on: [qdrant, opensearch]` у сервисов `api`, `agent`, `search-service` (если выделяется `apps/search-service/` по §6.1).
- [x] Расширить `src/kg/config.py` (`Settings`) полями: `qdrant_url` (default `http://localhost:6333`), `qdrant_grpc_port`, `qdrant_api_key`, `opensearch_url` (default `http://localhost:9200`), `opensearch_user`, `opensearch_password`, `search_backend` (enum `inprocess|qdrant_opensearch`, default `inprocess`), `embedding_model_dense`, `embedding_model_sparse`, `embedding_model_multivector`, `reranker_model`, `reranker_enabled` (bool).
- [x] Добавить в `Settings` поля управления fusion/деградацией: `opensearch_enabled` (bool, default `true`; при `false` — Qdrant-only режим для MVP согласно §18 «disable OpenSearch for MVP if needed»), `search_fusion_mode` (enum `weighted|rrf|qdrant_native_rrf`, default `weighted`), `rrf_k` (int, default `60`), `rerank_top_n` (int, default `50` — top-N для cross-encoder по §10.2), плюс веса `fusion_weights` (dense/sparse/bm25/graph_proximity/evidence_quality из §10.2).
- [x] Определить размещение сервиса поиска по §6.1/§3: зафиксировать в docstring/README, что обёртки живут в `packages/kg_retrievers/` и импортируются in-process сервисами `api`/`agent`; опциональный тонкий микросервис `apps/search-service/` (диаграмма §3 «Search Service») лишь экспонирует `kg_retrievers` через HTTP — выбрать один вариант для MVP и указать его в `docker-compose.yml` (`depends_on`).
- [x] Добавить соответствующие ключи в `.env.example` (без секретов) с комментариями.
- [x] Реализовать в `packages/kg_retrievers/` фабрики клиентов: `get_qdrant_client()` (обёртка над `QdrantClient` из `qdrant-client`) и `get_opensearch_client()` (обёртка над `OpenSearch` из `opensearch-py`), читающие настройки из `Settings`, с ленивой инициализацией и таймаутами.
- [x] Добавить в endpoint `GET /api/v1/admin/health` (§6.2) проверки доступности Qdrant (`GET /healthz` / `client.get_collections()`) и OpenSearch (`GET /_cluster/health`), возвращающие статус `green|yellow|red` по каждому бэкенду.
- [x] Написать Makefile/скрипт `scripts/wait_for_search.py`, который блокирует до готовности обоих сервисов (для CI/интеграционных тестов).

**Критерий приёмки:** `docker compose up qdrant opensearch` поднимает оба сервиса; `GET http://localhost:6333/collections` и `GET http://localhost:9200/_cluster/health` отвечают 200; `GET /api/v1/admin/health` показывает `qdrant: green`, `opensearch: green|yellow`.

---

### 4.2 Пакет `packages/kg_retrievers`: общие DTO и интерфейс `SearchIndex` (совместимость с `HybridIndex`)

- [x] Создать структуру пакета: `packages/kg_retrievers/` с `pyproject.toml`, `kg_retrievers/__init__.py`, подмодулями `qdrant_retriever.py`, `opensearch_retriever.py`, `hybrid.py`, `embeddings.py`, `schemas.py`, `filters.py`, `reindex.py`, `client.py`.
- [x] В `kg_retrievers/schemas.py` объявить `ScoredChunk` (поля `chunk: dict`, `score: float`, `sparse_score: float=0.0`, `dense_score: float=0.0`), 1:1 совместимый с текущим `src/kg/search/index.py::ScoredChunk` (те же имена полей и типы), чтобы потребители не менялись.
- [x] Добавить в `ScoredChunk` дополнительные необязательные поля `bm25_score: float=0.0`, `graph_proximity_score: float=0.0`, `evidence_quality_score: float=0.0`, `rerank_score: float|None=None` с default-значениями, чтобы старый код продолжал работать без них.
- [x] Определить `Protocol` `SearchIndex` с методами, повторяющими текущий контракт `HybridIndex`: `search(query: str, k: int = 10, filters: dict | None = None) -> list[ScoredChunk]`; классметод `build_from_store(store, use_dense: bool = False) -> SearchIndex`.
- [x] Задокументировать семантику `filters` в точности как в текущем `HybridIndex._passes_filters` (набор-пересечение по ключам `material_ids`/`property_ids`/`source_type`/… — совпадение хотя бы по одному значению), чтобы поведение фильтрации не изменилось при замене бэкенда.
- [x] Реализовать модель запроса `SearchQuery` (поля: `query`, `k`, `filters`, `mode: dense|sparse|bm25|hybrid|qdrant_native_rrf|entity|community`, `numeric_ranges`, `facets`, `highlight: bool`, `min_confidence`, `verified_only`, `date_from`/`date_to`) — единый DTO для Qdrant/OpenSearch/hybrid; режимы `entity`/`community` обслуживают поиск по `entity_descriptions`/`community_summaries` (см. §4.5, §7.2 route GRAG / §7.3 entity_resolver).
- [x] В структуре `filters` предусмотреть ВСЕ фасетные ключи из §7.5 Node 6 и §5.2.1/§5.2.5: `material_ids`, `property_ids`, `entity_ids`, `source_type`, `review_status`, `processing_operation`, `doc_id`, а также `lab_ids` (явно требуется §7.5 «payload filters: material, property, lab, date, source type»), `equipment_ids`, `atmosphere` — с той же set-семантикой пересечения, что `_passes_filters`.
- [x] Реализовать модель ответа `SearchResult` (список `ScoredChunk`, `facets: dict`, `aggregations: dict`, `total: int`, `took_ms: int`) для endpoint-ов `/search/*`.
- [x] Обеспечить экспорт публичного API пакета из `kg_retrievers/__init__.py` (`QdrantRetriever`, `OpenSearchRetriever`, `HybridRetriever`, `ScoredChunk`, `SearchQuery`, `SearchResult`).

**Критерий приёмки:** `from kg_retrievers import HybridRetriever, ScoredChunk` импортируется; `HybridRetriever` статически удовлетворяет `Protocol SearchIndex` (проверка `isinstance`/mypy); поле-имена `ScoredChunk` идентичны текущим (`chunk`, `score`, `sparse_score`, `dense_score`).

---

### 4.3 Qdrant: коллекции и payload-схема (§9.8 / §9.2 Step 8)

- [ ] Реализовать модуль `kg_retrievers/qdrant_schema.py` c декларативным описанием коллекций: `chunks`, `table_rows`, `claims`, `entity_descriptions`, `graph_neighborhood_summaries`, `community_summaries` (Step 8 indexing).
- [ ] Для каждой коллекции задать `create_collection`-конфиг с именованными векторами (named vectors): `dense` (Cosine, размерность из `embedding_model_dense`), `sparse` (SparseVectorParams), `multivector` (late-interaction / ColBERT, `MultiVectorConfig(comparator=MAX_SIM)`) — включать по конфигу, не все коллекции обязаны иметь multivector.
- [ ] Реализовать идемпотентную функцию `ensure_collections(client, recreate: bool = False)`, создающую отсутствующие коллекции и не трогающую существующие; при `recreate=True` — пересоздание.
- [ ] Реализовать payload-схему для `chunks` строго по §9.2 Step 8: `doc_id`, `chunk_id`, `evidence_id`, `entity_ids: list`, `material_ids: list`, `property_ids: list`, `processing_operation`, `temperature_c`, `time_h`, `source_type`, `confidence`, `review_status`; расширить полями из §9.2 Step 3 chunking: `section_path`, `page_start`, `page_end`, `chunk_type`, `tokens`, а также `published_date` для date-фильтров.
- [ ] Добавить в payload `chunks`/`table_rows` фасетные поля `lab_ids: list` (обязательно по §7.5 Node 6 payload filters), `equipment_ids: list` и `atmosphere` (фильтры Experiment Explorer §5.2.5 и quick-filters §5.2.1) — заполнять из графа (Lab/Equipment/ProcessingRegime.atmosphere) при индексации.
- [ ] Реализовать payload-схемы остальных коллекций: `table_rows` (доп. `table_id`, `row_index`, `column_headers`, numeric-ячейки), `claims` (`claim_id`, `about_material_ids`, `about_property_ids`, `about_regime_ids`, `verified`), `entity_descriptions` (`entity_id`, `entity_type`, `name`, `aliases`), `community_summaries` (`community_id`, `level`, `title`, `member_entity_ids`).
- [ ] Реализовать payload-схему коллекции `graph_neighborhood_summaries` (§9.2 Step 8): `center_entity_id`, `entity_type`, `neighbor_entity_ids: list`, `hop`/`level`, `summary_text` — чтобы Mode B/GRAG мог искать по сводкам окрестностей узлов.
- [ ] Для numeric-ячеек `table_rows`/measurement-полей индексировать нормализованные значения из §9.5 (`value_normalized`, `normalized_unit`) — чтобы numeric range-фильтры работали в единых единицах (HV/MPa/GPa/°C/h), а не по сырым строкам.
- [ ] Зафиксировать решение по хранению эмбеддингов сущностей: node/entity-эмбеддинги живут в Qdrant-коллекции `entity_descriptions` (единый vector store), а Neo4j vector index (§8.4) для MVP не используется — отметить это в docstring модуля.
- [ ] Создать payload-индексы (payload indexes) в Qdrant по всем фильтруемым полям: `keyword`-индексы (`doc_id`, `material_ids`, `property_ids`, `entity_ids`, `lab_ids`, `equipment_ids`, `atmosphere`, `source_type`, `review_status`, `processing_operation`), `integer`/`float`-индексы (`temperature_c`, `time_h`, `confidence`, `tokens`, `page_start`), `datetime`-индекс (`published_date`) — для быстрой pre-filtered search.
- [ ] Реализовать Pydantic-валидацию payload перед upsert (тип-чек и приведение единиц: `temperature_c` число, `time_h` число), отбрасывать/логировать невалидные точки.
- [ ] Задать стабильную схему point id: детерминированный UUID из `chunk_id`/`claim_id`/… (uuid5) — чтобы reindex был идемпотентным (upsert перезаписывает точку с тем же id).
- [ ] Написать unit-тест `tests/test_qdrant_schema.py`, проверяющий: коллекции создаются со всеми named vectors; payload-индексы присутствуют; повторный `ensure_collections` не падает и не дублирует.

**Критерий приёмки:** после `ensure_collections` `client.get_collection("chunks")` показывает named vectors `dense/sparse/multivector` и payload-индексы по `material_ids`, `property_ids`, `temperature_c`, `review_status`; upsert одной точки и повторный upsert с тем же `chunk_id` дают одну точку (idempotent).

---

### 4.4 Эмбеддинги: dense / sparse / multivector

- [ ] Реализовать `kg_retrievers/embeddings.py`: обёртка `Embedder` над `fastembed` с ленивой загрузкой моделей и кешированием (`functools.lru_cache` по имени модели).
- [ ] Реализовать `embed_dense(texts) -> list[list[float]]` (dense модель из `embedding_model_dense`, напр. `BAAI/bge-small-en-v1.5`), с батчингом и нормализацией.
- [ ] Реализовать `embed_sparse(texts) -> list[SparseEmbedding]` через `fastembed` sparse-модель (BM25/SPLADE, напр. `Qdrant/bm25` или `prithivida/Splade_PP_en_v1`), возвращая `indices`/`values` для Qdrant `SparseVector`.
- [ ] Реализовать `embed_multivector(texts) -> list[list[list[float]]]` через late-interaction модель (напр. `colbert-ir/colbertv2.0` из `fastembed`) для multivector-коллекций; включать по конфигу.
- [ ] Обеспечить единый интерфейс `embed_query(text)` / `embed_documents(texts)` для каждого типа вектора и переиспользовать существующую dense-логику `HybridIndex._maybe_build_dense` (сохранить graceful-fallback: если модель не грузится — dense/sparse отключаются, но пакет не падает).
- [ ] Зафиксировать размерности и имена моделей в конфиге и провалидировать соответствие размерности dense-вектора конфигу коллекции при старте (ошибка при рассогласовании).
- [ ] Написать тест `tests/test_embeddings.py`: dense-вектор нужной размерности; sparse-вектор непустой для текста с токенами; multivector — список векторов; кеш моделей не перезагружает при повторном вызове.

**Критерий приёмки:** `Embedder.embed_dense(["Al-Cu hardness"])` возвращает вектор размерности, равной конфигу коллекции `chunks.dense`; `embed_sparse` возвращает ненулевые `indices/values`; при отсутствии модели вызовы не бросают исключение, а возвращают пустой/None результат с логом.

---

### 4.5 Клиент-обёртка `QdrantRetriever` (upsert, dense/sparse/multivector search, фильтры)

- [ ] Реализовать `kg_retrievers/qdrant_retriever.py::QdrantRetriever(client, collection, embedder)` c методами `upsert_chunks`, `upsert_points`, `delete_by_doc`, `search`, `count`.
- [ ] Реализовать `upsert_points(points)` с батч-upsert (`client.upsert`, `wait=True`, батчи ≤256), заполняющий named vectors `dense`/`sparse` (и `multivector` при наличии) и payload по схеме §4.3.
- [ ] Реализовать `delete_by_doc(doc_id)` через `FilterSelector` по payload `doc_id` (для reindex одного документа).
- [ ] Реализовать `filters.py::build_qdrant_filter(filters, numeric_ranges, min_confidence, verified_only, date_from, date_to)`, транслирующий:
  - [ ] `material_ids`/`property_ids`/`entity_ids`/`lab_ids`/`equipment_ids`/`atmosphere`/`source_type`/`review_status`/`processing_operation` → `FieldCondition(MatchAny)` (семантика пересечения множеств, как в текущем `_passes_filters`);
  - [ ] `temperature_c`/`time_h`/`confidence` диапазоны → `Range(gte/lte)`;
  - [ ] `min_confidence` → `Range(gte=…)`; `verified_only=True` → `MatchValue(review_status="verified")`;
  - [ ] `date_from`/`date_to` → `DatetimeRange` по `published_date`.
- [ ] Реализовать `search(query, k, filters=None, mode="dense")`:
  - [ ] dense-режим — `query_points` с dense-вектором и `query_filter`;
  - [ ] sparse-режим — `query_points` с `SparseVector`;
  - [ ] multivector-режим — `query_points` с late-interaction и MAX_SIM;
  - [ ] возвращать `list[ScoredChunk]` с `dense_score`/`sparse_score`, `chunk` = payload точки.
- [ ] Реализовать Qdrant-native гибрид (опционально) через `Prefetch` + `FusionQuery(RRF)` (dense+sparse в одном запросе) и выставить его как режим `mode="qdrant_native_rrf"`.
- [ ] Реализовать `build_from_store(store, use_dense=…)` (классметод для drop-in совместимости): вычитывает `Evidence`-узлы из `GraphStore` тем же способом, что текущий `HybridIndex.build_from_store` (обогащение material/property терминами), эмбеддит и upsert-ит в коллекцию `chunks`.
- [ ] Реализовать `search_entities(name_query, k, entity_type=None)` над коллекцией `entity_descriptions` (dense/sparse по `name`/`aliases`) — vector-lookup имён/описаний сущностей для agent-нод `entity_resolver` (§7.3) и tool-ов `resolve_entities`/`search_material_aliases` (§7.4).
- [ ] Реализовать `community_search(query, level=None, k=…)` над `community_summaries` и `neighborhood_search(query, k=…)` над `graph_neighborhood_summaries` — для GraphRAG-режима «global corpus» (§10.1 Mode C, §7.2 route GRAG); возвращать сводки как `ScoredChunk` (payload = summary).
- [ ] Написать интеграционный тест `tests/test_qdrant_retriever.py` (skip если Qdrant недоступен): upsert 5 точек; dense-поиск с фильтром `material_ids=["material:al-cu"]` возвращает только релевантные; numeric range `temperature_c` фильтрует корректно; `search_entities("AA2024")` находит канонический `material:al-cu-2024`.

**Критерий приёмки:** для сид-набора поиск `QdrantRetriever.search("hardness after aging", k=5, filters={"material_ids":["material:al-cu"]})` возвращает `ScoredChunk` только с этим материалом; отключение фильтра расширяет выдачу; numeric range по `temperature_c=[150,200]` отсекает точки вне диапазона.

---

### 4.6 OpenSearch: index mappings, analyzers, settings

- [ ] Реализовать `kg_retrievers/opensearch_schema.py` с определениями индексов: `kg_chunks`, `kg_table_rows`, `kg_claims`, `kg_entities` (index-per-doctype), либо единый `kg_search` с полем `doc_type` — зафиксировать выбор и обосновать в docstring.
- [ ] Определить `settings`: кастомный analyzer `scientific_text` (lowercase + english stemmer + asciifolding + сохранение химических токенов вроде `Al-Cu`, `AA2024` через word_delimiter_graph с `preserve_original`), плюс `standard`/`keyword` analyzers.
- [ ] Определить `mappings` для `kg_chunks`:
  - [ ] `text` — `type: text`, analyzer `scientific_text`, с subfield `text.keyword` (`type: keyword`) и `text.exact` для точных фраз;
  - [ ] facet-поля — `keyword`: `material_ids`, `property_ids`, `entity_ids`, `lab_ids`, `equipment_ids`, `atmosphere`, `source_type`, `review_status`, `processing_operation`, `doc_id`, `chunk_type`, `section_path` (набор фасетов покрывает фильтры §7.5 Node 6 и §5.2.1/§5.2.5);
  - [ ] numeric-поля: `temperature_c` (float), `time_h` (float), `confidence` (float), `page_start`/`page_end`/`tokens` (integer);
  - [ ] `published_date` — `type: date`;
  - [ ] highlight-поля — задать `term_vector: with_positions_offsets` на `text` для быстрого highlight.
- [ ] Реализовать идемпотентную `ensure_indices(client, recreate=False)` (создать при отсутствии, не трогать существующие; `recreate` пересоздаёт).
- [ ] Задать document `_id` = `chunk_id`/`claim_id`/… для идемпотентного bulk-index.
- [ ] Написать тест `tests/test_opensearch_schema.py`: индекс создаётся; `_mapping` содержит `scientific_text` analyzer, keyword-facet поля и numeric/date-типы.

**Критерий приёмки:** `GET /kg_chunks/_mapping` содержит analyzer `scientific_text`, keyword-поля `material_ids/property_ids/source_type/review_status`, numeric `temperature_c/time_h/confidence`, date `published_date`; повторный `ensure_indices` не падает.

---

### 4.7 Клиент-обёртка `OpenSearchRetriever` (BM25, facets, aggregations, highlight, numeric ranges, search pipelines)

- [ ] Реализовать `kg_retrievers/opensearch_retriever.py::OpenSearchRetriever(client, index)` c методами `bulk_index`, `delete_by_doc`, `search`, `count`.
- [ ] Реализовать `bulk_index(docs)` через `opensearchpy.helpers.bulk` (батчи, `refresh` контролируемый), заполняя все поля mapping из §4.6.
- [ ] Реализовать `delete_by_doc(doc_id)` через `delete_by_query` по `doc_id` (для reindex одного документа).
- [ ] Реализовать `search(query, k, filters, numeric_ranges, facets, highlight)`:
  - [ ] BM25 — `multi_match`/`match` по `text` (analyzer `scientific_text`) с boost точных фраз (`text.exact`);
  - [ ] фильтры — `bool.filter` с `terms` по facet-полям (та же set-семантика, что §4.2);
  - [ ] numeric ranges — `range` по `temperature_c`/`time_h`/`confidence`; `verified_only` → `term review_status=verified`; date — `range` по `published_date`;
  - [ ] highlight — секция `highlight` по `text` (`pre_tags`/`post_tags`, `fragment_size`, `number_of_fragments`), возвращать highlighted-фрагменты в результате;
  - [ ] возвращать `list[ScoredChunk]` (`bm25_score` = `_score`, `chunk` = `_source` + highlight).
- [ ] Реализовать `aggregate(query, facets)`: `terms`-агрегации по facet-полям (`material_ids`, `property_ids`, `source_type`, `review_status`, `processing_operation`, `lab_ids`, `equipment_ids`, `atmosphere` — для UI quick-filters §5.2.1 и Experiment Explorer §5.2.5), `histogram` по `temperature_c`/`time_h`, `stats` по `confidence`, вернуть `aggregations` в `SearchResult`.
- [ ] Реализовать создание и применение OpenSearch **search pipeline** (`PUT /_search/pipeline/kg_hybrid`) с `normalization-processor` (min-max / L2) и `combination`-техникой (arithmetic/geometric mean) — для нормализации/комбинирования, использовать в hybrid-режиме (§4.8).
- [ ] Реализовать `build_from_store(store, use_dense=…)` классметод (drop-in): вычитывает те же `Evidence`-узлы, что текущий `HybridIndex.build_from_store`, и bulk-index-ит в `kg_chunks` с обогащёнными материал/свойство терминами.
- [ ] Написать интеграционный тест `tests/test_opensearch_retriever.py` (skip если OpenSearch недоступен): bulk-index 5 доков; BM25-запрос возвращает по релевантности; facet-агрегация по `material_ids` даёт корректные bucket-ы; highlight возвращает `<em>`-фрагменты; numeric range фильтрует.

**Критерий приёмки:** запрос `OpenSearchRetriever.search("aging hardness", filters={"material_ids":["material:al-cu"]}, highlight=True)` возвращает `ScoredChunk` с `bm25_score>0` и highlighted-фрагментом; `aggregate` по `source_type` возвращает bucket-ы `{table_row: n, paragraph: m}`; numeric range по `time_h` отсекает вне диапазона.

---

### 4.8 Hybrid fusion: RRF / weighted, graph_proximity, evidence_quality, reranking

- [ ] Реализовать `kg_retrievers/hybrid.py::HybridRetriever(qdrant, opensearch, graph_store=None, reranker=None)`.
- [ ] Реализовать weighted-fusion строго по формуле §10.2: `score = 0.35*dense + 0.25*sparse + 0.20*bm25 + 0.10*graph_proximity + 0.10*evidence_quality`; веса вынести в конфиг (`FusionWeights`), значения по умолчанию — из §10.2.
- [ ] Реализовать min-max нормализацию покомпонентных скорингов (`dense`, `sparse`, `bm25`) перед взвешиванием (или через OpenSearch normalization-processor §4.7) — чтобы шкалы были сопоставимы.
- [ ] Реализовать альтернативный режим RRF-fusion (Reciprocal Rank Fusion, `k=60`), совместимый по интерфейсу с текущим `HybridIndex._rrf`; выбор `weighted|rrf` — по конфигу.
- [ ] Реализовать `graph_proximity_score` по §10.3 (`1.0` chunk напрямую поддерживает matched measurement; `0.8` тот же эксперимент; `0.6` тот же material+property; `0.4` тот же документ; `0.2` то же community) — считать через `graph_store`/`GraphStore` по `evidence_id`/`entity_ids` кандидата относительно matched-сущностей запроса; при отсутствии `graph_store` компонента = 0.
- [ ] Реализовать `evidence_quality_score` из payload (`confidence`, `review_status==verified` буст, штраф за отсутствие source span) — нормировать в `[0,1]`.
- [ ] Реализовать `search(query, k, filters=None)`:
  - [ ] параллельно опросить Qdrant (dense+sparse) и OpenSearch (bm25) с общими фильтрами;
  - [ ] объединить кандидатов по стабильному ключу (`chunk_id`);
  - [ ] посчитать fusion-score и вернуть top-k `ScoredChunk` с заполненными покомпонентными полями (`dense_score`, `sparse_score`, `bm25_score`, `graph_proximity_score`, `evidence_quality_score`).
- [ ] Реализовать опциональный cross-encoder reranker (§10.2, §7.5 Node 6) на `sentence-transformers` (напр. `cross-encoder/ms-marco-MiniLM-L-6-v2`): рерэнкить top-50 кандидатов, буст verified evidence, штраф за missing source spans и low-confidence extraction; заполнять `rerank_score`; включать по `reranker_enabled`.
- [ ] Обеспечить graceful degradation: если Qdrant недоступен — падать на BM25-only; если OpenSearch недоступен — на vector-only; если оба недоступны — понятная ошибка 503 на уровне API.
- [ ] Написать тест `tests/test_hybrid_fusion.py`: при известных покомпонентных скорах итоговый `score` равен взвешенной сумме §10.2 (в пределах eps); RRF-режим воспроизводит порядок текущего `HybridIndex._rrf` на общем наборе; reranker меняет порядок верхних кандидатов и заполняет `rerank_score`.

**Критерий приёмки:** для контрольного набора `HybridRetriever.search("Al-Cu hardness after aging 180C")` возвращает верным порядком `ScoredChunk`, где `score` == `0.35*dense+0.25*sparse+0.20*bm25+0.10*graph_proximity+0.10*evidence_quality` (проверка на синтетических скорах); verified-evidence поднимается выше при включённом reranker.

---

### 4.9 Drop-in замена in-process `HybridIndex` на `HybridRetriever`

- [ ] Убедиться, что `HybridRetriever` реализует ровно контракт текущего `src/kg/search/index.py::HybridIndex`: сигнатуры `search(query, k=10, filters=None) -> list[ScoredChunk]` и классметод `build_from_store(store, use_dense=False)` идентичны.
- [ ] Обновить `src/kg/api/deps.py::get_index()` для выбора реализации по `Settings.search_backend`: `inprocess` → текущий `HybridIndex`; `qdrant_opensearch` → `HybridRetriever` из `kg_retrievers` (сохранить singleton-кеширование `_index`).
- [ ] Не менять сигнатуры потребителей: `make_tools(store, index)` (`src/kg/agent/tools.py`, tool `hybrid_search` вызывает `index.search(query, k, filters)`) и `build_agent_graph(store, index)` (`src/kg/agent/graph.py`, node `hybrid_retrieval` в `src/kg/agent/nodes.py`) должны работать без правок логики.
- [ ] Проверить, что agent node `hybrid_retrieval` (`src/kg/agent/nodes.py`, вызывает `tools["hybrid_search"](q, 8, filters)`) получает те же `ScoredChunk`-поля.
- [ ] Добавить в `make_tools` (`src/kg/agent/tools.py`) недостающие tool-ы из §7.4: `vector_search_qdrant` (Qdrant-only, `mode=dense|sparse`) и `keyword_search_opensearch` (OpenSearch BM25-only), с той же сигнатурой `(query, k, filters)` и возвратом `list[ScoredChunk]`; существующий `hybrid_search` не менять. При `search_backend=inprocess` они деградируют на текущий `HybridIndex.search` (совместимая заглушка), чтобы набор tool-ов был стабилен.
- [ ] Убедиться, что `packages/kg_retrievers` доступен как dependency в `pyproject.toml` (workspace/editable install), и `src/kg` может импортировать `kg_retrievers`.
- [ ] Прогнать существующий `tests/test_search.py`, `tests/test_agent_tools.py`, `tests/test_agent_nodes.py`, `tests/test_api.py` против `search_backend=qdrant_opensearch` (с поднятыми контейнерами) — они должны проходить без изменений контрактов.
- [ ] Добавить фикстуру-переключатель бэкенда в `tests/conftest.py` (env `SEARCH_BACKEND`) для параметризации тестов обоими бэкендами.

**Критерий приёмки:** при `SEARCH_BACKEND=qdrant_opensearch` весь существующий набор тестов поиска/агента/API проходит без правок их кода; переключение обратно на `inprocess` тоже зелёное; `deps.get_index()` возвращает корректную реализацию по конфигу.

---

### 4.10 Reindex API и bulk-индексация из ingestion pipeline

- [ ] Реализовать оркестратор `kg_retrievers/reindex.py::reindex_document(doc_id, store)` и `reindex_all(store)`: строит chunks/claims/table rows/entity descriptions/community summaries из графа (§9 Step 8) и синхронно апсертит в Qdrant (`upsert_points`) и OpenSearch (`bulk_index`); перед этим `delete_by_doc(doc_id)` в обоих бэкендах (для консистентности при переиндексации).
- [ ] Реализовать endpoint `POST /api/v1/documents/{doc_id}/reindex` (§6.2) — ставит job переиндексации документа, возвращает `job_id`; выполнение — фоновой задачей.
- [ ] Реализовать admin-endpoint полной переиндексации (напр. `POST /api/v1/admin/reindex` или через `ingest/jobs`) для пересборки всех коллекций/индексов из графа.
- [ ] Встроить индексацию в ingestion pipeline: после `Step 7: graph upsert` вызывать `reindex_document` (hook), чтобы новый документ обновлял индексы (зависимость от раздела §9).
- [ ] Реализовать в `reindex.py` учёт `review_status` (payload обновляется при curation-решениях, §12) — endpoint `POST /api/v1/evidence/{evidence_id}/review` должен триггерить частичное обновление payload (`review_status`) в Qdrant (`set_payload`) и OpenSearch (`update`).
- [ ] Учесть флаг `opensearch_enabled` (§4.1, §18): при `false` `reindex_document`/`reindex_all` пишут только в Qdrant, `/search/keyword` возвращает 501/пустой результат с понятным сообщением, `/search/hybrid` работает в Qdrant-only режиме.
- [ ] Обеспечить консистентность id: point/doc id детерминированы (§4.3, §4.6), reindex идемпотентен (повторный вызов не плодит дубликаты).
- [ ] Реализовать батч-прогресс/лог (structlog) и метрики (кол-во upsert, время) для reindex-джоб; отражать статус в `GET /api/v1/ingest/jobs/{job_id}`.
- [ ] Обновить endpoints `POST /api/v1/search/hybrid|vector|keyword` (`src/kg/api/routers/search.py`) для маршрутизации: `/vector` → Qdrant-only (`mode=dense`+`sparse`), `/keyword` → OpenSearch BM25-only, `/hybrid` → `HybridRetriever` (сейчас все три вызывают один `index.search`; сохранить обратную совместимость формата ответа `{chunk, score, sparse_score, dense_score}` + добавить опциональные `facets`/`highlight`).
- [ ] Написать тест `tests/test_reindex.py`: reindex документа наполняет обе коллекции; повторный reindex не дублирует; `delete_by_doc` очищает старые точки; изменение `review_status` через review-endpoint отражается в payload Qdrant и OpenSearch.

**Критерий приёмки:** `POST /api/v1/documents/{doc_id}/reindex` наполняет Qdrant `chunks` и OpenSearch `kg_chunks` для документа; повторный вызов даёт то же число точек/доков (idempotent); `POST /evidence/{id}/review` меняет `review_status` в обоих бэкендах; `/search/vector` и `/search/keyword` возвращают результаты только соответствующего бэкенда.

---

### 4.11 Тесты, интеграция, наблюдаемость поисковой подсистемы

- [ ] Добавить в `tests/conftest.py` фикстуры-контейнеры (или skip-маркеры) для Qdrant/OpenSearch: пропуск интеграционных тестов, если сервисы недоступны (`pytest.mark.skipif`), запуск в CI с docker-compose.
- [ ] Написать end-to-end тест `tests/test_search_e2e.py`: сид-граф → reindex → `/api/v1/search/hybrid` возвращает ожидаемые chunks с evidence; фильтры `material`/`property`/`temperature_c` работают через API; facets/highlight присутствуют в ответе.
- [ ] Добавить golden-проверку релевантности: набор запрос→ожидаемый top-1 chunk (в `tests/golden/`), считать `Recall@10` для evidence и `MRR` для релевантных экспериментов (§15.2) для hybrid vs bm25-only vs dense-only, зафиксировать порог (hybrid ≥ каждого из одиночных). Разместить harness в `packages/kg_eval/` (§6.1) как шаг `EVAL` из pipeline §9.1.
- [ ] Добавить OpenTelemetry-трейсинг/структурные логи (structlog, §13.2) на границах `QdrantRetriever.search`/`OpenSearchRetriever.search`/`HybridRetriever.search`: latency, число кандидатов, выбранный режим fusion, применённые фильтры.
- [ ] Экспортировать метрики в `GET /api/v1/admin/metrics` (§6.2): p50/p95 latency поиска, размер коллекций Qdrant, число документов OpenSearch, доля запросов с rerank.
- [ ] Задокументировать в `README.md`/`docs/` запуск поисковой подсистемы: поднять контейнеры, `ensure_collections`/`ensure_indices`, `reindex_all`, переключение `SEARCH_BACKEND`.
- [ ] Явно сверить критерии приёмки фаз §16, за которые отвечает раздел: Phase 1 «index chunks in Qdrant and OpenSearch» + «chunks searchable» (upload→reindex→`/search/*` находит chunk с page/source-метаданными) и Phase 4 «implement Qdrant search wrapper / OpenSearch wrapper / RRF/weighted fusion / reranking optional» + «query material X + regime Y + property Z returns experiments, values, evidence and graph» (hybrid-выдача несёт `evidence_id`, кликабельна) — оформить как проверки в E2E-тесте.

**Критерий приёмки:** E2E-тест зелёный на поднятых контейнерах; `Recall@10`/`MRR` hybrid не ниже bm25-only и dense-only на golden-наборе; выполняются acceptance-критерии §16 Phase 1 и Phase 4 для поисковой части; `GET /api/v1/admin/metrics` отдаёт latency и размеры индексов; в логах видны трейсы поиска с параметрами фильтров.


---


## 5. Document ingestion: Docling Serve

Раздел покрывает полный конвейер приёма документов: развёртывание `docling-serve` как отдельного контейнера, вендоринг и изучение OSS-репозиториев (`docling`, `docling-serve`, а также fallback-парсеров `Marker` и `Unstructured`), реализацию Upload API (§6.2, `/api/v1/documents/*` и `/api/v1/ingest/*`), парсинг PDF/DOCX/PPTX/HTML в markdown + structured JSON + таблицы + иерархию + page references + image crops, хранение raw + parsed артефактов в S3/MinIO по путям §9.2 Step 2, structure-aware chunking по §9.2 Step 3 с метаданными чанка, регистрацию источника (§9.2 Step 1), формирование граф-готовых DTO узлов документ-семейства (`Document`/`Paper`/`Section`/`Paragraph`/`Table`/`Figure`/`Chunk`, §8.1/§8.2) и Evidence-якорей (§8.3) как handoff в раздел графа, а также путь ручной корректировки парсинга (§18, «manual table upload»).

Основной сервис-владелец: `apps/ingestion-service/`. Используемые/затрагиваемые пакеты: `packages/kg_common/` (shared DTO, config, logging, S3-клиент), `packages/kg_schema/` (Pydantic-модели документа/чанка/источника/узлов графа). Инфраструктура: `infra/docker-compose.yml`, `infra/dagster/`. API-фасад: `apps/api-gateway/` (проксирование upload/download и job status).

**Зависимости от других разделов:**
- Раздел «Infra / Docker Compose / Phase 0» — поднятые сервисы `minio`, `postgres`, `redis`, `dagster` (§13.1). Данный раздел добавляет только сервис `docling`. Также Phase 0 поставляет seed-корпус (10 документов, §16 Phase 0), который прогоняется через данный конвейер.
- Раздел «Knowledge graph schema / Neo4j upsert» — создание узлов `Document`, `Section`, `Paragraph`, `Table`, `Figure`, `Chunk` (§8.1) и рёбер §8.2 выполняется в разделе графа; данный раздел лишь ПОСТАВЛЯЕТ валидированные DTO этих узлов/рёбер и Evidence-якоря (§8.3) как handoff.
- Раздел «Indexing (Qdrant/OpenSearch)» (§9.2 Step 8) — потребитель эмитированных чанков; данный раздел не индексирует, а публикует чанки в очередь/хендофф с доступным на этапе ingestion подмножеством payload §9.2 Step 8.
- Раздел «Extraction» (§9.2 Step 4) — потребитель чанков и parsed JSON; дозаполняет `extractor/model/confidence` у Evidence и `entity_ids` у чанков.

---

### 5.1 Вендоринг и изучение OSS-репозиториев парсинга

- [x] Создать директорию `vendor/parsing/` и склонировать туда основной парсер `docling`: `git clone https://github.com/docling-project/docling vendor/parsing/docling`. Зафиксировать pinned commit/tag в `vendor/parsing/VERSIONS.md`.
- [x] Склонировать сервер: `git clone https://github.com/docling-project/docling-serve vendor/parsing/docling-serve`. Извлечь из README/`docs` список endpoints, формат request/response, поддерживаемые input-форматы и опции конвертации; законспектировать в `apps/ingestion-service/docs/docling_serve_api.md`.
- [x] Склонировать fallback-парсер `Marker`: `git clone https://github.com/datalab-to/marker vendor/parsing/marker`. Зафиксировать поддерживаемые форматы и лицензию в `vendor/parsing/VERSIONS.md`.
- [x] Склонировать fallback-парсер `Unstructured`: `git clone https://github.com/Unstructured-IO/unstructured vendor/parsing/unstructured`. Зафиксировать поддерживаемые форматы (PDF/DOCX/PPTX/HTML) и лицензию.
- [x] Выгрузить актуальную OpenAPI-спецификацию `docling-serve` (из локально поднятого контейнера `GET /openapi.json` или из репозитория) в `apps/ingestion-service/contracts/docling_serve_openapi.json`; сгенерировать типизированный python-клиент или, минимум, Pydantic-модели request/response из этой спеки.
- [x] Изучить и задокументировать структуру `DoclingDocument` (результат `export_to_dict()`/JSON у vendored `docling`): поля `body`/`texts`/`tables`/`pictures`/`groups`, иерархию страниц, provenance/bbox — это первоисточник для нормализации в §5.7; конспект в `apps/ingestion-service/docs/docling_document_model.md`.
- [x] Составить сравнительную таблицу `apps/ingestion-service/docs/parser_matrix.md`: для каждого парсера (docling / marker / unstructured) — поддерживаемые форматы, наличие структуры/иерархии, наличие таблиц, наличие page refs, наличие image crops, лицензия, режим запуска (HTTP/CLI/lib).
- [x] Зафиксировать в `parser_matrix.md`/`VERSIONS.md` лицензии всех четырёх репозиториев (docling, docling-serve, marker, unstructured) и поддерживаемые docling OCR-движки — для юридической и функциональной прозрачности.

**Критерий приёмки:** все 4 репозитория присутствуют в `vendor/parsing/` с зафиксированными в `VERSIONS.md` commit-хэшами и лицензиями; файл `docling_serve_api.md` описывает реальные (а не выдуманные) endpoints, подтверждённые содержимым `docling_serve_openapi.json`; `docling_document_model.md` описывает реальную структуру export-JSON docling; `parser_matrix.md` заполнен для всех трёх парсеров.

---

### 5.2 Развёртывание docling-serve (контейнер, §13.1)

- [x] Добавить в `infra/docker-compose.yml` сервис `docling` строго по §13.1: `image: quay.io/docling-project/docling-serve:latest`, `ports: ["5001:5001"]`, `environment: DOCLING_SERVE_ENABLE_UI: "1"`. Запинить конкретный тег версии вместо `latest` в `.env`-переменной `DOCLING_SERVE_IMAGE`.
- [x] Прописать сервис `ingestion` (`build: ./apps/ingestion-service`, `ports: ["8020:8020"]`, `env_file: .env`) с `depends_on: [docling, dagster, minio]` согласно §13.1.
- [x] Объявить зависимости `apps/ingestion-service/pyproject.toml` строго по §13.2 и потребностям раздела: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `httpx`, `boto3`/`minio`, `alembic`, `dagster`, `structlog`, `opentelemetry-sdk`, `orjson`, `pandas`/`polars`, токенайзер (`tiktoken`/`transformers`) для подсчёта `tokens` (§5.9).
- [x] Добавить в `docling`-сервис healthcheck (HTTP GET на health-endpoint docling-serve, подтверждённый OpenAPI из 5.1) с `interval`, `timeout`, `retries`; `ingestion` не должен стартовать до `service_healthy`.
- [x] Вынести в `.env`/`.env.example` переменные: `DOCLING_SERVE_URL=http://docling:5001`, `DOCLING_SERVE_IMAGE`, лимиты ресурсов, timeouts. Задокументировать в `apps/ingestion-service/README.md`.
- [x] Смонтировать volume под кэш моделей docling (layout/OCR/table), чтобы контейнер `docling` не перекачивал веса на каждый рестарт; путь кэша вынести в `.env`.
- [x] Настроить (при доступности GPU) вариант образа/переменные для ускорения OCR/layout; по умолчанию — CPU-профиль. Отразить оба профиля в `docker-compose.override.yml`.
- [x] Ограничить ресурсы контейнера `docling` (`deploy.resources.limits` / `mem_limit`) и настроить перезапуск (`restart: unless-stopped`), чтобы OOM на большом PDF не ронял стек.
- [x] Проверить доступность встроенного UI docling-serve на `http://localhost:5001` (флаг `DOCLING_SERVE_ENABLE_UI=1`) после `docker compose up docling`.

**Критерий приёмки:** `docker compose up -d docling ingestion` поднимает оба сервиса; healthcheck `docling` переходит в `healthy`; из контейнера `ingestion` доступен `curl $DOCLING_SERVE_URL/health` (или эквивалент из OpenAPI) с кодом 200; UI docling-serve открывается в браузере.

---

### 5.3 Клиент docling-serve в ingestion-service

- [ ] Создать модуль `apps/ingestion-service/src/parsers/docling_client.py` — async-клиент (httpx.AsyncClient) к `DOCLING_SERVE_URL`, использующий модели из `contracts/docling_serve_openapi.json` (5.1).
- [ ] Реализовать метод submit-конвертации файла/URL (по реальному async-convert endpoint docling-serve) с передачей опций конвертации: `do_ocr`, `do_table_structure`, `image_export_mode`, целевые output-форматы (markdown + structured JSON) — параметры подтвердить по OpenAPI, не выдумывать имена.
- [ ] Реализовать polling-статуса задачи и получение результата (task submit → poll status → fetch result) с exponential backoff и общим `DOCLING_TASK_TIMEOUT`.
- [ ] Реализовать синхронный (single-shot) режим конвертации для малых файлов и async-режим для больших; выбор по размеру файла (порог в конфиге).
- [ ] Добавить retry-политику (transient 5xx / сетевые ошибки) с ограничением попыток и джиттером; неретраибл-ошибки (415 unsupported format, 422) пробрасывать как доменные исключения `UnsupportedFormatError` / `ParseValidationError`.
- [ ] Определить набор поддерживаемых MIME/расширений (`application/pdf`, `.pdf`, `.docx`, `.pptx`, `.html`/`.htm`) в `apps/ingestion-service/src/parsers/formats.py`; отклонять неподдерживаемые до вызова docling.
- [ ] Определять MIME по содержимому (magic bytes, напр. `python-magic`/`filetype`), а не только по расширению; при рассинхроне расширения и реального типа — доверять содержимому и/или отклонять как `UnsupportedFormatError`.
- [ ] Написать unit-тесты клиента на замоканном docling-serve (respx/pytest-httpx): успешный parse, timeout, 5xx-retry, unsupported format.

**Критерий приёмки:** вызов `docling_client.parse(file_bytes, filename="sample.pdf")` в интеграционном тесте против реально поднятого контейнера `docling` возвращает объект с непустыми markdown и structured JSON; unit-тесты клиента зелёные; при подаче `.txt` бросается `UnsupportedFormatError`.

---

### 5.4 Source registration (§9.2 Step 1)

- [ ] В `packages/kg_schema/` определить Pydantic-модель `SourceRegistration` со всеми полями §9.2 Step 1: `source_id`, `file_hash`, `source_type`, `owner`/`lab`, `access_policy`, `ingestion_job_id`, `version`.
- [ ] Создать таблицу Postgres `ingestion.sources` (Alembic-миграция в `apps/ingestion-service/migrations/`) с колонками под все поля модели + `created_at`, `updated_at`, `original_filename`, `mime_type`, `size_bytes`, `s3_raw_uri`.
- [ ] Реализовать вычисление `file_hash` (sha256 контента) и использовать его для дедупликации: при повторной загрузке файла с тем же хэшем — не плодить новый `source_id`, а вернуть существующий (idempotent upload) с флагом `duplicate=true`.
- [ ] Присваивать детерминированный `doc_id`/`source_id` (например `doc:{uuid}` и стабильный id на базе `file_hash`) согласно правилу детерминированных ID (§9.2 Step 7).
- [ ] Реализовать версионирование источника: при повторной загрузке изменённого файла с тем же `original_filename`/логическим ключом — инкремент `version`, сохранение предыдущих версий (не перезаписывать).
- [ ] Реализовать репозиторий `apps/ingestion-service/src/registry/source_repo.py` с методами `register()`, `get_by_id()`, `get_by_hash()`, `bump_version()`; покрыть unit-тестами на тестовой БД.
- [ ] Записывать `access_policy` и `owner`/`lab` из метаданных запроса (или дефолтов) — для последующего governance-раздела.

**Критерий приёмки:** после успешного upload в `ingestion.sources` появляется строка со всеми полями §9.2 Step 1; повторная загрузка идентичного файла не создаёт вторую строку и возвращает `duplicate=true`; загрузка изменённого файла увеличивает `version`, сохраняя предыдущую запись.

---

### 5.5 Object storage layout в S3/MinIO (§9.2 Step 2)

- [ ] Создать бакеты `kg-raw` и `kg-parsed` в MinIO при старте (bootstrap-скрипт `infra/minio/bootstrap.sh` или init-контейнер `mc mb`); сделать операцию идемпотентной.
- [ ] В `packages/kg_common/` реализовать S3-клиент-обёртку (`boto3`/`minio`) с конфигом из `.env` (`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, endpoint `minio:9000`).
- [ ] Реализовать функции построения путей строго по §9.2 Step 2:
  - `s3://kg-raw/documents/{doc_id}/original.{ext}` — исходный файл;
  - `s3://kg-parsed/documents/{doc_id}/docling.json` — structured JSON;
  - `s3://kg-parsed/documents/{doc_id}/document.md` — markdown;
  - `s3://kg-parsed/documents/{doc_id}/tables/table_{NNN}.json` — по одной таблице на файл (нумерация с `001`).
- [ ] Дополнительно определить пути для image crops: `s3://kg-parsed/documents/{doc_id}/images/img_{NNN}.png` (и/или per-figure) и для chunks-манифеста `s3://kg-parsed/documents/{doc_id}/chunks.jsonl`.
- [ ] Определить пути per-page артефактов для endpoint `/pages/{page}` (5.6): `s3://kg-parsed/documents/{doc_id}/pages/page_{NNN}.json` (page-level structured JSON/markdown) и `s3://kg-parsed/documents/{doc_id}/pages/page_{NNN}.png` (preview-рендер страницы).
- [ ] Сохранять документ-манифест `s3://kg-parsed/documents/{doc_id}/manifest.json` c метаданными парсинга (`parser_used`, `ocr_used`, счётчики страниц/секций/таблиц/фигур/картинок, checksum'ы артефактов) — источник для `GET /api/v1/documents/{doc_id}`.
- [ ] Сохранять raw-файл в `kg-raw` ДО вызова docling; сохранять все parsed-артефакты в `kg-parsed` ПОСЛЕ успешного парсинга атомарно (сначала temp-ключ, затем финальный, или запись под версионным префиксом).
- [ ] Проставлять object metadata/теги (`doc_id`, `source_id`, `version`, `content_type`) на каждый загружаемый объект.
- [ ] Реализовать чтение артефактов обратно (`get_parsed_json`, `get_markdown`, `get_table`, `get_page`, `list_images`) для нужд download-endpoints (5.6).

**Критерий приёмки:** после ingestion одного PDF в MinIO присутствуют объекты по всем путям §9.2 (`original.pdf`, `docling.json`, `document.md`, `tables/table_001.json` при наличии таблиц, `images/img_001.png` при наличии картинок, `pages/page_001.json`, `manifest.json`); повторный ingestion того же `doc_id` перезаписывает под контролем версии, не создавая «сирот».

---

### 5.6 Upload API и ingestion jobs (§6.2)

- [ ] Реализовать `POST /api/v1/documents/upload` (multipart file + опциональные метаданные owner/lab/access_policy): валидация формата (5.3), сохранение raw в `kg-raw`, регистрация источника (5.4), создание ingestion job и запуск pipeline (5.10). Ответ: `{doc_id, source_id, job_id, status, duplicate}`.
- [ ] Реализовать `GET /api/v1/documents/{doc_id}` — метаданные документа (source registration + статус парсинга + список доступных артефактов из `manifest.json`).
- [ ] Реализовать `GET /api/v1/documents/{doc_id}/parsed` — отдать structured JSON (`docling.json`) и/или markdown (`document.md`) из `kg-parsed`.
- [ ] Реализовать `GET /api/v1/documents/{doc_id}/pages/{page}` — отдать per-page артефакт (page-level structured JSON/markdown/preview image) для конкретной страницы из `pages/page_{NNN}.*`.
- [ ] Реализовать `POST /api/v1/documents/{doc_id}/reindex` — перезапуск chunking+downstream (без повторного парсинга, если parsed-артефакты есть) с созданием нового job.
- [ ] Реализовать `POST /api/v1/ingest/jobs` — создать job вручную (по существующему `doc_id`/источнику); `GET /api/v1/ingest/jobs/{job_id}` — статус/прогресс/ошибки; `POST /api/v1/ingest/jobs/{job_id}/cancel` — отмена.
- [ ] Реализовать `GET /api/v1/admin/health` (§6.2): агрегированный readiness ingestion-service — доступность `docling` (health по OpenAPI), MinIO, Postgres, Dagster; коды 200/503.
- [ ] Ввести модель статусов job (`queued → parsing → storing → chunking → done | failed | cancelled`) в Postgres-таблице `ingestion.jobs`; endpoint статуса возвращает текущий этап, проценты, `error`-детали.
- [ ] Проксировать эти endpoints через `apps/api-gateway/` (auth/session, rate limit, audit log) к `ingestion-service`, сохранив контракт §6.2.
- [ ] Добавить лимиты размера файла и число одновременных загрузок; при превышении — 413/429 с понятной ошибкой.
- [ ] Написать contract-тесты (pytest + httpx) на все перечисленные endpoints по путям §6.2, включая коды ошибок.

**Критерий приёмки:** `curl -F file=@sample.pdf POST /api/v1/documents/upload` возвращает `job_id`; `GET /api/v1/ingest/jobs/{job_id}` со временем доходит до `done`; `GET /api/v1/documents/{doc_id}/parsed` отдаёт непустой markdown; `GET /api/v1/documents/{doc_id}/pages/1` отдаёт данные страницы 1; `GET /api/v1/admin/health` возвращает 200 при поднятых зависимостях; все endpoint-пути точно совпадают с §6.2.

---

### 5.7 Парсинг PDF/DOCX/PPTX/HTML: полный набор outputs (§9.2 Step 2) и граф-DTO документа (§8.1/§8.2/§8.3)

- [ ] Настроить конвертацию так, чтобы для каждого поддерживаемого формата (PDF, DOCX, PPTX, HTML) docling возвращал все outputs §9.2 Step 2: markdown, structured JSON, tables, document hierarchy, page references, images/crops.
- [ ] Реализовать нормализацию ответа docling в внутренний Pydantic-DTO `ParsedDocument` (`packages/kg_schema/`): поля — `doc_id`, `markdown`, `structured` (raw docling JSON), `sections` (иерархия), `tables[]`, `figures[]`, `images[]`, `page_count`, `page_map`, `meta` (document-level метаданные).
- [ ] Извлекать document-level метаданные (title, authors, DOI/идентификаторы, year, journal — если присутствуют) из docling-вывода в `ParsedDocument.meta`; использовать `source_type` (§5.4) для выбора метки `Document` vs `Paper` (§8.1).
- [ ] Извлекать и сохранять **document hierarchy** (title → sections → subsections → paragraphs) в структурированный вид с `section_path` (например `"Results > Mechanical properties"`, как в §9.2 Step 3) для каждого узла.
- [ ] Извлекать **таблицы** как отдельные объекты (ячейки, заголовки строк/колонок, span, номер страницы) и сериализовать каждую в `tables/table_{NNN}.json`; сохранять маппинг `table_id → page`.
- [ ] Сохранять координаты ячеек таблиц (`row_index`, `col_index`, `table_id`) и `page` для каждой ячейки/строки — обязательные якоря Evidence-модели (§8.3: `table_id`, `row_index`, `col_index`, `page`).
- [ ] Сохранять **page references** для каждого структурного элемента (paragraph/table/figure) — `page_start`/`page_end` и bbox, чтобы поддержать §9.2 Step 3 и Evidence-модель (§8.3 поля `page`, `char_start`, `char_end`).
- [ ] Реализовать экспорт **image crops** (figures/встроенные изображения) через docling `image_export_mode` в `images/img_{NNN}.png`; связать каждый crop с его figure/caption и страницей. Управлять флагом «извлекать картинки» (config `EXTRACT_IMAGES`), т.к. §9.2 указывает «if needed».
- [ ] Извлекать **figure captions** как отдельные текстовые элементы (нужны для chunk_type=caption в §9.2 Step 3).
- [ ] Обрабатывать OCR-ветку для сканированных PDF (`do_ocr=true`), фиксируя в метаданных документа флаг `ocr_used`.
- [ ] Сформировать граф-готовые (валидированные) DTO узлов документ-семейства строго по §8.1: `Document`/`Paper`, `Section`, `Paragraph`, `Table`, `Figure`, `Chunk` — и рёбер по §8.2: `(:Document)-[:HAS_SECTION]->(:Section)`, `(:Section)-[:HAS_CHUNK]->(:Chunk)`, `(:Evidence)-[:FROM_CHUNK]->(:Chunk)`, `(:Evidence)-[:FROM_TABLE]->(:Table)`; ПОСТАВЛЯЕТСЯ как handoff в раздел графа (сами узлы создаёт раздел «KG schema/Neo4j upsert»), а не апсертится здесь.
- [ ] Генерировать Evidence-якоря (стабы §8.3) для каждого структурного элемента-источника: `doc_id`, `page`, `table_id`, `row_index`, `col_index`, `char_start`, `char_end`, `source_type` ∈ {`paragraph`,`table_cell`,`figure_caption`} — без `extractor/model/confidence` (их проставит extraction-раздел), но с корректными span/локацией.
- [ ] Обеспечить, что `doc_id` (и `chunk_id`) детерминированы и уникальны, удовлетворяя constraints §8.4 (`document_id` unique) на стороне графа.
- [ ] Логировать и подсчитывать per-document метрики парсинга: число страниц, секций, таблиц, фигур, картинок; сохранять в `ingestion.jobs`/parsed-манифест (`manifest.json`).

**Критерий приёмки:** для набора из ≥4 тестовых файлов (по одному PDF/DOCX/PPTX/HTML) `ParsedDocument` содержит непустые `markdown`, `sections` (с корректными `section_path`), ≥1 `table` (для файла с таблицей) с page-reference и координатами ячеек, и image crops (для файла с рисунком); граф-DTO `Document/Section/Paragraph/Table/Figure/Chunk` валидны по меткам §8.1 и связям §8.2; для каждой таблицы/абзаца сформированы Evidence-якоря §8.3 с корректными `page`/`table_id`/`row_index`/`col_index`/`char_start`/`char_end`; все артефакты выгружены в `kg-parsed` по путям §5.5.

---

### 5.8 Fallback-парсеры: Marker и Unstructured

- [ ] Определить общий интерфейс `DocumentParser` (protocol) в `apps/ingestion-service/src/parsers/base.py` с методом `parse(file) -> ParsedDocument`, чтобы docling/marker/unstructured были взаимозаменяемы.
- [ ] Реализовать адаптер `MarkerParser` (на базе vendored `marker`) с маппингом его вывода в `ParsedDocument` (markdown + структура + таблицы, насколько поддерживается).
- [ ] Реализовать адаптер `UnstructuredParser` (на базе vendored `unstructured`) с маппингом элементов (`Title`/`NarrativeText`/`Table`/`ListItem`) в `sections`/`tables`/hierarchy `ParsedDocument`.
- [ ] Реализовать fallback-оркестрацию: primary = docling; при неудаче парсинга (ошибка/пустой результат/качество ниже порога) — переключение на marker, затем на unstructured; фиксировать использованный парсер в метаданных документа (`parser_used`).
- [ ] Сделать выбор парсера конфигурируемым per-format (например HTML → unstructured, если docling даёт хуже) через таблицу приоритетов в конфиге.
- [ ] Реализовать путь ручной корректировки парсинга (§18, mitigation «manual table upload»): endpoint/ingestion-хук для загрузки исправленной таблицы/markdown, который замещает соответствующий parsed-артефакт, помечает источник (`parser_used=manual`/`corrected=true`) и сохраняется как новая версия артефакта (не затирая исходный docling-вывод); событие передать в curation/governance-раздел.
- [ ] Добавить тесты, подтверждающие, что при принудительной ошибке docling pipeline завершает документ через fallback-парсер и всё равно производит непустой `ParsedDocument`.

**Критерий приёмки:** при искусственном отключении docling (`DOCLING_SERVE_URL` недоступен) ingestion того же PDF успешно завершается через `MarkerParser`/`UnstructuredParser`, поле `parser_used` в метаданных ≠ `docling`, а markdown непустой; ручная замена таблицы создаёт новую версию parsed-артефакта с `corrected=true`, не удаляя исходный.

---

### 5.9 Structure-aware chunking (§9.2 Step 3)

- [ ] Реализовать модуль `apps/ingestion-service/src/chunking/structure_chunker.py`, который принимает `ParsedDocument` и производит structure-aware чанки (НЕ naive fixed-size), по типам §9.2 Step 3: title/abstract, methods, results, figure captions, table rows, experimental procedure paragraphs, measurement rows.
- [ ] Определить Pydantic-модель `Chunk` в `packages/kg_schema/` строго по §9.2 Step 3: `chunk_id` (`chunk:{uuid}`), `doc_id`, `section_path`, `page_start`, `page_end`, `text`, `chunk_type` ∈ {`paragraph`,`table_row`,`caption`}, `tokens`.
- [ ] Реализовать сегментацию по document hierarchy: каждый параграф/логический блок → чанк `paragraph` с корректным `section_path` из §5.7.
- [ ] Реализовать построчный разбор таблиц: каждая значимая строка таблицы → чанк `table_row` (с сохранением заголовков колонок в тексте для контекста) и ссылкой на `table_id`.
- [ ] Реализовать чанки для подписей рисунков → `chunk_type=caption` с page reference.
- [ ] Подсчитывать `tokens` для каждого чанка реальным токенайзером (совместимым с эмбеддинг/LLM-моделью); задать max-token порог с мягким разбиением слишком длинных параграфов по предложениям без потери `section_path`/page refs.
- [ ] Прокинуть в каждый чанк дополнительные метаданные для downstream (§9.2 Step 8 payload): `source_type` (`paragraph|table_row|caption`), ссылки на `table_id`/`figure_id`, `char_start`/`char_end` внутри исходного текста (для Evidence-модели §8.3).
- [ ] Гарантировать, что эмитируемый payload чанка содержит доступные на этапе ingestion поля §9.2 Step 8 (`doc_id`, `chunk_id`, `source_type`, `page_start`/`page_end`, `section_path`); поля `entity_ids`/`material_ids`/`property_ids`/`confidence`/`review_status` дозаполняет extraction/indexing-раздел.
- [ ] Сериализовать все чанки документа в `kg-parsed/documents/{doc_id}/chunks.jsonl` и вернуть их как результат этапа chunking.
- [ ] Эмитировать чанки в хендофф для downstream-разделов (extraction §9.2 Step 4 и indexing §9.2 Step 8) — публикация в очередь/шину (Redis/Dagster asset), НЕ индексируя их в этом разделе.
- [ ] Написать unit-тесты чанкера на фикстурах: проверить, что для абзаца создаётся `paragraph`-чанк с непустым `section_path`, для строки таблицы — `table_row`, для подписи — `caption`; проверить корректность `page_start/page_end` и `tokens`.

**Критерий приёмки:** для тестового документа `chunks.jsonl` содержит чанки всех трёх `chunk_type`; каждый чанк валиден по Pydantic-схеме §9.2 Step 3 (непустые `chunk_id`, `doc_id`, `section_path`, корректные `page_start ≤ page_end`, `tokens > 0`); ни один чанк не длиннее сконфигурированного max-token порога.

---

### 5.10 Оркестрация ingestion job (Dagster pipeline wiring)

- [ ] В `infra/dagster/` описать Dagster-job/graph `document_ingestion` с ops/assets по этапам §9.1: `register_source` → `store_raw` → `docling_parse` → `store_parsed` → `chunk` → `emit_chunks`.
- [ ] Связать запуск job из `POST /api/v1/documents/upload` и `POST /api/v1/ingest/jobs` (5.6): триггер Dagster-run, проброс `run_id` в `ingestion.jobs.job_id`.
- [ ] Реализовать обновление статуса job на каждом op (запись этапа/прогресса/ошибки в `ingestion.jobs`), чтобы `GET /api/v1/ingest/jobs/{job_id}` отражал реальное состояние.
- [ ] Реализовать отмену (`.../cancel`) через прерывание Dagster-run и перевод job в `cancelled`.
- [ ] Настроить идемпотентность и retry отдельных ops (parse/store) без повторного дублирования артефактов в MinIO.
- [ ] Реализовать batch/bulk-ingestion (Dagster-job или sensor на директорию/бакет) для пакетной загрузки seed-корпуса (Phase 0: 10 seed-документов, §16; §19: 20–50 документов) с тем же per-doc конвейером §9.1 и агрегированным отчётом.
- [ ] Зафиксировать lineage-метаданные ingestion (source → raw → parsed → chunks) для последующей интеграции с DataHub/Marquez (governance-раздел, §16 Phase 8) — как минимум структурированные события в логах/Dagster asset metadata.

**Критерий приёмки:** upload одного документа порождает Dagster-run, который последовательно проходит все ops до `done`; статусы этапов видны через job-status endpoint; `cancel` в середине переводит job в `cancelled` и останавливает выполнение; batch-ingestion seed-набора проходит все документы и выдаёт агрегированный отчёт.

---

### 5.11 Наблюдаемость, надёжность и обработка ошибок

- [ ] Внедрить structured logging (`structlog`, §13.2) во всех модулях ingestion с корреляцией по `job_id`/`doc_id`.
- [ ] Добавить OpenTelemetry-трейсинг (`opentelemetry-sdk`, §13.2) на этапы upload → parse → store → chunk; спаны с длительностью каждого этапа.
- [ ] Экспонировать метрики (Prometheus-совместимые) через `GET /api/v1/admin/metrics` (§6.2): число ingested docs, среднее время парсинга, доля fallback-парсинга, доля failed jobs, распределение chunk_type.
- [ ] Реализовать dead-letter/retry-логику для упавших jobs: сохранять полную ошибку, разрешать ручной re-run без повторной загрузки файла (raw уже в `kg-raw`).
- [ ] Валидировать все parsed/chunk/граф-DTO артефакты Pydantic-схемами (§8.1/§8.3/§9.2 Step 3) перед записью; при невалидных данных — падать этап с понятной ошибкой, а не молча писать мусор.
- [ ] Обеспечить очистку временных файлов и потоковую (streaming) загрузку/выгрузку в MinIO, чтобы большие PDF не держались целиком в памяти.

**Критерий приёмки:** при принудительной ошибке парсинга job переходит в `failed` с сохранённым текстом ошибки и доступен re-run; `GET /api/v1/admin/metrics` возвращает счётчики ingestion; в логах прослеживается полная цепочка одного `job_id` от upload до emit_chunks.

---

### 5.12 Интеграционные тесты и приёмка раздела

- [ ] Подготовить golden-набор тестовых файлов в `apps/ingestion-service/tests/fixtures/`: минимум по одному PDF (текстовый), PDF (сканированный, для OCR), DOCX, PPTX, HTML, и один файл с таблицей и один с рисунком.
- [ ] Написать end-to-end тест: upload файла → ожидание `done` → проверка наличия всех артефактов §9.2 в MinIO → проверка записи источника в Postgres → проверка `chunks.jsonl` и валидности чанков §9.2 Step 3.
- [ ] Проверить, что для загруженного документа сформированы и переданы в граф-раздел валидные DTO `Document/Section/Chunk/Table` (§8.1/§8.2) с Evidence-якорями (§8.3), и после upsert (граф-раздел) документ виден в графе — соответствие §16 Phase 1 acceptance «document nodes visible in graph».
- [ ] Прогнать сквозную ingestion seed-корпуса Phase 0 (≥10 документов) как smoke-набор; убедиться, что Phase 1 acceptance выполняется для всего набора, а не только для одного файла.
- [ ] Написать тест дедупликации (повторная загрузка → `duplicate=true`, без дублей в `sources`/MinIO) и тест версионирования (изменённый файл → `version+1`).
- [ ] Написать тест fallback-цепочки (docling недоступен → успех через marker/unstructured) и тест ручной замены таблицы (`corrected=true`, исходный артефакт сохранён).
- [ ] Написать тест контрактов §6.2 для всех `/documents/*`, `/ingest/*` и `/admin/health`, `/admin/metrics` endpoints (коды, форма ответа).
- [ ] Прогонять весь набор в CI против реально поднятых `docling` + `minio` + `postgres` (docker compose в CI).

**Критерий приёмки (раздел завершён, если):** e2e-тест зелёный для всех форматов PDF/DOCX/PPTX/HTML; для каждого документа в MinIO присутствуют `original.*`, `docling.json`, `document.md`, `tables/table_001.json` (при таблицах), `images/img_001.png` (при рисунках), `pages/page_001.json`, `manifest.json`, `chunks.jsonl`; источник зарегистрирован по §9.2 Step 1; чанки соответствуют §9.2 Step 3; сформированы граф-DTO узлов `Document/Section/Chunk/Table` (§8.1/§8.2) с Evidence-якорями (§8.3); `GET /api/v1/admin/health` и `GET /api/v1/admin/metrics` (§6.2) отвечают 200; upload PDF через `/api/v1/documents/upload` приводит к parsed-результату, видимому через `/api/v1/documents/{doc_id}/parsed`, полностью выполняя deliverables и acceptance criteria §16 Phase 1.


---


## 6. KG extraction (правила + ML + LLM)

Раздел покрывает полную реализацию извлечения фактов знаний из распарсенных и разбитых на чанки документов (§9.2 Step 4, §9.4, §4.2). Извлечение строится на трёх слоях: (1) rule/domain extractors (regex единиц, composition parser, processing/property vocabulary), (2) ML extractors (GLiNER, MatBERT/MatSciBERT, SciSpacy, MatEntityRecognition), (3) LLM schema-guided extraction (Pydantic-схемы, JSON mode / function calling, обязательный evidence span). Базой graph-extraction служит LlamaIndex `PropertyGraphIndex`, а reference-реализацией — Neo4j LLM Graph Builder. Целевые типы узлов извлечения по §8.1: `Material`, `Alloy`, `ChemicalElement`, `Composition`, `Sample`, `ProcessingRegime`, `ProcessingStep`, `Parameter`, `Equipment`, `Lab`, `ResearchTeam`, `Person`, `Property`, `Measurement`, `Unit`, `Method`, `Experiment`, `Claim`, `Finding`, `Evidence`, `ExtractorRun`. Затрагиваемые компоненты по §6.1: `packages/kg_extractors/` (основной код), `apps/extraction-service/` (воркеры schema-guided extraction), `packages/kg_schema/` (Pydantic + LinkML-схемы), `packages/kg_common/` (общие DTO, config, logging).

**Зависимости от других разделов:**
- Раздел KG schema (§8): определения labels/relationships, `Evidence`, `ExtractorRun`, constraints (§8.4) — extraction создаёт узлы этих типов и обязан соблюдать `evidence_id IS UNIQUE`.
- Раздел ingestion pipeline (§9.1–9.3): на вход extraction приходят structure-aware chunks с полями `chunk_id`, `doc_id`, `section_path`, `page_start/page_end`, `chunk_type`, `text` (§9.2 Step 3).
- Раздел `kg_schema` / LinkML: extraction импортирует Pydantic-модели из `packages/kg_schema`.
- Раздел units normalization (§9.2 Step 5): extraction отдаёт сырые `(value, unit, value_raw)` + флаг `needs_custom_normalization`; поля `value_normalized`/`normalized_unit`/`normalization_method` заполняет нормализация — здесь НЕ реализуется, но контракт на выходе фиксируется (§6.16).
- Раздел entity resolution (§9.2 Step 6, Splink) и graph upsert (§9.2 Step 7): extraction отдаёт им сырые mentions и факты; сам upsert и Splink здесь НЕ реализуются, но контракт на выходе фиксируется.
- Раздел curation (§12): low-confidence факты попадают в review queue.

---

### 6.1 Scaffolding: каркас `packages/kg_extractors` и `apps/extraction-service`

- [x] Создать Python-пакет `packages/kg_extractors/` (`pyproject.toml`, `src/kg_extractors/__init__.py`, `py.typed`), устанавливаемый в editable-режиме (`pip install -e`).
- [x] Создать подпакеты по слоям: `kg_extractors/rules/`, `kg_extractors/ml/`, `kg_extractors/llm/`, `kg_extractors/graph/` (LlamaIndex), `kg_extractors/evidence/`, `kg_extractors/orchestrator/`, `kg_extractors/resources/` (YAML-словари, gazetteers).
- [x] Определить единый протокол `Extractor` (Python `Protocol`/ABC) с методом `extract(chunk: ChunkInput) -> ExtractionResult` в `kg_extractors/base.py`; все rule/ML/LLM extractors реализуют этот интерфейс.
- [x] Определить общий DTO `ExtractionResult` (Pydantic) в `packages/kg_common`: список mentions/фактов, список `EvidenceSpan` (с `chunk_id`, `doc_id`, `char_start`/`char_end`, при табличных фактах — `table_id`/`row_index`/`col_index`), `extractor_run_id`, `confidence`, `raw_payload`.
- [x] Добавить в `packages/kg_common/config.py` (pydantic-settings) настройки extraction: включённые слои, thresholds, пути к моделям, LLM endpoint/ключи, batch size, лимиты токенов.
- [x] Подключить структурное логирование (`structlog`) и OpenTelemetry-спаны (`opentelemetry-sdk`) вокруг каждого extractor-вызова (span-атрибуты: `extractor`, `chunk_id`, `n_facts`, `latency_ms`).
- [x] Прописать в `packages/kg_extractors/pyproject.toml` зависимости из §13.2, релевантные extraction: `pydantic`, `gliner`, `sentence-transformers`, `fastembed`, `pint`, `pymatgen`, `networkx`, `orjson`, `llama-index`, `llama-index-graph-stores-neo4j`, `llama-index-vector-stores-qdrant`, `spacy`/`scispacy`, `transformers`.
- [x] Создать сервис `apps/extraction-service/` (FastAPI/worker-скелет) с health-эндпоинтом и точкой входа воркера (`main.py`), импортирующий `kg_extractors`.

**Критерий приёмки:** `pip install -e packages/kg_extractors` и `pip install -e apps/extraction-service` проходят без ошибок; `from kg_extractors.base import Extractor` и `from kg_common.dto import ExtractionResult` импортируются; `pytest packages/kg_extractors -q` запускает пустой набор без коллекции ошибок; `python -c "import kg_extractors"` завершается кодом 0.

---

### 6.2 Vendoring / клонирование OSS-репозиториев (§22)

- [x] Создать директорию `vendor/` и скрипт `infra/scripts/vendor_extraction.sh`, клонирующий репозитории с фиксацией конкретного commit SHA (не `HEAD`) в `vendor/manifest.lock`.
- [x] Клонировать GLiNER: `git clone https://github.com/urchade/GLiNER vendor/gliner` (модель для flexible NER, §9.2 Step 4).
- [x] Клонировать MatBERT: `git clone https://github.com/lbnlp/MatBERT vendor/matbert` (§22, materials-BERT эмбеддинги/классификаторы).
- [x] Клонировать MatSciBERT: `git clone https://github.com/M3RG-IITD/MatSciBERT vendor/matscibert` (materials science language model).
- [x] Клонировать MatEntityRecognition: `git clone https://github.com/CederGroupHub/MatEntityRecognition vendor/mat-entity-recognition` (§22, NER для материаловедения).
- [x] Клонировать LlamaIndex: `git clone https://github.com/run-llama/llama_index vendor/llama_index` (§22, reference для `PropertyGraphIndex`).
- [x] Клонировать Neo4j LLM Graph Builder как reference-реализацию: `git clone https://github.com/neo4j-labs/llm-graph-builder vendor/llm-graph-builder` (§22) — использовать только как образец промптов/схем, не как runtime-зависимость.
- [x] (Опционально helper) Клонировать SciSpacy: `git clone https://github.com/allenai/scispacy vendor/scispacy` для scientific-текста (§9.2 Step 4, «only as helper»).
- [x] (Опционально reference) Клонировать MatKG: `git clone https://github.com/olivettigroup/MatKG vendor/matkg` (§22, materials KG из литературы) — как источник gazetteers/vocab материалов и свойств для rule-экстракторов (§6.4/§6.6), не runtime-зависимость.
- [x] (Опционально helper) Клонировать Matscholar: `git clone https://github.com/materialsintelligence/matscholar vendor/matscholar` (§22, materials NER/embeddings) — как дополнительный materials-NER/справочник, отключаемый флагом config.
- [x] Для каждого vendored-репозитория зафиксировать LICENSE и записать в `vendor/LICENSES.md` (тип лицензии, совместимость), plus заметку в `NOTICE`.
- [x] Настроить загрузку весов моделей (HF Hub: `urchade/gliner_*`, `m3rg-iitd/matscibert`, MatBERT checkpoints) через скрипт `infra/scripts/download_models.sh` с кэшем в `models/` (не коммитить веса, добавить в `.gitignore`).

**Критерий приёмки:** `infra/scripts/vendor_extraction.sh` завершается кодом 0; `vendor/manifest.lock` содержит по строке (repo, URL, commit SHA) для gliner, matbert, matscibert, mat-entity-recognition, llama_index, llm-graph-builder; `vendor/LICENSES.md` содержит запись для каждого репо (включая опциональные scispacy/matkg/matscholar, если клонированы); `infra/scripts/download_models.sh` скачивает GLiNER + MatSciBERT веса, и smoke-скрипт `python -c "from gliner import GLiNER; GLiNER.from_pretrained(...)"` выполняется без ошибки.

---

### 6.3 Rule extractor: regex единиц измерения

- [ ] Реализовать модуль `kg_extractors/rules/units_regex.py` с regex-паттернами для единиц из §9.2 Step 4: `°C` (temperature), `h`/`hr`/`hours` (time), `wt%` (weight percent), `at%` (atomic percent), `MPa`, `GPa` (stress), `HV` (Vickers hardness), `HRC` (Rockwell C hardness).
- [ ] Реализовать токенайзер «значение+единица», распознающий: целые/дробные числа, экспоненту (`1.2e3`), знак `±` (tolerance), диапазоны (`180-200 °C`, `2–4 h`), списки (`180, 200, 220 °C`).
- [ ] Возвращать для каждого совпадения структурированный объект `{value, unit, value_min, value_max, tolerance, raw_text, char_start, char_end}` с точными оффсетами внутри chunk-текста.
- [ ] Поддержать частые вариации написания единиц: `deg C`, `degC`, `℃`, `wt.%`, `wt %`, `at.%`, `at %`, `M Pa`, `GPa`, `Hv`, `HRC`/`Rockwell C`.
- [ ] Не терять единицы твёрдости, которые нельзя привести через `pint` (HV, HRC) — помечать флагом `needs_custom_normalization=True` для передачи в units normalization (§9.2 Step 5).
- [ ] Написать unit-тесты `tests/rules/test_units_regex.py` минимум с 30 кейсами (по 3+ на каждую единицу + диапазоны + `±` + отрицательные кейсы, где не должно быть матча), с проверкой корректности `char_start`/`char_end`.

**Критерий приёмки:** `pytest tests/rules/test_units_regex.py` зелёный; на фиксированном тест-наборе из 30+ строк extractor извлекает все ожидаемые (value, unit) пары с precision ≥ 0.95 и recall ≥ 0.95, а `text[char_start:char_end]` всегда равен исходному matched-фрагменту.

---

### 6.4 Rule extractor: composition parser

- [ ] Реализовать `kg_extractors/rules/composition_parser.py`, парсящий обозначения материалов/составов: систем сплавов (`Al-Cu`, `Ti-6Al-4V`, `Fe-Ni-Cr`), стандартных марок (`AA2024`, `2024-T6`, `Inconel 718`), явных составов в `wt%`/`at%` (`Al-4.5wt%Cu`).
- [ ] Извлекать список химических элементов (`ChemicalElement`) и их долей, формируя объект `Composition` (§8.1: `Material`→`HAS_COMPOSITION`→`Composition`→`CONTAINS_ELEMENT`→`ChemicalElement`).
- [ ] Валидировать символы элементов и нормализовать формулы через `pymatgen` (`pymatgen.core.Composition`) — отбрасывать невалидные комбинации, распознавать периодическую таблицу.
- [ ] Различать `wt%` vs `at%` и сохранять тип доли; поддержать «balance/bal.» для основного элемента.
- [ ] (Опционально) Обогащать gazetteer имён/марок сплавов из MatKG (`vendor/matkg`) для повышения recall распознавания материалов (§6.2).
- [ ] Возвращать `material_mention` (raw string) + распарсенную структуру + evidence span (char offsets), не привязываясь к каноническому ID (canonicalization делается в entity resolution, §9.2 Step 6).
- [ ] Написать тесты `tests/rules/test_composition_parser.py` (≥ 20 кейсов: alloy systems, grades, wt%/at% составы, невалидные строки).

**Критерий приёмки:** на тест-наборе из ≥ 20 обозначений parser корректно извлекает элементы и доли с recall ≥ 0.9; `pymatgen`-валидация отклоняет ≥ 95% заведомо невалидных строк; каждый результат содержит корректный evidence span.

---

### 6.5 Rule extractor: processing vocabulary

- [ ] Создать YAML-словарь `kg_extractors/resources/processing_vocab.yaml` с операциями обработки (`ProcessingRegime`/`ProcessingStep`, §8.1): `aging`, `solution treatment`, `quenching`, `annealing`, `tempering`, `homogenization`, `cold rolling`, `hot rolling`, `extrusion`, `forging`, `normalizing` и их синонимами.
- [ ] Добавить в словарь параметры (`Parameter`): `temperature`, `time`, `atmosphere` (`air`, `argon`, `vacuum`, `N2`), `cooling_rate` (`water quench`, `air cool`, `furnace cool`).
- [ ] Реализовать `kg_extractors/rules/processing_vocab.py` — gazetteer-матчер (по нормализованным леммам), связывающий обнаруженную операцию с рядом стоящими значениями единиц из §6.3 (temperature_c, time_h) в объект `ProcessingRegimeExtract` (см. §6.9).
- [ ] Обеспечить association правило: параметр (например, `180 °C`) привязывается к ближайшей операции в пределах одного предложения/чанка, с записью расстояния как признака уверенности.
- [ ] Структурировать multi-step режим в граф §8.2: `ProcessingRegime`-[:HAS_STEP]->`ProcessingStep`-[:HAS_PARAMETER]->`Parameter`; каждый шаг сохраняет порядок (`step_index`) и свои параметры (temperature/time/atmosphere/cooling_rate).
- [ ] Ассоциировать оборудование с шагом обработки (`(:ProcessingStep)-[:USED_EQUIPMENT]->(:Equipment)`, §8.2), связывая equipment-упоминания (§6.7) с ближайшей операцией.
- [ ] Написать тесты `tests/rules/test_processing_vocab.py` (≥ 15 кейсов, включая multi-step режимы «solution treated at 500 °C then aged at 180 °C for 2 h»).

**Критерий приёмки:** на тест-наборе процедурных предложений extractor распознаёт операции с recall ≥ 0.9 и корректно связывает temperature/time с операцией в ≥ 85% multi-parameter кейсов; multi-step предложение раскладывается на упорядоченные `ProcessingStep` с параметрами; словарь содержит ≥ 15 операций и покрывает синонимы.

---

### 6.6 Rule extractor: property vocabulary

- [ ] Создать YAML-словарь `kg_extractors/resources/property_vocab.yaml` со свойствами (`Property`, §8.1): `hardness` (Vickers/Rockwell), `tensile strength`, `yield strength`, `elongation`, `Young's modulus`, `fatigue life`, `grain size`, `electrical conductivity`, `thermal conductivity`, с синонимами и допустимыми единицами.
- [ ] Реализовать `kg_extractors/rules/property_vocab.py`, извлекающий упоминания свойств и связывающий их со значением+единицей (§6.3) в `MeasurementExtract` (см. §6.9), а также с каноническим property-ключом (для последующего property vocabulary mapping в §9.2 Step 6).
- [ ] Распознавать `baseline_value` и `effect_direction` (increase/decrease/no change) по маркерам («increased from … to …», «improved by», «reduced»), заполняя соответствующие поля `MeasurementExtract`.
- [ ] Извлекать метод измерения/характеризации свойства (`Method`, §8.1): напр. Vickers/Rockwell для hardness, tensile test для strength, XRD/SEM/TEM; сохранять как `method_mention` при `MeasurementExtract` для последующего создания узла `Method`.
- [ ] Валидировать соответствие единицы свойству (например, HV/HRC → hardness; MPa/GPa → strength) и помечать несоответствия для review (флаг `unit_property_mismatch`, используется в §6.15).
- [ ] Написать тесты `tests/rules/test_property_vocab.py` (≥ 15 кейсов, включая baseline+effect_direction и распознавание метода измерения).

**Критерий приёмки:** на тест-наборе extractor извлекает property-mentions с recall ≥ 0.9; связка property↔unit валидна в ≥ 95% кейсов; `baseline_value`/`effect_direction` заполняются корректно в ≥ 80% релевантных предложений; метод измерения распознаётся, когда присутствует в тексте.

---

### 6.7 ML extractor: GLiNER (flexible NER)

- [ ] Реализовать `kg_extractors/ml/gliner_ner.py`, загружающий GLiNER-модель (из `vendor/gliner` + HF-веса) с конфигурируемым набором меток, соответствующих доменным типам: `material`, `alloy`, `chemical_element`, `sample`, `processing_operation`, `equipment`, `property`, `measurement`, `method`, `lab`, `person`, `research_team` (§8.1).
- [ ] Обеспечить batched-инференс по чанкам с настраиваемым порогом уверенности (`gliner_threshold` в config) и maпингом spans в char offsets внутри chunk-текста (evidence spans).
- [ ] Возвращать mentions как `ExtractionResult` с полями `{label, text, char_start, char_end, score}`; каждый mention получает evidence span (обязательно для §6.11).
- [ ] Поддержать выбор GLiNER-модели через config (например, `urchade/gliner_medium` vs large), с fallback на CPU и опциональным GPU.
- [ ] Добавить кэширование модели в память процесса (singleton loader), чтобы не перезагружать веса на каждый вызов.
- [ ] Написать тесты `tests/ml/test_gliner_ner.py`: smoke-тест загрузки модели (skip если веса недоступны в CI), детерминированный тест на 5 предложениях с проверкой, что span-оффсеты валидны (`text[start:end]` совпадает).

**Критерий приёмки:** GLiNER-extractor загружается и обрабатывает батч из ≥ 8 чанков; для каждого извлечённого mention `char_start`/`char_end` валидны; на размеченном mini-наборе (≥ 20 предложений) NER-recall по типу `material` ≥ 0.7; latency логируется в OTel-спане.

---

### 6.8 ML extractors: MatBERT / MatSciBERT / MatEntityRecognition

- [ ] Реализовать `kg_extractors/ml/materials_bert.py`, загружающий MatSciBERT (`m3rg-iitd/matscibert`) и/или MatBERT для: (a) эмбеддингов доменного текста, (b) классификатора типа чанка/сущности где полезно (§9.2 Step 4 «where useful»).
- [ ] Реализовать классификатор chunk_type/entity-type поверх MatSciBERT-эмбеддингов (fine-tuned head или zero-shot similarity) для разметки чанков как `methods`/`results`/`measurement_row` (помощь chunker-у и LLM-роутингу).
- [ ] Интегрировать MatEntityRecognition (`vendor/mat-entity-recognition`) как специализированный materials-NER: обернуть его инференс в интерфейс `Extractor`, маппить его теги (`MAT`, `PRO`, `APL`, `SMT`, ...) на доменные labels (§8.1).
- [ ] Реализовать fusion mentions от GLiNER и MatEntityRecognition: dedup по перекрытию spans, объединение уверенности (см. §6.13 orchestration).
- [ ] Обеспечить, что эмбеддинги MatSciBERT доступны как переиспользуемый компонент для indexing (§9.2 Step 8) и entity resolution (общий контракт через `kg_common`).
- [ ] Написать тесты `tests/ml/test_materials_bert.py` (smoke: загрузка модели; форма эмбеддинга = hidden_size; MatEntityRecognition возвращает ≥ 1 сущность на эталонном предложении).

**Критерий приёмки:** MatSciBERT-эмбеддер возвращает вектор корректной размерности для батча; MatEntityRecognition-обёртка реализует `Extractor` и извлекает materials-mentions с evidence spans; fusion GLiNER+MatEntityRecognition не создаёт дубликатов при полном перекрытии spans (проверено тестом).

---

### 6.9 LLM schema-guided extraction: Pydantic-схемы (§9.4)

- [ ] В `packages/kg_schema` определить Pydantic-схемы извлечения ровно по §9.4: `ProcessingRegimeExtract` (`operation`, `temperature_c`, `time_h`, `atmosphere`, `cooling_rate`, `evidence_text`, `confidence`), `MeasurementExtract` (`property_name`, `value`, `unit`, `condition`, `baseline_value`, `effect_direction`, `evidence_text`, `confidence`), `ExperimentExtract` (`material_mentions`, `processing[]`, `measurements[]`, `equipment_mentions[]`, `lab_mentions[]`, `claims[]`).
- [ ] Добавить в каждую схему валидаторы: `confidence` в диапазоне [0,1] (`Field(ge=0, le=1)`), непустой `evidence_text` (обязателен — основа правила «no span → no fact», §9.2 Step 4), нормализация `effect_direction` в enum `{increase, decrease, no_change}`.
- [ ] Различать `Claim` и `Finding` (§8.1): структурировать элементы `claims[]` в объект с полями `statement`, `claim_type` (`claim|finding`) и mention-ссылками `about_material`/`about_property`/`about_regime` (для последующих связей `(:Claim)-[:ABOUT_MATERIAL|ABOUT_PROPERTY|ABOUT_REGIME]->` §8.2), сохраняя evidence span.
- [ ] Реализовать `kg_extractors/llm/schema_extractor.py`, вызывающий LLM в JSON mode / через function calling с `response_format`/tool-schema, сгенерированной из Pydantic-модели `ExperimentExtract`.
- [ ] Написать доменные промпты `kg_extractors/llm/prompts/experiment_extract.md` (§4.2 «extraction prompts под материалы/сплавы/режимы») с инструкцией: извлекать только факты, подтверждённые дословным фрагментом текста; `evidence_text` обязан быть точной подстрокой chunk-текста.
- [ ] Реализовать retry/repair-логику: при невалидном JSON или ошибке Pydantic-валидации — повторный вызов с сообщением об ошибке (bounded retries), затем drop с логом.
- [ ] Сделать LLM-провайдер конфигурируемым (endpoint/model/ключи в config); использовать структурированный вывод open-source модели через OpenRouter (tool use / JSON-схема из Pydantic; политика open-source-only §23.33) и/или локальную модель — управлять через `packages/kg_common/config.py`.
- [ ] Написать тесты `tests/llm/test_schema_extractor.py` с мокнутым LLM-ответом: (a) валидный JSON → корректный `ExperimentExtract`; (b) `confidence`=1.5 → ValidationError; (c) пустой `evidence_text` → факт отбрасывается.

**Критерий приёмки:** для замоканного корректного ответа extractor возвращает валидный `ExperimentExtract`; факты с пустым/невалидным `evidence_text` не попадают в результат; невалидный JSON вызывает bounded retry, а после исчерпания — контролируемый drop с логом; `pytest tests/llm/test_schema_extractor.py` зелёный.

---

### 6.10 LLM extraction: строгое правило evidence span («no span → no fact»)

- [ ] Реализовать `kg_extractors/evidence/span_validator.py`, проверяющий, что `evidence_text` каждого факта является дословной (или fuzzy с порогом ≥ 0.95) подстрокой исходного chunk-текста; при несовпадении факт помечается `rejected_no_span`.
- [ ] Вычислять для валидного span точные `char_start`/`char_end` относительно chunk и, через chunk-метаданные (§9.2 Step 3: `page_start`, `section_path`), заполнять `page`; для табличных фактов — `table_id`, `row_index`, `col_index` (§8.3).
- [ ] Формировать узел `Evidence` строго по модели §8.3: `id`, `source_type` (`paragraph|table_cell|figure_caption|metadata|manual`), `doc_id`, `page`, `table_id`, `row_index`, `col_index`, `char_start`, `char_end`, `text`, `extractor`, `model`, `confidence`, `created_at`, `reviewed_by=null`, `review_status=pending`.
- [ ] Заполнять в `Evidence` ссылку на исходный chunk (`chunk_id`) для связи `(:Evidence)-[:FROM_CHUNK]->(:Chunk)`, а для табличных фактов — `table_id` для `(:Evidence)-[:FROM_TABLE]->(:Table)` (§8.2).
- [ ] Поддержать `source_type=figure_caption` (Evidence из подписей к рисункам) и `source_type=metadata` наравне с `paragraph`/`table_cell` (§8.3).
- [ ] Устанавливать связи факт↔Evidence по §8.2: `(:Measurement)-[:SUPPORTED_BY]->(:Evidence)`, `(:Claim)-[:SUPPORTED_BY]->(:Evidence)` и `(:Evidence)-[:SUPPORTS]->(:Claim)` — каждый факт (measurement/processing/claim) ссылается на своё `Evidence`.
- [ ] Гарантировать инвариант: ни один граф-факт (measurement/processing/claim) не создаётся без связанного `Evidence` (§9.2 Step 4 «no source span → no graph fact»); orchestrator (§6.13) отбрасывает факты без Evidence.
- [ ] Написать тесты `tests/evidence/test_span_validator.py`: (a) точная подстрока → Evidence с корректными offsets; (b) галлюцинированный `evidence_text` (нет в chunk) → факт отклонён; (c) табличный span → заполнены `table_id/row/col` и связь `FROM_TABLE`.

**Критерий приёмки:** ни один факт без валидного span не проходит в выход orchestrator (проверено integration-тестом на синтетическом chunk с галлюцинацией); для валидных фактов `chunk.text[char_start:char_end]` совпадает с `Evidence.text`; каждое `Measurement` имеет ровно одно `Evidence` через `SUPPORTED_BY` и ссылку `FROM_CHUNK`/`FROM_TABLE` (соответствует acceptance §Phase 2 «every measurement has evidence»).

---

### 6.11 Graph extraction на LlamaIndex `PropertyGraphIndex`

- [ ] Реализовать `kg_extractors/graph/property_graph.py`, использующий LlamaIndex `PropertyGraphIndex` как основу graph extraction (§9.2 Step 4, §22, docs: developers.llamaindex.ai/.../lpg_index_guide/).
- [ ] Сконфигурировать `SchemaLLMPathExtractor` (LlamaIndex) с доменной схемой: разрешённые entity-типы строго из §8.1 (`Material`, `Sample`, `Composition`, `ChemicalElement`, `ProcessingRegime`, `ProcessingStep`, `Parameter`, `Property`, `Measurement`, `Unit`, `Method`, `Experiment`, `Equipment`, `Lab`, `ResearchTeam`, `Person`, `Claim`) и relationship-типы строго из §8.2 (`USES_SAMPLE`, `HAS_MATERIAL`, `HAS_COMPOSITION`, `CONTAINS_ELEMENT`, `PROCESSED_BY`, `HAS_STEP`, `HAS_PARAMETER`, `USED_EQUIPMENT`, `MEASURED`, `OF_PROPERTY`, `HAS_UNIT`, `PERFORMED_BY`, `SUPPORTED_BY`, ...).
- [ ] Синтезировать узел `Sample` как связующее звено (§8.2): `Experiment`-[:USES_SAMPLE]->`Sample`-[:HAS_MATERIAL]->`Material`, `Sample`-[:PROCESSED_BY]->`ProcessingRegime`; measurements крепятся к `Experiment` через `MEASURED` (не терять `Sample` при построении путей).
- [ ] Подключить `Neo4jPropertyGraphStore` (`llama-index-graph-stores-neo4j`) как graph store, согласованный со схемой и constraints из §8.4.
- [ ] Обеспечить, что LlamaIndex-экстрактор не пишет напрямую факты без Evidence: обернуть его выход в тот же span-validator (§6.10) и orchestrator (§6.13), не делать auto-upsert в обход curation.
- [ ] Изучить Neo4j LLM Graph Builder (`vendor/llm-graph-builder`) как reference: перенести удачные промпт-паттерны и подход к chunk→graph, задокументировав в `docs/extraction/llm_graph_builder_notes.md` (что взято, что отброшено и почему для научного домена).
- [ ] Написать интеграционный тест `tests/graph/test_property_graph.py` (с мокнутым/локальным LLM и тестовым Neo4j из docker-compose): на 1 документе строится PropertyGraph с ≥ 1 путём `Experiment-USES_SAMPLE->Sample-PROCESSED_BY->ProcessingRegime` и `Sample-HAS_MATERIAL->Material`, все типы — из whitelist схемы.

**Критерий приёмки:** `PropertyGraphIndex` с `SchemaLLMPathExtractor` извлекает только whitelisted-типы (нарушающие схему триплеты отфильтрованы — проверено тестом); построенный подграф содержит валидный `Sample`-путь, записывается в тестовый Neo4j и проходит schema-validation (§8); reference-заметки по LLM Graph Builder зафиксированы в `docs/`.

---

### 6.12 SciSpacy как helper для научного текста (опционально)

- [ ] Реализовать `kg_extractors/ml/scispacy_helper.py` (§9.2 Step 4 «SciSpacy only as helper»), выполняющий: sentence segmentation, аббревиатуры (`AbbreviationDetector`), POS/dependency для улучшения association параметров с операциями (§6.5) и baseline/effect (§6.6).
- [ ] Использовать SciSpacy для разрешения аббревиатур («ST» → «solution treatment»), расширяя gazetteer-матчинг rule-экстракторов.
- [ ] Сделать SciSpacy отключаемым флагом config (`enable_scispacy`), т.к. это опциональный helper, не критичный путь.
- [ ] Написать тесты `tests/ml/test_scispacy_helper.py` (sentence split, обнаружение ≥ 1 аббревиатуры на эталонном тексте) со `skip` при отсутствии модели.

**Критерий приёмки:** при `enable_scispacy=true` helper корректно сегментирует предложения и извлекает пары abbreviation→long_form; при `enable_scispacy=false` пайплайн работает без него (проверено, что импорт scispacy не является обязательным).

---

### 6.13 Orchestration: слияние rules + ML + LLM в единый `ExperimentExtract`

- [ ] Реализовать `kg_extractors/orchestrator/pipeline.py`, прогоняющий чанк через все включённые слои (rules → ML → LLM/PropertyGraph) и объединяющий результаты в консолидированный `ExperimentExtract` + список `Evidence`.
- [ ] Реализовать дедупликацию и слияние фактов из разных слоёв: сопоставление measurements/processing по (property/operation, value, unit, span-overlap); согласование расхождений (rules vs LLM) с записью источника каждого поля.
- [ ] Синтезировать `Sample`-узлы в консолидированном `ExperimentExtract`, связывая `Experiment`↔`Material`↔`ProcessingRegime`↔`Measurement` по §8.2 (`USES_SAMPLE`/`HAS_MATERIAL`/`PROCESSED_BY`/`MEASURED`); при отсутствии явного sample генерировать детерминированный `sample_id` на основе (doc, experiment, material, regime).
- [ ] Реализовать fusion уверенности: комбинировать `confidence` слоёв (например, boost при согласии rules+LLM, штраф при рассогласовании) в итоговый `confidence` факта по документированной формуле в `orchestrator/confidence.py`.
- [ ] Гарантировать выполнение инварианта §6.10 на уровне orchestrator: любой факт без связанного валидного `Evidence` отбрасывается до формирования выхода.
- [ ] Прописать порядок и приоритет слоёв (rule-факты для чисел/единиц предпочтительнее LLM при конфликте значений; LLM — для связей и claims) в конфиге `extraction_policy.yaml`.
- [ ] Написать тесты `tests/orchestrator/test_pipeline.py`: (a) rules+LLM согласны → один merged факт с повышенной уверенностью; (b) конфликт значений → факт помечен для review; (c) факт без Evidence не выходит из pipeline; (d) синтез `Sample` связывает Experiment→Material→ProcessingRegime.

**Критерий приёмки:** на эталонном документе orchestrator возвращает единый `ExperimentExtract` без дублей (проверено: перекрывающиеся measurements схлопнуты) и с корректно синтезированными `Sample`-связями; confidence-fusion детерминирован и покрыт тестом; ни один факт без Evidence не присутствует в выходе.

---

### 6.14 Метаданные extractor run (`ExtractorRun`)

- [ ] Определить в `packages/kg_schema` модель `ExtractorRun` (узел графа, §8.2 связь `(:Evidence)-[:EXTRACTED_BY]->(:ExtractorRun)`): `run_id`, `pipeline_version`, включённые extractors и их версии, `model` (LLM/GLiNER/rules идентификаторы), параметры (thresholds), `doc_id(s)`, `started_at`, `finished_at`, `status`, `n_facts`, `n_rejected_no_span`.
- [ ] Реализовать `kg_extractors/orchestrator/run_metadata.py`, создающий `ExtractorRun` в начале обработки документа и присоединяющий каждый `Evidence` через `EXTRACTED_BY` (§8.2); поле `Evidence.extractor`/`Evidence.model` заполняется из run (§8.3).
- [ ] Сохранять `extractor_run_id` в каждом факте для последующего graph upsert (§9.2 Step 7 «store extraction run id») и для трассируемости/lineage (интеграция с Dagster/MLflow — раздел metadata §13).
- [ ] Обеспечить воспроизводимость: логировать git commit из `vendor/manifest.lock`, версии моделей, seed/temperature LLM в `ExtractorRun.params`.
- [ ] Написать тесты `tests/orchestrator/test_run_metadata.py`: run создаётся, все Evidence ссылаются на него, метаданные содержат версии моделей и промптов.

**Критерий приёмки:** для обработки документа создаётся ровно один `ExtractorRun`, на который ссылаются все `Evidence` этого прогона через `EXTRACTED_BY`; `ExtractorRun.params` содержит версии всех задействованных extractors/моделей и LLM-параметры; `extractor_run_id` присутствует в каждом факте.

---

### 6.15 Confidence scoring и маршрутизация в review queue

- [ ] Реализовать `kg_extractors/orchestrator/review_routing.py`: факты с `confidence < review_threshold` (конфигурируемый, напр. 0.65 как `min_confidence` в §6.2 API) помечаются `review_status=pending` и формируют review-tasks (§Phase 2 «create review tasks for low confidence», §12.1 триггеры review queue).
- [ ] Определить контракт review-task (Pydantic DTO в `kg_common`): `evidence_id`, `fact_type`, `extracted_value`, `confidence`, `doc_id`, `page`, span — для передачи в curation-service (§12.1 review queue).
- [ ] Реализовать правила auto-accept/needs-review/reject по confidence-порогам и по флагам несоответствий (unit↔property mismatch из §6.6, конфликт слоёв из §6.13, low-quality OCR и «new schema term» из §12.1).
- [ ] Написать тесты `tests/orchestrator/test_review_routing.py`: факт с confidence 0.5 → pending/review-task; факт 0.9 → авто-accept-кандидат; unit-mismatch → review независимо от confidence.

**Критерий приёмки:** low-confidence факты (confidence < threshold) детерминированно попадают в review-очередь с валидным review-task DTO; факты с несоответствием unit↔property всегда идут в review; поведение покрыто тестами (соответствует acceptance §Phase 2 «low-confidence extraction appears in review queue»).

---

### 6.16 Extraction workers в `apps/extraction-service` (интеграция со Step 4 pipeline)

- [ ] Реализовать в `apps/extraction-service` воркер, потребляющий задачи «extract chunk/document» (очередь/Dagster asset — согласовать с разделом ingestion §9.1), вызывающий orchestrator (§6.13) и возвращающий факты+Evidence+ExtractorRun.
- [ ] Реализовать batch-режим (по документу: все чанки) и single-chunk режим; идемпотентность по (`doc_id`, `chunk_id`, `pipeline_version`) — повторный прогон не плодит дубликаты Evidence (детерминированные `evidence_id` под constraint §8.4).
- [ ] Зафиксировать handoff-контракт для units normalization (§9.2 Step 5): для каждого `Measurement` передать `value_raw`, `value`, `unit`, флаг `needs_custom_normalization` (HV/HRC из §6.3); поля `value_normalized`/`normalized_unit`/`normalization_method` заполняет нормализация (Step 5), здесь НЕ реализуется.
- [ ] Отдавать результат в handoff-контракт для entity resolution (§9.2 Step 6, Splink) и graph upsert (§9.2 Step 7): сырые `material_mentions`/`equipment_mentions`/`lab_mentions`/`person`/`method` — на entity resolution; measurements/processing/claims + Evidence + Sample-связи — на upsert. Сам upsert/Splink в этом разделе НЕ реализуются.
- [ ] Реализовать job-статусы и прогресс (`queued|running|done|failed`, число фактов, число rejected_no_span), совместимые с эндпоинтами `/api/v1/ingest/jobs/{job_id}` (§6.2 API Gateway).
- [ ] Обработка ошибок: изоляция сбоя на уровне чанка (сбой одного чанка не валит весь документ), запись частичного результата и логирование.
- [ ] Написать интеграционный тест `tests/service/test_extraction_worker.py`: подать документ из golden-набора (§6.17) → получить факты, Evidence, ExtractorRun; повторный прогон идемпотентен.

**Критерий приёмки:** воркер обрабатывает документ end-to-end и отдаёт handoff-DTO для units normalization (Step 5), entity resolution (Step 6) и graph upsert (Step 7); повторный запуск того же (`doc_id`, `pipeline_version`) не создаёт дублирующих Evidence (idempotency-тест зелёный); job-статус доступен и корректно отражает прогресс/ошибки.

---

### 6.17 Тестирование, evaluation и приёмка extraction

- [ ] Собрать golden extraction-набор `packages/kg_eval/data/extraction_golden/`: ≥ 15 репрезентативных научных документов/фрагментов (materials/alloys/regimes/properties) с ручной разметкой ожидаемых materials/processing/measurements/evidence spans.
- [ ] Реализовать eval-харнесс `packages/kg_eval/extraction_eval.py`, считающий per-extractor и end-to-end метрики: precision/recall/F1 по типам сущностей, точность (value, unit) для measurements, span-accuracy (IoU оффсетов), долю фактов с валидным Evidence.
- [ ] Считать в eval стоимость/латентность извлечения на документ (§15.2 «extraction cost per document»): токены/стоимость LLM, latency по слоям, число вызовов — и трекать по `pipeline_version`.
- [ ] Добавить отчёт evaluation (JSON + markdown) и интеграцию с MLflow (§13.2, §15.3) для трекинга метрик по `pipeline_version`.
- [ ] Реализовать регрессионный тест приёмки Phase 2: на sample-документах ≥ 70% дают полезные граф-факты; каждое `Measurement` имеет Evidence; low-confidence факты уходят в review (§Phase 2 acceptance criteria).
- [ ] Настроить CI-джоб `extraction-tests`, запускающий unit + integration тесты (`pytest packages/kg_extractors apps/extraction-service tests`), с mock-LLM для детерминизма и `skip`-маркерами для тестов, требующих тяжёлых весов/GPU.
- [ ] Задокументировать в `docs/extraction/README.md`: архитектуру трёх слоёв, конфиги, thresholds, как добавлять новые единицы/vocab/entity-типы, как запускать eval.

**Критерий приёмки:** `python -m kg_eval.extraction_eval --golden ...` выдаёт отчёт с метриками (включая cost/latency на документ); на golden-наборе end-to-end: ≥ 70% документов дают полезные граф-факты, 100% measurements имеют Evidence, span-accuracy (IoU ≥ 0.9) ≥ 0.85; CI-джоб `extraction-tests` зелёный; документация в `docs/extraction/README.md` присутствует и описывает все три слоя.


---


## 7. Нормализация единиц и величин

Раздел описывает подсистему нормализации численных величин и единиц измерения, извлечённых на этапе extraction (§9.4). Цель — превратить сырые строки вроде `"148 HV"`, `"≥ 320 MPa"`, `"180 ± 5 °C"`, `"12–28 %"` в структурированные, сравнимые, валидированные значения по модели `Measurement` из §9.5 (`value_raw`, `value`, `unit`, `value_normalized`, `normalized_unit`, `normalization_method`). Всё, что не удаётся нормализовать однозначно, помечается флагами и уходит в review queue (§12) и в gap analysis как `missing_unit` (§11). Движок нормализации — общий (shared) слой, используется extraction-service и graph upsert (§9.7).

Общий принцип: нормализация детерминирована, идемпотентна и версионируется. Любое значение всегда сохраняет исходную сырую строку `value_raw`, а нормализованное значение снабжается `normalization_method` (`direct` | `converted` | `rule` | `manual`) и версией registry, чтобы результат был воспроизводим и объясним в Evidence Inspector.

---

### 7.1 Интеграция `pint` и собственный UnitRegistry

- [x] Добавить зависимость `pint` (pinned версия) в `packages/kg_common/pyproject.toml` и в общий `requirements`/lock; зафиксировать точную версию для воспроизводимости.
- [x] Создать модуль `packages/kg_common/units/registry.py` с фабрикой `build_unit_registry() -> pint.UnitRegistry`, инкапсулирующей всю доменную конфигурацию.
- [x] Загружать базовый `default_en.txt` из pint и поверх него применять доменный файл определений `packages/kg_common/units/domain_units.txt` через `registry.load_definitions(...)`.
- [x] Настроить registry: `non_int_type=Decimal` или явная политика float, `autoconvert_offset_to_baseunit=True` (для корректной работы температур), `case_sensitive=True` где нужно различать регистр (например, `HV` vs `hv`).
- [x] Реализовать singleton/кэш registry на уровне процесса (`functools.lru_cache`) — не создавать `UnitRegistry` на каждый вызов (дорого и ломает сравнение Quantity из разных registry).
- [x] Присвоить registry версию `UNIT_REGISTRY_VERSION` (semver-строка) и экспортировать её; писать эту версию в поле нормализации, чтобы каждое значение знало, каким registry получено.
- [x] Реализовать функцию `parse_quantity(raw: str) -> pint.Quantity` — тонкая обёртка над `registry.Quantity(...)` с перехватом `UndefinedUnitError`, `DimensionalityError`, `pint.errors.*` и возвратом типизированного результата (успех/ошибка), без «сырых» исключений наружу.
- [x] Реализовать `to_unit(q: Quantity, target: str) -> Quantity` с обработкой `DimensionalityError` (несовместимые размерности) и возвратом причины провала.
- [x] Добавить поддержку системы единиц по умолчанию (`registry.default_system`) и явный контекст SI для internal storage; определить canonical target-единицу для каждого класса свойств (см. 7.2).
- [x] Написать `packages/kg_common/units/__init__.py` с публичным API: `build_unit_registry`, `parse_quantity`, `to_unit`, `normalize_measurement`, `UNIT_REGISTRY_VERSION`.

**Критерий приёмки:** `from kg_common.units import build_unit_registry; ureg = build_unit_registry()` работает; `parse_quantity("180 degC").to("kelvin").magnitude == 453.15` (± 1e-6); повторный вызов `build_unit_registry()` возвращает тот же объект (idempotent, кэширован); версия registry доступна как строка.

---

### 7.2 Доменные единицы и canonical target-единицы по классам свойств

- [x] Создать `packages/kg_common/units/domain_units.txt` с pint-определениями доменных единиц, отсутствующих в default (например `ksi`, `mpy`, `wt_percent`, `at_percent`, `ppm`, `ppb`, `HV`, `HRC`, `HB` как безразмерные именованные единицы твёрдости).
- [x] Определить прочность: `MPa`, `GPa`, `kPa`, `Pa`, `ksi = 6.894757 * MPa`, `psi`, `N/mm**2` → canonical target `MPa`.
- [x] Определить температуру: `degC`, `kelvin`, `degF` (offset units) → canonical target `degC` для отображения, `kelvin` для internal storage; явно задать политику (хранить оба или одно + правило конверсии).
- [x] Определить время: `s`, `min`, `h`, `day` → canonical target `h` для режимов обработки (совместимо с `time_h` из §8), `s` для быстрых процессов; задать правило выбора target по контексту свойства.
- [x] Определить состав: `wt_percent` (weight %), `at_percent` (atomic %), `ppm`, `ppb`, `mol_percent` как разные измерения (НЕ взаимоконвертируемые без состава/молярных масс) — пометить их как non-interconvertible классы.
- [x] Определить скорость охлаждения: `K/s`, `degC/s`, `degC/min`, `K/min` → canonical target `K/s`.
- [x] Определить скорость коррозии: `mm/year`, `mpy` (mils per year), `um/year`, `g/(m**2 * day)` → canonical target `mm/year`; задать `mpy = 0.0254 * mm/year`.
- [x] Определить длину/размер зерна: `um`, `nm`, `mm`, `angstrom` → canonical target `um`.
- [x] Определить модуль упругости и модуль сдвига: `GPa`, `MPa` → canonical target `GPa`.
- [x] Определить плотность тока/электрохимию по мере надобности (`A/cm**2`, `mA/cm**2`) → canonical target `A/m**2`.
- [x] Создать реестр `PROPERTY_UNIT_POLICY: dict[str, PropertyUnitPolicy]` в `packages/kg_common/units/policies.py`, где для каждого класса свойства (`hardness`, `tensile_strength`, `yield_strength`, `temperature`, `time`, `composition`, `cooling_rate`, `corrosion_rate`, `grain_size`, `elastic_modulus`, ...) заданы: допустимые размерности, canonical target unit, набор допустимых входных единиц, флаг `interconvertible`.
- [x] Связать `PROPERTY_UNIT_POLICY` с property vocabulary (§9.6 entity resolution) так, чтобы `property_name` из `MeasurementExtract` маппился на класс свойства и его политику.
- [x] Задать дефолтную единицу-предположение (assumed unit) только там, где это безопасно и явно документировано (например, для явно именованного свойства `hardness_HV`), и всегда помечать такой случай `normalization_method="rule"` + флаг `unit_assumed=true`.

**Критерий приёмки:** для каждого класса свойств из списка существует запись в `PROPERTY_UNIT_POLICY` с canonical target unit и списком допустимых единиц; `ureg("1 ksi").to("MPa").magnitude ≈ 6.894757`; `ureg("1 mpy").to("mm/year").magnitude ≈ 0.0254`; `wt_percent` и `at_percent` имеют разные размерности/классы и не конвертируются автоматически.

---

### 7.3 Политики и маппинги для твёрдости (HV/HRC/HB, Vickers/Rockwell/Brinell)

- [x] Определить `HV`, `HRC`, `HRB`, `HB` (Brinell) как именованные безразмерные единицы твёрдости; зафиксировать, что pint НЕ умеет конвертировать их линейно (шкалы нелинейны и стандартозависимы).
- [x] Реализовать отдельный `HardnessConverter` в `packages/kg_common/units/hardness.py`, НЕ через pint-конверсию, а через табличные/стандартные соответствия (ASTM E140 / ISO 18265) — как rule-based конверсию.
- [x] Встроить таблицу соответствий HV↔HRC↔HB (по ASTM E140) как данные `packages/kg_common/units/data/astm_e140.csv` с интерполяцией между узлами таблицы.
- [x] Задать политику: конверсия твёрдости между шкалами выполняется ТОЛЬКО по запросу и всегда помечается `normalization_method="rule"` + `conversion_standard="ASTM E140"`; хранить и исходную шкалу.
- [x] Задать область применимости конверсионных таблиц (диапазоны валидности каждой шкалы) и возвращать флаг `out_of_conversion_range`, если исходное значение вне узлов таблицы.
- [x] Учесть, что Brinell (HB) зависит от нагрузки/диаметра индентора (HBW 10/3000 и т.п.) — парсить и хранить эти параметры как метаданные, не терять их при нормализации.
- [x] Учесть Vickers-нагрузку (HV0.5, HV1, HV10, HV30) — распознавать суффикс нагрузки, хранить как `load_kgf`, не смешивать значения с разной нагрузкой при сравнении без пометки.
- [x] По умолчанию НЕ конвертировать твёрдость между шкалами при upsert (хранить в исходной шкале, `normalization_method="direct"`); конверсию делать лениво в retrieval/сравнении с явной пометкой.
- [x] Написать unit-тесты на несколько эталонных пар из ASTM E140 (например, ~30 HRC ≈ ~302 HV ≈ ~286 HB) с допуском.

**Критерий приёмки:** `HardnessConverter.convert(30, "HRC", "HV")` возвращает значение в допустимом диапазоне таблицы ASTM E140 с меткой `normalization_method="rule"` и `conversion_standard`; попытка pint-конверсии `HV → MPa` даёт контролируемую ошибку (не молчаливый неверный результат); значение вне диапазона таблицы возвращает флаг `out_of_conversion_range`.

---

### 7.4 Парсер сырых значений (диапазоны, ±, неравенства, нотация)

- [ ] Создать `packages/kg_extractors/units/value_parser.py` (или `packages/kg_common/units/value_parser.py` — см. 7.9) с функцией `parse_raw_value(raw: str) -> ParsedValue`.
- [ ] Определить Pydantic-модель `ParsedValue` с полями: `kind` (`scalar` | `range` | `bound` | `list` | `unparseable`), `value`, `value_min`, `value_max`, `uncertainty`, `operator` (`=`|`>`|`>=`|`<`|`<=`|`~`), `unit_str`, `raw`, `warnings: list[str]`.
- [ ] Парсить скаляр с единицей: `"148 HV"`, `"148HV"`, `"320 MPa"`, `"180 °C"`, `"2 h"` — разделять число и единицу, включая слипшиеся написания.
- [ ] Парсить диапазоны: `"12–28 %"`, `"12-28%"`, `"120 to 150 MPa"`, `"120...150"`, `"от 120 до 150"` — распознавать разные тире (`-`, `–`, `—`), `to`, `…`, русские предлоги; заполнять `value_min`/`value_max`, `value` = среднее (с пометкой).
- [ ] Парсить погрешность `±`: `"180 ± 5 °C"`, `"180+/-5"`, `"180 +- 5"` — заполнять `value` и `uncertainty`.
- [ ] Парсить неравенства: `"≥ 320 MPa"`, `">=320"`, `"< 0.1 mm/year"`, `"≤2 at%"`, `"max 300 HV"`, `"min 320 MPa"` — заполнять `operator` и `value` (bound).
- [ ] Парсить научную нотацию и разделители: `"1.2e-3"`, `"1,2·10^3"`, `"1.5 × 10^6"`, `"1 200"` (пробел как разделитель тысяч), `"1,5"` (запятая как десятичный разделитель, RU/EN) — с явной эвристикой RU/EN и warning при неоднозначности.
- [ ] Парсить приблизительные значения: `"~150"`, `"≈150"`, `"about 150"`, `"порядка 150"` → `operator="~"`.
- [ ] Парсить значения с единицей до числа и локализованные единицы: `"HV 148"`, `"МПа 320"` (кириллические единицы) → маппинг кириллица→латиница (`МПа→MPa`, `ГПа→GPa`, `°С→degC`).
- [ ] Отделять условие/контекст от значения (например `"148 HV (after aging)"`) — контекст в отдельное поле, не в число.
- [ ] Возвращать `kind="unparseable"` с сохранением `raw` и warning, если ничего не распозналось; НИКОГДА не бросать исключение наружу.
- [ ] Нормализовать десятичный разделитель, unicode-минусы, неразрывные пробелы, множественные пробелы перед передачей строки единицы в pint.

**Критерий приёмки:** набор из ≥ 40 табличных примеров (`packages/kg_extractors/units/tests/parser_cases.csv`) парсится в ожидаемый `ParsedValue`; `parse_raw_value("180 ± 5 °C").uncertainty == 5`; `parse_raw_value("≥ 320 MPa").operator == ">="`; `parse_raw_value("12–28 %").kind == "range"` и `value_min==12, value_max==28`; `parse_raw_value("1,2e-3")` корректно даёт `0.0012`; неразпознанное даёт `kind="unparseable"` без исключений.

---

### 7.5 Модель хранения и функция нормализации (§9.5)

- [ ] Реализовать Pydantic-модель `NormalizedMeasurement` в `packages/kg_common/units/models.py` строго по §9.5: `value_raw: str`, `value: float | None`, `unit: str | None`, `value_normalized: float | None`, `normalized_unit: str | None`, `normalization_method: Literal["direct","converted","rule","manual"]`.
- [ ] Расширить модель служебными полями (не ломая контракт §9.5): `value_min`/`value_max`/`uncertainty`/`operator` (из ParsedValue), `property_class`, `unit_registry_version`, `normalized_at`, флаги `unit_missing`/`unit_assumed`/`out_of_conversion_range`/`unparseable`, `warnings: list[str]`.
- [ ] Реализовать основную функцию `normalize_measurement(raw: str, property_name: str | None) -> NormalizedMeasurement`, объединяющую parser (7.4) + registry (7.1) + policy (7.2) + hardness (7.3) + validation (7.7).
- [ ] Определить семантику `normalization_method`: `direct` — единица уже canonical, конверсии нет; `converted` — pint-конверсия к canonical target; `rule` — доменное правило/таблица (твёрдость, assumed unit); `manual` — значение проставлено/исправлено куратором.
- [ ] Для диапазонов/неравенств нормализовать границы: сохранять `value` (репрезентативное — среднее для range, само значение для bound) + `value_min`/`value_max` в canonical единицах; `value_normalized` держать согласованным с `value`.
- [ ] Гарантировать идемпотентность: повторная нормализация уже нормализованного `NormalizedMeasurement` даёт тот же результат (тест round-trip).
- [ ] Гарантировать сохранность `value_raw` всегда, даже при `unparseable` — исходная строка не теряется никогда.
- [ ] Согласовать поля с `MeasurementExtract` из §9.4 (`property_name`, `value`, `unit`, `baseline_value`) — реализовать адаптер `from_extract(m: MeasurementExtract) -> NormalizedMeasurement`, нормализующий и `value`, и `baseline_value`.
- [ ] Согласовать с graph-схемой §8: маппинг `NormalizedMeasurement` → свойства узла `Measurement` (`value_normalized` индексируется, см. `measurement_value_index` в §8.4) и связь `(:Measurement)-[:HAS_UNIT]->(:Unit)` с canonical `normalized_unit`.
- [ ] Сериализация в JSON стабильна (orjson) и обратима; добавить `to_neo4j_props()` для upsert.

**Критерий приёмки:** `normalize_measurement("148 HV", "hardness")` даёт `value=148, unit="HV", value_normalized=148, normalized_unit="HV", normalization_method="direct"` (совпадает с примером §9.5); `normalize_measurement("46.5 ksi", "tensile_strength")` даёт `value_normalized≈320.6, normalized_unit="MPa", normalization_method="converted"`; повторная нормализация результата идемпотентна; `value_raw` всегда заполнено.

---

### 7.6 Неконвертируемые / неоднозначные / отсутствующие единицы → review queue и gap

- [ ] Определить классификацию проблем нормализации: `NO_UNIT` (единицы нет), `UNKNOWN_UNIT` (единица не распознана registry), `AMBIGUOUS_UNIT` (несколько трактовок, например `%` без wt/at), `DIMENSION_MISMATCH` (единица не соответствует классу свойства), `UNPARSEABLE_VALUE`, `OUT_OF_CONVERSION_RANGE`, `SUSPECT_VALUE` (провал sanity-check, см. 7.7).
- [ ] При `NO_UNIT`: выставлять флаг `unit_missing=true`, `normalization_method` не присваивать конверсию, и эмитить gap-сигнал `missing_unit` (совместимо с §11.1 `missing_unit` и §9.4-нодой gap `missing_unit`).
- [ ] При `AMBIGUOUS_UNIT` (`%` без указания wt/at для состава): НЕ угадывать, ставить флаг `unit_ambiguous`, создавать review task.
- [ ] При `UNKNOWN_UNIT`/`DIMENSION_MISMATCH`/`UNPARSEABLE_VALUE`: сохранять `value_raw`, оставлять `value_normalized=None`, ставить соответствующий флаг, создавать review task.
- [ ] Реализовать эмиттер `build_review_task(measurement, problem) -> ReviewTaskDTO` и интеграцию с curation-service (§12) через `create_review_task` (совместимо с agent-tool `create_review_task` из §7.4 дизайна).
- [ ] Проставлять в review task: `value_raw`, распознанные части, тип проблемы, предложенные варианты (candidate units/interpretations), ссылку на Evidence (§8.3) — чтобы куратор видел источник.
- [ ] Реализовать путь `manual`-коррекции: когда куратор проставляет/исправляет единицу или значение, записывать `normalization_method="manual"`, фиксировать `CurationEvent` (§12.3) и защищать поле от перезаписи автоматической ре-нормализацией (§9.7 «never overwrite reviewed fields»).
- [ ] Согласовать с Gap Dashboard (§5.2.7 «properties without units») и gap-scan Cypher: значения с `unit_missing=true` должны попадать в матрицу пробелов.
- [ ] Не блокировать ingestion при проблемах нормализации: факт всё равно апсертится (с флагами и пониженной пригодностью к сравнению), но помечается для ревью — degrade gracefully.

**Критерий приёмки:** `normalize_measurement("320", "tensile_strength")` даёт `unit_missing=true`, `value_normalized=None` и порождает gap-сигнал `missing_unit` + review task; `normalize_measurement("2.5 %", "composition")` даёт `unit_ambiguous=true` и review task (не выбирает wt/at молча); значение с `normalization_method="manual"` не перезаписывается повторным прогоном нормализации.

---

### 7.7 Валидация диапазонов свойств (sanity checks) и детект выбросов

- [ ] Создать конфиг `packages/kg_common/units/data/property_ranges.yaml` с физически допустимыми диапазонами (min/max в canonical единицах) для каждого класса свойства: hardness (HV, HRC, HB отдельно), tensile/yield strength (MPa), temperature (degC/K), time (h), composition (0–100 %), cooling_rate, corrosion_rate, grain_size, elastic_modulus.
- [ ] Реализовать `validate_range(nm: NormalizedMeasurement) -> list[Warning]`: проверять, что `value_normalized` попадает в допустимый диапазон класса; вне диапазона — флаг `SUSPECT_VALUE` + warning (не отбрасывать значение).
- [ ] Добавить sanity-проверки согласованности: `value_min <= value <= value_max` для диапазонов; неотрицательность там, где требуется (время, размер зерна, состав); состав в сумме по элементам не превышает 100 wt% (мягкая проверка на уровне Composition).
- [ ] Добавить проверку правдоподобия единицы против класса: например `hardness` в `MPa` без явного контекста → warning/ambiguous; `temperature` ниже 0 K → hard error.
- [ ] Реализовать статистический outlier-детект по популяции: для (material_class × property_class) собирать распределение `value_normalized` и помечать выбросы (например по IQR/robust z-score) флагом `statistical_outlier` для ревью.
- [ ] Детектировать вероятные ошибки единиц по «фактору 1000/10» (например значение прочности 0.32 вместо 320 MPa, или GPa/MPa путаница) — эвристика `unit_scale_suspect`.
- [ ] Отделить hard-errors (нефизичные значения → в review, `value_normalized` не индексируется) от soft-warnings (подозрительно, но допускается) — разные флаги, разные последствия.
- [ ] Связать `SUSPECT_VALUE`/`statistical_outlier` с curation review queue (§12.1 «LLM extracted value from low-quality OCR») и с contradiction detection (§11 conflicting measurements).

**Критерий приёмки:** значение `hardness = 5000 HV` помечается `SUSPECT_VALUE` (вне диапазона `property_ranges.yaml`) и уходит в review; `tensile_strength = -50 MPa` даёт hard-error и не индексируется как валидное; диапазон с `value_min > value_max` порождает warning согласованности; outlier-детект помечает значение, отстоящее от медианы популяции по robust z-score.

---

### 7.8 Юнит-тесты, эталонная таблица конверсий, property-based тесты

- [ ] Создать `packages/kg_common/units/tests/test_conversions.py` с параметризованными тестами по эталонной таблице конверсий (см. ниже).
- [ ] Встроить эталонную таблицу конверсий `packages/kg_common/units/data/reference_conversions.csv` (from_value, from_unit, to_unit, expected_value, tolerance) и покрыть все canonical-переходы из 7.2.
- [ ] Написать тесты парсера (7.4) по `parser_cases.csv`: ≥ 40 кейсов (скаляры, диапазоны, ±, неравенства, нотация, кириллица, unparseable).
- [ ] Написать property-based тесты (Hypothesis): round-trip `X unit → target → back` в пределах tolerance; идемпотентность `normalize(normalize(x)) == normalize(x)`.
- [ ] Написать тесты твёрдости (7.3) против узлов ASTM E140 с допуском; тест на `out_of_conversion_range`.
- [ ] Написать тесты sanity/range (7.7): нефизичные значения → флаги; согласованность диапазонов; outlier-детект на синтетической популяции.
- [ ] Написать тесты интеграции `from_extract` (7.5): `MeasurementExtract` → `NormalizedMeasurement` → `to_neo4j_props()`; проверить маппинг baseline_value.
- [ ] Добавить negative-тесты: `DimensionalityError` (`HV→MPa`), `UndefinedUnitError` (мусорная единица) → контролируемые флаги, без необработанных исключений.
- [ ] Достичь покрытия ≥ 90% строк для модуля `kg_common/units` (замер `pytest --cov`); включить модуль в CI (`ruff`, `mypy`, `pytest` из §16 Phase 0).
- [ ] Задокументировать эталонную таблицу конверсий прямо в разделе (ниже) для ревью и как источник тест-данных.

Эталонная таблица конверсий (источник для `reference_conversions.csv`):

| from | from_unit | to_unit | expected | tolerance |
|---|---|---|---|---|
| 180 | degC | kelvin | 453.15 | 1e-6 |
| 100 | degC | degF | 212.0 | 1e-3 |
| 1 | ksi | MPa | 6.894757 | 1e-4 |
| 46.5 | ksi | MPa | 320.6 | 0.1 |
| 1 | GPa | MPa | 1000.0 | 1e-6 |
| 2 | h | s | 7200.0 | 1e-6 |
| 90 | min | h | 1.5 | 1e-9 |
| 1 | mpy | mm/year | 0.0254 | 1e-6 |
| 1 | mm/year | mpy | 39.3701 | 1e-3 |
| 60 | degC/min | K/s | 1.0 | 1e-6 |
| 1000 | nm | um | 1.0 | 1e-9 |
| 30 | HRC | HV | ~302 (ASTM E140, ±10) | 10 |
| 30 | HRC | HB | ~286 (ASTM E140, ±10) | 10 |

**Критерий приёмки:** `pytest packages/kg_common/units` зелёный; все строки эталонной таблицы проходят с указанным tolerance; покрытие модуля ≥ 90%; property-based round-trip и идемпотентность держатся на сгенерированных входах; negative-тесты не приводят к необработанным исключениям.

---

### 7.9 Размещение кода в монорепо и интеграция с extraction-service / graph upsert

- [ ] Разместить ядро нормализации (registry, policies, hardness, models, normalize_measurement, validation) в `packages/kg_common/units/` — как shared-слой, доступный всем сервисам (extraction, graph, curation, retrieval), так как нормализация нужна и при ingestion, и при сравнении в retrieval.
- [ ] Разместить парсер сырых строк и доменные extraction-хелперы либо в `packages/kg_common/units/value_parser.py` (если нужен и в retrieval для парсинга пользовательских запросов, ср. §7.5-нода `preprocess_question` дизайна нормализует `°C, h, wt%, MPa, HV`), либо в `packages/kg_extractors/units/`; принять и задокументировать одно решение (рекомендация: parser в `kg_common`, доменные property-vocab маппинги в `kg_extractors`).
- [ ] Экспортировать стабильный публичный API из `kg_common.units`, чтобы `apps/extraction-service` и `apps/graph-service` импортировали только его, не внутренние модули.
- [ ] Встроить вызов `normalize_measurement`/`from_extract` в `apps/extraction-service` сразу после LLM/rule extraction (§9.4 Step 4) и перед graph upsert (§9.5 Step 5 → §9.7 Step 7) в pipeline Dagster (`NORMALIZE` asset из §9.1).
- [ ] В graph upsert (`apps/graph-service`) писать в узел `Measurement` поля `value_raw/value/unit/value_normalized/normalized_unit/normalization_method` + флаги; создавать/мёрджить узел `Unit` по canonical `normalized_unit`; индексировать `value_normalized` (§8.4).
- [ ] Соблюдать правило §9.7: не перезаписывать поля с `normalization_method="manual"` при повторной автоматической нормализации (проверять флаг перед upsert).
- [ ] Прокидывать `unit_registry_version` и `normalized_at` в Evidence/ExtractorRun-метаданные, чтобы Evidence Inspector (§5.2.6) показывал, как получено нормализованное значение.
- [ ] Эмитить gap-сигналы `missing_unit` и review tasks из pipeline (не из ядра библиотеки напрямую) — ядро возвращает флаги, сервис оркестрирует создание задач/гэпов (чистое разделение ответственности).
- [ ] Добавить контрактные тесты интеграции extraction→normalize→upsert на 1–2 seed-документах (§16 Phase 2/Phase 3): проверить, что нормализованные значения появляются в Neo4j и индексируются.
- [ ] Задокументировать модуль в `packages/kg_common/units/README.md` (публичный API, добавление новой единицы/класса свойства, политика конверсии твёрдости) — как единственный источник правды для команды.

**Критерий приёмки:** `apps/extraction-service` и `apps/graph-service` импортируют нормализацию только из `kg_common.units`; прогон ingestion на seed-документе создаёт узлы `Measurement` с заполненными `value_normalized`/`normalized_unit`/`normalization_method` и связью `HAS_UNIT`; значения без единиц дают gap `missing_unit`; поля `manual` не перезаписываются повторной нормализацией; `unit_registry_version` виден в метаданных для Evidence Inspector.


---


## 8. Entity resolution (Splink)

Раздел реализует Step 6 pipeline (§9.1, §9.2 «Step 6: entity resolution») — вероятностное разрешение сущностей (entity resolution, ER) поверх извлечённых mentions. Цель: свести множество упоминаний (`Al-Cu 2024`, `AA2024`, `2024 aluminum alloy`) к одной canonical-сущности с сохранением alias-истории, привязать decision (`auto_merge | review_needed | separate`) к порогам match_probability и защитить проверенные canonical-сущности от автоматической перезаписи.

Затрагиваемые сервисы/пакеты (§6.1):
- **новый пакет** `packages/kg_er/` — вся ER-логика: Splink-модели, blocking/comparison-конфиги, decision engine, alias-store адаптеры (расположен рядом с `packages/kg_extractors/`, использует `packages/kg_schema/` и `packages/kg_common/`).
- `apps/ingestion-service/` и `apps/extraction-service/` — вызов ER-шага после normalization (Step 5) и перед graph upsert (Step 7).
- `apps/curation-service/` — merge/split события, CurationEvent history, review queue, защита reviewed canonical.
- `apps/api-gateway/` — endpoints §6.2: `POST /entities/merge`, `POST /entities/{entity_id}/aliases`, `GET /entities/search`, `GET /entities/{entity_id}`.
- `apps/graph-service/` — Cypher upsert canonical/alias, чтение соседей, MERGE by canonical id (§9.2 Step 7).
- `infra/dagster/` — ER как asset/op в ingestion-графе.

OSS для клонирования/вендоринга (§22 «Entity resolution / cleaning»):
- Splink: `https://github.com/moj-analytical-services/splink`
- Dedupe (альтернатива): `https://github.com/dedupeio/dedupe`
- OpenRefine (альтернатива/reconciliation): `https://github.com/OpenRefine/OpenRefine`
- Materials-helpers для нормализации: pymatgen `https://github.com/materialsproject/pymatgen`, MatKG `https://github.com/olivettigroup/MatKG`, Matscholar `https://github.com/materialsintelligence/matscholar`.

Зависимости от других разделов: KG schema и `kg_schema` labels Material/Equipment/Person/Lab/ResearchTeam/Property (§8.1–8.4); ingestion pipeline Steps 4–5 (extraction + units normalization); curation workflow (§12); Neo4j constraints и fulltext-index `entity_name_index` по `n.name, n.canonical_name, n.aliases_text` (§8.4).

### 8.1 Вендоринг и интеграция Splink и зависимостей

- [x] Добавить в единый requirements/lock (`packages/kg_er/pyproject.toml` + корневой lock) зависимости: `splink`, `duckdb`, `pandas`, `polars`, `pymatgen`, `sentence-transformers`, `fastembed`, `pint`, `networkx`, `orjson`, `structlog`, `opentelemetry-sdk`, `mlflow`, `mp-api` (Materials Project client) — версии зафиксировать точным pin, совместимым со списком §13.2 (`pint`, `networkx`, `opentelemetry-sdk`, `mlflow` уже есть в §13.2).
- [x] Выбрать и зафиксировать backend Splink = **DuckDB** (in-process, из списка §13.2 `duckdb`); задокументировать в `packages/kg_er/README.md`, что Spark/Athena backends не используются в MVP.
- [x] Склонировать/вендорить Splink `https://github.com/moj-analytical-services/splink` в `infra/vendor/splink/` (или зафиксировать как pip-зависимость) и зафиксировать конкретный релиз/commit hash в `infra/vendor/VENDOR.lock`.
- [x] Создать скелет пакета `packages/kg_er/` со структурой: `kg_er/models/` (Splink settings per entity type), `kg_er/blocking/`, `kg_er/comparisons/`, `kg_er/decision/`, `kg_er/store/` (alias/canonical persistence), `kg_er/pipeline.py` (entrypoint Step 6), `kg_er/cli.py`.
- [x] Реализовать smoke-скрипт `packages/kg_er/scripts/smoke_splink.py`, который на DuckDB backend обучает тривиальную модель на 20 синтетических строках и печатает predictions — используется как проверка среды.
- [x] Настроить детерминизм: зафиксировать `random_seed` во всех Splink `estimate_*` вызовах и в EM-обучении, чтобы результаты воспроизводились между запусками.

**Критерий приёмки:** команда `python packages/kg_er/scripts/smoke_splink.py` завершается кодом 0, выводит непустой DataFrame с колонкой `match_probability`; `pip show splink` показывает pinned-версию, совпадающую с `VENDOR.lock`.

### 8.2 Alias-датасеты для Material и property vocabulary

- [x] Определить в `packages/kg_schema/` Pydantic/LinkML-модель `AliasRecord{ alias_text, canonical_id, entity_type, source (curated|imported|extracted), confidence, added_by, added_at }` и `CanonicalEntity{ id, entity_type, name, canonical_name, aliases_text, attributes }`.
- [x] Создать seed alias-датасет для Material `packages/kg_er/data/material_aliases.csv` (columns: `alias_text, canonical_id, canonical_name, normalized_formula, source`), включив минимум: маппинги вида `AA2024|2024 aluminum alloy|Al-Cu 2024 -> material:al-cu-2024` и ещё ≥50 распространённых сплавов/обозначений (UNS, AA, EN, ГОСТ где применимо).
- [x] Реализовать импортёр внешних alias-источников `kg_er/store/import_aliases.py` с адаптерами для MatKG (`https://github.com/olivettigroup/MatKG`), Matscholar (`https://github.com/materialsintelligence/matscholar`) и MatEntityRecognition (`https://github.com/CederGroupHub/MatEntityRecognition`); импортёр помечает записи `source=imported` и не перезаписывает `source=curated`.
- [x] Реализовать нормализатор химсостава на pymatgen (`Composition`, `Element`) `kg_er/comparisons/composition.py`: из mention/формулы получать `normalized_formula` и вектор долей элементов для сравнения Material.
- [x] Реализовать привязку Material к внешнему авторитету через Materials Project API (`https://github.com/materialsproject/api`, `mp-api`/pymatgen `MPRester`) `kg_er/store/mp_authority.py`: по `normalized_formula` получать `mp_id` и canonical-формулу, сохранять `mp_id` в `CanonicalEntity.attributes` и использовать как якорь канонизации (§7.6 Node 3 «Materials Project / internal catalog IDs»); помечать `source=imported`.
- [x] При заливке canonical Material в Neo4j строить графовую структуру состава `(:Material)-[:HAS_COMPOSITION]->(:Composition)-[:CONTAINS_ELEMENT]->(:ChemicalElement)` (§8.2 relationships) из `normalized_formula`, чтобы element-based blocking/comparison согласовывался с графом.
- [x] Определить controlled **property vocabulary** `packages/kg_er/data/property_vocab.yaml`: список canonical Property (`property:hardness`, `property:yield_strength`, …) с полями `canonical_id, canonical_name, synonyms[], symbol, allowed_units[]` (согласовать `allowed_units` с units normalization §9.2 Step 5 и `pint`).
- [x] Реализовать loader `kg_er/store/property_vocab.py`, который валидирует уникальность `canonical_id`, непустой `synonyms`, и что каждый `allowed_units` парсится `pint`.
- [x] Обогатить `property_vocab.yaml` синонимами/символами из Propnet (`https://github.com/materialsintelligence/propnet`) через `kg_er/store/import_property_vocab.py`; импортированные synonyms помечать источником и не затирать курированные записи.
- [x] Написать миграцию/loader, который заливает alias-датасеты и property vocab в Neo4j как canonical-узлы с полем `aliases_text` (для fulltext `entity_name_index` §8.4) через `graph-service`.

**Критерий приёмки:** `pytest packages/kg_er/tests/test_alias_data.py` проверяет, что `AA2024`, `2024 aluminum alloy`, `Al-Cu 2024` резолвятся в один `canonical_id=material:al-cu-2024`; `property_vocab.yaml` проходит валидацию loader'а без ошибок; в Neo4j для этих aliases заполнено `aliases_text`, а у Material-узла есть `mp_id` и подграф `HAS_COMPOSITION/CONTAINS_ELEMENT`.

### 8.3 Подготовка данных и feature engineering для Splink

- [ ] Реализовать `kg_er/pipeline.py::build_er_frame(entity_type)` — сбор кандидатов ER: mentions из extraction (Step 4) + существующие canonical-узлы Neo4j одного `entity_type` в единый DuckDB/pandas frame с колонкой `unique_id`.
- [ ] Реализовать общие cleaning-функции `kg_er/comparisons/text.py`: lowercasing, удаление пунктуации, unicode-нормализация (NFKC), сжатие пробелов, term expansion по synonyms property vocab.
- [ ] Реализовать per-type feature-колонки:
  - [ ] Material: `name_clean`, `normalized_formula`, `element_set`, `alloy_family`, `designation_code (AA/UNS/EN)`.
  - [ ] Equipment: `name_clean`, `manufacturer`, `model_code`, `equipment_class` (SEM/XRD/tensile/…).
  - [ ] Person: `name_clean`, `given_name`, `family_name`, `initials`, `orcid`, `email_domain`.
  - [ ] Lab / ResearchTeam: `name_clean`, `org`, `city`, `country`, `parent_institution`.
- [ ] Реализовать embedding-фичу `kg_er/comparisons/embed.py` (sentence-transformers/fastembed): вектор от `name`+`description` для доменного comparison-level "semantic near match".
- [ ] Персистить эмбеддинги canonical-сущностей (1024-dim, cosine) в Neo4j `entity_embedding_index` (§8.4 `CREATE VECTOR INDEX entity_embedding_index ... vector.dimensions:1024, similarity_function:'cosine'`) и переиспользовать этот индекс для embedding-based blocking/генерации кандидатов и для query-time resolve (§8.8); зафиксировать модель эмбеддингов и её размерность (=1024).
- [ ] Настроить blocking rules per type в `kg_er/blocking/`:
  - [ ] Material: block по первой букве `element_set` + `alloy_family`; и отдельный блок по `designation_code`.
  - [ ] Equipment: block по `manufacturer` и по `model_code` prefix.
  - [ ] Person: block по `family_name` + `given_name[0]`; и по `orcid`.
  - [ ] Lab/ResearchTeam: block по `org` token + `country`.
- [ ] Добавить проверку размера декартова произведения после blocking: логировать число comparisons на блок и падать/варнить, если блок превышает конфиг-лимит `max_block_size`.

**Критерий приёмки:** `build_er_frame("Material")` на тестовом наборе возвращает frame со всеми обязательными feature-колонками без NaN в ключевых полях; сумма пар после blocking для теста строго меньше полного `n*(n-1)/2` и логируется в structlog.

### 8.4 Splink-модель для Material

- [ ] Определить Splink `settings` для Material `kg_er/models/material.py`: `link_type="dedupe_only"`, blocking rules из §8.3, comparisons:
  - [ ] `name_clean` — jaro-winkler/levenshtein levels;
  - [ ] `normalized_formula` — exact + composition-distance level (через `composition.py`);
  - [ ] `element_set` — Jaccard-подобный уровень;
  - [ ] `designation_code` — exact-match term.
- [ ] Реализовать обучение модели: `estimate_u_using_random_sampling`, `estimate_parameters_using_expectation_maximisation` по blocking rules; сохранить обученные params в `packages/kg_er/models/artifacts/material_settings.json` (versioned).
- [ ] Реализовать `predict()` wrapper, возвращающий пары с `match_probability`; агрегировать транзитивно (connected components) в candidate-группы через `splink.cluster_pairwise_predictions_at_threshold`.
- [ ] Замапить каждую candidate-группу в decision-output формат §9.2 Step 6:
  ```json
  { "candidate_id": "material:al-cu-2024",
    "mentions": ["Al-Cu 2024", "AA2024", "2024 aluminum alloy"],
    "match_probability": 0.93,
    "decision": "auto_merge|review_needed|separate" }
  ```
- [ ] Залогировать/сохранить model card `material_settings.json` с датой обучения, seed, размером train-набора, распределением match_probability.
- [ ] Обеспечить, что Material-модель обрабатывает и label `Material`, и label `Alloy` (§8.1 core labels) как единое пространство разрешения (Alloy — подтип Material), а designation_code (AA/UNS/EN/ГОСТ) резолвится в тот же canonical id.

**Критерий приёмки:** на golden-наборе Material (§8.12) обученная модель кластеризует `Al-Cu 2024 / AA2024 / 2024 aluminum alloy` в одну группу с `match_probability ≥ 0.9`, а несвязанный `Ti-6Al-4V` попадает в отдельную группу; `material_settings.json` сериализуется и перезагружается без переобучения.

### 8.5 Splink-модели для Equipment, Person, Lab/ResearchTeam

- [ ] Реализовать `kg_er/models/equipment.py` (dedupe_only): comparisons по `manufacturer` (exact/fuzzy), `model_code` (exact + fuzzy), `equipment_class` (exact), `name_clean` (jaro-winkler); блокировка §8.3.
- [ ] Реализовать `kg_er/models/person.py`: comparisons по `orcid` (exact = сильный сигнал, term-level с высоким m), `family_name` (fuzzy), `given_name/initials` (fuzzy/initial-match), `email_domain` (exact); учесть same-name-different-person через low base rate.
- [ ] Реализовать `kg_er/models/lab.py` для Lab и ResearchTeam: comparisons по `org` (fuzzy), `parent_institution` (fuzzy), `city/country` (exact); ResearchTeam дополнительно учитывает пересечение members (Person canonical ids).
- [ ] Обучить и сохранить артефакты `equipment_settings.json`, `person_settings.json`, `lab_settings.json` в `models/artifacts/` (versioned, с seed и model card).
- [ ] Обеспечить единый интерфейс `kg_er/models/registry.py::get_model(entity_type)`, чтобы pipeline и decision engine работали с любой из моделей одинаково.
- [ ] Задать per-type пороги (thresholds) в конфиге `kg_er/decision/thresholds.yaml` (Person/ORCID может иметь более строгие/мягкие границы, чем Material).

**Критерий приёмки:** для каждого из 4 типов (Material/Equipment/Person/Lab) существует загружаемый settings-артефакт и проходит per-type unit-тест кластеризации на ≥1 позитивном и ≥1 негативном примере; `registry.get_model("Person")` возвращает рабочую модель.

### 8.6 Property vocabulary mapping

- [ ] Реализовать `kg_er/decision/property_mapper.py`: маппинг Property-mention → canonical property_id. Стратегия каскадом: (1) exact/synonym lookup по `property_vocab.yaml`; (2) fuzzy match по synonyms; (3) embedding-similarity fallback.
- [ ] Установить порог semantic-fallback: если top-1 similarity < `property_map_min_sim`, помечать mention как `review_needed` (новый термин, §12.1 «new schema term found»).
- [ ] При маппинге проверять совместимость единицы измерения mention с `allowed_units` canonical property (интеграция с `pint`, §9.2 Step 5); при несовместимости — флаг `unit_mismatch` в review.
- [ ] Реализовать эмиссию события `schema_change`/new-term в review queue (§12.2 `schema_change`) при обнаружении неизвестного property-термина.

**Критерий приёмки:** `hardness`, `Vickers hardness`, `HV` мапятся в `property:hardness`; неизвестный термин `unobtanium modulus` уходит в `review_needed` с причиной `new_property_term`; несовместимая единица порождает флаг `unit_mismatch`.

### 8.7 Decision engine: auto_merge / review_needed / separate

- [ ] Реализовать `kg_er/decision/engine.py`, вычисляющий `decision` по `match_probability` и порогам из `thresholds.yaml`: `>= tau_auto -> auto_merge`, `tau_review <= p < tau_auto -> review_needed`, `p < tau_review -> separate` (значения по умолчанию задокументировать, например `tau_auto=0.92`, `tau_review=0.7`).
- [ ] Ввести дополнительные правила эскалации в `review_needed` независимо от probability (§12.1): противоречие с существующим canonical, конфликт `designation_code`/ORCID, mention из low-quality OCR (флаг из extraction), несколько сильных canonical-кандидатов в одной группе.
- [ ] Реализовать «hard blockers» для `auto_merge`: запрет автослияния, если кандидат-группа содержит ≥2 разных **reviewed/verified** canonical-сущностей (защита §8.9) — принудительно `review_needed`.
- [ ] Сформировать для каждой группы `ERDecision{ candidate_id, entity_type, mentions[], member_ids[], match_probability, decision, reasons[], model_version }`.
- [ ] Реализовать роутинг: `auto_merge` → сразу в graph upsert (Step 7) через curation-service с авто-CurationEvent(action=merge, actor=system); `review_needed` → создать review task; `separate` → создать/оставить отдельные canonical.
- [ ] Эмитить сигнал `low_confidence_entity_resolution` (§7.8 gap rules / §11 gap types) в gap-analysis/`Gap`-узел, когда группа уходит в `review_needed` из-за низкой probability, чтобы пробел разрешения был виден в gap dashboard.
- [ ] Сделать пороги конфигурируемыми per entity_type и переопределяемыми из env/settings (`pydantic-settings`), без изменения кода.

**Критерий приёмки:** unit-тест `test_decision_engine.py` покрывает все три ветки (три probability по разные стороны порогов) и все эскалационные правила; группа с двумя verified canonical всегда даёт `decision=review_needed` вне зависимости от probability.

### 8.8 Candidate API (§6.2 /entities/*)

- [ ] Реализовать `GET /api/v1/entities/search?q=&type=&limit=` в `api-gateway`: поиск по Neo4j fulltext `entity_name_index` (`name, canonical_name, aliases_text`), возвращает canonical-сущности с их aliases.
- [ ] Реализовать `GET /api/v1/entities/{entity_id}` — canonical-сущность + `aliases[]` + `merge/split history` (см. §8.9) + evidence-ссылки.
- [ ] Реализовать `GET /api/v1/entities/{entity_id}/neighbors?depth=&types=` (используется merge-review UI) через graph-service.
- [ ] Реализовать `POST /api/v1/entities/{entity_id}/aliases` (§6.2): body `{ alias_text, source, confidence }`; добавляет `AliasRecord`, обновляет `aliases_text` canonical-узла (для fulltext), пишет `CurationEvent(action=alias_add)` (§12.3), возвращает обновлённую сущность.
- [ ] Реализовать `POST /api/v1/entities/merge` (§6.2): body `{ source_ids[], target_id, reason }`; выполняет merge через curation-service (см. §8.9), возвращает результат и `event_id`.
- [ ] Реализовать endpoint выдачи ER-кандидатов на review, например `GET /api/v1/entities/candidates?status=review_needed&type=` — отдаёт `ERDecision` в формате §9.2 Step 6 (`candidate_id, mentions, match_probability, decision`).
- [ ] Реализовать query-time резолвер `kg_er/resolve.py::resolve_mention(text, entity_type=None) -> EntityMention` для агента (§7.6 Node 3): каскад exact alias-lookup → Neo4j fulltext `entity_name_index` → vector search по `entity_embedding_index` → Splink-скоринг кандидатов; возвращает `EntityMention{ text, canonical_id, entity_type, confidence }` в формате §7.3.
- [ ] Завести agent-tools `resolve_entities` и `search_material_aliases` (§7.4), проксирующие в `resolve_mention`/alias-store; при неоднозначности возвращать top-k кандидатов с confidence и запрашивать уточнение только если это блокирует ответ (§7.6).
- [ ] Опционально выставить `POST /api/v1/entities/resolve` (body `{ text, entity_type? }`) в `api-gateway`, возвращающий `EntityMention` + список кандидатов; read-only, без curator-роли.
- [ ] Добавить Pydantic request/response-схемы всех endpoints в `packages/kg_schema/` и валидацию (§6.2 request validation).
- [ ] Реализовать защиту прав: merge/split/alias-add требуют curator-роли (audit log §6.2), обычный search/get — read-only.
- [ ] Написать OpenAPI-описание и contract-тесты (например, schemathesis/pytest) для всех `/entities/*` endpoints.

**Критерий приёмки:** через `POST /entities/{id}/aliases` добавленный alias немедленно находится через `GET /entities/search?q=<alias>`; `POST /entities/merge` возвращает 200 с `event_id`, а `GET /entities/candidates?status=review_needed` отдаёт кандидатов в формате §9.2 Step 6; `resolve_mention("AA2024","Material")`/agent-tool `resolve_entities` возвращает `EntityMention` с `canonical_id=material:al-cu-2024` и `confidence>0`.

### 8.9 Merge/split события, история и защита reviewed canonical

- [ ] Определить в Neo4j модель хранения canonical/alias/merge: canonical-узел с полями `id, canonical_name, aliases_text, review_status (pending|accepted|rejected|corrected), reviewed_by, verified (bool), locked (bool)`, alias как `(:Alias)-[:ALIAS_OF]->(canonical)` или как список — зафиксировать один вариант и задокументировать.
- [ ] Реализовать `curation-service` операцию **merge**: перенаправить рёбра source→target (`APOC` `apoc.refactor.mergeNodes` или явные Cypher-перепривязки), объединить aliases, записать `CurationEvent{action:merge, before, after}` (§12.3), сохранить обратную ссылку `merged_from[]` на исходные id для reversibility.
- [ ] Реализовать операцию **split**: разбить canonical на ≥2 сущности, перераспределить aliases/evidence по указанию куратора, записать `CurationEvent{action:split}`; гарантировать, что evidence не теряется (каждый переезжает ровно к одной цели).
- [ ] Реализовать **историю**: `merge/split` события хранятся как узлы `CurationEvent` со связями `(:CurationEvent)-[:CHANGED]->(:Entity)` (§8.2), plus `before/after` JSON snapshots; API `GET /entities/{id}` отдаёт эту историю.
- [ ] Реализовать **защиту reviewed canonical от перезаписи** (§9.2 Step 7 «never overwrite reviewed fields automatically»): при graph upsert и auto_merge запрещено изменять поля сущности с `review_status in {accepted, corrected}` или `verified=true`/`locked=true`; вместо перезаписи — создавать review task или писать в `pending`-shadow-поля.
- [ ] Реализовать field-level protection: список protected fields per label в конфиге; extraction-run может обновлять только незащищённые поля; попытка тронуть защищённое → `review_needed`.
- [ ] Обеспечить версионирование (§9.2 Step 7 «preserve previous versions»): при любом изменении canonical сохранять предыдущую версию (snapshot/`before`) и `extraction_run_id`.
- [ ] Реализовать deterministic canonical IDs (§9.2 Step 7 «deterministic IDs where possible; MERGE by canonical id»): стабильный id из normalized key per entity_type (`material:<normalized_formula>` или `material:<mp_id>`, `person:<orcid>`-иначе-slug, `equipment:<manufacturer-model-slug>`, `lab:<org-country-slug>`); MERGE в Neo4j по этому id (согласовать с UNIQUE-constraints `material_id/property_id/equipment_id` §8.4).
- [ ] Реализовать откат (undo) merge по `event_id`, восстанавливающий сущности из `merged_from[]`/before-snapshot.
- [ ] Гарантировать, что все ER/merge/split/alias-события пишутся как `CurationEvent` строго по схеме §12.3: `{ id, action(accept|reject|correct|merge|split|alias_add|schema_change), actor_id, target_type(node|edge|evidence|schema), target_id, before, after, reason, created_at }`.
- [ ] Для merge/split, меняющих политику/схему разрешения, дополнительно создавать `Decision`-узел и связь `(:Decision)-[:AFFECTS]->(:Entity)` (§8.2 relationships, §2.1 decision history), связанный с соответствующим `CurationEvent`.

**Критерий приёмки:** после merge все рёбра source указывают на target и `GET /entities/{target}` показывает объединённые aliases + `CurationEvent(action=merge)`; попытка авто-upsert перезаписать поле сущности с `review_status=accepted` не меняет значение и создаёт review task; undo восстанавливает исходные узлы; сплит не теряет ни одного evidence (проверка по count).

### 8.10 Интеграция ER-шага в ingestion pipeline и Dagster

- [ ] Встроить `kg_er/pipeline.py` как Step 6 между NORMALIZE и VALIDATE (§9.1 flowchart: `NORMALIZE --> ER --> VALIDATE`) в `ingestion-service`/`extraction-service`.
- [ ] Реализовать Dagster asset/op `entity_resolution` в `infra/dagster/`, принимающий normalized mentions и возвращающий `ERDecision[]`; связать upstream=normalization, downstream=schema validation/graph upsert.
- [ ] Прокинуть `extraction_run_id` через ER, чтобы Step 7 сохранял его (§9.2 Step 7) и чтобы merge/split события ссылались на run.
- [ ] Обеспечить, что `auto_merge` группы попадают в graph upsert с MERGE by canonical id, а `review_needed`/`separate` не блокируют pipeline (идут в очередь/создают отдельные узлы).
- [ ] Реализовать инкрементальный режим ER: при добавлении нового документа сравнивать только новые mentions против существующих canonical (blocking по индексам), не переобучая модель каждый раз.
- [ ] Добавить конфиг-флаг для переобучения моделей по расписанию (Dagster schedule) отдельно от inference.

**Критерий приёмки:** прогон ingestion на тестовом документе проходит стадию ER; в Dagster asset `entity_resolution` виден зелёным, downstream upsert получает canonical ids; добавление второго документа с `AA2024` мержится к уже существующему `material:al-cu-2024` без создания дубликата.

### 8.11 Альтернативы: dedupe и OpenRefine

- [ ] Спроектировать абстракцию `kg_er/models/base.py::ERBackend` (методы `train`, `predict`, `cluster`), чтобы Splink был реализацией по умолчанию, а альтернативы подключались без изменения decision engine/pipeline.
- [ ] Реализовать экспериментальный backend на dedupe (`https://github.com/dedupeio/dedupe`) `kg_er/models/dedupe_backend.py` для типов с малым размеченным набором (active-learning) и задокументировать, когда он предпочтительнее Splink.
- [ ] Реализовать интеграцию OpenRefine reconciliation (`https://github.com/OpenRefine/OpenRefine`) `kg_er/store/openrefine_reconcile.py` как ручной curator-инструмент: экспорт candidate-групп в OpenRefine reconciliation API формат и импорт решений обратно как CurationEvents.
- [ ] Написать сравнительный бенч `kg_er/scripts/compare_backends.py` (Splink vs dedupe) по метрикам §8.12 на одном golden-наборе и зафиксировать выбор по умолчанию в `README.md`.

**Критерий приёмки:** `ERBackend`-интерфейс реализован Splink и dedupe; `compare_backends.py` выдаёт таблицу precision/recall/F1 для обоих; OpenRefine-экспорт/импорт round-trip сохраняет `candidate_id` и применяет решения как CurationEvents.

### 8.12 Golden-набор, оценка качества и тесты

- [ ] Собрать размеченный golden ER-набор `packages/kg_er/data/golden/{material,equipment,person,lab}.jsonl` с парами mention↔canonical и негативными примерами (минимум по 30 позитивных и 30 негативных на тип).
- [ ] Реализовать оценку качества `kg_er/eval.py`: pairwise precision/recall/F1 и cluster-level metrics (например, cluster purity/pairwise-F1) относительно golden; интегрировать с `packages/kg_eval/`.
- [ ] Задать пороги приёмки в CI: Material/Equipment F1 ≥ 0.85, Person F1 ≥ 0.80 (или обоснованно скорректировать после первого прогона и зафиксировать в конфиге).
- [ ] Написать unit-тесты: `test_decision_engine.py`, `test_alias_data.py`, `test_property_mapper.py`, `test_merge_split.py`, `test_protection.py`, `test_candidate_api.py`.
- [ ] Написать integration-тест «common aliases map to same entity; ambiguous merges go to review; merge history is preserved» (acceptance §Phase 3, строки 1780–1782) end-to-end через ingestion → ER → curation → API.
- [ ] Настроить CI-джоб, запускающий eval на golden-наборе и падающий при регрессии F1 ниже порога.

**Критерий приёмки:** `pytest packages/kg_er/tests` зелёный; `python packages/kg_er/eval.py` печатает F1 по всем типам ≥ заданных порогов; end-to-end integration-тест подтверждает три acceptance-условия Phase 3.

### 8.13 Observability и метрики ER

- [ ] Логировать (structlog) на каждый ER-прогон: число mentions, число блоков, число comparisons, распределение `match_probability`, счётчики `auto_merge/review_needed/separate`, число заблокированных перезаписей reviewed canonical.
- [ ] Экспортировать метрики в `GET /api/v1/admin/metrics` (§6.2): `er_candidates_total`, `er_auto_merge_total`, `er_review_needed_total`, `er_blocked_overwrite_total`, `er_model_version`, `er_last_run_ts`.
- [ ] Добавить OpenTelemetry-спаны (`opentelemetry-sdk`, §13.2) вокруг `train/predict/cluster/decision` для трассировки латентности ER-шага.
- [ ] Настроить логирование model_version и seed в каждом ERDecision и в MLflow (`mlflow`, §13.2) как эксперимент обучения ER-моделей (метрики + артефакты settings.json).

**Критерий приёмки:** после ingestion-прогона `GET /admin/metrics` возвращает ненулевые ER-счётчики; в MLflow есть run обучения с сохранённым `material_settings.json` и метриками; OTel-трейс содержит спаны train/predict/cluster/decision.


---


## 9. Оркестрация пайплайнов (Dagster)

Раздел покрывает полную реализацию оркестрации ingestion/indexing пайплайна на Dagster (asset graph по §9.1), schedules, sensors, retries, partitions, эмиссию lineage и метаданных запусков, интеграцию с Job status API (§6.2 `/ingest/jobs`), а также лёгкий фоновый исполнитель Redis/RQ (или Celery) для быстрых UI/API-задач (executive summary §1).

Зависимости от других разделов:
- Раздел ingestion/extraction/ER/upsert/indexing (шаги §9.2 Step 1–8): Dagster-ассеты вызывают код из `apps/ingestion-service/`, `apps/extraction-service/`, `apps/graph-service/`, `apps/search-service/`, `packages/kg_extractors/`, `packages/kg_retrievers/`, `packages/kg_schema/`.
- Раздел API Gateway (§6.2): endpoints `/api/v1/ingest/jobs*` в `apps/api-gateway/`.
- Раздел metadata/lineage (Phase 8, DataHub/OpenMetadata): эмиссия lineage.
- Раздел gap analysis (§11) и retrieval eval (§15): финальные ассеты графа (`gap_scan`, `retrieval_eval`).
- Раздел infra/Docker Compose (§13.1): сервис `dagster` (port 3001), `redis`, `postgres`, `minio`.

Все структуры путей — по §6.1 (каталог `infra/dagster/` и `packages/`). Термины ассетов соответствуют шагам §9.1.

### 9.1 Вендоринг Dagster и базовый проект оркестрации

- [ ] Склонировать/вендорить референсный репозиторий Dagster в `vendor/dagster/`: `git clone https://github.com/dagster-io/dagster` (git-URL из §22 «Metadata / orchestration / lineage»); зафиксировать используемую версию в `infra/dagster/DAGSTER_VERSION` (например, git tag/commit).
- [ ] Создать каталог оркестрации по §6.1: `infra/dagster/` со структурой:
  - `infra/dagster/pyproject.toml` (пакет `kg_orchestration`, зависимость `dagster`, `dagster-webserver`, `dagster-postgres`, `dagster-aws`);
  - `infra/dagster/kg_orchestration/__init__.py` с объектом `Definitions`;
  - `infra/dagster/kg_orchestration/assets/`, `.../resources/`, `.../schedules/`, `.../sensors/`, `.../jobs/`, `.../partitions/`, `.../io_managers/`;
  - `infra/dagster/workspace.yaml`, `infra/dagster/dagster.yaml`, `infra/dagster/Dockerfile`, `infra/dagster/README.md`.
- [ ] В `infra/dagster/Dockerfile` собрать образ (соответствует `build: ./infra/dagster` из §13.1), установить `kg_orchestration` вместе с локальными пакетами `packages/kg_*` (editable install), выставить порт `3001`.
- [ ] Настроить `infra/dagster/dagster.yaml`: storage на Postgres (`run_storage`, `event_log_storage`, `schedule_storage` через `dagster-postgres`, БД `kg_app` из §13.1), `run_launcher`/`run_coordinator` (`QueuedRunCoordinator` с лимитом одновременных runs), директория `compute_logs`.
- [ ] Настроить `infra/dagster/workspace.yaml`: единственная code location `kg_orchestration` (module `kg_orchestration`); проверить загрузку через `dagster definitions validate`.
- [ ] Обновить `infra/docker-compose.yml` (§13.1): сервис `dagster` (webserver + `dagster-daemon`), `env_file: .env`, `depends_on: [postgres, redis, minio, docling]`, проброс кода `infra/dagster`; при необходимости отдельный контейнер `dagster-daemon` для schedules/sensors.
- [ ] Добавить в `.env.example` переменные: `DAGSTER_HOME`, `DAGSTER_PG_*`, `DAGSTER_WEBSERVER_PORT=3001`, а также хосты ресурсов (`NEO4J_URI`, `QDRANT_URL`, `OPENSEARCH_URL`, `S3_ENDPOINT`, `DOCLING_URL`, `REDIS_URL`).
- [ ] Добавить `Makefile`/скрипты: `dagster-dev` (локальный `dagster dev`), `dagster-materialize` (CLI materialize), `dagster-validate`.

**Критерий приёмки:** `docker compose up dagster` поднимает Dagit на `http://localhost:3001`, code location `kg_orchestration` загружается без ошибок; `dagster definitions validate` проходит; на графе ассетов виден весь pipeline из §9.1.

### 9.2 Asset graph всего ingestion/indexing пайплайна (§9.1)

- [ ] Реализовать в `infra/dagster/kg_orchestration/assets/` по одному Dagster software-defined asset на каждый шаг §9.1, сохраняя порядок зависимостей из mermaid-графа:
  - [ ] `source_registration` (Step 1 §9.2): регистрирует source в Postgres (source id, file hash, source type, owner/lab, access policy, ingestion job id, version) и эмитит регистрацию источника в каталог DataHub/OpenMetadata (§9.1 REGISTER «Register source in Postgres/DataHub», §9.8).
  - [ ] `docling_parse` (Step 2): вызывает Docling Serve (`DOCLING_URL`, порт 5001), получает markdown/structured JSON/tables/hierarchy/page refs.
  - [ ] `store_parsed_artifacts` (Step 2): пишет в S3/MinIO по путям `s3://kg-raw/documents/{doc_id}/original.pdf`, `s3://kg-parsed/documents/{doc_id}/docling.json`, `.../document.md`, `.../tables/table_001.json`.
  - [ ] `chunking` (Step 3): structure-aware чанки (title/abstract, methods, results, captions, table rows, procedure paragraphs, measurement rows) со схемой chunk из §9.2 (`chunk_id`, `doc_id`, `section_path`, `page_start/end`, `text`, `chunk_type`, `tokens`).
  - [ ] `extraction` (Step 4): комбинирует rule/domain extractors (regex единиц °C/h/wt%/at%/MPa/GPa/HV/HRC, composition/processing/property vocab), GLiNER NER, LLM schema-guided extraction по Pydantic-схемам `ExperimentExtract`/`ProcessingRegimeExtract`/`MeasurementExtract` из §9.2 (`packages/kg_extractors/`, `packages/kg_schema/`); требование evidence span для каждого факта.
  - [ ] `units_normalization` (Step 5): `pint` + кастомные маппинги HV/HRC/MPa/GPa; сохраняет `value_raw/value/unit/value_normalized/normalized_unit/normalization_method`; выполняет и нормализацию названий материалов (canonical naming — §9.1 NORMALIZE «Normalize units/material names»), передавая канонические формы в `entity_resolution`.
  - [ ] `entity_resolution` (Step 6): Splink jobs для Material/Equipment/Person/Lab/Property; выдаёт `candidate_id/mentions/match_probability/decision`.
  - [ ] `schema_validation` (VALIDATE): валидация Pydantic/LinkML (`packages/kg_schema/`); невалидные факты уходят в отдельный output/review.
  - [ ] `graph_upsert` (Step 7): `MERGE` по caнonical id в Neo4j (`apps/graph-service/`), правила upsert §9.2 (deterministic IDs, never overwrite reviewed fields, store extraction run id, preserve previous versions).
  - [ ] `qdrant_indexing` (Step 8): индексирует chunks/table rows/claims/entity descriptions/neighborhood & community summaries с payload из §9.2 (`doc_id/chunk_id/entity_ids/material_ids/property_ids/processing_operation/temperature_c/time_h/source_type/confidence/review_status`).
  - [ ] `opensearch_indexing` (Step 8): full text/keywords/facets/numeric ranges/highlight fields (`apps/search-service/`).
  - [ ] `community_summarization` (§10.3, §4/§21 GraphRAG): community detection над графом после `graph_upsert` (Neo4j GDS Louvain/Leiden или Microsoft GraphRAG reference pipeline) + LLM-генерация neighborhood- и community-summaries; корпус-уровневый ассет, чей выход индексируется в Qdrant (Step 8 «graph neighborhood summaries; community summaries»).
  - [ ] `gap_scan` (GAP §11): запускает gap-scan Cypher (`missing_baseline`, material/regime/property matrix gaps) после `graph_upsert`.
  - [ ] `retrieval_eval` (EVAL §15): прогоняет retrieval eval после индексации.
- [ ] Задать корректные `deps`/`ins` между ассетами строго по mermaid §9.1: `graph_upsert` и `*_indexing` оба зависят от `schema_validation`; `gap_scan` от `graph_upsert`; `retrieval_eval` от `qdrant_indexing`+`opensearch_indexing`; `community_summarization` от `graph_upsert`, а индексация community/neighborhood summaries в `qdrant_indexing` — от `community_summarization` (отдельная корпус-уровневая ветка от per-document индексации чанков).
- [ ] Присвоить всем ассетам `AssetKey` с префиксами-группами (`raw`, `parse`, `extract`, `graph`, `index`, `analytics`) и `group_name`, чтобы Dagit показывал слои пайплайна.
- [ ] Определить агрегирующий `job` `full_ingestion_job` (через `define_asset_job`) и подмножества: `parse_only_job`, `extract_only_job`, `reindex_job` (`qdrant_indexing`+`opensearch_indexing`), `community_summary_job` (`community_summarization`+переиндексация summaries), `gap_scan_job`.
- [ ] Собрать `Definitions` в `infra/dagster/kg_orchestration/__init__.py`: все assets, jobs, schedules, sensors, resources, io_managers.
- [ ] Для каждого ассета вернуть `MaterializeResult`/`Output` с метаданными (см. §9.7): число обработанных элементов, размеры артефактов, ссылки на S3.

**Критерий приёмки:** в Dagit виден полный asset graph, топологически совпадающий с §9.1 (12+ ассетов); `dagster asset materialize --select full_ingestion_job` для одного seed-документа проходит от `source_registration` до `retrieval_eval`, создавая узлы в Neo4j и записи в Qdrant/OpenSearch.

### 9.3 Partitions (по документам и по источникам)

- [ ] Создать `DynamicPartitionsDefinition("documents")` в `partitions/` — партиция на каждый `doc_id`; добавлять партицию при регистрации нового документа (из sensor §9.6 и из API-триггера §9.8).
- [ ] Создать `StaticPartitionsDefinition`/`DynamicPartitionsDefinition("sources")` для источников (source id) — для батч-переобработки по источнику/лаборатории.
- [ ] Применить document-partitions к per-document ассетам (`docling_parse` … `qdrant_indexing`/`opensearch_indexing`), чтобы каждый документ материализовался независимо.
- [ ] Настроить `PartitionMapping` (например, `IdentityPartitionMapping`) между документ-партиционированными ассетами; для агрегирующих ассетов (`gap_scan`, `retrieval_eval`) использовать `AllPartitionMapping` (пересканирование по всему корпусу).
- [ ] Добавить `TimeWindowPartitionsDefinition` (daily) для периодических корпус-ассетов (`gap_scan`, `retrieval_eval`, catalog sync) — привязка к schedules §9.5.
- [ ] Реализовать backfill-поддержку: команда/скрипт `dagster job backfill` для переобработки всех документов источника после смены схемы извлечения.
- [ ] Гарантировать идемпотентность per-partition материализации (повторный запуск того же `doc_id` не дублирует узлы благодаря `MERGE` и deterministic IDs из Step 7).

**Критерий приёмки:** каждая загрузка нового документа добавляет partition в `documents`; материализация одной партиции обрабатывает ровно один документ; backfill по источнику переобрабатывает все его документы; `gap_scan`/`retrieval_eval` агрегируют по всем партициям.

### 9.4 Resources и IO managers

- [ ] Реализовать в `resources/` типизированные Dagster-ресурсы (`ConfigurableResource`) с конфигом из env:
  - [ ] `Neo4jResource` (bolt `NEO4J_URI`, auth) — обёртка над `apps/graph-service` Cypher-клиентом.
  - [ ] `QdrantResource` (`qdrant-client`, `QDRANT_URL`).
  - [ ] `OpenSearchResource` (`opensearch-py`, `OPENSEARCH_URL`).
  - [ ] `PostgresResource` (job/source registry, `kg_app`).
  - [ ] `S3Resource`/MinIO (`dagster-aws` S3, endpoint `S3_ENDPOINT`, buckets `kg-raw`/`kg-parsed`).
  - [ ] `DoclingResource` (HTTP-клиент к Docling Serve).
  - [ ] `LLMResource` (клиент schema-guided extraction) и `EmbeddingResource` (`fastembed`/`sentence-transformers`).
  - [ ] `SplinkResource` (конфиг ER-моделей).
  - [ ] `LineageResource` (клиент DataHub/OpenMetadata/OpenLineage — см. §9.8).
  - [ ] `GraphRAGResource`/`GDSResource` (Neo4j GDS или Microsoft GraphRAG) для community detection/summarization ассета `community_summarization`.
  - [ ] `MLflowResource` (§15.3, §13.2 `mlflow`) — логирование метрик extraction/eval-ранов (число фактов, confidence-распределение, стоимость извлечения на документ §15.2).
- [ ] Реализовать `S3IOManager` (или использовать `dagster-aws` `s3_pickle_io_manager`) для промежуточных артефактов (parsed JSON, chunks, extraction outputs) с путями по §9.2.
- [ ] Реализовать `io_managers/parsed_artifact_io_manager.py`, кладущий markdown/JSON/tables в структуру `s3://kg-parsed/documents/{doc_id}/...` (не pickle, а нативные форматы) и возвращающий S3-URI как метаданные.
- [ ] Реализовать `healthcheck_asset` (или `@asset_check`), пингующий все ресурсы (Neo4j/Qdrant/OpenSearch/Postgres/MinIO/Docling/LLM/Embedding/Splink) и возвращающий статус доступности как метаданные.
- [ ] Подключить ресурсы к `Definitions` и параметризовать через env; добавить smoke-тест доступности каждого ресурса (`dagster asset materialize --select healthcheck_asset`).

**Критерий приёмки:** все ассеты получают внешние системы только через ресурсы (никаких глобальных клиентов); healthcheck-ассет успешно подключается к Neo4j/Qdrant/OpenSearch/Postgres/MinIO/Docling; артефакты парсинга физически лежат по путям §9.2.

### 9.5 Schedules

- [ ] Создать файл `schedules/__init__.py` со следующими `ScheduleDefinition`/`@schedule`:
  - [ ] `nightly_gap_scan_schedule` — ежедневный запуск `gap_scan_job` (cron, например `0 2 * * *`), партиция «сегодня».
  - [ ] `nightly_retrieval_eval_schedule` — ежедневный прогон `retrieval_eval` на golden dataset (§15) после gap scan.
  - [ ] `reindex_schedule` — периодический (напр. еженедельный) `reindex_job` + `community_summary_job` для пересчёта community detection и обновления community/neighborhood summaries (GraphRAG/GDS, §10.3) и их переиндексации.
  - [ ] `catalog_sync_schedule` — периодическая синхронизация lineage/каталога в DataHub/OpenMetadata (§9.8).
- [ ] Реализовать логику пропуска (`SkipReason`) в schedules, если нет новых материализаций (не гонять eval вхолостую).
- [ ] Обеспечить работу schedules через `dagster-daemon`; задать `execution_timezone`.
- [ ] Добавить теги запусков schedule (`dagster/schedule_name`, `run_type=scheduled`) для фильтрации в Dagit и в Job status API.

**Критерий приёмки:** в Dagit во вкладке Schedules видны 4 расписания, все включаемы; ручной тик `dagster schedule preview` возвращает валидный `RunRequest`; ночной тик реально запускает `gap_scan_job` и `retrieval_eval`.

### 9.6 Sensors (новые файлы)

- [ ] Создать `sensors/new_document_sensor.py`: `@sensor`, опрашивающий MinIO-бакет `kg-raw` / очередь загрузок Postgres; на новый файл добавляет dynamic partition `doc_id` и эмитит `RunRequest` на `full_ingestion_job` (курсор по последнему обработанному объекту).
- [ ] Создать `sensors/upstream_asset_sensor.py`: `@asset_sensor` на материализацию `graph_upsert`, автоматически запускающий `gap_scan_job` для затронутых партиций.
- [ ] Создать `sensors/reindex_request_sensor.py`: сенсор, слушающий таблицу/очередь запросов `POST /documents/{doc_id}/reindex` (§6.2) и запускающий `reindex_job` для конкретного `doc_id`.
- [ ] Создать `sensors/run_failure_sensor.py`: `@run_failure_sensor`, который при падении run пишет запись в review/alerts (Postgres) и обновляет статус связанного ingest job (§9.9); опционально шлёт уведомление через быстрый фоновый исполнитель (§9.10).
- [ ] Создать `sensors/run_status_sensor.py`: `@run_status_sensor(DagsterRunStatus.SUCCESS/FAILURE)`, синхронизирующий статус Dagster run со статусом `/ingest/jobs/{job_id}` (§9.9).
- [ ] Создать `sensors/ingest_job_sensor.py`: сенсор, слушающий таблицу `ingest_jobs` (запросы из `POST /api/v1/ingest/jobs`) и запускающий соответствующий job с нужным конфигом/партицией.
- [ ] Создать `sensors/catalog_source_sensor.py`: сенсор/scheduled-опрос внешних каталогов и ELN/LIMS (eLabFTW/openBIS REST, §4.1) как источников новых записей (RAW «Raw docs/catalogs», §9.1); регистрирует новые источники через `source_registration` и эмитит `RunRequest` (курсор по последнему импортированному id).
- [ ] Зарегистрировать все sensors в `Definitions`; задать минимальный `minimum_interval_seconds`; реализовать корректные курсоры (idempotent, без повторной обработки).

**Критерий приёмки:** загрузка нового файла в `kg-raw` автоматически (без ручного запуска) приводит к появлению partition и старту `full_ingestion_job`; падение любого ассета создаёт alert-запись и переводит связанный ingest job в статус `failed`; успешное завершение обновляет статус в `succeeded`.

### 9.7 Retries, backoff и обработка сбоев

- [ ] Задать `RetryPolicy` (max_retries, delay, `Backoff.EXPONENTIAL`, `Jitter.PLUS_MINUS`) на «хрупких» ассетах: `docling_parse` (сетевые сбои Docling), `extraction` (LLM/GLiNER таймауты и rate limits), `graph_upsert` (deadlock/transient Neo4j), `qdrant_indexing`/`opensearch_indexing` (сетевые сбои).
- [ ] Дифференцировать retry по типу ошибки: транзиентные (retry) vs схемные/валидационные (fail-fast, без retry, в review) — через `Failure`/`RetryRequested` исключения.
- [ ] Настроить `op_retry_policy`/дефолтную политику в `define_asset_job`; для LLM-извлечения предусмотреть отдельный больший `delay` под rate limits.
- [ ] Реализовать dead-letter путь: элементы, не прошедшие после max_retries, писать в таблицу `ingestion_failures` (Postgres) с контекстом (doc_id, stage, error) для последующего ручного разбора и review-очереди.
- [ ] Настроить run-level `max_concurrent` через `QueuedRunCoordinator` и per-asset concurrency limits (tag concurrency) для защиты Neo4j/LLM от перегрузки.
- [ ] Добавить таймауты на внешние вызовы (Docling, LLM, Neo4j) внутри ресурсов, чтобы retries имели смысл.

**Критерий приёмки:** искусственный транзиентный сбой Docling (напр. остановка контейнера на 1 попытку) автоматически ретраится и завершается успехом; невалидная по схеме запись не ретраится, а попадает в `ingestion_failures`; в Dagit виден счётчик попыток и backoff.

### 9.8 Эмиссия lineage и метаданных запусков

- [ ] Прикреплять к `MaterializeResult`/`Output` каждого ассета `MetadataValue`: число входов/выходов (docs, chunks, entities, edges, vectors), `confidence`-распределение, ссылки на S3-артефакты (`MetadataValue.path`/`url`), `extraction_run_id`, версия схемы.
- [ ] Добавить `run_tags`, связывающие Dagster run с `doc_id`, `source_id`, `ingest_job_id`, `run_type`.
- [ ] Реализовать эмиссию lineage во внешний каталог (Phase 8 §16): через `LineageResource` отправлять OpenLineage-события (Marquez) или напрямую в DataHub/OpenMetadata — датасеты (source, parsed artifact, Neo4j graph, Qdrant collection, OpenSearch index) и рёбра lineage между ними по asset graph §9.1. Использовать git-репозитории из §22: Marquez `https://github.com/MarquezProject/marquez`, DataHub `https://github.com/datahub-project/datahub`, OpenMetadata `https://github.com/open-metadata/OpenMetadata`; для Dagster→каталог применить готовую интеграцию (`dagster-datahub`/OpenLineage-Dagster), а не самописный клиент.
- [ ] Регистрировать в каталоге ownership: source → owner/lab (из Step 1) для admin UI (§5.2.8) и agent metadata context.
- [ ] Настроить хук/`run_status_sensor` для эмиссии сводных run-метаданных (длительность, статус, число фактов) в metadata store и в MLflow (§15.3) через `MLflowResource` по завершении.
- [ ] Обеспечить, чтобы `AssetLineage`/upstream-downstream в Dagit точно отражал §9.1 (визуальная проверка); добавить asset descriptions с ссылкой на шаг §9.2.
- [ ] Логировать через `structlog`/OpenTelemetry (§13.2) идентификаторы run/asset/partition для сквозной трассировки.

**Критерий приёмки:** для каждого материализованного ассета в Dagit видны метаданные (counts, S3-ссылки, `extraction_run_id`); в DataHub/OpenMetadata появляется lineage source→parsed→graph/index; каждый документ имеет owner/lab; run-теги позволяют найти все ассеты одного `ingest_job_id`.

### 9.9 Интеграция с Job status API (§6.2 `/ingest/jobs`)

- [ ] Спроектировать таблицу `ingest_jobs` в Postgres (`kg_app`): `job_id (uuid)`, `dagster_run_id`, `job_type`, `params (jsonb)`, `partition_key`, `status (queued|running|succeeded|failed|canceled)`, `progress`, `created_at`, `updated_at`, `error`.
- [ ] Реализовать `POST /api/v1/ingest/jobs` в `apps/api-gateway/`: создаёт запись `ingest_jobs`, кладёт запрос (через `ingest_job_sensor` §9.6 или напрямую через Dagster GraphQL `launchRun`), возвращает `job_id`.
- [ ] Реализовать `GET /api/v1/ingest/jobs/{job_id}`: читает статус/прогресс из `ingest_jobs`, синхронизированный через `run_status_sensor` (§9.6), возвращает статус, стадию, метрики, ссылки на артефакты и на run в Dagit.
- [ ] Реализовать `POST /api/v1/ingest/jobs/{job_id}/cancel`: вызывает Dagster GraphQL `terminateRun` по `dagster_run_id`, переводит запись в `canceled`.
- [ ] Реализовать клиент Dagster GraphQL/REST в `apps/api-gateway/` (или `apps/ingestion-service/`): `launchRun`, `terminateRun`, `runOrError` (статус), маппинг `DagsterRunStatus` → статус API.
- [ ] Обеспечить обратную синхронизацию: `run_status_sensor`/`run_failure_sensor` (§9.6) обновляют `ingest_jobs.status` при переходах STARTED/SUCCESS/FAILURE/CANCELED.
- [ ] Прокинуть прогресс по стадиям: обновлять `progress`/current stage из метаданных ассетов (§9.8) по мере материализации (через asset materialization sensor или логи).
- [ ] Написать contract-тест соответствия ответов API примеру ingest-job из §6.2 (поля и коды статусов).

**Критерий приёмки:** `POST /api/v1/ingest/jobs` запускает Dagster run и возвращает `job_id`; `GET` отражает реальный статус run (running→succeeded); `cancel` действительно терминирует run в Dagit и выставляет `canceled`; статусы согласованы между Postgres, Dagster и API.

### 9.10 Быстрый фоновый исполнитель (Redis/RQ или Celery) для UI/API-задач

- [ ] Выбрать и зафиксировать в ADR исполнитель для быстрых задач: RQ или Celery поверх Redis (§13.1 сервис `redis`, §1 executive summary — «Redis/RQ или Celery только для быстрых фоновых задач UI/API»); чётко разграничить с Dagster (тяжёлый ingestion) в `README`.
- [ ] Реализовать модуль `apps/api-gateway/tasks/` (или `packages/kg_common/tasks/`) с конфигом брокера (`REDIS_URL`) и определением очередей (`default`, `fast`, `notifications`).
- [ ] Реализовать быстрые задачи, НЕ требующие полного pipeline:
  - [ ] warm-up/инвалидация кэша поиска и graph payload;
  - [ ] генерация/обновление превью документа и page-image crops (§6.2 `/documents/{doc_id}/pages/{page}`);
  - [ ] отправка уведомлений о завершении/падении ingest job (потребитель событий из §9.6);
  - [ ] лёгкий single-doc reindex-триггер (постановка запроса, который затем ловит `reindex_request_sensor` §9.6);
  - [ ] пересчёт мелких UI-агрегатов (счётчики review queue, gap counters).
- [ ] Добавить worker-сервис в `infra/docker-compose.yml` (`worker`, команда `rq worker` или `celery -A ... worker`, `depends_on: [redis]`); при необходимости `scheduler`/`beat` для лёгких периодических UI-задач.
- [ ] Реализовать в API endpoints постановку задач в очередь и получение их статуса (job id очереди), отдельный от Dagster ingest job id.
- [ ] Добавить retry/таймаут-политику и dead-letter для быстрых задач; ограничить их назначение (никакого тяжёлого извлечения/индексации всего документа в этой очереди).
- [ ] Настроить graceful-обработку недоступности Redis (fallback/деградация без падения API).

**Критерий приёмки:** worker поднимается через `docker compose up worker`, обрабатывает быстрые задачи (<неск. секунд), уведомление о завершении ingest job доходит до UI; тяжёлый ingestion идёт исключительно через Dagster, а быстрые UI-задачи — через Redis-очередь; статусы двух систем не смешиваются.

### 9.11 Тестирование, CI и наблюдаемость оркестрации

- [ ] Написать unit-тесты ассетов с mock-ресурсами (`build_asset_context`, поддельные Neo4j/Qdrant/Docling), проверяющие корректные метаданные и зависимости.
- [ ] Написать integration-тест `full_ingestion_job` на 1–2 seed-документах против docker-compose стека (materialize → проверка узлов Neo4j, точек Qdrant, документов OpenSearch).
- [ ] Написать тесты sensors/schedules: `build_sensor_context`/`build_schedule_context`, проверка курсоров, `RunRequest`, `SkipReason`.
- [ ] Написать тест retry-логики (транзиентный vs фатальный сбой) и dead-letter записи.
- [ ] Добавить CI-джобу (по Phase 9 `CI/CD`): `dagster definitions validate`, `ruff`/`mypy` по `infra/dagster`, запуск pytest оркестрации.
- [ ] Подключить OpenTelemetry-трейсинг ассетов (§13.2 `opentelemetry-sdk`) и структурированные логи (`structlog`) с run/asset/partition ids; экспорт compute logs.
- [ ] Реализовать backup/restore метаданных Dagster (Phase 9 §16 «backup/restore»): дамп run/event/schedule storage в Postgres (`kg_app`) и compute logs; документировать процедуру восстановления и smoke-проверку целостности в `README`.
- [ ] Написать `infra/dagster/README.md`: как запускать `dagster dev`, materialize, backfill, как связаны jobs/schedules/sensors/ingest API и быстрый Redis-исполнитель.

**Критерий приёмки:** `pytest infra/dagster` зелёный; CI прогоняет валидацию Definitions и тесты; integration-тест доказывает end-to-end материализацию на seed-данных; трейсы/логи содержат run/asset/partition ids.


---


## 10. Метаданные, lineage и governance (DataHub/OpenMetadata)

Этот раздел покрывает §16 Phase 8 дизайн-документа: выбор и развёртывание платформы каталога метаданных (DataHub или OpenMetadata), регистрацию datasets/documents/источников, эмиссию pipeline-метаданных и lineage из Dagster, ownership и привязку источников к labs, каталог источников в admin UI, audit logs, а также альтернативный backend lineage (Marquez/OpenLineage). Цель раздела (acceptance §16 Phase 8): у каждого document/source есть owner и lineage; каждый pipeline-run трассируем; агент может использовать metadata-контекст.

Затрагиваемые сервисы/пакеты (по §6.1): `apps/api-gateway/`, `apps/ingestion-service/`, `apps/extraction-service/`, `apps/curation-service/`, `apps/agent-service/`, `apps/frontend/`, `packages/kg_common/` (shared DTOs, config, logging), `infra/docker-compose.yml`, `infra/helm/`, `infra/dagster/`, а также новый каталог `infra/metadata/` для конфигов платформы каталога и `third_party/` для вендоринга OSS (§22).

Зависимости от других разделов:
- Раздел по ingestion pipeline (§9): Step 1 «source registration» (§9.2, эмиссия в Postgres **и** DataHub, см. диаграмму §9.1 `REGISTER[Register source in Postgres/DataHub]`) — точка эмиссии метаданных источника; шаги parse/chunk/extract/normalize/ER/upsert/index — узлы lineage.
- Раздел по orchestration/Dagster (§13.1 сервис `dagster`, `infra/dagster/`) — источник pipeline-метаданных.
- Раздел по curation (§12): `CurationEvent` (§12.3, enum action/target_type) — источник audit-событий governance.
- Раздел по extraction (§9.2 Step 4, §8.3 `extractor`/`model`, §8.2 `ExtractorRun`): источник AI/model-lineage (MLflow, §10.13).
- Раздел по schema (§8.1 core labels, §8.2 relationships): доменный словарь для glossary/маппинга.
- Раздел по gap-analysis (§5.2.7 Gap Dashboard «missing metadata by lab/team»): потребитель ownership-audit (§10.6).
- Раздел по frontend (§5.1): выбор граф-компонентов — ELK.js/dagre для lineage-layout, React Flow для pipeline-DAG, Reagraph для neighborhood.
- Раздел по agent (§7): регистрация metadata-tool для узлов агента.
- Раздел по auth/RBAC (§16 Phase 9): роли для доступа к governance UI и audit logs.
- OSS-репозитории темы (§22 «Metadata / orchestration / lineage»): DataHub, OpenMetadata, Marquez, Apache Atlas, MLflow, lakeFS, DVC, Airbyte.

### 10.1 Выбор платформы (DataHub vs OpenMetadata) и вендоринг OSS

- [ ] Написать ADR `docs/adr/0010-metadata-platform.md` с решением DataHub **или** OpenMetadata; включить матрицу сравнения по критериям: поддержка кастомных entity/aspect, качество lineage (в т.ч. dataset/column-level), Python emitter SDK, интеграция с Dagster, ресурсоёмкость стека (Kafka/ES/MySQL vs ES/Postgres), встраиваемость каталога в admin UI, лицензия.
- [ ] Зафиксировать в ADR выбор backend для lineage: primary (native lineage выбранной платформы) и alternative (Marquez + OpenLineage, см. §10.9); указать feature-flag `METADATA_LINEAGE_BACKEND=datahub|openmetadata|marquez` и `METADATA_PLATFORM=datahub|openmetadata` (выбор адаптера, см. §10.4).
- [ ] Зафиксировать в ADR флаг полного отключения стека каталога для MVP: `METADATA_STACK_ENABLED=false` (риск §18 «disable OpenSearch/DataHub for MVP if needed») — при выключении ingestion работает в graceful-degradation (§10.4), platform-profile не поднимается (§10.2).
- [ ] Оценить в ADR смежные OSS темы из §22 (`Airbyte`, `MLflow`, `lakeFS`, `DVC`) для data/AI-lineage и версионирования артефактов; зафиксировать решение integrate|skip с обоснованием (детали интеграции — §10.13).
- [ ] Клонировать/вендорить репозитории в `third_party/` с фиксацией версии (git tag/commit в `third_party/VERSIONS.lock`):
  - [ ] `git clone https://github.com/datahub-project/datahub third_party/datahub` (если выбран DataHub);
  - [ ] `git clone https://github.com/open-metadata/OpenMetadata third_party/openmetadata` (если выбран OpenMetadata);
  - [ ] `git clone https://github.com/MarquezProject/marquez third_party/marquez` (alternative lineage backend, обязателен независимо от primary-выбора);
  - [ ] (опционально, для справки) `git clone https://github.com/apache/atlas third_party/atlas` — только как reference, не для деплоя;
  - [ ] смежные OSS темы (клонировать только при решении integrate в ADR, иначе reference): `git clone https://github.com/mlflow/mlflow third_party/mlflow`, `git clone https://github.com/treeverse/lakeFS third_party/lakefs`, `git clone https://github.com/iterative/dvc third_party/dvc`, `git clone https://github.com/airbytehq/airbyte third_party/airbyte` (§10.13).
- [ ] Зафиксировать pinned-версии образов и Python-пакетов SDK в `packages/kg_common/pyproject.toml` (или requirements): `acryl-datahub` (для DataHub) либо `openmetadata-ingestion` (для OpenMetadata), плюс `openlineage-python` и `openlineage-dagster`; при решении integrate — `mlflow` (уже в §13.2), клиенты `lakefs`/`dvc`.
- [ ] Добавить выбранный SDK в общий список Python-пакетов проекта (§13.2) и в lockfile.

**Критерий приёмки:** файл `docs/adr/0010-metadata-platform.md` содержит принятое решение с матрицей сравнения, зафиксированные флаги `METADATA_PLATFORM`/`METADATA_LINEAGE_BACKEND`/`METADATA_STACK_ENABLED` и решение integrate|skip по Airbyte/MLflow/lakeFS/DVC; `third_party/VERSIONS.lock` содержит зафиксированные commit-hash для datahub/openmetadata и marquez; выбранный emitter-SDK устанавливается в CI (`pip install` проходит без ошибок).

### 10.2 Развёртывание платформы каталога (Docker Compose + Helm)

- [ ] Создать `infra/metadata/docker-compose.metadata.yml` с полным стеком выбранной платформы:
  - [ ] для DataHub: сервисы `datahub-gms`, `datahub-frontend-react` (порт `9002`), `datahub-actions`, `elasticsearch` (или переиспользовать `opensearch` из §13.1 через совместимый режим), `mysql`/`postgres`, `kafka` + `zookeeper`/`kraft`, `schema-registry`;
  - [ ] для OpenMetadata: сервисы `openmetadata-server` (порт `8585`), `openmetadata-ingestion` (airflow), `elasticsearch`/`opensearch`, `mysql`/`postgres`.
- [ ] Прописать в каждом сервисе healthcheck (HTTP ping GMS `/health` для DataHub или `/healthcheck` для OpenMetadata) и `depends_on` с `condition: service_healthy`.
- [ ] Интегрировать стек метаданных в корневой `infra/docker-compose.yml` через `include:`/`extends` или profile `metadata`, чтобы `docker compose --profile metadata up` поднимал каталог рядом с основным стеком (§13.1).
- [ ] Переиспользовать существующий `postgres` (§13.1, `POSTGRES_DB: kg_app`) для хранилища платформы, создав отдельную БД `metadata` (init-скрипт в `infra/metadata/initdb/`), либо явно обосновать отдельный инстанс в ADR.
- [ ] Вынести все секреты/креды в `.env` и обновить `.env.example` переменными: `METADATA_PLATFORM`, `DATAHUB_GMS_URL`/`OPENMETADATA_SERVER_URL`, `METADATA_AUTH_TOKEN`, `METADATA_LINEAGE_BACKEND`, `METADATA_EMISSION_ENABLED`, `METADATA_STACK_ENABLED`, `MARQUEZ_URL`.
- [ ] Обеспечить полное отключение стека для MVP: при `METADATA_STACK_ENABLED=false` (или отсутствии profile `metadata`) корневой `docker compose up` поднимает только основной стек §13.1 без каталога, ingestion продолжает работать (graceful degradation §10.4) — реализует риск-митигацию §18 «disable DataHub for MVP if needed».
- [ ] Создать Helm-чарты в `infra/helm/metadata/` (или values для upstream-чартов datahub/openmetadata) с ресурсными лимитами, persistent volumes для ES и БД, ingress для UI.
- [ ] Добавить `infra/metadata/README.md` с командами первичного bootstrap (создание индексов ES, применение миграций, генерация service-token для emitter).
- [ ] Добавить smoke-скрипт `infra/metadata/scripts/wait_healthy.sh`, опрашивающий health-эндпоинты до готовности (используется в CI и локально).

**Критерий приёмки:** `docker compose --profile metadata up -d` поднимает все сервисы платформы; health-эндпоинт GMS/OpenMetadata возвращает `200`; UI каталога открывается в браузере (DataHub `http://localhost:9002` или OpenMetadata `http://localhost:8585`); `wait_healthy.sh` завершается с кодом `0`; при `METADATA_STACK_ENABLED=false` основной стек поднимается без сервисов каталога.

### 10.3 Модель метаданных: маппинг доменных сущностей на entities каталога

- [ ] Описать в `docs/metadata/entity-mapping.md` маппинг доменных объектов системы на entity-типы платформы каталога:
  - [ ] `Source` (реестр источников из §9.2 Step 1) → dataset/container с custom-aspect `sourceType`, `fileHash`, `accessPolicy`, `version`, `ingestionJobId`;
  - [ ] `Document`/`Paper` (§8.1 labels) → dataset или отдельный custom entity `Document` с полями `doc_id`, `page_count`, `parsed_uri`, `raw_uri`;
  - [ ] `Project` (§8.1 label) → Data Product/Domain-группировка (см. §10.6); `Dataset` (§8.1 label) → dataset каталога; `Method` (§8.1 label) → glossary term/классификация;
  - [ ] хранилища как platform/dataPlatform: Neo4j (граф KG), Qdrant (vector collections), OpenSearch (keyword indices), MinIO/S3 buckets (`kg-raw`, `kg-parsed`, а также `kg-audit` из §10.8), Postgres (app tables).
- [ ] Зафиксировать URN-схему для всех объектов (например `urn:li:dataset:(urn:li:dataPlatform:kg-source,{source_id},PROD)` для DataHub) в `packages/kg_common/metadata/urns.py`.
- [ ] Определить custom aspects/properties (DataHub: `customProperties` + опционально кастомная модель; OpenMetadata: custom properties на entity type) для evidence-first полей: `confidence`, `review_status`, `extractor`, `model` (из §8.3 Evidence) и ссылку `extractor_run_id`/`mlflow_run_id` (§8.2 `ExtractorRun`, §10.13).
- [ ] Создать бизнес-глоссарий (Glossary) с полным доменным словарём core labels §8.1: `Material`, `Alloy`, `ChemicalElement`, `Composition`, `ProcessingRegime`, `ProcessingStep`, `Parameter`, `Equipment`, `Experiment`, `Sample`, `Property`, `Measurement`, `Unit`, `Method`, `Claim`, `Finding`, `Evidence`, `Gap`, `Contradiction`, `Lab`, `ResearchTeam`, `Person`, `Project`, `Decision` и связать их с datasets как glossary terms.
- [ ] Определить tags/классификации: `access:public|internal|restricted`, `pii:none`, `quality:verified|pending`, `domain:materials`.
- [ ] Реализовать регистрацию всех вышеперечисленных platform/dataPlatform как idempotent-bootstrap `packages/kg_common/metadata/bootstrap_platforms.py` (создаёт dataPlatform-записи `kg-source`, `neo4j-kg`, `qdrant`, `opensearch`, `minio`, `postgres`).

**Критерий приёмки:** `docs/metadata/entity-mapping.md` описывает маппинг каждого доменного объекта; запуск `bootstrap_platforms.py` создаёт все dataPlatform и glossary terms в каталоге (проверяется API каталога — записи присутствуют); URN-схема покрыта unit-тестами в `packages/kg_common/tests/test_urns.py`.

### 10.4 Metadata client и регистрация datasets/documents/источников

- [ ] Реализовать общий клиент метаданных `packages/kg_common/metadata/client.py` с абстракцией `MetadataClient` и адаптерами `DataHubAdapter` / `OpenMetadataAdapter` (выбор по `METADATA_PLATFORM` env), методы: `register_source()`, `register_document()`, `register_dataset()`, `emit_lineage()`, `set_owner()`, `add_tags()`, `upsert_schema()`.
- [ ] Реализовать Pydantic-DTO `SourceMetadata`, `DocumentMetadata`, `DatasetMetadata` в `packages/kg_common/metadata/models.py`, соответствующие полям §9.2 Step 1 (source id, file hash, source type, owner/lab, access policy, ingestion job id, version).
- [ ] Встроить вызов `register_source()` в ingestion Step 1 (`apps/ingestion-service/`, source registration) — при регистрации источника в Postgres одновременно эмитировать метаданные в каталог (транзакционно/через outbox, чтобы избежать рассинхрона).
- [ ] Встроить `register_document()` после Docling-парсинга (§9.2 Step 2) с ссылками на `s3://kg-raw/...` и `s3://kg-parsed/...` (raw/parsed URI).
- [ ] Зарегистрировать индексируемые артефакты после §9.2 Step 8 (indexing): Qdrant collection и OpenSearch index как datasets с их schema (поля векторов, размерность, метрика).
- [ ] Зарегистрировать Neo4j KG как dataset/container со schema, отражающей core labels и relationships (§8.1, §8.2).
- [ ] Реализовать батч-скрипт `apps/ingestion-service/scripts/backfill_metadata.py` для ретроспективной регистрации уже существующих источников/документов из Postgres в каталог.
- [ ] Обеспечить идемпотентность эмиссии (повторный ingest того же `source_id`/`file_hash` обновляет, а не дублирует запись).
- [ ] Добавить настройку `METADATA_EMISSION_ENABLED=true|false` (graceful degradation: при недоступности каталога ingestion не падает, а логирует и ставит событие в retry-очередь Redis).

**Критерий приёмки:** после загрузки тестового документа через `POST /api/v1/documents/upload` в каталоге появляются запись source, запись document (с raw/parsed URI) и связанные dataset-записи Neo4j/Qdrant/OpenSearch; повторная загрузка того же файла не создаёт дубликатов; при остановленном каталоге ingestion завершается успешно и событие попадает в retry-очередь.

### 10.5 Эмиссия pipeline-метаданных и lineage из Dagster

- [ ] Подключить интеграцию Dagster→каталог в `infra/dagster/`: для DataHub — sensor/hook на базе `acryl-datahub` (Dagster Actions/OpenLineage); для OpenMetadata — connector; плюс базовый слой `openlineage-dagster` для унификации.
- [ ] Определить Dagster assets/ops для каждого шага pipeline (§9.1, включая узел `STORE`): `register_source`, `docling_parse`, `store_parsed_s3`, `chunk`, `extract`, `normalize_units`, `entity_resolution`, `validate_schema`, `neo4j_upsert`, `qdrant_index`, `opensearch_index`, `gap_scan`, `retrieval_eval`.
- [ ] Реализовать эмиссию lineage-графа inputs→outputs, отражающего поток §9.1: `RAW → source → docling.json/document.md → chunks → extracted triples → normalized → resolved → Neo4j KG + Qdrant + OpenSearch`.
- [ ] Эмитировать run-level метаданные каждого прогона: `job_id` (совпадает с `POST /api/v1/ingest/jobs`), статус (success/failed), длительность, число обработанных документов/чанков/триплетов, версия extractor (`extractor`/`model` из §8.3).
- [ ] Реализовать column/field-level lineage там, где применимо (например, поля extraction schema → свойства узлов Neo4j).
- [ ] Прокинуть в lineage-метаданные ссылку на ingestion job (`ingestion_job_id`), чтобы связать pipeline-run с зарегистрированными source/document (§10.4).
- [ ] Добавить обработку падений: при failed-run эмитировать run со статусом `FAILED` и сообщением об ошибке (для трассируемости).
- [ ] Написать интеграционный тест `infra/dagster/tests/test_lineage_emission.py`: прогон mini-pipeline на 1 seed-документе создаёт полную цепочку lineage в каталоге.

**Критерий приёмки:** после прогона Dagster ingestion-job в UI каталога виден end-to-end lineage-граф от raw-source до Neo4j/Qdrant/OpenSearch; каждый run отображается со статусом, длительностью и `job_id`; failed-run отображается как FAILED; интеграционный тест `test_lineage_emission.py` проходит.

### 10.6 Ownership и привязка источников к labs/teams

- [ ] Синхронизировать `Person`, `ResearchTeam`, `Lab` (core labels §8.1) в users/groups каталога: DataHub `CorpUser`/`CorpGroup`, OpenMetadata `User`/`Team`; реализовать sync-скрипт `packages/kg_common/metadata/sync_owners.py` из Postgres/Neo4j.
- [ ] При регистрации источника (§10.4) проставлять owner и lab: маппинг `owner/lab` из §9.2 Step 1 на ownership-aspect каталога (owner type: `DATAOWNER`/`TECHNICAL_OWNER`).
- [ ] Создать Domains/Data Products (DataHub Domains или OpenMetadata Domains) по лабораториям: каждый `Lab` → отдельный domain; привязать источники/датасеты этого лаба к домену.
- [ ] Прокинуть access policy (§9.2 Step 1 `access policy`) в теги/классификации каталога (`access:public|internal|restricted`).
- [ ] Реализовать валидацию полноты: batch-джоб `packages/kg_common/metadata/audit_ownership.py`, который находит источники/документы без owner или без lab и создаёт curation-таски/предупреждения.
- [ ] Прокинуть результаты `audit_ownership.py` в Gap Dashboard §5.2.7 (панель «missing metadata by lab/team») как источник данных для этой категории пробелов.
- [ ] Настроить обратную связь UI→каталог: при merge/split/alias в curation (§12.2) владелец затронутого источника не теряется (owner переносится).

**Критерий приёмки:** `audit_ownership.py` для seed-корпуса возвращает пустой список нарушений — у каждого document/source есть owner и lab (соответствует acceptance §16 Phase 8 «every document/source has owner and lineage»); в UI каталога источники сгруппированы по domain=лаборатория; access policy отображается тегом.

### 10.7 Каталог источников в admin UI

- [ ] Добавить в `apps/api-gateway/` эндпоинты-прокси к платформе каталога (расширение admin-неймспейса §6.2):
  - [ ] `GET /api/v1/admin/catalog/sources?q=&lab=&owner=&access=` — список/поиск источников;
  - [ ] `GET /api/v1/admin/catalog/sources/{source_id}` — карточка источника (owner, lab, версия, hash, access policy, freshness);
  - [ ] `GET /api/v1/admin/catalog/sources/{source_id}/lineage` — lineage-граф (upstream/downstream);
  - [ ] `GET /api/v1/admin/catalog/datasets/{urn}` — карточка dataset (Neo4j/Qdrant/OpenSearch/document).
- [ ] Реализовать серверный слой `apps/api-gateway/services/catalog_gateway.py`, вызывающий `MetadataClient` (кэширование в Redis, TTL, устойчивость к недоступности каталога).
- [ ] Расширить экран Admin/Curation (§5.2.8) вкладкой «Source Catalog» в `apps/frontend/`: таблица источников с фильтрами (lab, owner, access, freshness), карточка источника, встроенный просмотр lineage-графа. Для lineage/pipeline-DAG использовать hierarchical layout ELK.js/dagre или React Flow (per §5.1: «ELK.js / dagre — для lineage, pipeline, decision history»; «React Flow — pipeline DAG»); Reagraph (§5.2.3) — для neighborhood-представления связанных сущностей.
- [ ] Отобразить на карточке источника: pipeline-runs, коснувшиеся источника (из §10.5), статус последнего ingest, число извлечённых evidence/claims.
- [ ] Добавить deep-link «Открыть в каталоге» (внешняя ссылка на native UI DataHub/OpenMetadata) для расширенного просмотра.
- [ ] Покрыть новые эндпоинты OpenAPI-схемой и контрактными тестами в `apps/api-gateway/tests/test_catalog_endpoints.py`.

**Критерий приёмки:** во frontend Admin открывается вкладка «Source Catalog», отображающая список источников с owner/lab/lineage; клик по источнику показывает карточку и lineage-граф; `GET /api/v1/admin/catalog/sources` возвращает данные каталога (контрактный тест зелёный); при недоступном каталоге UI показывает graceful-fallback вместо ошибки 500.

### 10.8 Audit logs

- [ ] Спроектировать append-only audit-хранилище в Postgres: таблица `audit_log` (`id`, `actor_id`, `action`, `target_type`, `target_id`, `before`, `after`, `reason`, `ip`, `request_id`, `created_at`) — согласовано со схемой `CurationEvent` (§12.3): `action ⊇ {accept, reject, correct, merge, split, alias_add, schema_change}` (расширить API-действиями `upload`, `ingest`, `review`, admin-мутациями), `target_type ⊇ {node, edge, evidence, schema}` (расширить `source`, `document`, `job`).
- [ ] Реализовать audit-middleware в `apps/api-gateway/middleware/audit.py`: логировать все мутационные запросы (POST/PUT/PATCH/DELETE), особенно `entities/merge`, `evidence/{id}/review`, `documents/upload`, `ingest/jobs`, admin-действия (§6.2) — писать actor, endpoint, payload-diff, request_id.
- [ ] Эмитировать `CurationEvent` (§12.3, curation-service) одновременно в `audit_log` и (опционально) в каталог как metadata-события/institutional memory.
- [ ] Обеспечить неизменяемость audit-лога: запретить UPDATE/DELETE на уровне БД (только INSERT), хранить cryptographic hash-chain (`prev_hash`→`hash`) для tamper-evidence.
- [ ] Реализовать эндпоинты чтения audit-лога: `GET /api/v1/admin/audit?actor=&action=&target_type=&target_id=&from=&to=` с пагинацией и RBAC (только роль admin/curator).
- [ ] Отобразить audit-лог во frontend Admin (§5.2.8): фильтруемая таблица событий с diff before/after.
- [ ] Настроить retention/архивацию audit-лога (экспорт старых записей в MinIO `s3://kg-audit/` по расписанию Dagster).
- [ ] Написать тесты: попытка UPDATE/DELETE записи audit_log отклоняется; hash-chain непрерывен; мутационный API-вызов создаёт ровно одну audit-запись.

**Критерий приёмки:** любой мутационный запрос (напр. `POST /api/v1/entities/merge`) создаёт запись в `audit_log` с actor/before/after/request_id; UPDATE/DELETE по `audit_log` отклоняется на уровне БД; `GET /api/v1/admin/audit` возвращает отфильтрованный список только для авторизованных ролей; hash-chain проверяется тестом без разрывов.

### 10.9 Alternative lineage backend: Marquez + OpenLineage

- [ ] Добавить сервис `marquez` (API + web) в `infra/metadata/docker-compose.metadata.yml` под profile `marquez` (образ из склонированного `third_party/marquez`), с БД Postgres.
- [ ] Настроить эмиссию OpenLineage-событий из Dagster (`openlineage-dagster`) на Marquez endpoint `MARQUEZ_URL` параллельно/альтернативно primary-каталогу.
- [ ] Реализовать переключение backend через `METADATA_LINEAGE_BACKEND=datahub|openmetadata|marquez` в `packages/kg_common/metadata/lineage.py` (единый интерфейс `LineageEmitter`, реализации для каждого backend).
- [ ] Убедиться, что цепочка §9.1 (RAW→...→Neo4j/Qdrant/OpenSearch) корректно отображается в Marquez UI при выбранном backend=marquez.
- [ ] Задокументировать в `docs/metadata/lineage-backends.md` компромиссы и процедуру переключения.

**Критерий приёмки:** при `METADATA_LINEAGE_BACKEND=marquez` прогон ingestion-job создаёт полный lineage-граф в Marquez UI (`http://localhost:5000`/`3000`); переключение backend не требует изменения кода pipeline (только env); документ `lineage-backends.md` описывает процедуру.

### 10.10 Metadata-контекст для агента

- [ ] Реализовать agent-tool `get_source_provenance` в `apps/agent-service/` (регистрация среди tools §7.4): по `doc_id`/`source_id`/`entity_id` возвращает owner, lab, версию, freshness, extractor/model, review_status и lineage-краткое из каталога.
- [ ] Подключить tool к узлам агента `evidence_assembler` (§7.5 Node 8) и `verifier` (Node 9): при сборке evidence прикладывать provenance/freshness, при верификации помечать устаревшие/непроверенные источники.
- [ ] Прокинуть provenance-поля в ответный контракт (§6.2 «Пример ответа», блок `citations`): к каждой citation добавить owner/lab/version/freshness.
- [ ] Написать тест агентского сценария: запрос по материалу возвращает ответ, в citations которого присутствуют provenance-поля из каталога.

**Критерий приёмки:** agent-tool `get_source_provenance` возвращает метаданные из каталога; в стриме/ответе агента citations содержат owner/lab/version/freshness (соответствует acceptance §16 Phase 8 «agent can use metadata context»); тест сценария зелёный.

### 10.11 Governance-политики, классификации, retention

- [ ] Определить и загрузить в каталог governance-политики: access-классификации (`public|internal|restricted`), PII-теги (для полей Person/ResearchTeam), quality-теги (`verified|pending` из §8.3 review_status).
- [ ] Реализовать автоматическое проставление quality-тега на dataset/document по агрегату review_status связанных evidence (§8.3): если доля accepted ниже порога — тег `quality:pending`.
- [ ] Определить data retention policy per source-type и зафиксировать в `docs/metadata/governance.md` (что и как долго хранится в `kg-raw`/`kg-parsed`/`audit`).
- [ ] Реализовать проверку соответствия (compliance check) Dagster-джобом `governance_audit`: находит datasets без domain, без owner, без access-тега — эмитирует отчёт и создаёт curation-таски.
- [ ] Настроить RBAC-политики доступа к каталогу (native policies DataHub/OpenMetadata): curator видит все источники, обычный пользователь — только public/internal (согласовать с §16 Phase 9 RBAC).

**Критерий приёмки:** каждый dataset в каталоге имеет access-тег и quality-тег; `governance_audit` для seed-корпуса возвращает 0 нарушений; `docs/metadata/governance.md` описывает retention; неавторизованный пользователь не видит restricted-источники в каталоге (проверяется тестом политики).

### 10.12 Тесты, seed, CI и документация

- [ ] Создать seed-скрипт `infra/metadata/seed_metadata.py`, регистрирующий 10 seed-документов (из §Phase 0) с owner/lab/domain/lineage для демо и e2e-тестов.
- [ ] Написать e2e-тест `tests/e2e/test_metadata_governance.py`: upload документа → регистрация source/document → прогон Dagster → lineage в каталоге → provenance доступен агенту → audit-запись создана.
- [ ] Добавить в CI job `metadata-ci`: поднять минимальный стек каталога (или mock/testcontainers), прогнать unit/contract/e2e тесты раздела, проверить bootstrap платформ.
- [ ] Написать `docs/metadata/README.md` — обзор архитектуры метаданных/lineage/governance, диаграмма потоков, инструкции эксплуатации (bootstrap, backfill, переключение lineage backend).
- [ ] Добавить runbook `docs/metadata/runbook.md`: восстановление каталога, ре-эмиссия метаданных, ротация service-token, обработка рассинхрона Postgres↔каталог.

**Критерий приёмки:** `seed_metadata.py` наполняет каталог демо-данными; e2e-тест `test_metadata_governance.py` проходит полный путь upload→lineage→provenance→audit; CI job `metadata-ci` зелёный; документация `README.md` и `runbook.md` присутствуют и описывают все процедуры раздела.

### 10.13 Data & AI lineage: версионирование артефактов и model tracking (MLflow / lakeFS / DVC / Airbyte)

Этот подраздел закрывает оставшиеся OSS-репозитории темы из §22 «Metadata / orchestration / lineage» (MLflow, lakeFS, DVC, Airbyte), расширяя lineage до AI/model-контекста (line 23 «Data/AI context») и версионирования артефактов. Каждая интеграция включается только при решении `integrate` в ADR §10.1; иначе фиксируется как reference с обоснованием skip.

- [ ] Развернуть MLflow tracking (переиспользовать пакет `mlflow` из §13.2; при деплое — сервис `mlflow` в `infra/metadata/docker-compose.metadata.yml` под profile `metadata`, backend store — Postgres `metadata`, artifact store — MinIO `s3://kg-mlflow/`).
- [ ] Логировать каждый extraction-run (§9.2 Step 4, задача §16 Phase 2 «create extraction run metadata») как MLflow run: параметры `extractor`, `model` (§8.3), метрики (число извлечённых триплетов/evidence, доля с evidence-span), артефакты (extraction schema/prompt-версия).
- [ ] Связать `ExtractorRun` (§8.2 `(:Evidence)-[:EXTRACTED_BY]->(:ExtractorRun)`) ↔ MLflow `run_id` ↔ dataset/lineage в каталоге (пробросить `mlflow_run_id` в custom-aspect §10.3 и в lineage-run §10.5).
- [ ] Настроить версионирование бакетов `s3://kg-raw`/`s3://kg-parsed` (§9.2) через lakeFS **или** DVC (по решению ADR): каждый ingest создаёт commit/data-version, поле `version` источника (§9.2 Step 1) ссылается на data-version; отразить политику в retention/governance (§10.11) и runbook (§10.12).
- [ ] Реализовать в `packages/kg_common/metadata/versioning.py` абстракцию `ArtifactVersioner` с адаптерами `LakeFSVersioner`/`DVCVersioner`/`NoopVersioner` (выбор по env `ARTIFACT_VERSIONING=lakefs|dvc|none`).
- [ ] Airbyte — зафиксировать как reference для будущих коннекторов внешних каталогов/источников метаданных (не деплой в MVP); при решении integrate — задокументировать connector→DataHub/OpenMetadata lineage.
- [ ] Прокинуть `mlflow_run_id` и data-version в provenance-tool агента (§10.10) и в `citations` ответа (§6.2) как расширение provenance.
- [ ] Добавить `.env`-переменные: `MLFLOW_TRACKING_URI`, `ARTIFACT_VERSIONING`, `LAKEFS_ENDPOINT`/`DVC_REMOTE` (обновить `.env.example`).

**Критерий приёмки:** extraction-run создаёт MLflow run с параметрами `extractor`/`model` и метриками; соответствующий dataset/lineage в каталоге ссылается на `mlflow_run_id`; при `ARTIFACT_VERSIONING=lakefs|dvc` каждый ingest фиксирует data-version, на которую ссылается `version` источника; ADR §10.1 содержит решение integrate|skip по MLflow/lakeFS/DVC/Airbyte; provenance агента (§10.10) включает `mlflow_run_id`/data-version.


---


## 11. GraphRAG (community summaries)

Раздел реализует **Mode C** из §10.1 — GraphRAG community summaries: reference-пайплайн для глобальных вопросов по корпусу (broad overview, «какие направления были в теме», «что известно в целом», multi-document synthesis). Основа — вендоренный `microsoft/graphrag` (§22, git-URL: https://github.com/microsoft/graphrag). Пайплайн строит иерархический граф сообществ (Leiden) и community summaries, которые индексируются в Qdrant (§9, Step 8 indexing, payload-схема §9.8) и/или в Neo4j (§8), периодически перестраиваются через Dagster (`infra/dagster/`) и подключаются к LangGraph-агенту (§7) как один из retrieval-режимов. Ключевое ограничение дизайна (§1, §4.1): GraphRAG **не должен становиться единственным retrieval core** — он дополняет structured (Mode A), hybrid (Mode B) и graph-algorithms (Mode D) режимы.

Зависимости от других разделов:
- §9 Ingestion: парсенный корпус (Markdown/JSON в MinIO/S3), chunking, Step 8 indexing.
- §8 Knowledge graph schema: расширение схемы новыми labels `Community`, `CommunityReport`.
- §7 Agent system: маршрут `ROUTE -->|global corpus| GRAG`, tools, nodes.
- §10 Retrieval strategy: `graph_proximity_score` использует «same community» = 0.2.
- §6.1/§6.2 Backend services и endpoints; §13 Docker Compose и Python packages; §15 Evaluation.

Затрагиваемые сервисы/пакеты (§6.1): `apps/search-service/`, `apps/agent-service/`, `apps/ingestion-service/`, `apps/api-gateway/`, `packages/kg_retrievers/`, `packages/kg_common/`, `infra/dagster/`, `infra/docker-compose.yml`.

---

### 11.1 Вендоринг microsoft/graphrag и структура модуля

- [ ] Клонировать `microsoft/graphrag` (https://github.com/microsoft/graphrag) в `vendor/graphrag/`, зафиксировать конкретный тег/commit в `vendor/graphrag/VERSION.txt` (записать `git rev-parse HEAD` и tag).
- [ ] Проверить лицензию (MIT) и добавить её в `vendor/graphrag/LICENSE` и в реестр лицензий проекта `docs/licenses/THIRD_PARTY.md` с указанием версии.
- [ ] Принять решение о способе использования и зафиксировать в ADR `docs/adr/0011-graphrag-integration.md`: (а) `graphrag` как pip-зависимость с pinned-версией vs (б) частичный вендоринг форкнутых модулей; по умолчанию — pip-зависимость, vendor-каталог как источник справки и кастомных промптов.
- [ ] Добавить `graphrag` (с pinned версией, совпадающей с `VERSION.txt`) в `apps/ingestion-service/pyproject.toml` и в общий список из §13.2 (`requirements`/`pyproject`), не ломая версии `llama-index`, `qdrant-client`, `neo4j`.
- [ ] Создать пакет-обёртку `packages/kg_retrievers/graphrag/` с модулями: `__init__.py`, `config.py`, `input_adapter.py`, `pipeline.py`, `qdrant_store.py`, `neo4j_store.py`, `global_search.py`, `local_search.py`, `artifacts.py`, `versioning.py`.
- [ ] Зафиксировать в ADR (`docs/adr/0011-graphrag-integration.md`) выбор `microsoft/graphrag` как reference-пайплайна (§4.1, таблица: «GraphRAG baseline») вместо самостоятельной реализации community-суммаризации; отметить `LlamaIndex PropertyGraphIndex` (§22, https://github.com/run-llama/llama_index) как рассмотренную альтернативу и причину отклонения.
- [ ] Явно запретить написание собственных graph/community-алгоритмов (§4.1: «Не писать graph algorithms», §20: не строить своё): кластеризация (Leiden) и community reports берутся из vendored `graphrag`, community/centrality Mode D — из Neo4j GDS; в коде обёртки не должно быть кастомной реализации clustering.
- [ ] Прогнать smoke-тест установки: `python -c "import graphrag; print(graphrag.__version__)"` возвращает pinned-версию; результат зафиксирован в CI job `graphrag-smoke`.

**Критерий приёмки:** `pip install`/`uv sync` в `ingestion-service` проходит без конфликтов зависимостей; `import graphrag` даёт зафиксированную в `VERSION.txt` версию; ADR и запись о лицензии присутствуют в репозитории.

---

### 11.2 Конфигурация GraphRAG pipeline (settings.yaml, prompts, LLM/embeddings)

- [ ] Создать каталог конфигурации `infra/graphrag/` c `settings.yaml`, `.env.example`, `prompts/` и `README.md`.
- [ ] Сгенерировать базовый конфиг командой `graphrag init --root infra/graphrag` и закоммитить полученные `settings.yaml` и `prompts/*`.
- [ ] В `settings.yaml` настроить LLM-провайдера (chat model) и embeddings через переменные окружения (`GRAPHRAG_API_KEY`, `GRAPHRAG_LLM_MODEL`, `GRAPHRAG_EMBEDDING_MODEL`), согласовав embedding-модель с той, что используется в §9 Step 8 / §10 (single source of truth в `packages/kg_common/config.py`).
- [ ] Настроить `chunks` в `settings.yaml` (size/overlap) согласованно с chunking-стратегией из §9.3, чтобы `text_units` GraphRAG совпадали по границам с `Chunk` из графа (для трассируемости evidence, п. 11.11).
- [ ] Настроить `input` на кастомный адаптер (п. 11.3): storage type, base_dir, file pattern.
- [ ] Настроить `snapshots`/`storage`/`cache` на MinIO/S3 (`storage.type: blob` или локальный том, монтируемый из MinIO), путь артефактов `graphrag/output/<build_id>/`.
- [ ] Настроить `community_reports` (max length, max input length) и `cluster_graph` (Leiden, `max_cluster_size`) параметры; зафиксировать выбранные значения в комментариях `settings.yaml`.
- [ ] Выполнить prompt-tuning под научный корпус: `graphrag prompt-tune --root infra/graphrag --domain "materials science / experimental results"`, закоммитить адаптированные промпты в `infra/graphrag/prompts/` (entity extraction, community report, summarize descriptions).
- [ ] Добавить конфиг-валидатор `packages/kg_retrievers/graphrag/config.py::load_and_validate_settings()` (Pydantic), который читает `settings.yaml`, проверяет обязательные ключи и падает с внятной ошибкой при отсутствии модели/ключей.

**Критерий приёмки:** `graphrag index --root infra/graphrag --dry-run` (или эквивалентная валидация конфига) проходит без ошибок; `load_and_validate_settings()` возвращает валидный объект для закоммиченного `settings.yaml`; embedding-модель в GraphRAG идентична модели §9/§10.

---

### 11.3 Входной адаптер: корпус проекта → GraphRAG input

- [ ] Реализовать `packages/kg_retrievers/graphrag/input_adapter.py::export_corpus(build_id, filters)`, который выгружает parsed Markdown/plain-text документов из MinIO/S3 (результат §9 Step 2/3) в GraphRAG input-директорию `graphrag/input/<build_id>/`.
- [ ] Каждому входному файлу присвоить стабильное имя `<doc_id>.txt` и сохранить mapping `doc_id ↔ graphrag document_id ↔ source path` в `graphrag/input/<build_id>/manifest.json`.
- [ ] Применять фильтры доступа/политик (`access_policy`, `owner/lab` из §9 Step 1) и исключать документы со `review_status: rejected`; параметры фильтра логировать в manifest.
- [ ] Реализовать дедупликацию по `file_hash` (§9 Step 1), чтобы один и тот же документ не попадал дважды.
- [ ] Прокинуть метаданные (`doc_id`, `source_type`, `page` карту offset→page) в дополнительные колонки input CSV/parquet, чтобы GraphRAG сохранял их в `text_units` для последующей трассировки (п. 11.11).
- [ ] Написать unit-тест `tests/graphrag/test_input_adapter.py`: на фикстуре из 3 документов проверить корректность manifest, дедупликацию и фильтрацию rejected.

**Критерий приёмки:** `export_corpus()` для тестового корпуса создаёт input-директорию, корректный `manifest.json` с обратным mapping'ом на `doc_id`/page, отфильтрованные rejected/недоступные документы отсутствуют; unit-тест зелёный.

---

### 11.4 Индексирующий пайплайн GraphRAG (entities → communities → summaries)

- [ ] Реализовать `packages/kg_retrievers/graphrag/pipeline.py::run_index(build_id)` — обёртку над `graphrag index --root infra/graphrag` с подстановкой input/output путей текущего `build_id` и захватом логов/кодов возврата.
- [ ] Обеспечить получение всех артефактов пайплайна в `graphrag/output/<build_id>/`: `entities`, `relationships`, `text_units`, `communities`, `community_reports` (parquet), и лог `pipeline.log`.
- [ ] Проверить, что выполняется иерархическая кластеризация (Leiden) с несколькими уровнями (`community_level` 0..N) и что `community_reports` содержат `title`, `summary`, `full_content`, `rank`, `findings`, `level`, `community_id`.
- [ ] Реализовать `artifacts.py::load_artifacts(build_id)` для чтения parquet-файлов в Polars/Pandas DataFrame с валидацией ожидаемых колонок (падать при отсутствии `community_reports`).
- [ ] Добавить проверку целостности build: число сообществ > 0, число community_reports == числу communities с непустым отчётом; при провале build помечается `failed`.
- [ ] Реализовать инкрементальный режим (если поддерживается версией GraphRAG — `graphrag update`), иначе — полный rebuild; выбор режима задаётся параметром `mode: full|incremental` и фиксируется в ADR.
- [ ] Ограничить стоимость/время: пробросить лимиты параллелизма LLM и timeout в `settings.yaml`; логировать суммарное число LLM-вызовов и токенов на build.
- [ ] Интеграционный тест `tests/graphrag/test_pipeline.py` (помечен `@pytest.mark.slow`, mock LLM/embeddings): запускает `run_index` на мини-корпусе и проверяет наличие и схему всех parquet-артефактов.

**Критерий приёмки:** `run_index(build_id)` на тестовом корпусе завершается с кодом 0, создаёт полный набор parquet-артефактов, `community_reports` содержит требуемые поля и минимум 2 уровня иерархии; проверки целостности проходят.

---

### 11.5 Хранение community summaries в Qdrant (§9, Step 8; payload §9.8)

- [ ] Спроектировать Qdrant-коллекцию `graphrag_community_summaries` (dense-вектор от embedding-модели §9/§10; при необходимости sparse для гибрида) — конфиг размерности/метрики в `infra/qdrant/` и `packages/kg_retrievers/graphrag/qdrant_store.py`.
- [ ] Реализовать эмбеддинг текста отчёта: индексировать `summary` (и/или `full_content`) каждого community report; хранить `title`+`summary` как основной текст точки.
- [ ] Определить payload-схему точки, согласованную с §9 Step 8 indexing («community summaries») и §9.8 (payload fields): как минимум `community_id`, `level`, `title`, `rank`, `findings`, `entity_ids`, `material_ids`, `property_ids`, `doc_ids` (источники), `build_id`, `build_version`, `created_at`, плюс совместимые поля из §9.8 (`source_type: "community_summary"`, `confidence`, `review_status`).
- [ ] Реализовать `qdrant_store.py::upsert_community_reports(build_id)` — батч-upsert точек с детерминированными point id (`hash(build_id, community_id, level)`), идемпотентно.
- [ ] Реализовать поисковый метод `qdrant_store.py::search_communities(query_vector, level=None, top_k, filters)` с payload-фильтрами по `level`, `material_ids`, `property_ids`, `build_version`.
- [ ] Заполнять `entity_ids/material_ids/property_ids` в payload, резолвя GraphRAG-сущности к каноническим id графа (§9 Step 6 entity resolution) там, где mapping доступен; несопоставленные оставлять как raw text с флагом.
- [ ] Unit/integration тест `tests/graphrag/test_qdrant_store.py` (Qdrant в тест-контейнере): upsert + search возвращает релевантный community report; повторный upsert того же build не создаёт дубликатов.

**Критерий приёмки:** после build в коллекции `graphrag_community_summaries` присутствует по точке на каждый community report со всеми обязательными payload-полями (§9.8); `search_communities()` возвращает top-k с фильтрацией по `level`; повторный upsert идемпотентен.

---

### 11.6 Хранение иерархии сообществ в Neo4j (§8) и поддержка graph_proximity_score

- [ ] Расширить схему §8.1 новыми labels: `Community`, `CommunityReport` (добавить в реестр labels и в документацию схемы).
- [ ] Добавить constraints/indexes (в стиле §8.4) в `infra/neo4j/schema.cypher`:
  - `CREATE CONSTRAINT community_id IF NOT EXISTS FOR (c:Community) REQUIRE c.id IS UNIQUE;`
  - `CREATE CONSTRAINT community_report_id IF NOT EXISTS FOR (r:CommunityReport) REQUIRE r.id IS UNIQUE;`
  - индексы по `Community.level`, `Community.build_version`.
- [ ] Определить связи иерархии и членства: `(:Community)-[:HAS_SUBCOMMUNITY]->(:Community)`, `(:Community)-[:HAS_REPORT]->(:CommunityReport)`, `(:Community)-[:INCLUDES_ENTITY]->(:Entity)`, `(:Chunk)-[:IN_COMMUNITY]->(:Community)`.
- [ ] Реализовать `packages/kg_retrievers/graphrag/neo4j_store.py::upsert_communities(build_id)` — идемпотентный `MERGE` community/report узлов и связей из parquet-артефактов, с `build_version` на узлах.
- [ ] Проставить `community_id`/`community_level` на узлах `Chunk` (и/или связь `IN_COMMUNITY`), чтобы `graph_proximity_score` из §10.3 мог вычислять правило «0.2 if chunk is same community».
- [ ] Продублировать `community_id` в Qdrant payload chunk-точек (§9.8) — чтобы hybrid-retriever (§7 Node 6, §10.2) мог применять community-boost без обращения к Neo4j.
- [ ] Обеспечить связь community → источники: `(:CommunityReport)-[:CITES]->(:Document)` или список `doc_ids` в свойстве для трассировки (п. 11.11).
- [ ] Зафиксировать (в ADR `docs/adr/0011-graphrag-integration.md` и в схеме §8), что для правила §10.3 «0.2 if chunk is same community» авторитетным является GraphRAG-Leiden `community_id` (не Neo4j GDS-community из Mode D §10.1); во избежание коллизии хранить GDS-сообщества под отдельным свойством (например, `gds_community`) и не смешивать их с `community_id` GraphRAG.
- [ ] Реализовать Cypher-функцию/шаблон вычисления `graph_proximity_score` компонента «same community» (§10.2 весом 0.10, §10.3) в `packages/kg_retrievers/` и покрыть тестом: два чанка с одинаковым `community_id` → 0.2, с разным → 0.
- [ ] Тест `tests/graphrag/test_neo4j_store.py` (Neo4j в тест-контейнере): upsert создаёт иерархию с ≥2 уровнями, chunk получает `community_id`, повторный upsert не плодит дубликатов.

**Критерий приёмки:** после build в Neo4j есть узлы `Community`/`CommunityReport` с корректной иерархией `HAS_SUBCOMMUNITY`; узлы `Chunk` имеют `community_id` (GraphRAG-Leiden), отдельный от GDS-сообществ Mode D; Cypher-запрос §10.3 «same community» возвращает 0.2 для двух чанков одного сообщества; constraints применены.

---

### 11.7 GraphRAG retrieval: global & local search обёртки (search-service)

- [ ] Реализовать `packages/kg_retrievers/graphrag/global_search.py::global_search(query, community_level, top_k)` поверх GraphRAG global search engine, читая community_reports текущего активного build.
- [ ] Реализовать `packages/kg_retrievers/graphrag/local_search.py::local_search(query, top_k)` (local search по entities/relationships/text_units) — как дополнительный режим для сущностно-ориентированных broad-вопросов.
- [ ] Реализовать fusion-путь: сначала vector-retrieval community summaries из Qdrant (п. 11.5, дёшево), затем map-reduce суммаризация выбранных отчётов через LLM (в стиле GraphRAG global search) — чтобы не гонять все сообщества через LLM на каждый запрос.
- [ ] Возвращать структурированный результат `GraphRagResult`: `answer_text`, `used_community_ids`, `source_reports[]` (id, level, title), `cited_doc_ids[]`, `token_usage`, `latency_ms`.
- [ ] Инкапсулировать вызов в `apps/search-service/`: модуль `apps/search-service/app/graphrag_search.py`, использующий обёртки из `packages/kg_retrievers/graphrag/`.
- [ ] Реализовать выбор `community_level` по типу вопроса (более высокий уровень = более общий обзор); значение по умолчанию и override — параметром запроса.
- [ ] Кэшировать результаты global search в Redis по ключу `(query_hash, build_version, level)` с TTL (согласуется с §18 mitigation «precomputed summaries / cached retrieval»).
- [ ] Тест `tests/graphrag/test_global_search.py` (mock LLM): проверяет, что `global_search` возвращает `used_community_ids` и `cited_doc_ids`, и что кэш срабатывает на повторный идентичный запрос.

**Критерий приёмки:** `global_search()` на тестовом build возвращает непустой `GraphRagResult` с непустыми `used_community_ids` и `cited_doc_ids`; повторный запрос обслуживается из Redis-кэша (latency < первого); local search доступен как отдельный метод.

---

### 11.8 Интеграция в LangGraph-агента (Mode C: routing, tool, node)

- [ ] Добавить agent tool `graphrag_global_search` (и опционально `graphrag_local_search`) в список `TOOLS` (§7.4) в `apps/agent-service/app/tools/graphrag.py`, оборачивающий search-service вызов из п. 11.7.
- [ ] Расширить `intent_classifier` (§7.5 Node 2) распознаванием интента «global corpus / broad overview / multi-document synthesis» (примеры из §10.1: «какие направления были в теме», «что известно в целом»).
- [ ] В `query_planner` (§7.5 Node 4) реализовать маршрут `ROUTE -->|global corpus| GRAG` (§7.2): выбор Mode C для соответствующего интента.
- [ ] Реализовать node `graphrag_retrieval` в `apps/agent-service/app/nodes/graphrag_retrieval.py`, заполняющий поля `ScientificAgentState` (§7.3): `retrieved_chunks`/новое поле `retrieved_communities`, `evidence` (EvidenceRef на источники отчётов), `tool_trace`.
- [ ] Подключить выход node к `evidence_assembler` (§7.2 `GRAG --> EVID`, §7.5 Node 7) — community summaries проходят ту же сборку citations, что и остальные режимы.
- [ ] Гарантировать, что `verifier` (§7.5 Node 9) применяется к GraphRAG-ответам: числовые/фактические утверждения из community summaries должны иметь трассировку до источников (иначе помечаются warning/unsupported).
- [ ] Прокинуть в `visualization_payload` (§7.5 Node 10) граф-снапшот сообществ (community view) для UI — использовать `used_community_ids` и иерархию из п. 11.6.
- [ ] Сформировать community-view payload в формате Reagraph graph payload (§5.3 «Graph payload для Reagraph»): узлы `Community`/`CommunityReport`/ключевые `Entity`, рёбра `HAS_SUBCOMMUNITY`/`INCLUDES_ENTITY`; обеспечить совместимость с режимом «cluster/community overview» и large-graph fallback Sigma.js/Graphology (§5.1, §3.1), как того требует mitigation §18 «Graph becomes unreadable → community view, Sigma fallback».
- [ ] Тест `tests/agent/test_graphrag_route.py`: broad-вопрос маршрутизируется в Mode C и вызывает tool `graphrag_global_search`; узко-структурный вопрос — НЕ маршрутизируется в GraphRAG (см. п. 11.12).

**Критерий приёмки:** для broad-вопроса агент выбирает Mode C, вызывает `graphrag_global_search`, результат проходит через `evidence_assembler`+`verifier`, а `tool_trace` фиксирует вызов; структурный/сущностный вопрос НЕ уходит в GraphRAG.

---

### 11.9 API endpoints (§6.2)

- [ ] Добавить endpoint `POST /api/v1/search/global` в `apps/api-gateway/` (расширение блока `search` из §6.2), тело: `{ "query": str, "community_level": int?, "top_k": int?, "build_version": str? }`.
- [ ] Добавить `GET /api/v1/graphrag/communities?level=&limit=` — листинг сообществ активного build с `title`, `rank`, `level`.
- [ ] Добавить `GET /api/v1/graphrag/communities/{community_id}` — детальный community report (`summary`, `findings`, `cited_doc_ids`, sub-communities).
- [ ] Добавить `GET /api/v1/graphrag/status` — метаданные текущего активного build (`build_version`, `created_at`, число communities/reports, состояние).
- [ ] Ответ `POST /api/v1/search/global` должен возвращать формат, совместимый с общим ответом (§6.2 «Пример ответа»): `answer`, `evidence`/`sources`, `graph` payload (community view), `used_community_ids`.
- [ ] Добавить request validation (Pydantic-модели), rate limit и audit log (§6.2) для новых endpoints.
- [ ] OpenAPI-схема обновлена, endpoints видны в `/docs`; добавить контрактный тест `tests/api/test_graphrag_endpoints.py`.

**Критерий приёмки:** новые endpoints присутствуют в OpenAPI и проходят контрактные тесты; `POST /api/v1/search/global` на seed-данных возвращает ответ с `sources`/`used_community_ids`; `GET /api/v1/graphrag/status` отдаёт активный `build_version`.

---

### 11.10 Периодическое перестроение (Dagster) и версионирование индекса

- [ ] Реализовать Dagster assets в `infra/dagster/graphrag/` : `graphrag_input` (п. 11.3) → `graphrag_index` (п. 11.4) → `graphrag_qdrant_upsert` (п. 11.5) → `graphrag_neo4j_upsert` (п. 11.6) с зависимостями между ними.
- [ ] Реализовать `versioning.py`: каждый прогон создаёт новый `build_version` (timestamp/uuid); хранить реестр билдов в Postgres (таблица `graphrag_builds`: `build_version`, `status`, `n_communities`, `created_at`, `active`).
- [ ] Реализовать **blue/green swap**: индексировать новый build в отдельную Qdrant-коллекцию/алиас (`graphrag_community_summaries_<build_version>`) и атомарно переключать alias `graphrag_community_summaries` только после успешной валидации build (п. 11.4).
- [ ] Настроить Dagster schedule (например, ежедневно/еженедельно) и sensor, запускающий rebuild при росте корпуса выше порога (N новых документов после §9 ingestion); параметры в `infra/dagster/graphrag/config.yaml`.
- [ ] Реализовать retention: хранить последние K билдов, удалять старые Qdrant-коллекции и Neo4j-узлы прошлых `build_version` в rollback-safe порядке.
- [ ] Реализовать rollback-процедуру: переключение alias/`active` на предыдущий валидный `build_version` одной командой/asset-запуском.
- [ ] Добавить сервис `dagster` (уже в §13.1 Docker Compose) и убедиться, что образ `./infra/dagster` включает graphrag-зависимости.
- [ ] Тест `tests/graphrag/test_versioning.py`: успешный build активируется и виден в `status`; неуспешный build НЕ переключает alias; rollback возвращает предыдущий build.

**Критерий приёмки:** Dagster job строит новый build в отдельной коллекции и переключает alias только при успехе; `graphrag_builds` содержит запись с `active=true` ровно для одного билда; schedule/sensor зарегистрированы и видны в Dagster UI (`:3001`); rollback работает.

---

### 11.11 Трассируемость evidence и citations из GraphRAG (§8.3, §7 verifier)

- [ ] Обеспечить, чтобы `text_units` GraphRAG несли `doc_id`/`chunk_id`/`page` (из input-адаптера п. 11.3), и сохранить mapping `community_report → contributing text_units → doc/page` в артефактах.
- [ ] Реализовать `artifacts.py::report_to_evidence(community_id)` → список `EvidenceRef` (§7.3: `evidence_id`, `source_id`, `doc_id`, `page`, `span_start/end`, `confidence`) на основе источников отчёта.
- [ ] В node `graphrag_retrieval` (п. 11.8) заполнять `state.evidence` этими `EvidenceRef`, чтобы `evidence_assembler` мог подтянуть snippets (§7.5 Node 7) и `evidence inspector` UI (§5.2.6) работал для Mode C.
- [ ] Проставлять `confidence`/`review_status` community summary в payload (§9.8) и в answer, чтобы `verifier` мог понижать доверие к неподтверждённым обобщениям (§18: «no unsupported answer claims»).
- [ ] Тест `tests/graphrag/test_traceability.py`: для сгенерированного community report восстанавливаются ≥1 `EvidenceRef` с валидными `doc_id` и `page`.

**Критерий приёмки:** ответ Mode C содержит список источников (`doc_id`/`page`) для ключевых утверждений; `verifier` отклоняет/помечает community-утверждения без трассируемых источников; evidence inspector открывает snippet по evidence из GraphRAG.

---

### 11.12 Guardrails: GraphRAG не единственный retrieval core

- [ ] В `query_planner` (§7.5) зафиксировать правило: Mode C выбирается ТОЛЬКО для broad/global/multi-document интентов; для structured (Mode A), similar-experiments/semantic (Mode B) и graph-algorithm (Mode D) вопросов GraphRAG не является первичным.
- [ ] Добавить feature-flag `GRAPHRAG_ENABLED` (в `packages/kg_common/config.py`) и `graphrag.mode` (`primary_for_global | disabled`); при `disabled` агент/эндпоинты корректно деградируют на hybrid retrieval (§18: «disable ... for MVP if needed»).
- [ ] Реализовать fallback: если GraphRAG build отсутствует/устарел/`failed`, роутер уходит в hybrid retrieval (Mode B) с пометкой в `tool_trace` и warning в ответе.
- [ ] Добавить в ответ пометку «обзорный ответ на основе community summaries» для Mode C, чтобы UI отличал обзор от точного structured-ответа.
- [ ] Тест `tests/agent/test_graphrag_guardrails.py`: при `GRAPHRAG_ENABLED=false` broad-вопрос обслуживается hybrid retrieval; точные numeric/material-regime-property вопросы никогда не роутятся в Mode C.

**Критерий приёмки:** отключение флага не ломает агента (broad-вопросы обслуживаются hybrid retrieval); ни один структурный/numeric вопрос из golden-набора не маршрутизируется в GraphRAG как первичный источник; в ответе Mode C есть явная пометка режима.

---

### 11.13 Тестирование, evaluation и observability

- [ ] Добавить в golden dataset (§15.1) подмножество «global/broad» вопросов (не менее 10) с эталонными обзорами/охватом источников.
- [ ] Расширить eval-harness `packages/kg_eval/` метриками для Mode C (§15.2): coverage сообществ, correctness обзора (ragas/deepeval), доля утверждений с источниками, отсутствие unsupported claims.
- [ ] Встроить в автоматический eval-loop (§15.3) прогон global-вопросов против текущего активного build; результаты логировать в MLflow (§13.2 `mlflow`).
- [ ] Добавить детерминированные проверки (§15.3 «Custom deterministic checks for numeric values and citations») для ответов Mode C: каждое числовое утверждение и каждая цитата в обзоре сверяются с `cited_doc_ids`/evidence (п. 11.11); нарушение → тест падает.
- [ ] Замерять метрики ответа Mode C из §15.2: `citation precision`, `unsupported claim rate`, `numeric accuracy` — на подмножестве global-вопросов, логировать в MLflow.
- [ ] Инструментировать GraphRAG-пайплайн и retrieval OpenTelemetry-трейсами (§13.2 `opentelemetry-sdk`): span'ы `graphrag.index`, `graphrag.global_search`, с атрибутами `build_version`, `n_communities`, `token_usage`.
- [ ] Подключить трейсы Mode C к LangGraph trace viewer / LangSmith (§15.3, Phase 9 «add LangGraph trace viewer integration»), чтобы вызов `graphrag_global_search` был виден в общем agent-trace.
- [ ] Экспонировать метрики в `/api/v1/admin/metrics` (§6.2): последний `build_version`, время последнего rebuild, число сообществ, средняя latency global search, доля cache hit.
- [ ] Написать e2e-тест `tests/e2e/test_graphrag_flow.py`: upload корпуса (§9) → Dagster build (п. 11.10) → `POST /api/v1/search/global` возвращает обзор с источниками.
- [ ] Задокументировать пайплайн и операционные процедуры (rebuild, rollback, tuning) в `infra/graphrag/README.md`.

**Критерий приёмки:** global-вопросы golden-набора проходят автоматический eval с зафиксированным порогом и без unsupported claims; трейсы `graphrag.*` видны в OTEL; `/api/v1/admin/metrics` отдаёт метрики GraphRAG; e2e-тест зелёный; README с процедурами присутствует.

---

### 11.14 Позиционирование в roadmap (§16 Phase 9) и статус SOTA/optional

- [ ] Зафиксировать GraphRAG как feature фазы **Phase 9 «Hardening and SOTA polish»** (§16) и SOTA-дифференциатор №3 (§17: «GraphRAG community summaries»), а не как компонент MVP-ядра; отразить план работ п. 11.1–11.13 в задачах Phase 9.
- [ ] Явно исключить GraphRAG из «Minimal viable demo path» (§19): 5 базовых tools (`resolve_entities`, `run_cypher_template`, `hybrid_search`, `get_evidence`, `build_graph_payload`) и топовый query flow «что делали по X при Y и эффект на Z?» работают без Mode C.
- [ ] Отметить в ADR/README статус GraphRAG «Optional / для wow-effect» (§21) и «не Must-have»: система (Modes A/B/D, §10.1) должна проходить приёмку фаз Phase 4/5 без GraphRAG.
- [ ] Обеспечить, что критерий приёмки Phase 9 «no unsupported answer claims in golden set» и «reproducible benchmark» (§16) выполняется в том числе на broad/global-вопросах Mode C (связь с п. 11.11, 11.13).
- [ ] Тест/CI-проверка `tests/graphrag/test_optional_offline.py`: при полностью отсутствующем GraphRAG-стеке (пакет/индекс не установлены) unit- и e2e-наборы Phase 4/5 остаются зелёными (Modes A/B/D не зависят от Mode C).

**Критерий приёмки:** документация и roadmap помечают GraphRAG как Phase 9 / Optional-SOTA; демонстрационный и MVP-путь (§19) полностью функциональны без Mode C; при отсутствующем GraphRAG-стеке приёмочные наборы Phase 4/5 проходят; broad-вопросы Mode C включены в golden-benchmark Phase 9 без unsupported claims.


---


## 12. Retrieval strategy и fusion

Раздел реализует четыре режима поиска (§10.1: Mode A structured graph query, Mode B hybrid semantic, Mode C GraphRAG community, Mode D graph algorithms), формулу гибридного скоринга (§10.2), graph proximity score (§10.3), cross-encoder reranker и Text2Cypher с guardrails (§7.4). Основной дом кода — пакет `packages/kg_retrievers/` (graph/vector/hybrid retrievers по §6.1), с обёртками в `apps/search-service/` (Qdrant/OpenSearch), `apps/graph-service/` (Cypher templates, schema validation) и вызовом из `apps/agent-service/` (nodes 5/6 — `structured_retrieval`, `hybrid_retrieval`).

**Зависимости от других разделов:**
- Раздел §8 (KG schema) — canonical labels/relationships для allowlist и Cypher-шаблонов (§8.1, §8.2), constraints/indexes (§8.4), evidence-first model (§8.3).
- Раздел §9 (ingestion/indexing) — Qdrant/OpenSearch должны быть заполнены (Step 8, payload-поля из §9.2), community summaries и graph neighborhood summaries проиндексированы.
- Раздел §7 (agent) — retrieval вызывается из nodes `structured_retrieval`, `hybrid_retrieval`, tools `run_cypher_readonly`, `run_cypher_template`, `vector_search_qdrant`, `keyword_search_opensearch`, `hybrid_search`, `find_graph_paths`, `expand_subgraph`, `get_experiment_table`, `get_evidence_by_ids`, `get_document_snippet`, `build_graph_visualization_payload` (§7.4).
- Раздел §6.2 — endpoints `/api/v1/search/hybrid|vector|keyword`, `/api/v1/graph/query|expand|path|subgraph|schema`, `/api/v1/experiments|/{id}|/query`, `/api/v1/entities/{id}/neighbors`, `/api/v1/evidence/by-edge/{edge_id}`.
- Раздел §15 (evaluation) — golden dataset и метрики для приёмки retrieval.

**OSS-репозитории для клонирования/вендоринга (§22):**
- Microsoft GraphRAG — `https://github.com/microsoft/graphrag` (Mode C, community summaries).
- Neo4j Graph Data Science — `https://github.com/neo4j/graph-data-science` (Mode D, GDS алгоритмы).
- Neo4j APOC — `https://github.com/neo4j-contrib/neo4j-apoc-procedures` (path/subgraph helpers).
- Qdrant — `https://github.com/qdrant/qdrant`; OpenSearch — `https://github.com/opensearch-project/OpenSearch`.
- LlamaIndex — `https://github.com/run-llama/llama_index` (`TextToCypherRetriever`, PropertyGraphIndex).
- Haystack — `https://github.com/deepset-ai/haystack` (опциональные rerankers/pipeline-блоки).
- NetworkX (Python-пакет из §13.2) — локальные graph-алгоритмы, если GDS недоступен в Community edition.

Python-пакеты (из §13.2), затрагиваемые разделом: `neo4j`, `qdrant-client`, `opensearch-py`, `llama-index`, `llama-index-graph-stores-neo4j`, `llama-index-vector-stores-qdrant`, `sentence-transformers`, `fastembed`, `haystack-ai`, `networkx`, `pint`, `structlog`, `ragas`.

---

### 12.1 Retrieval core: DTOs, router и общая оркестрация режимов

Общий каркас пакета `packages/kg_retrievers/`: единые запрос/ответ, router режимов (§10.1) и оркестратор, который вызывается из agent nodes 5/6 (§7.5) и из API Gateway endpoints (§6.2).

- [x] Создать пакет `packages/kg_retrievers/` со стандартной структурой (`pyproject.toml`, `__init__.py`, модули `router.py`, `structured.py`, `hybrid.py`, `fusion.py`, `proximity.py`, `evidence_quality.py`, `rerank.py`, `graphrag.py`, `gds.py`, `text2cypher.py`, `orchestrator.py`).
- [x] В `packages/kg_common/` описать Pydantic DTO `RetrievalRequest` (поля: `query: str`, `normalized_query: str`, `intent: str`, `entities: list[EntityMention]`, `numeric_constraints: dict`, `filters: dict` — material/property/lab/date/source_type/min_confidence/verified_only по §6.2, `mode: Literal['auto','structured','hybrid','graphrag','graph_algo']`, `top_k: int`, `limit: int`).
- [x] Описать DTO `RetrievalHit` (поля: `id`, `type` в терминах labels §8.1, `score: float`, `component_scores: dict[str,float]` — dense/sparse/bm25/graph_proximity/evidence_quality, `payload: dict`, `evidence_ids: list[str]`, `source_type`, `confidence`, `review_status`) и `RetrievalResult` (`hits`, `mode_used`, `graph: GraphResponse` по §5.3, `experiments: list`, `timings: dict`, `generated_cypher: str | None`).
- [x] Реализовать `router.select_mode(request) -> mode`: маппинг intent (§7.5 Node 2) → mode: `material_regime_property_query|experiment_lookup|evidence_request` → Mode A; `entity_exploration|method_comparison` → Mode B; `literature_summary` → Mode C; `gap_analysis|contradiction_analysis` → Mode A+D; `schema_help` → без retrieval. Router обязан соблюдать mermaid-маршрутизацию §7.2 (ROUTE → CYPHER/HYBRID/GRAG/GAP).
- [x] Реализовать `orchestrator.retrieve(request) -> RetrievalResult`: выбор режима router-ом, вызов соответствующего retriever(ов), передача top-N в fusion (§12.4) и reranker (§12.8), сборка `RetrievalResult`; поддержать комбинированные планы (`query_plan.retrieval_strategy` может содержать несколько стратегий, §7.5 Node 4).
- [x] Реализовать конфиг retrieval в `packages/kg_common/config` (pydantic-settings): веса fusion, `top_k` кандидатов на источник (default 100), `rerank_top_n=50`, флаги включения reranker/graphrag/gds, timeouts. Все веса и лимиты — из env/config, не hardcoded.
- [x] Реализовать единую точку регистрации retrieval-tools (§7.4) в `apps/agent-service/` с маппингом на модули пакета: `run_cypher_template`→`structured.py`, `run_cypher_readonly`→`text2cypher.py`/guardrail-executor, `vector_search_qdrant`/`keyword_search_opensearch`/`hybrid_search`→`hybrid.py`, `find_graph_paths`/`expand_subgraph`→`gds.py`/`structured.py`, `get_experiment_table`/`get_evidence_by_ids`/`get_document_snippet`→evidence-обёртки, `build_graph_visualization_payload`→payload builder (§12.11).
- [x] Добавить структурированное логирование (`structlog`) и OpenTelemetry-спаны на каждый режим и стадию (retrieval → fusion → rerank) с записью timings в `RetrievalResult.timings`.

**Критерий приёмки:** unit-тест `router.select_mode` покрывает все 9 intent-классов §7.5 и возвращает ожидаемый mode; `orchestrator.retrieve` с `mode='auto'` для запроса «material X + regime Y + property Z» отрабатывает end-to-end и возвращает непустой `RetrievalResult` с заполненными `timings` и `mode_used='structured'`; все retrieval-tools §7.4 зарегистрированы в agent-service и разрешаются через единый маппинг.

### 12.2 Mode A: structured graph query (Cypher templates)

Реализация Mode A (§10.1) — детерминированные Cypher-шаблоны в `apps/graph-service/` и tool `run_cypher_template` (§7.4). Использует labels/relationships §8.2 и indexes §8.4.

- [x] Создать реестр шаблонов `apps/graph-service/templates/registry.py` со словарём `TEMPLATES` (§7.4). Каждый шаблон — объект с полями: `name`, `cypher`, `required_params`, `optional_params`, `param_types`, `default_limit`.
- [x] Реализовать шаблон `material_regime_property` дословно по §7.4 (MATCH Material→Sample→ProcessingRegime→Measurement→Property, WHERE по `$material/$operation/$temperature_c ± $temperature_tolerance/$time_h ± $time_tolerance/$property`, OPTIONAL MATCH SUPPORTED_BY Evidence, `LIMIT $limit`).
- [x] Добавить шаблоны для остальных intent-классов §7.5:
  - [x] `experiment_lookup` (Paper-[:REPORTS]->Experiment-[:USES_SAMPLE]->Sample, с evidence);
  - [x] `entity_neighbors` (соседи узла с фильтром по типам, для `/api/v1/graph/expand` и `/api/v1/entities/{id}/neighbors`);
  - [x] `find_graph_paths` (variable-length path между двумя entity, `/api/v1/graph/path`);
  - [x] `expand_subgraph` (проекция подграфа вокруг seed-узлов с depth-лимитом, `/api/v1/graph/subgraph`);
  - [x] `evidence_by_ids` (Evidence по списку id с FROM_CHUNK/FROM_TABLE и spans, §8.3);
  - [x] `contradictions_for_triple` (Claim-[:CONTRADICTS]->Claim по material/property/regime).
- [x] Реализовать валидатор параметров `validate_params(template, params)`: проверка обязательных полей, типов, диапазонов числовых constraints; отклонение неизвестных полей.
- [x] Реализовать executor `run_cypher_template(name, params) -> rows` в `packages/kg_retrievers/structured.py`: подстановка только через `$`-параметры Neo4j driver (никакой строковой конкатенации Cypher), исполнение в readonly-сессии (см. §12.9), принудительный `LIMIT`.
- [x] Реализовать маппер `rows -> RetrievalHit[] + GraphResponse` (§5.3): узлы/рёбра из результата с `type`, `confidence`, `evidenceCount`, `verified`, `contradicted`, `evidenceIds`; заполнить `queryContext.generatedCypher`.
- [x] Зарегистрировать tool `run_cypher_template` в agent-service (§7.4) и подключить Mode A к node `structured_retrieval` (§7.5 Node 5): Cypher-шаблоны, traversal, path-queries, сбор evidence IDs.
- [x] Зарегистрировать остальные Mode A retrieval-tools (§7.4): `get_evidence_by_ids` (поверх шаблона `evidence_by_ids`, spans §8.3), `find_graph_paths` и `expand_subgraph` (поверх соответствующих шаблонов/GDS §12.8); подключить шаблон `entity_neighbors` также к endpoint `/api/v1/entities/{entity_id}/neighbors?depth=&types=` (§6.2), а `experiment_lookup` — к `/api/v1/experiments/query` и `/api/v1/experiments/{experiment_id}` (§6.2, реализация в §12.11).
- [x] Написать интеграционный тест на seed-графе: шаблон `material_regime_property` для Al-Cu/aging/180°C/2h/hardness возвращает эксперименты, значения и evidence (соответствие примеру ответа §6.2).

**Критерий приёмки:** для запроса из примера §6.2 (`material_regime_property`, Al-Cu, aging 180°C 2h, hardness) tool `run_cypher_template` возвращает строки с material/sample/regime/measurement/property/evidence; параметризация подтверждена тестом на инъекцию (значение `material="x' OR 1=1//"` не меняет структуру запроса и не выполняет доп. операции).

### 12.3 Mode B: hybrid semantic search (dense + sparse + BM25)

Три источника кандидатов (§10.2, §7.5 Node 6): dense/sparse из Qdrant, BM25/keyword из OpenSearch. Обёртки в `apps/search-service/`, вызываются из `packages/kg_retrievers/hybrid.py`.

- [x] Реализовать Qdrant-клиент `apps/search-service/clients/qdrant_client.py` (`qdrant-client`): dense-поиск и sparse-поиск по коллекциям chunks/table_rows/claims/entity_descriptions/graph_neighborhood_summaries/community_summaries (§9.2 Step 8), с payload-фильтрами `material_ids/property_ids/processing_operation/temperature_c/time_h/source_type/confidence/review_status` (§9.2 payload).
- [x] Реализовать sparse-эмбеддинги через `fastembed` (SPLADE/BM42) для `sparse_vector_score`; dense-эмбеддинги — той же моделью, что при ingestion (согласовать dimension с §8.4 vector index, 1024).
- [x] Поддержать (опционально, за config-флагом) multivector / late-interaction retrieval в Qdrant (§4.1 «dense/sparse/multivector»): ColBERT-подобные представления для точного re-scoring; по умолчанию dense+sparse.
- [x] Реализовать OpenSearch-клиент `apps/search-service/clients/opensearch_client.py` (`opensearch-py`): BM25 full-text по индексу chunks/claims, facet-фильтры, numeric ranges, highlight fields (§9.2 Step 8).
- [x] Реализовать `hybrid.search(request) -> dict[source -> RetrievalHit[]]`: параллельный вызов dense/sparse (Qdrant) и bm25 (OpenSearch), каждый с `top_k` кандидатов; проброс `filters` из `RetrievalRequest` в payload/facet-фильтры всех источников.
- [x] Реализовать нормализацию score по источнику (min-max или z-score внутри выдачи источника) перед fusion, чтобы шкалы dense/sparse/bm25 были сопоставимы.
- [x] Реализовать использование коллекции `graph_neighborhood_summaries` (§9.2 Step 8) как отдельного источника для intent `entity_exploration` (соседский контекст узла) с проекцией результата в `RetrievalHit`.
- [x] Реализовать payload-обогащение: подтянуть `entity_ids/material_ids/property_ids/source_type/confidence/review_status` в `RetrievalHit.payload` для последующего evidence quality (§12.5) и rerank (§12.8).
- [x] Реализовать API-обёртки `/api/v1/search/vector`, `/api/v1/search/keyword`, `/api/v1/search/hybrid` (§6.2) в `apps/api-gateway/` поверх search-service.
- [x] Зарегистрировать в agent-service tools `vector_search_qdrant` и `keyword_search_opensearch` (§7.4) поверх search-service, связав их с endpoints `/api/v1/search/vector` и `/api/v1/search/keyword` соответственно.
- [x] Подключить Mode B к node `hybrid_retrieval` (§7.5 Node 6) и tool `hybrid_search` (§7.4).
- [x] Написать тесты: (a) фильтр `material_ids` реально сужает выдачу; (b) при пустом OpenSearch (MVP-режим отключения, §18) hybrid деградирует до dense+sparse без падения.

**Критерий приёмки:** `hybrid.search` для «похожие эксперименты по aging Al-Cu» возвращает по каждому из трёх источников ≥1 кандидата с нормализованными score в [0,1]; отключение OpenSearch не роняет пайплайн (graceful degradation подтверждён тестом); tools `vector_search_qdrant`/`keyword_search_opensearch`/`hybrid_search` зарегистрированы и обслуживают `/api/v1/search/vector|keyword|hybrid`.

### 12.4 Weighted fusion и RRF

Слияние кандидатов из §12.3 (+ graph proximity §12.5 и evidence quality §12.6) по формуле §10.2, с альтернативой RRF (§7.5 Node 6, Phase 4).

- [x] Реализовать weighted fusion `fusion.weighted_fuse(hits_by_source, weights) -> RetrievalHit[]` строго по формуле §10.2:
  `score = 0.35*dense + 0.25*sparse + 0.20*bm25 + 0.10*graph_proximity + 0.10*evidence_quality`.
- [x] Вынести веса `{dense:0.35, sparse:0.25, bm25:0.20, graph_proximity:0.10, evidence_quality:0.10}` в конфиг (§12.1); при загрузке проверять, что сумма весов == 1.0 (assert/валидация).
- [x] Реализовать дедупликацию/объединение кандидатов по `chunk_id`/`id` при слиянии источников: если документ найден несколькими источниками — объединить `component_scores`, отсутствующие компоненты = 0.
- [x] Реализовать альтернативный `fusion.rrf_fuse(hits_by_source, k=60) -> RetrievalHit[]` (Reciprocal Rank Fusion, `1/(k+rank)` по каждому источнику) как переключаемую стратегию (config-флаг `fusion.method: 'weighted'|'rrf'`).
- [x] Заполнять `RetrievalHit.component_scores` всеми пятью компонентами для объяснимости в UI/debug.
- [x] Написать unit-тесты: (a) на фиктивных score результат ручного расчёта совпадает с `weighted_fuse` до 1e-6; (b) RRF на известном ранжировании даёт ожидаемый порядок; (c) изменение веса `dense` меняет итоговый порядок предсказуемо.

**Критерий приёмки:** `weighted_fuse` воспроизводит формулу §10.2 (тест с эталонными числами проходит), сумма весов валидируется при старте, переключение `weighted`↔`rrf` работает без изменения интерфейса.

### 12.5 Graph proximity score

Компонент `graph_proximity_score` формулы §10.2, вычисляемый по правилам §10.3 относительно matched measurement/experiment из Mode A.

- [ ] Реализовать `proximity.compute(chunk, context) -> float` строго по §10.3:
  - [ ] `1.0` если chunk напрямую поддерживает matched measurement (Evidence-[:SUPPORTED_BY? / FROM_CHUNK]);
  - [ ] `0.8` если chunk связан с тем же Experiment;
  - [ ] `0.6` если chunk связан с тем же Material + Property;
  - [ ] `0.4` если chunk из того же Document;
  - [ ] `0.2` если chunk из того же community;
  - [ ] `0.0` иначе (default).
- [ ] Реализовать построение `proximity context` из результатов Mode A: matched measurement ids, experiment id, material/property ids, doc_id, community_id (из `layoutHints.communities` §5.3 / GraphRAG §12.7).
- [ ] Реализовать эффективный lookup связей chunk↔measurement/experiment/material/document/community батчем (один Cypher/один запрос к payload) вместо N+1; использовать fulltext/index §8.4.
- [ ] Обеспечить graceful fallback: если Mode A не выполнялся (чистый Mode B/C запрос) — proximity=0 для всех, вес перераспределяется согласно config-политике (документировать поведение).
- [ ] Написать тесты по каждому уровню шкалы §10.3 на seed-графе (5 кейсов → 5 ожидаемых значений).

**Критерий приёмки:** `proximity.compute` возвращает ровно значения {1.0/0.8/0.6/0.4/0.2/0.0} для сконструированных кейсов §10.3; батч-lookup не делает N+1 запросов (проверено счётчиком обращений к драйверу в тесте).

### 12.6 Evidence quality score

Компонент `evidence_quality_score` формулы §10.2, основанный на evidence-first модели §8.3 и warning-правилах §7.5 Node 9.

- [ ] Реализовать `evidence_quality.compute(hit) -> float` из полей evidence/extraction: наличие source span (`char_start/char_end` или `table row/col`, §8.3), `review_status` (accepted > pending > rejected), `confidence` экстракции, `source_type` (table_cell/paragraph выше, чем metadata).
- [ ] Определить и вынести в конфиг веса/коэффициенты компонентов evidence quality; нормализовать результат в [0,1].
- [ ] Учесть буст verified evidence и штрафы «missing span»/«low confidence» на уровне score (согласованно с reranker §12.9, чтобы не дублировать эффект — задать разделение ответственности: fusion-компонент = мягкий приор, rerank = финальная корректировка).
- [ ] Написать тесты: verified+span+high-conf → близко к 1.0; missing-span+low-conf+pending → близко к 0; rejected → 0.

**Критерий приёмки:** `evidence_quality.compute` монотонно растёт при добавлении span/verified/повышении confidence; граничные кейсы (rejected, no-span) дают минимальный score (тест проходит).

### 12.7 Mode C: GraphRAG community summaries

Mode C (§10.1, §10.3 community-уровень) на базе Microsoft GraphRAG для broad/global вопросов (§7.2 GRAG-ветка, intent `literature_summary`).

- [ ] Клонировать/вендорить Microsoft GraphRAG (`https://github.com/microsoft/graphrag`) в `infra/` или как зависимость; зафиксировать версию.
- [ ] Настроить community detection (Leiden) поверх графа Neo4j: экспорт проекции граф → GraphRAG, построение иерархии communities, генерация community summaries (согласовать с §9.2 Step 8 «community summaries» и §8 schema).
- [ ] Проиндексировать community summaries в Qdrant (коллекция `community_summaries`, §9.2 Step 8) и связать community_id с узлами графа (свойство узлов для §12.5 уровень 0.2 и `layoutHints.communities` §5.3).
- [ ] Реализовать `graphrag.community_search(request) -> RetrievalHit[]`: поиск релевантных community summaries (dense), сбор представителей сообществ, формирование сводного контекста для answer synthesizer (§7.5 Node 10).
- [ ] Реализовать map-reduce global search паттерн GraphRAG (per-community partial answers → агрегация) как опцию для intent `literature_summary`.
- [ ] Подключить Mode C в router (§12.1) и в agent-ветку GRAG (§7.2); community summaries использовать как precomputed summaries для снижения латентности (§18 «Slow chat»).
- [ ] Написать тест: broad-вопрос («какие направления были в теме X») возвращает ≥1 community summary с community_id и не требует точных сущностей.

**Критерий приёмки:** для broad-вопроса Mode C возвращает community summaries с корректными `community_id`; community_id проставлены на узлах графа и доступны graph proximity (§12.5, уровень 0.2) и `layoutHints.communities`.

### 12.8 Mode D: graph algorithms (GDS)

Mode D (§10.1, §4.1 «не писать graph algorithms сами»): similarity / community / centrality / paths через Neo4j GDS (fallback NetworkX). Питает tools `find_graph_paths`, `expand_subgraph` и «similar materials» (§7.4).

- [ ] Подключить Neo4j Graph Data Science (`https://github.com/neo4j/graph-data-science`) в `infra/neo4j/` (plugin) и APOC (`neo4j-apoc-procedures`); проверить доступность процедур `gds.*` на выбранной редакции (§13.1 neo4j image); если Community edition ограничивает GDS — предусмотреть NetworkX-fallback (`networkx`, §13.2).
- [ ] Реализовать модуль `packages/kg_retrievers/gds.py` с graph projection helper (создание/удаление именованных GDS-проекций для нужных подграфов).
- [ ] Реализовать **similarity**: node similarity / kNN по узлам Material для «similar materials» (§10.1 Mode D, §7.4); опционально node embeddings (node2vec/FastRP) с записью в `entity_embedding_index` (§8.4 vector index).
- [ ] Реализовать **community**: Louvain/Leiden для кластеров методов/материалов (§10.1), запись `community_id` (совместимо с §12.7).
- [ ] Реализовать **centrality**: PageRank/Betweenness для «important labs/teams» и `node size = centrality` в UI (§5.2.3, node size = evidence count / centrality).
- [ ] Реализовать **paths**: shortest/weighted paths и «missing links»/anomaly detection (§10.1), питает tool `find_graph_paths` и endpoint `/api/v1/graph/path`.
- [ ] Реализовать tool `expand_subgraph` (§7.4): проекция подграфа вокруг seed-узлов с лимитами по depth и размеру (subgraph projection, §18 «Graph becomes unreadable» → subgraph projection + filters + community view).
- [ ] Смаппить результаты GDS в `GraphResponse` (§5.3) с `layoutHints` (communities, rootNodeIds) и в `RetrievalHit` для fusion, где применимо.
- [ ] Написать тесты: PageRank возвращает ненулевые ранги на seed-графе; node similarity для похожих сплавов даёт непустой список; shortest path между двумя узлами найден.

**Критерий приёмки:** каждый из четырёх классов алгоритмов (similarity/community/centrality/paths) исполняется на seed-графе через GDS (или NetworkX-fallback) и возвращает результат в формате `GraphResponse`/`RetrievalHit`; «similar materials» для заданного Material возвращает ранжированный список.

### 12.9 Cross-encoder reranker

Финальный reranking top-50 кандидатов (§10.2 Rerank, §7.5 Node 6): cross-encoder + буст verified evidence + штрафы за missing span / low confidence.

- [ ] Реализовать `rerank.rerank(query, hits, top_n=50) -> RetrievalHit[]` в `packages/kg_retrievers/rerank.py`: подача (query, chunk_text) пар в cross-encoder; брать не более `rerank_top_n=50` кандидатов после fusion (§10.2).
- [ ] Интегрировать cross-encoder через `sentence-transformers` `CrossEncoder` или `fastembed` reranker (§13.2); выбрать модель (кандидаты: `BAAI/bge-reranker-*`, `cross-encoder/ms-marco-MiniLM-*`), сделать модель конфигурируемой; загрузка модели — lazy singleton.
- [ ] Реализовать буст verified evidence: узлы/хиты с `review_status=accepted`/`verified=true` получают положительную поправку к rerank-score (§10.2 «boost verified evidence»).
- [ ] Реализовать штраф за missing source span: хиты без `char_start/char_end` (или table row/col, §8.3) — отрицательная поправка (§10.2 «penalize missing source spans»).
- [ ] Реализовать штраф за low-confidence extraction: линейный/пороговый штраф при `confidence < min_confidence` (§6.2 filters `min_confidence`, §10.2 «penalize low-confidence extraction»).
- [ ] Вынести коэффициенты буста/штрафов в конфиг; итоговый rerank-score = f(cross_encoder_score, boosts, penalties); сохранить исходный fusion-score в `component_scores` для трассировки.
- [ ] Сделать reranker опциональным (config-флаг, §Phase 4 «implement reranking optional», «reranking cross-encoder if available» §7.5 Node 6): при выключении/недоступности модели пайплайн отдаёт fusion-порядок.
- [ ] Добавить batching и timeout на инференс cross-encoder; логировать латентность в `timings`.
- [ ] Написать тесты: (a) verified-хит поднимается выше эквивалентного unverified; (b) хит без span опускается; (c) при выключенном reranker порядок == fusion-порядок.

**Критерий приёмки:** на подготовленном наборе из 50 кандидатов reranker меняет порядок так, что verified+span-хиты систематически выше missing-span/low-confidence при равном semantic score; выключение reranker детерминированно возвращает fusion-порядок (тесты проходят).

### 12.10 Text2Cypher с guardrails

Для сложных вопросов вне шаблонов — `TextToCypherRetriever` (LlamaIndex) строго после guardrails §7.4: schema grounding, readonly transaction, LIMIT, cost guard, allowlist labels/relations, retry with verifier.

- [ ] Реализовать `text2cypher.generate(question, schema) -> cypher` в `packages/kg_retrievers/text2cypher.py` поверх LlamaIndex `TextToCypherRetriever` (llama-index + `llama-index-graph-stores-neo4j`, §13.2).
- [ ] **Schema grounding:** формировать промпт-контекст из canonical schema §8.1/§8.2 (только реальные labels/relationships), автоматически из `/api/v1/graph/schema` (§6.2) / `packages/kg_schema/`; запрещать генерацию узлов/связей вне схемы.
- [ ] **Allowlist labels/relations:** реализовать статический валидатор сгенерированного Cypher — парсить labels/relationship-types и отклонять любые вне allowlist (labels §8.1: Material, Experiment, Sample, ProcessingRegime, Property, Measurement, Evidence, Document, ... ; relations §8.2: HAS_MATERIAL, PROCESSED_BY, MEASURED, OF_PROPERTY, SUPPORTED_BY, REPORTS, USES_SAMPLE, ...).
- [ ] **Readonly transaction:** исполнять только в `session.execute_read` / readonly-режиме драйвера; запретить write-ключевые слова (CREATE/MERGE/DELETE/SET/REMOVE/DETACH/CALL {…} write-процедуры/`apoc.*` мутирующие) статической проверкой AST/regex allowlist по clauses.
- [ ] **LIMIT enforcement:** если в запросе нет `LIMIT` — принудительно добавить `LIMIT $max_rows` (default из config); отклонять запросы с `LIMIT` больше максимума.
- [ ] **Cost guard:** прогонять `EXPLAIN`/`PROFILE`-оценку плана (dbHits/rows estimate) перед исполнением; блокировать запросы выше порога (§18 «Cypher generation dangerous»); задать server-side query timeout (Neo4j `dbms.transaction.timeout` / per-query timeout) и клиентский timeout.
- [ ] **Retry with verifier:** при синтаксической/валидационной ошибке или пустом результате — до N ретраев: передать LLM сообщение об ошибке + schema, перегенерировать; verifier (§7.5 Node 9) проверяет соответствие результата вопросу; после исчерпания ретраев — fallback на шаблоны §12.2 или явный «no answer».
- [ ] Реализовать единый `guardrail_pipeline(cypher)`, применяющий все проверки по порядку: schema-ground → allowlist → readonly → LIMIT → cost guard → execute; при любом отказе — структурированная ошибка с причиной (для UI/логов).
- [ ] Зарегистрировать tool `run_cypher_readonly` (§7.4) как единый guarded-executor свободного Cypher поверх `guardrail_pipeline` (отличается от `run_cypher_template`): используется Text2Cypher и агентом, когда ни один шаблон §12.2 не подходит; write-операции недоступны by design.
- [ ] Заполнять `queryContext.generatedCypher` (§5.3) и tool_trace (§7.3) сгенерированным (валидированным) Cypher для прозрачности агента (§17 «Agent transparency»).
- [ ] Написать тесты guardrails: (a) write-запрос (CREATE/DELETE/SET) отклоняется; (b) label/relation вне allowlist отклоняется; (c) запрос без LIMIT получает принудительный LIMIT; (d) дорогой план (декартово произведение) блокируется cost guard; (e) сломанный Cypher триггерит retry и восстанавливается или деградирует к шаблону.

**Критерий приёмки:** ни один сгенерированный Text2Cypher не выполняется, минуя `guardrail_pipeline`; adversarial-тесты (write-операции, disallowed labels, отсутствие LIMIT, дорогой план) все блокируются; для валидного сложного вопроса без готового шаблона Text2Cypher возвращает результат с проставленным `generatedCypher`; tool `run_cypher_readonly` не может выполнить write-операцию.

### 12.11 Интеграция в agent/API и evaluation retrieval

Связывание retrieval с agent nodes (§7.5), endpoints (§6.2), передача в evidence assembler (Node 7) и прогон retrieval-метрик (§15).

- [ ] Подключить `orchestrator.retrieve` к node `structured_retrieval` (Mode A) и `hybrid_retrieval` (Mode B, с fusion+rerank) в `apps/agent-service/` (§7.5 Node 5/6); прокинуть результаты в `ScientificAgentState` (`retrieved_graph`, `retrieved_chunks`, `retrieved_experiments`, §7.3).
- [ ] Обеспечить передачу собранных evidence IDs и hits в `evidence_assembler` (§7.5 Node 7): measurement → table row → document page, группировка по claim; использовать tool `get_document_snippet` (§7.4) для подтяжки source snippets.
- [ ] Гарантировать, что рёбра `GraphResponse` несут `evidenceIds`, чтобы endpoint `/api/v1/evidence/by-edge/{edge_id}` (§6.2) резолвил кликабельные доказательства (Phase 4 acceptance «evidence snippets are clickable», §16).
- [ ] Реализовать endpoints `/api/v1/graph/query|expand|path|subgraph`, `/api/v1/search/hybrid|vector|keyword` (§6.2) поверх retrieval-модулей; формат ответа для `/api/v1/graph/query` — по примеру §6.2 (summary/experiments/gaps/graph/citations).
- [ ] Реализовать endpoints `/api/v1/experiments`, `/api/v1/experiments/{experiment_id}`, `/api/v1/experiments/query` (§6.2) поверх Mode A (шаблоны `experiment_lookup`/`material_regime_property`); реализовать tool `get_experiment_table` (§7.4), формирующий `TablePayload` для chat stream event `table` (§5.3 ChatStreamEvent) — «experiment query API», Phase 4 deliverable §16.
- [ ] Реализовать endpoint `/api/v1/graph/schema` (§6.2), отдающий canonical schema (§8.1 labels / §8.2 relationships из `packages/kg_schema/`) для schema grounding Text2Cypher (§12.10) и UI.
- [ ] Реализовать `build_graph_visualization_payload` (§7.4) как общий конвертер retrieval-результата в `GraphResponse` (§5.3) для chat stream event `graph` (§5.3 ChatStreamEvent).
- [ ] Реализовать эмиссию chat stream events `graph` и `table` (§5.3 ChatStreamEvent) из retrieval-результатов в SSE-поток чата (§6.2 `/api/v1/chat/sessions/{id}/stream`).
- [ ] Добавить кэширование retrieval-результатов по (normalized_query + filters + mode) для снижения латентности чата (§18 «Slow chat» → cached retrieval); использовать Redis (§13.1) с TTL и инвалидацией кэша при ingestion-upsert (§9.2 Step 7), чтобы не отдавать устаревший граф.
- [ ] В `packages/kg_eval/` реализовать retrieval-eval harness (`ragas`, §13.2): метрики context recall/precision, hit@k, MRR, nDCG на golden dataset (§15.1); отдельно замерить вклад каждого режима и reranker on/off.
- [ ] Задать и проверить бюджеты латентности per-mode (structured / hybrid+fusion+rerank / graphrag / gds) и зафиксировать в тестах/CI пороги (§15.2 graph query latency / chat latency).
- [ ] Написать end-to-end тест benchmark-вопроса (§15): «material X + regime Y + property Z» → experiments + values + evidence + graph (соответствие Phase 4 acceptance §16, включая «graph explorer can expand returned entities» через `/api/v1/graph/expand`).

**Критерий приёмки:** end-to-end запрос через agent/API возвращает experiments+values+evidence+graph (Phase 4 acceptance §16); endpoints `/api/v1/experiments/query` и `/api/v1/graph/schema` отвечают валидными payload'ами; retrieval-eval harness прогоняется на golden dataset и выдаёт hit@k/MRR/nDCG; включение reranker измеримо повышает precision@10 на golden-наборе (зафиксировано в отчёте eval).


---


## 13. LangGraph Agent Service

Раздел полностью покрывает §7 дизайн-документа: сервис `apps/agent-service` на LangGraph — контролируемый workflow научного QA со state, tools, узлами (§7.5), роутингом по intent (§7.2), verifier/critic-циклом дополнительного сбора доказательств, human-in-the-loop (interrupt), streaming прогресса, repeatable execution, логированием tool calls, checkpointer на Postgres и долговременной памятью (Store).

Общие зависимости от других разделов:
- **graph-service** (Cypher templates, DTO, schema validation) — источник для `run_cypher_*`, `find_graph_paths`, `expand_subgraph`, `build_graph_visualization_payload`.
- **search-service** (Qdrant/OpenSearch wrappers) — источник для `vector_search_qdrant`, `keyword_search_opensearch`, `hybrid_search`.
- **packages/kg_retrievers** — реализации graph/vector/hybrid retrievers и Mode D graph-algorithms (§10), reuse внутри tools.
- **packages/kg_extractors** — GLiNER/materials extractors для `entity_resolver` и `resolve_entities`.
- **packages/kg_schema** — Pydantic/LinkML определения labels/relationships (§8), allowlist для Text2Cypher.
- **packages/kg_common** — shared DTO, config, logging (`structlog`), OpenTelemetry.
- **packages/kg_eval** — golden-набор и метрики evaluation (§15), reuse в §13.25.
- **api-gateway** — проксирует SSE stream (`GET /api/v1/chat/sessions/{session_id}/stream`, §6.2) в UI, потребляет `ChatStreamEvent` (§5.3).
- **curation-service** — принимает `create_review_task` (§12.1).
- **Раздел «Knowledge graph schema»** (§8) — labels/relationships для узлов и Cypher.
- **Раздел «Gap analysis»** (§11) — правила и Cypher для `gap_analyzer` / `scan_gaps` / `detect_contradictions`.
- **Microsoft GraphRAG** (§10.1 Mode C) — community summaries для `graphrag_search`.

---

### 13.1 Scaffolding сервиса `apps/agent-service`

- [x] Создать структуру пакета `apps/agent-service/` по §6.1:
  - [x] `apps/agent-service/pyproject.toml` (или `requirements.txt`) с зависимостями из §13.2: `langgraph`, `langchain-core`, `llama-index`, `llama-index-graph-stores-neo4j`, `llama-index-vector-stores-qdrant`, `neo4j`, `qdrant-client`, `opensearch-py`, `pydantic`, `pydantic-settings`, `fastapi`, `uvicorn[standard]`, `orjson`, `structlog`, `opentelemetry-sdk`, `pint`, `gliner`, `sentence-transformers`, `fastembed`, `haystack-ai`, `networkx`, `pandas`, `polars`, `duckdb` (табличные experiment-payload'ы), `splink`, `pymatgen` (entity resolution, §13.9), `mlflow`, `ragas`, `deepeval` (eval, §15).
  - [x] Дополнительно (не перечислены в §13.2, но обязательны для рантайма): `langgraph-checkpoint-postgres` + `psycopg[binary,pool]` (Postgres checkpointer/Store, §13.20), OpenAI-совместимый LLM-клиент под `LLM_BASE_URL` (`langchain-openai`/`openai`), `sse-starlette` (SSE-стрим, §13.22), `httpx` (вызовы curation-service/graph-service).
  - [x] `apps/agent-service/src/agent_service/__init__.py`, `main.py` (FastAPI app), `app.py` (сборка ASGI).
  - [x] Каталоги: `src/agent_service/graph/` (StateGraph, nodes, routing), `src/agent_service/tools/`, `src/agent_service/state/`, `src/agent_service/integrations/` (Neo4j/Qdrant/OpenSearch/GraphRAG/Postgres клиенты), `src/agent_service/streaming/`, `src/agent_service/api/`, `src/agent_service/memory/`, `src/agent_service/prompts/` (версионированные промпты узлов, §13.23), `src/agent_service/eval/`.
  - [x] `apps/agent-service/tests/` для unit/integration/eval тестов.
- [x] Реализовать `Settings` (pydantic-settings) в `src/agent_service/config.py`: `NEO4J_URI/USER/PASSWORD`, `QDRANT_URL`, `OPENSEARCH_URL`, `POSTGRES_DSN` (checkpointer/store), `LLM_MODEL`, `LLM_BASE_URL`, `EMBEDDING_MODEL`, `RERANKER_MODEL`, `AGENT_PORT=8010`, `MAX_ROWS`, `MAX_VERIFY_ATTEMPTS`, feature-flags (`ENABLE_TEXT2CYPHER`, `ENABLE_GRAPHRAG`, `ENABLE_RERANK`, `ENABLE_HITL`, `ENABLE_GRAPH_ALGO`). Читает из `.env` (совместимо с `env_file` в §13.1 docker-compose).
- [x] Создать `src/agent_service/prompts/` с версионированными промпт-шаблонами для LLM-узлов (intent few-shot, query planner, verifier/critic, answer synthesis); версия промпта фиксируется для repeatable execution (§7.1, §13.23).
- [x] Настроить `structlog` + OpenTelemetry (`opentelemetry-sdk`) в `src/agent_service/observability.py`: JSON-логи, `trace_id`/`session_id`/`node`/`tool` в каждой записи.
- [x] Добавить health-endpoint `GET /health` (проверяет доступность Neo4j/Qdrant/OpenSearch/Postgres) и `GET /ready`.

**Критерий приёмки:** `uvicorn agent_service.main:app --port 8010` стартует; `GET /health` возвращает 200 с полем `dependencies` (все `ok`); `python -c "import agent_service.graph"` не падает; структура каталогов соответствует §6.1.

---

### 13.2 Вендоринг / клонирование OSS (§22)

- [ ] Задокументировать и закрепить версии зависимостей LangGraph-стека в `apps/agent-service/pyproject.toml` (source: `https://github.com/langchain-ai/langgraph`).
- [ ] Подключить LlamaIndex Property Graph / Text2Cypher retriever (`https://github.com/run-llama/llama_index`, `llama-index-graph-stores-neo4j`, `llama-index-vector-stores-qdrant`) — как pip-зависимости.
- [ ] Клонировать/вендорить Microsoft GraphRAG для Mode C (community summaries): `git clone https://github.com/microsoft/graphrag` в `third_party/graphrag/`; зафиксировать commit; описать интеграцию через `integrations/graphrag_client.py` (чтение community reports из хранилища GraphRAG или Neo4j).
- [ ] Подключить Neo4j Graph Data Science для Mode D graph algorithms (`https://github.com/neo4j/graph-data-science`) — как плагин Neo4j (compose) + Python-клиент `graphdatascience`; описать в `packages/kg_retrievers`/`structured_retrieval` (§13.11).
- [ ] (Опционально, для reference) вендорить Neo4j LLM Graph Builder (`https://github.com/neo4j-labs/llm-graph-builder`) и Haystack/Hayhooks (`https://github.com/deepset-ai/haystack`, `https://github.com/deepset-ai/hayhooks`) как источники паттернов; НЕ включать в runtime без обоснования.
- [ ] Подключить GLiNER (`gliner`) и materials-NER помощники из §22 (`https://github.com/CederGroupHub/MatEntityRecognition`, `https://github.com/lbnlp/MatBERT`) через `packages/kg_extractors` (зависимость раздела extraction).
- [ ] Подключить Splink (`https://github.com/moj-analytical-services/splink`) и Materials Project helpers (`https://github.com/materialsproject/api`, `https://github.com/materialsproject/pymatgen`) для `entity_resolver` (§13.9).
- [ ] Зафиксировать все клонированные commit-хэши в `third_party/VENDORED.md` (repo URL + commit + дата + причина).

**Критерий приёмки:** `pip install -e apps/agent-service` проходит без конфликтов версий; `third_party/VENDORED.md` перечисляет каждый склонированный репозиторий с URL и pinned commit; import GraphRAG-клиента, GLiNER и Neo4j GDS-клиента работает в CI.

---

### 13.3 ScientificAgentState и Pydantic-модели (§7.3)

- [ ] Реализовать в `src/agent_service/state/models.py` Pydantic-модели строго по §7.3:
  - [ ] `EntityMention(text, canonical_id: str|None, entity_type: str|None, confidence: float=0.0)`.
  - [ ] `EvidenceRef(evidence_id, source_id, doc_id: str|None, page: int|None, span_start: int|None, span_end: int|None, confidence: float)`.
- [ ] Реализовать `ScientificAgentState(TypedDict, total=False)` в `src/agent_service/state/state.py` со ВСЕМИ 20 полями §7.3: `session_id`, `user_id`, `user_question`, `normalized_question`, `language` (`Literal['ru','en']`), `intent`, `entities: list[EntityMention]`, `query_plan: dict`, `cypher_queries: list[str]`, `retrieved_graph: dict`, `retrieved_chunks: list[dict]`, `retrieved_experiments: list[dict]`, `evidence: list[EvidenceRef]`, `gaps: list[dict]`, `contradictions: list[dict]`, `answer_draft`, `final_answer`, `visualization_payload: dict`, `tool_trace: list[dict]`, `errors: list[str]`.
- [ ] Добавить служебные (не из §7.3, но нужные для workflow) поля state с явными reducers, чтобы не ломать §7.3-контракт: `numeric_constraints: dict`, `retrieval_strategy: list[str]`, `verifier_report: dict`, `verifier_attempts: int`, `needs_more_evidence: bool`, `interrupt_request: dict|None`, `messages` (для LLM). Определить их отдельным `TypedDict` расширением `ScientificAgentStateExt(ScientificAgentState)`.
- [ ] Определить reducers через `Annotated[list, operator.add]`/кастомные merge-функции для аккумулирующих полей (`evidence`, `tool_trace`, `errors`, `retrieved_chunks`, `cypher_queries`), чтобы параллельные/повторные узлы не затирали накопленное.
- [ ] Написать функции сериализации state ↔ JSON (`orjson`) для checkpointer/logging; убедиться, что Pydantic-модели дампятся детерминированно (`model_dump(mode="json")`).

**Критерий приёмки:** unit-тест инстанцирует `ScientificAgentState` со всеми 20 полями §7.3, прогоняет через reducers (два узла добавляют `evidence`/`tool_trace` — результаты объединяются, не затираются) и round-trip сериализацию `orjson` без потери данных.

---

### 13.4 Клиенты интеграций (Neo4j / Qdrant / OpenSearch / GraphRAG / Postgres)

- [ ] `integrations/neo4j_client.py`: async-драйвер `neo4j`; helper `run_readonly(cypher, params, timeout, limit)` — открывает **read-only transaction**, применяет query-timeout и `LIMIT`-guard (см. §13.5). Reuse Cypher templates из graph-service.
- [ ] `integrations/gds_client.py`: клиент Neo4j Graph Data Science (`graphdatascience`) для Mode D graph-алгоритмов (node similarity, link prediction, centrality, community detection, anomaly), read-only проекции (§13.11).
- [ ] `integrations/qdrant_client.py`: обёртка над `qdrant-client` для dense+sparse search, payload-фильтры (`material`, `property`, `lab`, `date`, `source_type`) — переиспользует retriever из `packages/kg_retrievers`.
- [ ] `integrations/opensearch_client.py`: обёртка над `opensearch-py` для BM25 keyword/facet search.
- [ ] `integrations/graphrag_client.py`: доступ к community summaries (Mode C, §10.1) — чтение community reports (global + local search).
- [ ] `integrations/postgres.py`: пул подключений к Postgres (`POSTGRES_DSN`) для checkpointer + Store + chat-session storage.
- [ ] `integrations/llm.py`: клиент LLM (chat + structured output) под `LLM_MODEL`/`LLM_BASE_URL`, retry/backoff, ограничение по токенам, детерминизм (`temperature=0`, фиксированный `seed`), кэш идентичных вызовов.
- [ ] `integrations/embeddings.py`: `sentence-transformers`/`fastembed` для entity-vector-search и dense retrieval; `integrations/reranker.py`: cross-encoder reranker (feature-flag `ENABLE_RERANK`).
- [ ] `integrations/curation_client.py`: `httpx`-клиент curation-service для `create_review_task` (§12.1).
- [ ] Ко всем клиентам — health-check и graceful degradation (если сервис недоступен, узел пишет запись в `state["errors"]` и продолжает по деградированному пути).

**Критерий приёмки:** integration-тест на docker-compose (§13.1) поднимает neo4j/qdrant/opensearch/postgres; каждый клиент выполняет smoke-запрос (Cypher `RETURN 1`, Qdrant `count`, OpenSearch `_cluster/health`, Postgres `SELECT 1`) успешно; при остановленном сервисе клиент не роняет процесс, а возвращает ошибку в `errors`.

---

### 13.5 Cypher templates и Text2Cypher guardrails (§7.4)

- [ ] Реализовать словарь `TEMPLATES` в `tools/cypher_templates.py`, включив шаблон `material_regime_property` дословно из §7.4 (параметры `$material`, `$operation`, `$temperature_c`, `$temperature_tolerance`, `$time_h`, `$time_tolerance`, `$property`, `$limit`).
- [ ] Добавить шаблоны для остальных intent'ов (§7.2): `entity_neighbors`, `experiment_lookup`, `evidence_by_ids`, `method_comparison`, `path_material_property` (reuse из graph-service, синхронизировать с §8-схемой labels/rels).
- [ ] Реализовать `run_cypher_template(template_name, params)`: валидирует имя шаблона по allowlist, подставляет параметры (только через query-params, не строковую конкатенацию), исполняет через read-only транзакцию, гарантирует `LIMIT`.
- [ ] Реализовать `TextToCypherRetriever`-путь (LlamaIndex) для сложных вопросов, но включать ТОЛЬКО с полным набором guardrails из §7.4:
  - [ ] **schema grounding**: передавать LLM только allowlist labels/relationships из `packages/kg_schema` (§8).
  - [ ] **readonly transaction**: исполнять сгенерированный Cypher только в read-only режиме.
  - [ ] **LIMIT injection**: автоматически добавлять/форсировать `LIMIT` (конфиг `MAX_ROWS`).
  - [ ] **query cost guard**: статический анализ (запрет `CREATE/MERGE/DELETE/SET/CALL apoc.*write`, ограничение числа `MATCH`/variable-length hops, `EXPLAIN`-оценка cost перед запуском).
  - [ ] **allowlist labels/relations**: отклонять запрос, если он ссылается на label/relationship вне схемы §8.
  - [ ] **retry with verifier**: при пустом/ошибочном результате — один retry с фидбеком от verifier (см. §13.16).
- [ ] Логировать сгенерированный Cypher в `state["cypher_queries"]` и в `queryContext.generatedCypher` (§5.3) для UI.

**Критерий приёмки:** попытка исполнить write-Cypher или Cypher с label вне allowlist отклоняется guard'ом (unit-тест на 5+ вредоносных/невалидных запросов); `run_cypher_template("material_regime_property", …)` на seed-данных возвращает строки с `evidence`; каждый исполненный Cypher появляется в `state["cypher_queries"]`.

---

### 13.6 Agent tools (§7.4)

Реализовать все 16 tools из §7.4 в `tools/` как LangChain/LangGraph-совместимые tools (`@tool` с типизированными Pydantic-args и docstring-описанием для tool-calling). Каждый tool логирует вызов в `tool_trace` (см. §13.23).

- [ ] `resolve_entities(mentions, context)` — GLiNER-mentions → Neo4j alias lookup → vector search по именам/описаниям → Splink candidate groups (§7.5 Node 3); reuse `packages/kg_extractors`. Возвращает `list[EntityMention]`.
- [ ] `search_material_aliases(name)` — поиск по aliases материалов в Neo4j + Materials Project / internal catalog IDs (§22 materials helpers).
- [ ] `run_cypher_readonly(cypher, params)` — исполнить произвольный **read-only** Cypher с guard'ами §13.5 (только через Text2Cypher-путь).
- [ ] `run_cypher_template(template_name, params)` — см. §13.5.
- [ ] `vector_search_qdrant(query, filters, top_k)` — dense/sparse search в Qdrant с payload-фильтрами (§7.5 Node 6).
- [ ] `keyword_search_opensearch(query, filters, top_k)` — BM25/facet search.
- [ ] `hybrid_search(query, filters, top_k)` — RRF/weighted fusion по формуле §10.2 (`0.35*dense + 0.25*sparse + 0.20*bm25 + 0.10*graph_proximity + 0.10*evidence_quality`) + опциональный cross-encoder rerank топ-50 (§10.2); reuse `packages/kg_retrievers`.
- [ ] `get_experiment_table(filters)` — возвращает табличный payload экспериментов (`id, material, processing, property, value, unit, effect, confidence, evidence_ids`) в формате §6.2 «Пример ответа».
- [ ] `get_evidence_by_ids(evidence_ids)` — подтягивает `EvidenceRef` + snippets из graph/store.
- [ ] `get_document_snippet(doc_id, page, span)` — фрагмент документа по span (для inline-citation).
- [ ] `find_graph_paths(source_id, target_id, max_hops)` — path-запрос Material↔Property (§5.2.3 path search).
- [ ] `expand_subgraph(node_ids, depth, types)` — one-hop/two-hop expand (§5.2.3), фильтр по типам.
- [ ] `scan_gaps(filters)` — исполняет gap-Cypher из §11.2 (missing_baseline, matrix gaps) и правила §11.1; возвращает `list[GapFinding]`.
- [ ] `detect_contradictions(filters)` — находит conflicting measurements (`contradictory_measurements`, §11.1) для одинаковых material/regime/property.
- [ ] `build_graph_visualization_payload(graph_data)` — конвертирует Neo4j-результат в `GraphResponse` (§5.3): `nodes[]` (`type ∈ Material|Experiment|ProcessingRegime|Property|Equipment|Paper|Claim|Lab|Person|Gap`, `confidence`, `evidenceCount`, `verified`, `missingFields`), `edges[]` (`confidence`, `evidenceCount`, `inferred`, `contradicted`, `evidenceIds`), `layoutHints`, `queryContext`.
- [ ] `create_review_task(target_type, target_id, reason, payload)` — вызывает curation-service (§12.1) для авто-создания review task (confidence<threshold / ambiguous ER / contradiction / missing critical field).
- [ ] Собрать реестр `TOOLS` (список из §7.4) в `tools/__init__.py`; сгенерировать tool-schemas для LLM tool-calling; unit-тест на соответствие имён списку §7.4 (ровно 16).

**Критерий приёмки:** реестр содержит ровно 16 tools с именами из §7.4; каждый tool имеет типизированную сигнатуру и docstring; для каждого есть unit-тест (мок-интеграция), проверяющий контракт входа/выхода; `build_graph_visualization_payload` выдаёт объект, валидный по TS-типу `GraphResponse` (§5.3); `hybrid_search` возвращает результаты, отсортированные по формуле §10.2 (проверяемо на фикстуре с известными скорами).

---

### 13.7 Node: `preprocess_question` (§7.5 Node 1)

- [ ] Реализовать узел в `graph/nodes/preprocess.py`: детектирует язык (`ru`/`en`) → `state["language"]`.
- [ ] Нормализовать единицы через `pint`: `°C`, `h`, `wt%`, `MPa`, `HV` (и синонимы: `C`, `град`, `часов`, `hours`, `wt.%`, `масс.%`).
- [ ] Извлечь численные constraints (temperature_c, time_h, композиции, диапазоны) → `state["numeric_constraints"]`.
- [ ] Привести русские/английские термины к canonical vocabulary (`packages/kg_schema` словарь синонимов) → `state["normalized_question"]`.
- [ ] Эмитить streaming-событие `tool_start`/`tool_end` для timeline «preprocess» (§5.2.2).

**Критерий приёмки:** для запроса «Что делали по Al-Cu при aging 180C 2h и как менялась hardness?» узел заполняет `language='ru'`, `numeric_constraints={temperature_c:180, time_h:2}`, `normalized_question` содержит канонические термины `aging`/`hardness`; unit-тест на 5 ru/en запросов с разными единицами (MPa/HV/wt%) даёт корректную нормализацию.

---

### 13.8 Node: `intent_classifier` и routing (§7.5 Node 2, §7.2)

- [ ] Реализовать `graph/nodes/intent_classifier.py`: LLM-классификация в один из 9 классов §7.5: `material_regime_property_query`, `entity_exploration`, `experiment_lookup`, `evidence_request`, `gap_analysis`, `contradiction_analysis`, `method_comparison`, `literature_summary`, `schema_help` → `state["intent"]`.
- [ ] Использовать structured output (Pydantic enum) + few-shot примеры; `temperature=0` для детерминизма.
- [ ] Реализовать routing-функцию `route_after_plan(state)` (§7.2 mermaid `ROUTE`): маппинг intent → retrieval branch:
  - [ ] structured (`material_regime_property_query`, `experiment_lookup`, `entity_exploration`) → `structured_retrieval` (CYPHER).
  - [ ] semantic (`literature_summary`, `method_comparison`, `evidence_request`) → `hybrid_retrieval` (HYBRID).
  - [ ] global corpus (`literature_summary` broad) → `graphrag_search` community search (GRAG, §10.1 Mode C, §13.13).
  - [ ] gap (`gap_analysis`, `contradiction_analysis`) → `gap_analyzer` (GAP).
  - [ ] graph algorithms (§10.1 Mode D — similar materials / missing links / important labs / method clusters / anomaly) → `structured_retrieval` с `graph_algo`-стратегией (Neo4j GDS, §13.11); выбирается когда план содержит `retrieval_strategy=['graph_algo']`.
  - [ ] `schema_help` → короткий путь к answer_synthesizer со schema-описанием (§6.2 `/graph/schema`).
- [ ] Поддержать план с несколькими strategies одновременно (`retrieval_strategy` в query_plan, §7.5 Node 4 может содержать `["cypher_template","hybrid_chunks","evidence_lookup","gap_scan"]`) — routing через fan-out/последовательный обход strategies.

**Критерий приёмки:** classifier на golden-наборе из ≥18 размеченных вопросов (по 2 на класс) даёт accuracy ≥0.85; routing-функция для каждого из 9 intent'ов возвращает корректную ветку (unit-тест, все ветки покрыты, включая GRAG и graph_algo); multi-strategy план проходит все указанные ветки.

---

### 13.9 Node: `entity_resolver` (§7.5 Node 3)

- [ ] Реализовать `graph/nodes/entity_resolver.py`, оркеструющий tool `resolve_entities`:
  - [ ] GLiNER для извлечения mentions из `normalized_question`.
  - [ ] lookup в Neo4j aliases (`search_material_aliases`).
  - [ ] vector search над entity names/descriptions (embeddings).
  - [ ] Splink-backed candidate groups (`https://github.com/moj-analytical-services/splink`).
  - [ ] Materials Project / internal catalog IDs где доступно (§22 `materialsproject/api`, `pymatgen`).
  - [ ] Заполнить `state["entities"]: list[EntityMention]` с `canonical_id`, `entity_type`, `confidence`.
- [ ] Реализовать clarification-логику: **ask clarification only if ambiguity blocks the answer** — если top-кандидаты неразличимы по confidence И сущность критична для intent → выставить `state["interrupt_request"]` и уйти в HITL-interrupt (§13.21); иначе продолжать с best-guess + пометкой low-confidence.
- [ ] При low-confidence resolution (< threshold) — вызвать `create_review_task` (§12.1) и добавить в `state["gaps"]` тип `low_confidence_entity_resolution` (§7.5 Node 8).

**Критерий приёмки:** для «Al-Cu» узел возвращает `EntityMention` с непустым `canonical_id`, `entity_type='Material'`, `confidence>0.5`; при заведомо неоднозначной сущности, критичной для ответа, узел инициирует interrupt (проверяемо в тесте); при low-confidence создаётся review task и gap `low_confidence_entity_resolution`.

---

### 13.10 Node: `query_planner` (§7.5 Node 4)

- [ ] Реализовать `graph/nodes/query_planner.py`: строит `state["query_plan"]` в формате §7.5 Node 4 (JSON): `intent`, `entities` (`material`/`operation`/`property`), `numeric_constraints` (`temperature_c`/`time_h`), `retrieval_strategy: list[str]`, `expected_outputs: list[str]` (`summary`/`experiments_table`/`graph`/`gaps`).
- [ ] Валидировать план Pydantic-моделью `QueryPlan`; strategy-значения из allowlist (`cypher_template`, `hybrid_chunks`, `evidence_lookup`, `gap_scan`, `graphrag_community`, `graph_algo`).
- [ ] Выбирать retrieval mode по §10.1 (Mode A/B/C/D) на основе intent + наличия точных numeric constraints/entities: Mode A (точные сущности+параметры)→`cypher_template`; Mode B (похожие/messy terminology/методология)→`hybrid_chunks`; Mode C (broad overview/«что известно в целом»)→`graphrag_community`; Mode D→`graph_algo`.
- [ ] Замапить Mode D (§10.1) на graph-algo подзадачи: `similar materials`→node similarity; `missing links`→link prediction; `important labs/teams`→centrality; `clusters of methods`→community detection; `anomaly detection`→GDS anomaly; выставлять `retrieval_strategy` включающий `graph_algo` когда intent этого требует.
- [ ] Планировщик пере-вызывается при verifier-retry (§13.16): принимает `verifier_report` и расширяет план (доп. strategy, ослабление tolerance, доп. entities) — детерминированно, с лимитом попыток.

**Критерий приёмки:** для примера из §7.5 Node 4 (Al-Cu / aging / hardness / 180°C / 2h) planner выдаёт JSON, эквивалентный эталону (intent + entities + numeric_constraints + retrieval_strategy + expected_outputs); повторный вызов после verifier-retry расширяет `retrieval_strategy` без дублей; невалидный plan отклоняется Pydantic-валидацией.

---

### 13.11 Node: `structured_retrieval` (§7.5 Node 5)

- [ ] Реализовать `graph/nodes/structured_retrieval.py`: исполняет Cypher-шаблоны (`run_cypher_template`) и/или Text2Cypher (§13.5) по плану.
- [ ] Neo4j graph traversal + path queries (`find_graph_paths`), collect evidence IDs в `state["evidence"]` (через `SUPPORTED_BY`/`Evidence`, §8.3).
- [ ] Реализовать путь Mode D (graph algorithms, §10.1): через Neo4j GDS (`integrations/gds_client.py`, §13.4) или `packages/kg_retrievers` — node similarity (similar materials), link prediction (missing links), centrality (important labs/teams), community detection (method clusters), anomaly detection; включается только при `graph_algo` в плане и `ENABLE_GRAPH_ALGO`; результат кладётся в `retrieved_graph`/`retrieved_experiments`.
- [ ] Заполнить `state["retrieved_graph"]` (nodes/edges), `state["retrieved_experiments"]` (табличные строки для `get_experiment_table`), `state["cypher_queries"]`.
- [ ] Применить фильтры из запроса (§6.2): `min_confidence`, `verified_only`, `date_from`, tolerance для temperature/time.

**Критерий приёмки:** на seed-графе запрос material_regime_property возвращает ≥1 experiment-строку с непустыми `evidence_ids`; `state["retrieved_graph"]` содержит согласованные nodes/edges; все evidence IDs из Cypher попадают в `state["evidence"]`; при `retrieval_strategy=['graph_algo']` узел выполняет GDS-запрос (например node similarity) и возвращает ранжированный список похожих материалов.

---

### 13.12 Node: `hybrid_retrieval` (§7.5 Node 6)

- [ ] Реализовать `graph/nodes/hybrid_retrieval.py`: Qdrant dense/sparse search + OpenSearch keyword/facet search.
- [ ] Слияние результатов RRF или weighted fusion по формуле §10.2; вычислить `graph_proximity_score` по §10.3 (1.0/0.8/0.6/0.4/0.2 по связности chunk↔measurement/experiment/material+property/document/community).
- [ ] Вычислять `evidence_quality_score` (компонент формулы §10.2, вес 0.10): boost за verified evidence, штраф за missing source span, штраф за low-confidence extraction — нормировать в [0,1] и подставлять в fusion.
- [ ] Cross-encoder reranking топ-50 (если `ENABLE_RERANK`); boost verified evidence, penalize missing source spans / low-confidence extraction (§10.2).
- [ ] Payload-фильтры: `material`, `property`, `lab`, `date`, `source_type` (§7.5 Node 6).
- [ ] Заполнить `state["retrieved_chunks"]` (с score-breakdown для отладки) и добавить evidence в `state["evidence"]`.

**Критерий приёмки:** unit-тест с зафиксированными dense/sparse/bm25/proximity/evidence-скорами воспроизводит итоговый ранжирующий score ровно по формуле §10.2; при `ENABLE_RERANK=1` порядок топ-N меняется согласно reranker; payload-фильтр `material=Al-Cu` отсекает нерелевантные chunks.

---

### 13.13 Node: `graphrag_search` (§7.2 GRAG, §10.1 Mode C)

- [ ] Реализовать `graph/nodes/graphrag_search.py` — ветка GRAG из §7.2 для broad/overview-вопросов (`literature_summary`, «какие направления были в теме», «что известно в целом», multi-document synthesis, §10.1 Mode C).
- [ ] Через `integrations/graphrag_client.py` (§13.4) читать community reports/summaries (Microsoft GraphRAG, `third_party/graphrag/`, §13.2) — global + local search по community-иерархии.
- [ ] Заполнять `state["retrieved_chunks"]` community-summary-фрагментами (с `community_id`) и добавлять их evidence в `state["evidence"]`; заполнять `state["retrieved_graph"]` community-узлами при необходимости.
- [ ] Прокидывать соответствие chunk↔community для `graph_proximity_score=0.2` (§10.3) в hybrid-фьюжене и для `layoutHints.communities` (§5.3) в visualization payload (§13.18).
- [ ] Feature-flag `ENABLE_GRAPHRAG`: при выключенном — деградировать на `hybrid_retrieval` (§13.12) и писать запись в `state["errors"]`.

**Критерий приёмки:** для broad-вопроса («какие направления по упрочнению Al-Cu исследовались») узел возвращает ≥1 community-summary с `community_id` и evidence; при `ENABLE_GRAPHRAG=0` вопрос обрабатывается через hybrid-путь без падения; community-идентификаторы доступны для `layoutHints.communities`.

---

### 13.14 Node: `evidence_assembler` (§7.5 Node 7)

- [ ] Реализовать `graph/nodes/evidence_assembler.py`: подтягивает snippets (`get_document_snippet`, `get_evidence_by_ids`).
- [ ] Связывает цепочку measurement → table row → document page (§7.5 Node 7, evidence-first model §8.3): формирует полные `EvidenceRef` с `doc_id`, `page`, `span_start`, `span_end`.
- [ ] Собирает citations и группирует evidence по claim (`state["evidence"]` + группировка в `visualization_payload`/answer).
- [ ] Дедуплицирует evidence по `evidence_id`; сортирует по confidence.

**Критерий приёмки:** для набора measurement-узлов assembler возвращает `EvidenceRef` с заполненными `doc_id`/`page`/`span_*`; evidence сгруппированы по claim; дубликаты по `evidence_id` устранены (unit-тест на входе с повторами).

---

### 13.15 Node: `gap_analyzer` (§7.5 Node 8, §11)

- [ ] Реализовать `graph/nodes/gap_analyzer.py`, применяющий tools `scan_gaps` + `detect_contradictions`.
- [ ] Покрыть все правила §7.5 Node 8 / §11.1: `missing_property_value`, `missing_unit`, `missing_processing_parameter`, `missing_baseline`, `missing_equipment`, `missing_source_span`, `low_confidence_entity_resolution`, `conflicting_measurements`/`contradictory_measurements`, `unverified_critical_claim`/`unverified_claim`, `low_coverage_material`, `orphan_entity`.
- [ ] Использовать Cypher из §11.2 (missing baseline; material/regime/property matrix gaps) через graph-service.
- [ ] Заполнить `state["gaps"]` (`type`, `entity_id`, `description` — формат §6.2 «Пример ответа») и `state["contradictions"]`.
- [ ] Для критичных gap'ов (missing critical field, contradiction) вызвать `create_review_task` (§12.1).

**Критерий приёмки:** на seed-графе с известными пробелами узел детектирует `missing_baseline` для эксперимента без baseline и matrix-gap для material без measured property (совпадает с ручной проверкой Cypher §11.2); каждый gap имеет `type` из справочника §11.1; контрадикции с conflicting values попадают в `state["contradictions"]`.

---

### 13.16 Node: `verifier` / critic + цикл дополнительного сбора доказательств (§7.5 Node 9, §7.2)

- [ ] Реализовать `graph/nodes/verifier.py`, выполняющий проверки §7.5 Node 9:
  - [ ] каждое численное значение в `answer_draft` имеет привязанное evidence (сверка чисел ↔ `state["evidence"]`).
  - [ ] единицы не смешаны (одна физ. величина — одна каноническая единица, через `pint`).
  - [ ] материал и режим не подменены (entities в ответе совпадают с `state["entities"]`/plan).
  - [ ] answer не содержит unsupported claim (каждое утверждение мапится на evidence/graph).
  - [ ] contradictions явно отмечены (если `state["contradictions"]` непуст — в ответе есть блок).
  - [ ] для low-confidence добавлен warning.
- [ ] Заполнять `state["verifier_report"]` (список нарушений с severity) и флаг `state["needs_more_evidence"]`.
- [ ] Реализовать conditional edge `route_after_verify(state)` (§7.2 `VERIFY -->|needs more evidence| PLAN`): если есть исправимые пробелы (не хватает evidence для числа, пустой retrieval) И `verifier_attempts < MAX_VERIFY_ATTEMPTS` → инкремент `verifier_attempts` и переход обратно на `query_planner` (доп. сбор доказательств); иначе → `answer_synthesizer`.
- [ ] Гарантировать ограничение цикла (`MAX_VERIFY_ATTEMPTS`, конфиг) для предотвращения бесконечного loop; при исчерпании — синтезировать ответ с явными warning'ами о недостающих доказательствах.
- [ ] Citation guardrail (Phase 5 acceptance §16): блокировать выпуск числового claim без evidence — если после ретраев claim не подтверждён, удалять/помечать его как «unsupported» в `answer_draft`.

**Критерий приёмки:** ответ с числом без evidence помечается verifier'ом как нарушение и (при наличии бюджета попыток) инициирует возврат на planner; после `MAX_VERIFY_ATTEMPTS` цикл завершается и финальный ответ НЕ содержит числовых claim без evidence (проверяемо тестом: подставлен draft с «hardness = 148 HV» без evidence → в финале claim либо подтверждён, либо снят/помечен); смешанные единицы (HV и MPa для hardness) детектируются.

---

### 13.17 Node: `answer_synthesizer` (§7.5 Node 10)

- [ ] Реализовать `graph/nodes/answer_synthesizer.py`, формирующий `state["final_answer"]` в структуре §7.5 Node 10 и §5.2.2: краткая сводка; «что найдено»; таблица экспериментов; «что влияет на эффект»; «пробелы»; «на что опирается ответ» (citations); ссылка на graph payload.
- [ ] Сформировать таб-структуру ответа под UI-вкладки §5.2.2: `[Summary] [Experiments] [Evidence] [Graph] [Gaps] [Contradictions]` — по секции/пейлоуду на каждую вкладку.
- [ ] Вычислить и включить агрегаты (как в примере §5.2.2): число экспериментов и статей, диапазон эффекта (напр. «hardness +12–28%»), группировку расходящихся случаев по причине (different quench rate / composition), число случаев без baseline (data gap).
- [ ] Inline-citations: каждое число/claim сопровождается ссылкой на `EvidenceRef` (`ev:*`), совместимо с UI inline citations (§5.2.2).
- [ ] Сформировать поле `citations: list` в формате ответа §6.2 (список `EvidenceRef`/`ev:*`, на которые опирается ответ).
- [ ] Собрать табличный `TablePayload` экспериментов (§5.3 `table`) из `state["retrieved_experiments"]` в формате примера ответа §6.2 (`material, processing, property, value, unit, effect, confidence, evidence_ids`).
- [ ] Собрать экспортируемый report-артефакт (для кнопки `export report`, §5.2.2): самодостаточный ответ со всеми секциями, таблицей и citations (markdown/JSON).
- [ ] Warning-panel данные: contradictions, low-confidence, missing data (§5.2.2) — из `state["contradictions"]`/`gaps`/verifier_report.
- [ ] Поддержать вывод на языке пользователя (`state["language"]`).

**Критерий приёмки:** для эталонного вопроса (§5.2.2 Al-Cu пример) ответ содержит все секции/вкладки (сводка/эксперименты/evidence/graph/пробелы/contradictions), таблицу экспериментов, агрегаты (счётчики экспериментов/статей, диапазон эффекта) и inline-citations; ни одно числовое значение не выводится без соответствующего `evidence_id` (перепроверка verifier'ом); язык ответа совпадает с языком вопроса.

---

### 13.18 Node: `visualization_payload` builder (§7.2 VIS)

- [ ] Реализовать `graph/nodes/visualization_payload.py`, вызывающий `build_graph_visualization_payload` → `state["visualization_payload"]` в формате `GraphResponse` (§5.3).
- [ ] Мапить визуальные кодировки (§5.2.3): `node.type` → цвет; `evidenceCount`/centrality → размер; `edge.evidenceCount` → толщина; `edge.confidence` → opacity; `inferred=true` → dashed; `contradicted=true` → red; `missingFields`непусто → hollow node; `verified=true` → lock. Все атрибуты класть в узлы/рёбра payload.
- [ ] Заполнить `layoutHints` (`rootNodeIds` из resolved entities, `communities` из GraphRAG — §13.13) и `queryContext` (`userQuery`, `filters`, `generatedCypher` из `state["cypher_queries"]`).
- [ ] Добавить `Gap`-узлы (§5.3 `type:'Gap'`) для найденных пробелов, чтобы UI Gap Dashboard (§5.2.7) мог их отрисовать.

**Критерий приёмки:** payload валиден по TS-типу `GraphResponse` (§5.3), проходит JSON-schema-валидацию; contradicted edges помечены `contradicted=true`, inferred — `inferred=true`, узлы с `missingFields` присутствуют; `queryContext.generatedCypher` содержит исполненный Cypher; payload рендерится в Reagraph-фикстуре без ошибок.

---

### 13.19 Сборка графа (StateGraph), routing и compile (§7.2)

- [ ] В `graph/build.py` собрать `StateGraph(ScientificAgentStateExt)` со всеми узлами §7.5 (§13.7–§13.18): `preprocess_question`, `intent_classifier`, `entity_resolver`, `query_planner`, `structured_retrieval`, `hybrid_retrieval`, `graphrag_search`, `gap_analyzer`, `evidence_assembler`, `verifier`, `answer_synthesizer`, `visualization_payload`.
- [ ] Задать edges строго по §7.2 mermaid: `START→preprocess→intent→entity_resolver→query_planner→ROUTE`; ветки ROUTE (structured/hybrid/graphrag/gap) → `evidence_assembler` → `verifier`; conditional `verifier` (`needs_more_evidence`→`query_planner` | иначе→`answer_synthesizer`); `answer_synthesizer→visualization_payload→END`.
- [ ] Реализовать conditional edges через `add_conditional_edges` с функциями `route_after_plan` (§13.8) и `route_after_verify` (§13.16).
- [ ] Скомпилировать граф с checkpointer + store (§13.20) и `interrupt_before`/`interrupt` для HITL (§13.21).
- [ ] Экспортировать функцию `get_compiled_graph()` (singleton), переиспользуемую HTTP-слоем и тестами.
- [ ] Сгенерировать и закоммитить визуализацию графа (`graph.get_graph().draw_mermaid()`), сверить с §7.2.

**Критерий приёмки:** `graph.get_graph().draw_mermaid()` структурно совпадает с диаграммой §7.2 (те же узлы и рёбра, включая ветку GRAG и обратное ребро verifier→planner); `get_compiled_graph()` возвращает скомпилированный граф; end-to-end прогон на seed-вопросе доходит от START до END и заполняет `final_answer` + `visualization_payload`.

---

### 13.20 Checkpointer на Postgres + долговременная память (Store)

- [ ] Подключить `PostgresSaver` (LangGraph, `langgraph-checkpoint-postgres`) как checkpointer поверх `POSTGRES_DSN`; выполнить `checkpointer.setup()` (создание таблиц `checkpoints`, `checkpoint_writes`, `checkpoint_blobs`) через миграцию.
- [ ] Прокидывать `thread_id = session_id` в `config={"configurable":{"thread_id": session_id}}` при каждом invoke/stream — обеспечивает per-session persistence и resume после interrupt.
- [ ] Реализовать resume: повторный вызов с тем же `thread_id` восстанавливает state из последнего checkpoint (repeatable execution, §7.1).
- [ ] Подключить `PostgresStore` (LangGraph long-term memory Store) для кросс-сессионной памяти: `store.setup()`; namespace `(user_id, "memories")`.
- [ ] Записывать в Store: подтверждённые пользователем канонические сущности/aliases, предпочтения пользователя, часто используемые фильтры; читать в `entity_resolver`/`query_planner` для персонализации.
- [ ] Реализовать TTL/размер-лимиты и очистку памяти; индекс для semantic search по памяти (embeddings), если включено.

**Критерий приёмки:** после падения/перезапуска процесса вызов с тем же `thread_id` восстанавливает частично выполненный state (тест: прерывание после `structured_retrieval`, resume продолжает с `verifier`); запись в Store сохраняется между двумя разными `session_id` одного `user_id` (long-term memory) и подхватывается в `entity_resolver` следующей сессии.

---

### 13.21 Human-in-the-loop (interrupt)

- [ ] Реализовать HITL через LangGraph `interrupt()` в узлах, требующих подтверждения: `entity_resolver` (неоднозначная критичная сущность, §7.5 Node 3), `verifier` (критичный unsupported claim перед выпуском), опционально `query_planner` (подтверждение дорогого/широкого запроса).
- [ ] При interrupt заполнять `state["interrupt_request"]` структурой для UI: `type` (`clarify_entity`/`confirm_claim`/`approve_query`), `question`, `options`, `context`.
- [ ] Реализовать API-эндпоинт возобновления: `POST /internal/agent/resume` принимает `session_id` + `resume_value`; вызывает граф с `Command(resume=resume_value)` и тем же `thread_id`.
- [ ] Эмитить в stream отдельное событие о необходимости ввода пользователя (маппится на UI-панель, §5.2.2 warning/clarification); фронтенд собирает ответ и шлёт resume.
- [ ] Feature-flag `ENABLE_HITL`: при выключенном — узлы идут best-guess без остановки (для batch/eval).

**Критерий приёмки:** тест с неоднозначной сущностью: граф останавливается на interrupt, отдаёт `interrupt_request` c вариантами; после `resume` с выбранным вариантом граф продолжает и завершает ответ с корректной сущностью; при `ENABLE_HITL=0` тот же вход проходит без остановки.

---

### 13.22 Streaming прогресса (SSE / ChatStreamEvent §5.3)

- [ ] Реализовать `streaming/events.py`: маппинг событий LangGraph (`astream_events` / `stream_mode=["updates","messages","custom"]`) в `ChatStreamEvent` (§5.3): `token`, `tool_start`, `tool_end`, `evidence`, `graph`, `table`, `gap`, `error`.
- [ ] `token` — стрим токенов из `answer_synthesizer` (LLM streaming).
- [ ] `tool_start`/`tool_end` — по каждому tool-вызову, с `tool`, `args`, `summary`, `dataRef`; формирует tool-call timeline UI (§5.2.2: `resolved entities`, `graph query`, `vector search`, `evidence check`, `gap scan`).
- [ ] `evidence` — при пополнении `state["evidence"]`; `graph` — при готовности `visualization_payload`; `table` — `TablePayload` экспериментов; `gap` — `GapFinding[]`; `error` — из `state["errors"]`.
- [ ] Реализовать endpoint `GET /internal/agent/stream` (SSE, `text/event-stream`, `sse-starlette`), который api-gateway проксирует в `GET /api/v1/chat/sessions/{session_id}/stream` (§6.2). Поддержать backpressure и heartbeat/keep-alive.
- [ ] Гарантировать корректный порядок и завершающее событие (end-of-stream marker).

**Критерий приёмки:** e2e-тест: клиент подписывается на SSE и получает последовательность `tool_start`/`tool_end` для entity/graph/vector/evidence/gap, затем `evidence`, `graph`, `table`, `gap`, поток `token` и финальный маркер; каждый эмитируемый объект валиден по union-типу `ChatStreamEvent` (§5.3); при ошибке интеграции приходит событие `error`, поток не виснет.

---

### 13.23 Логирование tool calls, observability, repeatable execution (§7.1)

- [ ] Реализовать декоратор/обёртку `traced_tool`, который на каждый tool-вызов дописывает запись в `state["tool_trace"]`: `{tool, args, started_at, finished_at, duration_ms, status, summary, dataRef, error?}`.
- [ ] Прокидывать OpenTelemetry span на каждый node и tool (parent — session/trace); экспорт в коллектор (§13.4 observability); дополнительно поддержать LangSmith trace debugging (§15.3).
- [ ] Логировать через `structlog` каждый переход узла (`node_enter`/`node_exit`) с `session_id`, `intent`, latency.
- [ ] Repeatable execution: фиксировать LLM `temperature=0`+`seed`, версионировать промпты (`prompts/` с версией), сохранять полный `tool_trace` и `cypher_queries` в checkpoint — прогон восстановим и воспроизводим.
- [ ] Реализовать `GET /internal/agent/trace/{session_id}` — возврат `tool_trace` для отладки/аудита (совместимо с audit logs §6.2).
- [ ] Метрики (Prometheus/OTel): счётчики tool-вызовов, node-latency, verifier-retry rate, interrupt rate, доля ответов без unsupported claims.

**Критерий приёмки:** после прогона `state["tool_trace"]` содержит по записи на каждый фактический tool-вызов с ненулевым `duration_ms` и `status`; два прогона одного вопроса с одинаковым seed дают идентичные `intent`/`query_plan`/`cypher_queries` (детерминизм); `GET /internal/agent/trace/{session_id}` возвращает полный трейс; метрики экспортируются.

---

### 13.24 HTTP API сервиса и хранение chat-сессий

- [ ] Реализовать внутренние endpoints `apps/agent-service` (порт 8010), потребляемые api-gateway:
  - [ ] `POST /internal/agent/sessions` — создать сессию (`session_id`, `user_id`), инициализировать thread.
  - [ ] `POST /internal/agent/sessions/{session_id}/messages` — принять вопрос, запустить граф (invoke/stream).
  - [ ] `GET /internal/agent/stream` — SSE (§13.22).
  - [ ] `POST /internal/agent/resume` — HITL resume (§13.21).
  - [ ] `GET /internal/agent/trace/{session_id}` — трейс (§13.23).
- [ ] Реализовать storage chat-сессий и сообщений в Postgres (таблицы `chat_sessions`, `chat_messages`) — либо поверх LangGraph checkpoints, либо отдельные таблицы; согласовать с api-gateway `/api/v1/chat/*` (§6.2).
- [ ] Валидация запросов (Pydantic), rate limit hook, audit-запись на каждый message.
- [ ] Определить контракт «agent-service ↔ api-gateway» (OpenAPI): api-gateway маппит публичные `/api/v1/chat/sessions/*` → внутренние `/internal/agent/*`.

**Критерий приёмки:** через api-gateway (`POST /api/v1/chat/sessions` → `POST …/messages` → `GET …/stream`) проходит полный диалог; сессия и сообщения персистятся в Postgres и доступны при `GET /api/v1/chat/sessions/{session_id}`; OpenAPI-схема сервиса генерируется и валидна.

---

### 13.25 Тестирование и evaluation (§15, §16 Phase 5)

- [ ] Unit-тесты на каждый узел §7.5 (мок-интеграции) и каждый tool §7.4.
- [ ] Integration-тесты на docker-compose (§13.1) с seed-графом/индексами: end-to-end прогон по каждому из 9 intent'ов.
- [ ] Собрать golden-dataset §15.1 (50–100 вопросов) с распределением: 20 material-regime-property, 15 experiment lookup, 10 evidence, 10 gap, 10 contradiction, 10 broad literature summary; каждый вопрос в YAML-формате §15.1 (`question`, `expected_entities`, `expected_answer_contains`, `must_not_contain`, `required_graph_nodes`) в `packages/kg_eval`.
- [ ] Подключить eval-harness `packages/kg_eval` + `ragas`/`deepeval` (§13.2, §15): прогон golden-набора вопросов (§15.1).
- [ ] Реализовать метрики §15.2: retrieval (`Recall@10` evidence, `MRR` experiments, entity-resolution precision/recall, graph-path correctness), answer quality (citation precision, unsupported-claim rate, numeric accuracy, unit accuracy, contradiction-detection recall, gap-detection precision).
- [ ] Трекинг прогонов в MLflow (§15.3); детерминированные custom-проверки числовых значений и citations (§15.3); экспорт agent-trace в LangSmith/OpenTelemetry (§15.3).
- [ ] Тест citation guardrail: ни один числовой claim не выпускается без evidence (Phase 5 acceptance §16: «no numeric claim without evidence»).
- [ ] Тест verifier-retry: сценарий с недостающим evidence инициирует ретрай и улучшает ответ либо помечает пробел.
- [ ] Тест «UI shows tool calls»: stream содержит tool_start/tool_end для основных инструментов; «graph and table attachments render» — payload валиден для Reagraph/таблицы.
- [ ] CI-джоба: линт (`ruff`), типы (`mypy`), тесты, eval-gate (порог метрик из §15.2).

**Критерий приёмки:** чат отвечает на main benchmark вопросы (§16 Phase 5 acceptance); в CI: unit+integration зелёные, eval-метрики ≥ порога §15.2, guardrail-тест подтверждает 0 unsupported числовых claim, stream содержит tool-calls, graph/table attachments валидны.

---

### 13.26 Docker и deployment (§13.1)

- [ ] Написать `apps/agent-service/Dockerfile` (multi-stage, python slim, non-root) — совместимо с сервисом `agent` в §13.1 (`build: ./apps/agent-service`, `ports: ["8010:8010"]`, `depends_on: [api, neo4j, qdrant, opensearch]`).
- [ ] Добавить/сверить сервис `agent` в `infra/docker-compose.yml`; прокинуть `POSTGRES_DSN` (для checkpointer/store) и добавить `postgres` в `depends_on` агента (в §13.1 у `agent` его нет — обязательно дополнить).
- [ ] Прокинуть env из `.env` (§13.1 `env_file`): neo4j/qdrant/opensearch/postgres/LLM/embedding настройки.
- [ ] Обеспечить наличие плагина Neo4j GDS в compose (Mode D, §13.11) — расширить `NEO4J_PLUGINS` (`apoc` + `graph-data-science`).
- [ ] Реализовать startup-миграции (checkpointer/store setup, chat-session таблицы) при старте контейнера (idempotent).
- [ ] Healthcheck в compose (`GET /health`); graceful shutdown (закрытие драйверов Neo4j/Qdrant/OpenSearch/PG-пулов).
- [ ] (Опционально) Helm-чарт `infra/helm/agent-service` для k8s-деплоя (§6.1 `infra/helm`).

**Критерий приёмки:** `docker compose up agent` поднимает сервис на `:8010`, healthcheck зелёный, миграции применяются идемпотентно; агент подключается к neo4j/qdrant/opensearch/postgres из compose и обрабатывает end-to-end вопрос через api-gateway.


---


## 14. FastAPI API Gateway

Раздел покрывает полную реализацию публичного API-шлюза (`apps/api-gateway/`, §6.1) для frontend и внешних клиентов. Шлюз реализует все endpoints §6.2, отвечает за auth/session, SSE/WebSocket streaming для чата, upload/download документов, отслеживание job status, request validation, rate limits, audit logs и опциональный Neo4j GraphQL proxy. Помимо явного списка §6.2 (36 endpoints), шлюз должен предоставлять derived-endpoints для экранов §5.2 (список чат-сессий, saved views, review queue, split/mark-inferred/manual-evidence/gap-annotate/schema-edit, decision history, facets, экспорт). Форматы запросов/ответов берутся строго из §6.2 (пример graph query/response), §5.3 (GraphResponse, ChatStreamEvent, GraphNode, GraphEdge), §8.3 (Evidence), §11.1 (GapTypes), §12.2 (human actions) и §12.3 (CurationEvent).

Технологический стек (§13.2): `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `orjson`, `structlog`, `opentelemetry-sdk`, `redis` (job/session/rate-limit backend), `neo4j` (для GraphQL proxy и schema introspection), `qdrant-client`, `opensearch-py`. Шлюз НЕ содержит бизнес-логики графа/поиска/агента — он проксирует и оркестрирует вызовы к `agent-service` (порт 8010), `graph-service`, `search-service`, `ingestion-service` (порт 8020), `curation-service`, а также напрямую к Neo4j/Qdrant/OpenSearch/Postgres/Redis/MinIO по §13.1. Публичный порт `8000` (§13.1).

Зависимости от других разделов: раздел «Agent system на LangGraph» (§7, streaming событий чата), «Knowledge graph schema» (§8, DTO сущностей/evidence), «Ingestion pipeline» (§9, jobs), «Retrieval strategy» (§10, search endpoints), «Gap analysis» (§11), «Curation workflow» (§12, review/merge/split/decision history), пакет `packages/kg_common/` (shared DTOs, config, logging) и `packages/kg_schema/` (Pydantic/LinkML модели).

---

### 14.1 Каркас сервиса, конфигурация и структура (apps/api-gateway/)

- [x] Создать пакет `apps/api-gateway/` с `pyproject.toml`, зафиксировать зависимости из §13.2 (`fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `orjson`, `structlog`, `opentelemetry-sdk`) плюс `redis`, `httpx`, `python-multipart`, `sse-starlette`, `websockets`, `slowapi`/собственный лимитер; собирается `pip install -e apps/api-gateway`.
- [x] Создать структуру внутри `apps/api-gateway/app/`:
    - [x] `main.py` — фабрика `create_app()`, монтирование роутеров, middleware, lifespan.
    - [x] `config.py` — `Settings(BaseSettings)` через `pydantic-settings`, читает `.env` (§13.1): URL и креды `NEO4J_URI`, `QDRANT_URL`, `OPENSEARCH_URL`, `POSTGRES_DSN`, `REDIS_URL`, `MINIO_*`, `AGENT_SERVICE_URL=http://agent:8010`, `INGESTION_SERVICE_URL=http://ingestion:8020`, `GRAPH_SERVICE_URL`, `SEARCH_SERVICE_URL`, `CURATION_SERVICE_URL`, `JWT_SECRET`, `RATE_LIMIT_*`, `ENABLE_GRAPHQL_PROXY`.
    - [x] `routers/` — по одному модулю на группу endpoints §6.2 (`chat.py`, `entities.py`, `graph.py`, `search.py`, `experiments.py`, `evidence.py`, `gaps.py`, `documents.py`, `ingest.py`, `admin.py`, `graphql_proxy.py`) плюс `curation.py`, `views.py` (derived-endpoints §5.2).
    - [x] `schemas/` — Pydantic-модели request/response, реэкспорт из `packages/kg_common` и `packages/kg_schema`.
    - [x] `clients/` — httpx-обёртки к внутренним сервисам (`agent_client.py`, `graph_client.py`, `search_client.py`, `ingestion_client.py`, `curation_client.py`) и драйверы (`neo4j_client.py`, `qdrant_client.py`, `opensearch_client.py`, `redis_client.py`, `minio_client.py`, `postgres_client.py`).
    - [x] `middleware/` — auth, rate limit, request-id, audit, error handling.
    - [x] `deps.py` — FastAPI dependencies (`get_current_user`, `get_db`, `get_redis`, пагинация).
- [x] Настроить единый префикс роутинга `/api/v1` через `APIRouter(prefix="/api/v1")`; проверяемо: все пути из §6.2 доступны под этим префиксом.
- [x] Настроить `ORJSONResponse` как `default_response_class` (пакет `orjson` из §13.2); проверяемо: заголовок `content-type: application/json`, сериализация `datetime`/`UUID` без ошибок.
- [x] Реализовать `lifespan`-контекст: инициализация пулов Neo4j/Qdrant/OpenSearch/Redis/Postgres/MinIO при старте и корректное закрытие при shutdown; при недоступности зависимости — fail-fast с понятной ошибкой в лог `structlog`.
- [x] Написать `Dockerfile` (`apps/api-gateway/Dockerfile`) под сервис `api` из §13.1 (`ports: ["8000:8000"]`, `env_file: .env`, `depends_on: [postgres, redis, neo4j, qdrant, opensearch]`); `docker compose up api` поднимает сервис, healthcheck зелёный.
- [x] Настроить структурированное логирование `structlog` (§13.2): JSON-логи с полями `request_id`, `user_id`, `route`, `latency_ms`, `status_code`.

**Критерий приёмки:** `docker compose up api` запускает сервис на `:8000`, `GET /api/v1/admin/health` возвращает `200`, OpenAPI-схема `/openapi.json` содержит все 36 endpoint'ов из §6.2, все роутеры зарегистрированы под `/api/v1`.

### 14.2 Общие модели, валидация запросов и обработка ошибок

- [x] Определить в `schemas/common.py` базовые модели: `PageParams(limit:int<=200, offset:int>=0)`, `ErrorResponse(code:str, message:str, details:dict, request_id:str)`, `Paginated[T](items, total, limit, offset)`.
- [x] Настроить глобальный exception handler для `RequestValidationError` → `422` с телом `ErrorResponse` (поле `details` = список ошибок Pydantic); проверяемо: невалидный body возвращает `422` со списком путей полей.
- [x] Настроить handler для `HTTPException` и кастомных доменных исключений (`EntityNotFound`→`404`, `Conflict`→`409`, `RateLimited`→`429`, `Unauthorized`→`401`, `Forbidden`→`403`, `UpstreamUnavailable`→`503`).
- [x] Реализовать проброс ошибок вышестоящих сервисов: при `5xx`/timeout от `agent`/`graph`/`search`/`ingestion`/`curation` возвращать `502/504` с `ErrorResponse`, не раскрывая внутренние стектрейсы.
- [x] Включить строгую валидацию: `model_config = ConfigDict(extra="forbid")` для всех входных моделей; неизвестные поля → `422`.
- [x] Реализовать серверную пагинацию и сортировку как переиспользуемую dependency (`limit`, `offset`, `sort`); проверяемо на `entities/search`, `experiments`, `gaps`, `ingest/jobs`, `chat/sessions`, `curation/review-queue`, `documents`.
- [x] Добавить request-size-limit middleware (например 25 MB для JSON, отдельный лимит для upload — см. 14.9); превышение → `413`.

**Критерий приёмки:** любой endpoint при некорректном вводе отдаёт `422` с телом `ErrorResponse`; отсутствие ресурса — `404`; при падении upstream — `502/504`; все ответы об ошибке содержат `request_id`.

### 14.3 Auth и session management

- [x] Реализовать `middleware/auth.py`: проверка JWT (Bearer) через `JWT_SECRET`, извлечение `user_id`, `roles`; невалидный/просроченный токен → `401`.
- [x] Реализовать endpoints логина/выдачи токена (или интеграцию с внешним IdP) достаточные для frontend; хранить refresh/session в Redis (`REDIS_URL` из §13.1) с TTL.
- [x] Реализовать dependency `get_current_user()` и `require_roles(...)` для RBAC (роли: `viewer`, `curator`, `admin`) — согласовано с Phase 9 «add role-based access».
    - [x] `viewer` — только read endpoints (search/entities/graph/experiments/evidence read/gaps read/documents read/chat/views).
    - [x] `curator` — плюс `entities/merge`, `entities/{id}/split`, `entities/{id}/aliases`, `evidence/{id}/review`, `evidence` (manual create), `experiments/{id}/verify`, `gaps/scan`, `gaps/{id}/annotate`, `curation/review-queue` actions, `relations/{id}/mark-inferred`, `documents/upload`, `reindex`.
    - [x] `admin` — плюс `admin/*`, `ingest/jobs/*/cancel`, `schema/terms` (edit schema terms).
- [x] Реализовать серверные chat-сессии как отдельный ресурс (не путать с auth-сессиями): хранение метаданных сессии в Postgres (`kg_app`), сообщений — в Postgres, привязка к `user_id`.
- [x] Защитить все `/api/v1/*` endpoints auth-зависимостью, кроме `admin/health` (liveness) и, опционально, `admin/metrics` (закрыт internal-токеном).

**Критерий приёмки:** запрос без валидного JWT к защищённому endpoint возвращает `401`; `viewer` при вызове `POST /entities/merge` получает `403`; chat-сессия создаётся и привязывается к `user_id`, доступ к чужой сессии → `403/404`.

### 14.4 Chat endpoints, SSE и WebSocket streaming (интеграция с §7)

- [ ] `POST /api/v1/chat/sessions` — создать chat-сессию; body: `{ "title"?, "metadata"? }`; ответ `{ "session_id", "created_at", "user_id" }`; запись в Postgres.
- [ ] `GET /api/v1/chat/sessions` — список сессий/последних вопросов пользователя (§5.2.1 «последние вопросы»): пагинация, сортировка по дате, фильтр по дате; только свои сессии; элемент `{ session_id, title, created_at, last_message_at }`.
- [ ] `GET /api/v1/chat/sessions/{session_id}` — вернуть сессию с историей сообщений (`messages: [...]`), tool-трейсами и прикреплёнными артефактами (graph/table/evidence/gaps/contradictions); `404` если чужая/нет.
- [ ] `POST /api/v1/chat/sessions/{session_id}/messages` — принять сообщение пользователя `{ "content", "attachments"? }`, сохранить, запустить прогон LangGraph в `agent-service` (`AGENT_SERVICE_URL`, §13.1); режим ответа: синхронный JSON ИЛИ инициирование стрима (см. ниже). Возвращает `{ "message_id", "stream_url" }`.
    - [ ] Поддержать в `attachments` передачу `node_ids`/выделенного подграфа для сценария «ask agent about selected subgraph» (§5.2.3 lasso selection).
- [ ] `GET /api/v1/chat/sessions/{session_id}/stream` — SSE endpoint: проксирует поток событий из `agent-service` наружу. Использовать `sse-starlette`/`EventSourceResponse`.
    - [ ] Реализовать сериализацию строго по контракту `ChatStreamEvent` (§5.3): типы событий `token`, `tool_start`, `tool_end`, `evidence`, `graph`, `table`, `gap`, `error`. Каждое SSE-сообщение = `event: <type>` + `data: <json>`.
    - [ ] Для события `tool_start`/`tool_end` транслировать поля §5.3 (`tool`, `args`/`summary`, `dataRef`) — для tool-call timeline UI (§5.2.2: `resolved entities`, `graph query`, `vector search`, `evidence check`, `gap scan`).
    - [ ] Для события `graph` тело соответствует `GraphResponse` (§5.3: `nodes`, `edges`, `layoutHints`, `queryContext`).
    - [ ] Для события `evidence` — массив `EvidenceRef` (id, doc_id, page, snippet), для `gap` — `GapFinding[]` (§11.1 типы), для `table` — `TablePayload` (§5.3).
    - [ ] Отправлять heartbeat/`: keep-alive` каждые N секунд для предотвращения таймаута прокси; корректно завершать поток событием окончания.
    - [ ] Обрабатывать client disconnect (отмена генерации в `agent-service`) и восстановление по `Last-Event-ID` (resume токенов, если поддерживается агентом).
- [ ] Реализовать WebSocket-вариант `/api/v1/chat/sessions/{session_id}/ws` (двунаправленный): приём пользовательских сообщений и отправка тех же `ChatStreamEvent`; авторизация по токену в query/subprotocol; ping/pong keepalive.
- [ ] Персистить финальный ответ и все стрим-артефакты (graph/table/evidence/gaps/contradictions) в историю сессии по завершении прогона (для табов §5.2.2 [Summary][Experiments][Evidence][Graph][Gaps][Contradictions]).
- [ ] `GET /api/v1/chat/sessions/{session_id}/messages/{message_id}/export` — экспорт ответа-отчёта (§5.2.2 «export report») в JSON/Markdown с summary/experiments/evidence/graph/gaps/contradictions.
- [ ] Гарантировать guardrail-контракт (§7, Phase 5 «no numeric claim without evidence»): если событие ответа содержит числовые claim без `evidence_ids`, помечать/фильтровать — но реализация гварда на стороне агента; шлюз лишь корректно транслирует поле.

**Критерий приёмки:** клиент открывает SSE на `/chat/sessions/{id}/stream`, получает последовательность событий `token`/`tool_start`/`tool_end`/`evidence`/`graph`/`table`/`gap` в формате §5.3; WebSocket-вариант передаёт те же события; `GET /chat/sessions` возвращает последние вопросы пользователя; после завершения `GET /chat/sessions/{id}` возвращает сохранённую историю с артефактами; `messages/{id}/export` отдаёт отчёт; отключение клиента отменяет генерацию.

### 14.5 Entities endpoints (search / detail / neighbors / merge / split / aliases / history)

- [ ] `GET /api/v1/entities/search?q=&type=&limit=` — полнотекстовый поиск по сущностям через Neo4j fulltext index `entity_name_index` (§8.4, метки `Material|Property|Equipment|Lab|Person|ProcessingRegime`); фильтр `type`, `limit`; ответ — список `GraphNode`-совместимых DTO (§5.3: `id`, `label`, `type`, `confidence`, `evidenceCount`, `verified`).
- [ ] `GET /api/v1/entities/{entity_id}` — детальная карточка сущности (§5.2.4): `canonical_name`, `aliases[]`, `type`/schema, свойства узла, `properties and measured values`, linked experiments, linked documents, `timeline`, входящие/исходящие связи, evidence list, агрегаты (кол-во evidence, кол-во связей, `verified`-статус, `confidence`, `review_status`, `missingFields`), merge/split history (из `CurationEvent`, §12.3); `404` если нет.
- [ ] `GET /api/v1/entities/{entity_id}/neighbors?depth=1&types=` — соседи в графе с ограничением глубины (`depth`, дефолт 1, max 3) и фильтром меток связей/узлов (`types`); ответ — `GraphResponse` (§5.3), пригодный для «expand» в Graph Explorer.
- [ ] `POST /api/v1/entities/merge` — слияние сущностей (curator+): body `{ "source_ids": [...], "target_id", "reason" }`; проксирует в `curation-service`; порождает `CurationEvent` (`action: merge`, §12.3); ответ — итоговая сущность и `curation_event_id`.
    - [ ] Валидация: все id существуют и одного типа; иначе `409/422`.
- [ ] `POST /api/v1/entities/{entity_id}/split` — разделение сущности (curator+, §12.2 «split entity», Phase 3 «implement merge/split events»): body `{ "into": [...], "reason" }`; проксирует в `curation-service`; порождает `CurationEvent` (`action: split`, §12.3); ответ — новые сущности и `curation_event_id`.
- [ ] `POST /api/v1/entities/{entity_id}/aliases` — добавить alias (curator+): body `{ "alias", "reason"? }`; обновляет `n.aliases_text` (§8.4) и порождает `CurationEvent` (`action: alias_add`).
- [ ] `GET /api/v1/entities/{entity_id}/history` — история решений/изменений сущности: список `CurationEvent`/`Decision` (§8.2 `(:CurationEvent)-[:CHANGED]->(:Entity)`, `(:Decision)-[:AFFECTS]->(:Entity)`, §2.1 сценарий 5 «Decision history», §5.2.4 merge/split history); ответ — упорядоченный список событий (§12.3).

**Критерий приёмки:** `entities/search?q=Al-Cu&type=Material` возвращает ранжированный список из fulltext-индекса; `entities/{id}` содержит canonical_name/aliases/relations/evidence/merge-split history; `entities/{id}/neighbors?depth=1` возвращает валидный `GraphResponse`; `entities/merge`, `split`, `aliases` доступны только curator/admin, создают `CurationEvent` и возвращают его id; `entities/{id}/history` перечисляет CurationEvent'ы.

### 14.6 Graph endpoints (query / expand / path / subgraph / schema / diff)

- [ ] `POST /api/v1/graph/query` — центральный запрос по графу; принять body строго по примеру §6.2 (`query_type`, `material`, `processing{operation,temperature_c,time_h}`, `property`, `filters{min_confidence,verified_only,date_from}`, `include_evidence`, `include_graph`); проксировать в `graph-service` (Cypher templates, §10 Mode A) / `agent-service`.
    - [ ] Ответ строго по примеру §6.2: `summary`, `experiments[]` (`id,material,processing,property,value,unit,effect,confidence,evidence_ids`), `gaps[]` (`type,entity_id,description`), `graph{nodes,edges}`, `citations[]`.
    - [ ] Поддержать `query_type: "material_regime_property"` (endpoint из Phase 4) и другие типы, определённые в `graph-service`.
- [ ] `POST /api/v1/graph/expand` — расширение подграфа вокруг заданных `node_ids` на N шагов с фильтрами меток/типов связей; ответ — `GraphResponse`.
- [ ] `POST /api/v1/graph/path` — поиск путей между двумя/несколькими узлами (`source_id`, `target_id`, `max_length`, фильтры типов рёбер); ответ — `GraphResponse` + список путей (§5.2.3 «path search → find path between Material and Property»).
- [ ] `POST /api/v1/graph/subgraph` — извлечение подграфа по набору фильтров (материалы/свойства/режимы/даты/сообщества) с лимитами узлов/рёбер; ответ — `GraphResponse` c `layoutHints.communities` (§5.3).
- [ ] `GET /api/v1/graph/schema` — вернуть схему графа (метки §8.1, связи §8.2, свойства, constraints/indexes §8.4) в машинно-читаемом виде для frontend Graph Explorer и валидации.
- [ ] `POST /api/v1/graph/diff` — сравнение версий графа / before-after curation (§5.2.3 «graph diff → compare versions / before-after curation», §5.2.8 «compare graph versions»); body `{ "from_version"|"before_event_id", "to_version"|"after_event_id", "scope"? }`; ответ — узлы/рёбра `added`/`removed`/`changed`.
- [ ] Реализовать защиту от «тяжёлых» запросов: серверные лимиты `max_nodes`, `max_edges`, `timeout_ms` для всех graph-endpoints; превышение → усечение с флагом `truncated:true` или `413/504`.
- [ ] Обеспечить, что все graph-ответы соответствуют типам `GraphNode.type` из §5.3 (`Material|Experiment|ProcessingRegime|Property|Equipment|Paper|Claim|Lab|Person|Gap`) и полям `GraphEdge` (§5.3: `id,source,target,label,type,confidence,evidenceCount,inferred,contradicted,evidenceIds`).
- [ ] Включать в ответы `queryContext` (§5.3: `userQuery`, `filters`, `generatedCypher`) для прозрачности агента (§17 «agent transparency»).

**Критерий приёмки:** `POST /graph/query` с телом-примером §6.2 возвращает ответ ровно с полями примера §6.2; `expand`/`path`/`subgraph` возвращают валидный `GraphResponse` с корректными `GraphEdge` (inferred/contradicted/evidenceIds); `GET /graph/schema` перечисляет метки и связи из §8.1–8.2; `graph/diff` возвращает added/removed/changed; тяжёлый запрос усечён/ограничен без падения сервиса.

### 14.7 Search endpoints (hybrid / vector / keyword)

- [ ] `POST /api/v1/search/hybrid` — гибридный поиск (§10.2, RRF/weighted fusion); body `{ "query", "top_k", "filters"?, "weights"?, "rerank"? }`; проксирует в `search-service`; ответ — ранжированный список chunks/сущностей с `score`, `source`, `evidence_ref`, подсветкой.
- [ ] `POST /api/v1/search/vector` — только семантический поиск через Qdrant (`qdrant-client`, §13.2/§13.1); body `{ "query"|"vector", "top_k", "filters"? }`; ответ с cosine-score и payload.
- [ ] `POST /api/v1/search/keyword` — только лексический поиск через OpenSearch (`opensearch-py`, §13.2/§13.1); body `{ "query", "top_k", "filters"? }`; поддержка BM25, фильтров по метаданным, подсветки.
- [ ] Унифицировать формат hit'а между тремя endpoint'ами (`id`, `text`, `score`, `doc_id`, `page`, `metadata`) для единообразного рендера на frontend.
- [ ] Прокинуть фильтры (`min_confidence`, `verified_only`, `date_from`, `material`, `property`) в нижележащие сервисы; валидировать диапазоны.

**Критерий приёмки:** три search-endpoint'а возвращают унифицированные ранжированные hits; `search/hybrid` объединяет vector+keyword по формуле §10.2; фильтры корректно пробрасываются; невалидный `top_k` → `422`.

### 14.8 Experiments, Evidence, Gaps и Contradictions endpoints

- [ ] `GET /api/v1/experiments` — список экспериментов с пагинацией и фильтрами §5.2.5 (`material`, `processing operation`, `temperature_c`, `time_h`, `atmosphere`, `equipment`, `property`, `regime`, `date_from`, `min_confidence`, `verified_only`); элемент — DTO эксперимента как в §6.2 (`id,material,processing,property,value,unit,effect,confidence,evidence_ids`).
- [ ] `GET /api/v1/experiments/{experiment_id}` — детальная карточка эксперимента (образец, режим, измерения, evidence, документ-источник); `404` если нет.
- [ ] `POST /api/v1/experiments/query` — структурированный запрос по экспериментам (те же фильтры, что `graph/query`, но табличный ответ); ответ — `Paginated[Experiment]` + опционально `graph`.
- [ ] `GET /api/v1/experiments/export?format=csv|json` — экспорт отфильтрованной таблицы экспериментов (§5.2.5 «export CSV/JSON», Phase 6 «export JSON/CSV»); корректные `content-type`/`content-disposition`.
- [ ] `POST /api/v1/experiments/{experiment_id}/verify` — пометить эксперимент `verified`/`needs_review` (curator+, §5.2.5 «mark as verified/needs review»); body `{ "status": "verified|needs_review", "reason"? }`; порождает `CurationEvent` (§12.3).
- [ ] `GET /api/v1/evidence/{evidence_id}` — вернуть evidence-объект строго по модели §8.3 (`id, source_type, doc_id, page, table_id, row_index, col_index, char_start, char_end, text, extractor, model, confidence, created_at, reviewed_by, review_status`); включить ссылку на порождённое ребро/claim (§5.2.6 «graph edge generated from this evidence»).
- [ ] `GET /api/v1/evidence/by-edge/{edge_id}` — вернуть все evidence, обосновывающие данное ребро графа (evidence-first, §8.3); ответ — список evidence-объектов.
- [ ] `POST /api/v1/evidence/{evidence_id}/review` — curator-действие ревью; body `{ "review_status": "accepted|rejected|corrected", "corrected_value"?, "corrected_unit"?, "reason" }` (§8.3 `review_status`, §12.2 human actions accept/reject/correct value/unit); проксирует в `curation-service`, порождает `CurationEvent` (§12.3); обновляет `reviewed_by`, `review_status`.
- [ ] `POST /api/v1/evidence` — создать manual evidence (curator+, §8.3 `source_type: manual`, §12.2 «create manual evidence»); body по §8.3; порождает `CurationEvent` (§12.3) и (при указании) привязывает к claim/edge.
- [ ] `GET /api/v1/gaps` — список найденных gap'ов с фильтром по `type` (значения §11.1: `missing_property_value`, `missing_baseline`, `missing_processing_parameter`, `missing_equipment`, `missing_unit`, `unverified_claim`, `contradictory_measurements`, `low_coverage_material`, `orphan_entity`), пагинацией и статусом (`open/known/irrelevant`).
- [ ] `POST /api/v1/gaps/scan` — запустить сканирование gap'ов (Cypher §11.2) как асинхронный job; body `{ "types"?, "target_properties"?, "scope"? }`; ответ `{ "job_id" }`, статус — через ingest/jobs или отдельный статус.
- [ ] `GET /api/v1/gaps/matrix` — вернуть coverage-матрицу material×property (по Cypher «matrix gaps» §11.2) для Gap Dashboard (§5.2.7); параметры `materials`, `target_properties`; ответ — плотная/разреженная матрица с ячейками `{material_id, property, count, gap:bool}`.
- [ ] `POST /api/v1/gaps/{gap_id}/annotate` — пометить gap как `known/irrelevant/open` (curator+, §12.2 «annotate gap as known/irrelevant»); body `{ "status": "known|irrelevant|open", "reason" }`; порождает `CurationEvent` (§12.3); обновляет статус для фильтра `gaps`.
- [ ] `GET /api/v1/contradictions` — противоречия по `material`/`property` (§8.1 `Contradiction`, §8.2 `(:Claim)-[:CONTRADICTS]->(:Claim)`, §11.1 `contradictory_measurements`) для Gap Dashboard (§5.2.7 «contradictions by material/property») и таба Contradictions (§5.2.2); фильтры `material`, `property`, пагинация; альтернативно surface через `gaps?type=contradictory_measurements`.

**Критерий приёмки:** `experiments` фильтруется (включая operation/temperature/time/atmosphere/equipment) и пагинируется, экспорт CSV/JSON работает; `experiments/{id}/verify` доступен curator+; `evidence/{id}` возвращает объект ровно по полям §8.3 плюс ссылку на ребро; `evidence/{id}/review` и manual `POST /evidence` доступны curator+, обновляют статус и создают `CurationEvent`; `gaps` фильтруется по типам §11.1; `gaps/scan` создаёт job; `gaps/{id}/annotate` меняет статус; `gaps/matrix` и `contradictions` возвращают данные для Gap Dashboard.

### 14.9 Documents endpoints и upload/download

- [ ] `GET /api/v1/documents` — список документов с фильтрами (`source_type`, `owner`/`lab`, статус ingest, `date`) и пагинацией (§5.2.1 режим `Document`, §5.2.8 admin).
- [ ] `POST /api/v1/documents/upload` — приём файла (`multipart/form-data`, `python-multipart`); валидация MIME (pdf/docx/…) и размера (лимит, напр. 200 MB, → `413`); стрим-загрузка в MinIO (`minio_client`, §13.1); регистрация документа в Postgres; запуск ingest-job в `ingestion-service` (§13.1 порт 8020); ответ `{ "doc_id", "job_id", "status": "queued" }`.
- [ ] `GET /api/v1/documents/{doc_id}` — метаданные документа (источник, владелец/lab, lineage, статус ingest, кол-во страниц, дата) из Postgres/graph/каталога (Phase 8 «every document/source has owner and lineage»); `404` если нет.
- [ ] `GET /api/v1/documents/{doc_id}/parsed` — вернуть распарсенный документ (Docling-вывод, §9.2 Step 2): структурированный JSON (разделы, таблицы, подписи) из хранилища; поддержать формат Docling.
- [ ] `GET /api/v1/documents/{doc_id}/chunks` — список chunks документа с метаданными §9.3 (`chunk_id, section_path, page_start, page_end, chunk_type, tokens`) для отображения в UI (Phase 1 «show chunks in UI», «chunk has page/source metadata»); пагинация.
- [ ] `GET /api/v1/documents/{doc_id}/pages/{page}` — вернуть рендер/контент страницы: изображение страницы и/или её текст+bbox для подсветки evidence (§8.3 `page`, `char_start/end`); поддержать `Accept: image/*` и `application/json`.
- [ ] `POST /api/v1/documents/{doc_id}/reindex` — переиндексировать документ (curator+): пересчёт chunking/extraction/embeddings (§9.2 Step 3–8) через `ingestion-service`; ответ `{ "job_id" }`.
- [ ] Реализовать download распарсенных артефактов и исходника через presigned URL MinIO либо стриминг через шлюз (`StreamingResponse`) с корректными `content-type`/`content-disposition`/`content-length`.
- [ ] Поддержать `Range`-запросы для больших файлов/страниц (частичная загрузка → `206`).

**Критерий приёмки:** `documents` возвращает список с фильтрами; upload PDF возвращает `doc_id`+`job_id`, файл появляется в MinIO, документ — в Postgres; `documents/{id}/parsed` возвращает Docling-структуру; `documents/{id}/chunks` отдаёт chunks с page/section-метаданными; `documents/{id}/pages/{page}` отдаёт изображение или текст с bbox; `reindex` создаёт job; download отдаёт файл с корректными заголовками, поддерживает `Range`.

### 14.10 Ingest jobs endpoints и job status

- [ ] `POST /api/v1/ingest/jobs` — создать ingest-job напрямую (без upload, напр. по URL/источнику §9.2 Step 1); body `{ "source_type", "source_ref", "options"? }`; проксирует в `ingestion-service`; ответ `{ "job_id", "status": "queued" }`.
- [ ] `GET /api/v1/ingest/jobs` — список job'ов с фильтром по статусу/типу/дате и пагинацией (§5.2.8 «monitor pipeline status»); включает job'ы из upload/reindex/gaps-scan.
- [ ] `GET /api/v1/ingest/jobs/{job_id}` — статус job'а: `{ "job_id", "status": queued|running|succeeded|failed|cancelled, "progress": 0..1, "steps": [...], "error"?, "result_refs"? }` (шаги pipeline §9.1: register→parse→store→chunk→extract→normalize→resolve→validate→upsert→index→gap→eval).
- [ ] `POST /api/v1/ingest/jobs/{job_id}/cancel` — отмена job'а (admin/curator); проксирует сигнал отмены в `ingestion-service`/Dagster; идемпотентно, повторная отмена завершённого → `409/200` с текущим статусом.
- [ ] Реализовать единый job-store: хранить статусы job'ов в Redis/Postgres, чтобы `gaps/scan`, `documents/upload`, `reindex`, `ingest/jobs` возвращали статус через один механизм.
- [ ] (Опционально) SSE/long-poll `GET /api/v1/ingest/jobs/{job_id}/stream` для live-прогресса ingest в Admin UI (§5.2.8, §5.1 «SSE/WebSocket for streaming chat and job progress»).

**Критерий приёмки:** созданный job проходит через статусы `queued→running→succeeded`; `GET /ingest/jobs` показывает все job'ы для мониторинга pipeline; `GET /ingest/jobs/{id}` показывает прогресс и шаги pipeline §9.1; `cancel` переводит running-job в `cancelled`; статусы job'ов из upload/reindex/gaps-scan доступны через тот же endpoint.

### 14.11 Admin endpoints (health / metrics) и observability

- [ ] `GET /api/v1/admin/health` — агрегированный health: readiness/liveness каждой зависимости (Neo4j, Qdrant, OpenSearch, Postgres, Redis, MinIO, agent-service, ingestion-service, curation-service); ответ `{ "status": "ok|degraded|down", "checks": {...} }`; `503` если критичная зависимость недоступна.
- [ ] `GET /api/v1/admin/metrics` — экспорт метрик в формате Prometheus (RPS, latency p50/p95/p99 по route, кол-во ошибок, размер job-очереди, rate-limit hits); защитить internal-токеном/ролью `admin`.
- [ ] Интегрировать `opentelemetry-sdk` (§13.2, Phase 9 «add OpenTelemetry traces»): трейсы HTTP-запросов и исходящих вызовов к сервисам/БД; проброс `traceparent` в upstream (agent/graph/search/ingestion/curation).
- [ ] Прокинуть/сгенерировать `X-Request-ID` во всех запросах (middleware), логировать и включать в `ErrorResponse` и в audit-логи.
- [ ] Реализовать корректный readiness vs liveness split: `health` не должен падать при деградации некритичных сервисов (degraded), но должен отражать это в `checks`.

**Критерий приёмки:** `GET /admin/health` при остановленном Neo4j возвращает `503`/`degraded` с детализацией по `checks`; `GET /admin/metrics` отдаёт Prometheus-текст под ролью admin; в трейсах OTel виден полный путь запроса через шлюз к upstream с общим trace-id.

### 14.12 Rate limits, audit logs и request validation middleware

- [ ] Реализовать rate limiting middleware на Redis (sliding window / token bucket): лимиты по `user_id` и по IP, настраиваемые через `RATE_LIMIT_*` (напр. отдельные лимиты для дорогих endpoint'ов: `chat/messages`, `graph/query`, `search/hybrid`, `documents/upload`); превышение → `429` с заголовком `Retry-After`.
- [ ] Добавить стандартные заголовки лимитов в ответы: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
- [ ] Реализовать audit-log middleware (Phase 8 «implement audit logs»): для мутирующих запросов (`entities/merge`, `split`, `aliases`, `evidence/review`, `evidence` create, `experiments/{id}/verify`, `gaps/{id}/annotate`, `relations/{id}/mark-inferred`, `schema/terms`, `documents/upload`, `reindex`, `ingest/jobs`, `gaps/scan`, `cancel`) писать запись в Postgres со схемой, согласованной с `CurationEvent` (§12.3): `{actor_id, action, target_type, target_id, before, after, reason, created_at, request_id}`.
- [ ] Обеспечить, что доменные curation-действия порождают `CurationEvent` в `curation-service`, а шлюз дополнительно фиксирует технический audit-log (кто/что/когда/с какого IP).
- [ ] Настроить CORS-middleware с allowlist origin для frontend (`:3000`, §13.1) и корректной обработкой preflight.
- [ ] Настроить security-заголовки (`X-Content-Type-Options`, `X-Frame-Options`/CSP по необходимости) и защиту от чрезмерной глубины/размера JSON.
- [ ] Обеспечить консистентную request-валидацию для всех endpoint'ов через Pydantic-схемы `schemas/` (см. 14.2) — единый источник правды форматов §6.2.

**Критерий приёмки:** превышение лимита на `chat/messages` возвращает `429` с `Retry-After` и заголовками `X-RateLimit-*`; каждое мутирующее действие оставляет запись в audit-log Postgres с `actor_id`/`action`/`target`/`before`/`after`/`request_id`; CORS-preflight с frontend-origin проходит.

### 14.13 Опциональный Neo4j GraphQL proxy

- [ ] Оценить и реализовать опциональный GraphQL proxy к Neo4j (§6.2 «GraphQL proxy if needed», §22 Neo4j GraphQL: https://github.com/neo4j/graphql — КЛОНИРОВАТЬ/изучить schema-first подход; если реализуется Node-sidecar `@neo4j/graphql`, разместить как отдельный сервис (напр. `apps/graphql-proxy/` или `infra/neo4j-graphql/`), шлюз проксирует `POST /api/v1/graphql`).
- [ ] Определить GraphQL type definitions на основе схемы графа (§8.1 метки, §8.2 связи) — переиспользовать `packages/kg_schema` как источник типов.
- [ ] Реализовать проксирование GraphQL-запросов на Neo4j GraphQL-сервис (Node-based `@neo4j/graphql`) ИЛИ встроить через отдельный процесс; шлюз добавляет auth/rate-limit/audit поверх.
- [ ] Применить те же auth/RBAC/rate-limit/audit middleware к `/graphql`, что и к REST (запрет мутаций для `viewer`).
- [ ] Ограничить сложность GraphQL-запросов (query depth/complexity limit) для защиты Neo4j; превышение → ошибка GraphQL с кодом.
- [ ] Задокументировать, что GraphQL proxy — опциональная фича за feature-flag (`ENABLE_GRAPHQL_PROXY`, §3.1 feature flags); при выключенном флаге `/api/v1/graphql` возвращает `404`.

**Критерий приёмки:** при `ENABLE_GRAPHQL_PROXY=true` `POST /api/v1/graphql` исполняет валидный GraphQL-запрос по схеме графа (§8.1–8.2) с наложенными auth/rate-limit; глубокий/сложный запрос отклоняется лимитом сложности; при выключенном флаге endpoint отсутствует.

### 14.14 Curation actions, review queue и decision history (§5.2.8, §12)

- [ ] `GET /api/v1/curation/review-queue` — список review-задач (curator+, §5.2.8 «review queue», §12.1): фильтры по типу/статусу/приоритету, пагинация; проксирует в `curation-service`; причины постановки согласованы с §12.1 (confidence < threshold, ambiguous entity resolution, claim contradicts existing, critical field missing, low-quality OCR, new schema term).
- [ ] `POST /api/v1/curation/review-queue/{task_id}` — accept/reject/correct extracted triple/claim (curator+, §5.2.8 «approve/reject extracted triples», §12.2 accept/reject extraction); body `{ "decision": "accept|reject|correct", "corrected"?, "reason" }`; порождает `CurationEvent` (§12.3).
- [ ] `POST /api/v1/relations/{edge_id}/mark-inferred` — пометить связь как inferred (curator+, §12.2 «mark relation as inferred», §5.3 `GraphEdge.inferred`, §5.2.3 «dashed edge = inferred»); порождает `CurationEvent` (§12.3); влияет на `GraphEdge.inferred`.
- [ ] `POST /api/v1/schema/terms` (+ `PATCH`/`DELETE`) — редактирование schema terms/vocabulary (admin, §5.2.8 «edit schema terms»); порождает `CurationEvent` (`action: schema_change`, §12.3).
- [ ] `GET /api/v1/curation/events` — список `CurationEvent` (§12.3) с фильтрами (`actor_id`, `action`, `target_type`, `target_id`, `date`); decision history (§2.1 сценарий 5), питает Entity Detail merge/split history (§5.2.4) и Admin/Curation (§5.2.8).
- [ ] Обеспечить, что все curation-действия шлюза (merge/split/alias_add/accept/reject/correct/schema_change/mark_inferred/manual_evidence/gap_annotate/experiment_verify) единообразно проксируются в `curation-service`, порождают `CurationEvent` (§12.3) и технический audit-log (14.12), с проверкой RBAC (14.3).

**Критерий приёмки:** `curation/review-queue` возвращает pending-задачи с причинами §12.1; accept/reject/correct триплов, `mark-inferred`, `schema/terms` доступны curator/admin и порождают соответствующий `CurationEvent` (§12.3) с корректным `action`; `curation/events` отдаёт историю решений с фильтрами и питает merge/split history сущности.

### 14.15 Saved views, пользовательские настройки, facets и exports (§5.2.1/§5.2.3)

- [ ] Saved graph views CRUD: `POST /api/v1/views`, `GET /api/v1/views`, `GET /api/v1/views/{view_id}`, `DELETE /api/v1/views/{view_id}` — сохранённые graph views и saved queries (§5.2.1 «сохраненные graph views», §5.2.3 «saved views», Phase 6 «implement saved graph views»); хранение в Postgres `kg_app`, привязка к `user_id`; доступ к чужому view → `403/404`.
- [ ] `GET /api/v1/me/settings` + `PUT /api/v1/me/settings` — пользовательские настройки UI (§3.1 «настройки UI»), привязка к `user_id`, персист в Postgres.
- [ ] `GET /api/v1/facets` — значения быстрых фильтров для §5.2.1/§5.2.5 (`material`, `property`, `processing regime`, `lab`, `date-range`, `confidence-range`); источник — Neo4j fulltext `entity_name_index` (§8.4) / агрегаты graph-service.
- [ ] `GET /api/v1/config` — публичные feature-flags (`ENABLE_GRAPHQL_PROXY` и т.п., §3.1) и версия сборки для frontend (доступно viewer+).
- [ ] `GET /api/v1/graph/subgraph/export?format=json|csv` — экспорт выбранного/построенного подграфа (§5.2.3 «export subgraph», Phase 6 «export JSON/CSV»); PNG рендерится на клиенте (Reagraph), backend отдаёт структурированные данные.

**Критерий приёмки:** saved view создаётся/читается/удаляется и виден только владельцу; `me/settings` персистит настройки в Postgres; `facets` возвращает списки материалов/свойств/лабораторий/режимов для UI-фильтров; `config` отдаёт feature-flags и версию; `graph/subgraph/export` отдаёт JSON/CSV с корректными заголовками.

### 14.16 OpenAPI-контракт, клиентские типы и интеграционные тесты

- [ ] Обеспечить полноту OpenAPI-спеки: все 36 endpoint'ов §6.2 плюс derived-endpoints (14.4/14.5/14.8/14.9/14.10/14.14/14.15) с корректными request/response-моделями, примерами (в т.ч. пример graph query/response §6.2), тегами по группам.
- [ ] Сгенерировать TypeScript-типы для frontend (`apps/frontend`) из OpenAPI (напр. `openapi-typescript`); проверяемо: типы `GraphResponse`/`GraphNode`/`GraphEdge`/`ChatStreamEvent` из §5.3 совпадают с backend-моделями.
- [ ] Написать contract-тесты, проверяющие соответствие ответов примерам §6.2 (`graph/query` response schema), §8.3 (evidence), §5.3 (`GraphResponse`, `ChatStreamEvent`), §12.3 (`CurationEvent`).
- [ ] Написать интеграционные тесты (pytest + httpx TestClient) на каждый endpoint: happy-path + auth (`401/403`) + validation (`422`) + not-found (`404`) + rate-limit (`429`); покрыть derived-endpoints (sessions list, entities/split, entities/history, review-queue, saved views, gaps/annotate, contradictions, documents chunks/list, experiments filters/export/verify, curation/events).
- [ ] Написать тест SSE-стрима чата: убедиться, что последовательность событий соответствует `ChatStreamEvent` (§5.3) и корректно завершается; тест WebSocket-эхо событий.
- [ ] Написать e2e-тест «material X + regime Y + property Z» (Phase 4 acceptance): `POST /graph/query` c телом §6.2 → ответ с `experiments`, `value`, `evidence`, `graph`; проверить, что evidence-ids резолвятся через `GET /evidence/{id}`; graph explorer expand через `entities/{id}/neighbors` (§5.2.3 «graph explorer can expand returned entities»).
- [ ] Настроить CI-прогон тестов и линтинг (Phase 9 «add CI/CD»); порог покрытия роутеров ≥ заданного.

**Критерий приёмки:** `pytest apps/api-gateway/tests` зелёный; OpenAPI содержит все 36 endpoints §6.2 плюс derived-endpoints с примерами; сгенерированные TS-типы совпадают с контрактами §5.3; e2e-тест graph query возвращает данные ровно в формате примера §6.2 и evidence-ids резолвятся.


---


## 15. Gap analysis и contradiction detection

Раздел реализует подсистему обнаружения пробелов в данных (gap analysis, §11) и обнаружения противоречий (contradiction detection). Итог: все 11 типов gap из §11.1 детектируются исполняемыми Cypher-сканами (§11.2), материализуются как first-class узлы графа (`:Gap`, `:Contradiction`, `:GapScanRun` из §8.1–§8.2), доступны через API `/api/v1/gaps*` (§6.2), рассчитываются как Dagster asset после `UPSERT` (§9.1), используются агентом (`gap_analyzer`, tools `scan_gaps` / `detect_contradictions`, §7.4–§7.5) и объясняются пользователю в чате (stream-событие `gap`, §5.3).

Затрагиваемые сервисы/пакеты (по §6.1): `packages/kg_schema/`, `apps/graph-service/`, `apps/agent-service/`, `apps/api-gateway/`, `infra/dagster/`, `packages/kg_common/`, `packages/kg_retrievers/`.

Зависимости от других разделов:
- KG schema (§8) — метки, связи, свойства узлов, constraints/indexes должны существовать до gap-сканов.
- Ingestion & indexing (§9) — gap scan запускается после `UPSERT Neo4j`; зависит от `missing_unit`/`missing_source_span`/`low_confidence_entity_resolution` полей, проставляемых на шагах normalize/ER.
- Graph service / Cypher templates (§6.1 `graph-service`) — общий слой запуска Cypher-шаблонов.
- Agent system (§7) — интеграция `gap_analyzer`, tools, verifier, answer_synthesizer.
- API Gateway (§6.2) — endpoints и DTO-контракты.
- Frontend Gap Dashboard (§5.2.7) — потребитель `/gaps/matrix` и `GapFinding` DTO (реализация дашборда — во frontend-разделе; здесь только контракты).

OSS для клонирования/вендоринга (git-URL из §22):
- Neo4j APOC — `https://github.com/neo4j-contrib/neo4j-apoc-procedures` (batched-скан через `apoc.periodic.iterate`).
- Neo4j Graph Data Science — `https://github.com/neo4j/graph-data-science` (опционально: degree/coverage-метрики, community для orphan-детекции).
- Dagster — `https://github.com/dagster-io/dagster` (asset-оркестрация gap scan).
- pymatgen — `https://github.com/materialsproject/pymatgen` (канонизация имён target-properties/материалов при построении coverage-матрицы).
- Propnet — `https://github.com/materialsintelligence/propnet` (опционально: словарь/связи материаловедческих свойств для определения набора `target_properties` coverage-матрицы).
- MatKG — `https://github.com/olivettigroup/MatKG` (опционально: справочник материаловедческих сущностей для канонизации имён свойств/материалов).

Дополнительно затрагиваемый сервис: `apps/curation-service/` (§6.1) — приёмник review-tasks для критических gap/contradiction (§12.1, tool `create_review_task` из §7.4).

---

### 15.1 Gap domain model и схема (packages/kg_schema)

Файлы: `packages/kg_schema/src/kg_schema/gap.py` (Pydantic), `packages/kg_schema/src/kg_schema/contradiction.py`, `packages/kg_schema/linkml/gap.yaml` (LinkML), `packages/kg_common/src/kg_common/dtos/gaps.py` (shared DTO для API/agent/frontend).

- [x] Определить `Enum GapType` со ВСЕМИ 11 значениями из §11.1 + §7.5: `missing_property_value`, `missing_baseline`, `missing_processing_parameter`, `missing_equipment`, `missing_unit`, `unverified_claim`, `contradictory_measurements`, `low_coverage_material`, `orphan_entity`, `missing_source_span`, `low_confidence_entity_resolution`.
  - [x] Зафиксировать алиасы, встречающиеся в §7.5 (`conflicting_measurements` → `contradictory_measurements`, `unverified_critical_claim` → `unverified_claim`) через маппинг-словарь `GAP_TYPE_ALIASES`, чтобы agent-node и scan использовали одинаковые канонические строки.
- [x] Определить Pydantic-модель `Gap` с полями: `id: str` (формат `gap:<uuid>`), `gap_type: GapType`, `severity: Literal['low','medium','high','critical']`, `status: Literal['open','acknowledged','resolved','dismissed']`, `about_entity_id: str`, `about_entity_type: str`, `subject_material_id: str | None`, `subject_regime_id: str | None`, `subject_property_id: str | None`, `description: str`, `description_ru: str`, `score: float` (0..1 приоритет), `detected_by: str` (`gap_scan_run` id), `detected_at: datetime`, `resolved_at: datetime | None`, `evidence_ids: list[str]`, `metadata: dict[str, Any]`.
- [x] Определить Pydantic-модель `Contradiction` с полями: `id: str` (`contradiction:<uuid>`), `material_id`, `regime_id | None`, `property_id`, `value_a`, `value_b`, `unit`, `relative_diff: float`, `overlap: bool` (пересечение доверительных интервалов), `claim_ids: list[str]`, `measurement_ids: list[str]`, `evidence_ids: list[str]`, `heuristic: str`, `contradiction_subtype: Literal['numeric_divergence','effect_direction','unit_mismatch']` (соответствует эвристикам 15.4), `likely_correct_measurement_id: str | None` (результат эвристики качества источника, 15.4), `severity`, `detected_at`.
- [x] Определить Pydantic-модель `GapScanRun`: `id` (`gapscan:<uuid>`), `started_at`, `finished_at`, `status: Literal['running','success','failed']`, `scan_config_hash: str`, `rules_executed: list[str]`, `gaps_created: int`, `gaps_reopened: int`, `gaps_auto_resolved: int`, `contradictions_created: int`, `dagster_run_id: str | None`, `graph_snapshot_version: str | None`.
- [x] Определить shared DTO `GapFinding` в `packages/kg_common` (совпадает по форме с ответом §6.2: `type`, `entity_id`, `description`) плюс расширенные поля `gap_id`, `severity`, `score`, `subject`, `evidence_ids` — используется в API-ответе `/gaps`, в LangGraph-стейте (`state['gaps']`, §7.3) и в stream-событии `{ type: 'gap'; gaps: GapFinding[] }` (§5.3).
- [x] Определить DTO `CoverageMatrix` и `CoverageCell` (`material_id`, `material`, `property_id`, `property`, `regime_id | None`, `regime | None`, `measured_count: int`, `verified_count: int`, `has_gap: bool`, `gap_ids: list[str]`) для ответа `/gaps/matrix` и heatmap/sankey из §5.2.7.
- [x] Определить DTO `GapByOwner` (`owner_type: Literal['Lab','ResearchTeam']`, `owner_id`, `owner_name`, `gap_type`, `gap_count`, `gap_ids`) для панели «missing metadata by lab/team» (§5.2.7).
- [x] Определить DTO `CoverageTimelinePoint` (`period: str` (год/квартал), `measured_count`, `gap_count`, `coverage_ratio: float`) для визуализации «timeline of experiment coverage» (§5.2.7).
- [x] Зарегистрировать метку `:GapScanRun` в реестре core-labels `kg_schema` (в §8.1 явно перечислены только `:Gap`/`:Contradiction`, тогда как `:GapScanRun` фигурирует в связях §8.2 `(:Gap)-[:DETECTED_BY]->(:GapScanRun)`) — добавить в списки labels/constraints, чтобы схема была замкнута.
- [x] Сгенерировать/сверить LinkML-схему `gap.yaml` с Pydantic-моделями; добавить проверку соответствия в CI (LinkML `--> pydantic` round-trip).
- [x] Добавить JSON Schema экспорт DTO в `packages/kg_common` для валидации frontend-контрактов.

**Критерий приёмки:** `python -c "from kg_schema.gap import GapType; assert len(GapType)==11"` проходит; все 11 канонических типов и оба алиаса присутствуют; Pydantic-модели `Gap`/`Contradiction`/`GapScanRun` сериализуются в JSON и валидируются против LinkML-схемы; `GapFinding`-DTO совпадает по ключам с примером ответа §6.2 (`type`, `entity_id`, `description`); `:GapScanRun` присутствует в реестре меток; DTO `GapByOwner`/`CoverageTimelinePoint` экспортированы в JSON Schema.

---

### 15.2 Gap и Contradiction как first-class узлы графа (apps/graph-service)

Файлы: `apps/graph-service/graph_service/gaps/upsert.py`, `apps/graph-service/graph_service/cypher/gaps/constraints.cypher`, `apps/graph-service/graph_service/gaps/lifecycle.py`.

- [x] Добавить Neo4j constraints/indexes для gap-подсистемы (расширение §8.4):
  - [x] `CREATE CONSTRAINT gap_id IF NOT EXISTS FOR (n:Gap) REQUIRE n.id IS UNIQUE;`
  - [x] `CREATE CONSTRAINT contradiction_id IF NOT EXISTS FOR (n:Contradiction) REQUIRE n.id IS UNIQUE;`
  - [x] `CREATE CONSTRAINT gapscanrun_id IF NOT EXISTS FOR (n:GapScanRun) REQUIRE n.id IS UNIQUE;`
  - [x] `CREATE INDEX gap_type_status IF NOT EXISTS FOR (g:Gap) ON (g.gap_type, g.status);`
  - [x] `CREATE INDEX gap_score IF NOT EXISTS FOR (g:Gap) ON (g.score);`
  - [x] `CREATE INDEX gap_dedup_key IF NOT EXISTS FOR (g:Gap) ON (g.dedup_key);`
- [x] Реализовать детерминированный `dedup_key` для gap: хэш от (`gap_type` + отсортированный набор subject-id: material/regime/property/entity), чтобы повторный скан НЕ создавал дубликаты, а обновлял существующий узел.
- [x] Реализовать `upsert_gap` (Cypher `MERGE (g:Gap {dedup_key:$k})` + `SET` полей) и связи из §8.2:
  - [x] `(:Gap)-[:ABOUT]->(:Entity)` для целевой сущности.
  - [x] `(:Gap)-[:DETECTED_BY]->(:GapScanRun)`.
  - [x] дополнительные типизированные связи `(:Gap)-[:ABOUT_MATERIAL]->(:Material)`, `(:Gap)-[:ABOUT_PROPERTY]->(:Property)`, `(:Gap)-[:ABOUT_REGIME]->(:ProcessingRegime)` (по аналогии с `:Claim`, §8.2) для навигации в Graph Explorer.
  - [x] `(:Gap)-[:SUPPORTED_BY]->(:Evidence)` для evidence-подкреплённых gap (например `missing_baseline` ссылается на measurement-evidence).
- [x] Реализовать `upsert_contradiction`: `MERGE (c:Contradiction {id})`, связи `(:Contradiction)-[:ABOUT_MATERIAL]->(:Material)`, `(:Contradiction)-[:ABOUT_PROPERTY]->(:Property)`, `(:Claim)-[:CONTRADICTS]->(:Claim)` (§8.2), `(:Contradiction)-[:INVOLVES]->(:Measurement)`.
- [x] Реализовать lifecycle-переходы gap:
  - [x] при новом скане: если `dedup_key` найден и `status='resolved'`, но условие снова истинно → `reopen` (status→`open`, инкремент `gaps_reopened`).
  - [x] auto-resolve: если gap с `status='open'` больше не воспроизводится текущим сканом (его `dedup_key` отсутствует в результатах) → `SET g.status='resolved', g.resolved_at=$now` и `gaps_auto_resolved++` (при этом узел НЕ удаляется — сохраняется история).
  - [x] уважать ручные статусы: `acknowledged`/`dismissed`, проставленные курацией (§12), НЕ перезаписывать авто-логикой.
  - [x] при ручной смене статуса (annotate gap as known/irrelevant, §12.2) создавать `(:CurationEvent)-[:CHANGED]->(:Gap)` с before/after (§12.3), чтобы история решений по gap версионировалась (§8.2, §17 «versioned decisions»).
- [x] Реализовать вычисление проекций `missingFields` для узлов сущностей (поле `GraphNode.missingFields`, §5.3): агрегировать открытые gap по сущности и писать список недостающих полей в `properties`/материализованное свойство для быстрого рендера графа.

**Критерий приёмки:** повторный запуск gap scan на неизменённом графе НЕ увеличивает число `:Gap` узлов (идемпотентность по `dedup_key`); закрытие условия приводит к `status='resolved'`, а не к удалению; Cypher `MATCH (g:Gap)-[:DETECTED_BY]->(:GapScanRun) RETURN count(g)` возвращает согласованные значения; из любого `:Gap` достижимы `:Material`/`:Property`/`:ProcessingRegime` через типизированные связи (граф навигируем).

---

### 15.3 Реализация всех 11 gap-правил и Cypher-сканов (§11.2)

Файлы: `apps/graph-service/graph_service/cypher/gaps/<rule>.cypher` (по одному на правило), реестр `apps/graph-service/graph_service/gaps/rules.py`, конфиг `infra/dagster/config/gap_rules.yaml`.

- [ ] Ввести реестр правил `GAP_RULES: dict[GapType, GapRule]`, где `GapRule` = {`cypher_path`, `params_builder`, `severity_fn`, `score_fn`, `description_builder(ru/en)`, `enabled`}.
- [ ] Каноникализировать traversal-паттерны относительно §8.2 и устранить расхождение направлений между §11.2 и §8.2:
  - [ ] зафиксировать, что `(:Sample)-[:HAS_MATERIAL]->(:Material)` (направление §8.2), а измерения идут через `(:Experiment)-[:MEASURED]->(:Measurement)-[:OF_PROPERTY]->(:Property)` и `(:Measurement)-[:HAS_UNIT]->(:Unit)`.
  - [ ] переписать примеры §11.2 под канонический паттерн; добавить unit-тест «schema-conformance» (все gap-Cypher парсятся и матчатся на fixture-графе).
- [ ] `missing_property_value` — Material/regime существует, но целевое свойство не измерено. Основа — matrix-gap из §11.2:
  ```cypher
  MATCH (m:Material)
  MATCH (p:Property) WHERE p.canonical_name IN $target_properties
  OPTIONAL MATCH (m)<-[:HAS_MATERIAL]-(:Sample)<-[:USES_SAMPLE]-(:Experiment)
                 -[:MEASURED]->(meas:Measurement)-[:OF_PROPERTY]->(p)
  WITH m, p, count(meas) AS n WHERE n = 0
  RETURN m.id AS material_id, p.id AS property_id;
  ```
  - [ ] расширить вариантом с привязкой к режиму (`ProcessingRegime`) для gap на уровне material-regime-property.
- [ ] `missing_baseline` — эффект заявлен, но нет baseline. Реализовать Cypher из §11.2 (адаптировать под §8.2: `Experiment-[:MEASURED]->(meas)`), условие `meas.effect_direction IS NOT NULL AND meas.baseline_value IS NULL`.
- [ ] `missing_processing_parameter` — режим есть, но нет ключевого параметра (temperature/time/atmosphere):
  ```cypher
  MATCH (r:ProcessingRegime)-[:HAS_STEP]->(st:ProcessingStep)
  WHERE NOT EXISTS { (st)-[:HAS_PARAMETER]->(:Parameter {kind:'temperature'}) }
     OR NOT EXISTS { (st)-[:HAS_PARAMETER]->(:Parameter {kind:'time'}) }
  RETURN r.id, st.id, ...;
  ```
  - [ ] параметризовать список обязательных `Parameter.kind` через `$required_parameters`; учитывать `r.temperature_c`/`r.time_h` (индексы §8.4) как fallback.
  - [ ] добавить подтип `missing_regime` (сценарий §2.1.4 «есть property value, но нет режима обработки»): measurement свойства существует, но у соответствующего `Sample`/`Experiment` НЕТ связанного `(:ProcessingRegime)` — обратный к `missing_property_value` gap; помечать флагом `subtype:'missing_regime'` в `metadata`, чтобы не плодить 12-й канонический тип.
- [ ] `missing_equipment` — эксперимент/шаг без оборудования: `MATCH (e:Experiment) WHERE NOT EXISTS { (e)-[:USES_SAMPLE]->(:Sample)-[:PROCESSED_BY]->(:ProcessingRegime)-[:HAS_STEP]->(:ProcessingStep)-[:USED_EQUIPMENT]->(:Equipment) }`.
- [ ] `missing_unit` — численное значение без единицы: `MATCH (meas:Measurement) WHERE meas.value_normalized IS NOT NULL AND NOT EXISTS { (meas)-[:HAS_UNIT]->(:Unit) } RETURN meas.id;` (согласовать с шагом normalize §9, где проставляется `HAS_UNIT`).
- [ ] `missing_source_span` — evidence/measurement/claim без span: `MATCH (ev:Evidence) WHERE ev.char_start IS NULL OR ev.char_end IS NULL OR ev.doc_id IS NULL RETURN ev.id;` (см. поля Evidence §8.3); плюс вариант для `Measurement`/`Claim`, у которых нет `SUPPORTED_BY`/`FROM_CHUNK` evidence со span.
- [ ] `unverified_claim` (`unverified_critical_claim`) — claim не отревьюен и нет прямого измерения:
  ```cypher
  MATCH (cl:Claim)-[:SUPPORTED_BY]->(ev:Evidence)
  WHERE coalesce(ev.review_status,'pending') <> 'accepted'
    AND NOT EXISTS {
      (cl)-[:ABOUT_MATERIAL]->(m:Material)<-[:HAS_MATERIAL]-(:Sample)<-[:USES_SAMPLE]-(:Experiment)
          -[:MEASURED]->(:Measurement)-[:OF_PROPERTY]->(:Property)<-[:ABOUT_PROPERTY]-(cl)
    }
  RETURN cl.id;
  ```
  - [ ] выделять «critical» подтип по флагу `cl.is_critical` / по типу свойства из `$critical_properties`.
- [ ] `contradictory_measurements` (`conflicting_measurements`) — делегируется в 15.4 (эвристика), но gap-узел этого типа создаётся здесь по факту наличия `:Contradiction` для (material, [regime], property).
- [ ] `low_coverage_material` — материал часто упоминается, но мало измеренных свойств:
  ```cypher
  MATCH (m:Material)
  OPTIONAL MATCH (m)<-[:MENTIONS]-(:Chunk) WITH m, count(*) AS mentions
  OPTIONAL MATCH (m)<-[:HAS_MATERIAL]-(:Sample)<-[:USES_SAMPLE]-(:Experiment)
                 -[:MEASURED]->(meas:Measurement)-[:OF_PROPERTY]->(p:Property)
  WITH m, mentions, count(DISTINCT p) AS props
  WHERE mentions >= $mention_threshold AND props <= $coverage_min_props
  RETURN m.id, mentions, props;
  ```
- [ ] `orphan_entity` — сущность без evidence и без графового контекста: `MATCH (n) WHERE any(l IN labels(n) WHERE l IN $entity_labels) AND NOT (n)--() RETURN n;` плюс вариант «нет ни одной `Evidence`/`MENTIONS`/`SUPPORTED_BY`».
  - [ ] опционально: усилить `orphan_entity`/`low_coverage_material` метриками Neo4j GDS (§22) — degree-centrality (изолированность узла) и community-detection (узел вне значимой компоненты), проектируя in-memory граф через GDS.
- [ ] `low_confidence_entity_resolution` — резолвинг неоднозначен/низкой уверенности: `MATCH (n) WHERE n.resolution_confidence < $er_threshold OR n.er_candidate_count > 1 RETURN n;` (поля проставляются на шаге ER §9/Splink; согласовать имена с entity-resolution разделом).
- [ ] Для каждого правила реализовать `params_builder` (тянет `$target_properties`, `$required_parameters`, пороги из конфига), `severity_fn` и `score_fn` (нормировка в 0..1, влияет на ранжирование 15.9).
- [ ] Обернуть тяжёлые сканы в `apoc.periodic.iterate` (APOC, §22) для батч-обработки больших графов без таймаутов.
- [ ] Реализовать оркестратор `run_all_gap_rules(scan_run_id, config)` — последовательный/параллельный запуск включённых правил, сбор результатов, вызов `upsert_gap` (15.2).

**Критерий приёмки:** на подготовленном fixture-графе (15.10) каждый из 11 типов детектируется хотя бы одним позитивным кейсом и НЕ срабатывает на негативном (полном) кейсе; все `<rule>.cypher` синтаксически валидны (`EXPLAIN`) и соответствуют меткам/связям §8.2; список сработавших правил равен списку включённых в `gap_rules.yaml`.

---

### 15.4 Эвристики обнаружения противоречий (contradiction detection)

Файлы: `apps/graph-service/graph_service/gaps/contradictions.py`, `apps/graph-service/graph_service/cypher/gaps/contradictory_measurements.cypher`.

- [ ] Реализовать группировку измерений по ключу (material_id, regime_id?, property_id, unit_normalized) с приведением к общей нормализованной единице (использовать units-normalization из §9; при несовместимых единицах — отдельный подтип конфликта `unit_mismatch`).
- [ ] Реализовать эвристику числового расхождения: конфликт, если `relative_diff = |a-b| / max(|a|,|b|) > $rel_tol` (по умолчанию 0.2) И доверительные интервалы (`value ± std`/`value_min..value_max`) НЕ пересекаются.
- [ ] Реализовать эвристику направления эффекта: конфликт, если для одного (material, regime, property) `effect_direction` расходится (`increase` vs `decrease`).
- [ ] Реализовать эвристику качества источника: при конфликте измерений сравнивать `confidence`/`review_status`/OCR-качество и помечать «likely-correct» кандидата (не удалять, только ранжировать).
- [ ] Учитывать легитимную вариативность: НЕ считать конфликтом, если различаются условия (разные `ProcessingRegime`, разные `Method`) — сравнивать только при совпадении регламентированного набора условий из `$contradiction_group_keys`.
- [ ] Материализовать результат: создать `:Contradiction` узел (15.2), проставить `contradiction_subtype` (`numeric_divergence`/`effect_direction`/`unit_mismatch`, 15.1) и `likely_correct_measurement_id`; связать `(:Claim)-[:CONTRADICTS]->(:Claim)` (§8.2) и `INVOLVES` измерения; породить сопутствующий `:Gap {gap_type:'contradictory_measurements'}`.
- [ ] Проставлять `severity` противоречия по величине `relative_diff` и критичности свойства.
- [ ] Собирать `evidence_ids` обеих сторон конфликта для отображения в Evidence Inspector (§5.2.6) и для verifier (§7.5, «contradictions явно отмечены»).
- [ ] При обнаружении противоречия создавать review-task в `curation-service` (§12.1 триггер «claim contradicts existing claim») через tool `create_review_task` (§7.4) — противоречие попадает в review queue курации.

**Критерий приёмки:** на fixture с двумя измерениями одной (material, regime, property) с расхождением > `rel_tol` создаётся ровно один `:Contradiction` и связь `CONTRADICTS`; измерения при разных `ProcessingRegime` НЕ порождают конфликт; при пересекающихся доверительных интервалах конфликт не создаётся; `evidence_ids` содержат ссылки на обе стороны.

---

### 15.5 Coverage matrix (material-property и material-regime-property)

Файлы: `apps/graph-service/graph_service/gaps/coverage.py`, `apps/graph-service/graph_service/cypher/gaps/coverage_matrix.cypher`, `packages/kg_retrievers` (переиспользование граф-обёрток).

- [ ] Реализовать `build_material_property_matrix(target_properties, filters)` → плотная матрица material × property со счётчиками `measured_count`/`verified_count` (на базе matrix-Cypher §11.2, расширенного `count(meas)` и `count(CASE WHEN ev.review_status='accepted')`).
- [ ] Реализовать `build_material_regime_property_matrix(...)` → трёхмерное покрытие material × regime × property (для sankey material → regime → property из §5.2.7).
- [ ] Канонизировать имена свойств и материалов через pymatgen/property-словарь (§22) перед агрегированием, чтобы синонимы не расщепляли ячейки.
- [ ] Помечать ячейки с `measured_count=0` как `has_gap=true` и связывать с соответствующими `:Gap {gap_type:'missing_property_value'}` (`gap_ids`).
- [ ] Реализовать серверную агрегацию для heatmap (плотность покрытия по материалу/свойству) и для «ranked gap list» (§5.2.7) — сортировка материалов по доле незакрытых целевых свойств.
- [ ] Реализовать `aggregate_gaps_by_owner()` → `list[GapByOwner]` (15.1): группировка открытых gap по `Lab`/`ResearchTeam` через `(:Experiment)-[:PERFORMED_BY]->(:ResearchTeam)-[:PART_OF]->(:Lab)` (§8.2) для панели «missing metadata by lab/team» (§5.2.7); включать сущности вовсе без привязки к lab/team как отдельный gap-класс метаданных.
- [ ] Реализовать `build_coverage_timeline()` → `list[CoverageTimelinePoint]` (15.1): временной ряд покрытия/пробелов по периодам (год/квартал публикации/эксперимента) для «timeline of experiment coverage» (§5.2.7).
- [ ] Поддержать фильтры из §6.2 (`min_confidence`, `verified_only`, `date_from`) при построении матрицы.
- [ ] Кэшировать результат матрицы (materialized snapshot per `GapScanRun`) для быстрого ответа `/gaps/matrix`.

**Критерий приёмки:** `build_material_property_matrix` для набора `$target_properties` возвращает `CoverageMatrix`, где каждая ячейка с `measured_count=0` имеет `has_gap=true` и непустой `gap_ids`; суммарное число gap-ячеек совпадает с числом `:Gap {gap_type:'missing_property_value'}` за тот же scan; матрица корректно строится и в 2D (material×property), и в 3D (material×regime×property); `aggregate_gaps_by_owner` возвращает непустой список для fixture с lab/team, а `build_coverage_timeline` — монотонный по периодам ряд.

---

### 15.6 Gap scan как Dagster asset (infra/dagster)

Файлы: `infra/dagster/assets/gap_scan.py`, `infra/dagster/assets/coverage_matrix.py`, `infra/dagster/jobs/gap_jobs.py`, `infra/dagster/config/gap_rules.yaml`.

- [ ] Определить Dagster asset `gap_scan` (зависит от asset `neo4j_upsert` — узел `GAP` в pipeline §9.1), который: открывает `GapScanRun`, запускает `run_all_gap_rules` (15.3), запускает contradiction detection (15.4), фиксирует счётчики и закрывает run.
- [ ] Определить downstream asset `coverage_matrix`, зависящий от `gap_scan`, материализующий snapshot матрицы (15.5).
- [ ] Прокинуть конфиг `gap_rules.yaml` (`target_properties`, `critical_properties`, `required_parameters`, пороги `rel_tol`/`mention_threshold`/`coverage_min_props`/`er_threshold`) как Dagster config schema; хэш конфига писать в `GapScanRun.scan_config_hash`.
- [ ] Эмитить Dagster asset metadata (число gaps по типам, число contradictions, длительность) для наблюдаемости и связки с §8 (governance/lineage).
- [ ] Настроить триггеры: (а) авто-запуск после успешного `neo4j_upsert` нового документа (§9.1 `UPSERT --> GAP`); (б) ручной запуск через `/gaps/scan` (15.7); (в) расписание (Dagster schedule) для периодического полного скана.
- [ ] Реализовать incremental-режим: скан только по сущностям, затронутым последним ingest (список изменённых entity_id из upsert-asset), + периодический full-scan; параметр `scope: incremental|full`.
- [ ] Пробросить `dagster_run_id` в `GapScanRun` и обратно в API `job_id` (для `/gaps/scan` → `/ingest/jobs/{job_id}` статуса).
- [ ] Обеспечить идемпотентность повторного материализования asset (опирается на `dedup_key`, 15.2).

**Критерий приёмки:** `dagster asset materialize --select gap_scan` создаёт один `:GapScanRun` со статусом `success` и корректными счётчиками; asset `coverage_matrix` строится downstream; повторная материализация не плодит дубли gap; авто-триггер после `neo4j_upsert` виден в Dagster run history; метаданные asset содержат разбивку gaps по типам.

---

### 15.7 Gap API endpoints (apps/api-gateway)

Файлы: `apps/api-gateway/api_gateway/routers/gaps.py`, `apps/api-gateway/api_gateway/schemas/gaps.py`, `apps/graph-service/graph_service/queries/gaps_read.py`.

- [ ] Реализовать `GET /api/v1/gaps` (§6.2) с query-параметрами: `type` (GapType), `status`, `material_id`, `property_id`, `regime_id`, `severity_min`, `min_score`, `limit`, `offset`, `sort`. Ответ — `list[GapFinding]` + пагинация; формат `type`/`entity_id`/`description` совместим с примером §6.2.
- [ ] Реализовать `POST /api/v1/gaps/scan` (§6.2): триггерит Dagster `gap_scan` job (15.6), принимает body `{scope, gap_types?, target_properties?}`, возвращает `{job_id, gap_scan_run_id}`; статус доступен через `/ingest/jobs/{job_id}` (§6.2).
- [ ] Реализовать `GET /api/v1/gaps/matrix` (§6.2): параметры `target_properties`, `dimensions=2|3`, фильтры (`min_confidence`, `verified_only`, `date_from`); возвращает `CoverageMatrix` (15.5) — источник для heatmap/sankey §5.2.7.
- [ ] Реализовать `GET /api/v1/gaps/{gap_id}` — детальная карточка gap с evidence-ссылками и связанными сущностями (для клика из dashboard/graph).
- [ ] Реализовать `GET /api/v1/gaps/contradictions` — список `:Contradiction` (для «contradictions by material/property» §5.2.7).
- [ ] Расширить `/gaps/matrix` (или добавить `GET /api/v1/gaps/by-owner` и `GET /api/v1/gaps/coverage-timeline`) для панелей «missing metadata by lab/team» и «timeline of experiment coverage» (§5.2.7): отдавать `list[GapByOwner]` и `list[CoverageTimelinePoint]` (15.1/15.5).
- [ ] Реализовать read-only Cypher-запросы в `graph-service` для перечисленных endpoint (без записи), с использованием индексов `gap_type_status`/`gap_score` (15.2).
- [ ] Провалидировать все request/response Pydantic-схемами; добавить в OpenAPI-спеку gateway.
- [ ] Добавить rate-limit и audit-log для `POST /gaps/scan` (§6.2 «rate limits», «audit logs»).
- [ ] Интегрировать с curation (§12): `GET /gaps` должен уметь отдавать gaps как источник review-tasks; статусы `acknowledged/dismissed`, выставленные курацией, отражаются в ответе; для gap типа «critical field missing» (§12.1) уметь заводить review-task через `curation-service` (tool `create_review_task`, §7.4).

**Критерий приёмки:** `GET /api/v1/gaps?type=missing_baseline` возвращает валидные `GapFinding` с полями из §6.2; `POST /api/v1/gaps/scan` возвращает `job_id`, статус которого достижим через `/ingest/jobs/{job_id}`; `GET /api/v1/gaps/matrix` возвращает `CoverageMatrix`, пригодную для рендера heatmap; endpoint'ы by-owner и coverage-timeline отдают DTO `GapByOwner`/`CoverageTimelinePoint`; OpenAPI-спека gateway содержит все `/gaps*` endpoint; contract-тест сверяет ответ с DTO из 15.1.

---

### 15.8 Интеграция с агентом: tools, gap_analyzer node, verifier

Файлы: `apps/agent-service/agent_service/tools/gaps.py`, `apps/agent-service/agent_service/nodes/gap_analyzer.py`, `apps/agent-service/agent_service/nodes/verifier.py`.

- [ ] Реализовать agent tool `scan_gaps` (§7.4): по контексту запроса (материал/свойство/режим из `state['entities']`, `query_plan`) вызывает read-only gap-запросы `graph-service` (или узкий on-the-fly скан) и возвращает `list[GapFinding]`; результат кладётся в `state['gaps']` (§7.3).
- [ ] Реализовать agent tool `detect_contradictions` (§7.4): для набора измерений/утверждений в контексте запускает эвристики 15.4, возвращает `list[Contradiction]` в `state['contradictions']`.
- [ ] Реализовать node `gap_analyzer` (§7.5) поверх этих tools: применяет все rules из §7.5 (`missing_property_value`, `missing_unit`, `missing_processing_parameter`, `missing_baseline`, `missing_equipment`, `missing_source_span`, `low_confidence_entity_resolution`, `conflicting_measurements`, `unverified_critical_claim`) к уже извлечённым `retrieved_experiments`/`retrieved_graph`/`evidence`; заполняет `state['gaps']` и `state['contradictions']`.
  - [ ] обеспечить, что node различает «gap в подмножестве, релевантном вопросу» (runtime) и переиспользует материализованные `:Gap` из графа, если они уже есть (не дублировать вычисления).
- [ ] Расширить node `verifier` (§7.5) проверками: «contradictions явно отмечены», «для low-confidence добавлен warning», «каждое численное значение имеет evidence» — блокировать финализацию ответа, если найден unsupported claim с сопутствующим gap `missing_source_span`.
- [ ] Прокинуть gaps/contradictions в `answer_synthesizer` (§7.5) в секцию «пробелы» и в `visualization_payload` (gap-узлы в графе ответа).
  - [ ] в `visualization_payload` проставлять визуальные кодировки §5.2.3: рёбра между конфликтующими claim/measurement получают `GraphEdge.contradicted=true` (red edge), сущности с открытыми gap — `GraphNode.missingFields` (hollow node), gap-узлы — `GraphNode.type='Gap'`; согласовать с полями `GraphEdge`/`GraphNode` из §5.3.
- [ ] Для «critical field missing» / контрадикций из runtime-скана вызывать tool `create_review_task` (§7.4) — критические пробелы попадают в review queue (§12.1), consistently с 15.4/15.7.
- [ ] Реализовать генерацию stream-события `{ type: 'gap'; gaps: GapFinding[] }` (§5.3) при завершении `gap_analyzer`, чтобы UI показывал пробелы инкрементально.
- [ ] Зарегистрировать `scan_gaps`/`detect_contradictions` в `TOOLS` (§7.4) и в LangGraph-графе между `evidence_assembler` и `verifier` (§7.2 порядок нод).

**Критерий приёмки:** для тестового вопроса «где пробелы по hardness у Al-Cu?» агент вызывает `scan_gaps`, наполняет `state['gaps']`, и в стриме появляется событие `type:'gap'`; verifier помечает ответ warning-ом при low-confidence и не пропускает unsupported claim; gap-узлы присутствуют в `visualization_payload`.

---

### 15.9 Объяснение пробелов в чате, ранжирование и приоритизация

Файлы: `apps/agent-service/agent_service/nodes/answer_synthesizer.py`, `apps/graph-service/graph_service/gaps/scoring.py`, `apps/agent-service/agent_service/prompts/gap_explanation.jinja`.

- [ ] Реализовать функцию `gap_priority_score(gap)` (severity × частота упоминаний субъекта × критичность свойства × наличие/отсутствие evidence) → поле `Gap.score`; использовать для сортировки в `/gaps` и «ranked gap list» §5.2.7.
- [ ] Реализовать генерацию человекочитаемых объяснений gap на RU и EN (`description_ru`/`description` в 15.1), с указанием: какого материала/свойства/режима не хватает, почему это пробел, и какой эксперимент его закроет (пример из §6.2: «Есть hardness после aging, но нет исходного значения до обработки»).
- [ ] В `answer_synthesizer` собрать секцию «пробелы» (§7.5) в чат-ответе: top-N gap по `score` с ссылками на evidence и предложением следующего измерения.
- [ ] Обеспечить, что объяснение gap ссылается на evidence-span (для `missing_source_span` — прямо указывает отсутствие span), чтобы соблюсти evidence-first принцип (§8.3, §23).
- [ ] Поддержать запрос вида «где пробелы по X?» (Phase 7 acceptance): intent-роутинг на gap-ответ, вызов `scan_gaps`, рендер ranked-списка + graph payload с `:Gap` узлами (`type:'Gap'`, §5.3 `GraphNode.type`).
- [ ] Сгенерировать для каждого gap рекомендацию «next experiment to close the gap» (для §23 — «пробелы можно закрывать новыми экспериментами»).
- [ ] Сформировать данные для warning-панели чата (§5.2.2 «warning panel: contradictions, low-confidence results, missing data»): агрегировать contradictions, low-confidence-результаты и missing-data (gaps) в структуру ответа, чтобы UI показал предупреждения рядом с ответом.

**Критерий приёмки:** на вопрос «где пробелы по X?» чат возвращает отсортированный по `score` список пробелов с RU-объяснениями и цитатами; каждый gap в ответе имеет `score` и предложение по закрытию; graph payload содержит узлы `type:'Gap'`, кликабельные в Graph Explorer; warning-панель наполняется contradictions/low-confidence/missing-data.

---

### 15.10 Тестирование, фикстуры и eval gap-подсистемы

Файлы: `apps/graph-service/tests/gaps/`, `packages/kg_eval/src/kg_eval/gap_eval.py`, `infra/dagster/tests/test_gap_scan.py`, `tests/fixtures/gap_graph.cypher`.

- [ ] Создать Cypher-fixture `gap_graph.cypher`: для КАЖДОГО из 11 типов — минимум один позитивный (gap присутствует) и один негативный (данные полны) подграф, соответствующий меткам/связям §8.2.
- [ ] Написать unit-тесты на каждое gap-правило (11 тестов): позитив детектируется, негатив — нет; проверка `dedup_key` идемпотентности.
- [ ] Написать тесты contradiction-эвристик (15.4): числовое расхождение, direction-конфликт, unit-mismatch, легитимная вариативность (разные режимы — не конфликт).
- [ ] Написать тест coverage-матрицы: сверка числа gap-ячеек с числом `:Gap {missing_property_value}`.
- [ ] Написать integration-тест Dagster `gap_scan` (материализация → `GapScanRun` success, счётчики, downstream `coverage_matrix`).
- [ ] Написать contract-тест API `/gaps`, `/gaps/scan`, `/gaps/matrix` против DTO (15.1) и примера ответа §6.2.
- [ ] Добавить в `kg_eval` (§15.2 метрики) метрику `gap_detection_precision`/gap-recall И отдельно `contradiction_detection_recall` (обе явно перечислены в §15.2 «Answer quality») на размеченном golden-подграфе и включить в automated eval loop (§15.3).
- [ ] Добавить в golden-dataset (§15.1) 10 gap-вопросов и 10 contradiction-вопросов с `expected_answer_contains`/`required_graph_nodes` (в т.ч. узлы `Gap`/`Contradiction`), чтобы eval-loop покрывал чат-сценарии пробелов и противоречий.
- [ ] Добавить регресс-тест lifecycle: gap открывается → условие устраняется → auto-resolve; ручной `dismissed` не перезаписывается сканом; при ручной смене статуса создаётся `:CurationEvent` (15.2).
- [ ] Написать тест idempotency Dagster-материализации (повторный `gap_scan` не плодит `:Gap`, 15.6) и incremental-скана (только затронутые сущности).
- [ ] Написать тесты agent-интеграции: `scan_gaps`/`detect_contradictions` наполняют `state['gaps']`/`state['contradictions']`, verifier блокирует unsupported claim, в стриме появляется событие `type:'gap'` (15.8).

**Критерий приёмки:** `pytest apps/graph-service/tests/gaps` и `infra/dagster/tests/test_gap_scan.py` зелёные; для всех 11 типов позитив/негатив-кейсы проходят; `gap_detection_precision`, gap-recall и `contradiction_detection_recall` на golden-подграфе рассчитываются в `kg_eval` и попадают в отчёт eval-loop; golden-dataset содержит ≥10 gap- и ≥10 contradiction-вопросов; contract-тесты API совпадают с §6.2.

---


---


## 16. Curation workflow и decision history

Раздел реализует полный человеко-машинный контур курирования (§12): автоматическую генерацию review-задач, набор human actions над извлечениями и графом, неизменяемую модель `CurationEvent`/`Decision` с версионированием, защиту проверенных полей от перезаписи при повторном ingest, backend для Curation UI (§5.2.8, endpoints §6.2) и сравнение версий графа (graph diff). Основной сервис — `apps/curation-service/`; модели — в `packages/kg_schema/`; общие DTO — в `packages/kg_common/`. Граф-операции идут через `apps/graph-service/`.

Зависимости от других разделов:
- KG schema (§8): labels `Decision`, `CurationEvent`, `Evidence`, `Gap`, `Contradiction`, relationships `(:Decision)-[:AFFECTS]->(:Entity)`, `(:CurationEvent)-[:CHANGED]->(:Entity)`, constraints/indexes.
- Ingestion pipeline (§9, Step 7 graph upsert): интеграция «never overwrite reviewed fields»; Step 8 indexing — обновление `review_status`/`verified` в Qdrant/OpenSearch payload при курировании.
- Entity resolution (§9 Step 6, Splink): источник кандидатов для merge/split и ambiguous-ER задач (`candidate_id/mentions/match_probability/decision`).
- Gap analysis / Contradiction detection (§11, Phase 7): источники review-задач `contradiction` и action `annotate gap`; резолюция узлов `Contradiction` как исход курирования.
- API Gateway (§6.2): проксирование curation endpoints, auth/RBAC, audit logs, `verified_only`-фильтр графовых запросов.
- Frontend Admin / Curation (§5.2.8): этот раздел даёт backend-контракты.
- Frontend Graph Explorer (§5.2.3, §5.3): backend поставляет флаги для визуальных кодировок — `verified` (lock icon), `inferred` (dashed edge), contradiction (red edge), missing critical field (hollow node).
- Frontend Entity Detail / Experiment Explorer (§5.2.4, §5.2.5): timeline/merge-split history, action «mark as verified / needs review».
- Frontend Evidence Inspector (§5.2.6): reviewer decision, «who confirmed/corrected», «graph edge generated from this evidence».
- Agent (§7.4 tool `create_review_task`, §7.5 verifier flag `unverified_critical_claim`): агент программно ставит review-задачи.
- Retrieval (§10.2 «boost verified evidence», §6.2 `verified_only`): опирается на актуальный `verified`/`review_status`, который поддерживает курирование.

OSS для клонирования/вендоринга (§21, §22) — с путями в монорепо:
- Splink: `https://github.com/moj-analytical-services/splink` → `vendor/splink/` (ambiguous-ER кандидаты для merge/split, entity candidate API).
- OpenRefine: `https://github.com/OpenRefine/OpenRefine` → `third_party/openrefine/` (reconciliation-API для schema-term / alias курирования, референс UX).
- Neo4j APOC: `https://github.com/neo4j-contrib/neo4j-apoc-procedures` → плагин Neo4j в `infra/neo4j/plugins/` (образ `neo4j:2026.05-community` с `apoc`; `apoc.export.json.all`, `apoc.map.removeKeys`, `apoc.diff.*` для snapshots/diff/guard).
- lakeFS: `https://github.com/treeverse/lakeFS` → `third_party/lakefs/` и DVC: `https://github.com/iterative/dvc` → `third_party/dvc/` (версионирование графовых snapshot-артефактов).
- Marquez: `https://github.com/MarquezProject/marquez` → `third_party/marquez/` и DataHub: `https://github.com/datahub-project/datahub` → `third_party/datahub/` (lineage/audit курирования, OpenLineage-события).

Артефакты snapshot хранятся в MinIO/S3 (§13, bucket `kg-snapshots`), метаданные — в Postgres; версии — через lakeFS/DVC.

---

### 16.1 Скелет curation-service и хранилище

- [x] Создать `apps/curation-service/` как отдельный FastAPI-микросервис: `pyproject.toml` (deps: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `neo4j`, `psycopg[binary]`/`sqlalchemy`, `alembic`, `structlog`, `orjson`, `pint`, `qdrant-client`, `opensearch-py`, `boto3`/`minio`), `Dockerfile`, `app/main.py`, `app/config.py`, `app/routers/`, `app/services/`, `app/repositories/`.
- [x] Добавить сервис в `infra/docker-compose.yml` (порт согласно §13.1; зависимости на `postgres`, `neo4j`, `qdrant`, `opensearch`, `minio`), health endpoint `GET /health` возвращает `200 {"status":"ok","neo4j":true,"postgres":true}`.
- [x] Завести Postgres-схему курирования (Alembic migration `0001_curation_init`): таблицы `review_task`, `curation_event`, `decision`, `entity_lock`, `graph_snapshot`, `graph_diff`. Все таблицы имеют `id UUID PK`, `created_at`, `updated_at`.
- [x] Настроить подключения к Neo4j (bolt) и Postgres через `app/config.py` (env `NEO4J_URI`, `NEO4J_AUTH`, `POSTGRES_DSN`); connection pool, graceful shutdown.
- [x] Настроить клиент MinIO/S3 для snapshot-артефактов (env `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, bucket `kg-snapshots`) и клиенты Qdrant/OpenSearch для пропагации `review_status`/`verified` в индексы (§9 Step 8).
- [x] Реализовать слой репозиториев `app/repositories/`: `ReviewTaskRepository`, `CurationEventRepository`, `DecisionRepository`, `EntityLockRepository`, `GraphSnapshotRepository`, `GraphDiffRepository` (интерфейсы CRUD + фильтры).
- [x] Добавить `structlog` JSON-логирование с `trace_id`/`actor_id` в каждой записи; интеграция с OpenTelemetry (span на каждый curation action).

**Критерий приёмки:** `docker compose up curation-service` поднимает сервис, `GET /health` возвращает `200` с проверкой обеих БД; `alembic upgrade head` создаёт все 6 таблиц без ошибок (проверяется `\dt` в psql); все 6 репозиториев инстанцируются и проходят smoke-тест CRUD.

### 16.2 Pydantic/LinkML-модели: ReviewTask, CurationEvent, Decision

- [x] В `packages/kg_schema/` определить Pydantic-модель `CurationEvent` строго по §12.3: поля `id: str` (`cur:<uuid>`), `action: Literal["accept","reject","correct","merge","split","alias_add","mark_inferred","manual_evidence","annotate_gap","schema_change","mark_verified"]`, `actor_id: str` (`user:<uuid>`), `target_type: Literal["node","edge","evidence","schema"]`, `target_id: str`, `before: dict|None`, `after: dict|None`, `reason: str`, `created_at: datetime`. (Enum расширен относительно §12.3, чтобы покрыть все human actions §12.2.)
- [x] Определить модель `Decision`: `id: str` (`dec:<uuid>`), `title`, `rationale`, `curation_event_ids: list[str]`, `affected_entity_ids: list[str]`, `status: Literal["proposed","applied","reverted"]`, `actor_id`, `created_at`, `applied_at`.
- [x] Определить модель `ReviewTask`: `id` (`rev:<uuid>`), `task_type: Literal["low_confidence","ambiguous_er","contradiction","missing_critical_field","low_quality_ocr","new_schema_term"]`, `target_type`, `target_id`, `payload: dict`, `priority: int`, `status: Literal["open","in_review","resolved","dismissed","auto_resolved"]`, `assignee_id: str|None`, `resolution: dict|None`, `resolved_by_event_id: str|None`, `dedup_key: str`, `created_at`, `resolved_at`.
- [x] Определить модель `EntityLock`: `entity_id: str`, `verified_fields: list[str]`, `locked_by: str`, `locked_at: datetime`, `reason: str|None` (источник guard §16.8).
- [x] Определить DTO `GraphSnapshot` (`id`, `label`, `neo4j_tx_id`/`commit`, `uri`, `scope`, `created_at`) и `GraphDiff` (`from_snapshot`, `to_snapshot`, `counts`, `added/removed/changed`) для §16.10.
- [x] Расширить модель `Evidence` (§8.3) полями курирования: `review_status: Literal["pending","accepted","rejected","corrected"]`, `reviewed_by: str|None`, `reviewed_at: datetime|None`, `verified: bool` (default `false`); `source_type` включает `manual` (§8.3) для action `manual_evidence`.
- [x] Добавить в модели узлов/рёбер (`kg_schema`) служебные поля версионирования: `verified: bool`, `verified_fields: list[str]`, `version: int`, `valid_from: datetime`, `valid_to: datetime|None`, `superseded_by: str|None`, `last_curation_event_id: str|None`, `inferred: bool` (для §5.2.3 dashed edge / action `mark_inferred`).
- [x] Описать те же сущности в LinkML-схеме (`packages/kg_schema/linkml/curation.yaml`) и добавить проверку эквивалентности Pydantic↔LinkML в тесте `test_schema_parity`.
- [x] Сгенерировать JSON Schema из Pydantic (`model_json_schema()`) и выложить в `packages/kg_schema/generated/` для контрактов frontend.

**Критерий приёмки:** `pytest packages/kg_schema/tests/test_curation_models.py` зелёный; невалидный `action`/`target_type` вызывает `ValidationError`; `test_schema_parity` подтверждает совпадение полей Pydantic и LinkML; JSON Schema для `CurationEvent`/`Decision`/`ReviewTask`/`EntityLock` присутствует в `generated/`.

### 16.3 Neo4j constraints, индексы и хранение CurationEvent/Decision в графе

- [x] Добавить в `infra/neo4j/constraints.cypher` uniqueness-constraints: `CREATE CONSTRAINT curation_event_id IF NOT EXISTS FOR (n:CurationEvent) REQUIRE n.id IS UNIQUE;` и `CREATE CONSTRAINT decision_id IF NOT EXISTS FOR (n:Decision) REQUIRE n.id IS UNIQUE;`.
- [x] Добавить индексы для запросов истории: `CREATE INDEX curation_event_target IF NOT EXISTS FOR (n:CurationEvent) ON (n.target_id);` и `CREATE INDEX curation_event_created IF NOT EXISTS FOR (n:CurationEvent) ON (n.created_at);`.
- [x] Зарегистрировать в schema-реестре (`packages/kg_schema`, документ §8.2) и в allowlist graph-service новый тип связи `(:Decision)-[:INCLUDES]->(:CurationEvent)` (в §8.2 явно заданы только `AFFECTS`/`CHANGED`) — чтобы обходы истории и TextToCypher allowlist его пропускали.
- [x] Реализовать в `graph-service` Cypher-шаблон записи события: `MERGE (c:CurationEvent {id:$id}) SET c += $props` + `MATCH (e {id:$target_id}) MERGE (c)-[:CHANGED]->(e)` (relationship `(:CurationEvent)-[:CHANGED]->(:Entity)` из §8.2).
- [x] Реализовать Cypher записи решения: `MERGE (d:Decision {id:$id}) SET d += $props` + `(d)-[:AFFECTS]->(:Entity)` для каждого `affected_entity_id`, и `(d)-[:INCLUDES]->(c:CurationEvent)`.
- [x] Обеспечить двойную запись: `CurationEvent`/`Decision` пишутся и в Postgres (для быстрых списков/фильтров), и в Neo4j (для графовых обходов истории); реализовать транзакционный порядок «Postgres→Neo4j» с компенсацией при сбое (outbox или idempotent retry).
- [x] Реализовать Cypher-запрос истории сущности: по `entity_id` вернуть цепочку `CurationEvent` отсортированную по `created_at` (для Entity Detail Page timeline).

**Критерий приёмки:** после применения `constraints.cypher` дубликат `CurationEvent.id` отклоняется Neo4j; запись одного action создаёт ровно 1 узел `CurationEvent`, 1 ребро `CHANGED` и 1 строку в Postgres; `Decision` из N событий создаёт N рёбер `INCLUDES`; запрос истории по `entity_id` возвращает события в хронологическом порядке.

### 16.4 Review queue: репозиторий, приоритеты, дедупликация, назначение

- [ ] Реализовать `ReviewTaskRepository` (`app/repositories/review_task.py`): `create`, `get`, `list(filters)`, `update_status`, `assign`, `resolve`, `dismiss`, `bulk_create`.
- [ ] Реализовать дедупликацию: `dedup_key` вычисляется как хэш от (`task_type`,`target_type`,`target_id`, нормализованный payload); повторное создание задачи с тем же `dedup_key` в статусе `open|in_review` не создаёт дубль, а обновляет `payload`/`priority`.
- [ ] Реализовать модель приоритизации `priority`: функция от `confidence` (ниже → выше приоритет), `task_type` (contradiction > missing_critical_field > ambiguous_er > low_confidence > low_quality_ocr > new_schema_term по умолчанию), количества связанного evidence и «центральности» сущности (degree в графе).
- [ ] Реализовать назначение задач: `assignee_id`, переходы `open→in_review→resolved/dismissed`; запрет resolve чужой `in_review`-задачи без роли `admin` (интеграция с RBAC §16.9).
- [ ] Реализовать SLA/aging: поле `age_hours`, флаг `overdue` (по конфигурируемому порогу на `task_type`), сортировка очереди по (`priority` desc, `created_at` asc).
- [ ] Экспонировать программный интерфейс создания задачи для agent-service (tool `create_review_task`, §7.4): метод `create_from_agent(task_type, target, payload, source="agent")`, куда verifier-node (§7.5 Node 9, флаг `unverified_critical_claim`) и gap_analyzer (§7.5 Node 8) шлют задачи; проходит ту же дедупликацию.
- [ ] Добавить индексы Postgres: `(status, task_type, priority)`, `(dedup_key)` unique partial WHERE `status IN ('open','in_review')`, `(assignee_id, status)`.

**Критерий приёмки:** повторный вызов авто-генерации для того же объекта не увеличивает число `open`-задач (unit-тест на `dedup_key`); список очереди отсортирован по `priority desc, created_at asc`; попытка resolve чужой in-review задачи без роли admin даёт `403`; задача, поставленная агентом через `create_review_task`, появляется в очереди и дедуплицируется наравне с авто-генерацией.

### 16.5 Авто-генерация review-задач (§12.1)

- [ ] Реализовать модуль правил `app/services/rules/` с единым интерфейсом `Rule.detect(context) -> list[ReviewTaskDraft]`; каждое правило чистое и юнит-тестируемое.
- [ ] Rule `low_confidence`: создать задачу если `evidence.confidence < threshold` (threshold из config, по умолчанию `0.65`, синхронно с §6.2 `min_confidence`); payload содержит `evidence_id`, `confidence`, `threshold`, snippet `text`.
  - [ ] Порог задаётся per-`source_type` и per-`property` (override map в config).
- [ ] Rule `ambiguous_er`: создать задачу когда entity resolution (§9 Step 6) вернул `decision:"review_needed"` либо разница score top-1 и top-2 < `margin` (из Splink-скоринга); payload содержит `candidate_id`, `mentions`, `match_probability`, список кандидатов со scores и предлагаемый canonical.
- [ ] Rule `contradiction`: создать задачу при появлении ребра/узла `Contradiction` или `(:Claim)-[:CONTRADICTS]->(:Claim)` (§8.2, Phase 7); payload содержит оба `claim_id`, конфликтующие значения/единицы, evidence обеих сторон, `contradiction_id`.
- [ ] Rule `missing_critical_field`: создать задачу если у `Experiment`/`Measurement`/`ProcessingRegime` отсутствует critical field (список critical-полей per-label в config: например `Measurement` требует `unit`, `value`, `OF_PROPERTY`; `ProcessingRegime` требует `temperature_c`/`time_h`); payload перечисляет `missing_fields` (согласовано с §11 gap `missing_processing_parameter`/`missing_unit`/`missing_equipment`).
- [ ] Rule `low_quality_ocr`: создать задачу если evidence извлечён из источника с низким OCR-качеством (флаг/скор из parsing-стадии Docling, §9 Step 2) или `source_type=table_cell` с низкой уверенностью распознавания; payload содержит `doc_id`, `page`, OCR-score.
- [ ] Rule `new_schema_term`: создать задачу при обнаружении нового термина/типа, отсутствующего в canonical-vocabulary (новый `Property`/`Method`/`Unit`/label вне LinkML-схемы); payload содержит термин, контекст, предложение маппинга; `target_type=schema`.
- [ ] Реализовать Dagster-asset/sensor `curation_task_generator` (`infra/dagster/`), запускаемый после `VALIDATE`/`UPSERT` (§9.1) на новом батче: прогоняет все 6 правил и вызывает `bulk_create` с дедупликацией.
- [ ] Реализовать ручной re-scan endpoint `POST /api/v1/curation/tasks/scan` (по `doc_id`/`batch_id`) для повторной генерации без полного реингеста.
- [ ] Обеспечить идемпотентность: повторный прогон над теми же данными не плодит задачи (проверяется на дедупликации §16.4).

**Критерий приёмки:** на фикстурном датасете с заведомыми дефектами (6 кейсов — по одному на правило) генератор создаёт ровно 6 задач с корректными `task_type` и `payload`; `ambiguous_er` срабатывает именно на ER-выходе `decision:"review_needed"`; повторный прогон создаёт 0 новых задач; отключение любого правила в config убирает соответствующую задачу.

### 16.6 Human actions: обработчики (§12.2)

- [ ] Ввести единый паттерн `ActionHandler.execute(action_request, actor) -> CurationEvent`: валидирует вход, вычисляет `before` (снимок цели), применяет изменение в графе/Postgres, пишет `CurationEvent` (§16.3), опционально закрывает связанную `ReviewTask`. Всё в одной транзакции с rollback при ошибке.
- [ ] Action `accept`: перевести `Evidence.review_status → accepted`, проставить `reviewed_by`, `reviewed_at`, `verified=true`; связать `CurationEvent{action:"accept",target_type:"evidence"}`.
- [ ] Action `reject`: `review_status → rejected`; извлечённые из этого evidence узлы/рёбра помечаются как отозванные (`valid_to=now`, не удаляются физически); `CurationEvent{action:"reject"}`.
- [ ] Action `correct`: изменить `value`/`unit`/иное поле цели; сохранить `before`/`after`, проставить `review_status=corrected`, `verified=true`, добавить изменённые поля в `verified_fields`; для единиц — валидация через `pint` (совместимость размерности) и пересчёт `value_normalized`.
- [ ] Action `merge`: объединить сущности через `POST /api/v1/entities/merge` (§6.2). Перенести все входящие/исходящие рёбра, объединить `aliases`, выбрать canonical `id`, пометить исходные узлы `superseded_by=<canonical_id>`, `valid_to=now`; записать `CurationEvent{action:"merge", before:{merged_ids}, after:{canonical_id}}`. Сохранить merge-history (Phase 3 acceptance: «merge history is preserved»).
  - [ ] Реализовать guard: нельзя merge, если у сущностей конфликтуют `verified`-поля без явного `reason`/override.
- [ ] Action `split`: разделить сущность на N узлов; перераспределить рёбра/evidence по правилу из payload; исходный узел помечается `superseded_by` (список), создаются новые с новыми `id`; `CurationEvent{action:"split"}`.
- [ ] Action `alias_add`: добавить alias через `POST /api/v1/entities/{entity_id}/aliases` (§6.2); обновить `aliases`, `aliases_text` (для fulltext index §8.4); `CurationEvent{action:"alias_add"}`.
- [ ] Action `mark_inferred`: проставить ребру `inferred=true` (поле `GraphEdge.inferred` из §5.3, dashed edge §5.2.3) с указанием основания; `CurationEvent{action:"mark_inferred",target_type:"edge"}`.
- [ ] Action `manual_evidence`: создать `Evidence` с `source_type=manual` (§8.3), `extractor="manual"`, `verified=true`, привязать к целевому claim/measurement (`SUPPORTS`/`SUPPORTED_BY`); `CurationEvent{action:"manual_evidence"}`.
- [ ] Action `annotate_gap`: пометить `Gap`-узел (§11, `(:Gap)-[:ABOUT]->(:Entity)`) как `status=known|irrelevant|accepted` с комментарием; `CurationEvent{action:"annotate_gap"}`; при необходимости закрыть связанную gap-задачу.
- [ ] Action `mark_verified`: пометить сущность/эксперимент как `verified=true` либо `review_status=needs_review` (Experiment Explorer §5.2.5 «mark as verified/needs review», Entity Detail §5.2.4 review status); `CurationEvent{action:"mark_verified",target_type:"node"}`.
- [ ] Action `schema_change`: применить решение по `new_schema_term` — принять новый термин в vocabulary/LinkML либо смапить на существующий; `CurationEvent{action:"schema_change",target_type:"schema", after:{term, mapping}}`; версионировать canonical-vocabulary/LinkML и триггерить её обновление.
- [ ] Резолюция контрадикций: при разрешении задачи `contradiction` (выбор верного claim через `accept`/`correct`/`reject`) проставить узлу `Contradiction` (§8.1) `status=resolved` и `resolution`, снять/погасить `(:Claim)-[:CONTRADICTS]->(:Claim)` при необходимости; `CurationEvent`, закрытие contradiction-задачи (§11 `contradictory_measurements`).
- [ ] Пропагация в индексы: после `accept`/`reject`/`correct`/`merge`/`mark_verified` обновить `review_status`/`verified`/`confidence` в Qdrant- и OpenSearch-payload затронутых chunks/claims/entity descriptions (§9 Step 8), чтобы работали `verified_only` (§6.2) и «boost verified evidence» (§10.2).
- [ ] Decision по изменению pipeline/конфигурации (§2.1 сценарий 5 «изменение pipeline»): фиксировать смену версии extractor/модели/порогов как `CurationEvent{target_type:"schema"}` + `Decision`, привязанный к затронутым прогонам/сущностям (auditability изменений конвейера).
- [ ] Каждый обработчик при успехе, если пришёл из review-задачи, ставит `ReviewTask.status=resolved` и `resolved_by_event_id`.

**Критерий приёмки:** для каждого из 11 actions есть интеграционный тест, проверяющий: (1) корректное изменение цели в Neo4j/Postgres, (2) созданный `CurationEvent` с валидными `before`/`after`, (3) закрытие связанной задачи; `merge`+`split` сохраняют полную историю (исходные узлы находимы через `superseded_by`); `correct` единицы с несовместимой размерностью отклоняется (`422`); после `accept`/`correct` соответствующий документ находится с `verified_only=true` (payload в Qdrant/OpenSearch обновлён); резолюция `contradiction` переводит узел `Contradiction` в `resolved`.

### 16.7 Версионирование и привязка решений к изменениям графа (§12.3, §17.8)

- [ ] Реализовать стратегию версионирования узлов/рёбер: при курирующем изменении увеличивать `version`, ставить `valid_to` на старую версию и создавать/обновлять запись с новой версией; предыдущие версии не удаляются (Step 7: «preserve previous versions»).
- [ ] Хранить на каждой сущности `last_curation_event_id`, чтобы из графа можно было перейти к событию, которое привело к текущему состоянию.
- [ ] Реализовать `Decision`-агрегацию: сгруппировать связанные `CurationEvent` в один `Decision` (например, серия merge при разрешении дубликатов); API `POST /api/v1/curation/decisions` создаёт Decision из списка event_id, связывает `(:Decision)-[:AFFECTS]->(:Entity)` и `INCLUDES` события.
- [ ] Реализовать revert: `POST /api/v1/curation/decisions/{id}/revert` восстанавливает `before`-состояние всех входящих событий (в обратном порядке), создавая компенсирующие `CurationEvent{action:...}` и переводя `Decision.status=reverted`. Revert сам логируется как событие (полная auditability, ничего не удаляется).
- [ ] Гарантировать полную трассируемость: для любого текущего значения поля можно построить цепочку `значение → CurationEvent → Decision → actor → evidence` (запрос-обход в Neo4j).
- [ ] Написать тест «versioned decisions»: применить correct→revert и проверить, что итоговое состояние равно исходному, но история содержит 2 события (correct + revert) и не потеряна.

**Критерий приёмки:** после любой цепочки правок для сущности доступны все её версии с корректными `valid_from/valid_to`; revert решения из 3 событий полностью восстанавливает `before`-состояние и добавляет 3 компенсирующих события; обход `значение→event→decision→actor` возвращает непустой путь для каждого верифицированного поля.

### 16.8 Защита проверенных полей от перезаписи (§9 Step 7)

- [ ] Реализовать `EntityLock`/поле `verified_fields` (модель §16.2, `EntityLockRepository` §16.1): список полей узла/ребра, помеченных как проверенные человеком, которые ingestion НЕ имеет права перезаписывать автоматически.
- [ ] Модифицировать граф-upsert (`graph-service`, Step 7 §9): `MERGE by canonical id`, но `SET` только для полей, отсутствующих в `verified_fields`; проверенные поля пропускаются. Реализовать Cypher/параметрический guard (например, `apoc.map.removeKeys(props, verified_fields)` перед `SET`).
- [ ] При попытке ingestion изменить verified-поле с новым (отличающимся) значением — не перезаписывать, а создать review-задачу `contradiction`/`low_confidence` с обоими значениями (человек решает).
- [ ] Защитить canonical entities после review от overwrite при повторной ER (Phase 3 acceptance: «protect reviewed canonical entities from overwrite») — merge не должен «расклеивать» проверенное объединение автоматически.
- [ ] Написать интеграционный тест: пометить поле `verified`, повторно прогнать ingestion того же документа с другим значением — verified-поле не меняется, создаётся review-задача.

**Критерий приёмки:** повторный ingest с изменённым значением verified-поля оставляет значение прежним и порождает ровно одну review-задачу; не-verified поля обновляются нормально (проверяется двумя тест-кейсами: verified и non-verified).

### 16.9 Curation UI backend: endpoints и контракты (§6.2, §5.2.8)

- [ ] Реализовать `GET /api/v1/curation/tasks` (list с фильтрами `status`, `task_type`, `assignee`, `priority_min`, пагинация, сортировка) — питает Admin review queue (§5.2.8).
- [ ] Реализовать `GET /api/v1/curation/tasks/{task_id}` — деталь задачи с загруженным контекстом (target, evidence, snippet, кандидаты, предлагаемое действие).
- [ ] Реализовать `POST /api/v1/curation/tasks/{task_id}/assign`, `.../dismiss`, `.../resolve` — переходы статусов.
- [ ] Реализовать `POST /api/v1/evidence/{evidence_id}/review` (§6.2) c телом `{action: accept|reject|correct, value?, unit?, reason}` — маппится на handlers §16.6; возвращает созданный `CurationEvent`.
- [ ] Расширить контекст Evidence Inspector (§5.2.6): `GET /api/v1/evidence/{evidence_id}` и `GET /api/v1/evidence/by-edge/{edge_id}` (§6.2) возвращают `review_status`, `reviewed_by`, `reviewed_at` («reviewer decision», «who confirmed/corrected») и `id` графового ребра/claim, порождённого из evidence («graph edge generated from this evidence»).
- [ ] Подключить `POST /api/v1/entities/merge` и `POST /api/v1/entities/{entity_id}/aliases` (§6.2) к handlers `merge`/`alias_add`.
- [ ] Реализовать `GET /api/v1/curation/merge-candidates?entity_id=` — entity candidate API (Phase 3 «implement entity candidate API»), питаемый Splink ER-выходом (`vendor/splink/`, §9 Step 6), для merge/split UI Admin.
- [ ] Реализовать generic action endpoint `POST /api/v1/curation/actions` c телом `{action, target_type, target_id, payload, reason}` для split / mark_inferred / manual_evidence / annotate_gap / mark_verified / schema_change.
- [ ] Реализовать `GET /api/v1/curation/events?target_id=&actor_id=&action=&from=&to=` (история/audit) и `GET /api/v1/entities/{entity_id}/history` (timeline для Entity Detail Page §5.2.4). История отдаётся и в виде DAG (`events` + `decisions` с рёбрами `INCLUDES`/`AFFECTS`) для decision-history layout ELK.js/dagre (§5.1, §5.2.4).
- [ ] Реализовать `POST /api/v1/curation/decisions`, `GET /api/v1/curation/decisions/{id}`, `POST /api/v1/curation/decisions/{id}/revert`.
- [ ] Реализовать schema-term curation endpoints: `GET /api/v1/curation/schema/terms` (pending новые термины), `POST /api/v1/curation/schema/terms/{id}` (accept/map/reject) — под «edit schema terms» (§5.2.8); опционально проксировать reconciliation-API формата OpenRefine (`third_party/openrefine/`) для alias/term сверки.
- [ ] Реализовать SSE/WebSocket `GET /api/v1/curation/tasks/stream` для live-обновления очереди в Admin UI.
- [ ] Прокинуть все endpoints через API Gateway (§6.2) с auth/session, rate-limit и записью в audit log; вернуть согласованные error-схемы (`401` неаутентифицирован, `422` валидация, `403` RBAC, `409` конфликт версий).
- [ ] Выводить `actor_id` из аутентифицированной сессии/JWT (API Gateway §6.2), а не из тела запроса; анонимный мутирующий вызов отклоняется `401`.
- [ ] Реализовать optimistic concurrency: мутирующие endpoints принимают `expected_version`/`If-Match` по полю `version` (§16.7); при рассинхроне — `409` (два куратора не затирают правки друг друга).
- [ ] Реализовать RBAC-роли: `viewer` (только чтение очереди), `curator` (actions/resolve), `admin` (merge/split/schema_change/revert, назначение). Проверять роль в каждом мутирующем endpoint.
- [ ] Записывать audit log каждого мутирующего вызова (actor, action, target, timestamp, IP) — согласованно с Phase 8 «audit logs».
- [ ] Сгенерировать и опубликовать OpenAPI-спеку curation-раздела; добавить контракт-тесты соответствия ответов Pydantic-моделям.

**Критерий приёмки:** OpenAPI содержит все перечисленные пути; e2e-сценарий «взять задачу из очереди → resolve через `/evidence/{id}/review` → задача закрыта → событие видно в `/curation/events` и в `/entities/{id}/history`» проходит; вызов мутирующего endpoint без нужной роли даёт `403`, без аутентификации — `401`; повторная правка с устаревшим `expected_version` даёт `409`; SSE-поток присылает событие при создании новой задачи; Evidence Inspector получает reviewer decision и id порождённого ребра.

### 16.10 Сравнение версий графа (graph diff)

- [ ] Реализовать снапшоты графа: `POST /api/v1/curation/snapshots` создаёт именованный snapshot через `apoc.export.json.all` (или экспорт подграфа по фильтру), сохраняет артефакт в MinIO/S3 (bucket `kg-snapshots`, §13) и метаданные в таблице `graph_snapshot` (`id`, `label`, `neo4j_tx_id`/`commit`, `created_at`, `uri`, `scope`).
- [ ] Интегрировать версионирование snapshot-артефактов через lakeFS (`third_party/lakefs/`) или DVC (`third_party/dvc/`): каждый snapshot — commit/version с ссылкой на предыдущий; снапшот пригоден как точка backup/restore (Phase 9 «backup/restore»).
- [ ] Реализовать diff-движок `app/services/graph_diff.py`: сравнение двух snapshot (или snapshot↔live) и вычисление `added_nodes`, `removed_nodes`, `changed_nodes` (по полям), `added_edges`, `removed_edges`, `changed_edges`; матчинг по canonical `id`, для изменённых полей — property-level diff (`before`/`after`).
- [ ] Реализовать «curation diff»: показать, какие изменения графа между версиями произошли из-за курирования (по связанным `CurationEvent.created_at` в интервале), отделив их от ingestion-изменений (before-after curation, §5.2.3).
- [ ] Реализовать `POST /api/v1/curation/graph/diff` c телом `{from_snapshot, to_snapshot|"live", scope?}` — возвращает структурированный diff в формате, пригодном для Reagraph (узлы/рёбра с пометкой `status: added|removed|changed`) и сводку счётчиков.
- [ ] Реализовать `GET /api/v1/curation/snapshots` (список) и `GET /api/v1/curation/snapshots/{id}` (метаданные/скачивание).
- [ ] Кешировать/сохранять вычисленный diff в таблицу `graph_diff` (idempotent по паре snapshot-id) для быстрого повторного открытия в UI.
- [ ] Написать тест: snapshot A → применить merge+correct → snapshot B → `diff(A,B)` содержит corrected node в `changed_nodes` с верными `before/after` и объединённые узлы в `removed_nodes`/`changed_edges`.

**Критерий приёмки:** для контролируемой пары версий diff-endpoint возвращает точный набор added/removed/changed с property-level `before/after`; ответ рендерится в Reagraph-совместимом формате с пометками статуса; «curation diff» корректно отделяет курирующие изменения от ingestion (проверяется тестом со смешанным батчем); артефакт snapshot присутствует в bucket `kg-snapshots` и версионирован в lakeFS/DVC.

### 16.11 Тестирование, фикстуры, наблюдаемость, lineage

- [ ] Собрать фикстурный корпус `apps/curation-service/tests/fixtures/` с заранее известными дефектами под все 6 правил §12.1 и целями для всех 11 actions §12.2/§16.6.
- [ ] Покрыть unit-тестами: правила детекции, дедупликацию, приоритизацию, каждый ActionHandler, guard verified-полей, версионирование/revert, diff-движок, пропагацию в индексы.
- [ ] Написать e2e интеграционные тесты через API Gateway (поднятые Neo4j+Postgres+Qdrant+OpenSearch+MinIO в testcontainers/compose): полный цикл «ingest → авто-задачи → human action → событие → history → snapshot → diff → verified_only-поиск».
- [ ] Добавить метрики (OpenTelemetry/Prometheus): `curation_tasks_open`, `curation_tasks_resolved_total{task_type}`, `curation_action_latency_seconds{action}`, `verified_fields_protected_total`, `review_backlog_age_p95`, `auto_resolved_ratio`.
- [ ] Добавить curation-панель в Admin metrics (`GET /api/v1/admin/metrics`, §6.2): размер очереди по типам, throughput кураторов, доля auto-resolved.
- [ ] Эмитить lineage/audit-события курирующих действий в Marquez (`third_party/marquez/`, OpenLineage) или DataHub (`third_party/datahub/`) — регистрировать курирование как шаг lineage (Phase 8 «lineage»/«audit logs»).
- [ ] Написать `README.md` сервиса с описанием ролей, endpoints, правил, RBAC и порядка локального запуска (для Phase 8/9 governance-документации).

**Критерий приёмки:** `pytest apps/curation-service/tests` проходит полностью (unit+e2e) в CI; метрики курирования доступны на `/admin/metrics` и меняются при выполнении action (наблюдается рост `curation_tasks_resolved_total`); при курирующем action в Marquez/DataHub появляется lineage-событие.


---


## 17. Frontend — все экраны и graph-визуализация

Раздел покрывает §5 целиком (стек §5.1, все экраны §5.2, контракты §5.3), детали реализации §14, а также вендоринг OSS graph-библиотек из §22. Весь код фронтенда живёт в `apps/frontend/` (см. структуру §6.1). Раздел зависит от бекенда: API Gateway endpoints §6.2 (раздел про API Gateway), контракты DTO из `packages/kg_common`, SSE/WebSocket chat stream из agent-service. Там, где backend ещё не готов, все задачи используют MSW-моки (mock service worker) на основе контрактов §5.3/§6.2, чтобы фронт можно было разрабатывать и тестировать независимо.

Целевой UX (§23): scientific intelligence workspace — исследователь задаёт вопрос в чате → агент строит план и стримит ответ → рядом появляется граф материалов/режимов/экспериментов/свойств/источников → клик по ребру показывает доказательство → пробелы данных становятся first-class объектами. Раздел также закрывает frontend-части фаз §16: Phase 5 (agent chat UI), Phase 6 (graph explorer + evidence UX), Phase 7 (gap dashboard), Phase 8 (metadata/lineage/audit в admin UI).

---

### 17.1 Bootstrap проекта, стек и tooling (§5.1, §14.1)

- [x] Создать `apps/frontend/` как отдельный package в mono-repo (pnpm workspace), с `package.json`, привязанным к workspace root (`pnpm-workspace.yaml` должен включать `apps/*` и `packages/*`).
- [x] Инициализировать проект на **Vite + React 19 + TypeScript** (`vite.config.ts`, `tsconfig.json` с `strict: true`, `noUncheckedIndexedAccess: true`, path alias `@/*` → `src/*`). Если выбран Next.js — использовать App Router; принять решение и зафиксировать в `apps/frontend/DECISIONS.md` (по §5.1 допускаются оба, по умолчанию берём Vite для SPA-скорости).
- [x] Установить и зафиксировать версии зависимостей из §14.1 в `package.json`:
  - `react`, `react-dom`, `typescript`, `vite`;
  - `@tanstack/react-query`, `@tanstack/react-router` (или Next App Router);
  - `zustand` (основной state store), опционально `jotai` для atom-based локального состояния графа;
  - `zod`, `react-hook-form`, `@hookform/resolvers`;
  - `tailwindcss`, `postcss`, `autoprefixer`, `lucide-react`;
  - `reagraph`, `sigma`, `graphology` (+ `graphology-layout`, `graphology-layout-forceatlas2`, `graphology-communities-louvain`), `cytoscape` (+ `cytoscape-cose-bilkent`, `cytoscape-dagre`), `react-force-graph` (2D/3D);
  - `@xyflow/react` (React Flow) для pipeline/agent DAG, `dagre` (`@dagrejs/dagre`) и/или `elkjs` для авто-layout DAG/lineage/decision-history (§5.1 таблица: ELK.js/dagre — hierarchical layouts);
  - `echarts`, `echarts-for-react`; `@observablehq/plot` для части аналитики;
  - `react-markdown`, `remark-gfm` для рендера ответов агента.
- [x] Настроить **TailwindCSS** (`tailwind.config.ts`, `src/styles/globals.css` c `@tailwind base/components/utilities`), тему (CSS-переменные для light/dark), контент-пути на `src/**/*.{ts,tsx}`.
- [x] Инициализировать **shadcn/ui** (`components.json`, `src/components/ui/`), поставить базовый набор компонентов: `button`, `input`, `select`, `dialog`, `sheet`, `tabs`, `table`, `tooltip`, `badge`, `card`, `dropdown-menu`, `command`, `toast`, `skeleton`, `resizable`, `scroll-area`, `accordion`.
- [x] Настроить линт/формат: `eslint` (typescript-eslint, react-hooks, jsx-a11y), `prettier`, `stylelint` для css; добавить `pnpm lint`, `pnpm typecheck`, `pnpm format:check` скрипты. Все скрипты проходят без ошибок на пустом скелете.
- [x] Настроить env-конфигурацию: `.env.example` с `VITE_API_BASE_URL`, `VITE_SSE_BASE_URL`, `VITE_WS_BASE_URL`; типобезопасный доступ через `src/lib/env.ts` (валидация через Zod при старте).
- [x] Настроить dev-proxy на API Gateway (`/api/v1` → `VITE_API_BASE_URL`) в `vite.config.ts` (или `next.config.js` rewrites).

**Критерий приёмки:** `pnpm --filter frontend dev` поднимает пустое приложение на `localhost`, `pnpm --filter frontend build` собирает production-бандл без ошибок, `pnpm lint && pnpm typecheck` зелёные, все пакеты из §14.1 присутствуют в `package.json`.

---

### 17.2 Вендоринг/клонирование OSS graph-библиотек (§22)

- [x] Создать `third_party/frontend/` для вендоринга исходников OSS-графовых библиотек (для reference, кастомизации renderer'ов и локального форка при необходимости). Добавить в `.gitignore`/`.gitattributes` политику (submodule vs vendored copy — зафиксировать в `third_party/README.md`).
- [x] Клонировать **Reagraph**: `git clone https://github.com/reaviz/reagraph third_party/frontend/reagraph` (основной graph UI; изучить API `GraphCanvas`, custom nodes/edges, theming, `useSelection`, `layoutType`).
- [x] Клонировать **Sigma.js**: `git clone https://github.com/jacomyal/sigma.js third_party/frontend/sigma.js` (WebGL large-graph renderer; изучить custom node/edge programs, reducers, camera API).
- [x] Клонировать **Graphology**: `git clone https://github.com/graphology/graphology third_party/frontend/graphology` (in-memory граф-модель, метрики, layout, import/export GEXF/JSON).
- [x] Клонировать **Cytoscape.js**: `git clone https://github.com/cytoscape/cytoscape.js third_party/frontend/cytoscape.js` (layouts, export figures, graph-алгоритмы в браузере).
- [x] Клонировать **react-force-graph**: `git clone https://github.com/vasturiano/react-force-graph third_party/frontend/react-force-graph` (2D/3D/VR force graphs для wow-эффекта/3D демо).
- [x] Клонировать **Apache ECharts**: `git clone https://github.com/apache/echarts third_party/frontend/echarts` (charts для аналитики: heatmap, sankey, timeline).
- [x] Клонировать **React Flow (xyflow)**: `git clone https://github.com/xyflow/xyflow third_party/frontend/xyflow` (`@xyflow/react`; изучить custom node types, handles, dagre/ELK.js авто-layout) — использовать строго для pipeline/agent DAG (§5.1), не для KG.
- [x] Опционально клонировать запасные из §5.1/§22: G6 (`antvis/G6`), Graphin (`antvis/Graphin`), Graphistry Graph App Kit, D3+d3-force — пометить как optional (брать только при deep-customization / GPU visual analytics / low-level widgets).
- [x] Написать `third_party/frontend/README.md`: назначение каждой библиотеки (маппинг на §5.1: Reagraph=main, Sigma/Graphology=large-graph, Cytoscape=layout/export, react-force-graph=3D, ECharts=charts, React Flow=pipeline/agent DAG), лицензии (проверить совместимость: MIT/Apache-2.0), версия/commit hash.

**Критерий приёмки:** все 7 обязательных репозиториев (Reagraph, Sigma.js, Graphology, Cytoscape.js, react-force-graph, ECharts, xyflow/React Flow) склонированы в `third_party/frontend/`, `third_party/frontend/README.md` содержит таблицу «библиотека → роль в UI → лицензия → pinned commit», лицензии проверены и совместимы.

---

### 17.3 Типы контрактов и API-client слой (§5.3, §6.2)

- [x] Создать `src/types/graph.ts` с точной реализацией контракта §5.3: `GraphNode` (id, label, type union `'Material' | 'Experiment' | 'ProcessingRegime' | 'Property' | 'Equipment' | 'Paper' | 'Claim' | 'Lab' | 'Person' | 'Gap'`, confidence, evidenceCount, verified, missingFields, properties), `GraphEdge` (id, source, target, label, type, confidence, evidenceCount, inferred, contradicted, evidenceIds), `GraphResponse` (nodes, edges, layoutHints.rootNodeIds, layoutHints.communities, queryContext.userQuery/filters/generatedCypher).
- [x] Добавить тип ответа `POST /graph/query` из §6.2 (envelope-объект с полями `summary: string`, `experiments[]` = { id, material, processing, property, value, unit, effect, confidence, evidenceIds }, `gaps[]` = { type, entityId, description }, `graph: GraphResponse`, `citations: []`), а также запрос `GraphQueryRequest` (query_type, material, processing.{operation,temperature_c,time_h}, property, filters.{min_confidence,verified_only,date_from}, include_evidence, include_graph). Покрыть Zod-схемой.
- [x] Создать `src/types/chat.ts` с `ChatStreamEvent` discriminated union из §5.3: `token`, `tool_start`, `tool_end`, `evidence`, `graph`, `table`, `gap`, `error`; плюс типы `EvidenceRef`, `TablePayload`, `GapFinding`.
- [x] Создать Zod-схемы, зеркалящие все контракты (`src/lib/api/schemas.ts`), для runtime-валидации ответов API и SSE-событий; типы выводить через `z.infer` чтобы TS-типы и рантайм-валидация не расходились.
- [x] По возможности не дублировать DTO вручную, а смэпить общие контракты из `packages/kg_common` (shared DTOs §6.1): если backend публикует OpenAPI/JSON-schema из `kg_common`, генерировать TS-типы оттуда как единый источник истины; зафиксировать решение в `DECISIONS.md`.
- [x] Настроить генерацию типов из OpenAPI-схемы API Gateway (`openapi-typescript` → `src/lib/api/generated.ts`), со скриптом `pnpm gen:api`. Пока backend недоступен — держать committed snapshot OpenAPI JSON в `src/lib/api/openapi.snapshot.json` (составленный по §6.2).
- [x] Реализовать HTTP-клиент `src/lib/api/client.ts`: обёртка над `fetch` с baseURL, JSON parse+Zod-валидацией, обработкой ошибок (типизированный `ApiError`), auth-заголовком (session), retry для идемпотентных GET, отменой через `AbortSignal`.
- [x] В `client.ts` обработать rate-limit (HTTP 429) с backoff/`Retry-After` и user-facing toast, а также прокидывать корреляционный заголовок запроса для audit-logs (§6.2: rate limits, audit logs).
- [x] Реализовать endpoint-модули (по §6.2) в `src/lib/api/endpoints/`:
  - `entities.ts` — `search` (`GET /entities/search?q=&type=&limit=`), `get` (`GET /entities/{id}`), `neighbors` (`GET /entities/{id}/neighbors?depth=&types=`), `merge` (`POST /entities/merge`), `addAliases` (`POST /entities/{id}/aliases`);
  - `graph.ts` — `query` (`POST /graph/query`, возвращает envelope summary/experiments/gaps/graph/citations §6.2), `expand` (`POST /graph/expand`), `path` (`POST /graph/path`), `subgraph` (`POST /graph/subgraph`), `schema` (`GET /graph/schema`);
  - `search.ts` — `hybrid`/`vector`/`keyword` (`POST /search/*`);
  - `experiments.ts` — `list` (`GET /experiments`), `get` (`GET /experiments/{id}`), `query` (`POST /experiments/query`);
  - `evidence.ts` — `get` (`GET /evidence/{id}`), `byEdge` (`GET /evidence/by-edge/{edge_id}`), `review` (`POST /evidence/{id}/review`);
  - `gaps.ts` — `list` (`GET /gaps`), `scan` (`POST /gaps/scan`), `matrix` (`GET /gaps/matrix`);
  - `documents.ts` — `upload` (`POST /documents/upload`), `get` (`GET /documents/{id}`), `parsed` (`GET /documents/{id}/parsed`), `page` (`GET /documents/{id}/pages/{page}`), `reindex` (`POST /documents/{id}/reindex`);
  - `ingest.ts` — `createJob` (`POST /ingest/jobs`), `getJob` (`GET /ingest/jobs/{id}`), `cancelJob` (`POST /ingest/jobs/{id}/cancel`);
  - `admin.ts` — `health` (`GET /admin/health`), `metrics` (`GET /admin/metrics`);
  - `chat.ts` — `createSession` (`POST /chat/sessions`), `getSession` (`GET /chat/sessions/{id}`), `postMessage` (`POST /chat/sessions/{id}/messages`), stream URL builder (`GET /chat/sessions/{id}/stream`).
- [x] Настроить **TanStack Query**: `src/lib/query/queryClient.ts` (defaults: staleTime, retry, error handling), `QueryClientProvider` в `App.tsx`, единый `queryKeys` фабрикатор (`src/lib/query/keys.ts`). Обернуть каждый endpoint в query/mutation-хук в `src/hooks/api/` (`useEntitySearch`, `useEntityNeighbors`, `useGraphQuery`, `useExperiments`, `useEvidence`, `useGaps`, `useGapMatrix`, `useDocument`, `useIngestJob` и т.д.).
- [x] Настроить **MSW** (mock service worker) `src/mocks/`: handlers для всех endpoints §6.2 с фикстурами, соответствующими примерам запроса/ответа §6.2 (graph query request/response с `query_type: material_regime_property`) и контрактам §5.3; включить в dev и в тестах. Фикстуры графа — реалистичный Al-Cu/aging/hardness пример из §5.2.2/§6.2.

**Критерий приёмки:** все типы §5.3 реализованы 1:1 и покрыты Zod-схемами; типизирован envelope-ответ `POST /graph/query` из §6.2; каждый endpoint §6.2 имеет типизированный клиент-метод и TanStack Query hook; клиент обрабатывает 429/ошибки/отмену; MSW отдаёт валидные моки для всех endpoints; `pnpm typecheck` проходит; unit-тест валидирует, что пример graph-response и graph-query-envelope из §6.2 проходят Zod-парсинг.

---

### 17.4 Streaming: SSE / WebSocket для chat и job progress (§5.3, §6.2, §14.3)

- [ ] Реализовать `src/lib/sse/chatStream.ts`: подключение к `GET /api/v1/chat/sessions/{session_id}/stream` через `EventSource` (по §14.3), парсинг каждого события в `ChatStreamEvent`, Zod-валидация, типобезопасный reducer-callback (`onToken`, `onToolStart`, `onToolEnd`, `onEvidence`, `onGraph`, `onTable`, `onGap`, `onError`). Обработка reconnect с backoff и `Last-Event-ID`.
- [ ] Добавить WebSocket-вариант транспорта `src/lib/ws/` (fallback/альтернатива SSE) с тем же событийным контрактом — переключение через env/feature flag; общий интерфейс `ChatTransport`.
- [ ] Реализовать job-progress стриминг для ingestion (`GET /ingest/jobs/{job_id}` polling + SSE, если доступно): хук `useJobProgress(jobId)` возвращает статус/процент/лог.
- [ ] Реализовать хук `useChatStream(sessionId)`: аккумулирует токены в текущее сообщение, собирает tool-timeline, накапливает graph/evidence/table/gap payloads в структуру состояния сообщения, обрабатывает завершение и ошибки; отмена стрима при unmount/abort.
- [ ] Написать unit-тесты стрим-парсера на синтетическом потоке всех типов событий из §5.3 (включая частично полученные токены и `error`).

**Критерий приёмки:** `useChatStream` корректно собирает финальное сообщение из синтетического потока `token`/`tool_start`/`tool_end`/`evidence`/`graph`/`table`/`gap`, обрабатывает `error`, переживает reconnect; тесты зелёные.

---

### 17.5 App shell, routing, state, дизайн-система

- [ ] Настроить **TanStack Router** (или Next App Router): маршруты `/` (Home), `/chat/:sessionId?`, `/graph`, `/entity/:entityId`, `/experiments`, `/evidence/:evidenceId`, `/document/:docId`, `/gaps`, `/admin`, с типобезопасными params/search-params (Zod). Файл `src/router.tsx` (или `app/` дерево).
- [ ] Реализовать app shell `src/components/layout/`: `AppLayout` (top nav + боковое меню + content), глобальный `CommandPalette` (shadcn `command`, Cmd+K для быстрого перехода/поиска сущностей), `ThemeProvider` (light/dark), `Toaster`, глобальный error boundary + suspense fallback (skeletons).
- [ ] Реализовать auth/session слой (§6.2 auth/session): `src/lib/auth/` — контекст сессии, чтение/refresh сессии, `ProtectedRoute`/route guard, редирект на login при 401, интеграция с auth-заголовком `client.ts`; минимальный экран/диалог входа, если backend требует аутентификацию.
- [ ] Настроить **Zustand** stores в `src/stores/`: `chatStore` (сессии, сообщения, активная вкладка ответа), `graphStore` (текущий `GraphResponse`, selection, layout, visual-encoding настройки, история expand), `filtersStore` (глобальные фильтры: material/property/regime/lab/date/confidence), `savedViewsStore` (сохранённые graph views), `uiStore` (панели open/close, drawer). Persist критичных частей в `localStorage` (saved views, filters, theme).
- [ ] Реализовать общий компонент фильтров `src/components/filters/GlobalFilters.tsx`: material, property, processing regime, lab, date range, min confidence, verified-only toggle, тип узла (node type), источник (source) — с RHF+Zod, синхронизацией в `filtersStore` и в URL search-params (по §2.1: фильтры по типам узлов, времени, confidence, источникам, лабораториям, статусу верификации).
- [ ] Реализовать переиспользуемые UI-примитивы домена: `ConfidenceBadge`, `EntityTypeChip` (цвет по типу сущности), `VerifiedLock` (lock icon для human-verified), `EvidenceCountBadge`, `CitationChip`, `WarningBanner`.
- [ ] Определить единую цветовую/визуальную схему кодировок в `src/lib/graphEncoding.ts` (single source of truth для §5.2.3): маппинг entity type → color, функции size(evidenceCount/centrality), edgeThickness(evidenceCount), edgeOpacity(confidence), стили dashed(inferred)/red(contradicted)/hollow(missingFields)/lock(verified). Используется и Reagraph, и Sigma, и Cytoscape, и 3D режимами.
- [ ] Реализовать общий модуль графиков `src/components/charts/`: типизированные обёртки над ECharts (`echarts-for-react`) и Observable Plot (`@observablehq/plot`) с единой light/dark темой; переиспользуются в Entity timeline (17.11), Gap Dashboard (17.14), Admin metrics/lineage (17.15/17.20).

**Критерий приёмки:** навигация между всеми маршрутами работает, Cmd+K открывает command palette и осуществляет переход/поиск, тема переключается и сохраняется, глобальные фильтры (включая node type/source) отражаются в URL и store; auth-guard редиректит неавторизованных; `graphEncoding.ts` покрыт unit-тестами (проверка цветов/размеров/стилей для представительных входов).

---

### 17.6 Экран Home / Search (§5.2.1)

- [ ] Реализовать `src/features/home/HomePage.tsx`: глобальный search bar по центру (large, autofocus), с debounce и live-подсказками сущностей (`useEntitySearch`).
- [ ] Реализовать переключатель режимов поиска: `Question` | `Entity` | `Experiment` | `Document` | `Gap` (segmented control); выбор режима определяет целевой маршрут при submit (Question→`/chat`, Entity→`/entity` или `/graph`, Experiment→`/experiments`, Document→`/document` (viewer 17.19), Gap→`/gaps`).
- [ ] Реализовать блок «последние вопросы» (recent questions) — читает из `chatStore`/localStorage, клик восстанавливает сессию.
- [ ] Реализовать блок «сохранённые graph views» (saved views) — из `savedViewsStore`, клик открывает `/graph` с восстановленным состоянием (nodes/edges/layout/filters).
- [ ] Реализовать быстрые фильтры на Home: material, property, processing regime, lab, date, confidence — предзаполняют `filtersStore` перед переходом.
- [ ] Обработать пустые/loading/error состояния (skeletons, empty states с CTA).

**Критерий приёмки:** ввод запроса в каждом из 5 режимов ведёт на корректный экран с проброшенными фильтрами; recent questions и saved views кликабельны и восстанавливают состояние; live-подсказки сущностей работают через MSW.

---

### 17.7 Экран Chat with Scientific Agent (§5.2.2, §14.3, Phase 5)

- [ ] Реализовать `src/features/chat/ChatPage.tsx` layout: список сообщений (scroll-area) + composer (RHF+Zod, submit по Enter, Shift+Enter=newline) + правая/нижняя область артефактов (graph/experiments/evidence/gaps).
- [ ] Реализовать создание/восстановление сессии: `POST /chat/sessions`, `GET /chat/sessions/{id}`, `POST /chat/sessions/{id}/messages`, затем подписка на `GET /chat/sessions/{id}/stream` через `useChatStream`.
- [ ] Реализовать **streaming answer**: инкрементальный рендер токенов через `react-markdown` + `remark-gfm` (таблицы, списки, код), typing-cursor во время стрима, автоскролл с «stick to bottom».
- [ ] Реализовать **tool-call timeline** (`src/features/chat/ToolTimeline.tsx`): визуализирует последовательность `tool_start`/`tool_end` со статусами и лейблами из §5.2.2 — `resolved entities`, `graph query`, `vector search`, `evidence check`, `gap scan`; каждый шаг раскрывается (args/summary/dataRef), с иконками статуса (pending/running/done/error) и таймингами (§17 SOTA #7 agent transparency).
- [ ] Сопоставить лейблы tool-timeline с реальными agent-tools §19 (`resolve_entities`→resolved entities, `run_cypher_template`→graph query, `hybrid_search`→vector search, `get_evidence`→evidence check, `build_graph_payload`→graph build, gap scan) для консистентных иконок/лейблов независимо от имени tool в потоке.
- [ ] Реализовать **inline citations**: маркеры `[n]` в тексте ответа кликабельны → открывают Evidence Inspector (drawer/side panel) для соответствующего `EvidenceRef`; hover показывает превью источника (документ, страница, snippet).
- [ ] Реализовать **unsupported-claim guardrail** (§18 mitigation «evidence inspector and unsupported-claim guardrails», Phase 5 acceptance «no numeric claim without evidence»): помечать числовые значения/утверждения в ответе без привязанной цитаты визуальным маркером-предупреждением и включать их в warning panel; клик ведёт к добавлению/проверке evidence.
- [ ] Реализовать **tabs ответа** (§5.2.2): `[Summary] [Experiments] [Evidence] [Graph] [Gaps] [Contradictions]`, наполняемые из соответствующих stream-событий (`graph`→Graph tab через embedded Reagraph snapshot, `table`→Experiments, `evidence`→Evidence, `gap`→Gaps; Contradictions = отфильтрованные edges с `contradicted=true`).
- [ ] Реализовать embedded graph snapshot в Graph tab (§17 SOTA #9): mini `KnowledgeGraphView` с кнопкой «Open in Graph Explorer» (передаёт `GraphResponse` в `graphStore` и переходит на `/graph`).
- [ ] Реализовать кнопки действий ответа (§5.2.2): `show graph`, `show experiments`, `show evidence`, `export report` (export report → генерация JSON/Markdown/CSV сводки ответа; см. 17.16).
- [ ] Реализовать **warning panel** (§5.2.2): агрегирует contradictions, low-confidence results (confidence ниже порога), missing data (gaps) и unsupported claims в единый предупреждающий блок с цветовой индикацией и переходами к деталям.
- [ ] Обработать состояния: stream error (событие `error`), отмена генерации (stop button, abort стрима), повтор запроса, пустая сессия.

**Критерий приёмки (Phase 5):** на сценарии из §5.2.2 (вопрос про Al-Cu aging 180C 2h) чат стримит ответ по токенам, tool-timeline показывает все 5 стадий, работают inline citations→evidence, ни одно числовое утверждение не остаётся без evidence (guardrail), переключаются все 6 tabs с корректным контентом, warning panel показывает contradictions/low-confidence/missing data, кнопка «show graph» открывает Graph Explorer с тем же графом; всё воспроизводимо на MSW-моках стрима.

---

### 17.8 Graph Explorer — Reagraph core, панели, интеракции, визуальные кодировки (§5.2.3, §14.2)

- [ ] Реализовать базовый компонент `src/components/graph/KnowledgeGraphView.tsx` на **Reagraph** `GraphCanvas` по эскизу §14.2: маппинг `GraphNode`/`GraphEdge` в reagraph nodes/edges с `data`, `labelType="all"`, `draggable`, `onNodeClick`/`onEdgeClick` пробрасывают `data` (наш domain-объект).
- [ ] Реализовать layout `src/features/graph-explorer/GraphExplorerPage.tsx` из §5.2.3 через resizable panels:
  - left sidebar: filters (GlobalFilters), graph query templates, saved views;
  - center: graph canvas;
  - right sidebar: selected entity/edge detail;
  - bottom drawer: evidence table / timeline / raw source snippets.
- [ ] Реализовать **визуальные кодировки** §5.2.3 через `graphEncoding.ts` (17.5), применённые к Reagraph node/edge стилям:
  - node color = entity type;
  - node size = evidenceCount / centrality;
  - edge thickness = evidenceCount;
  - edge opacity = confidence;
  - dashed edge = `inferred=true`;
  - red edge = `contradicted=true`;
  - hollow node = наличие `missingFields` (missing critical field);
  - lock icon overlay = `verified=true` (human-verified).
- [ ] Реализовать легенду (`GraphLegend`) с расшифровкой всех кодировок и toggle видимости каждой категории/типа.
- [ ] Реализовать интеракции §5.2.3:
  - click node → right panel details + кнопки expand one-hop / two-hop (`POST /graph/expand` или `GET /entities/{id}/neighbors?depth=`), merge новых nodes/edges в `graphStore` без сброса layout;
  - click edge → открыть Evidence Inspector в bottom drawer (`GET /evidence/by-edge/{edge_id}`); поддержать научные типы связей §2.1 (`IMPROVES`, `MEASURED_PROPERTY`, `PROCESSED_BY`, `SUPPORTED_BY`);
  - hover edge → tooltip: relation type, confidence, source count (evidenceCount);
  - hover node → tooltip: type, evidenceCount, verified/missingFields;
- [ ] Реализовать **lasso/box selection** (Reagraph `useSelection`) → панель действий над выделенным subgraph: «export subgraph» (JSON/PNG), «ask agent about selected subgraph» (собирает node ids и открывает чат с контекстом).
- [ ] Реализовать **path search** между двумя сущностями (Material↔Property и др.): UI выбора source/target + `POST /graph/path`, подсветка найденного пути в графе.
- [ ] Реализовать **graph diff** (§5.2.3): сравнение двух версий графа / before-after curation — цветовое выделение added/removed/changed nodes и edges; вход — два `GraphResponse` (например из версий или снапшотов). Вынести как переиспользуемый модуль `src/features/graph-explorer/graphDiff.ts` (используется и в Admin 17.15).
- [ ] Реализовать переключатель layout'ов (Reagraph `layoutType`: forceDirected2d, radial, hierarchical, circular) и центрирование/fit-to-screen, zoom controls, minimap toggle.
- [ ] Реализовать **graph query templates** (left sidebar): пресеты запросов (например `material_regime_property` из §6.2) с формой параметров (RHF+Zod) → `POST /graph/query`, результат (envelope summary/experiments/gaps/graph) в canvas; показывать `queryContext.generatedCypher` в раскрываемом блоке.
- [ ] Оптимизировать производительность для 1k–5k элементов (Phase 6 acceptance): виртуализация панелей, мемоизация node/edge маппинга, debounce обновлений, отключение тяжёлых лейблов при большом zoom-out.

**Критерий приёмки (Phase 6):** researcher может перейти chat answer → graph → evidence; граф остаётся usable на 1k–5k элементах (интерактив без заметных фризов); все 8 визуальных кодировок §5.2.3 видимы и корректны; click edge показывает source snippets; expand/lasso/path search/graph diff работают на MSW-моках.

---

### 17.9 Large-graph mode: Sigma.js + Graphology (§5.1, §10 Mode C)

- [ ] Реализовать `src/features/graph-explorer/LargeGraphView.tsx` на **Sigma.js** + **Graphology**: построение `Graphology` graph из `GraphResponse`, рендер через Sigma WebGL. Переключатель режима «Reagraph ↔ Sigma large-graph» в Graph Explorer.
- [ ] Реализовать применение визуальных кодировок §5.2.3 через Sigma node/edge reducers (color/size/thickness/opacity), с fallback-стилями для inferred/contradicted (Sigma custom edge programs).
- [ ] Реализовать layout через Graphology (`forceatlas2` в web worker, чтобы не блокировать UI) и camera API (zoom/pan/fit).
- [ ] Реализовать **graph minimap** и **cluster/community overview**: вычисление communities через `graphology-communities-louvain`, раскраска по сообществам, использование `layoutHints.communities` из `GraphResponse` при наличии.
- [ ] Реализовать панель **community summaries** (GraphRAG Mode C §10 / §17 SOTA #3): для broad-вопросов и corpus overview показывать текстовые сводки сообществ (из backend GraphRAG community summaries) рядом с cluster-раскраской; клик по community → фокус/фильтр подграфа.
- [ ] Реализовать **corpus overview** режим: быстрый large-graph preview всего корпуса (тысячи узлов) без React reconciliation — прямой Sigma рендер; порог автопереключения на Sigma при N узлов > threshold (конфигурируемо).
- [ ] Реализовать метрики через Graphology (degree, betweenness/centrality приблизительно) для node size = centrality (когда evidenceCount отсутствует).
- [ ] Обеспечить общий selection/tooltip/detail-panel контракт с Reagraph-режимом (переиспользовать right sidebar и bottom drawer).

**Критерий приёмки:** Sigma-режим рендерит граф в тысячи узлов/рёбер плавно (WebGL), forceatlas2 считается в worker без фриза UI, communities раскрашиваются и имеют текстовые summaries, minimap работает, автопереключение Reagraph→Sigma по порогу срабатывает; клик по узлу открывает тот же detail-panel, что и в Reagraph.

---

### 17.10 Cytoscape.js mode: layouts, export figures, algorithms (§5.1)

- [ ] Реализовать `src/features/graph-explorer/CytoscapeView.tsx` на **Cytoscape.js**: построение elements из `GraphResponse`, применение стилей §5.2.3, доступный как «advanced layout / export» режим.
- [ ] Подключить набор layout-расширений (`cose-bilkent`, `dagre`, `cola` при необходимости) для advanced layout experiments и dense subgraphs; UI-выбор layout.
- [ ] Реализовать **export graph figure** через Cytoscape (`cy.png({ scale, full })` и `cy.jpg`) высокого разрешения для публикаций/фигур — интегрировать в общий export (17.16).
- [ ] Реализовать прототипирование graph-алгоритмов в браузере (Cytoscape API): shortest path (`elements().dijkstra`/`aStar`), degree/pagerank, подсветка результатов — как «graph analysis mode».
- [ ] Обеспечить общий detail-panel/selection контракт с другими режимами.

**Критерий приёмки:** Cytoscape-режим переключается из Graph Explorer, минимум 3 layout'а работают на dense subgraph, high-res PNG export скачивается, shortest-path алгоритм подсвечивает путь; стили §5.2.3 применены.

---

### 17.11 Экран Entity Detail Page (§5.2.4)

- [ ] Реализовать `src/features/entity-detail/EntityDetailPage.tsx` (`/entity/:entityId`), данные из `GET /entities/{id}` + `GET /entities/{id}/neighbors`.
- [ ] Отобразить header сущности: canonical name, type + schema, confidence, review status (VerifiedLock), aliases (chips) с «unresolved aliases» секцией.
- [ ] Реализовать секцию **linked experiments** (таблица/список с переходом в Experiment Explorer).
- [ ] Реализовать секцию **linked documents/papers** (с переходом в Document Viewer 17.19 / Evidence Inspector).
- [ ] Реализовать секцию **properties and measured values** (для Material: composition range, measured hardness/tensile strength/corrosion; unit-aware отображение).
- [ ] Реализовать **timeline** сущности (появление/изменения/эксперименты по времени) через общий charts-модуль (ECharts/Observable Plot, 17.5).
- [ ] Реализовать секции **outgoing/incoming relations** (сгруппированные по типу связи; клик → mini-graph или переход в Graph Explorer c neighborhood expand).
- [ ] Реализовать **evidence list** сущности (переходы в Evidence Inspector).
- [ ] Реализовать **merge/split history** (decision history model §12.3): хронология merge/split операций (`CurationEvent`) с ссылками на решения.
- [ ] Отобразить ownership/lineage сущности (источник/лаборатория/происхождение) badge'ем (Phase 8, данные из metadata API 17.20 при наличии).
- [ ] Реализовать конкретный пример `Material: Al-Cu alloy 2024` (§5.2.4): composition range, related samples, treatments, measured properties, papers, labs, unresolved aliases — как reference-верстку/фикстуру.
- [ ] Кнопка «Show in Graph» открывает Graph Explorer с этой сущностью как root (`layoutHints.rootNodeIds`).

**Критерий приёмки:** для сущности из мока отображаются все секции §5.2.4 (canonical name, aliases, type/schema, linked experiments/documents, properties/values, timeline, in/out relations, evidence list, confidence/review, merge/split history); переходы в Graph Explorer, Experiment Explorer, Document Viewer и Evidence Inspector работают.

---

### 17.12 Экран Experiment Explorer (§5.2.5)

- [ ] Реализовать `src/features/experiment-explorer/ExperimentExplorerPage.tsx` (`/experiments`) — таблично-графовый интерфейс, данные из `GET /experiments` и `POST /experiments/query`.
- [ ] Реализовать панель фильтров (§5.2.5): material, processing operation, temperature, time, atmosphere, equipment, property — RHF+Zod, синхронизация в URL, отправка в `POST /experiments/query`.
- [ ] Реализовать **sortable table** (shadcn table + TanStack Table): колонки experiment/material/processing/property/value/unit/effect/confidence/evidence; сортировка, пагинация/виртуализация, per-row confidence badge и evidence link.
- [ ] Реализовать **graph projection** (§5.2.5): Experiment → Sample → Material → Regime → Property — mini-graph рядом с таблицей (Reagraph), синхронизированный с выбранной строкой.
- [ ] Реализовать **export CSV/JSON** отфильтрованного/выбранного набора экспериментов (см. 17.16).
- [ ] Реализовать действия **mark as verified / needs review** (по строке) → `POST /evidence/{id}/review` или curation endpoint; optimistic update + toast.
- [ ] Обработать пустые/loading/error состояния.

**Критерий приёмки:** таблица фильтруется по всем полям §5.2.5, сортируется, выбранная строка подсвечивает соответствующую цепочку Experiment→Sample→Material→Regime→Property в mini-graph, экспорт CSV/JSON скачивается, mark verified/needs-review обновляет статус.

---

### 17.13 Экран Evidence Inspector (§5.2.6)

- [ ] Реализовать `src/features/evidence-inspector/EvidenceInspector.tsx` — как полноэкранный маршрут `/evidence/:evidenceId` и как drawer/side-panel (переиспользуемый в Chat, Graph Explorer, Entity/Experiment экранах). Данные из `GET /evidence/{id}` и `GET /evidence/by-edge/{edge_id}`.
- [ ] Отобразить все поля доверия §5.2.6:
  - original document (viewer / ссылка на `GET /documents/{doc_id}/pages/{page}`, открытие в Document Viewer 17.19);
  - page number;
  - table id / figure id / paragraph id;
  - extracted statement;
  - source text snippet (с подсветкой span в контексте);
  - parsed structured object (JSON-виджет);
  - model/extractor (extractor/model version, §2.1);
  - confidence;
  - reviewer decision (кто подтвердил/исправил, §2.1);
  - graph edge, сгенерированное из этого evidence (ссылка → подсветка ребра в Graph Explorer).
- [ ] Реализовать document/page preview: рендер parsed-страницы (`GET /documents/{doc_id}/parsed`), скролл к нужной странице, подсветка table/figure/paragraph по id.
- [ ] Реализовать reviewer-действие: approve/reject/needs-review + комментарий (RHF+Zod) → `POST /evidence/{id}/review`; optimistic update, обновление review status в связанных местах.
- [ ] Реализовать навигацию «prev/next evidence» в рамках ребра/сущности.

**Критерий приёмки:** для evidence из мока показаны все поля §5.2.6 включая source snippet с подсветкой span, parsed structured object, extractor/model version, reviewer decision и ссылку на сгенерированное graph edge; reviewer decision сохраняется через review endpoint; открытие из чата (inline citation) и из Graph Explorer (click edge) ведёт в тот же инспектор.

---

### 17.14 Экран Gap Dashboard (§5.2.7, Phase 7)

- [ ] Реализовать `src/features/gap-dashboard/GapDashboardPage.tsx` (`/gaps`), данные из `GET /gaps`, `GET /gaps/matrix`, `POST /gaps/scan`.
- [ ] Реализовать **matrix heatmap** (§5.2.7) на ECharts (`heatmap` series): material × property и material × (regime→property) coverage; цвет = степень покрытия/кол-во измерений; клик по ячейке → drill-down (список экспериментов/gap-ов для пары).
- [ ] Реализовать **sankey diagram** material → regime → property (ECharts `sankey`): потоки покрытия, толщина = evidence/experiment count.
- [ ] Реализовать **timeline of experiment coverage** (charts-модуль 17.5): покрытие экспериментов во времени (по материалам/свойствам).
- [ ] Реализовать **ranked gap list** (§5.2.7) со ВСЕМИ типами gap из §11.1: `missing_property_value`, `missing_baseline`, `missing_processing_parameter`, `missing_equipment`, `missing_unit`, `unverified_claim`, `contradictory_measurements`, `low_coverage_material`, `orphan_entity`; для каждого типа — иконка/цвет, severity/rank, фильтр по типу, сортировка; клик → детали и переход в Graph Explorer (Gap как first-class node §17 SOTA #4 — hollow/gap-type styling).
- [ ] Реализовать запуск gap scan из UI: `POST /gaps/scan` с прогрессом (job) и обновлением дашборда по завершении.
- [ ] Реализовать связку «gap → chat»: кнопка «Discuss this gap» открывает чат с контекстом gap (для сценария «где пробелы по X?» из Phase 7).
- [ ] Обработать пустые/loading/error состояния и легенды для всех визуализаций.

**Критерий приёмки (Phase 7):** dashboard показывает material-property matrix heatmap, sankey material→regime→property, timeline покрытия и ranked gap list по всем 9 типам §11.1/§5.2.7; клик по ячейке/gap ведёт в Graph Explorer к navigable Gap-узлу; запуск gap scan обновляет данные; «Discuss this gap» открывает чат, который отвечает на «где пробелы по X?».

---

### 17.15 Экран Admin / Curation + pipeline/agent DAG на React Flow (§5.2.8, §12)

- [ ] Реализовать `src/features/admin/AdminPage.tsx` (`/admin`) с суб-табами: Review Queue, Entity Merge, Triple Review, Schema Terms, Ingestion Jobs, Pipeline Status, Graph Versions, Decision History.
- [ ] Реализовать **review queue** (§12.1): список pending items (evidence/triples/entities) с фильтрами, приоритетами и bulk-действиями; данные из curation endpoints. Отображать/фильтровать по причине постановки в очередь (§12.1: confidence<threshold, ambiguous entity resolution, claim contradicts existing, critical field missing, low-quality OCR value, new schema term).
- [ ] Реализовать **merge duplicate entities** (§5.2.8, §12.2): UI выбора двух+ сущностей, предпросмотр объединения (aliases/relations/evidence), подтверждение → `POST /entities/merge`; показ конфликтов.
- [ ] Реализовать **approve/reject extracted triples** (§12.2): карточка triple с source evidence, кнопки approve/reject/edit, запись в decision history (§12.3).
- [ ] Реализовать остальные curation-действия §12.2: **split entity**, **correct value/unit**, **add alias** (`POST /entities/{id}/aliases`), **mark relation as inferred**, **create manual evidence**, **annotate gap as known/irrelevant** — каждое с формой (RHF+Zod), optimistic update и записью `CurationEvent` (§12.3).
- [ ] Реализовать **edit schema terms** (§5.2.8): просмотр/редактирование schema-терминов (labels/relationship types) из `GET /graph/schema`.
- [ ] Реализовать **run ingestion jobs** (§5.2.8): форма запуска (`POST /ingest/jobs`), список jobs (`GET /ingest/jobs/{id}`), cancel (`POST /ingest/jobs/{id}/cancel`), live-прогресс через `useJobProgress`.
- [ ] Реализовать **monitor pipeline status**: **React Flow (`@xyflow/react`)** DAG ingestion/agent workflow (source→parse→chunk→extract→normalize→resolve→upsert→index, а также LangGraph agent nodes) — узлы со статусами/метриками, кликом раскрывают детали шага. Использовать React Flow строго для pipeline/agent DAG, не для KG (§5.1 таблица); авто-layout через **dagre/ELK.js** (§5.1: hierarchical layouts для lineage/pipeline/decision history).
- [ ] Реализовать **admin health/metrics** панель: `GET /admin/health`, `GET /admin/metrics` — статус сервисов, ключевые метрики (charts-модуль 17.5), обновление по интервалу.
- [ ] Реализовать **compare graph versions** (§5.2.8): выбор двух версий → graph diff (переиспользовать `graphDiff` из 17.8).
- [ ] Реализовать **decision history** viewer (§12.3 `CurationEvent`): хронология action/actor_id/target_type/target_id/before/after/reason/created_at с diff-просмотром before↔after и переходом к затронутому node/edge/evidence/schema.
- [ ] Добавить RBAC-гейтинг admin-маршрутов (скрывать/дизейблить для неадминов; согласовать с auth/session из §6.2 / 17.5).

**Критерий приёмки:** admin может просматривать review queue (с причинами очереди), мержить/сплитить сущности, approve/reject/edit триплы, добавлять alias, корректировать value/unit, помечать связь inferred, создавать manual evidence, аннотировать gap — с записью в decision history; запускать/отменять ingestion jobs с live-прогрессом; видеть pipeline/agent DAG на React Flow (dagre/ELK layout) со статусами узлов; видеть health/metrics; сравнивать версии графа (graph diff); просматривать decision history с before/after; admin-маршруты закрыты RBAC.

---

### 17.16 Saved views и экспорт PNG / JSON / CSV (§5.2, Phase 6)

- [ ] Реализовать **saved graph views**: сохранение текущего состояния Graph Explorer (nodes/edges snapshot или query + filters + layout + selection + visual settings) в `savedViewsStore` (+ backend persist при наличии endpoint); именование, список, загрузка, удаление; появление в Home и left sidebar.
- [ ] Реализовать **export PNG**: экспорт текущего canvas (Reagraph export API / Cytoscape `cy.png` для high-res / Sigma canvas capture) с выбором масштаба и фона.
- [ ] Реализовать **export JSON**: выгрузка `GraphResponse` (или выделенного subgraph) в JSON, включая `queryContext.generatedCypher`.
- [ ] Реализовать **export CSV**: табличная выгрузка (nodes CSV, edges CSV, experiments CSV, gaps CSV) — общий утилитарный модуль `src/lib/export/` c корректным экранированием.
- [ ] Реализовать **export report** из чата (§5.2.2): сборка Markdown/JSON отчёта из финального ответа (summary + experiments table + evidence citations + gaps + graph snapshot ref), скачивание файла.
- [ ] Написать unit-тесты сериализаторов export (JSON round-trip, CSV escaping).

**Критерий приёмки (Phase 6):** из Graph Explorer скачиваются PNG, JSON и CSV; saved views сохраняются/восстанавливаются (включая layout и фильтры) и видны на Home; export report из чата формирует корректный Markdown/JSON; тесты сериализаторов зелёные.

---

### 17.17 Тестирование, доступность, производительность, CI

- [ ] Настроить **unit/component тесты** (Vitest + React Testing Library) для: контракт-схем (17.3), стрим-парсера (17.4), graphEncoding (17.5), export-сериализаторов (17.16), ключевых компонентов (ToolTimeline, EvidenceInspector, GapDashboard heatmap data-mapping).
- [ ] Настроить **E2E тесты** (Playwright) на MSW-моках для главного сценария §23: Home → задать вопрос → чат стримит ответ с tool-timeline и tabs → «show graph» → Graph Explorer → click edge → Evidence Inspector; плюс сценарий «где пробелы по X?» → Gap Dashboard; плюс сценарий «добавление документа → ingestion job → обновление графа/coverage» (§23, 17.19).
- [ ] Обеспечить **accessibility**: прогон `jsx-a11y` линта и axe-проверок в E2E для ключевых экранов; keyboard-навигация command palette, tabs, table, dialogs; ARIA для графовых canvas (текстовые альтернативы/summary).
- [ ] Настроить **performance-бюджет и проверку**: измерить интерактивность Graph Explorer на 1k–5k элементов (Phase 6), Sigma на тысячах узлов; добавить проверку размера бандла (code-splitting по маршрутам, lazy-load тяжёлых graph-режимов Sigma/Cytoscape/react-force-graph/ECharts).
- [ ] Настроить **CI** (`.github/workflows` или общий mono-repo CI): `typecheck`, `lint`, `test`, `build` для `apps/frontend` на каждый PR; артефакт production-бандла.
- [ ] Написать `apps/frontend/README.md`: запуск dev/build/test, переменные окружения, режимы графа (Reagraph/Sigma/Cytoscape/3D), маппинг экранов §5.2 → маршруты, работа с MSW-моками.

**Критерий приёмки:** `pnpm --filter frontend test` (unit) и Playwright E2E главного сценария §23 зелёные на MSW; axe не выдаёт критичных нарушений на ключевых экранах; CI выполняет typecheck/lint/test/build на PR; тяжёлые graph-режимы загружаются lazy; README покрывает запуск и режимы.

---

### 17.18 3D / force-graph wow-mode (react-force-graph) (§5.1, §22)

- [ ] Реализовать `src/features/graph-explorer/ForceGraph3DView.tsx` на **react-force-graph** (2D/3D): построение из `GraphResponse`, node color/size и link styling по §5.2.3, доступный как «3D / wow» режим Graph Explorer.
- [ ] Добавить в переключатель режимов Graph Explorer вариант «3D» (полный набор: «Reagraph ↔ Sigma ↔ Cytoscape ↔ 3D») с единым selection/detail-panel контрактом (right sidebar / bottom drawer).
- [ ] Реализовать 3D-интеракции: click node → detail panel, hover → tooltip, zoom/pan/rotate, focus/fit-to-node; graceful fallback на 2D для слабых устройств.
- [ ] Обеспечить **lazy-загрузку** тяжёлого 3D-рендерера только при активации режима (code-splitting, согласовано с perf-бюджетом 17.17).

**Критерий приёмки:** 3D-режим переключается из Graph Explorer, рендерит тот же `GraphResponse`, применяет кодировки §5.2.3, click/hover открывают общий detail-panel; 3D-бандл грузится lazy и не входит в основной чанк.

---

### 17.19 Document Viewer и upload (§5.2.1 Document mode, §6.2 documents/*, §23)

- [ ] Реализовать маршрут `/document/:docId` и `src/features/document/DocumentViewer.tsx`: рендер parsed-документа (`GET /documents/{doc_id}/parsed`), постранично (`GET /documents/{doc_id}/pages/{page}`), с подсветкой table/figure/paragraph по id (общий рендер-компонент с Evidence Inspector 17.13).
- [ ] Отобразить метаданные документа (`GET /documents/{doc_id}`): источник, число страниц, статус парсинга, extractor/model version, owner/lab (при наличии metadata API 17.20).
- [ ] Реализовать **upload документа** (`POST /documents/upload`) с прогрессом, затем запуск ingestion job (`POST /ingest/jobs`) + live-прогресс через `useJobProgress`; по завершении — инвалидация TanStack Query кэшей графа/индексов/coverage (§23: «добавление нового документа обновляет граф, индексы и coverage dashboards»).
- [ ] Реализовать **reindex** документа (`POST /documents/{doc_id}/reindex`) с прогрессом.
- [ ] Связать Home `Document`-режим (17.6) с этим маршрутом; обеспечить переходы из Evidence Inspector (original document) и Entity Detail (linked documents).

**Критерий приёмки:** документ открывается по `/document/:docId` с постраничным parsed-просмотром и подсветкой table/figure/paragraph; upload запускает ingestion job с live-прогрессом и по завершении инвалидирует кэши графа/coverage; reindex доступен; переходы из Home/Evidence/Entity ведут в viewer.

---

### 17.20 Admin: metadata, lineage, governance, audit (Phase 8)

- [ ] Реализовать в Admin (17.15) под-таб **Source / Dataset Catalog**: список источников/датасетов/документов с owner/lab, статусом и датой (данные из metadata-сервиса DataHub/OpenMetadata через backend; Phase 8).
- [ ] Реализовать **lineage view** ingestion (source→parse→chunk→extract→normalize→resolve→upsert→index) с owner/lab и трассировкой прогонов Dagster; переиспользовать React Flow/dagre DAG (17.15).
- [ ] Реализовать **audit log** viewer (§6.2 audit logs, Phase 8): фильтруемый журнал действий (кто/что/когда), корреляция с `CurationEvent` (17.15).
- [ ] Отображать ownership/lineage прямо на Entity Detail (17.11) и Document Viewer (17.19): badge источника/владельца/происхождения.

**Критерий приёмки (Phase 8):** admin видит каталог источников/датасетов с owner/lineage, lineage-граф ingestion с трассируемыми прогонами Dagster, audit log действий; у каждого документа/источника показаны owner и lineage; данные приходят через backend metadata API (при отключённом DataHub для MVP — из MSW-моков).

---

**Критерий приёмки раздела 17 (итог):** реализованы все 8 экранов §5.2 (Home/Search, Chat with Agent, Graph Explorer, Entity Detail, Experiment Explorer, Evidence Inspector, Gap Dashboard, Admin/Curation) плюс Document Viewer на стеке §5.1/§14.1; Reagraph — основной graph UI с полным набором визуальных кодировок и интеракций §5.2.3; подключены режимы Sigma.js+Graphology (large graph + community summaries), Cytoscape.js (layout/export), react-force-graph (3D), ECharts/Observable Plot (аналитика), React Flow (pipeline/agent DAG, dagre/ELK layout); контракты §5.3 (`GraphResponse`, `ChatStreamEvent`) и envelope `POST /graph/query` §6.2 реализованы 1:1 с Zod-валидацией; работает SSE/WebSocket streaming чата и job-progress; действует unsupported-claim guardrail (нет числа без evidence); работают saved views и export PNG/JSON/CSV; curation-петля §12 (merge/split/alias/correct/inferred/manual-evidence/annotate-gap + decision history) и Phase 8 metadata/lineage/audit доступны в admin UI; все OSS-репозитории §22 склонированы в `third_party/frontend/`; проходят frontend-части фаз 5–8 §16 и сквозной сценарий §23 на E2E.
</content>
</invoke>


---


## 18. Observability и evaluation

Раздел покрывает §15 (Evaluation plan) и observability из roadmap Phase 9. Цель: полная наблюдаемость (structured logging, distributed tracing агента через OpenTelemetry + LangSmith, метрики системы через Prometheus/Grafana), полноценный трекинг ML-прогонов в MLflow (extraction/retrieval/answer runs), и воспроизводимый evaluation harness с golden dataset (50–100 вопросов, §15.1), метриками retrieval/answer/system (§15.2) и автоматическим eval loop (§15.3) с детерминированными числовыми и цитатными проверками, RAGAS и DeepEval.

Затрагиваемые сервисы/пакеты (§6.1): `packages/kg_eval/` (главный evaluation harness), `packages/kg_common/` (logging, tracing, cost accounting), `apps/agent-service/`, `apps/api-gateway/`, `apps/ingestion-service/`, `apps/extraction-service/`, `apps/search-service/`, `apps/graph-service/`, `apps/curation-service/`, `apps/frontend/`, `infra/docker-compose.yml`, `infra/dagster/`, новый `infra/observability/`.

OSS для клонирования/вендоринга (в `third_party/`): MLflow `https://github.com/mlflow/mlflow` (§22), RAGAS `https://github.com/explodinggradients/ragas`, DeepEval `https://github.com/confident-ai/deepeval`, OpenTelemetry Python `https://github.com/open-telemetry/opentelemetry-python`.

Зависимости от других разделов: агент и `tool_trace`/nodes (§7), ingestion/extraction (§9), retrieval (§10), gap analysis (§11), contradiction detection (§17.5), curation loop (§12), admin endpoints `GET /api/v1/admin/health`, `GET /api/v1/admin/metrics` (§6.2), evidence-first model и `EvidenceRef` (§7.3, §8.3), Python-пакеты `opentelemetry-sdk`, `mlflow`, `ragas`, `deepeval`, `structlog` (§13.2).

### 18.0 Vendoring OSS и базовые зависимости

- [ ] Склонировать/вендорить репозитории в `third_party/` с фиксацией commit SHA в `third_party/VERSIONS.lock`:
  - [ ] `git clone https://github.com/mlflow/mlflow third_party/mlflow`;
  - [ ] `git clone https://github.com/explodinggradients/ragas third_party/ragas`;
  - [ ] `git clone https://github.com/confident-ai/deepeval third_party/deepeval`;
  - [ ] `git clone https://github.com/open-telemetry/opentelemetry-python third_party/opentelemetry-python` (как справочник для инструментирования).
- [ ] Добавить в pin-файл зависимостей (`packages/kg_common/pyproject.toml` и корневой lock) точные версии: `mlflow`, `ragas`, `deepeval`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-httpx`, `opentelemetry-instrumentation-logging`, `structlog`, `langsmith`, `prometheus-client`, `dvc` (§22, снапшоты golden dataset).
- [ ] Создать пакет `packages/kg_eval/` со структурой: `datasets/`, `metrics/`, `runners/`, `checks/`, `reports/`, `cli.py`, `pyproject.toml`; зарегистрировать console-script `kg-eval`.
- [ ] Документировать в `packages/kg_eval/README.md` карту «метрика → модуль → критерий приёмки из §15.2».

**Критерий приёмки:** `pip install -e packages/kg_eval` проходит без ошибок; `python -c "import mlflow, ragas, deepeval, opentelemetry"` успешен; `kg-eval --help` печатает список подкоманд (`run`, `traces`, `report`, `regression-gate`); `third_party/VERSIONS.lock` содержит SHA всех четырёх репозиториев.

### 18.1 Structured logging (structlog) и корреляция запросов

- [x] В `packages/kg_common/logging.py` реализовать конфигурацию `structlog` с JSON-рендерером, единой схемой полей: `ts`, `level`, `service`, `env`, `event`, `session_id`, `user_id`, `request_id`, `trace_id`, `span_id`, `job_id`.
- [x] Реализовать `contextvars`-контекст (`bind_request_context()`) для проброса `request_id`/`session_id`/`trace_id` во все логи внутри одного запроса без явной передачи.
- [x] Добавить FastAPI middleware в `apps/api-gateway/` и `apps/agent-service/`, который генерирует/принимает `X-Request-ID`, кладёт его в контекст и возвращает в response headers.
- [x] Подключить `structlog` во все backend-сервисы (`api-gateway`, `agent-service`, `ingestion-service`, `extraction-service`, `graph-service`, `search-service`, `curation-service`) через общий `kg_common.logging.configure()`.
- [x] Гарантировать, что `trace_id`/`span_id` из активного OpenTelemetry-спана автоматически инжектятся в каждую log-запись (log-trace correlation).
- [x] Настроить уровни логирования из env (`LOG_LEVEL`, `LOG_FORMAT=json|console`) через `pydantic-settings`.
- [x] Реализовать структурированный audit-log (§6.2 «audit logs», §5.2.8 monitor/curation): отдельный logger/sink для security- и curation-значимых действий (login, `POST /entities/merge`, alias add, schema change, `POST /evidence/{id}/review` decision, запуск/отмена ingest job) с полями `actor_id`, `action`, `target_type`, `target_id`, `before`/`after` diff, `result`, `request_id`; писать в таблицу Postgres `audit_log` + JSON-лог, синхронно с `CurationEvent` (§12.3), не смешивая с debug-логами.
- [x] Определить транспорт логов: все сервисы пишут JSON в stdout; docker-compose logging + OTel Collector (18.2) собирают их и отправляют в Loki (18.5); обеспечить переход logs↔traces по `trace_id`/`request_id` в Grafana.

**Критерий приёмки:** запрос к любому endpoint порождает JSON-логи, где по одному `request_id` можно проследить цепочку `api-gateway → agent-service → graph/search-service`; каждая запись содержит непустые `trace_id`/`span_id`, совпадающие со спаном в трейсере; curation-действие (merge/review) порождает запись в `audit_log` с before/after diff.

### 18.2 OpenTelemetry distributed tracing (инфраструктура и инструментирование)

- [x] В `packages/kg_common/tracing.py` реализовать `init_tracing(service_name)`: настройка `TracerProvider`, `Resource` (service.name, service.version, deployment.environment), OTLP-exporter (gRPC на collector), sampler (`parentbased_traceidratio`, ratio из env).
- [x] Развернуть OpenTelemetry Collector в `infra/observability/otel-collector-config.yaml` и добавить сервис `otel-collector` в `infra/docker-compose.yml` (receivers OTLP grpc/http, exporters в трейс-бэкенд и Prometheus).
- [x] Добавить в `otel-collector-config.yaml` logs-pipeline (OTLP logs receiver → exporter в Loki, 18.5) и `tail_sampling`-processor (100% трейсов с ошибкой/высокой латентностью, сэмплирование остальных) для контроля объёма.
- [x] Добавить трейс-бэкенд (Jaeger `all-in-one` или Grafana Tempo) сервисом в `infra/docker-compose.yml` с портом UI и persistent volume.
- [x] Инструментировать FastAPI (`opentelemetry-instrumentation-fastapi`) во всех API-сервисах — авто-спаны на каждый HTTP-запрос.
- [x] Инструментировать исходящие вызовы: `httpx`/`requests` (`opentelemetry-instrumentation-httpx`), Neo4j-драйвер (спаны на Cypher с атрибутом `db.statement.template`), Qdrant-client, `opensearch-py` — ручные спаны в `apps/search-service/` и `apps/graph-service/`.
- [x] Инструментировать Dagster-ассеты/ops ingestion-пайплайна (§9.1) OTel-спанами по шагам (parse→chunk→extract→normalize→ER→validate→upsert→index→gap→eval) в `apps/ingestion-service/`/`infra/dagster/`; связать `job_id` из логов (18.1) с `trace_id` и эмитить метрику `ingestion_throughput_docs_per_min` (18.5).
- [x] Обеспечить W3C `traceparent` propagation между сервисами (заголовки прокидываются через API Gateway → agent-service → downstream).
- [x] Добавить span-атрибуты домена: `kg.intent`, `kg.retrieval_mode`, `kg.entity_count`, `kg.evidence_count`, `kg.cypher_template`, `kg.confidence_min`.

**Критерий приёмки:** одиночный chat-запрос виден в UI трейс-бэкенда как единый trace с вложенными спанами по сервисам и по Cypher/vector/keyword вызовам; propagation работает (нет «обрезанных» трейсов); атрибуты домена присутствуют на спанах.

### 18.3 Трейсинг агента: LangGraph + LangSmith / OpenTelemetry

- [ ] Реализовать конфиг переключения провайдера трейсинга агента в `apps/agent-service/config.py`: `AGENT_TRACING=langsmith|otel|both` (env `LANGSMITH_API_KEY`, `LANGCHAIN_TRACING_V2`, `LANGCHAIN_PROJECT`).
- [ ] Включить LangSmith-трейсинг LangGraph-графа (§7.2): каждый прогон графа = один trace, каждый node (`preprocess_question`, `intent_classifier`, `entity_resolver`, `query_planner`, `structured_retrieval`, `hybrid_retrieval`, `gap_analyzer`, `verifier`, `answer_synthesizer` и др., §7.5) = отдельный run/span.
- [ ] Реализовать OTel-обёртку узлов графа (`@traced_node`) в `apps/agent-service/tracing.py`: каждый node оборачивается в спан с именем node и атрибутами входа/выхода (размеры state-полей, а не полный текст, для PII-safety).
- [ ] Инструментировать каждый tool из `TOOLS` (§7.4: `resolve_entities`, `run_cypher_template`, `hybrid_search`, `get_evidence_by_ids`, `scan_gaps`, `detect_contradictions` и т.д.) как child-спан с атрибутами `tool.name`, `tool.latency_ms`, `tool.status`, `tool.result_size`.
- [ ] Синхронизировать поле state `tool_trace` (§7.3) с реальными спанами: `tool_trace[i]` содержит `span_id`/`trace_id`, чтобы UI Agent Transparency (§17.7) мог линковать шаги на трейс.
- [ ] Прокидывать `trace_id` в SSE/WebSocket stream событий чата (contract §5.3) отдельным event-типом `trace`, чтобы фронтенд показывал ссылку «open trace».
- [ ] Логировать LLM-вызовы внутри узлов с атрибутами `llm.model`, `llm.prompt_tokens`, `llm.completion_tokens`, `llm.latency_ms` (основа для cost-метрик, см. 18.10).
- [ ] Реализовать подкоманду `kg-eval traces <question_id>` (из списка подкоманд 18.0): по прогону golden-вопроса печатать дерево спанов node→tool→LLM и прямые ссылки на trace в LangSmith/трейс-бэкенде (из MLflow-tag `trace_id`/`langsmith_run_url`, 18.4).
- [ ] В `apps/frontend/` обработать SSE-event `trace` (§5.3): в chat и панели Agent Transparency (§17.7 «Agent transparency») показывать кнопку «open trace» со ссылкой на LangSmith/трейс-бэкенд по `trace_id`, линкуя каждый шаг `tool_trace` на соответствующий спан.

**Критерий приёмки:** прогон одного вопроса golden-набора отображается в LangSmith (и/или трейс-бэкенде) как дерево node→tool→LLM; поле `tool_trace` в финальном state содержит `span_id` для каждого шага; переключение `AGENT_TRACING` между `langsmith`/`otel` не ломает работу графа; `kg-eval traces <id>` печатает дерево спанов со ссылкой на trace; во фронтенде работает «open trace».

### 18.4 MLflow tracking server и трекинг extraction/retrieval/answer runs

- [ ] Развернуть MLflow tracking server сервисом `mlflow` в `infra/docker-compose.yml`: backend store в `postgres` (schema `mlflow`), artifact store в `minio` (S3-совместимый bucket `mlflow-artifacts`), порт UI `5000`.
- [ ] В `packages/kg_common/mlflow_utils.py` реализовать хелперы: `start_run(experiment, run_type, tags)`, `log_params`, `log_metrics`, `log_artifact_json`, авто-тег `git_sha`, `dataset_version`, `model_id`.
- [ ] Создать три MLflow experiments: `extraction`, `retrieval`, `answer` (константы в `packages/kg_eval/mlflow_experiments.py`).
- [ ] Инструментировать extraction runs (`apps/extraction-service/`, §9 Step 4): логировать params (schema-версия, LLM-модель, chunk-стратегия), metrics (extraction precision/recall на аннотированном подмножестве, avg confidence, cost per document), artifacts (примеры извлечённых триплетов с source spans).
- [ ] Реализовать модуль метрик `packages/kg_eval/metrics/extraction.py`: extraction precision/recall и avg confidence на аннотированном подмножестве, доля measurements без evidence (должна быть 0, §8.3 «no source span → no graph fact»), доля документов с полезными фактами (acceptance Phase 2 «≥70% docs дают полезные факты»); подключить к experiment `extraction` и суите `extraction` (18.11).
- [ ] Инструментировать retrieval runs (`apps/search-service/`, `packages/kg_retrievers/`, §10): логировать веса hybrid-формулы (§10.2: dense 0.35 / sparse 0.25 / bm25 0.20 / graph 0.10 / evidence 0.10), reranker-конфиг, metrics (Recall@10, MRR — см. 18.7).
- [ ] Инструментировать answer runs (`apps/agent-service/`): логировать intent-распределение, metrics answer-quality (citation precision, unsupported claim rate и т.д. — см. 18.8), artifact — полный QA-отчёт по golden-набору.
- [ ] Реализовать связку MLflow run ↔ trace: в каждый run писать tag `trace_id`/`langsmith_run_url` для перехода из метрик в трейс.

**Критерий приёмки:** после `kg-eval run --suite golden` в MLflow UI видны три experiments с run-ами; каждый run содержит params, метрики §15.2 и артефакт-отчёт; run помечен `git_sha` и `dataset_version`; из run открывается связанный trace.

### 18.5 System-метрики: Prometheus, Grafana и admin endpoints

- [ ] Подключить `prometheus-client` в `packages/kg_common/metrics.py`: реестр метрик, декоратор `@measure_latency`, счётчики/гистограммы с лейблами `service`, `endpoint`, `intent`, `retrieval_mode`.
- [ ] Экспонировать `/metrics` (Prometheus format) на каждом backend-сервисе и реализовать агрегирующий `GET /api/v1/admin/metrics` (§6.2) с JSON-сводкой ключевых метрик.
- [ ] Реализовать `GET /api/v1/admin/health` (§6.2): проверка доступности Neo4j, Qdrant, OpenSearch, Postgres, Redis, MinIO, MLflow, Docling Serve, Dagster и трейс-бэкенда (§13.1 полный список сервисов) с per-dependency статусом и общим `status: healthy|degraded|down`.
- [ ] Определить и экспортировать system-метрики (§15.2): `ingestion_throughput_docs_per_min`, `chat_latency_seconds` (histogram), `graph_query_latency_seconds` (histogram), `extraction_cost_usd_per_document`, `reviewer_corrections_per_100_extractions`.
- [ ] Добавить сервисы `prometheus` (scrape-config `infra/observability/prometheus.yml`, retention + persistent volume) и `grafana` (provisioning в `infra/observability/grafana/`) в `infra/docker-compose.yml`.
- [ ] Добавить сервис `loki` (log aggregation) в `infra/docker-compose.yml` с persistent volume и retention; подключить Loki datasource в Grafana и настроить derived fields для перехода logs↔traces по `trace_id` (Grafana Explore), замыкая log-trace correlation из 18.1/18.2.
- [ ] Собрать Grafana-дашборды (JSON provisioning): «System Overview» (latency p50/p95/p99, throughput, error rate, health), «Ingestion Pipeline» (§5.2.8 monitor pipeline status: `ingestion_throughput_docs_per_min`, статус/длительность Dagster-шагов), «Retrieval & Answer Quality» (метрики §15.2 из Prometheus push/exporter), «Cost» (LLM cost per doc / per query), «Curation» (reviewer corrections).
- [ ] Настроить alert-rules в Prometheus/Grafana: chat p95 latency > SLO, error rate > порога, health degraded, unsupported-claim-rate > 0 на golden.

**Критерий приёмки:** `GET /api/v1/admin/health` возвращает статус всех зависимостей; `GET /api/v1/admin/metrics` и `/metrics` отдают метрики §15.2; Grafana показывает 4 дашборда с реальными данными после нагрузочного прогона; alert срабатывает при принудительном отключении Neo4j.

### 18.6 Golden dataset (§15.1)

- [ ] Определить YAML-схему одного вопроса в `packages/kg_eval/datasets/schema.py` (Pydantic) строго по §15.1: `question`, `expected_entities` (material/processing/property), `expected_answer_contains`, `must_not_contain`, `required_graph_nodes`, плюс служебные `id`, `category`, `language`, `expected_numeric` (значение+unit+tolerance), `expected_citations` (evidence_ids/doc_ids), `expected_gaps`, `expected_contradictions`.
- [ ] Собрать 50–100 вопросов в `packages/kg_eval/datasets/golden/*.yaml` строго по категориям и квотам §15.1:
  - [ ] 20 material-regime-property questions;
  - [ ] 15 experiment lookup questions;
  - [ ] 10 evidence questions;
  - [ ] 10 gap questions;
  - [ ] 10 contradiction questions;
  - [ ] 10 broad literature summary questions.
- [ ] Включить не менее эталонного примера из §15.1 (Al-Cu, aging 180C 2h, hardness) с полным заполнением `expected_*` полей.
- [ ] Обеспечить двуязычность (`ru`/`en`) выборки вопросов (соответствует `language` в state, §7.3).
- [ ] Реализовать loader+validator `kg_eval.datasets.load_golden()` с проверкой соответствия схеме, уникальности `id`, покрытия всех категорий и квот; фейлить CI при нарушении.
- [ ] Версионировать golden dataset: `dataset_version` (semver) в манифесте `datasets/golden/manifest.yaml`, привязка к git-тегу; хранить снапшоты через DVC (§22) при необходимости.
- [ ] Написать guideline `packages/kg_eval/datasets/ANNOTATION.md` по составлению эталонных ответов (как проставлять `expected_numeric`, evidence_ids, gap/contradiction ожидания).

**Критерий приёмки:** `kg_eval.datasets.load_golden()` загружает ≥50 вопросов, валидатор подтверждает точное покрытие квот §15.1 (20/15/10/10/10/10) и уникальность id; манифест содержит `dataset_version`; эталонный Al-Cu пример присутствует и валиден.

### 18.7 Retrieval-метрики (§15.2)

- [ ] Реализовать `Recall@10` для evidence в `packages/kg_eval/metrics/retrieval.py`: доля golden-вопросов, где ≥1 ожидаемый evidence_id входит в top-10 hybrid-retrieval (§10.2).
- [ ] Реализовать `MRR` для релевантных экспериментов: mean reciprocal rank первого релевантного experiment по `expected_entities`.
- [ ] Реализовать Entity Resolution precision/recall: сравнение выхода `entity_resolver` (§7.5 Node 3) / Splink-пайплайна (§9 Step 6) с `expected_entities` на аннотированном наборе; отдельно precision (нет ложных склеек) и recall (все ожидаемые сущности найдены).
- [ ] Реализовать graph path correctness: для structured-вопросов проверять, что путь из `run_cypher_template` содержит `required_graph_nodes` (Material→ProcessingRegime→Measurement→Evidence, §15.1) в правильном порядке и с правильными типами рёбер.
- [ ] Реализовать harness прогона retrieval-метрик через реальный `apps/search-service`/`graph-service` (не моки) с фикс-сидом и логированием в MLflow experiment `retrieval`.
- [ ] Задать целевые пороги (baseline) для каждой метрики в `packages/kg_eval/thresholds.yaml` и подключить к regression-gate (18.12).

**Критерий приёмки:** `kg-eval run --suite retrieval` вычисляет Recall@10, MRR, ER precision/recall, graph path correctness по golden-набору, пишет их в MLflow и в JSON-отчёт; значения детерминированы (повтор даёт те же числа при фикс-сиде).

### 18.8 Answer-quality метрики (§15.2)

- [ ] Реализовать `citation precision` в `packages/kg_eval/metrics/answer.py`: доля цитат в ответе (`citations`/`evidence_ids`), реально подтверждающих связанное утверждение (сверка с evidence spans, §8.3).
- [ ] Реализовать `unsupported claim rate`: доля утверждений ответа без привязанного evidence_ref — детерминированный парсинг ответа на claims + сопоставление с `evidence` (§7.3), опора на verifier (§7.5 Node 9).
- [ ] Реализовать `numeric accuracy`: извлечь численные значения из ответа, сопоставить с `expected_numeric` из golden с учётом tolerance; несовпадение значения = ошибка.
- [ ] Реализовать `unit accuracy`: нормализовать единицы через `pint` (§13.2, §9 Step 5) и сверить с ожидаемыми; штрафовать смешение единиц (verifier-правило «единицы не смешаны», §7.5 Node 9).
- [ ] Реализовать `contradiction detection recall`: доля golden contradiction-вопросов, где агент явно пометил contradiction (сверка с `expected_contradictions`, §17.5).
- [ ] Реализовать `gap detection precision`: доля обнаруженных gap, реально присутствующих в `expected_gaps` (типы gap из §11.1 / §7.5 Node 8).
- [ ] Логировать все answer-метрики в MLflow experiment `answer` и в JSON-отчёт с разбивкой по категориям §15.1.

**Критерий приёмки:** `kg-eval run --suite answer` считает все 6 answer-метрик; `unsupported claim rate == 0` на golden-наборе (соответствует acceptance Phase 9 «no unsupported answer claims in golden set»); numeric/unit accuracy рассчитаны детерминированно через pint.

### 18.9 RAG-проверки через RAGAS и DeepEval

- [ ] Реализовать адаптер `packages/kg_eval/runners/ragas_runner.py`: преобразование golden-вопросов и выходов агента в RAGAS-формат (`question`, `answer`, `contexts`, `ground_truth`).
- [ ] Подключить метрики RAGAS: `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`, `answer_correctness`; логировать в MLflow experiment `answer`.
- [ ] Реализовать адаптер `packages/kg_eval/runners/deepeval_runner.py`: маппинг на DeepEval `LLMTestCase`.
- [ ] Подключить DeepEval-метрики: `FaithfulnessMetric`, `AnswerRelevancyMetric`, `ContextualPrecisionMetric`, `HallucinationMetric` + кастомная `GEval`-метрика «citation groundedness» под evidence-first модель.
- [ ] Настроить LLM-judge провайдера для RAGAS/DeepEval через конфиг (без хардкода ключей), с фиксацией judge-модели в MLflow tags для воспроизводимости.
- [ ] Написать pytest-набор `packages/kg_eval/tests/test_deepeval_suite.py`, где DeepEval-ассерты (`assert_test`) фейлят при падении ниже порогов из `thresholds.yaml`.

**Критерий приёмки:** `kg-eval run --suite ragas` и `pytest packages/kg_eval/tests/test_deepeval_suite.py` выполняются на golden-наборе, пишут RAGAS/DeepEval-метрики в MLflow; judge-модель зафиксирована в tags; пороговые ассерты DeepEval работают как gate.

### 18.10 Детерминированные numeric/citation checks и cost accounting (§15.3)

- [ ] Реализовать в `packages/kg_eval/checks/numeric_check.py` детерминированную проверку: regex/parser числовых значений + единиц из ответа, нормализация `pint`, сравнение с evidence-значением из графа (Measurement, §8) — не LLM, чистая логика.
- [ ] Реализовать `packages/kg_eval/checks/citation_check.py`: каждая численная/фактическая claim должна ссылаться на существующий `evidence_id`, который резолвится через `get_evidence_by_ids` (§7.4) и указывает на реальный source span (`doc_id`/`page`/`span_start`/`span_end`, §7.3).
- [ ] Реализовать проверку «нет фантомных цитат»: все `citations` в ответе существуют в графе; несуществующий evidence_id = hard fail.
- [ ] Реализовать `packages/kg_common/cost.py`: аккумуляция token-usage из LLM-вызовов (18.3), расчёт `cost_usd` по прайсингу моделей (конфиг цен), агрегация в `extraction_cost_usd_per_document` и `answer_cost_usd_per_query`; экспорт в Prometheus (18.5) и MLflow.
- [ ] Реализовать `reviewer_corrections_per_100_extractions`: считать из событий curation-service (§12.3 decision history) — accepted/rejected/merged/split на 100 извлечений.
- [ ] Обеспечить, что все детерминированные checks не зависят от LLM и дают идентичный результат при повторе (unit-тесты в `packages/kg_eval/tests/test_checks.py`).

**Критерий приёмки:** numeric и citation checks запускаются офлайн без вызовов LLM и детерминированы; фантомная цитата и неверное числовое значение приводят к hard fail; cost per document/query и reviewer corrections per 100 доступны в метриках; unit-тесты checks проходят.

### 18.11 Автоматический eval loop, отчёты и regression-gate (§15.3)

- [ ] Реализовать оркестратор `kg-eval run --suite {golden|retrieval|answer|extraction|ragas|all}` в `packages/kg_eval/runners/orchestrator.py`: прогон всех вопросов через реальный агент, сбор extraction/retrieval/answer/RAGAS/deterministic метрик, запись в MLflow (18.4) и генерация отчёта.
- [ ] Реализовать генератор отчёта `kg-eval report`: Markdown + HTML в `packages/kg_eval/reports/out/` со сводкой по категориям §15.1, всеми метриками §15.2, diff к предыдущему `dataset_version`/`git_sha`.
- [ ] Реализовать `kg-eval regression-gate`: сравнение текущих метрик с baseline из `thresholds.yaml`; exit code ≠ 0 при регрессии любой метрики §15.2 (падение Recall@10/MRR/ER precision-recall/graph path correctness/citation precision/numeric-unit accuracy/contradiction recall/gap precision/RAGAS faithfulness, рост unsupported claim rate).
- [ ] Встроить шаг «Retrieval eval» (§9.1, узел EVAL после INDEX) в Dagster ingestion-пайплайн (`infra/dagster/`): после индексации новых документов прогонять retrieval-метрики (18.7) на затронутом подмножестве, логировать в MLflow experiment `retrieval`; регрессия ниже baseline создаёт alert (18.5).
- [ ] Интегрировать в CI (`.github/workflows/eval.yml` или аналог): на PR запускать быстрый sub-suite (smoke, ~10 вопросов), на merge в main — полный `--suite all` с regression-gate.
- [ ] Настроить в `infra/dagster/` расписанный job `nightly_eval` (§22 Dagster): ночной полный прогон golden-набора, публикация метрик в MLflow и Grafana, уведомление при регрессии.
- [ ] Обеспечить воспроизводимость (acceptance Phase 9 «reproducible benchmark»): фикс сидов, pin версий моделей и `dataset_version`, запись всех входных параметров в MLflow run.
- [ ] Задокументировать запуск eval-harness и чтение отчётов в `packages/kg_eval/README.md` (команды, интерпретация метрик, обновление baseline).

**Критерий приёмки:** `kg-eval run --suite all` выполняет полный прогон golden-набора, пишет метрики §15.2 в MLflow и генерирует Markdown/HTML-отчёт; `regression-gate` фейлит при искусственном ухудшении метрики; nightly Dagster-job и CI-workflow настроены; повторный прогон при тех же входах даёт идентичные метрики (reproducible benchmark).


---


## 19. Security, RBAC, аутентификация и hardening

Раздел покрывает Phase 9 (§16) в части безопасности, а также все митигации рисков из §18. Реализуется как сквозной слой: основной код в `apps/api-gateway/` (auth, sessions, rate limits, audit logs), общие DTO/config в `packages/kg_common/`, guardrails для Cypher в `apps/graph-service/` и `apps/agent-service/`, инфраструктура backup/CI/CD/deploy в `infra/`. Зависимости от других разделов: схема ролей опирается на модель `Person`/`Lab`/`ResearchTeam` (§8.1) и `access policy` из source registration (§9.2 Step 1); audit log переиспользует `CurationEvent` (§12.3); observability и eval-harness Phase 9 покрываются отдельными разделами (мониторинг/OpenTelemetry, evaluation §15) — здесь только их интеграция с auth-контекстом. OSS для клонирования/вендоринга: LangGraph (`https://github.com/langchain-ai/langgraph`).

### 19.1 Модель ролей и RBAC (role-based access control)

- [x] Определить перечень ролей в `packages/kg_common/security/roles.py` как `enum RoleName`: `admin`, `curator`, `researcher`, `viewer`, `ingest_operator`, `service` (machine-to-machine). Каждая роль задокументирована с назначением.
- [x] Определить перечень permissions (scopes) в `packages/kg_common/security/permissions.py` как `enum Permission`, покрывающий все действия из endpoints §6.2 и human actions §12.2, минимум:
  - `chat:read`, `chat:write`;
  - `graph:read`, `graph:query` (`graph:read` покрывает read-only `/graph/schema`, `/graph/expand`, `/graph/path`, `/graph/subgraph`);
  - `search:read`;
  - `entities:read`, `entities:merge`, `entities:alias_add`;
  - `experiments:read`, `experiments:query` (endpoints `/experiments`, `/experiments/{id}`, `/experiments/query` из §6.2);
  - `evidence:read`, `evidence:review`;
  - `gaps:read`, `gaps:scan`;
  - `documents:read`, `documents:upload`, `documents:reindex`;
  - `ingest:submit`, `ingest:cancel`;
  - `curation:accept`, `curation:reject`, `curation:correct`, `curation:merge`, `curation:split`, `curation:schema_change`;
  - `admin:health`, `admin:metrics`, `admin:users`, `admin:audit_read`, `admin:backup`.
- [x] Реализовать role→permissions матрицу в `packages/kg_common/security/rbac_matrix.py` (dict) с явным маппингом; матрица покрыта unit-тестом, проверяющим что каждый permission присвоен хотя бы одной роли и что `viewer` не имеет ни одного write/mutate permission.
- [x] Реализовать FastAPI dependency `require_permission(perm: Permission)` в `apps/api-gateway/app/security/deps.py`, которая извлекает роли из auth-контекста, разворачивает их в permissions по матрице и возвращает HTTP 403 с телом `{ "error": "forbidden", "required": "<perm>" }` при отсутствии права.
- [x] Навесить `require_permission(...)` на КАЖДЫЙ endpoint из §6.2 согласно матрице (таблица соответствия endpoint→permission ведётся в `apps/api-gateway/app/security/endpoint_permissions.md`).
- [x] Реализовать deny-by-default (fail-closed): любой endpoint, не имеющий явного маппинга на permission и не входящий в public-allowlist, требует аутентификации и по умолчанию отклоняется; unit-тест проходит по OpenAPI-роутам и падает, если найден endpoint без явного permission/public-статуса.
- [x] Определить allowlist публичных (no-auth) маршрутов в `apps/api-gateway/app/security/public_routes.py`: `/healthz`, `/readyz` (liveness/readiness, легковесные), `/api/v1/auth/login`, `/api/v1/auth/refresh`, `/api/v1/auth/register` (только при `ALLOW_SELF_REGISTER`), `/docs`/`/openapi.json` (закрываются в prod флагом `ENABLE_API_DOCS`); всё остальное — под аутентификацией.
- [x] Реализовать поддержку нескольких ролей у одного пользователя (many-to-many) и эффективные permissions как объединение.
- [x] Написать pytest-набор `apps/api-gateway/tests/test_rbac.py`: для каждой роли прогнать матрицу «endpoint × ожидаемый код (200/403)»; тест падает при любом расхождении с матрицей.

**Критерий приёмки:** запрос от `viewer` к любому mutate-endpoint (`/entities/merge`, `/evidence/{id}/review`, `/documents/upload`, `/ingest/jobs`, curation actions) возвращает 403; запрос от роли с нужным permission — 2xx; каждый endpoint §6.2 либо имеет явный permission, либо входит в public-allowlist (fail-closed тест зелёный); тест `test_rbac.py` зелёный и покрывает 100% endpoints §6.2.

### 19.2 Аутентификация пользователей, сессии и токены

- [x] Выбрать и зафиксировать в `docs/security/auth_design.md` модель auth: OAuth2 Password/Bearer + JWT для MVP с точкой расширения на OIDC (Keycloak/Auth0) через `AUTH_PROVIDER` env-флаг.
- [x] Создать таблицы в Postgres (`kg_app`) миграцией (Alembic) в `apps/api-gateway/migrations/`: `users(id uuid pk, email unique, password_hash, display_name, is_active, created_at)`, `user_roles(user_id, role_name)`, `refresh_tokens(id, user_id, token_hash, expires_at, revoked_at, user_agent, ip)`, `api_keys(id, name, key_hash, owner_id, scopes, expires_at, revoked_at)`.
- [x] Создать таблицу `user_labs(user_id, lab_id, team_id, role_in_lab)` (Alembic-миграция) для членства пользователя в лабораториях/командах; синхронизируется с узлами `Person`/`ResearchTeam`/`Lab` графа (§8.1); служит источником `labs`-claim и access policy (19.3).
- [x] Реализовать хеширование паролей через `argon2` (или `bcrypt`) в `apps/api-gateway/app/security/passwords.py`; запрещено хранить plaintext; unit-тест на verify/rehash.
- [x] Реализовать endpoint `POST /api/v1/auth/register` (создание пользователя, по умолчанию роль `viewer`; создание доступно только `admin` или включается флагом `ALLOW_SELF_REGISTER`).
- [x] Реализовать endpoint `POST /api/v1/auth/login` → выдаёт short-lived access JWT (TTL из `ACCESS_TOKEN_TTL_MIN`, по умолчанию 15 мин) и refresh token (TTL `REFRESH_TOKEN_TTL_DAYS`, по умолчанию 14 дней), refresh хранится хешированным.
- [x] Реализовать `POST /api/v1/auth/refresh` (ротация refresh-токена: старый помечается `revoked_at`, выдаётся новый) и `POST /api/v1/auth/logout` (ревокация текущего refresh).
- [x] Реализовать JWT: подпись `HS256`/`RS256` (ключ из `JWT_SECRET`/`JWT_PRIVATE_KEY`), claims `sub`, `roles`, `labs`, `exp`, `iat`, `jti`; проверка подписи, срока и `jti` в blacklist (Redis) на каждом запросе; `labs`-claim заполняется из `user_labs`.
- [x] Поддержать ротацию ключей подписи JWT: заголовок `kid` и keyset из нескольких активных ключей (`JWT_KEYS`), чтобы старые и новые токены валидировались одновременно во время ротации (runbook rotate-keys — 19.12).
- [x] Реализовать хранение сессий/blacklist ревокации в Redis (сервис `redis` из §13.1) с TTL = сроку токена; middleware отклоняет отозванные `jti`.
- [x] Реализовать защиту от brute-force на `/auth/login`: счётчик неудачных попыток в Redis по ключу (email+IP), блокировка после `LOGIN_MAX_FAILED` попыток на `LOGIN_LOCKOUT_MIN`, экспоненциальный backoff; единый ответ 401 без раскрытия существования пользователя (no user enumeration); все события пишутся в audit (19.5).
- [x] Реализовать M2M-аутентификацию по API-ключам (`Authorization: Bearer sk_...`) для service-role (agent-service, ingestion-service): проверка `api_keys.key_hash`, scopes мапятся в permissions.
- [x] Реализовать endpoint `POST /api/v1/auth/api-keys` (создание, только `admin`) и `DELETE /api/v1/auth/api-keys/{id}` (ревокация); полный ключ показывается один раз.
- [x] Реализовать admin-endpoints управления пользователями (permission `admin:users`, изменения в audit log): `GET /api/v1/admin/users` (список с фильтрами/пагинацией), `GET /api/v1/admin/users/{id}`, `PATCH /api/v1/admin/users/{id}` (назначение `roles`/`labs`/`is_active`), `POST /api/v1/admin/users/{id}/deactivate`.
- [x] Реализовать FastAPI dependency `get_current_principal()` в `apps/api-gateway/app/security/deps.py`, возвращающую `Principal{user_id, roles, labs, permissions, auth_method}`; используется всеми защищёнными endpoints. DTO `Principal` вынесен в `packages/kg_common/security/` для переиспользования сервисами.
- [x] Аутентифицировать SSE/WebSocket-стрим чата (`GET /chat/sessions/{id}/stream`, §6.2): т.к. `EventSource` не шлёт заголовок `Authorization`, использовать короткоживущий одноразовый stream-token (query `?token=`, выдаётся авторизованным `POST /messages`) или HttpOnly-cookie; токен валидируется, связывается с сессией и её владельцем; неаутентифицированный/чужой stream → 401/403.
- [x] Привязать chat-сессии из §6.2 (`/chat/sessions`) к `user_id`: пользователь видит только свои сессии (кроме `admin`); добавить проверку владельца в `GET/POST /chat/sessions/{id}`.

**Критерий приёмки:** полный цикл login → доступ по access-token → истечение → refresh → logout работает и покрыт integration-тестом `apps/api-gateway/tests/test_auth_flow.py`; запрос без/с истёкшим/с отозванным токеном возвращает 401; SSE-стрим без валидного stream-token отклоняется; серия неудачных логинов блокирует аккаунт по `LOGIN_MAX_FAILED` и не раскрывает существование пользователя; пароли в БД хранятся только как argon2-хеши (проверяется тестом на формат).

### 19.3 Access policy на источники и лаборатории

- [x] Расширить source registration (§9.2 Step 1) полем `access_policy` в Postgres/graph: `enum{ public, lab_restricted, private }` + список `allowed_lab_ids` и `owner_id`; миграция и обновление модели `Document`/`Source` в `apps/graph-service/`.
- [x] Ввести deny-by-default: источники без проставленного `access_policy`/`owner_id` (в т.ч. до backfill Phase 8) трактуются как `private` (доступ только owner/`admin`); backfill-миграция проставляет `owner`/`lab` из lineage (зависимость от Phase 8 acceptance «every document/source has owner and lineage»).
- [x] Реализовать в `packages/kg_common/security/access.py` функцию `can_access_source(principal, source) -> bool`: `public` доступен всем аутентифицированным; `lab_restricted` — если `principal.labs ∩ source.allowed_lab_ids ≠ ∅` или `principal` в `owner`; `private` — только owner и `admin`.
- [x] Внедрить фильтрацию по access policy во ВСЕ read-пути, возвращающие данные документов/evidence/experiments: `/documents/*`, `/evidence/*`, `/experiments/*`, `/search/*`, `/graph/*` — результаты, у которых источник недоступен principal, исключаются из ответа (row-level filtering).
- [x] Пробросить access-фильтр в retrievers `packages/kg_retrievers/`: Cypher-шаблоны (§10.1 Mode A) получают параметр `$allowed_source_ids`/`$labs`; Qdrant/OpenSearch запросы (Mode B) применяют filter по `source_id`/`access_policy` в payload; GraphRAG community summaries (Mode C) не раскрывают контент из недоступных источников.
- [x] Пробросить access-контекст principal в LangGraph state (§7.3) как поле `auth: {user_id, labs, allowed_source_ids}`, чтобы все agent-tools (`run_cypher_template`, `hybrid_search`, `get_evidence`) применяли тот же фильтр; агент не может обойти policy.
- [x] Реализовать endpoint управления policy `PATCH /api/v1/documents/{doc_id}/access` (только owner/`admin`) с записью в audit log.
- [x] Написать тест `apps/api-gateway/tests/test_access_policy.py`: пользователь лаборатории A не видит `lab_restricted` документ лаборатории B ни в search, ни в graph, ни в evidence, ни через chat-агента.

**Критерий приёмки:** researcher из лаборатории A не может получить контент/evidence/experiments приватного или lab_restricted-источника лаборатории B ни одним из путей (REST, hybrid search, graph query, chat-агент); источник без owner/lab недоступен никому кроме admin (deny-by-default); тест `test_access_policy.py` подтверждает изоляцию по всем четырём путям.

### 19.4 Rate limiting и защита от abuse

- [ ] Реализовать rate-limiting middleware в `apps/api-gateway/app/security/ratelimit.py` на Redis (token-bucket или sliding-window), ключ = `principal.user_id` (или IP для анонимных), лимиты конфигурируемы через env (`RATE_LIMIT_DEFAULT_RPM`, отдельные лимиты для тяжёлых endpoints).
- [ ] Задать дифференцированные лимиты: строгие для дорогих операций (`/chat/.../messages`, `/search/hybrid`, `/graph/query`, `/gaps/scan`, `/documents/upload`, `/ingest/jobs`), мягкие для лёгких read.
- [ ] Задать жёсткий per-IP лимит на неаутентифицированные `/auth/login`, `/auth/register`, `/auth/refresh` (anti-brute-force, в связке с 19.2), не зависящий от user_id.
- [ ] Возвращать HTTP 429 с заголовками `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
- [ ] Реализовать ограничение размера тела запроса и upload (`MAX_UPLOAD_MB`) и content-type allowlist для `/documents/upload` (pdf/docx/…); превышение → 413.
- [ ] Валидировать загружаемые файлы по сигнатуре (magic bytes), а не только по заявленному `Content-Type`: несоответствие → 415/400; санитизировать имя файла; опциональный AV-скан (ClamAV, флаг `ENABLE_AV_SCAN`) в ingestion перед парсингом.
- [ ] Реализовать concurrency-квоты на LLM-вызовы/ingestion-jobs на пользователя (semaphore в Redis), чтобы один пользователь не занял весь пул агентов.
- [ ] Написать тест `test_ratelimit.py`: серия запросов сверх лимита получает 429, после `Retry-After` восстанавливается.

**Критерий приёмки:** превышение сконфигурированного лимита на `/chat/.../messages` даёт 429 с корректным `Retry-After`; upload файла больше `MAX_UPLOAD_MB` даёт 413; файл с подменённым content-type (magic bytes не совпадают) отклоняется; тест `test_ratelimit.py` зелёный.

### 19.5 Audit logs

- [ ] Создать таблицу `audit_log(id uuid, ts, actor_id, actor_role, auth_method, ip, user_agent, method, path, action, target_type, target_id, status_code, request_id, before jsonb, after jsonb, reason)` в Postgres (`apps/api-gateway/migrations/`).
- [ ] Реализовать audit-middleware в `apps/api-gateway/app/security/audit.py`, логирующую все mutate-запросы (POST/PATCH/PUT/DELETE) и все доступы к чувствительным данным (evidence, документы private/lab_restricted, admin-endpoints).
- [ ] Интегрировать audit с моделью `CurationEvent` (§12.3): каждая curation-action (`accept/reject/correct/merge/split/alias_add/schema_change`) пишет и `CurationEvent` (граф/Postgres), и запись в `audit_log` с `before/after`.
- [ ] Логировать security-события отдельным типом: login success/fail, refresh, logout, token revocation, 401/403, rate-limit hit, api-key create/revoke, access-policy change, account lockout.
- [ ] Присвоить каждому запросу `request_id` (middleware) и пробросить его в structlog (`packages/kg_common`), в SSE/agent traces и в audit — end-to-end корреляция.
- [ ] Пробросить auth-контекст (`user_id`, `role`, `request_id`; без PII/секретов) в OpenTelemetry span attributes, чтобы audit↔traces↔logs коррелировали по `request_id`/`user_id` (интеграция с разделом observability).
- [ ] Гарантировать неизменяемость audit-лога: только append (нет UPDATE/DELETE из приложения), отдельная роль БД без прав на изменение audit; опционально — периодический экспорт в MinIO (WORM-подобное хранение).
- [ ] Задать retention-политику `audit_log` (`AUDIT_RETENTION_DAYS`) с архивацией в MinIO до удаления; фактическое удаление возможно только через привилегированную БД-роль вне приложения.
- [ ] Реализовать endpoint `GET /api/v1/admin/audit?actor=&action=&from=&to=&target=` (permission `admin:audit_read`) с пагинацией и фильтрами.
- [ ] Обеспечить отсутствие секретов/паролей/полных токенов в логах: маскирование `Authorization`, `password`, JWT в structlog processor; unit-тест на маскирование.

**Критерий приёмки:** merge сущностей и review evidence создают запись в `audit_log` с `before/after` и связанный `CurationEvent`; неуспешный login, account lockout и 403 фиксируются; `GET /admin/audit` доступен только `admin` и фильтрует по actor/action/date; лог не содержит plaintext-секретов (проверено тестом маскирования).

### 19.6 Cypher/query hardening и agent guardrails (митигация «Cypher generation dangerous»)

- [ ] Реализовать read-only режим доступа агента к Neo4j: отдельный БД-пользователь с ролью `reader` (Neo4j RBAC), используемый в `apps/graph-service`/`apps/agent-service`; write-операции идут только через curation-service под отдельной ролью `writer`.
- [ ] Запретить свободный Text2Cypher: агент вызывает только зарегистрированные Cypher-шаблоны из allowlist в `apps/graph-service/app/templates/` (§7.4 `run_cypher_template`); tool отклоняет любой запрос вне allowlist.
- [ ] Ограничить/выключить tool `run_cypher_readonly` (§7.4): в prod свободный Cypher отключён (`ALLOW_RAW_CYPHER=false`, по умолчанию агент использует только `run_cypher_template`); если включён для отладки — проходит полный набор guardrails §7.4 (schema grounding, read-only transaction, LIMIT, query cost guard, allowlist labels/relations, retry with verifier), реализованный в `cypher_guard`.
- [ ] Внедрить статический валидатор Cypher в `apps/graph-service/app/security/cypher_guard.py`: запрет `CREATE/MERGE/DELETE/SET/REMOVE/CALL apoc.*write*/LOAD CSV/dbms.*` в read-path (парсер по ключевым словам + проверка на mutating clauses); allowlist используемых labels/relations; нарушение → отказ и audit-запись.
- [ ] Принудительный `LIMIT` (инъекция `MAX_ROWS`, по умолчанию 1000), query cost guard и query timeout (`neo4j` transaction timeout `CYPHER_TIMEOUT_MS`, по умолчанию 5000) на все запросы read-path.
- [ ] Параметризовать все шаблоны (только `$params`, никакой конкатенации пользовательского ввода в строку Cypher) — защита от Cypher-инъекций; тест с попыткой инъекции подтверждает экранирование.
- [ ] Внедрить prompt-injection guardrail: контент документов/чанков/community summaries, попадающий в контекст LLM, трактуется как недоверенные данные, а не инструкции; системный промпт изолирует пользовательский/источниковый ввод (delimiters/roles), запрещает выполнение встроенных в текст команд, смену tool-политики и раскрытие данных недоступных источников (19.3); тест с документом, содержащим «ignore previous instructions / delete the graph / reveal lab B data», подтверждает, что агент не вызывает mutating-tools и не нарушает access policy.
- [ ] Применить те же ограничения (allowlist, LIMIT, timeout, параметризация) к запросам gap-scan и contradiction-detection (§11).
- [ ] Написать тест `apps/graph-service/tests/test_cypher_guard.py`: mutating-запрос и запрос без LIMIT отклоняются; попытка инъекции через параметр не изменяет граф; injected-инструкция в тексте документа не приводит к mutating-вызову.

**Критерий приёмки:** любой mutating Cypher или запрос вне allowlist, инициированный агентом, отклоняется и попадает в audit; read-only БД-пользователь физически не может писать в граф (проверяется интеграционным тестом с реальным Neo4j); все шаблоны параметризованы и имеют LIMIT+timeout; prompt-injection из контента источника не заставляет агента мутировать граф или обойти access policy.

### 19.7 Secrets management, транспорт и container hardening

- [ ] Убрать все hardcoded-креды из §13.1 docker-compose (`NEO4J_AUTH: neo4j/password`, `POSTGRES_PASSWORD: kg`, `MINIO_ROOT_PASSWORD`, `OPENSEARCH_INITIAL_ADMIN_PASSWORD: adminadminadmin`) в переменные из `.env`/секрет-стора; создать `.env.example` без реальных значений и `docs/security/secrets.md`.
- [ ] Ввести секрет-менеджмент: локально — `.env` (в `.gitignore`), prod — Docker/K8s secrets или external (Vault/SOPS); ни один секрет не коммитится (проверяется pre-commit `gitleaks`/`detect-secrets`).
- [ ] Настроить TLS termination (reverse-proxy `traefik`/`nginx` в `infra/`) для frontend и API; редирект HTTP→HTTPS; включить HSTS, secure/`SameSite` cookies для refresh-токена (HttpOnly).
- [ ] Реализовать CSRF-защиту для cookie-based refresh flow: `SameSite=Strict` + double-submit CSRF-token на state-changing запросах, если refresh хранится в cookie; для чистого Bearer-header-flow CSRF неактуален — выбранную модель задокументировать в `docs/security/auth_design.md`.
- [ ] Настроить CORS в `apps/api-gateway` по allowlist origins (`CORS_ALLOWED_ORIGINS`), без `*` в prod; и security headers (`Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`) через middleware.
- [ ] Включить security-plugin OpenSearch в prod (в §13.1 он `disabled`): `plugins.security.disabled: "false"`, internal users/roles, TLS для node/http; для MVP оставить отключённым только в изолированном local-профиле (документировать разницу профилей).
- [ ] Включить Neo4j auth (не default `neo4j/password`) и создать роли `reader`/`writer`/`admin` (Neo4j native RBAC); MinIO — отдельные access/secret keys и per-bucket policy вместо root.
- [ ] Защитить исходящие fetch в ingestion от SSRF (если источник задаётся URL): allowlist схем/доменов, блокировка приватных диапазонов и cloud-metadata `169.254.169.254`, запрет редиректов на внутренние адреса.
- [ ] Включить шифрование данных at-rest для volume/bucket Postgres/Neo4j/MinIO (disk/bucket encryption) и TLS между внутренними сервисами в prod-профиле; задокументировать в `docs/security/secrets.md`.
- [ ] Hardening Docker-образов: non-root user в каждом `Dockerfile` (`apps/*/Dockerfile`), pinned base-image digests, multi-stage build, `.dockerignore` без секретов, drop capabilities/`read_only` rootfs где возможно.
- [ ] Добавить сканирование образов и зависимостей в CI: `trivy`/`grype` для образов, `pip-audit`/`safety` для Python, `npm audit` для frontend; сборка падает на HIGH/CRITICAL уязвимостях.

**Критерий приёмки:** `grep`/`gitleaks` по репозиторию не находит секретов и default-паролей вне `.env.example`; prod-профиль docker-compose/helm поднимает сервисы с TLS, включённой security OpenSearch и non-default Neo4j auth; CORS без `*` и security headers присутствуют; CI-скан не пропускает образы с CRITICAL CVE.

### 19.8 Backup и restore процедуры

- [ ] Реализовать backup Neo4j: скрипт `infra/backup/neo4j_backup.sh` (`neo4j-admin database dump`/online backup для community — dump при остановке или APOC export), артефакт в MinIO/S3 с датой; расписание через Dagster (`infra/dagster/`) или cron.
- [ ] Реализовать backup Postgres (`kg_app`): `pg_dump` в MinIO, ежедневно, с ретеншеном (`BACKUP_RETENTION_DAYS`).
- [ ] Реализовать backup Qdrant (snapshot API `POST /collections/{c}/snapshots`) и OpenSearch (snapshot repository в MinIO/S3) с расписанием.
- [ ] Реализовать backup MinIO (объекты: оригиналы + parsed artifacts) через `mc mirror`/replication в отдельный bucket/регион.
- [ ] Шифровать backup-артефакты (SSE-KMS / `age`/`gpg`) и хранить в отдельном bucket с выделенными creds и restrictive policy (не root, не public); ключи шифрования — в секрет-сторе; включить object-lock/immutability и ретеншен на backup-bucket.
- [ ] Реализовать единый скрипт `infra/backup/backup_all.sh` (все хранилища консистентно, с манифестом `backup_manifest.json`: версии, checksums, timestamps).
- [ ] Реализовать restore-скрипты `infra/backup/restore_*.sh` для каждого хранилища и общий `restore_all.sh` из выбранного backup-манифеста.
- [ ] Задокументировать RPO/RTO и процедуру disaster recovery в `docs/ops/backup_restore.md`.
- [ ] Провести и задокументировать тест восстановления: поднять чистый стек, восстановить из backup, прогнать smoke-тесты (health, sample-query, chat) — результат записан как runbook.

**Критерий приёмки:** запуск `backup_all.sh` создаёт согласованный набор зашифрованных артефактов с манифестом в отдельном restricted bucket; `restore_all.sh` на чистом стеке восстанавливает граф/БД/векторы/объекты, после чего проходят health-checks и sample graph query возвращает те же данные (verified в CI job или документированном прогоне).

### 19.9 CI/CD пайплайны деплоя

- [ ] Создать CI-workflow (`.github/workflows/ci.yml` или GitLab CI) `lint+typecheck`: `ruff`, `mypy`, `eslint`, `prettier` (инструменты уже вводятся в Phase 0) — падает при нарушениях.
- [ ] Создать CI-job `test`: `pytest` для всех `apps/*` и `packages/*` с поднятием сервисов через docker-compose (Neo4j/Qdrant/OpenSearch/Postgres/Redis) как CI services; собирается coverage-отчёт.
- [ ] Создать CI-job `security-scan`: `gitleaks`/`detect-secrets`, `pip-audit`, `npm audit`, `trivy` образов (см. 19.7), а также SAST (`bandit`/`semgrep` для Python, `eslint-plugin-security` для frontend); job падает на findings выше порога.
- [ ] Настроить автообновление зависимостей (`dependabot`/`renovate`) с авто-PR, проходящими `security-scan`.
- [ ] Создать CD-job `build-and-push`: сборка Docker-образов для всех `apps/*` с тегами `sha`/`semver`, публикация в registry; SBOM (`syft`) как артефакт.
- [ ] Создать CD-job `deploy-staging`: деплой в staging через `infra/helm/` (Helm charts) или docker-compose на VM; smoke-тесты после деплоя используют публичные `/healthz`/`/readyz` (без токена) для liveness/readiness, а проверки, требующие данных, — сервисный токен (`service`-role API-key) для `/api/v1/admin/health`.
- [ ] Реализовать `deploy-prod` с manual approval gate и стратегией отката (`helm rollback`/предыдущий tag); задокументировать rollback-процедуру.
- [ ] Настроить миграции БД в пайплайне: Alembic-миграции применяются до старта API, идемпотентно; Neo4j constraints/indexes (§8.4) применяются миграционным скриптом.
- [ ] Настроить branch protection: merge в `main` только при зелёных `lint+typecheck+test+security-scan`.

**Критерий приёмки:** push в PR запускает lint/typecheck/test/security-scan (включая SAST и secret-scan); merge в `main` собирает и пушит образы; `deploy-staging` разворачивает стек и smoke-тест `/readyz`+`/admin/health` возвращает 200; ручной откат `helm rollback` возвращает предыдущую версию (проверено на staging).

### 19.10 LangGraph Platform / langgraph-cli и Assistants API

- [ ] Добавить `langgraph-cli` (`pip install "langgraph-cli[inmem]"`) в зависимости `apps/agent-service/` и, при необходимости, вендорить/клонировать LangGraph (`https://github.com/langchain-ai/langgraph`) для reference.
- [ ] Создать `apps/agent-service/langgraph.json` с полями `dependencies` (пакеты/пути graph), `graphs` (маппинг `scientific_agent` → `./app/graph.py:build_graph`, отражающий nodes §7.5), `env` (`.env`), `http` (auth-хук).
- [ ] Настроить persistence: LangGraph checkpointer на Postgres (`kg_app` или отдельная БД) для thread/state (§7.3), чтобы chat-сессии переживали рестарт; конфиг в `langgraph.json`/env.
- [ ] Поднять локальный dev-сервер `langgraph dev` (in-memory) и задокументировать в `docs/dev/langgraph.md`; убедиться что граф компилируется и виден в LangGraph Studio trace viewer (интеграция trace viewer из Phase 9).
- [ ] Настроить `langgraph build`/`langgraph up` для контейнеризованного запуска agent-service; интегрировать полученный образ в docker-compose (§13.1 сервис `agent`) и Helm.
- [ ] Реализовать интеграцию с Assistants API LangGraph Platform: создать assistant для `scientific_agent` (versioned config), эндпоинты threads/runs; API Gateway проксирует чат (`/chat/sessions/*` §6.2) в Assistants API/agent-service.
- [ ] Защитить LangGraph Platform endpoint аутентификацией: custom auth-хук (`langgraph_sdk` auth / middleware), пробрасывающий `Principal` и access-контекст (labs, allowed_source_ids из 19.3) в state; агент нельзя вызвать без валидного токена/API-key.
- [ ] Реализовать привязку LangGraph threads к `user_id` и chat-сессиям (19.2), чтобы Assistants-threads уважали RBAC и access policy.
- [ ] Написать тест `apps/agent-service/tests/test_langgraph_config.py`: `langgraph.json` валиден, граф импортируется, checkpointer подключается, неаутентифицированный вызов run отклоняется.

**Критерий приёмки:** `langgraph dev` поднимает граф `scientific_agent` локально и он виден в Studio; контейнер, собранный `langgraph build`/`up`, обслуживает Assistants API через API Gateway; вызов run без валидного токена отклоняется; state содержит корректный `auth`-контекст пользователя; thread привязан к `user_id`.

### 19.11 Демо-данные и walkthrough (§19 minimal viable demo path)

- [ ] Подготовить seed-набор из 20–50 научных документов (§19 demo path, минимум seed 10 из Phase 0) с разными `access_policy` и лабораториями для демонстрации RBAC/access; скрипт `infra/seed/load_demo_docs.py`.
- [ ] Создать демо-пользователей и роли: `admin`, `curator@labA`, `researcher@labA`, `researcher@labB`, `viewer` (с записями в `user_labs`); скрипт `infra/seed/seed_users.py` с известными паролями только для demo-профиля.
- [ ] Прогнать полный ingestion→extraction→resolution→graph pipeline на demo-корпусе так, чтобы получился граф с Material/Regime/Property/Measurement/Evidence и хотя бы одним Gap и одним Contradiction (§19 demo path пункты 3,7).
- [ ] Реализовать демонстрацию топового flow «что делали по X при Y и эффект на Z?» (§19 demo path п.6) и убедиться, что ответ содержит числа, условия, источники, evidence и graph payload.
- [ ] Написать пошаговый walkthrough-скрипт `docs/demo/walkthrough.md`: login под каждой ролью → показ разницы доступа → chat-вопрос → graph explorer → evidence inspector → gap dashboard; каждый шаг с ожидаемым результатом.
- [ ] Реализовать one-command demo bootstrap `make demo` / `infra/demo/up.sh`: поднимает стек, применяет миграции/constraints, грузит demo-данные и пользователей, печатает URL и креды.
- [ ] Подготовить sanitized demo, безопасный для показа: demo-креды не совпадают с prod, demo-профиль изолирован (`COMPOSE_PROFILES=demo`), без реальных секретов.

**Критерий приёмки:** `make demo` на чистой машине за одну команду поднимает систему с загруженными demo-данными и пользователями; walkthrough из `docs/demo/walkthrough.md` проходится end-to-end локально и на VM; researcher@labA и researcher@labB видят разный набор источников; топовый query возвращает числа+условия+источники+evidence+graph.

### 19.12 Документация деплоя

- [ ] Написать `docs/deploy/README.md`: архитектура развёртывания (сервисы §6.1, порты §13.1), требования (CPU/RAM/GPU для extraction), профили `local`/`staging`/`prod`/`demo`.
- [ ] Написать `docs/deploy/local.md`: запуск через docker-compose (§13.1), `.env.example`→`.env`, порядок старта, health-checks (`/api/v1/admin/health`), типовые проблемы.
- [ ] Написать `docs/deploy/production.md`: Helm-чарты (`infra/helm/`), секреты, TLS/reverse-proxy, включённая security OpenSearch/Neo4j auth, масштабирование agent/ingestion, backup/restore ссылки.
- [ ] Задокументировать полный перечень env-переменных в `docs/deploy/env_reference.md` (auth TTL, JWT keys/keyset, login lockout, rate limits, CORS origins, backup retention, audit retention, LangGraph config) с дефолтами и пометкой обязательных/секретных.
- [ ] Написать runbooks в `docs/ops/`: rotate secrets/keys (JWT keyset, 19.2), revoke user/API-key, incident response (compromised token), restore from backup, rollback deploy.
- [ ] Задокументировать security-модель в `docs/security/overview.md`: роли/permissions (19.1), access policy (19.3), audit (19.5), guardrails (19.6), threat-model и покрытие рисков §18.

**Критерий приёмки:** новый инженер по `docs/deploy/local.md` поднимает систему без внешней помощи; `docs/deploy/production.md` содержит воспроизводимую prod-инструкцию с TLS/secrets/backup; `env_reference.md` перечисляет все env-переменные, используемые в коде (проверяется скриптом сверки кода и доков).

### 19.13 Явная митигация всех рисков из §18

- [ ] **LLM hallucinated triples (High):** обеспечить, что verifier-node (§7.5 Node 9) и guardrail «no numeric claim without evidence» (Phase 5) включены и покрыты тестом; low-confidence извлечения принудительно уходят в review queue (§12.1); citation guardrails возвращают ошибку при claim без evidence.
- [ ] **Poor PDF parsing (High):** сконфигурировать fallback-цепочку Docling→Marker→Unstructured (`https://github.com/datalab-to/marker`, `https://github.com/Unstructured-IO/unstructured`) и путь ручной загрузки таблиц; тест на документ, где Docling падает, а fallback срабатывает.
- [ ] **Entity duplicates (High):** подтвердить работу Splink (`https://github.com/moj-analytical-services/splink`) + alias tables + review queue (Phase 3); тест: типовые алиасы схлопываются, неоднозначные уходят в review, история merge сохраняется.
- [ ] **Graph becomes unreadable (Medium):** включить subgraph projection, фильтры, community view и Sigma.js fallback (§5.1) при >N элементов; тест производительности на 1k–5k элементов (Phase 6 acceptance).
- [ ] **Slow chat (Medium):** включить SSE streaming, кэш retrieval (Redis), query templates и precomputed community summaries; замерить и задокументировать p95 latency; regression-тест на бюджет времени.
- [ ] **Cypher generation dangerous (High):** покрыто 19.6 (templates-first, read-only, allowlist, LIMIT, timeout) — добавить чек-лист соответствия в `docs/security/overview.md`.
- [ ] **Too many moving parts (Medium):** обеспечить чёткие границы сервисов и профили docker-compose, позволяющие отключить OpenSearch/DataHub для MVP (`COMPOSE_PROFILES`); задокументировать минимальный профиль.
- [ ] **Weak eval (High):** подтвердить наличие golden QA set и метрик из Phase 9/§15 в CI (eval-job), падающего при регрессии unsupported-claim rate (интеграция с разделом evaluation).
- [ ] **Users do not trust answers (High):** обеспечить работу evidence inspector (§5.2.6) и unsupported-claim guardrails; тест: каждый числовой ответ агента кликабельно ведёт к source snippet.
- [ ] Свести все девять рисков §18 в таблицу `docs/security/risk_mitigation.md` со ссылкой на конкретную задачу/тест, закрывающий риск; каждая строка имеет статус и verification-ссылку.

**Критерий приёмки:** в `docs/security/risk_mitigation.md` каждый из 9 рисков §18 сопоставлен реализованной митигации и проверяющему тесту/прогону; соответствующие тесты (verifier/no-claim-without-evidence, fallback-parsing, entity-dedup, graph-scale, chat-latency, cypher-guard, eval-regression, evidence-clickthrough) зелёные.

### 19.14 Итоговые acceptance-критерии Phase 9 (security-часть)

- [ ] Подтвердить (§16 Phase 9 acceptance) «reproducible benchmark»: eval-job в CI (интеграция с §15/evaluation) детерминированно воспроизводит метрики golden-set; регрессия валит gate.
- [ ] Подтвердить (§16 Phase 9 acceptance) «no unsupported answer claims in golden set»: eval-прогон на golden QA set показывает 0 unsupported numeric claims.
- [ ] Подтвердить «full demo can be run locally or on VM»: `make demo` отработал и на localhost, и на чистой VM; walkthrough пройден.
- [ ] Провести сводный security review по чек-листу `docs/security/overview.md` (auth, RBAC, access policy, rate limit, audit, cypher-guard, prompt-injection, secrets/TLS, backup, CI/CD) и зафиксировать результат.
- [ ] Прогнать полный test-suite безопасности (`test_rbac`, `test_auth_flow`, `test_access_policy`, `test_ratelimit`, `test_cypher_guard`, audit-masking, `test_langgraph_config`) в CI — все зелёные как gate релиза.

**Критерий приёмки:** Phase 9 security-deliverables (auth/RBAC, deployment docs, demo script, backup/restore, CI/CD) реализованы; reproducible benchmark и «no unsupported claims» подтверждены; сводный security review пройден; весь security test-suite зелёный в CI и является обязательным gate для деплоя.


---


## 20. Интеграции лабораторных систем и materials data

Раздел покрывает §4.1 (строка «Lab notebook integration | eLabFTW/openBIS»), §22 «Scientific/materials helpers» (MatKG, MatBERT, MatEntityRecognition, Matscholar, Propnet, Materials Project API, pymatgen) и «Lab systems» (eLabFTW, openBIS), §21 (optional «eLabFTW/openBIS integration», strongly recommended «MatBERT/MatSciBERT-related models»), а также точки интеграции с §9 (ingestion pipeline), §8 (KG schema), §7.3 (entity_resolver: «Materials Project / internal catalog IDs»), §6.1 (структура monorepo), §6.2 (endpoints `/api/v1/experiments`). Цель — подключить внешние лабораторные системы (eLabFTW, openBIS) как источники экспериментов/инвентаря через REST API и обогатить граф каноническими материалами и свойствами из Materials Project / pymatgen / MatKG / Matscholar / Propnet, а также материаловедческими NER/эмбеддингами (MatBERT/MatSciBERT, MatEntityRecognition), с корректным маппингом внешних ID на canonical сущности графа.

Все интеграции реализуются как отдельные connector-модули внутри нового пакета `packages/kg_connectors/` (домённая часть — пишем сами, §4.2), материаловедческие NER/эмбеддинги (MatBERT/MatSciBERT, MatEntityRecognition) — как extractors в `packages/kg_extractors/` (§9.2 Step 4), и запускаются из `apps/ingestion-service/` через Dagster assets (`infra/dagster/`). Затрагиваемые сервисы/пакеты: `apps/ingestion-service/`, `apps/api-gateway/`, `apps/graph-service/`, `apps/agent-service/` (entity_resolver, §7.3), `packages/kg_connectors/` (новый), `packages/kg_schema/`, `packages/kg_extractors/`, `packages/kg_common/`, `packages/kg_eval/`, `infra/dagster/`, `infra/docker-compose.yml`, `infra/neo4j/`.

Зависимости от других разделов: §8 KG schema (labels/relationships), §9 Step 1 (source registration), Step 4 (extraction, MatBERT/MatEntityRecognition), Step 5 (units normalization, `pint`), Step 6 (entity resolution, Splink), Step 7 (graph upsert), §7.3 (agent entity_resolver с MP/internal catalog IDs), §12 Curation (review внешних merge-решений), §13.2 Python packages (`pymatgen` уже в списке), §16 Phase 8 (metadata/lineage/DataHub).

---

### 20.1 Вендоринг и подготовка OSS-репозиториев (§22)

- [ ] Создать директорию `third_party/lab_materials/` для reference-клонов и зафиксировать её в `.gitignore`/`git submodules` (по решению команды: submodule vs shallow clone + pinned commit в `third_party/lab_materials/SOURCES.lock`).
- [ ] Склонировать репозитории и записать pinned commit SHA каждого в `third_party/lab_materials/SOURCES.lock`:
  - [ ] eLabFTW: `git clone https://github.com/elabftw/elabftw` (только для чтения OpenAPI-спеки и REST-контрактов; сам сервис поднимаем docker-образом).
  - [ ] openBIS community repos: `git clone https://github.com/openbis` (индекс организации; фактически вендорим `pybis` из подрепозитория).
  - [ ] Materials Project API (`mp-api`): `git clone https://github.com/materialsproject/api`.
  - [ ] pymatgen: `git clone https://github.com/materialsproject/pymatgen`.
  - [ ] MatKG: `git clone https://github.com/olivettigroup/MatKG`.
  - [ ] Matscholar: `git clone https://github.com/materialsintelligence/matscholar`.
  - [ ] Propnet: `git clone https://github.com/materialsintelligence/propnet`.
  - [ ] MatBERT: `git clone https://github.com/lbnlp/MatBERT` (скрипты/веса материаловедческого BERT; веса модели скачиваются отдельно в `MATBERT_MODEL_PATH`).
  - [ ] MatEntityRecognition: `git clone https://github.com/CederGroupHub/MatEntityRecognition` (доменный NER материалов/операций синтеза).
- [ ] Добавить в `apps/ingestion-service/pyproject.toml` (или общий `requirements`) pip-зависимости: `pymatgen` (уже в §13.2), `mp-api`, `elabapi-python` (официальный клиент eLabFTW API v2), `pybis` (клиент openBIS), `matscholar` (или REST-вызовы, если пакет не публикуется в PyPI), `transformers`+`torch` (для MatBERT/MatSciBERT), `MatEntityRecognition` (editable из GitHub, если нет в PyPI).
- [ ] Для `MatKG`, `propnet`, `MatBERT`-скриптов и `MatEntityRecognition` (не всегда публикуются в PyPI) — вендорить как editable-install из `third_party/lab_materials/` либо оформить как локальные пакеты в `packages/kg_connectors/vendored/` (материаловедческие NER — в `packages/kg_extractors/vendored/`); зафиксировать способ в README пакета.
- [ ] Скачать веса MatBERT (`lbnlp/MatBERT`) и MatSciBERT (`m3rg-iitd/matscibert` с HuggingFace) в путь `MATBERT_MODEL_PATH`/`MATSCIBERT_MODEL`; зафиксировать версии моделей (SHA/revision) в `SOURCES.lock` для воспроизводимости.
- [ ] Провести license review каждого репозитория (MIT/BSD/Apache/GPL) и занести результат в `third_party/lab_materials/LICENSES.md`; пометить GPL-компоненты (например, eLabFTW — AGPL) как используемые только через сетевой API, без линковки кода; отдельно проверить лицензии/условия использования весов MatBERT/MatSciBERT.

**Критерий приёмки:** `third_party/lab_materials/SOURCES.lock` содержит все 9 репозиториев с pinned SHA (плюс revision весов MatBERT/MatSciBERT), `LICENSES.md` заполнен, `pip install -e .` в `apps/ingestion-service/` проходит без ошибок и `python -c "import pymatgen, mp_api, elabapi_python, pybis, transformers"` выполняется успешно; веса MatBERT/MatSciBERT грузятся через `transformers` из `MATBERT_MODEL_PATH`.

---

### 20.2 Каркас пакета `packages/kg_connectors/` и конфигурация

- [ ] Создать пакет `packages/kg_connectors/` со структурой:
  - `kg_connectors/base.py` — абстрактный `SourceConnector` (методы `list_records`, `fetch_record`, `to_canonical`, `incremental_cursor`).
  - `kg_connectors/eln/` (eLabFTW), `kg_connectors/lims/` (openBIS), `kg_connectors/materials/` (mp/pymatgen), `kg_connectors/enrichment/` (MatKG, Matscholar, Propnet).
  - `kg_connectors/crosswalk/` — маппинг внешних ID на canonical (см. 20.3).
  - `kg_connectors/models.py` — Pydantic DTO промежуточного слоя (`ExternalExperiment`, `ExternalSample`, `ExternalInventoryItem`, `ExternalMaterialRecord`, `MaterialsProjectEntry`).
- [ ] Определить единый конфиг `ConnectorSettings` через `pydantic-settings` в `packages/kg_common/config.py`: base URL, API-ключ/токен, verify TLS, rate-limit, page size, timeout, `enabled: bool` для каждого коннектора и для материаловедческих NER-моделей (MatBERT/MatEntityRecognition).
- [ ] Добавить в `.env.example` переменные: `ELABFTW_BASE_URL`, `ELABFTW_API_KEY`, `OPENBIS_URL`, `OPENBIS_USER`, `OPENBIS_PASSWORD` (или token), `MP_API_KEY`, `MATSCHOLAR_API_KEY` (при наличии), `MATKG_DATA_PATH`, `PROPNET_ENABLED`, `MATBERT_MODEL_PATH`, `MATSCIBERT_MODEL`, `MATBERT_ENABLED`, `MATENTITYRECOGNITION_ENABLED`.
- [ ] Секреты не хранить в git: интегрировать чтение из окружения/секрет-стора; добавить fail-fast проверку наличия обязательных ключей при старте connector-джобы.
- [ ] Реализовать shared HTTP-слой `kg_connectors/http.py` на `httpx` с retry (экспоненциальный backoff), rate-limit (token bucket), пагинацией и структурированным логированием через `structlog` (§13.2).
- [ ] Добавить в `apps/ingestion-service/` endpoint `POST /connectors/{connector}/sync` (запуск синка) и `GET /connectors/{connector}/status` (последний cursor, счётчики), а также CLI `python -m kg_connectors sync <connector> --since <cursor>`.

**Критерий приёмки:** `pytest packages/kg_connectors/tests/test_base.py` проходит; `python -m kg_connectors --help` перечисляет все 5 групп коннекторов; запуск любого коннектора без обязательного ключа падает с понятной ошибкой конфигурации, а не стек-трейсом httpx.

---

### 20.3 Crosswalk-модель: маппинг внешних ID на canonical сущности

- [ ] Расширить `packages/kg_schema/` (Pydantic + LinkML) новой сущностью и связями для внешних идентификаторов, не ломая §8.1:
  - [ ] Добавить node label `ExternalRef` c полями `id`, `system` (`elabftw|openbis|materials_project|matkg|matscholar|propnet`), `external_id`, `external_url`, `system_version`, `fetched_at`, `payload_hash`.
  - [ ] Добавить relationship `(:Entity)-[:HAS_EXTERNAL_REF]->(:ExternalRef)` и обратную навигацию для reverse-lookup.
  - [ ] Добавить property `external_ids: map` на `Material`, `Experiment`, `Sample`, `Equipment`, `Property`, `Lab`, `Person` (быстрый доступ без обхода `ExternalRef`).
- [ ] Добавить Neo4j constraints/indexes в `infra/neo4j/` (в дополнение к §8.4):
  - [ ] `CREATE CONSTRAINT external_ref_id IF NOT EXISTS FOR (n:ExternalRef) REQUIRE n.id IS UNIQUE;`
  - [ ] `CREATE CONSTRAINT external_ref_unique IF NOT EXISTS FOR (n:ExternalRef) REQUIRE (n.system, n.external_id) IS UNIQUE;`
  - [ ] `CREATE INDEX external_ref_system IF NOT EXISTS FOR (n:ExternalRef) ON (n.system);`
- [ ] Реализовать `kg_connectors/crosswalk/resolver.py`: детерминированная функция `resolve_or_create(system, external_id, candidate_props) -> canonical_id`, использующая (a) прямой lookup по `(system, external_id)`, (b) fallback на Splink entity resolution (§9.2 Step 6) для материалов/оборудования/персон при отсутствии прямого маппинга.
- [ ] Реализовать политику разрешения конфликтов: если внешняя запись матчится на существующий canonical с `match_probability >= 0.9` → `auto_merge`; `0.7–0.9` → создать `Gap`/review-элемент в curation queue (§12) и связать через `HAS_EXTERNAL_REF` с флагом `review_status=pending`; `< 0.7` → `separate` (новая сущность). Значения порогов брать из `ConnectorSettings`.
- [ ] Гарантировать соблюдение upsert-правил §9.2 Step 7: `MERGE` по canonical id, никогда не перезаписывать reviewed-поля из внешних систем (§16 Phase 3 «protect reviewed canonical entities from overwrite»), сохранять `system_version`/`payload_hash` для идемпотентности повторных синков.
- [ ] Реализовать reverse-crosswalk endpoint `GET /api/v1/entities/{entity_id}` — включить в ответ список `external_refs` (система + ссылка на оригинал в eLabFTW/openBIS/MP) для отображения в Entity Detail Page (§5.2.4).
- [ ] Обеспечить, чтобы agent-нода `entity_resolver` (§7.3) при резолве материалов/оборудования получала Materials Project / internal catalog IDs из crosswalk (через `external_ids`/reverse-lookup), возвращая `canonical_id` вместе с внешним MP `material_id`, где доступно.

**Критерий приёмки:** повторный синк одной и той же внешней записи не создаёт дублей (идемпотентность подтверждена тестом `test_crosswalk_idempotent`); для тестовой пары «AA2024 из eLabFTW» ↔ «material:al-cu-2024» устанавливается `HAS_EXTERNAL_REF`, а `MATCH (m:Material {id:'material:al-cu-2024'})-[:HAS_EXTERNAL_REF]->(r) RETURN r.system` возвращает `elabftw`; `entity_resolver` для материала с известным MP-маппингом возвращает external MP `material_id`.

---

### 20.4 Интеграция eLabFTW через REST API v2

- [ ] Реализовать `kg_connectors/eln/elabftw_client.py` поверх `elabapi-python` (или прямых вызовов `GET {base}/api/v2/...` с заголовком `Authorization: <api_key>`), с поддержкой TLS-verify и пагинации `limit`/`offset`.
- [ ] Реализовать чтение основных ресурсов eLabFTW API v2:
  - [ ] `experiments` — экспериментальные записи (title, body/HTML, metadata JSON, tags, timestamps, teams).
  - [ ] `items` (database/inventory) — инвентарь/образцы/реактивы.
  - [ ] `items_types` — типы инвентаря (для маппинга на `Material`/`Equipment`/`Sample`).
  - [ ] `uploads` — вложения (PDF/CSV/изображения) как источники для Docling-парсинга и Evidence.
  - [ ] `teams`/`users` — для маппинга на `ResearchTeam`/`Person`/`Lab`.
- [ ] Реализовать парсинг структурированных `metadata` (eLabFTW extra fields JSON) и извлечение доменных полей: material, processing operation, temperature, time, atmosphere, equipment, measured property/value/unit.
- [ ] Реализовать `to_canonical()` маппинг eLabFTW → KG (§8.2):
  - [ ] `experiment` → `(:Experiment)`, связать `(:Paper|:Experiment)-[:REPORTS]->` при необходимости, `(:Experiment)-[:PERFORMED_BY]->(:ResearchTeam)`.
  - [ ] `item` (образец) → `(:Sample)-[:HAS_MATERIAL]->(:Material)`; item типа «оборудование» → `(:Equipment)`; связать `(:Experiment)-[:USES_SAMPLE]->(:Sample)` по links между experiment и item.
  - [ ] processing extra-fields → `(:ProcessingRegime)-[:HAS_STEP]->(:ProcessingStep)-[:HAS_PARAMETER]->(:Parameter)`.
  - [ ] measurement extra-fields → `(:Experiment)-[:MEASURED]->(:Measurement)-[:OF_PROPERTY]->(:Property)`, `(:Measurement)-[:HAS_UNIT]->(:Unit)`.
- [ ] Для каждой перенесённой записи создать `Evidence` (§8.3) с `source_type: metadata`, `extractor: "elabftw_connector_v1"`, ссылкой на eLabFTW entity URL и `HAS_EXTERNAL_REF` на `ExternalRef{system:'elabftw'}`.
- [ ] Прогнать `uploads` (PDF/DOCX) через существующий ingestion pipeline (§9 Step 2, Docling Serve) так, чтобы вложения eLabFTW стали `Document`/`Chunk`/`Evidence` с обратной ссылкой на исходный experiment.
- [ ] Реализовать инкрементальный синк по `modified_at` (cursor), с сохранением курсора в Postgres (source registration, §9.2 Step 1).
- [ ] Нормализовать единицы измерений через `pint` (§9.2 Step 5), включая HV/HRC/MPa/GPa mappings.

**Критерий приёмки:** против локального eLabFTW (docker-контейнер, см. 20.12) синк переносит ≥1 experiment + ≥1 inventory item в Neo4j; Cypher `MATCH (e:Experiment)-[:MEASURED]->(:Measurement)-[:SUPPORTED_BY]->(ev:Evidence {extractor:'elabftw_connector_v1'}) RETURN count(*)` > 0; повторный синк не создаёт дублей; каждая созданная сущность имеет `HAS_EXTERNAL_REF` c валидным `external_url`.

---

### 20.5 Интеграция openBIS через REST API (pybis)

- [ ] Реализовать `kg_connectors/lims/openbis_client.py` поверх `pybis` (`Openbis(url).login(user, pw)`), с re-login по истечению токена и TLS-verify.
- [ ] Реализовать чтение иерархии openBIS:
  - [ ] `spaces` → маппинг на `Lab`/`Project`.
  - [ ] `projects` → `(:Project)`.
  - [ ] `experiments`/`collections` → `(:Experiment)` (или `Dataset` для коллекций данных).
  - [ ] `samples`/`objects` (с их property-types) → `(:Sample)` и связи `HAS_MATERIAL`/`PROCESSED_BY`.
  - [ ] `datasets` (с файлами в DSS) → `(:Dataset)` и загрузка файлов для парсинга.
  - [ ] `property_types`/`vocabularies` — как словарь для маппинга openBIS property на canonical `Property`.
- [ ] Реализовать `to_canonical()` маппинг openBIS → KG (§8.2), аналогично 20.4, с учётом openBIS property-type кодов (material composition, processing params, measured properties).
- [ ] Скачивать файлы dataset из openBIS Data Store Server (DSS) и прогонять через Docling (§9 Step 2) для генерации `Document`/`Evidence`.
- [ ] Создавать `Evidence` с `source_type: metadata`, `extractor: "openbis_connector_v1"` и `HAS_EXTERNAL_REF{system:'openbis'}` (используя permId openBIS как `external_id`).
- [ ] Реализовать инкрементальный синк по openBIS `registrationDate`/`modificationDate` с cursor в Postgres.
- [ ] Нормализовать единицы через `pint` и словарь HV/HRC/MPa/GPa (§9.2 Step 5).

**Критерий приёмки:** unit-тест `test_openbis_mapping` на замоканном ответе pybis корректно строит подграф `Space→Project→Experiment→Sample→Material`; интеграционный тест (при доступном openBIS demo-инстансе или записанных VCR-кассетах) переносит ≥1 sample с permId, устанавливает `HAS_EXTERNAL_REF{system:'openbis'}` и не дублирует при повторе.

---

### 20.6 Materials Project API + pymatgen: канонические материалы и свойства

- [ ] Реализовать `kg_connectors/materials/mp_client.py` поверх `mp-api` (`MPRester(api_key)`), с батч-запросами и обработкой rate-limit/quotas.
- [ ] Реализовать выборку по формуле/химсистеме материалов, встречающихся в графе: для каждого canonical `Material`/`Composition` вызывать `mpr.materials.summary.search(formula=..., chemsys=...)`.
- [ ] Извлекать канонические свойства из MP `summary`/тематических эндпоинтов и маппить на `Property`/`Measurement` (с `source_type: metadata`, `extractor: "materials_project_v1"`):
  - [ ] структурные: `structure`, `symmetry`, `spacegroup`, `density`, `volume`.
  - [ ] термодинамика: `formation_energy_per_atom`, `energy_above_hull`, `is_stable`.
  - [ ] электронные: `band_gap`, `is_metal`.
  - [ ] механические (где доступны): `bulk_modulus`, `shear_modulus`, `elastic tensor`.
  - [ ] `material_id` (mp-xxxxx) сохранять как `ExternalRef{system:'materials_project'}`.
- [ ] Использовать `pymatgen` для канонизации состава/формулы:
  - [ ] `Composition(formula)` → reduced formula, anonymized formula, элементы и их доли → заполнять `(:Composition)-[:CONTAINS_ELEMENT]->(:ChemicalElement)` с fraction.
  - [ ] нормализовать пользовательские/литературные обозначения материала (например «Al-Cu 2024») к каноническому составу перед матчингом на MP (fallback на Splink, §9.2 Step 6).
  - [ ] использовать `pymatgen.core.periodic_table.Element` для валидации элементов и заполнения свойств элементов.
- [ ] Пометить MP-происхождённые свойства как reference/canonical (флаг `provenance: external_db`), чтобы gap-analysis (§11) и verifier (§7.5) отличали их от извлечённых из литературы.
- [ ] Кэшировать ответы MP в MinIO/Postgres по `(material_id, endpoint, mp_api_version)` для воспроизводимости и экономии quota.
- [ ] Реализовать units-normalization для MP-величин через `pint` (eV, GPa, g/cm³ и т.д.), сохраняя `value_raw`/`value_normalized` (§9.2 Step 5).
- [ ] Экспонировать MP `material_id` в `external_ids` canonical материала для использования agent-нодой `entity_resolver` (§7.3, «Materials Project / internal catalog IDs where available»).

**Критерий приёмки:** для тестовой формулы (например `SiO2`) коннектор создаёт/обновляет `Material` с `HAS_EXTERNAL_REF{system:'materials_project', external_id:'mp-...'}` и минимум 3 `Measurement`-узла с `provenance=external_db`; `pymatgen`-канонизация формулы покрыта unit-тестом (reduced formula + элементы совпадают с ожидаемыми); повторный вызов берёт из кэша (проверяется отсутствием сетевого вызова в тесте).

---

### 20.7 Обогащение графа из MatKG

- [ ] Реализовать `kg_connectors/enrichment/matkg_loader.py`: загрузка датасета MatKG (entity–relation–entity триплеты, CSV/parquet) из `MATKG_DATA_PATH` (данные скачиваются отдельно, путь из конфигурации).
- [ ] Реализовать нормализацию MatKG-сущностей (materials, properties, applications, characterization methods, synthesis) и маппинг их типов на canonical labels (`Material`, `Property`, `Method`, `Equipment`).
- [ ] Реализовать связывание MatKG-сущностей с существующими canonical узлами через crosswalk (20.3): точный/fuzzy матч имён + Splink; несматченные добавлять как `alias`/candidate, а не как новые дубли.
- [ ] Импортировать релевантные MatKG-связи как обогащающие рёбра графа (например material–property co-occurrence) с обязательным `Evidence{source_type: metadata, extractor: "matkg_v1", confidence: <из MatKG>}` и `HAS_EXTERNAL_REF{system:'matkg'}`.
- [ ] Ограничить импорт по confidence/поддержке (threshold в конфиге), чтобы не заливать граф шумом; вести счётчики принятых/отклонённых триплетов.
- [ ] Отделять MatKG-обогащение флагом `provenance: literature_kg`, чтобы не смешивать с first-party extraction.

**Критерий приёмки:** загрузка sample-подмножества MatKG (например 1000 триплетов) добавляет обогащающие рёбра с прикреплённым `Evidence{extractor:'matkg_v1'}`; ни один существующий reviewed-узел не перезаписан; отчёт синка выводит число accepted/rejected триплетов и число сматченных на canonical.

---

### 20.8 Обогащение через Matscholar (NER + нормализация)

- [ ] Реализовать `kg_connectors/enrichment/matscholar_ner.py` поверх `matscholar` (или REST API Matscholar), возвращающий распознанные сущности материаловедения: materials (MAT), properties (PRO), applications (APL), characterization methods (CMT), synthesis (SMT), descriptors (DSC), phase labels (SPL).
- [ ] Интегрировать Matscholar NER как дополнительный extractor в `packages/kg_extractors/` рядом с GLiNER/LlamaIndex: прогонять по `Chunk`/`Paragraph` из ingestion pipeline (§9 Step 4) для повышения recall на материаловедческих терминах.
- [ ] Использовать Matscholar normalization (нормализованные формулы/материалы) для маппинга извлечённых mention на canonical `Material` через crosswalk (20.3).
- [ ] Каждое извлечение сопровождать `Evidence{source_type: paragraph, extractor: "matscholar_ner_v1", model: "matscholar", char_start/char_end}` (§8.3) со span-координатами.
- [ ] Добавить конфиг-флаг для включения/отключения Matscholar в extraction-цепочке и метрику вклада (сколько mention добавил Matscholar сверх базового экстрактора).

**Критерий приёмки:** на тестовом абзаце с материаловедческими терминами Matscholar-экстрактор возвращает ≥1 MAT и ≥1 PRO сущность со span-координатами; извлечения записываются как `Evidence{extractor:'matscholar_ner_v1'}` с непустыми `char_start/char_end`; отключение флага исключает Matscholar из пайплайна (проверено тестом).

---

### 20.9 Материаловедческие NER/эмбеддинги: MatBERT/MatSciBERT + MatEntityRecognition (§22, §9.2 Step 4/6)

- [ ] Подготовить модели (см. 20.1): `MatBERT` (веса из `lbnlp/MatBERT`) и `MatSciBERT` (`m3rg-iitd/matscibert`); зафиксировать способ загрузки весов и пути `MATBERT_MODEL_PATH`/`MATSCIBERT_MODEL` в README пакета `packages/kg_extractors/`.
- [ ] Реализовать `packages/kg_extractors/materials/matbert_embed.py`: загрузка MatBERT/MatSciBERT (`transformers`) и выдача контекстных эмбеддингов/классификаций для материаловедческого текста (§9.2 Step 4 «MatBERT/MatSciBERT embeddings/classifiers where useful»).
- [ ] Реализовать `packages/kg_extractors/materials/mat_entity_recognition.py` поверх `MatEntityRecognition` (CederGroupHub) — доменный NER материалов/операций синтеза; прогонять по `Chunk`/`Paragraph` (§9 Step 4) как дополнительный extractor рядом с GLiNER/Matscholar для повышения recall.
- [ ] Использовать MatBERT/MatSciBERT-эмбеддинги для (a) candidate-generation/blocking в entity resolution (§9.2 Step 6, вход для Splink по семантической близости) и (b) маппинга извлечённых mention на canonical `Material`/`Property` через crosswalk (20.3).
- [ ] Каждое извлечение сопровождать `Evidence{source_type: paragraph, extractor: "matentityrecognition_v1"|"matbert_ner_v1", model: "matbert"|"matscibert", char_start/char_end}` (§8.3) со span-координатами; не создавать граф-факт без span (§9.2 Step 4 «no source span → no graph fact»).
- [ ] Добавить конфиг-флаги `MATBERT_ENABLED`/`MATENTITYRECOGNITION_ENABLED` для включения/отключения в extraction-цепочке и метрику вклада (сколько mention добавила каждая модель сверх базового экстрактора и Matscholar).
- [ ] Кэшировать эмбеддинги (MinIO/Postgres) по `(text_hash, model_revision)` для воспроизводимости и экономии GPU.

**Критерий приёмки:** на тестовом материаловедческом абзаце MatEntityRecognition возвращает ≥1 материал-сущность со span-координатами, записанную как `Evidence{extractor:'matentityrecognition_v1'}` с непустыми `char_start/char_end`; MatBERT/MatSciBERT выдаёт эмбеддинг фиксированной размерности (покрыто unit-тестом), используемый в candidate-generation entity resolution; отключение флагов исключает обе модели из пайплайна (проверено тестом).

---

### 20.10 Propnet: вывод/дополнение свойств материалов

- [ ] Реализовать `kg_connectors/enrichment/propnet_deriver.py` поверх `propnet` (граф свойств + модели), принимающий известные свойства материала (в т.ч. из MP, 20.6) и выводящий производные свойства через propnet-модели.
- [ ] Смаппить propnet symbols на canonical `Property` vocabulary (§8, `Property`); вести таблицу соответствия propnet symbol ↔ `property:*` в `packages/kg_schema/`.
- [ ] Для каждого выведенного свойства создавать `(:Measurement)` с `provenance: derived`, `Evidence{source_type: metadata, extractor: "propnet_v1"}`, и записывать цепочку вывода (модель propnet + входные свойства) в поле `derivation`.
- [ ] Не перезаписывать измеренные/reviewed значения выведенными: derived-значения хранить как отдельные `Measurement` с явной пометкой и связывать с источниками-входами.
- [ ] Флагировать противоречия: если propnet-выведенное значение расходится с измеренным сверх допуска, создавать `(:Contradiction)` / `(:Claim)-[:CONTRADICTS]->(:Claim)` (§8.2) для рассмотрения в curation (§12).
- [ ] Обеспечить units-consistency выведенных свойств через `pint`.

**Критерий приёмки:** для материала с известными входными свойствами propnet выводит ≥1 производное свойство, создаёт `Measurement{provenance:'derived'}` с заполненным `derivation`; расхождение с измеренным значением сверх допуска порождает `Contradiction`-узел (покрыто тестом `test_propnet_contradiction`).

---

### 20.11 Оркестрация в ingestion pipeline (Dagster) и source registration

- [ ] Зарегистрировать каждый коннектор как источник в source registration (§9.2 Step 1): `source id`, `source type` (`eln|lims|materials_db|literature_kg`), `owner/lab`, `access policy`, `ingestion job id`, `version`, `file/payload hash`.
- [ ] Создать Dagster assets в `infra/dagster/` для: `elabftw_sync`, `openbis_sync`, `materials_project_enrich`, `matkg_load`, `matscholar_enrich`, `materials_ner_enrich` (MatBERT/MatEntityRecognition), `propnet_derive` — с зависимостями (например `materials_project_enrich` → `propnet_derive`).
- [ ] Настроить Dagster schedules/sensors для инкрементальных синков ELN/LIMS (например ежедневно) и on-demand запуска обогащений.
- [ ] Обеспечить, чтобы результат коннекторов проходил стандартные шаги пайплайна §9: extraction (Step 4, включая MatBERT/MatEntityRecognition/Matscholar) → normalize (Step 5) → entity resolution Splink (Step 6) → schema validation Pydantic/LinkML → upsert Neo4j (Step 7) → indexing Qdrant/OpenSearch (Step 8) → gap scan.
- [ ] Индексировать перенесённые experiments/samples/claims в Qdrant/OpenSearch с payload-полями §9.2 Step 8 (`doc_id`, `entity_ids`, `material_ids`, `property_ids`, `processing_operation`, `temperature_c`, `time_h`, `source_type`, `confidence`, `review_status`).
- [ ] Эмитить lineage/metadata из Dagster в DataHub/OpenMetadata (§16 Phase 8): source ownership (lab), связь external source → dataset → граф-сущности.
- [ ] Реализовать dead-letter/квара­нтин для записей, не прошедших schema validation, с возможностью ручного разбора.

**Критерий приёмки:** в Dagster UI видны 7 assets с корректным asset-graph; ручной запуск `elabftw_sync` материализует downstream-assets вплоть до `gap scan`; каждый источник имеет запись в source registry с owner и версией; в DataHub/OpenMetadata появляется lineage от external source до созданных узлов графа (§16 Phase 8: «every document/source has owner and lineage»).

---

### 20.12 API Gateway: endpoints для experiments/inventory (§6.2)

- [ ] Реализовать в `apps/api-gateway/` endpoints §6.2 с опорой на данные из ELN/LIMS/materials:
  - [ ] `GET /api/v1/experiments` — список с фильтрами material/processing operation/temperature/time/atmosphere/equipment/property (§5.2.5).
  - [ ] `GET /api/v1/experiments/{experiment_id}` — деталь эксперимента с samples/regime/measurements/evidence и `external_refs`.
  - [ ] `POST /api/v1/experiments/query` — структурный запрос (формат §6.2 `material_regime_property`), возвращающий `experiments[]`, `gaps[]`, `citations[]`.
- [ ] Включить в DTO эксперимента источник происхождения (`origin: elabftw|openbis|literature|manual`) и ссылку на оригинал во внешней системе.
- [ ] Обеспечить, чтобы Experiment Explorer (§5.2.5) мог экспортировать CSV/JSON и помечать записи verified/needs review, отражая review_status в graph.
- [ ] Добавить в docker-compose (`infra/docker-compose.yml`) сервисы для локального dev-теста коннекторов: `elabftw` (образ `elabftw/elabimg`) + его MySQL, и (опционально) openBIS demo/mock; прописать env для connector-сервиса.

**Критерий приёмки:** `GET /api/v1/experiments?material=Al-Cu&property=hardness` возвращает эксперименты, включающие записи, импортированные из eLabFTW, с полем `origin` и рабочей ссылкой на оригинал; `POST /api/v1/experiments/query` для запроса из §6.2 возвращает валидный ответ по контракту (`experiments`, `gaps`, `citations`); контрактный тест OpenAPI-схемы проходит.

---

### 20.13 Тестирование, наблюдаемость и приёмка раздела

- [ ] Написать unit-тесты маппинга `to_canonical()` для каждого коннектора (eLabFTW, openBIS, MP, MatKG, Matscholar, Propnet) и материаловедческих NER (MatBERT/MatEntityRecognition) на fixture-ответах.
- [ ] Записать VCR/replay-кассеты (например `pytest-recording`/`vcrpy`) для сетевых вызовов eLabFTW/openBIS/MP, чтобы CI не требовал живых сервисов.
- [ ] Написать интеграционный тест end-to-end: поднять eLabFTW + Neo4j в docker-compose, засеять 2 experiment + 2 inventory item, запустить `elabftw_sync`, проверить граф и evidence-цепочки.
- [ ] Написать тест идемпотентности: двойной синк каждого коннектора не увеличивает число узлов/рёбер (кроме `fetched_at`).
- [ ] Добавить OpenTelemetry-трейсинг (§13.2 `opentelemetry-sdk`) на connector-джобы: span на запись, атрибуты system/external_id/latency; экспорт метрик (records_synced, records_skipped, merge_auto/merge_review, errors).
- [ ] Добавить в `packages/kg_eval/` golden-проверки: набор известных external_id → canonical mappings, чтобы регресс crosswalk детектировался автоматически.
- [ ] Обновить документацию `packages/kg_connectors/README.md` и `packages/kg_extractors/README.md`: как получить API-ключи (Materials Project, eLabFTW, Matscholar), где брать веса MatBERT/MatSciBERT и данные MatKG/Propnet, как запустить каждый коннектор и материаловедческие NER.

**Критерий приёмки:** `pytest packages/kg_connectors/`, `pytest packages/kg_extractors/tests/materials/` и `pytest apps/ingestion-service/tests/connectors/` зелёные в CI без обращения к внешней сети (через кассеты/локальные модели); e2e-тест eLabFTW→Neo4j проходит; connector-джобы экспортируют OTel-трейсы и метрики; golden crosswalk-проверка проходит для всех эталонных пар. После выполнения всех задач раздела внешние лабораторные системы и materials-data источники полностью интегрированы: эксперименты/инвентарь из eLabFTW/openBIS и канонические материалы/свойства из MP/pymatgen/MatKG/Matscholar/Propnet/MatBERT/MatEntityRecognition присутствуют в графе с evidence, external-ref маппингом и lineage.


---


## 21. Репозитории для клонирования и вендоринга

Этот раздел фиксирует ИСЧЕРПЫВАЮЩИЙ план интеграции всех OSS-компонентов из §22 (OSS references), §21 (Рекомендуемый порядок выбора библиотек) и ключевых pip/npm-зависимостей из §13.2/§14.1 в монорепо, структура которого задана в §6.1 (`apps/`, `packages/`, `infra/`). Для каждого репозитория определяется: назначение, git-команда клонирования, способ интеграции (service / library-dependency / git-submodule / vendored-snapshot / reference-fork), лицензия (с обязательной проверкой) и конкретная выполнимая задача интеграции. Раздел зависит от: §13.1 (Docker Compose), §13.2 (Python packages), §14.1 (Frontend packages), Phase 0 (Repo, infra, skeleton) и Phase 8 (Metadata, lineage, governance).

Соглашения о способах интеграции и месте в монорепо:

- **service** — запускается как контейнер из готового Docker image в `infra/docker-compose.yml`, собственный код не клонируется в репо (только конфиги в `infra/<service>/`).
- **library-dependency** — подключается как пакет через `pip`/`uv` (в `pyproject.toml`/`packages/*/pyproject.toml`) или `npm`/`pnpm` (в `apps/frontend/package.json`); исходники не хранятся в монорепо.
- **git-submodule** — добавляется как git submodule под `third_party/<name>/` с пиннингом на конкретный commit SHA (нужен исходный код, но без модификаций).
- **vendored-snapshot** — снимок исходников/данных копируется в `vendor/<name>/` или в `packages/<pkg>/vendor/` с сохранением LICENSE (нужны локальные правки или отсутствует пакет в реестре).
- **reference-fork** — клонируется в `reference/<name>/` (в `.gitignore`, не шипается) как источник паттернов/кода для собственной реализации.

### 21.1 Общая политика вендоринга, раскладка и служебная инфраструктура

- [x] Создать директории верхнего уровня монорепо для сторонних артефактов: `third_party/` (git submodules), `vendor/` (vendored snapshots), `reference/` (reference-forks, добавить в `.gitignore`), а также `infra/<service>/` под конфиги контейнерных сервисов.
- [x] Создать файл-манифест `third_party/REPOS.yaml` (машиночитаемый) со списком ВСЕХ репозиториев из §22, §21 и ключевых зависимостей §13.2/§14.1, где для каждой записи заполнены поля: `name`, `group`, `git_url`, `pin` (commit SHA или version tag), `integration` (service|dependency|submodule|vendored|reference-fork), `license`, `monorepo_path`, `purpose`, `status`.
  - [x] Написать скрипт-валидатор `scripts/validate_repos_manifest.py`, который падает, если у записи не заполнены обязательные поля или `pin` не пиннится на SHA/tag.
- [x] Настроить `.gitmodules` для всех репозиториев со способом интеграции `git-submodule`, с фиксацией на конкретных commit SHA (не на плавающих ветках).
- [x] Создать файл `THIRD_PARTY_NOTICES.md` в корне репо, генерируемый скриптом `scripts/collect_licenses.py`, который агрегирует LICENSE-файлы всех зависимостей/submodules/vendored-снапшотов.
- [x] Настроить автоматизацию обновления зависимостей: `renovate.json` (или Dependabot) с группировкой по зонам (agent/RAG, graph-db, frontend, materials) и правилом «не автомёржить major-версии».
- [x] Задокументировать policy пиннинга: pip/npm-зависимости — точные версии + lockfile (`uv.lock`/`pnpm-lock.yaml`); submodules/vendored — commit SHA; Docker images — конкретный immutable tag или digest вместо `:latest`.
- [x] Заменить все `:latest` теги из §13.1 на конкретные версии/digest в `infra/docker-compose.yml` (docling-serve, qdrant, opensearch, minio) и задокументировать матрицу версий.

**Критерий приёмки:** `python scripts/validate_repos_manifest.py` проходит для всех записей; `git submodule status` показывает все submodules на фиксированных SHA; `THIRD_PARTY_NOTICES.md` содержит лицензию каждого репозитория из таблицы 21.2; в `docker-compose.yml` отсутствуют `:latest`.

### 21.2 Сводная таблица OSS-репозиториев

- [x] Внести в `third_party/REPOS.yaml` и продублировать в этой таблице ВСЕ репозитории ниже; каждая строка имеет соответствующую задачу интеграции в подзонах 21.3–21.12.

| Репозиторий | Назначение | git clone | Способ / место в монорепо | Лицензия (проверить) |
|---|---|---|---|---|
| **Agent / RAG / KG extraction** | | | | |
| FastAPI | REST API Gateway + agent-service (§6.1,§6.2) | `git clone https://github.com/fastapi/fastapi` | dependency (`fastapi`,`uvicorn[standard]`,`pydantic`,`pydantic-settings`) → `apps/api-gateway`, `apps/agent-service` | MIT |
| LangGraph | Оркестрация stateful-агента (§7) | `git clone https://github.com/langchain-ai/langgraph` | dependency (`langgraph`) → `apps/agent-service` | MIT |
| LlamaIndex | PropertyGraphIndex, graph/vector retrievers (§9,§10) | `git clone https://github.com/run-llama/llama_index` | dependency (`llama-index`, `-graph-stores-neo4j`, `-vector-stores-qdrant`) → `packages/kg_extractors`, `packages/kg_retrievers` | MIT |
| Microsoft GraphRAG | Community summaries, global questions (Mode C, §10.1) | `git clone https://github.com/microsoft/graphrag` | dependency + reference-fork → `packages/kg_retrievers`, `reference/graphrag` | MIT |
| Neo4j LLM Graph Builder | Reference для extraction pipeline UI/логики | `git clone https://github.com/neo4j-labs/llm-graph-builder` | reference-fork → `reference/llm-graph-builder` | Apache-2.0 |
| Haystack | Deployable RAG pipelines (optional) | `git clone https://github.com/deepset-ai/haystack` | dependency (`haystack-ai`) → `apps/search-service` | Apache-2.0 |
| Hayhooks | Deploy Haystack pipelines как REST (optional) | `git clone https://github.com/deepset-ai/hayhooks` | dependency/service → `infra/hayhooks` | Apache-2.0 |
| **Extraction / NER / embedding models** | | | | |
| GLiNER | Zero-shot NER для mentions (§9.2 Step 4, Phase 2) | `git clone https://github.com/urchade/GLiNER` | dependency (`gliner`) → `packages/kg_extractors` | Apache-2.0 |
| SciSpacy | Опциональный NER-хелпер для научного текста (§9.2 Step 4) | `git clone https://github.com/allenai/scispacy` | optional dependency (`scispacy`) → `packages/kg_extractors` | Apache-2.0 |
| sentence-transformers | Dense-эмбеддинги чанков (§9.2 Step 8, §10.2) | `git clone https://github.com/UKPLab/sentence-transformers` | dependency (`sentence-transformers`) → `apps/search-service` | Apache-2.0 |
| FastEmbed | Быстрые dense/sparse эмбеддинги для Qdrant (§9.2 Step 8) | `git clone https://github.com/qdrant/fastembed` | dependency (`fastembed`) → `apps/search-service` | Apache-2.0 |
| **Document parsing** | | | | |
| Docling | Парсинг PDF/DOCX/PPTX (§9.2 Step 2) | `git clone https://github.com/docling-project/docling` | dependency (`docling`) → `apps/ingestion-service` | MIT |
| Docling Serve | HTTP-сервис конвертации документов | `git clone https://github.com/docling-project/docling-serve` | service (`quay.io/docling-project/docling-serve`) → `infra/docker-compose.yml` | MIT |
| Marker | Fallback PDF→markdown парсер | `git clone https://github.com/datalab-to/marker` | optional dependency/service → `infra/marker` | GPL-3.0 / custom (FLAG) |
| Unstructured | Fallback парсер разных форматов | `git clone https://github.com/Unstructured-IO/unstructured` | optional dependency (`unstructured`) → `apps/ingestion-service` | Apache-2.0 |
| **Graph DB / search** | | | | |
| Neo4j | Graph storage, Cypher, vector index (§8) | `git clone https://github.com/neo4j/neo4j` | service (`neo4j:2026.05-community`) → `infra/neo4j` | GPLv3 (community) |
| Neo4j GraphQL | GraphQL proxy (optional, §6.2) | `git clone https://github.com/neo4j/graphql` | optional dependency (JS) → `apps/api-gateway` | Apache-2.0 |
| Neo4j APOC | Утилиты/процедуры для Cypher | `git clone https://github.com/neo4j-contrib/neo4j-apoc-procedures` | plugin (`NEO4J_PLUGINS: [apoc]`) → `infra/neo4j/plugins` | Apache-2.0 |
| Neo4j Graph Data Science | Similarity/community/centrality (§10.1 Mode D) | `git clone https://github.com/neo4j/graph-data-science` | plugin → `infra/neo4j/plugins` | GPLv3 / source-available (FLAG) |
| Qdrant | Dense/sparse vector search (§9.2 Step 8) | `git clone https://github.com/qdrant/qdrant` | service (`qdrant/qdrant`) → `infra/qdrant` | Apache-2.0 |
| OpenSearch | BM25/facets/highlighting | `git clone https://github.com/opensearch-project/OpenSearch` | service (`opensearchproject/opensearch`) → `infra/opensearch` | Apache-2.0 |
| NetworkX | In-memory graph algorithms, proximity (§10.3,§11) | `git clone https://github.com/networkx/networkx` | dependency (`networkx`) → `packages/kg_retrievers` | BSD-3-Clause |
| ArangoDB | Alternative multi-model DB (запас) | `git clone https://github.com/arangodb/arangodb` | reference/evaluation → `reference/arangodb` | Apache-2.0 / BSL (FLAG) |
| Memgraph | Alternative graph DB (запас) | `git clone https://github.com/memgraph/memgraph` | reference/evaluation → `reference/memgraph` | BSL 1.1 (FLAG) |
| TypeDB | Alternative typed graph DB (запас) | `git clone https://github.com/typedb/typedb` | reference/evaluation → `reference/typedb` | source-available (FLAG) |
| **Frontend / visualization** | | | | |
| Reagraph | Основной graph explorer (§5.1,§14.2) | `git clone https://github.com/reaviz/reagraph` | dependency (`reagraph`) → `apps/frontend` | Apache-2.0 |
| Cytoscape.js | Advanced layouts / export figures | `git clone https://github.com/cytoscape/cytoscape.js` | dependency (`cytoscape`) → `apps/frontend` | MIT |
| Sigma.js | Large-graph WebGL rendering | `git clone https://github.com/jacomyal/sigma.js` | dependency (`sigma`) → `apps/frontend` | MIT |
| Graphology | In-memory graph model/algorithms | `git clone https://github.com/graphology/graphology` | dependency (`graphology`) → `apps/frontend` | MIT |
| React Force Graph | 3D wow-effect граф (optional) | `git clone https://github.com/vasturiano/react-force-graph` | dependency (`react-force-graph`) → `apps/frontend` | MIT |
| AntV G6 | Alternative graph engine (запас) | `git clone https://github.com/antvis/G6` | optional dependency → `apps/frontend` | MIT |
| Graphin | React-toolkit над G6 (запас) | `git clone https://github.com/antvis/Graphin` | optional dependency → `apps/frontend` | MIT |
| React Flow (xyflow) | LangGraph workflow / pipeline DAG UI | `git clone https://github.com/xyflow/xyflow` | dependency (`@xyflow/react`) → `apps/frontend` | MIT |
| Apache ECharts | Dashboards / gap matrix / charts (§5.2.7) | `git clone https://github.com/apache/echarts` | dependency (`echarts`,`echarts-for-react`) → `apps/frontend` | Apache-2.0 |
| Apache Superset | BI-дашборды (§21 optional) | `git clone https://github.com/apache/superset` | optional service → `infra/superset` | Apache-2.0 |
| **Entity resolution / cleaning** | | | | |
| Splink | Probabilistic entity linkage (§9.2 Step 6) | `git clone https://github.com/moj-analytical-services/splink` | dependency (`splink`) → `packages/kg_extractors`, `apps/curation-service` | MIT |
| Dedupe | Fallback дедупликация (optional) | `git clone https://github.com/dedupeio/dedupe` | optional dependency (`dedupe`) → `packages/kg_extractors` | MIT |
| OpenRefine | Reconciliation API / очистка каталогов | `git clone https://github.com/OpenRefine/OpenRefine` | service/tool → `infra/openrefine` | BSD-3-Clause |
| **Metadata / orchestration / lineage / eval** | | | | |
| Dagster | Ingestion asset graph/schedules (§9,§13.1) | `git clone https://github.com/dagster-io/dagster` | service + dependency (`dagster`) → `infra/dagster` | Apache-2.0 |
| Airbyte | Коннекторы источников (optional) | `git clone https://github.com/airbytehq/airbyte` | optional service → `infra/airbyte` | ELv2 / MIT (FLAG) |
| DataHub | Metadata catalog + lineage (Phase 8) | `git clone https://github.com/datahub-project/datahub` | service → `infra/datahub` | Apache-2.0 |
| OpenMetadata | Alternative metadata catalog (Phase 8) | `git clone https://github.com/open-metadata/OpenMetadata` | alternative service → `infra/openmetadata` | Apache-2.0 |
| Marquez | OpenLineage backend (optional) | `git clone https://github.com/MarquezProject/marquez` | optional service → `infra/marquez` | Apache-2.0 |
| Apache Atlas | Alternative governance (запас) | `git clone https://github.com/apache/atlas` | reference → `reference/atlas` | Apache-2.0 |
| MLflow | Experiment/model tracking (§13.2,§15) | `git clone https://github.com/mlflow/mlflow` | service + dependency (`mlflow`) → `infra/mlflow`, `packages/kg_eval` | Apache-2.0 |
| Ragas | RAG-метрики eval-харнесса (§15.2) | `git clone https://github.com/explodinggradients/ragas` | dependency (`ragas`) → `packages/kg_eval` | Apache-2.0 |
| DeepEval | LLM/answer eval-метрики (§15.2) | `git clone https://github.com/confident-ai/deepeval` | dependency (`deepeval`) → `packages/kg_eval` | Apache-2.0 |
| lakeFS | Версионирование данных (optional) | `git clone https://github.com/treeverse/lakeFS` | optional service → `infra/lakefs` | Apache-2.0 |
| DVC | Версионирование датасетов/моделей | `git clone https://github.com/iterative/dvc` | dependency (`dvc`) → root tooling | Apache-2.0 |
| **Scientific / materials helpers** | | | | |
| MatKG | Seed-онтология материалов | `git clone https://github.com/olivettigroup/MatKG` | vendored-snapshot → `packages/kg_schema/vendor/matkg` | verify (FLAG) |
| MatBERT | NER-модель для материалов | `git clone https://github.com/lbnlp/MatBERT` | model + reference → `packages/kg_extractors` (HF weights) | verify (FLAG) |
| MatEntityRecognition | Materials NER pipeline | `git clone https://github.com/CederGroupHub/MatEntityRecognition` | vendored/reference → `packages/kg_extractors/vendor/mer` | verify (FLAG) |
| Matscholar | Нормализация/поиск материалов | `git clone https://github.com/materialsintelligence/matscholar` | reference/dependency → `packages/kg_extractors` | verify (FLAG) |
| Propnet | Граф связей свойств материалов | `git clone https://github.com/materialsintelligence/propnet` | reference → `reference/propnet` | verify (FLAG) |
| Materials Project API | Обогащение данными MP | `git clone https://github.com/materialsproject/api` | dependency (`mp-api`) → `packages/kg_extractors` | modified BSD (FLAG) |
| pymatgen | Парсинг composition/structure (§13.2) | `git clone https://github.com/materialsproject/pymatgen` | dependency (`pymatgen`) → `packages/kg_schema`, `kg_extractors` | MIT |
| Pint | Нормализация физических единиц (§9.2 Step 5) | `git clone https://github.com/hgrecco/pint` | dependency (`pint`) → `packages/kg_extractors` | BSD-3-Clause |
| **Ontology governance (optional)** | | | | |
| LinkML | Schema/ontology modeling (§21 optional, §4.2) | `git clone https://github.com/linkml/linkml` | optional dependency (`linkml`) → `packages/kg_schema` | CC0-1.0 (FLAG) |
| Protégé | Ontology editor (§21 optional) | `git clone https://github.com/protegeproject/protege` | reference/tool → `reference/protege` | BSD-2-Clause |
| **Lab systems** | | | | |
| eLabFTW | ELN — источник экспериментов (§4.1) | `git clone https://github.com/elabftw/elabftw` | service integration via REST API → `apps/ingestion-service` | AGPL-3.0 (FLAG) |
| openBIS | LIMS/ELN — источник экспериментов | `git clone https://github.com/openbis` | service integration via REST API → `apps/ingestion-service` | Apache-2.0 |

**Критерий приёмки:** таблица содержит все репозитории из §22 (49 GitHub-ссылок, исключая docs-ссылку LlamaIndex PGI) плюс дополнительные OSS-компоненты из §21 recommended-списка (FastAPI, GLiNER, Apache Superset, LinkML, Protégé) и ключевые pip-зависимости из §13.2/§9.2 (SciSpacy, sentence-transformers, FastEmbed, NetworkX, Pint, Ragas, DeepEval); для каждой строки заполнены столбцы «git clone», «способ/место», «лицензия»; каждая строка имеет матчащуюся задачу интеграции в подзонах 21.3–21.12 и запись в `third_party/REPOS.yaml`.

### 21.3 Agent / RAG / KG extraction (+ NER / embedding models)

- [ ] **FastAPI** (dependency, MIT): добавить `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings` в `apps/api-gateway` и `apps/agent-service` (§6.1); реализовать health-endpoints (Phase 0) и endpoints из §6.2; OpenAPI-схема доступна на `/docs`, health-checks возвращают 200.
- [ ] **LangGraph** (dependency, MIT): добавить `langgraph` + `langchain-core` в `apps/agent-service/pyproject.toml`, реализовать StateGraph с нодами `preprocess_question`→`answer_synthesizer` из §7.5; smoke-тест собирает граф без ошибок.
- [ ] **LlamaIndex** (dependency, MIT): добавить `llama-index`, `llama-index-graph-stores-neo4j`, `llama-index-vector-stores-qdrant` в `packages/kg_extractors` и `packages/kg_retrievers`; реализовать `PropertyGraphIndex` поверх Neo4jPropertyGraphStore (docs https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/).
  - [ ] Проверить подключение GraphStore к Neo4j из docker-compose и VectorStore к Qdrant (integration-тест создаёт и читает узел).
- [ ] **Microsoft GraphRAG** (dependency + reference-fork, MIT): добавить `graphrag` в `packages/kg_retrievers`; клонировать `reference/graphrag` для reference пайплайна community-detection и global search (Mode C, §10.1); реализовать адаптер, отдающий community summaries в agent tool.
- [ ] **Neo4j LLM Graph Builder** (reference-fork, Apache-2.0): клонировать в `reference/llm-graph-builder` (в `.gitignore`); задокументировать в `docs/references/llm-graph-builder.md`, какие паттерны extraction/chunking/schema-mapping переиспользуются в `extraction-service` (§9.2 Step 4). Код НЕ шипается в prod.
- [ ] **Haystack** (dependency, Apache-2.0): добавить `haystack-ai` в `apps/search-service`; собрать минимальный hybrid retrieval pipeline как альтернативу; пометить как optional-feature флагом конфигурации.
- [ ] **Hayhooks** (dependency/service, Apache-2.0): добавить сервис `hayhooks` в `infra/docker-compose.yml` (optional profile) для деплоя Haystack-пайплайна как REST endpoint; health-check отвечает 200.
- [ ] **GLiNER** (dependency, Apache-2.0): добавить `gliner` в `packages/kg_extractors`; интегрировать zero-shot NER для mentions материалов/установок/свойств в extraction Step 4 (§9.2, Phase 2 «integrate GLiNER for entity mentions»); зафиксировать конкретную GLiNER-модель/версию в конфиге; тест извлекает entity-spans на seed-чанке.
- [ ] **SciSpacy** (optional dependency, Apache-2.0): добавить `scispacy` как опциональный NER-хелпер для научного текста (§9.2 Step 4 «SciSpacy only as helper … if needed») за конфиг-флагом; задокументировать критерий включения; тест разбирает научное предложение при включённом флаге.

**Критерий приёмки:** `apps/agent-service` и `apps/api-gateway` поднимаются на FastAPI и проходят health-checks (Phase 0); `apps/agent-service` собирает LangGraph workflow; PropertyGraphIndex читает/пишет в Neo4j+Qdrant в integration-тесте; GLiNER извлекает spans на seed-чанке; GraphRAG-адаптер возвращает community summary на тестовом корпусе; `reference/llm-graph-builder` присутствует и задокументирован, но исключён из сборки prod-образов; SciSpacy выключен по умолчанию.

### 21.4 Document parsing

- [ ] **Docling Serve** (service, MIT): добавить сервис `docling` в `infra/docker-compose.yml` (образ `quay.io/docling-project/docling-serve`, порт 5001, `DOCLING_SERVE_ENABLE_UI: "1"`) согласно §13.1; из `apps/ingestion-service` вызывать convert API и сохранять markdown/JSON в MinIO (§9.2 Step 2).
- [ ] **Docling** (dependency, MIT): добавить `docling` в `apps/ingestion-service/pyproject.toml` для локального fallback-парсинга без сервиса; unit-тест парсит seed-PDF и возвращает таблицы.
- [ ] **Marker** (optional dependency/service, GPL-3.0/custom — LICENSE FLAG): вынести за отдельный docker-compose profile `parsers-alt`; ПЕРЕД включением выполнить license-review (коммерческие ограничения) и зафиксировать решение в `docs/licenses/marker.md`; интегрировать как альтернативный парсер только после approval.
- [ ] **Unstructured** (optional dependency, Apache-2.0): добавить `unstructured` в `apps/ingestion-service` как fallback для форматов, не покрытых Docling; тест обрабатывает `.docx` и `.pptx`.

**Критерий приёмки:** upload PDF через `POST /api/v1/documents/upload` проходит через Docling Serve и сохраняет parsed-артефакты в MinIO; fallback-парсеры доступны за feature-флагом; для Marker зафиксирован license-review и он выключен по умолчанию.

### 21.5 Graph DB / search (+ embeddings / graph-algo)

- [ ] **Neo4j** (service, GPLv3-community): добавить сервис `neo4j` (образ `neo4j:2026.05-community`, порты 7474/7687, `NEO4J_AUTH`, `NEO4J_PLUGINS: [apoc]`) в `infra/docker-compose.yml`; применить constraints/indexes из §8.4 через `infra/neo4j/init.cypher`.
- [ ] **Neo4j APOC** (plugin, Apache-2.0): включить через `NEO4J_PLUGINS`; проверить наличие процедур `apoc.*` запросом `CALL apoc.help('apoc')`.
- [ ] **Neo4j Graph Data Science** (plugin, GPLv3/source-available — LICENSE FLAG): смонтировать GDS jar в `infra/neo4j/plugins`; выполнить license-review для community/enterprise ограничений; реализовать graph algorithms Mode D (§10.1) — similarity/community/centrality; smoke-тест `CALL gds.version()`.
- [ ] **Neo4j GraphQL** (optional dependency, Apache-2.0): при необходимости GraphQL proxy (§6.2) добавить `@neo4j/graphql` в отдельный node-сервис или `apps/api-gateway`; сгенерировать schema из KG-модели; пометить optional.
- [ ] **Qdrant** (service, Apache-2.0): добавить сервис `qdrant` (порты 6333/6334) в `infra/docker-compose.yml`; создать коллекции для dense+sparse векторов из `apps/search-service` (§9.2 Step 8); health-check `GET /healthz`.
- [ ] **OpenSearch** (service, Apache-2.0): добавить сервис `opensearch` (single-node, security disabled, порт 9200) в `infra/docker-compose.yml`; создать индекс с BM25/facets/highlighting из `apps/search-service`; smoke-тест keyword search возвращает документ.
- [ ] **sentence-transformers + FastEmbed** (dependency, Apache-2.0): добавить `sentence-transformers` и `fastembed` в `apps/search-service`; генерировать dense- и sparse-эмбеддинги чанков/строк таблиц/claims для Qdrant-коллекций (§9.2 Step 8, hybrid formula §10.2); зафиксировать конкретную embedding-модель и её версию в конфиге; тест эмбеддит чанк и апсертит вектор в Qdrant.
- [ ] **NetworkX** (dependency, BSD-3-Clause): добавить `networkx` в `packages/kg_retrievers` для in-memory graph-алгоритмов и graph-proximity score (§10.3) и gap-скана (§11), когда не задействован GDS; unit-тест считает proximity на игрушечном графе.
- [ ] **ArangoDB / Memgraph / TypeDB** (reference/evaluation — LICENSE FLAG для Memgraph BSL и TypeDB): НЕ деплоить в MVP; создать `docs/evaluation/graph-db-alternatives.md` со сравнением и критериями, при которых их берут (§4.1 «Large graph fallback», §5.1); клонировать в `reference/` только при проведении evaluation.

**Критерий приёмки:** `docker compose up` поднимает neo4j+qdrant+opensearch; constraints из §8.4 применены (проверка `SHOW CONSTRAINTS`); APOC и GDS доступны; эмбеддинг-пайплайн (sentence-transformers/fastembed) апсертит dense+sparse векторы; `POST /api/v1/search/keyword` и `POST /api/v1/search/vector` возвращают результаты на seed-данных; NetworkX-proximity считается в unit-тесте.

### 21.6 Frontend / visualization

- [ ] **Reagraph** (dependency, Apache-2.0): добавить `reagraph` в `apps/frontend/package.json`; реализовать Graph Explorer (§5.2.3) и компонент из §14.2, рендерящий graph payload формата §5.3; проверить рендер seed-графа (Phase 0 acceptance «Reagraph renders sample graph»).
- [ ] **Sigma.js + Graphology** (dependency, MIT): добавить `sigma` и `graphology`; реализовать large-graph/overview режим (§5.1) для корпуса из тысяч узлов; тест рендерит граф ≥5000 узлов без зависания UI.
- [ ] **Cytoscape.js** (dependency, MIT): добавить `cytoscape`; реализовать альтернативный view для dense subgraphs и export графа-фигуры (§5.1).
- [ ] **React Flow (@xyflow/react)** (dependency, MIT): добавить `@xyflow/react`; использовать ТОЛЬКО для отображения LangGraph workflow и pipeline DAG (§5.1 таблица «не для KG»), не как graph explorer.
- [ ] **Apache ECharts** (dependency, Apache-2.0): добавить `echarts` + `echarts-for-react`; реализовать Gap Dashboard и coverage-матрицу (§5.2.7).
- [ ] **React Force Graph** (optional dependency, MIT): добавить `react-force-graph` за feature-флагом для 3D wow-демо (§5.1 «Optional / для wow-effect»).
- [ ] **AntV G6 / Graphin** (optional dependency, MIT): держать в запасе; задокументировать в `docs/frontend/graph-libs.md` условия перехода (§5.1 таблица альтернатив); не включать в prod-bundle по умолчанию.
- [ ] **Apache Superset** (optional service, Apache-2.0): при необходимости внешних BI-дашбордов (§21 optional «Superset for dashboards») добавить `superset` в `infra/docker-compose.yml` за optional profile как альтернативу встроенным ECharts-дашбордам; задокументировать выбор ECharts-vs-Superset в `docs/frontend/dashboards.md`; не включать в MVP.

**Критерий приёмки:** Reagraph рендерит seed-граф на экране Graph Explorer; Sigma/Graphology режим открывает overview большого графа; ECharts рисует gap-матрицу; React Flow показывает LangGraph workflow; Superset выключен по умолчанию и его роль зафиксирована в decision-doc; optional-библиотеки не увеличивают prod-bundle без флага.

### 21.7 Entity resolution / cleaning

- [ ] **Splink** (dependency, MIT): добавить `splink` в `packages/kg_extractors` и `apps/curation-service`; реализовать probabilistic linkage для сущностей материалов/установок/лиц/лабораторий (§9.2 Step 6); тест сматчивает известные дубликаты seed-набора с ожидаемым match probability.
- [ ] **Dedupe** (optional dependency, MIT): добавить `dedupe` как fallback-алгоритм ER за конфиг-флагом; задокументировать критерий выбора Splink vs Dedupe.
- [ ] **OpenRefine** (service/tool, BSD-3-Clause): добавить `openrefine` в `infra/docker-compose.yml` (optional profile) как reconciliation-инструмент для ручной очистки каталогов; задокументировать использование в curation-workflow (§12).

**Критерий приёмки:** Splink-пайплайн выдаёт кандидатов на merge, которые попадают в review queue (§12.1); OpenRefine доступен опционально; выбор ER-движка управляется конфигом.

### 21.8 Metadata / orchestration / lineage / eval

- [ ] **Dagster** (service + dependency, Apache-2.0): добавить `dagster` в зависимости и сервис `dagster` (build `./infra/dagster`, порт 3001) в `infra/docker-compose.yml`; реализовать asset graph ingestion-пайплайна (parse→chunk→extract→normalize→resolve→upsert→index) из §9.1; эмитить pipeline metadata (Phase 8).
- [ ] **DataHub** (service, Apache-2.0): развернуть `infra/datahub`; зарегистрировать документы/источники как datasets, эмитить lineage из Dagster, связать ownership/labs (Phase 8); UI показывает lineage документа.
- [ ] **OpenMetadata** (alternative service, Apache-2.0): подготовить `infra/openmetadata` как альтернативу DataHub; задокументировать решение DataHub-vs-OpenMetadata в `docs/decisions/metadata-catalog.md` (Phase 8 task «choose DataHub or OpenMetadata»).
- [ ] **MLflow** (service + dependency, Apache-2.0): добавить `mlflow` в `packages/kg_eval` и сервис в `infra/mlflow`; логировать метрики eval-харнесса (§15.2) и версии extraction-моделей; runs видны в MLflow UI.
- [ ] **Ragas + DeepEval** (dependency, Apache-2.0): добавить `ragas` и `deepeval` в `packages/kg_eval`; реализовать RAG/answer-метрики eval-харнесса (§15.2) — faithfulness, context precision/recall, answer correctness; прогонять на golden-наборе (§15.1) в automated eval loop (§15.3) и логировать в MLflow; прогон даёт метрики без ручного вмешательства.
- [ ] **Marquez** (optional service, Apache-2.0): развернуть `infra/marquez` как OpenLineage backend (optional profile), если DataHub lineage недостаточно; эмитить OpenLineage-события из Dagster.
- [ ] **Airbyte** (optional service, ELv2/MIT — LICENSE FLAG): добавить `infra/airbyte` за optional profile для коннекторов внешних источников; выполнить license-review ELv2 перед использованием.
- [ ] **lakeFS** (optional service, Apache-2.0) и **DVC** (dependency, Apache-2.0): выбрать один механизм версионирования данных/датасетов; добавить `dvc` в root tooling и/или `infra/lakefs`; задокументировать выбор в `docs/decisions/data-versioning.md`.
- [ ] **Apache Atlas** (reference, Apache-2.0): держать как reference governance; задокументировать в `docs/references/atlas.md`, не деплоить в MVP.

**Критерий приёмки:** Dagster asset graph выполняет полный ingestion end-to-end; каждый документ/источник имеет owner и lineage в выбранном каталоге (DataHub или OpenMetadata); MLflow содержит eval-runs с метриками Ragas/DeepEval на golden-наборе; выбор metadata-catalog и data-versioning зафиксирован в decision-docs.

### 21.9 Scientific / materials helpers

- [ ] **pymatgen** (dependency, MIT): добавить `pymatgen` в `packages/kg_schema` и `packages/kg_extractors`; использовать для парсинга/нормализации composition и структур (§13.2); тест нормализует "Al-Cu 2024" в каноническую форму.
- [ ] **Pint** (dependency, BSD-3-Clause): добавить `pint` в `packages/kg_extractors`; реализовать нормализацию физических единиц измерений в канонические единицы с сохранением `value_raw/value/unit/value_normalized/normalized_unit/normalization_method` (§9.2 Step 5); тест конвертирует «5 MPa» и «50 bar» в единый формат и падает на несовместимых размерностях.
- [ ] **Materials Project API** (dependency, modified BSD — LICENSE/ключ FLAG): добавить `mp-api` в `packages/kg_extractors`; реализовать optional-обогащение свойств материалов из MP (требует API key, хранить в `.env`); интеграционный тест за флагом наличия ключа.
- [ ] **MatBERT** (model + reference, license FLAG): подключить веса MatBERT/MatSciBERT (§21 Strongly recommended «MatBERT/MatSciBERT-related models») в NER-компонент `packages/kg_extractors` рядом с GLiNER (§9.2 Step 4); задокументировать источник весов (HF) и лицензию; тест извлекает материалы из span'а.
- [ ] **MatEntityRecognition** (vendored/reference, license FLAG): вендорить в `packages/kg_extractors/vendor/mer` (снапшот + LICENSE) или использовать как reference для materials-NER; выполнить license-review CederGroupHub-репо.
- [ ] **MatKG** (vendored-snapshot, license FLAG): вендорить seed-онтологию/данные в `packages/kg_schema/vendor/matkg` для инициализации доменной схемы (§4.2 п.1); проверить license перед включением в дистрибутив.
- [ ] **Matscholar** (reference/dependency, license FLAG): использовать для нормализации/канонизации терминов материалов; задокументировать в `docs/references/matscholar.md`.
- [ ] **Propnet** (reference, license FLAG): использовать как reference для графа связей свойств материалов (§8, property relationships); клонировать в `reference/propnet`, не шипать.
- [ ] Провести единый license-review для всех materials-репозиториев (все помечены FLAG) и зафиксировать результат в `docs/licenses/materials.md` перед включением любого из них в prod-дистрибутив.

**Критерий приёмки:** pymatgen нормализует composition в unit-тестах; Pint нормализует единицы и отклоняет несовместимые размерности; MP-обогащение работает при наличии ключа и корректно скипается без него; materials-NER (MatBERT/GLiNER) извлекает материалы на golden-span'ах; для всех vendored materials-артефактов сохранены LICENSE-файлы и пройден license-review.

### 21.10 Lab systems

- [ ] **eLabFTW** (service integration via REST API, AGPL-3.0 — LICENSE FLAG): реализовать в `apps/ingestion-service` коннектор к eLabFTW REST API для импорта экспериментов/инвентаря (§4.1); интеграция по сети, исходники НЕ вендорятся (AGPL распространяется только на сам сервис); тест на mock-API импортирует один experiment record.
- [ ] **openBIS** (service integration via REST API, Apache-2.0): реализовать коннектор к openBIS REST API в `apps/ingestion-service` как альтернативный источник экспериментов; задокументировать mapping полей openBIS → KG Experiment nodes (§8).
- [ ] Задокументировать в `docs/integrations/lab-systems.md`, что eLabFTW/openBIS подключаются как внешние сервисы (network integration), а не как встраиваемый код, чтобы избежать AGPL-copyleft на монорепо.

**Критерий приёмки:** коннекторы eLabFTW и openBIS импортируют experiment records через REST в graph (mock/integration-тест); отсутствует прямое встраивание AGPL-кода eLabFTW в монорепо; mapping полей задокументирован.

### 21.11 Соответствие лицензиям, submodule-CI и воспроизводимость

- [ ] Прогнать `scripts/collect_licenses.py` по всем зависимостям (pip lock + npm lock), submodules и vendored-снапшотам; сгенерировать `THIRD_PARTY_NOTICES.md`; сборка CI падает, если появилась зависимость без известной лицензии.
- [ ] Составить `docs/licenses/copyleft-review.md` с явным решением по каждому copyleft/source-available компоненту (FLAG): Neo4j (GPLv3), Neo4j GDS, Marker (GPL/custom), eLabFTW (AGPL), Memgraph/TypeDB/ArangoDB (BSL/source-available), Airbyte (ELv2), LinkML (CC0 — проверить трактовку), materials-репозитории (verify) — с указанием: используется как отдельный сервис / не модифицируется / не встраивается / выключен по умолчанию.
- [ ] Добавить CI-job `third_party-check`, который: (a) проверяет, что все submodules на пиннутых SHA; (b) валидирует `third_party/REPOS.yaml`; (c) сверяет версии Docker images в `docker-compose.yml` с манифестом; (d) запрещает `:latest`.
- [ ] Написать скрипт `scripts/bootstrap_third_party.sh`, который выполняет `git submodule update --init --recursive`, клонирует reference-forks в `reference/` и печатает сводку статусов — чтобы новый разработчик поднял окружение одной командой.
- [ ] Настроить license-scanner (например, `pip-licenses` для Python и `license-checker` для npm) в CI с allowlist разрешённых лицензий (MIT/Apache-2.0/BSD/MPL/CC0) и denylist, требующим ручного approval (GPL/AGPL/BSL/ELv2).

**Критерий приёмки:** CI-job `third_party-check` зелёный на чистом клоне; `scripts/bootstrap_third_party.sh` инициализирует все submodules и reference-forks за один запуск; `THIRD_PARTY_NOTICES.md` покрывает 100% зависимостей; каждый copyleft/source-available компонент имеет зафиксированное решение в `docs/licenses/copyleft-review.md`.

### 21.12 Ontology governance и schema-tooling (optional)

- [ ] **LinkML** (optional dependency, CC0-1.0 — LICENSE FLAG): при необходимости формального управления онтологией (§21 optional, «LinkML + Protégé if ontology governance becomes important») описать доменную схему KG (§8.1–§8.2, §4.2) в LinkML-YAML в `packages/kg_schema`; сгенерировать Pydantic/JSON-Schema из LinkML и сверить с существующими схемами §8; не включать в prod-зависимости без решения.
- [ ] **Protégé** (reference/tool, BSD-2-Clause): использовать как визуальный редактор онтологии для ручного governance-процесса; клонировать/держать в `reference/protege` (в `.gitignore`), не шипать; задокументировать процесс правки онтологии в `docs/decisions/ontology-governance.md`.
- [ ] Зафиксировать решение о внедрении ontology-governance в `docs/decisions/ontology-governance.md` с триггером (когда именно онтология переходит под LinkML/Protégé) и владельцем процесса.

**Критерий приёмки:** решение о внедрении ontology-governance (LinkML/Protégé) с триггером зафиксировано в `docs/decisions/ontology-governance.md`; при включении LinkML-схема генерирует Pydantic-модели, согласованные со схемой §8.1–§8.2; по умолчанию компоненты выключены и не входят в prod-зависимости/prod-bundle.


---


## 22. Definition of Done — критерии полной готовности

Этот раздел — **финальный сводный чек-лист**, по которому система «SOTA Knowledge Graph / научная поисково-аналитическая система» признаётся **полностью реализованной**. Раздел ничего не реализует сам: он агрегирует и проверяет результаты всех остальных разделов. Ни один пункт не закрывается «на слово» — под каждым чек-боксом стоит измеримый результат (артефакт, отчёт, лог, скриншот, прохождение автотеста или eval-прогона).

**Общие зависимости раздела:** данный раздел зависит от завершения ВСЕХ разделов, реализующих Phase 0–9 (§16), agent-service (§7), graph schema (§8), ingestion (§9), retrieval (§10), gap analysis (§11), curation (§12), frontend (§5, §14), eval harness (§15). Проверка выполняется на общем окружении, поднимаемом через `infra/docker-compose.yml`.

**Монорепо и пути (§6.1):** все проверки ведутся в едином монорепо со структурой:
- `apps/` — `api-gateway/` (FastAPI public API), `agent-service/` (LangGraph workflows/tools), `ingestion-service/` (upload/parse/extraction triggers), `graph-service/` (Cypher templates, graph DTOs, schema validation), `search-service/` (Qdrant/OpenSearch wrappers), `extraction-service/` (schema-guided extraction workers), `curation-service/` (review, merge/split, evidence validation), `frontend/` (React app);
- `packages/` — `kg_schema/` (Pydantic + LinkML), `kg_extractors/` (LlamaIndex/GLiNER/materials), `kg_retrievers/` (graph/vector/hybrid), `kg_eval/` (eval harness), `kg_common/` (shared DTOs, config, logging);
- `infra/` — `docker-compose.yml`, `helm/`, `dagster/`, `neo4j/`, `opensearch/`, `qdrant/`.

**Репозитории для клонирования/интеграции (§21, §22-OSS):** к моменту релиза должны быть подключены (как контейнеры, зависимости, vendored или fork): Neo4j (https://github.com/neo4j/neo4j) + APOC (https://github.com/neo4j-contrib/neo4j-apoc-procedures) + Graph Data Science (https://github.com/neo4j/graph-data-science); Qdrant (https://github.com/qdrant/qdrant); OpenSearch (https://github.com/opensearch-project/OpenSearch); Docling (https://github.com/docling-project/docling) + Docling Serve (https://github.com/docling-project/docling-serve) + fallback-парсеры Marker (https://github.com/datalab-to/marker) и Unstructured (https://github.com/Unstructured-IO/unstructured); LangGraph (https://github.com/langchain-ai/langgraph); LlamaIndex (https://github.com/run-llama/llama_index, Property Graph Index); Microsoft GraphRAG (https://github.com/microsoft/graphrag); Splink (https://github.com/moj-analytical-services/splink); Dagster (https://github.com/dagster-io/dagster); Reagraph (https://github.com/reaviz/reagraph) + fallback Sigma.js (https://github.com/jacomyal/sigma.js) и Graphology (https://github.com/graphology/graphology); MLflow (https://github.com/mlflow/mlflow); GLiNER; каталог DataHub (https://github.com/datahub-project/datahub) ИЛИ OpenMetadata (https://github.com/open-metadata/OpenMetadata).

**Единый источник факта готовности:** создать файл `docs/DEFINITION_OF_DONE.md`, который дублирует чек-лист этого раздела и заполняется ссылками на доказательства (номера прогонов MLflow, PR, коммиты, скриншоты, отчёты `packages/kg_eval`). Релиз `v1.0` разрешён только когда ВСЕ чек-боксы разделов 22.1–22.7 закрыты.

---

### 22.1 Acceptance criteria всех фаз roadmap (§16, Phase 0–9)

Каждая фаза считается закрытой, только когда закрыты (a) все её задачи-`[ ]` из §16 в соответствующих разделах плана и (b) все её acceptance criteria, перечисленные ниже как проверяемые чек-боксы. Помимо acceptance criteria §16, ниже дополнительно зафиксирована **полнота API-поверхности (§6.2), схемы графа (§8), контрактов (§5.3) и pipeline-артефактов (§9)**, относящихся к каждой фазе.

**Phase 0 — Repo, infra, skeleton, schema decisions:**

- [ ] `docker compose -f infra/docker-compose.yml up` поднимает ВСЕ сервисы из §13.1 (`frontend`, `api`, `agent`, `ingestion`, `docling`, `neo4j`, `qdrant`, `opensearch`, `postgres`, `redis`, `minio`, `dagster`) без ручных шагов; все контейнеры в статусе `healthy`.
- [ ] порты соответствуют §13.1 (frontend 3000, api 8000, agent 8010, ingestion 8020, docling 5001, neo4j 7474/7687, qdrant 6333/6334, opensearch 9200, postgres 5432, redis 6379, minio 9000/9001, dagster 3001); используется образ `neo4j:2026.05-community` с плагином `apoc`.
- [ ] создана структура монорепо §6.1 (`apps/*`, `packages/*`, `infra/*`); `.env.example` присутствует; python-зависимости §13.2 и frontend-зависимости §14.1 устанавливаются из lock-файлов.
- [ ] frontend открывается на порту 3000, отдаёт стартовый экран Home/Search без ошибок в консоли браузера.
- [ ] `GET /api/v1/admin/health` возвращает `200` и статусы всех зависимостей (`neo4j`, `qdrant`, `postgres`, `minio`, `opensearch`, `redis`) = `up`; `GET /api/v1/admin/metrics` реализован и отдаёт метрики.
- [ ] в `packages/kg_schema` объявлены ВСЕ core labels §8.1 (Document, Paper, Section, Paragraph, Table, Figure, Chunk, Evidence, Claim, Finding, Experiment, Sample, Material, Alloy, ChemicalElement, Composition, ProcessingRegime, ProcessingStep, Parameter, Equipment, Lab, ResearchTeam, Person, Property, Measurement, Unit, Method, Dataset, Project, Decision, CurationEvent, Gap, Contradiction) и core relationships §8.2.
- [ ] в Neo4j созданы ВСЕ constraints/indexes §8.4: 6 uniqueness-constraints (`Material/Experiment/Evidence/Document/Property/Equipment.id`), fulltext `entity_name_index`, `measurement_value_index`, `processing_temperature_index`, `processing_time_index`, и (если включены node embeddings) `entity_embedding_index` (dim 1024, cosine).
- [ ] в Neo4j загружен sample-граф из seed-скрипта (`infra/neo4j/` + seed script), 10 seed-документов §16 Phase 0.
- [ ] Reagraph рендерит sample-граф в Graph Explorer (узлы и рёбра видны, layout стабилен).
- [ ] линтеры/типизация настроены и проходят: `ruff`, `mypy`, `pytest` (backend), `eslint`, `prettier` (frontend) — CI-джоб зелёный.

**Phase 1 — Document ingestion MVP:**

- [ ] загрузка PDF через `POST /api/v1/documents/upload` → parsed-результат (Docling Serve) виден в UI на странице документа (`GET /api/v1/documents/{doc_id}`, `GET /api/v1/documents/{doc_id}/parsed`, `GET /api/v1/documents/{doc_id}/pages/{page}`).
- [ ] реализованы остальные document/ingest endpoints: `POST /api/v1/documents/{doc_id}/reindex`, `POST /api/v1/ingest/jobs`, `GET /api/v1/ingest/jobs/{job_id}`, `POST /api/v1/ingest/jobs/{job_id}/cancel`.
- [ ] Docling Serve отдаёт все outputs §9.2 step2 (markdown, structured JSON, tables, document hierarchy, page references, image crops); raw+parsed сохранены в MinIO по путям `kg-raw/documents/{doc_id}/original.pdf`, `kg-parsed/documents/{doc_id}/docling.json`, `document.md`, `tables/table_*.json`.
- [ ] доступны fallback-парсеры Marker/Unstructured и ручная загрузка таблиц (mitigation §18 «Poor PDF parsing»).
- [ ] chunking structure-aware §9.2 step3 (title/abstract, methods, results, figure captions, table rows, procedure paragraphs, measurement rows); каждый chunk хранит поля `chunk_id`, `doc_id`, `section_path`, `page_start/end`, `chunk_type` ∈ {paragraph|table_row|caption}, `tokens`.
- [ ] chunks доступны для поиска: `POST /api/v1/search/hybrid` / `/vector` / `/keyword` возвращают релевантные фрагменты загруженного документа.
- [ ] индексация §9.2 step8: в Qdrant записаны chunks/table rows/claims/entity descriptions/neighborhood+community summaries с payload-полями (`doc_id`, `chunk_id`, `entity_ids`, `material_ids`, `property_ids`, `processing_operation`, `temperature_c`, `time_h`, `source_type`, `confidence`, `review_status`); в OpenSearch — full text, keywords, facets, numeric ranges, highlight fields.
- [ ] узлы `Document`, `Section`, `Chunk`, `Table` видны в графе после ингеста.
- [ ] каждый `Chunk` имеет метаданные `page`/`source` (проверяется на выборке из 10 seed-документов).

**Phase 2 — KG extraction MVP:**

- [ ] реализованы Pydantic extraction schemas §9.2 (`ProcessingRegimeExtract`, `MeasurementExtract`, `ExperimentExtract`) в `packages/kg_extractors`/`kg_schema`, у каждой обязателен `evidence_text` и `confidence ∈ [0,1]`.
- [ ] работают все три подхода extraction §9.2 step4: rule/domain (regex °C/h/wt%/at%/MPa/GPa/HV/HRC, composition/processing/property vocab), ML (GLiNER, MatBERT/MatSciBERT), LLM schema-guided (JSON mode/function calling) — с жёстким правилом «no source span → no graph fact».
- [ ] units normalization §9.2 step5 (pint + custom HV/HRC/MPa/GPa mappings): у Measurement заполнены `value_raw`, `value`, `unit`, `value_normalized`, `normalized_unit`, `normalization_method`.
- [ ] graph upsert §9.2 step7: deterministic IDs, `MERGE` by canonical id, reviewed-поля не перезаписываются автоматически, сохранён extraction run id, прошлые версии сохранены.
- [ ] на sample-корпусе ≥ **70%** документов дают полезные graph facts (Material/Regime/Property/Measurement) — метрика подсчитана и залогирована в MLflow.
- [ ] **каждый** `Measurement`/claim имеет привязанный `Evidence` (source span) с ПОЛНЫМ набором полей §8.3 (`source_type`, `doc_id`, `page`, `table_id`, `row_index`, `col_index`, `char_start`, `char_end`, `text`, `extractor`, `model`, `confidence`, `created_at`, `reviewed_by`, `review_status`); отсутствие evidence = 0 (детерминированная проверка `packages/kg_eval`).
- [ ] заведены узлы `ExtractorRun`/`GapScanRun` и рёбра `(:Evidence)-[:EXTRACTED_BY]->(:ExtractorRun)`, `(:Evidence)-[:SUPPORTS]->(:Claim)` §8.2.
- [ ] extraction c низким confidence попадает в review queue (`curation-service`), виден в Admin/Curation UI.
- [ ] у каждого extraction-факта записаны extraction run metadata (extractor/model version, run_id).

**Phase 3 — Entity resolution and normalization:**

- [ ] Splink pipeline §9.2 step6 сконфигурирован для `Material`/`Equipment`/`Person`/`Lab` + property vocabulary mapping; готовы material alias dataset и property vocabulary.
- [ ] типовые алиасы материалов/оборудования/лабораторий/персон мапятся на один canonical entity (проверка на подготовленном alias-датасете).
- [ ] ER-выход имеет формат §9.2 step6 (`candidate_id`, `mentions`, `match_probability`, `decision` ∈ {auto_merge|review_needed|separate}); реализованы entity endpoints `GET /api/v1/entities/search`, `GET /api/v1/entities/{entity_id}`, `GET /api/v1/entities/{entity_id}/neighbors`, `POST /api/v1/entities/merge`, `POST /api/v1/entities/{entity_id}/aliases`.
- [ ] неоднозначные merge отправляются в review, а не сливаются автоматически.
- [ ] история merge/split сохранена (merge history), reviewed canonical entities защищены от перезаписи повторным ингестом.

**Phase 4 — Hybrid retrieval and graph query API:**

- [ ] реализованы graph endpoints `POST /api/v1/graph/query`, `POST /api/v1/graph/expand`, `POST /api/v1/graph/path`, `POST /api/v1/graph/subgraph`, `GET /api/v1/graph/schema`; search endpoints `/search/hybrid|vector|keyword`; experiment endpoints `GET /api/v1/experiments`, `GET /api/v1/experiments/{id}`, `POST /api/v1/experiments/query`; evidence endpoints `GET /api/v1/evidence/{id}`, `GET /api/v1/evidence/by-edge/{edge_id}`.
- [ ] запрос «material X + regime Y + property Z» (`POST /api/v1/graph/query`, `query_type=material_regime_property`) принимает формат запроса §6.2 (material/processing{operation,temperature_c,time_h}/property/filters{min_confidence,verified_only,date_from}/include_evidence/include_graph) и возвращает ответ формата §6.2 (`summary`, `experiments[]` с `value`/`unit`/`effect`/`confidence`/`evidence_ids`, `gaps[]`, `graph`, `citations`) в графовом payload §5.3.
- [ ] используются Cypher-шаблоны §7.4 (`material_regime_property` и др.) в readonly-транзакции; свободный `TextToCypherRetriever` — только после schema grounding + readonly + LIMIT + query cost guard + allowlist labels/relations + retry-with-verifier.
- [ ] работают все retrieval modes §10.1: Mode A (structured graph query), Mode B (hybrid semantic), Mode C (GraphRAG community summaries), Mode D (graph algorithms/Neo4j GDS — similar materials, missing links, important labs/teams, method clusters, anomaly detection).
- [ ] RRF/weighted fusion (§10.2) работает по формуле весов (0.35 dense + 0.25 sparse + 0.20 bm25 + 0.10 graph_proximity + 0.10 evidence_quality); graph proximity score §10.3 применяется; rerank cross-encoder на top-50 с boost verified evidence и penalty за missing source span / low confidence; hybrid результат отличается от чистого vector и чистого keyword, покрыт тестом фьюжна.
- [ ] Graph Explorer умеет expand возвращённых сущностей (`POST /api/v1/graph/expand`).
- [ ] evidence-сниппеты кликабельны и открывают Evidence Inspector.

**Phase 5 — LangGraph agent chat:**

- [ ] реализованы chat endpoints `POST /api/v1/chat/sessions`, `GET /api/v1/chat/sessions/{id}`, `POST /api/v1/chat/sessions/{id}/messages`, `GET /api/v1/chat/sessions/{id}/stream`; чат отвечает на основные benchmark-вопросы golden set через messages + SSE stream.
- [ ] в агенте зарегистрированы и вызываются ВСЕ 16 tools §7.4 (`resolve_entities`, `search_material_aliases`, `run_cypher_readonly`, `run_cypher_template`, `vector_search_qdrant`, `keyword_search_opensearch`, `hybrid_search`, `get_experiment_table`, `get_evidence_by_ids`, `get_document_snippet`, `find_graph_paths`, `expand_subgraph`, `scan_gaps`, `detect_contradictions`, `build_graph_visualization_payload`, `create_review_task`); вызовы видны в trace.
- [ ] в LangGraph собраны ВСЕ 10 nodes §7.5 по графу §7.2 (`preprocess_question`, `intent_classifier` c 9 классами §7.5, `entity_resolver`, `query_planner`, `structured_retrieval`, `hybrid_retrieval`, `evidence_assembler`, `gap_analyzer`, `verifier`, `answer_synthesizer`); LangGraph state §7.3 персистится; `query_planner` выдаёт план формата §7.5.
- [ ] `answer_synthesizer` возвращает формат §7.5 (краткая сводка, «что найдено», таблица экспериментов, «что влияет на эффект», «пробелы», «на что опирается ответ», graph payload).
- [ ] UI показывает tool calls / graph queries / evidence checks (agent transparency).
- [ ] `verifier` §7.5 выполняет все 6 проверок (каждое число имеет evidence; единицы не смешаны; material/regime не подменены; нет unsupported claim; contradictions отмечены; для low-confidence добавлен warning); **ни один** числовой claim не выдаётся без evidence — проверка на golden set = 0 нарушений.
- [ ] chat stream отдаёт ВСЕ 8 типов событий контракта §5.3 (`token`, `tool_start`, `tool_end`, `evidence`, `graph`, `table`, `gap`, `error`), фронт их корректно обрабатывает.
- [ ] к ответу рендерятся graph- и table-attachments; при провале verifier срабатывает retry path.

**Phase 6 — Frontend graph explorer and evidence UX:**

- [ ] реализованы ВСЕ 8 экранов §5.2: Home/Search, Chat with Scientific Agent, Graph Explorer, Entity Detail Page, Experiment Explorer, Evidence Inspector, Gap Dashboard, Admin/Curation.
- [ ] graph payload соответствует контракту §5.3 и валидируется zod: `GraphNode` (type ∈ {Material|Experiment|ProcessingRegime|Property|Equipment|Paper|Claim|Lab|Person|Gap}, `confidence`, `evidenceCount`, `verified`, `missingFields`), `GraphEdge` (`confidence`, `evidenceCount`, `inferred`, `contradicted`, `evidenceIds`), `layoutHints.communities`, `queryContext.generatedCypher`.
- [ ] исследователь проходит путь «chat answer → graph → evidence» без потери контекста (end-to-end клик-сценарий).
- [ ] граф остаётся usable при **1k–5k** элементов (замер FPS/времени layout; при превышении — работающий fallback Sigma.js + Graphology по §5.1).
- [ ] выбранное ребро (`IMPROVES`/`MEASURED_PROPERTY`/`PROCESSED_BY`/`SUPPORTED_BY`) показывает source snippets.
- [ ] работает export PNG/JSON/CSV и saved graph views.

**Phase 7 — Gap analysis and contradiction detection:**

- [ ] реализованы ВСЕ 9 типов gap §11.1 (`missing_property_value`, `missing_baseline`, `missing_processing_parameter`, `missing_equipment`, `missing_unit`, `unverified_claim`, `contradictory_measurements`, `low_coverage_material`, `orphan_entity`) плюс правила `gap_analyzer` §7.5 (`missing_source_span`, `low_confidence_entity_resolution`).
- [ ] реализованы gap scan Cypher §11.2 (missing baseline; material/regime/property matrix gaps), создаются `Gap`-узлы + рёбра `(:Gap)-[:ABOUT]->(:Entity)`, `(:Gap)-[:DETECTED_BY]->(:GapScanRun)`.
- [ ] система выявляет missing baseline / missing unit / missing equipment, создаёт `Gap`-узлы (`POST /api/v1/gaps/scan`).
- [ ] чат отвечает на «где пробелы по X?» с опорой на `Gap`-узлы (`GET /api/v1/gaps`).
- [ ] gap-граф навигируем в Gap Dashboard; coverage matrix доступна через `GET /api/v1/gaps/matrix`.
- [ ] contradiction detector находит одинаковый material/regime/property с несовместимыми значениями (heuristic §17.5), создаёт `Contradiction`/`(:Claim)-[:CONTRADICTS]->(:Claim)`, результат виден в UI.

**Phase 8 — Metadata, lineage, governance:**

- [ ] source registration §9.2 step1 сохраняет `source id`, `file hash`, `source type`, `owner/lab`, `access policy`, `ingestion job id`, `version`.
- [ ] зафиксирован выбор DataHub ИЛИ OpenMetadata; datasets и documents зарегистрированы в каталоге.
- [ ] у каждого document/source есть owner и lineage.
- [ ] pipeline-прогоны трассируемы: Dagster эмитит metadata, lineage виден в каталоге.
- [ ] агент может использовать metadata context (owner/lab/source) в ответах.
- [ ] audit logs пишутся для действий curation/admin.

**Phase 9 — Hardening and SOTA polish:**

- [ ] собран golden QA set (§15.1, 50–100 вопросов), benchmark **воспроизводим** (повторный прогон даёт те же метрики в пределах допуска).
- [ ] на golden set **нет** unsupported answer claims (unsupported_claim_rate = 0).
- [ ] eval-loop §15.3 подключён: MLflow (extraction/retrieval/answer), RAGAS/DeepEval (RAG-checks), детерминированные custom-checks для чисел/цитат, LangSmith/OpenTelemetry для agent trace.
- [ ] включены OpenTelemetry traces и LangGraph trace viewer; агентские трассы доступны для отладки.
- [ ] реализованы role-based access (RBAC), backup/restore, CI/CD; полный demo запускается локально или на VM по документированному сценарию.

**Критерий приёмки:** для каждой из фаз 0–9 в `docs/DEFINITION_OF_DONE.md` проставлены ссылки-доказательства (PR/коммит/MLflow run/скриншот); ВСЕ acceptance-чек-боксы выше закрыты, включая полноту API-поверхности §6.2 (ни один endpoint не возвращает 404/501), полноту схемы графа §8, контрактов §5.3 и pipeline-артефактов §9; сводный скрипт `packages/kg_eval` / CI печатает `PHASES 0-9: PASS`.

---

### 22.2 SOTA features реализованы (§17, все 10 пунктов)

- [ ] **1. Evidence-first graph** — в графе не «голые» triples, а triples с source spans, confidence и review status; для каждого связующего ребра доступен `Evidence` (модель §8.3). Проверка: выборка 50 рёбер, у 100% есть evidence+confidence+status.
- [ ] **2. Graph + vector + keyword retrieval** — работают structured graph query (Mode A), hybrid semantic (Mode B), keyword, а также graph-algorithms (Mode D §10.1: similar materials / missing links / important labs / method clusters / anomaly — хотя бы similar-materials и important-labs воспроизводимы на demo-графе); точные научные вопросы идут через граф, «грязный» текст — через hybrid. Проверка: eval сравнивает режимы на golden set.
- [ ] **3. GraphRAG community summaries** — community summaries (Microsoft GraphRAG, https://github.com/microsoft/graphrag) построены и используются для broad/corpus-level вопросов (Mode C §10.1). Проверка: broad-literature вопросы golden set обслуживаются community-summary путём.
- [ ] **4. Gap graph** — gaps являются first-class узлами (`Gap`), связаны с материалами/режимами/свойствами; навигируемы в UI (пересечение с 22.1 Phase 7).
- [ ] **5. Contradiction detection** — детектор находит несовместимые значения для одного material/regime/property; contradiction recall измерен на 10 contradiction-вопросах golden set.
- [ ] **6. Human curation loop** — в `curation-service` / Admin UI работают end-to-end review queue и ВСЕ human actions §12.2 (`accept`, `reject`, `correct value/unit`, `merge`, `split`, `add alias`, `mark relation as inferred`, `create manual evidence`, `annotate gap as known/irrelevant`); review-tasks создаются по всем 6 триггерам §12.1 (confidence < threshold, ER ambiguous, claim contradicts existing, critical field missing, low-quality OCR value, new schema term); каждое действие пишет `CurationEvent` формата §12.3 (`id`, `action`, `actor_id`, `target_type`, `target_id`, `before`, `after`, `reason`, `created_at`); evidence review доступен через `POST /api/v1/evidence/{evidence_id}/review`.
- [ ] **7. Agent transparency** — UI показывает tool calls, graph queries и evidence checks для каждого ответа (пересечение с 22.1 Phase 5).
- [ ] **8. Versioned decisions** — `Decision`/`CurationEvent` связаны с изменениями графа (`(:Decision)-[:AFFECTS]->(:Entity)`, `(:CurationEvent)-[:CHANGED]->(:Entity)`, decision history model §12.3); любая правка схемы/merge/ревью версионируется.
- [ ] **9. Graph snapshots in chat** — ответ чата отдаёт graph payload (§5.3), который пользователь открывает и инспектирует в Graph Explorer.
- [ ] **10. Scientific unit awareness** — measurements нормализованы (units normalization §9.2 step 5), зафиксированы единицы и направление baseline/effect; unit accuracy измерен.

**Критерий приёмки:** все 10 SOTA-features имеют по одному воспроизводимому демо-сценарию (описаны в `docs/DEFINITION_OF_DONE.md`), каждый прогоняется вживую на demo-корпусе; отдельный smoke-тест `packages/kg_eval/test_sota_features.py` проходит для всех 10.

---

### 22.3 Minimal viable demo path пройден (§19, все 8 пунктов — как минимум)

- [ ] **1.** Поднят стек Neo4j + Qdrant + Postgres + MinIO + FastAPI + React (проверяется через `docker compose up` + health, см. 22.1 Phase 0).
- [ ] **2.** Через Docling Serve обработано **20–50** документов demo-корпуса; parsed-артефакты в MinIO по путям §9.2 step2.
- [ ] **3.** Pydantic extraction для `Material`/`Regime`/`Property`/`Measurement`/`Evidence` работает на demo-корпусе (`packages/kg_schema`, `packages/kg_extractors`).
- [ ] **4.** Reagraph explorer открывается и корректно отображает demo-граф.
- [ ] **5.** LangGraph agent имеет и вызывает **5 demo-tools**: `resolve_entities`, `run_cypher_template`, `hybrid_search`, `get_evidence`, `build_graph_payload` (§19/§7.4) — вызовы видны в trace (полный набор из 16 tools проверяется в 22.1 Phase 5).
- [ ] **6.** Топовый query flow «что делали по X при Y и эффект на Z?» отрабатывает end-to-end с ответом = сводка + таблица + значения с единицами + evidence + граф.
- [ ] **7.** Gap scan находит minimum: missing baseline, missing unit, missing equipment (`POST /api/v1/gaps/scan`).
- [ ] **8.** Evidence inspector показывает source snippets по клику на ребро/связь.
- [ ] демо в целом выглядит как research intelligence system, а не обычный RAG-chatbot (subjective gate: фиксируется записью экрана/GIF в `docs/`).

**Критерий приёмки:** существует воспроизводимый скрипт `scripts/run_demo.sh` (или Make-таргет), который на чистом окружении разворачивает стек, загружает demo-корпус и проходит все 8 шагов; записан демо-walkthrough (видео/GIF), приложен к `docs/DEFINITION_OF_DONE.md`.

---

### 22.4 Целевые метрики достигнуты на golden set (§15.1–§15.3)

Предусловие — собран golden dataset (§15.1): 50–100 вопросов в разбивке 20 material-regime-property / 15 experiment lookup / 10 evidence / 10 gap / 10 contradiction / 10 broad literature, каждый с `expected_entities` / `expected_answer_contains` / `must_not_contain` / `required_graph_nodes`.

- [ ] golden set зафиксирован в репозитории (`packages/kg_eval/golden/`), число вопросов ≥ 50, покрыты все 6 категорий.
- [ ] eval-loop автоматизирован (§15.3): MLflow трекает extraction/retrieval/answer прогоны; RAGAS/DeepEval для RAG-проверок; детерминированные custom-checks для чисел и цитат; LangSmith/OpenTelemetry для agent trace.
- [ ] пороги всех метрик зафиксированы в `packages/kg_eval/thresholds.yaml` и одобрены (locked targets), прогон сравнивает факт vs порог и печатает PASS/FAIL.

**Retrieval metrics (§15.2) — измерены и порог достигнут:**

- [ ] Recall@10 for evidence ≥ target.
- [ ] MRR for relevant experiments ≥ target.
- [ ] entity resolution precision/recall ≥ target.
- [ ] graph path correctness ≥ target.

**Answer quality metrics (§15.2) — измерены и порог достигнут:**

- [ ] citation precision ≥ target.
- [ ] unsupported claim rate = **0** на golden set (жёсткий gate из §16 Phase 5/9).
- [ ] numeric accuracy ≥ target.
- [ ] unit accuracy ≥ target.
- [ ] contradiction detection recall ≥ target.
- [ ] gap detection precision ≥ target.

**System metrics (§15.2) — измерены и в пределах бюджета:**

- [ ] ingestion throughput (docs/час) измерен и задокументирован.
- [ ] average chat latency ≤ target (замер на golden set).
- [ ] graph query latency ≤ target.
- [ ] extraction cost per document измерен и в рамках бюджета.
- [ ] reviewer corrections per 100 extractions измерен и ≤ target.

**Критерий приёмки:** единый прогон `python -m kg_eval.run --suite golden` завершается статусом `PASS`, генерирует MLflow-отчёт со всеми метриками §15.2, фиксирует, что каждая метрика достигла порога из `thresholds.yaml`, и что `unsupported_claim_rate == 0`; отчёт воспроизводим (два прогона дают совпадающие результаты в допуске).

---

### 22.5 Все 5 пользовательских сценариев работают end-to-end (§2.1)

- [ ] **Сценарий 1 — Научный вопрос по корпусу.** На вопрос вида «Что уже делали по Al-Cu при aging 180°C 2h и эффект на hardness?» ответ содержит ВСЕ элементы: краткую сводку; таблицу экспериментов; значения свойств с единицами; условия обработки; ссылки на документы/таблицы/страницы/абзацы; граф связанных материалов/режимов/свойств; найденные противоречия и пробелы. Проверка: чек-лист из 7 подпунктов §2.1(1) выполнен на живом запросе.
- [ ] **Сценарий 2 — Graph explorer.** Пользователь вводит материал/режим/свойство/лабораторию → система строит подграф (материалы, эксперименты, режимы, оборудование, публикации, команды, claims) и позволяет фильтровать по типам узлов, времени, confidence, источникам, лабораториям, статусу верификации. Проверка: все перечисленные фильтры функциональны.
- [ ] **Сценарий 3 — Evidence inspector.** Клик по ребру `IMPROVES`/`MEASURED_PROPERTY`/`PROCESSED_BY`/`SUPPORTED_BY` показывает: откуда взята связь; фрагмент текста/таблицы; исходный PDF/страницу; extractor/model version; confidence; кто подтвердил/исправил. Проверка: все 6 полей отображаются.
- [ ] **Сценарий 4 — Gap analysis.** Система показывает «белые пятна» всех 5 типов §2.1(4): материал+режим без свойства Z; property value без режима; эксперимент без оборудования; claim без подтверждающего измерения; противоречащие значения без объяснения. Проверка: каждый тип воспроизводим в Gap Dashboard.
- [ ] **Сценарий 5 — Decision history.** Любая правка схемы, entity merge, ревью extraction, изменение pipeline фиксируется как `Decision`/`CurationEvent` и просматривается в UI. Проверка: выполнить по одному действию каждого типа и убедиться, что все записались.

**Критерий приёмки:** для всех 5 сценариев существуют end-to-end автотесты (или задокументированные ручные прогоны с записью экрана) в `packages/kg_eval` / e2e-suite; каждый сценарий проходит на demo-корпусе от ввода пользователя до финального артефакта без ручных обходных шагов.

---

### 22.6 Итоговая целевая картина достигнута (§23)

Система в финале выглядит как **scientific intelligence workspace**; каждый из пунктов §23 проверяется на живом сценарии:

- [ ] исследователь задаёт вопрос в чате, и это точка входа рабочего процесса.
- [ ] агент строит план и вызывает graph / search / evidence / gap tools (видно в trace).
- [ ] ответ содержит числа, условия, источники и предупреждения (warnings о противоречиях/пробелах).
- [ ] рядом с ответом появляется граф с материалами, режимами, экспериментами, свойствами и источниками.
- [ ] клик по любому ребру показывает доказательство (evidence).
- [ ] пробелы в данных представлены отдельными объектами (`Gap`), которые можно обсуждать и «закрывать» новыми экспериментами.
- [ ] все извлечения и решения версионируются (extraction runs + `Decision`/`CurationEvent`).
- [ ] добавление нового документа обновляет граф, индексы (Qdrant/OpenSearch) и coverage dashboards — проверка: загрузить новый документ и увидеть отражение во всех трёх местах.

**Критерий приёмки:** единый непрерывный демо-прогон (одна сессия) демонстрирует все 8 свойств целевой картины подряд; записан и приложен к `docs/DEFINITION_OF_DONE.md`.

---

### 22.7 Финальный release gate и sign-off

- [ ] заполнен `docs/DEFINITION_OF_DONE.md`: все чек-боксы разделов 22.1–22.6 закрыты и снабжены ссылками-доказательствами.
- [ ] нет открытых blocker/critical issues по функциональности из §2.1, §16, §17.
- [ ] соблюдены ВСЕ ограничения §20 «Что не делать в первой версии»: не своя graph-viz (используется Reagraph/Sigma/Cytoscape); не свой PDF-parser (Docling + fallback); нет full OWL/RDF/SPARQL-стека без жёсткого требования; нет свободного Text2Cypher без guardrails; нет попытки идеально извлечь весь корпус сразу; нет кастомного data catalog (DataHub/OpenMetadata); NER не обучается с нуля до появления размеченного датасета; нет «агента, решающего всё» без deterministic tools/templates.
- [ ] Cypher-путь безопасен per §18: templates-first, readonly, allowlist labels/relations, LIMIT, query timeout — проверка: security-review Cypher-пути пройден.
- [ ] проверено, что реализованы mitigations §18: evidence spans + verifier + human review для low confidence; Docling + fallback Marker/Unstructured + manual table upload; Splink + alias tables + review queue; subgraph projection + filters + community view + Sigma fallback; streaming + cached retrieval + query templates + precomputed summaries; docker-compose с чёткими границами сервисов (возможность отключить OpenSearch/DataHub для MVP); golden questions с первого дня; evidence inspector + unsupported-claim guardrails.
- [ ] полный стек `infra/docker-compose.yml` поднимается «с нуля» на чистой машине/VM по `README`/deployment docs без недокументированных шагов; smoke-test проходит.
- [ ] backup/restore и CI/CD проверены (тестовое восстановление из бэкапа успешно; CI-пайплайн зелёный на main).
- [ ] выполнен финальный воспроизводимый прогон всего eval-harness (§22.4) с итогом `PASS` и сохранён как release artifact для тега `v1.0`.
- [ ] проведён финальный sign-off (владелец продукта/архитектор) с приложенной записью полного демо (§22.3 + §22.6).

**Критерий приёмки:** тег `v1.0` создаётся только при закрытых 100% чек-боксов разделов 22.1–22.7; сводный CI-джоб `definition-of-done` (агрегирует phase-checks, полноту API/схемы/контрактов, SOTA smoke-tests, golden eval и e2e-сценарии) завершается статусом `GREEN`, и его артефакт-отчёт приложен к релизу.


---


## 23. Сквозные и недостающие задачи

Раздел агрегирует то, что требуется дизайн-документом (или необходимо для полной, production-ready реализации), но НЕ имеет единого владельца ни в одном из разделов §1–§22, либо покрыто фрагментарно (по кусочкам в разных разделах) без сквозной согласованной реализации. Каждая подзона — это «клеевой»/недостающий слой, который связывает уже описанные сервисы (`apps/*`, `packages/*`, `infra/*` по §6.1) и закрывает риски продакшена. Задачи здесь не дублируют внутренние тесты/доки отдельных разделов, а вводят cross-cutting-контур: сквозные интеграционные и контрактные тесты, единую фикстуру-фабрику, координацию миграций, реальный корпус, пользовательскую/разработческую документацию, локализацию, нагрузочное тестирование, LLM-cost governance, единый resilience-слой, сквозное версионирование данных и т.д.

Организационная заметка (для оркестратора): в наборе `fulltasks/` отсутствует файл `section_07.md` (нумерация идёт 01–06, 08–22). Содержательно тема §7 «Agent system на LangGraph» полностью покрыта разделом `section_13.md` (LangGraph Agent Service), поэтому content-gap по агенту нет; но следует подтвердить, что при генерации не был потерян отдельный запланированный раздел.

Зависимости: раздел опирается на ВСЕ разделы §1–§22 и является предпосылкой к §22 (Definition of Done) — сквозные gate'ы здесь питают финальный release-gate §22.7.

---

### 23.1 Сквозное интеграционное тестирование между сервисами (cross-service integration)

Внутри разделов есть per-service integration-тесты (§4.11, §5.12, §6.17, §9.11, §13.25, §14.16, §16.11), но нет единого владельца сквозных тестов, гоняющих полный путь через ВСЕ сервисы (`api-gateway → agent-service → graph-service → search-service → curation-service → ingestion-service` + Neo4j/Qdrant/OpenSearch/Postgres/Redis/MinIO) как единое целое.

- [ ] Создать выделенный пакет/каталог сквозных тестов `tests/e2e/` (корень репо) с общим harness'ом, поднимающим полный стек через `infra/docker-compose.yml` (или testcontainers) один раз на сессию и переиспользующим его для всех cross-service сценариев.
- [ ] Реализовать «золотой поток» §23 end-to-end как один тест: upload документа (`/documents/upload`) → Dagster ingestion (§9) → extraction+ER+upsert → reindex (§4.10) → chat-вопрос через SSE (`/chat/.../stream`) → ответ с evidence/graph/table → клик по ребру (`/evidence/by-edge/{id}`) → gap scan (`/gaps/scan`) → curation review (`/evidence/{id}/review`) → проверка обновления `verified` в Qdrant/OpenSearch/графе.
- [ ] Реализовать межсервисные сценарии для каждого из 5 пользовательских сценариев §2.1 (научный вопрос, graph explorer, evidence inspector, gap analysis, decision history) поверх общего seed-графа (§23.3), не изолированно внутри одного сервиса.
- [ ] Проверить сквозной проброс `request_id`/`trace_id` (§18.1/§18.2) по всей цепочке сервисов в одном тесте (лог/трейс одного запроса связен от gateway до Neo4j).
- [ ] Проверить сквозную согласованность данных: после ingestion одного документа он одновременно виден в Neo4j (узлы), Qdrant (точки), OpenSearch (документы), Postgres (source registry) и каталоге метаданных (§10) — единой проверкой.
- [ ] Настроить отдельный CI-job `e2e-integration` (nightly + на релизных PR), поднимающий полный compose-стек и гоняющий сквозной набор; собрать отчёт и артефакты (логи, трейсы).
- [ ] Реализовать «chaos/degradation»-подмножество: остановка одного зависимого сервиса (OpenSearch/agent/docling) в середине потока и проверка graceful degradation по §23.11 (не 500, а деградированный ответ/понятная ошибка).

**Критерий приёмки:** CI-job `e2e-integration` на чистом стеке проходит сквозной «золотой поток» и все 5 сценариев §2.1 через реальные HTTP-вызовы между сервисами (без моков внутренних сервисов); один `request_id` прослеживается end-to-end; проверка кросс-хранилищной согласованности зелёная; остановка некритичного сервиса не роняет поток (деградация подтверждена).

---

### 23.2 Контрактное тестирование API и межсервисных интерфейсов (contract testing)

Разделы упоминают contract-тесты на СВОЙ публичный API (§5.12, §9.9, §11.13, §14.16) и паритет OpenAPI↔TS/Pydantic (§1.13, §17.3), но нет consumer-driven contract-тестов между внутренними сервисами и единого gate на дрейф контрактов (в т.ч. handoff-DTO пайплайна §6.16/§8/§9).

- [ ] Ввести единый источник контрактов: FastAPI api-gateway публикует OpenAPI (§14.16), внутренние сервисы (agent/graph/search/ingestion/curation) публикуют свои OpenAPI; собрать их в `contracts/` с версионированием.
- [ ] Реализовать consumer-driven contract-тесты (например Pact или schemathesis-профиль) для пар: `api-gateway → agent-service`, `api-gateway → graph-service`, `api-gateway → search-service`, `api-gateway → ingestion-service`, `api-gateway → curation-service`; провайдер-верификация в CI каждого сервиса.
- [ ] Зафиксировать и провалидировать handoff-контракты пайплайна как формальные схемы (Pydantic/JSON Schema из `packages/kg_schema`): ingestion→extraction (chunks §5.9), extraction→normalization (§6.16 `needs_custom_normalization`), extraction→ER (§8), ER→upsert (§8.9), upsert→indexing (§4.10) — с contract-тестом на каждый стык.
- [ ] Реализовать CI-gate паритета `OpenAPI ↔ TS-типы фронтенда ↔ Pydantic-DTO kg_common` (§5.3/§7.3): кодогенерация TS из OpenAPI (`openapi-typescript`) и diff-проверка; расхождение валит CI (закрывает `docs/conventions/api-contracts.md` из §1.13 автоматической проверкой).
- [ ] Реализовать проверку обратной совместимости API (breaking-change detector, напр. `oasdiff`) на PR: удаление/переименование поля или endpoint без версии — блокирующая ошибка.
- [ ] Валидировать контракт SSE `ChatStreamEvent` (§5.3) как схему: генерируемые agent-service события проходят JSON-schema-валидацию, а фронтенд-парсер (§17.4) тестируется против тех же фикстур событий.
- [ ] Валидировать контракт `CurationEvent`/`Decision` (§12.3) и `GraphResponse`/`GraphNode`/`GraphEdge` как разделяемые схемы между backend и frontend (единый snapshot-набор фикстур).

**Критерий приёмки:** в CI есть job `contracts`, который (a) прогоняет consumer/provider contract-тесты для всех межсервисных пар, (b) валит сборку при дрейфе OpenAPI↔TS↔Pydantic, (c) валит при breaking-change без bump версии; все handoff-DTO пайплайна имеют схему и contract-тест на стыке; SSE/GraphResponse/CurationEvent фикстуры проходят валидацию на обеих сторонах.

---

### 23.3 Единая фабрика тестовых данных, фикстур и общий seed-граф

Каждый раздел определяет свои фикстуры (§3.17 seed-граф, §11.10 gap-фикстуры, §15.10 gap_graph, §18.6 golden, §16.11) и повторяет пример «Al-Cu / aging 180°C 2h / hardness» независимо, что ведёт к дрейфу. Нет единого versioned source-of-truth для тестовых данных.

- [ ] Создать пакет `packages/kg_testkit/` (или `packages/kg_common/testing/`) с типизированными фабриками/билдерами DTO (`Material`, `Experiment`, `Measurement`, `Evidence`, `Gap`, `Contradiction`, `Chunk`, `GraphResponse`, `ChatStreamEvent`) на базе `kg_schema` — единый способ конструировать валидные объекты в любом тесте.
- [ ] Вынести канонический эталонный пример «Al-Cu 2024 / aging 180°C 2h / hardness» (используемый в §5.2.2, §6.2, §7, §15.1) в единую фикстуру `kg_testkit/fixtures/al_cu_reference.py`, которую переиспользуют seed-скрипты (§2.6, §3.17), demo (§19.11) и golden (§18.6) — устранить дублирование/дрейф.
- [ ] Консолидировать seed-граф: один канонический `seed_graph` (§3.17) как источник для всех разделов (retrieval §4/§12, gap §15, agent §13, frontend MSW §17.3), с deterministic ID (§3.8) и полным provenance (§3.7); запретить локальные копии seed вне testkit.
- [ ] Реализовать генератор синтетического «большого» графа (тысячи узлов) для perf-тестов (§17.9, §23.9) и нагрузочных сценариев (§23.9), параметризуемый размером.
- [ ] Обеспечить детерминизм фикстур (фиксированные seed/ID/даты) для воспроизводимости eval (§18) и e2e (§23.1); запретить `datetime.now()`/random без seed в фикстурах.
- [ ] Реализовать anonymization/sanitization для demo-данных (§19.11): фикстуры не содержат реальных секретов/персональных данных; demo-креды ≠ prod.
- [ ] Задокументировать в `packages/kg_testkit/README.md` каталог фикстур и правило «новые тестовые данные — только через testkit».

**Критерий приёмки:** все разделы, использующие seed/фикстуры, импортируют их из `kg_testkit` (grep не находит дублей эталонного Al-Cu-примера вне testkit); фабрики строят только валидные по `kg_schema` объекты; один `seed_graph` переиспользуется в e2e/eval/frontend-mocks; генератор большого графа выдаёт граф заданного размера для perf-тестов.

---

### 23.4 Координация миграций (Postgres + Neo4j + Qdrant/OpenSearch)

Alembic-миграции живут отдельно в нескольких сервисах, пишущих в общую БД `kg_app` (§2.6 postgres-migrate, §5.4 ingestion, §14/§19.2 auth, §16.1 curation, §9.9 ingest_jobs), а Neo4j-миграции — в §3.15. Нет владельца координации: порядка применения, единого runner'а, предотвращения конфликтов схем разных сервисов в одной БД.

- [ ] Принять и зафиксировать в ADR (`docs/adr/00xx-migrations-strategy.md`) стратегию Postgres-схем: раздельные schema/namespace на сервис в общей БД `kg_app` (`auth`, `ingestion`, `curation`, `chat`, `dagster`, `metadata`, `audit`) ИЛИ раздельные БД — с обоснованием и правилом отсутствия cross-service FK.
- [ ] Реализовать единый migration-оркестратор (`infra/migrations/` + `make migrate`), применяющий в детерминированном порядке: Neo4j (§3.15) → Postgres по всем сервисам (Alembic, с общим `alembic` history или per-service history в своём schema) → init коллекций Qdrant (§4.3) → индексов OpenSearch (§4.6); идемпотентно и с fail-fast при рассинхроне.
- [ ] Обеспечить, чтобы `postgres-migrate`/Helm-hook (§2.6/§2.8) вызывал единый оркестратор, а не разрозненные `alembic upgrade` в каждом контейнере с гонками.
- [ ] Реализовать guard версии схемы на старте каждого сервиса: сервис проверяет ожидаемую версию своей Postgres-схемы и Neo4j `SchemaVersion` (§3.15); mismatch → fail-fast с понятной ошибкой.
- [ ] Реализовать и протестировать rollback/downgrade для Postgres (Alembic downgrade) и документировать откат Neo4j/индексов (пересоздание из snapshot §16.10, т.к. Cypher-миграции труднообратимы).
- [ ] Реализовать backfill-миграции данных (не только DDL): напр. проставление `access_policy=private` для источников без политики (§19.3), заполнение `aliases_text` (§3.12), добавление provenance-полей на старые узлы (§3.7) — как версионированные data-migrations.
- [ ] Согласовать миграции хранилищ Qdrant/OpenSearch с изменением embedding-модели/размерности (§23.13): смена dim требует пересоздания коллекции + reindex — оформить как миграцию с blue/green (§4.3 recreate, §11.10 alias swap).
- [ ] Написать тест «fresh vs migrated»: схема, полученная миграциями из нуля, идентична схеме после последовательного применения всех версий (Postgres); Neo4j `migrate up` из нуля == инкрементальному.

**Критерий приёмки:** `make migrate` на пустом стеке разворачивает Postgres (все schema сервисов), Neo4j constraints/indexes (§8.4), Qdrant-коллекции и OpenSearch-индексы в корректном порядке идемпотентно; повторный запуск — no-op; сервис с устаревшей схемой падает fail-fast; тест «fresh == migrated» зелёный; rollback Postgres-миграции протестирован.

---

### 23.5 Реальный seed-набор, демо-корпус и его происхождение/лицензирование

Разделы ссылаются на «10 seed-документов» (§2.6/§3.17/§16 Phase 0) и «20–50 demo-документов» (§19.11), но нет владельца фактического НАПОЛНЕНИЯ корпуса: где берутся реальные научные PDF по материаловедению, их лицензии/права на использование, ground-truth аннотации для golden (§18.6) и extraction-golden (§6.17).

- [ ] Определить источники и лицензионную чистоту seed/demo-корпуса: open-access статьи (arXiv/PMC/CC-BY), собственные лабораторные отчёты, синтетические документы; зафиксировать провенанс и лицензию каждого документа в `data/corpus/CORPUS_MANIFEST.md`.
- [ ] Собрать реальный seed-корпус (10 документов Phase 0) и demo-корпус (20–50 документов §19) с покрытием: text-PDF, сканированный PDF (OCR §5.7), DOCX, PPTX, HTML, документ с таблицами, документ с рисунками (совместимо с §5.12 fixtures).
- [ ] Обеспечить, чтобы demo-корпус давал граф с ≥1 `Gap` и ≥1 `Contradiction` (требование §19.11/§22.3) и покрывал материал/режим/свойство эталонного flow §2.1(1).
- [ ] Создать ground-truth разметку для golden-dataset (§18.6, 50–100 вопросов) и extraction-golden (§6.17, ≥15 документов) поверх реального корпуса; описать процесс аннотации (`ANNOTATION.md`, §18.6) и владельца.
- [ ] Реализовать репозиторий корпуса вне git-исходников (крупные бинарники в MinIO/DVC, §23.12) с manifest'ом и checksum'ами; в git — только манифест и указатели версий.
- [ ] Реализовать `make load-corpus` / `infra/seed/load_demo_docs.py` (§19.11), заливающий корпус в `kg-raw` и запускающий batch-ingestion (§5.10) идемпотентно.
- [ ] Разделить профили корпуса: минимальный `seed` (быстрый CI/e2e), полный `demo` (walkthrough §19.11), синтетический `perf` (§23.9); зафиксировать в конфиге.
- [ ] Провести license-review корпуса (аналогично §21.11 для кода) и запретить в demo/публичной сборке документы без прав на распространение.

**Критерий приёмки:** `data/corpus/CORPUS_MANIFEST.md` перечисляет каждый документ с источником, лицензией и checksum; `make load-corpus` на чистом стеке заливает seed/demo-корпус и прогоняет ingestion до графа с ≥1 Gap и ≥1 Contradiction; golden/extraction-golden аннотированы поверх реального корпуса; ни один документ без прав не попадает в публичный demo-профиль.

---

### 23.6 Пользовательская документация и справка в продукте (end-user docs)

Разделы генерируют технические README/ADR, но нет пользовательской документации для исследователя/куратора (как задавать вопросы, читать evidence, работать с gap dashboard, интерпретировать confidence/warnings) и in-app справки.

- [ ] Написать User Guide `docs/user/` для роли researcher: как формулировать научный вопрос (§2.1), интерпретировать вкладки ответа [Summary/Experiments/Evidence/Graph/Gaps/Contradictions] (§5.2.2), доверять/проверять числа через Evidence Inspector (§5.2.6), пользоваться фильтрами и saved views.
- [ ] Написать Curator Guide `docs/user/curation.md`: review queue (§12.1), human actions (§12.2: accept/reject/correct/merge/split/alias/mark-inferred/manual-evidence/annotate-gap), decision history, разрешение contradictions.
- [ ] Написать Admin Guide `docs/user/admin.md`: ingestion jobs, pipeline monitoring, source catalog/lineage (§10.7), audit log (§10.8/§19.5), управление пользователями/ролями (§19.2).
- [ ] Реализовать in-app справку/onboarding во фронтенде (§17): tooltips для визуальных кодировок графа (§5.2.3 легенда — уже в §17.8), первый tour/empty-state подсказки, глоссарий доменных терминов (labels §8.1).
- [ ] Задокументировать интерпретацию метрик доверия для пользователя: что означают confidence, review_status, inferred/dashed, contradicted/red, hollow node, lock icon (§5.2.3) — единый пользовательский словарь визуальных сигналов.
- [ ] Подготовить FAQ и troubleshooting для пользователей (почему нет ответа/evidence, что такое «data gap», как запросить re-review).
- [ ] Локализовать пользовательскую документацию и справку на ru/en (см. §23.8).

**Критерий приёмки:** незнакомый исследователь по `docs/user/` самостоятельно проходит основной сценарий (задать вопрос → прочитать ответ → открыть evidence → посмотреть gaps); in-app подсказки объясняют все визуальные кодировки §5.2.3; Curator/Admin guides покрывают все действия §12.2 и admin-функции §5.2.8; документация доступна на ru и en.

---

### 23.7 Документация для разработчиков и единый docs-портал

Документация разработчика разбросана по README отдельных разделов (§1.13, §3.18, §6.17, §9.11 и т.д.). Нет единого onboarding'а, docs-портала и консолидированного индекса ADR/архитектуры.

- [ ] Создать developer onboarding `docs/dev/getting-started.md`: клонирование, `make bootstrap` (§1.2), `make vendor`/submodules (§21.11), `make up`+`make migrate`+`make seed`, запуск тестов, карта сервисов/портов (§13.1) — путь «от нуля до локально работающей системы».
- [ ] Собрать единый docs-портал (MkDocs/Docusaurus в `docs/`), агрегирующий: архитектуру (§6.1), схему графа (§3.18 `graph_model.md`), API-контракты (§14.16 OpenAPI), онтологию (§3.18 gen-doc), ADR-индекс, runbooks (§2.13/§19.12), user docs (§23.6).
- [ ] Консолидировать ADR: единый индекс `docs/adr/README.md` со всеми ADR из разделов (§1.2 python-manager, §1.11 task-runner, §1.13 stack, §10.1 metadata-platform, §11.1 graphrag, §23.4 migrations, §23.12 data-versioning и др.); шаблон MADR (§1.13).
- [ ] Задокументировать карту «дизайн-документ § → раздел плана → код/сервис» как трассируемость требований (traceability matrix) для проверки полноты (питает §22 DoD).
- [ ] Написать guide по добавлению нового: agent-tool (§7.4), Cypher-шаблона (§12.2), gap-правила (§15.3), connector'а (§20.2), extraction-vocab (§6.5/§6.6) — расширяемость системы.
- [ ] Автогенерация справочника API (Redoc/Swagger UI из OpenAPI §14) и схемы графа (§3.16 `/graph/schema`) в портал; обновление в CI.
- [ ] Опубликовать developer-портал в CI (build+deploy как статический сайт) и добавить проверку «битых ссылок» в docs.

**Критерий приёмки:** новый разработчик по `docs/dev/getting-started.md` поднимает систему одной последовательностью команд без устного сопровождения; docs-портал собирается в CI, агрегирует API/схему/онтологию/ADR/runbooks и не содержит битых ссылок; traceability-matrix связывает каждый § дизайна с разделом/кодом.

---

### 23.8 Локализация и интернационализация фронтенда (i18n ru/en)

Дизайн предполагает двуязычность: `language ∈ {ru,en}` в agent-state (§7.3), ответ на языке пользователя (§13.17), RU/EN описания gap (§15.1/§15.9). Но локализация UI фронтенда (строки интерфейса, форматирование, переключение локали) НЕ покрыта ни одним разделом.

- [ ] Внедрить i18n-фреймворк во фронтенд (`i18next`/`react-i18next` или аналог) в `apps/frontend`: каталоги переводов `locales/{ru,en}/*.json`, извлечение всех UI-строк из компонентов (§17) в ключи.
- [ ] Локализовать все 8 экранов §5.2 + Document Viewer (§17.6–§17.20): нет хардкода строк в JSX; покрыть кнопки, вкладки, тултипы, легенды, ошибки, empty-states.
- [ ] Реализовать переключатель локали (в App shell §17.5) с персистом в `me/settings` (§14.15) и синхронизацией с языком чат-ответов (`language`, §7.3): выбор локали UI управляет и языком ответа агента.
- [ ] Настроить локале-зависимое форматирование чисел, единиц, дат/времени (Intl/`date-fns`), особенно для значений измерений и temperature/time.
- [ ] Обеспечить, чтобы backend отдавал двуязычные поля там, где это уже предусмотрено (gap `description`/`description_ru` §15.1) и добавить недостающие двуязычные сообщения (validation/ошибки API §14.2) или локализовать их на клиенте.
- [ ] Локализовать даты/тексты в export report (§17.16) и PDF/CSV-экспортах по выбранной локали.
- [ ] Настроить проверку полноты переводов в CI (нет отсутствующих ключей ru/en; линтер i18n) и запрет хардкод-строк (eslint-правило).
- [ ] Задокументировать процесс добавления новой строки/локали и работу переводчиков (`docs/frontend/i18n.md`).

**Критерий приёмки:** переключение локали ru↔en меняет ВСЕ строки UI на всех экранах (нет непереведённых), меняет формат чисел/дат и язык последующих ответов агента; CI падает при отсутствующем ключе перевода или хардкод-строке; выбранная локаль персистится в настройках пользователя.

---

### 23.9 Производительность, нагрузочное и стресс-тестирование (performance/load)

Есть точечные бюджеты латентности (§12.11, §18.5) и usability графа на 1k–5k (§17.8/§17.9), но нет владельца системного load/stress/soak-тестирования (конкурентные пользователи, throughput ingestion под нагрузкой, деградация под давлением, capacity planning).

- [ ] Сформулировать performance-требования/SLO в `docs/perf/slo.md`: целевые p50/p95/p99 для chat, graph query, search, upload→parsed; целевой ingestion throughput (docs/час, §15.2); допустимая деградация под нагрузкой.
- [ ] Реализовать load-тесты (k6/Locust) для ключевых путей: `/chat/.../messages`+SSE, `/graph/query`, `/search/hybrid`, `/experiments/query`, `/documents/upload` — с рампами и профилями конкурентности; хранить сценарии в `tests/load/`.
- [ ] Реализовать ingestion throughput-тест: пакетная загрузка N документов (§5.10 batch), измерение docs/час, latency стадий пайплайна (§18.2 spans), поведение очереди Dagster (§9.7 concurrency).
- [ ] Реализовать graph-render perf-тест (§17.17): интерактивность Reagraph на 1k–5k и Sigma на тысячах узлов на синтетическом большом графе (§23.3) с бюджетом FPS/времени layout.
- [ ] Реализовать soak/stability-тест (длительный прогон, поиск утечек памяти/дескрипторов в сервисах и в Neo4j/Qdrant/OpenSearch).
- [ ] Провести capacity planning и валидировать resource limits (§2.5) под целевой нагрузкой; проверить горизонтальное масштабирование stateless-сервисов и worker'ов (§2.8 HPA) под нагрузкой.
- [ ] Настроить regression-gate производительности: сравнение с baseline из `docs/perf/baseline.json`, алерт/фейл при регрессии латентности сверх допуска (интеграция с §18.5 alert-rules и §18.11 regression-gate).
- [ ] Валидировать поведение кэшей (Redis retrieval-cache §12.11, GraphRAG cache §11.7) под нагрузкой (hit-rate, инвалидация при upsert §12.11).

**Критерий приёмки:** load-suite (`tests/load/`) прогоняется в CI/nightly и печатает p50/p95/p99 vs SLO из `docs/perf/slo.md`; ingestion throughput измерен и задокументирован; graph-render укладывается в бюджет на 5k узлов; soak-тест не выявляет утечек за N часов; perf-regression-gate валит сборку при просадке сверх допуска.

---

### 23.10 Управление стоимостью и бюджетами LLM (LLM cost governance)

Есть учёт стоимости (§18.10 `cost.py`, §18.4 cost per doc/query, §6.17 extraction cost), но нет владельца управления БЮДЖЕТАМИ: квоты, лимиты, алерты по стоимости, оптимизация (кэш/батч/выбор модели), enforcement токен-бюджета.

- [ ] Реализовать централизованный cost-accounting как сквозной слой в `packages/kg_common/cost.py` (расширение §18.10): единая таблица цен моделей, агрегация token-usage со ВСЕХ LLM-вызовов (extraction §6, agent §13, graphrag §11, eval judge §18.9, connectors §20), запись в Postgres/MLflow.
- [ ] Реализовать бюджеты и квоты: per-user/per-session/per-tenant лимиты стоимости и токенов (в связке с §19.4 concurrency-квотами); превышение → 429/деградация на дешёвую модель/отказ с понятным сообщением.
- [ ] Реализовать response/prompt caching для LLM-вызовов (детерминированные шаги, §13.4 «кэш идентичных вызовов») и prompt caching провайдера, чтобы снизить стоимость повторов; измерить cache-hit-rate.
- [ ] Реализовать политику выбора модели по задаче: дешёвые модели для intent/классификации (§13.8), дорогие для synthesis/extraction; конфигурируемо, с fallback на дешёвую при исчерпании бюджета.
- [ ] Реализовать батчинг extraction-вызовов (§6.16) и лимиты параллелизма LLM (§9.7, §11.4) как cost-control, не только rate-limit.
- [ ] Настроить cost-дашборд и алерты (§18.5 «Cost» dashboard): `extraction_cost_usd_per_document`, `answer_cost_usd_per_query`, дневной/месячный бюджет, алерт при превышении; экспорт в Grafana.
- [ ] Задокументировать модель ценообразования и рекомендации по оптимизации в `docs/ops/llm-cost.md`; включить cost per document/query в acceptance §15.2/§22.4.
- [ ] Реализовать «dry-run/estimate» стоимости перед тяжёлой операцией (полный reindex/re-extraction корпуса, GraphRAG rebuild §11.10) с предупреждением.

**Критерий приёмки:** все LLM-вызовы во всех сервисах учитываются в едином cost-accounting (нет неучтённых путей); per-user бюджет enforce'ится (превышение даёт 429/деградацию, подтверждено тестом); cost-дашборд показывает cost/doc и cost/query с алертом при превышении бюджета; смена модели/включение кэша измеримо снижает стоимость на повторном прогоне golden.

---

### 23.11 Единый resilience-слой: обработка ошибок и ретраи между сервисами

Ретраи и обработка ошибок реализованы точечно (Dagster §9.7, docling-client §5.3, LLM §6.9/§13.4, gateway error-proxy §14.2, graceful degradation §12.3/§13.4). Нет единой политики resilience между сервисами: таймауты, circuit breaker, идемпотентность межсервисных вызовов, стандартизованное распространение ошибок, матрица деградации.

- [ ] Реализовать единый resilience-модуль в `packages/kg_common` (обёртка httpx-клиентов §14.1): стандартные timeout'ы, retry с экспоненциальным backoff+jitter только для идемпотентных/транзиентных ошибок, circuit breaker на нестабильные upstream, bulkhead/семафоры.
- [ ] Определить и задокументировать матрицу деградации (`docs/ops/degradation-matrix.md`): что происходит при падении каждого зависимого сервиса (OpenSearch → Qdrant-only §4.8/§12.3; agent → ошибка чата; docling → fallback-парсеры §5.8; graphrag → hybrid §11.12; catalog → ingestion продолжается §10.4; reranker → fusion-порядок §12.9) — единая, а не разрозненная политика.
- [ ] Стандартизовать распространение ошибок между сервисами: единый error-envelope (`code/message/details/request_id`, §14.2), маппинг upstream 5xx/timeout → 502/504 без утечки стектрейсов, сохранение `request_id`/`trace_id` в ошибке.
- [ ] Ввести идемпотентность межсервисных мутаций: idempotency-key для upload/ingest/merge/review, чтобы ретраи gateway/worker не создавали дубли (согласовать с deterministic ID §3.8 и dedup §5.4/§16.4).
- [ ] Реализовать единый dead-letter/quarantine-подход для всех фоновых путей (Dagster §9.7 `ingestion_failures`, extraction §6.16, connectors §20.11, worker §9.10) с общим форматом и ручным re-run.
- [ ] Реализовать health-driven graceful startup/shutdown всех сервисов: `depends_on service_healthy` (§2.4), закрытие пулов (§13.26), отказ обслуживать до готовности зависимостей (readiness §14.11/§18.5).
- [ ] Настроить таймауты на все внешние вызовы (Neo4j §12.10 `CYPHER_TIMEOUT_MS`, LLM, docling, Qdrant/OpenSearch) согласованно, чтобы ретраи имели смысл и не копились.
- [ ] Написать resilience-тесты: инъекция таймаута/5xx/недоступности каждого upstream и проверка соответствия матрице деградации (пересекается с §23.1 chaos-подмножеством).

**Критерий приёмки:** все межсервисные HTTP-вызовы идут через единый resilience-клиент с таймаутами/backoff/circuit-breaker; `docs/ops/degradation-matrix.md` покрывает падение каждого зависимого сервиса и подтверждён тестами инъекции сбоев; повторная доставка мутации по idempotency-key не создаёт дублей; ошибки upstream пробрасываются как единый error-envelope с `request_id` без стектрейсов.

---

### 23.12 Сквозное версионирование данных и артефактов (lakeFS / DVC / MLflow)

Версионирование данных упомянуто фрагментарно и как «optional»: MLflow/lakeFS/DVC/Airbyte в §10.13, graph-snapshots lakeFS/DVC в §16.10, golden dataset DVC в §18.6, model weights revision в §20.1. Нет единой сквозной стратегии версионирования всех данных/артефактов и одного ADR.

- [ ] Принять единый ADR `docs/adr/00xx-data-versioning.md`: что версионируется (raw docs `kg-raw`, parsed `kg-parsed`, golden datasets, model/embedding weights, graph snapshots, extraction outputs, community-build'ы §11.10) и каким инструментом (lakeFS vs DVC vs MLflow) — консолидировать разрозненные решения §10.13/§16.10/§18.6/§20.1 в одно.
- [ ] Реализовать `ArtifactVersioner`-абстракцию (расширение §10.13 `versioning.py`) с адаптерами lakeFS/DVC/Noop как ЕДИНУЮ точку версионирования, используемую ingestion (§5.5/§9), eval (§18.6), curation-snapshots (§16.10), connectors (§20.11).
- [ ] Связать версии сквозно: `source.version` (§5.4) ↔ data-version raw/parsed ↔ `ExtractorRun` (§6.14) ↔ MLflow run (§18.4) ↔ graph `schema_version` (§3.15) ↔ GraphRAG `build_version` (§11.10) — сквозной provenance «данные↔код↔модель↔граф».
- [ ] Обеспечить воспроизводимость: по (data-version + git-sha + model-revision + prompt-version) полностью восстановим прогон extraction/eval (питает §18.11 «reproducible benchmark» и §22.4).
- [ ] Версионировать веса моделей и эмбеддинги (§20.1 revision, §23.13): смена embedding-модели фиксируется версией и триггерит контролируемый reindex (§23.4/§23.13).
- [ ] Интегрировать data-version в lineage-каталог (§10.5) и в provenance-ответы агента/citations (§10.10/§10.13).
- [ ] Настроить retention/GC старых версий артефактов (согласовать с §16.10 retention, §11.10 retention билдов, §19.8 backup retention) без потери воспроизводимости последних релизов.
- [ ] Написать тест воспроизводимости: pin data-version+git-sha+model → повторный extraction/eval даёт идентичные результаты.

**Критерий приёмки:** единый ADR фиксирует стратегию версионирования всех классов артефактов; `ArtifactVersioner` — единственная точка версионирования во всех разделах; по набору версий (data+code+model+prompt) прогон воспроизводится байт-в-байт для детерминированных шагов; смена embedding-модели фиксируется версией и запускает контролируемый reindex; версии видны в lineage-каталоге и в provenance ответа.

---

### 23.13 Единый LLM/embedding-gateway и управление моделями

LLM- и embedding-клиенты реализованы независимо в разных сервисах (§6.9 extraction, §13.4 agent, §11.2 graphrag, §4.4 embeddings, §18.9 eval-judge). Нет единого владельца: провайдер-абстракции, консистентности embedding-модели/размерности, миграции при смене модели.

- [ ] Реализовать единый LLM-gateway в `packages/kg_common` (провайдер-абстракция поверх OpenRouter и локальных/OpenAI-совместимых моделей; только open-source/open-weight модели — политика §23.33): унифицированный интерфейс chat/structured-output/tool-use, конфиг модели/endpoint/ключей из `Settings` (§1.9), переиспользуемый ВСЕМИ сервисами вместо дублей клиентов.
- [ ] Реализовать провайдер-fallback и retry/rate-limit/cost-hook (§23.10/§23.11) в gateway; единая точка для caching, budget-enforcement и трейсинга LLM-вызовов (§18.3 `llm.*` атрибуты).
- [ ] Реализовать единый embedding-gateway с фиксацией модели и размерности (1024, §8.4/§4.4/§12.3) как single-source-of-truth; валидировать соответствие dim во ВСЕХ потребителях (Qdrant §4.3, Neo4j vector index §3.13, GraphRAG §11.2) при старте — mismatch → fail-fast.
- [ ] Обеспечить консистентность embedding-модели между ingestion-индексацией и query-time (§12.3 «той же моделью, что при ingestion»); запретить рассинхрон конфигурацией.
- [ ] Реализовать процедуру миграции при смене embedding-модели/размерности: пересоздание коллекций/индексов + полный reindex корпуса (§4.10 `reindex_all`) + пересчёт node-embeddings (§3.13/§3.14) как версионированную операцию (§23.4/§23.12), не «на живую».
- [ ] Реализовать реестр используемых моделей (LLM, embedding, reranker, GLiNER, MatBERT/MatSciBERT §6.8/§20.9) с версиями/revision в одном месте для воспроизводимости и cost/eval-трекинга.
- [ ] Обеспечить соблюдение политики open-source-only (§23.33): gateway принимает только модели из allowlist разрешённых open-source/open-weight моделей (OpenRouter id + лицензия); запрос к модели вне allowlist → fail-fast; CI-проверка `models-policy`.
- [ ] Написать тест: все сервисы получают LLM/embedding только через gateway (нет прямых клиентов провайдера в обход); dim-guard ловит рассинхрон конфигурации.

**Критерий приёмки:** все сервисы вызывают LLM и embeddings только через единый gateway (grep не находит прямых клиентов провайдера вне `kg_common`); размерность эмбеддингов согласована между Qdrant/Neo4j/GraphRAG и провалидирована на старте; смена embedding-модели выполняется как версионированная миграция с reindex; реестр моделей фиксирует версии всех используемых моделей; все модели — из open-source allowlist (§23.33), закрытые провайдеры не используются как основной runtime.

---

### 23.14 Управление промптами: реестр, версионирование, prompt-eval

Промпты версионируются локально в отдельных сервисах (§6.9 `prompts/`, §13.30 `prompts/` с версией, §11.2 prompt-tune). Нет сквозного реестра промптов, prompt-regression-eval и связи промпт↔метрики.

- [ ] Ввести единый реестр промптов (`packages/kg_common/prompts/` или per-service с общей конвенцией) с версией и хэшем каждого промпта (intent §13.8, planner §13.10, verifier §13.16, answer §13.17, extraction §6.9, graphrag §11.2, eval-judge §18.9).
- [ ] Связать версию промпта с прогонами и метриками: `prompt_version` в MLflow (§18.4), в `ExtractorRun` (§6.14), в agent `tool_trace`/state (§13.23) — для воспроизводимости (§7.1) и cost/quality-атрибуции.
- [ ] Реализовать prompt-regression-eval: изменение промпта прогоняется против golden (§18) и не должно ухудшать метрики §15.2 (gate на PR, интеграция с §18.11 regression-gate).
- [ ] Поддержать локализацию/двуязычность промптов там, где это влияет на язык ответа (§13.17, §23.8) без дублирования логики.
- [ ] Реализовать prompt-injection-safe шаблонизацию (§19.6): единый механизм изоляции недоверенного контента источников от инструкций во всех промптах, использующих контент документов.
- [ ] Задокументировать процесс изменения промпта (review + eval + version bump) в `docs/dev/prompts.md`.

**Критерий приёмки:** каждый промпт имеет версию/хэш в едином реестре и попадает в MLflow/`ExtractorRun`/`tool_trace`; изменение промпта запускает prompt-regression-eval и блокируется при регрессии метрик §15.2; prompt-injection-тест (§19.6) проходит для всех промптов с контентом источников; два прогона с той же версией промпта детерминированы.

---

### 23.15 Приватность данных, PII, retention и удаление (data privacy)

PII/retention затронуты точечно (PII-теги §10.11, retention audit §19.5, retention каталога §10.11, backup retention §19.8), но нет сквозной политики приватности: PII в `Person`/`ResearchTeam`, право на удаление, retention по всем хранилищам, обработка персональных данных авторов/сотрудников.

- [ ] Определить единую data-privacy политику `docs/security/privacy.md`: какие данные PII (Person: имена/ORCID/email §8.4; авторы документов), где хранятся (Neo4j/Postgres/Qdrant/OpenSearch/MinIO/каталог/логи/audit), правовая база и роли доступа (§19.3).
- [ ] Реализовать классификацию/тегирование PII-полей (§10.11 PII-теги) как single-source и применить маскирование в логах/трейсах (§18.1/§19.5) и в LLM-контексте (не отправлять лишние PII в промпты).
- [ ] Реализовать retention-политику по КАЖДОМУ хранилищу согласованно (raw/parsed §10.11, audit §19.5, backups §19.8, MLflow/traces, chat-история) с автоматической архивацией/удалением по расписанию (Dagster §9.5).
- [ ] Реализовать процедуру удаления/анонимизации субъекта данных (right-to-erasure): каскадное удаление/анонимизация Person и связанного контента во ВСЕХ хранилищах (граф, векторы, keyword-индекс, объекты, каталог, кэши) с записью в audit; учесть immutable audit (§19.5) через анонимизацию, а не удаление записи.
- [ ] Обеспечить, чтобы export/report (§17.16) и API-ответы не раскрывали PII недоступных пользователю источников (согласовать с access policy §19.3).
- [ ] Задокументировать data-flow PII и провести privacy-review как часть release-gate (§22.7).

**Критерий приёмки:** `docs/security/privacy.md` описывает все места хранения PII и их retention; PII маскируется в логах/трейсах и не утекает в LLM-контекст (тест); процедура right-to-erasure удаляет/анонимизирует субъекта во всех хранилищах с audit-записью; retention-джобы работают по расписанию для каждого хранилища.

---

### 23.16 SLO/SLI, алертинг, on-call и incident management

Метрики/дашборды/алерты и часть runbook'ов есть (§18.5 Prometheus/Grafana/alerts, §2.13 operational runbook, §19.12 runbooks), но нет владельца формальных SLO/SLI, on-call-процесса и incident-management как сквозного контура.

- [ ] Определить SLO/SLI в `docs/ops/slo.md`: доступность API, p95 chat/graph/search latency (§15.2/§23.9), ingestion success-rate, unsupported-claim-rate=0 (§18.8), error-budget policy.
- [ ] Настроить алерты на нарушение SLO (расширение §18.5 alert-rules): latency>SLO, error-rate, health degraded, unsupported-claim>0 на golden, ingestion failures, cost-budget (§23.10), backup-failure (§19.8), очередь review/dead-letter растёт.
- [ ] Определить каналы нотификаций и эскалацию (on-call): интеграция алертов с Slack/email/PagerDuty-подобным (переиспользовать notification-очередь §9.10); severity-уровни.
- [ ] Написать incident-response runbooks `docs/ops/incidents/` для типовых инцидентов: OOM Neo4j/OpenSearch (§2.13), недоступность docling/dagster/LLM, застрявшая очередь worker/Dagster, деградация retrieval-качества, compromised token (§19.12), исчерпание LLM-бюджета.
- [ ] Собрать единый operational-дашборд «здоровья системы» (agg §18.5 4 дашбордов + curation §16.11 + gap/coverage §15) для дежурного.
- [ ] Задокументировать процесс post-mortem и error-budget review.

**Критерий приёмки:** `docs/ops/slo.md` определяет SLO/SLI с error-budget; алерты срабатывают при нарушении каждого SLO (проверено принудительным нарушением, ср. §18.5); incident-runbooks покрывают типовые сбои; нотификация доходит до канала on-call; единый health-дашборд отражает все критичные подсистемы.

---

### 23.17 Обработка многоязычных и «грязных» входных документов (extraction robustness)

Extraction (§6) и materials-NER (§20.9) ориентированы на англоязычный материаловедческий текст, а агент нормализует ru/en вопросы (§13.7). Но обработка НЕанглоязычных исходных документов и устойчивость к «грязному» вводу как сквозная тема не покрыты.

- [ ] Определить политику языков исходных документов: детект языка документа/чанка (§13.7 детект языка — для вопроса; здесь — для документа), поддерживаемые языки extraction, стратегия для неподдерживаемых (перевод/пропуск/пометка).
- [ ] Реализовать детект языка на этапе chunking/extraction (§5.9/§6) и маршрутизацию: англоязычные модели (MatBERT/MatSciBERT/Matscholar §20.9) применять к en-тексту; для ru/др. — LLM-extraction (§6.9) с мультиязычным промптом или предварительный перевод терминов к canonical vocabulary (§3.2).
- [ ] Обеспечить двуязычный/мультиязычный поиск: запрос на ru находит en-контент (перевод/мультиязычные эмбеддинги §4.4, синонимы canonical vocab §3.2) — согласовать с retrieval (§12) и i18n (§23.8).
- [ ] Усилить устойчивость к «грязному» вводу: битые PDF/OCR-мусор (§5.8 fallback, §16.5 low_quality_ocr review), пустые/повреждённые файлы, огромные файлы (§14.9 лимиты), не тот формат (§5.3) — единый набор негативных фикстур и тестов.
- [ ] Обеспечить корректную обработку Unicode/спецсимволов в химических формулах/единицах (°C, ℃, ±, wt%, Å) сквозь весь пайплайн (§6.3 варианты единиц) и в индексах (§4.6 analyzer).
- [ ] Добавить в golden/extraction-golden (§6.17/§18.6) кейсы с ru-документами и «грязным» вводом; замерить деградацию метрик.

**Критерий приёмки:** язык документа детектируется и extraction маршрутизируется корректно; ru-запрос находит релевантный en-контент (тест мультиязычного поиска); негативные фикстуры (битый PDF, OCR-мусор, неверный формат, огромный файл) обрабатываются без падения пайплайна (в review/failed, не 500); спецсимволы формул/единиц сохраняются сквозь ingestion→extraction→index.

---

### 23.18 Эволюция онтологии и backfill/re-extraction при изменении схемы

§3.15 покрывает миграции constraints/indexes и `SchemaVersion`, но не покрывает DATA-миграцию при изменении СЕМАНТИКИ онтологии: как мигрировать/переизвлечь существующий граф при добавлении/переименовании label/rel/slot или смене extraction-схемы (§9.2 Step 7 «preserve previous versions» — только на уровне факта, не при эволюции модели).

- [ ] Определить процесс эволюции онтологии (`docs/dev/ontology-evolution.md`): версия `kg_ontology.yaml` (§3.2) → миграция схемы (§3.15) → data-backfill/re-extraction → re-index → re-eval; владелец и триггеры (§21.12 ontology-governance).
- [ ] Реализовать data-backfill миграции при добавлении новых обязательных полей/связей на существующие узлы (напр. новый provenance-slot, новая связь `HAS_EXTERNAL_REF` §20.3, новый gap-подтип §15.3): версионированный backfill-скрипт (§23.4).
- [ ] Реализовать контролируемое re-extraction корпуса при смене extraction-схемы/`pipeline_version` (§6.16): Dagster backfill по всем документам (§9.3 backfill) с новым `ExtractorRun`, сохранением истории и защитой reviewed-полей (§8.9/§16.8).
- [ ] Обеспечить, чтобы смена онтологии триггерила согласованное обновление: `/graph/schema` (§3.16), TS-типы фронтенда (§17.3), glossary каталога (§10.3), allowlist Text2Cypher (§12.10) — единым процессом, а не вручную по местам.
- [ ] Реализовать deprecation-политику для labels/rels/slots (мягкое устаревание с миграцией, а не резкое удаление) и совместимость чтения старых версий фактов (§3.7 versioning).
- [ ] Написать тест эволюции: добавить slot/rel в онтологию → миграция+backfill → существующие данные согласованы с новой схемой, reviewed-поля не тронуты, re-eval не деградировал.

**Критерий приёмки:** `docs/dev/ontology-evolution.md` описывает end-to-end процесс; изменение онтологии (новый slot/rel) через backfill приводит существующий граф в соответствие новой схеме без потери reviewed-данных; re-extraction по `pipeline_version` выполняется как Dagster-backfill с новым `ExtractorRun`; `/graph/schema`, TS-типы и glossary обновляются согласованно; тест эволюции зелёный.

---

### 23.19 Единая конфигурация окружений, feature flags и управление сборкой

Конфиг и флаги разбросаны (`Settings` §1.9, feature flags в Postgres §3.1, множество `ENABLE_*`/`*_ENABLED` в §4.1/§10/§11.12/§13/§20, Compose-профили §2.2, `/api/v1/config` §14.15). Нет единого владельца согласованности флагов, профилей окружений и их валидации.

- [ ] Свести все feature-flags и профили в единый реестр (`packages/kg_common/config.py` + `docs/ops/feature-flags.md`): полный список флагов (`opensearch_enabled`, `ENABLE_GRAPHRAG`, `ENABLE_RERANK`, `ENABLE_HITL`, `ENABLE_GRAPH_ALGO`, `METADATA_STACK_ENABLED`, `search_backend`, `ARTIFACT_VERSIONING`, `AGENT_TRACING`, connectors `*_ENABLED` и др.) с назначением, дефолтом и влиянием.
- [ ] Обеспечить согласованность флага между backend и frontend: публичные флаги отдаются через `/api/v1/config` (§14.15) и управляют UI (напр. отключённый GraphRAG скрывает соответствующий режим §17.9); единый source-of-truth.
- [ ] Валидировать профили окружений (`local`/`staging`/`prod`/`demo`, §2.2/§19.11) как согласованные наборы флагов+секретов; тест «профиль поднимается и внутренне непротиворечив» (напр. `METADATA_STACK_ENABLED=false` не ломает ingestion §10.4).
- [ ] Реализовать «минимальный MVP-профиль» (риск §18 «too many moving parts»): отключение OpenSearch/DataHub/GraphRAG/connectors одним профилем с работающей деградацией (§23.11) — и тест, что MVP-профиль проходит Phase 4/5 acceptance (§11.14/§22).
- [ ] Обеспечить fail-fast при несовместимых комбинациях флагов (напр. `search_backend=qdrant_opensearch` при `opensearch_enabled=false`) с понятной ошибкой.
- [ ] Задокументировать матрицу «флаг × профиль × влияние» и держать её в паритете с кодом (CI-проверка, что каждый флаг из кода есть в доке и наоборот).

**Критерий приёмки:** `docs/ops/feature-flags.md` перечисляет все флаги в паритете с `Settings` (CI-проверка); публичные флаги согласованы backend↔frontend через `/config`; каждый профиль (`local/staging/prod/demo/mvp`) поднимается и внутренне непротиворечив (тест); несовместимая комбинация флагов даёт fail-fast; MVP-профиль с отключёнными опциональными подсистемами проходит acceptance базовых фаз.

---

### 23.20 Итоговый gate сквозных задач и связь с Definition of Done

- [ ] Свести чек-лист §23.1–§23.19 и подтвердить, что каждая cross-cutting-тема из постановки (интеграционные тесты, контрактные тесты, фикстуры, миграции, seed/demo-корпус, user/dev-документация, локализация ru/en, нагрузочное тестирование, LLM-cost, resilience/ретраи, версионирование данных, а также добавленные: LLM/embedding-gateway, промпты, privacy/PII, SLO/on-call, многоязычный ввод, эволюция онтологии, feature-flags) имеет владельца-задачу и критерий приёмки.
- [ ] Интегрировать сквозные gate'ы в единый CI-мета-джоб (расширение `definition-of-done` §22.7): `e2e-integration` (§23.1), `contracts` (§23.2), load/perf-regression (§23.9), cost-budget (§23.10), resilience-injection (§23.11), reproducibility (§23.12), i18n-completeness (§23.8), privacy-review (§23.15), feature-flags-parity (§23.19).
- [ ] Дополнить `docs/DEFINITION_OF_DONE.md` (§22) разделом «Cross-cutting», где каждая подзона §23 закрывается ссылкой-доказательством (CI-run/отчёт/док).
- [ ] Обновить traceability-matrix (§23.7): каждая cross-cutting-тема сопоставлена коду/тесту/доку, gaps закрыты.
- [ ] Подтвердить, что отсутствие файла `section_07.md` не привело к потере запланированного содержания (агент покрыт §13); зафиксировать вывод в traceability-matrix.

**Критерий приёмки:** CI-мета-джоб `cross-cutting-gate` агрегирует все сквозные проверки §23 и завершается `GREEN`; `docs/DEFINITION_OF_DONE.md` содержит закрытый раздел «Cross-cutting» с доказательствами; traceability-matrix не имеет открытых cross-cutting-gaps; подтверждено, что пропуск `section_07.md` не потерял содержания.

---

### 23.21 Product discovery, MVP-slicing и управление scope

План описывает full-scale target-state, но ему нужен явный слой приоритизации, иначе набор задач превращается в бесконечный backlog. GraphRAG уже помечен как optional/SOTA (§11.14), минимальный demo-путь описан (§13.1 `make demo`, сценарии §2.1) — но нет единого владельца scope/приоритизации и защиты от scope creep.

- [ ] Сформировать 3 уровня реализации: Hackathon Demo, MVP, Full SOTA — и зафиксировать в `docs/product/scope.md`.
- [ ] Для каждой крупной фичи проставить уровень-метку: `demo|required`, `mvp|required`, `sota|optional`, `research|later` (согласовать с feature-flags §23.19 и статусами SOTA/optional §11.14).
- [ ] Составить RICE/WSJF-таблицу приоритетов: user value, risk reduction, effort, dependencies.
- [ ] Выделить critical path — минимальную цепочку `upload → parse → extract → upsert → search → chat answer → evidence click` (диаграмма, согласована с «золотым потоком» §23.1).
- [ ] Ввести `NOT NOW`-лист явно отложенных/отклонённых фич, чтобы ограничивать scope creep, и не тащить их в demo/MVP UI.
- [ ] Ввести правило: новая SOTA-фича попадает в план только при наличии acceptance-сценария и владельца.

**Критерий приёмки:** есть `docs/product/scope.md`, где каждая крупная фича помечена как Demo/MVP/SOTA/Later; есть диаграмма critical-path; CI/demo-gate (§22.7) проверяет минимальный end-to-end путь (пересекается с §23.1).

---

### 23.22 Domain expert validation loop (валидация ответов учёными/кураторами)

Golden datasets и eval есть (§18.6, §6.17, §13.25), но автоматические метрики не поймают «научно бесполезный, но формально правильный» ответ. Нужен отдельный контур валидации учёными/кураторами, связанный с curation (§16) и пользовательским feedback.

- [ ] Ввести научные (expert) метрики качества ответа: scientific usefulness, time-to-evidence, number of clicks to verify claim, trust score.
- [ ] Добавить в UI feedback-controls: `useful/not useful`, `wrong number`, `missing evidence`, `bad graph`, `bad entity match`.
- [ ] Связать feedback с eval/golden dataset (§18.6): пользовательская ошибка превращается в regression-тест.
- [ ] Ввести monthly expert review: 20 случайных ответов агента проверяются вручную.
- [ ] Хранить экспертные замечания как `ExpertReview`/`FeedbackEvent` с привязкой к answer/run/evidence (provenance §3.7, audit §10.8).

**Критерий приёмки:** минимум 30 expert-reviewed ответов; ≥80% ответов получают оценку useful/trustworthy; каждая найденная экспертами ошибка превращена в issue или regression-тест.

---

### 23.23 Product analytics и usage telemetry

В плане есть системные метрики и observability (§18, Prometheus/Grafana): latency, cost, health-checks. Но не хватает product-аналитики — как пользователи реально работают с системой. Телеметрия должна быть privacy-safe (согласовать с §23.15).

- [ ] Определить privacy-safe event taxonomy: `question_asked`, `answer_viewed`, `evidence_clicked`, `graph_expanded`, `gap_opened`, `curation_action`, `export_created`, `document_uploaded`.
- [ ] Реализовать frontend/backend tracking без PII и без содержания закрытых документов (§23.15/§23.28).
- [ ] Считать funnel: question → answer → evidence click → accepted/curated.
- [ ] Считать adoption-метрики: DAU/WAU, active labs, uploaded docs/week, answered questions/week.
- [ ] Считать trust-метрики: evidence click rate, unsupported answer reports, correction rate (связать с §23.22 feedback).
- [ ] Добавить дашборд `Product Usage`: самые частые materials/properties, самые проблемные gaps, самые активные лаборатории.
- [ ] Добавить opt-out/disable-telemetry профиль для закрытых установок (§23.19 профили).

**Критерий приёмки:** Grafana/Admin показывает usage-дашборд; события не содержат сырой текст закрытых документов; product-метрики используются в release review.

---

### 23.24 KG Health Score и data-quality scorecards

Gap analysis есть (§15), но нет отдельной метрики здоровья графа: не только «где пробелы», а насколько граф пригоден для поиска и анализа.

- [ ] Ввести общий `KGHealthScore` 0–100.
- [ ] Метрики: evidence coverage, orphan node rate, duplicate entity rate, contradiction rate (§15), unresolved review tasks (§16), missing units (§7.6), missing baseline, stale sources (§23.27), schema violations (§3.15).
- [ ] Считать score по срезам: lab, material family, property, source type, time range.
- [ ] Сделать daily Dagster-job `kg_health_scan` (§9.5 schedules).
- [ ] Добавить Admin-дашборд `KG Health`.
- [ ] Ввести деградационные пороги: если evidence coverage < X или orphan rate > Y — CI/demo-gate (§22.7) падает.
- [ ] Добавить export `kg_health_report.md/json`.

**Критерий приёмки:** `GET /api/v1/admin/kg-health` возвращает score и breakdown; дашборд показывает худшие области графа; demo-корпус имеет score выше заранее заданного порога.

---

### 23.25 Confidence calibration и uncertainty model

В плане много `confidence`/`review_status` (§3.7, §6.15, §8.7), но нет калибровки: число 0.83 выглядит убедительно, но неизвестно, что оно значит. Усиливает существующие блоки evidence-first (§3.6), review queue (§16) и метрики ER (§8.13).

- [ ] Разделить типы уверенности: extraction_confidence, entity_resolution_confidence, retrieval_score, evidence_quality, answer_confidence.
- [ ] Создать calibration dataset: предсказания extractor/ER/verifier + human labels (§23.26).
- [ ] Построить reliability diagrams и Expected Calibration Error (ECE) для extraction и ER.
- [ ] Откалибровать thresholds: auto-accept, review-needed, reject (§6.15/§8.7).
- [ ] Добавить UI-пояснения: confidence ≠ truth, verified ≠ automatically extracted.
- [ ] Ввести uncertainty-labels: `high confidence`, `needs review`, `conflicting`, `unsupported`, `estimated`.
- [ ] Добавить regression-тест: после смены модели (§23.13/§23.33) calibration не ухудшается выше порога.

**Критерий приёмки:** есть `docs/eval/confidence_calibration.md`; ECE считается в eval-job (§18); auto-review thresholds основаны на калиброванных данных, а не на произвольных 0.7/0.9.

---

### 23.26 Annotation protocol и quality control разметки

Задачи на golden dataset и ground-truth разметку есть (§18.6, §8.12, §6.17), но нет процесса: как размечать, как решать разногласия, как мерить качество разметки (IAA).

- [ ] Написать `docs/annotation/GUIDELINES.md`: как размечать Material, Regime, Property, Measurement, Evidence, Claim, Gap, Contradiction.
- [ ] Создать annotation UI или выбрать готовый инструмент: Label Studio / Argilla / Prodigy-like workflow.
- [ ] Ввести двойную разметку минимум 20% документов.
- [ ] Считать inter-annotator agreement: Cohen's kappa / Krippendorff alpha по entity/fact/evidence.
- [ ] Ввести adjudication workflow: disagreement → решение senior-куратора (§16).
- [ ] Версионировать annotation-схему.
- [ ] Связать annotation-версию с eval-runs в MLflow (§18.4/§23.12).
- [ ] Использовать active learning: выбирать на разметку примеры с высокой uncertainty (§23.25).

**Критерий приёмки:** golden dataset имеет annotation-версию, guidelines и IAA-отчёт; спорные кейсы задокументированы; eval не принимает данные без annotation provenance.

---

### 23.27 Source trust, retractions и freshness

Для научной системы важно учитывать, что статья может быть отозвана, устареть, противоречить более новым данным или быть low-quality source.

- [ ] Добавить модель `SourceTrust`: peer-reviewed/preprint/internal/lab-note/vendor-doc/manual.
- [ ] Интегрировать проверку DOI/metadata на retraction/correction, где доступно.
- [ ] Добавить поле `source_status`: active, corrected, retracted, superseded, deprecated.
- [ ] При retracted/superseded источнике не удалять факты, а понижать trust и показывать warning.
- [ ] Добавить freshness score для данных и документов.
- [ ] В answer-verifier (§13.16) учитывать source trust/freshness.
- [ ] Добавить UI-warning: «источник отозван/устарел/непроверен».
- [ ] Добавить тест: ответ не должен использовать retracted evidence как основной источник без предупреждения.

**Критерий приёмки:** source c `source_status=retracted` виден в graph/evidence, но answer содержит warning; verifier снижает confidence; freshness отображается в citations.

---

### 23.28 Scientific IP, embargo и publication workflow

В плане есть security, RBAC, audit (§19) и corpus license-review (§23.5). Но для научной/лабораторной системы нужен отдельный IP/compliance-слой поверх внутренних данных.

- [ ] Ввести классификацию источников: public, internal, confidential, patent-sensitive, embargoed.
- [ ] Добавить `embargo_until` и `publication_status` на документы/эксперименты.
- [ ] Запретить export/citation внешним пользователям для embargoed/patent-sensitive данных.
- [ ] Добавить redaction-pipeline для exports: скрытие lab/person/confidential values.
- [ ] Добавить policy-тест: researcher из Lab A не может получить evidence из Lab B через chat, search, graph, export или prompt injection (§19.3/§19.12).
- [ ] Добавить approval workflow для публикации evidence pack наружу (§23.29).
- [ ] Добавить audit-событие `export_sensitive_attempt` (§10.8).

**Критерий приёмки:** embargoed source не появляется в ответах и экспортах без нужной роли; все попытки доступа фиксируются в audit; redacted export проходит snapshot-тест.

---

### 23.29 Reproducible Evidence Pack

Экспорт графа/CSV уже есть (§17), но для исследователя полезен reproducible answer package: вопрос, ответ, граф, таблицы, доказательства, версии моделей, все citations.

- [ ] Реализовать export ответа в `Evidence Pack`: HTML/PDF/ZIP/JSON.
- [ ] Включить: original question, normalized query, final answer, experiments table, graph snapshot, evidence snippets, document pages, citations, gaps, contradictions.
- [ ] Включить provenance: model version, prompt version, extractor_run_id, graph schema version, data snapshot version, retrieval scores (§23.12/§23.13/§23.14).
- [ ] Добавить deterministic replay: `POST /api/v1/answers/{answer_id}/replay` на том же data snapshot.
- [ ] Добавить cryptographic checksum/manifest для evidence pack.
- [ ] Добавить UI-кнопку `Export evidence pack`.

**Критерий приёмки:** экспортированный evidence pack позволяет воспроизвести ответ и проверить каждое число по evidence; replay на том же snapshot даёт тот же ответ или объясняет divergence.

---

### 23.30 Python SDK и CLI для исследователей

API Gateway хорошо покрыт (§14), но научным пользователям и data engineers нужен SDK/CLI, чтобы не делать всё через UI.

- [ ] Создать `packages/kg_client/` — typed Python SDK поверх REST API (§14).
- [ ] Методы: `upload_document`, `ask`, `search_experiments`, `get_evidence`, `export_subgraph`, `run_gap_scan`, `list_sources`.
- [ ] Сгенерировать клиент из OpenAPI или поддерживать вручную с contract-тестами (§23.2).
- [ ] Сделать CLI `kg`:
  - `kg upload file.pdf`
  - `kg ask "что делали по Al-Cu ..."`
  - `kg experiments query --material ...`
  - `kg graph export --entity ...`
  - `kg gaps scan`
- [ ] Добавить Jupyter-notebook примеры для исследователей.
- [ ] Добавить auth/profile support: `kg login`, `kg config set profile`.

**Критерий приёмки:** researcher может загрузить документ и задать вопрос из Jupyter/CLI; SDK проходит contract-тесты против OpenAPI; версия SDK синхронизирована со схемой API.

---

### 23.31 Baseline/ablation benchmark

Eval есть (§18), но SOTA-плану нужен честный ответ: насколько система лучше plain RAG, Neo4j-only, GraphRAG-only и keyword search. Retrieval modes/fusion уже заложены (§12) — не хватает baseline/ablation как доказательства «SOTA».

- [ ] Реализовать baseline A: plain vector RAG без KG.
- [ ] Baseline B: BM25/OpenSearch only.
- [ ] Baseline C: Neo4j structured templates only.
- [ ] Baseline D: GraphRAG community only.
- [ ] Full system: structured + hybrid + graph proximity + rerank + verifier (§12).
- [ ] На golden dataset (§18.6) сравнить Recall@10, MRR, citation precision, numeric accuracy, unsupported claim rate, latency, cost/query.
- [ ] Добавить ablation-флаги: without reranker, without graph_proximity, without evidence_quality, without verifier (§23.19).
- [ ] Публиковать benchmark-report в MLflow и `docs/eval/benchmark_report.md`.
- [ ] Использовать конкретные SOTA-бейзлайны и лидерборды из §23.35 вместо самодельных: GraphRAG-режим сравнивать с **LightRAG / HippoRAG2 / PathRAG / MS GraphRAG**; парсинг — прогонять на **OmniDocBench / olmOCR-Bench**; faithfulness — на **FaithJudge/HHEM** (с open-weight судьёй, §23.33); научный QA/контр­адикции — на **LitQA2 / HalluMatData**; extraction — на **SciNLP / MatSciNLP**; entity linking — на **ZESHEL / GLADIS**.

**Критерий приёмки:** full system статистически лучше baseline по ключевым метрикам либо документированно объяснены trade-offs; benchmark воспроизводим одной командой; сравнение включает ≥1 внешний SOTA-репозиторий из §23.35 (LightRAG/HippoRAG2/PathRAG) и ≥1 публичный лидерборд (OmniDocBench/FaithJudge).

---

### 23.32 Collaboration и shared investigations

Curation есть (§16), но нет полноценной совместной работы исследователей вокруг графа.

- [ ] Добавить комментарии к Entity/Experiment/Evidence/Gap/Answer.
- [ ] Добавить mentions пользователей/лабораторий в комментариях.
- [ ] Добавить shared investigation workspace: сохранённая подборка entities, filters, graph view, notes, answer history.
- [ ] Добавить статусы: draft, in_review, resolved, archived.
- [ ] Добавить notification center: assigned review, mentioned, evidence corrected, gap closed.
- [ ] Добавить activity feed по проекту/лаборатории.
- [ ] Связать comments с audit/provenance (§10.8), но не считать их factual evidence без ручного promoted-статуса.

**Критерий приёмки:** два пользователя могут совместно разобрать contradiction/gap, оставить комментарии, назначить action и сохранить investigation; история видна в entity detail.

---

### 23.33 Model runtime, OpenRouter и политика open-source-only моделей

Система использует OpenRouter как единый шлюз к LLM (ключ в `Settings` §1.9). Жёсткое продуктовое ограничение: в основном runtime разрешены ТОЛЬКО open-source/open-weight модели с признанной открытой лицензией. Эта политика является authoritative и переопределяет упоминания проприетарных провайдеров в §6.9/§13.4/§23.13. Дополнительно нужен экран `Model Runtime` в demo/Admin.

- [ ] Зафиксировать провайдера LLM: OpenRouter как единый шлюз к моделям (ключ/endpoint в §1.9, интеграция через LLM-gateway §23.13).
- [ ] Ввести жёсткое ограничение «open-source-only»: разрешены только open-weight/open-source модели с признанной открытой лицензией (Apache-2.0/MIT/OpenRAIL/Llama-community и аналоги); проприетарные закрытые модели (GPT-4o, Claude, Gemini и т.п.) запрещены как основной runtime.
- [ ] Реализовать allowlist разрешённых моделей (`docs/models/allowed_models.md` + конфиг в `packages/kg_common`): для каждой модели — OpenRouter id, лицензия, размер, длина контекста, модальность (text/vision), назначение (extraction/agent/embedding/reranker/judge).
- [ ] Enforcement в LLM-gateway (§23.13): запрос к модели вне allowlist → fail-fast с понятной ошибкой; запретить обход allowlist прямыми клиентами провайдера.
- [ ] Добавить CI-проверку `models-policy`: ни один сервис не конфигурирует закрытую/не-open-source модель по умолчанию; каждая модель из кода/конфига присутствует в allowlist с валидной open-лицензией.
- [ ] Применить политику в §6.9 (LLM-extraction) и §13.4 (agent): дефолтные проприетарные модели заменить на open-source аналоги через OpenRouter, сохранив structured-output/tool-use на open-моделях.
- [ ] Добавить в demo UI/Admin экран `Model Runtime`: текущая модель, provider (OpenRouter), лицензия, размер, режим запуска (hosted/local), estimated cost/query (§23.10), статус соответствия open-source-политике.
- [ ] Отразить модели/лицензии в реестре моделей (§23.13) и в Evidence Pack provenance (§23.29); cost/query связать с LLM-cost governance (§23.10).

**Критерий приёмки:** все LLM-вызовы идут через OpenRouter-шлюз и только к моделям из open-source allowlist; CI-проверка `models-policy` падает при попытке использовать закрытую модель; экран `Model Runtime` показывает текущую модель, провайдера, лицензию и cost/query; в плане нет дефолтных проприетарных моделей в основном runtime.

---

### 23.34 Обработка изображений и документов с картинками (multimodal ingestion/extraction)

Docling (§5) парсит PDF/DOCX/PPTX, но фигуры/графики/микроструктуры/диаграммы и документы «только картинки» (сканы) как сквозная тема не покрыты. Мультимодальная extraction должна использовать open-source vision-модели через OpenRouter (политика §23.33).

- [ ] Определить политику обработки изображений в документах: извлечение figures/charts/tables-as-image/micrographs/diagrams при парсинге (§5.7), хранение как artifacts в object storage (§5.5) с привязкой к странице/документу.
- [ ] Поддержать документы «только картинки» (сканы, изображения-страницы): OCR (§5.8 fallback, §23.17 «грязный» ввод) + маршрутизация в extraction.
- [ ] Ввести image/figure-узлы в графе с evidence-привязкой (§8.3/§3.6): `Figure`/`Image` c bbox, caption, страницей и `SUPPORTED_BY`-связью к фактам.
- [ ] Реализовать multimodal-extraction через open-source vision-модель (VLM) на OpenRouter (§23.33 open-source-only): описание фигуры/микроструктуры, извлечение подписей и чисел из графиков — с confidence (§23.25) и маршрутизацией в review (§16).
- [ ] Индексировать captions/описания изображений в поиске (§4) и связывать с evidence/citations (§13.14); в ответе показывать фигуру как evidence.
- [ ] Добавить в UI (evidence inspector §17) просмотр изображения-доказательства с подсветкой bbox/страницы.
- [ ] Добавить golden/negative-кейсы (§6.17/§23.17): документ с ключевой таблицей-картинкой и график с числами; замерить, что числа извлекаются либо помечаются как «нужен review».

**Критерий приёмки:** документ с фигурами/картинками парсится с извлечением изображений и captions; хотя бы один факт поддержан image-evidence с bbox/страницей; multimodal-extraction использует только open-source VLM через OpenRouter (§23.33); изображение-доказательство отображается в UI и участвует в citations.

---

### 23.35 SOTA papers-with-code (2025–2026): каталог для вендоринга, бенчмарков и reference-архитектур

Раздел — результат целевого SOTA-скана 2025–2026 по подсистемам системы (deep-research: 5 углов → 25 источников → 121 claim → адверсариальная верификация 3 голосами). Включены только работы с публичным кодом/весами. Для каждой позиции статус: **adopt** (вендорить/интегрировать, §21), **benchmark** (сравнивать в §23.31/§18.11), **reference** (архитектурный образец, не тащить as-is). Лицензии проверяются под политику open-source-only (§23.33) и правила вендоринга (§21); non-permissive/закрытые компоненты помечены ⚠. arXiv-id даны как reported — валидировать при вендоринге.

**Парсинг документов и multimodal (§5/§23.34):**
- [ ] **Docling** — `github.com/docling-project/docling` (MIT, arXiv:2408.09869; IBM / LF AI & Data). PDF/DOCX/PPTX/HTML→structured (layout, reading order, tables, formulas), экспорт Markdown/HTML/JSON/DocTags, VLM GraniteDocling/SmolDocling для фигур, интеграции LangChain/LlamaIndex/Haystack. **adopt** — закрепить как основной парсер (уже частично в §5/§4827).
- [ ] **MinerU 2.5** — `github.com/opendatalab/MinerU` (arXiv:2509.22186; 1.2B VLM, open weights). Decoupled layout→native-resolution recognition; SOTA на OmniDocBench (MinerU2.5-Pro 95.75 / MinerU2.5 93.04) при низком compute. **adopt/benchmark** как VLM-парсер формул/таблиц (§23.34).
- [ ] **olmOCR 2** — `github.com/allenai/olmocr` (Apache-2.0, arXiv:2510.19817; olmOCR-2-7B-1025 на Qwen2.5-VL-7B, обучен RLVR). 82.4 olmOCR-Bench (vs GPT-4o 68.9, MinerU2.5 75.2, Marker 76.1); лидер по формулам/таблицам/multi-column. **adopt/benchmark** для OCR-тяжёлых сканов (§23.34/§23.17).
- [ ] **OmniDocBench** — `github.com/opendatalab/OmniDocBench` (Apache-2.0, CVPR2025, arXiv:2412.07626). 1651 стр., 10 типов документов; end-to-end/OCR/table/formula/layout; метрики TEDS/CDM/edit-distance; лидерборд MinerU/olmOCR/Marker/Docling/Nougat + open VLM (Qwen2-VL-72B 89.78, InternVL2-76B). **adopt** как эталон приёмки парсинга (§18.11/§23.31).
- [ ] Лиды: **PaddleOCR-VL** (arXiv:2510.14528, 0.9B VLM), formula-extraction benchmark (arXiv:2512.09874) — **reference** (fetch не подтвердил детали — проверить перед вендорингом).

**KG-extraction (schema-guided, evidence-span, §6):**
- [ ] **llm-ie** — `github.com/daviden1013/llm-ie` (JAMIA Open 2025, DOI 10.1093/jamiaopen/ooaf012). NER/attribute/relation-пайплайны; char-level span-grounding (совпадает с «no span→no fact» §6.10); backends OpenRouter/vLLM/Ollama/HF/LiteLLM, конфиги под Qwen3/GPT-OSS. ⚠ **нет лицензии** (all-rights-reserved) → **reference** (перенимать паттерн, не вендорить as-is).
- [ ] **OneKE** — `github.com/zjunlp/OneKE` (WWW 2025). Dockerized schema-guided LLM-agent knowledge extraction. **adopt/reference** для §6.9/§6.13.
- [ ] **KARMA** (arXiv:2502.06472, NeurIPS2025 spotlight) — 9-агентный schema-guided extraction + verification (83.1% LLM-verified, −18.6% conflict edges, 1200 PubMed). **reference** для orchestration §6.13 + verifier §13.16 (eval биомед, не materials; repo/лицензия/бэкбоны не подтверждены).
- [ ] **GLiNER-Relex** (arXiv:2605.10108) — joint NER+RE поверх GLiNER (GLiNER уже в §6.7). **reference/лид**.
- [ ] Anchor-constrained grounded KG extraction (MDPI Computers 15/3/178) — **reference** для provenance-anchored extraction (§3.7).
- [ ] Survey **LLM-empowered KG Construction** (arXiv:2510.20345) — таксономия schema-based vs schema-free, ontology→extraction→fusion; **reference** (кода нет).

**Materials NER / ER / units (§7/§8/§20.9):**
- [ ] **MatKG** — Nature Sci Data `s41597-024-03039-z` (MatBERT-NER, MatScholar-схема: 7 типов Material/Property/Application/Synthesis/Characterization/Descriptor/Symmetry; ~2M триплетов, TransE-эмбеддинги MRR 0.49). **adopt** онтологию/типы (§3.2/§20.9); ⚠ связи — co-occurrence, не span-grounded → не использовать как evidence.
- [ ] **Symbol/entity-marker + LLM** (arXiv:2505.05864) — гибрид encoder+CRF NER → генеративное структурирование; **+58% entity-F1 / +83% relation-F1** vs прямого LLM; всё open-weight (Llama-3.3-70B, Llama-3.2-3B, MatSciBERT/MatBERT+CRF; Ollama/llama.cpp/Unsloth), датасеты на HF. **adopt** как паттерн двухфазной extraction (§6.13), SOTA на MatScholar/SOFC/SOFC-Slot.
- [ ] **grobid-quantities** — `github.com/kermitt2/grobid-quantities` (Apache-2.0; CRF + SI-нормализация, вход PDF/XML/text, модуль GROBID). **adopt** в §7 как дополнение к `pint` для парсинга величин и SI-конверсии.
- [ ] **LELA** (arXiv:2601.05192) — zero-shot entity linking, 83.11 ZESHEL (+8.84 п.п. к SOTA), 62.3 GLADIS; open-weight (Magistral-Small-2509, Qwen3-30B-A3B/4B, Qwen3-Reranker/Embedding-4B); pipeline BM25/dense→pointwise rerank→self-consistency. **reference** для §8 ER (⚠ код «to be released» — проверить).
- [ ] Backbones/бейзлайны: **MatSciBERT / MatBERT / MaterialsBERT / LLaMat(-Chat)** — кандидаты §20.9.

**GraphRAG / retrieval (§11/§12):**
- [ ] **LightRAG** — `github.com/HKUDS/LightRAG` (MIT, EMNLP2025, arXiv:2410.05779). Dual-level graph+vector retrieval, 5 режимов (local/global/hybrid/naive/mix), backends Neo4j/Qdrant/OpenSearch/Milvus/PG, bge-m3; win-rate vs NaiveRAG 60–85%, ~паритет с MS GraphRAG. **adopt/benchmark** как лёгкая альтернатива GraphRAG (§11.12/§12).
- [ ] **HippoRAG 2** — `github.com/OSU-NLP-Group/HippoRAG` (MIT, ICML2025 arXiv:2502.14802 / NeurIPS2024 arXiv:2405.14831). KG + Personalized PageRank «долговременная память», non-parametric continual learning; vLLM open-weight (Llama-3.3-70B), NV-Embed-v2/GritLM/Contriever. **adopt/benchmark** для graph-proximity/memory (§12.5).
- [ ] **PathRAG** — `github.com/BUPT-GAMMA/PathRAG` (MIT, arXiv:2502.14902). Flow-pruned relational-path retrieval → текст для LLM; Qwen/Ollama/vLLM; лучше graph-RAG бейзлайнов на 6 датасетах. **benchmark/adopt** (§12.2/§12.5).
- [ ] **KAG** — `github.com/OpenSPG/KAG` (Ant / OpenSPG). Knowledge-augmented generation для professional domains. **benchmark/reference** (§11/§12).

**Faithfulness / hallucination / contradiction (§13.16/§15/§18):**
- [ ] **PaperQA2 / ContraCrow** — `github.com/Future-House/paper-qa` (arXiv:2409.13740). Agentic научный QA («superhuman synthesis»), contradiction detection 2.34/paper (70% human-validated), бенчмарк **LitQA2**, cited-ответы. **reference** для §13 (agent), §15 (contradictions), §23.29 (evidence pack).
- [ ] **HalluMatDetector / HalluMat** (arXiv:2512.22396) — materials-specific: contradiction-graph (Louvain по semantic-similarity) + hybrid FAISS+BM25+NLI (Entail/Neutral/Contradict), −30% hallucinations; бенчмарк **HalluMatData** (2629 queries) + метрика PHCS. **reference** для §15 + verifier §13.16.
- [ ] **FaithJudge / HHEM** — `github.com/vectara/FaithJudge` (EMNLP2025 Industry, arXiv:2505.04847). LLM-as-judge faithfulness-лидерборд по 46 моделям (Llama/Qwen/Mistral) для summarization/QA/data-to-text. **benchmark** (§18/§23.31); ⚠ судья — закрытый o3-mini → заменить open-weight judge (§23.33).
- [ ] **FRANQ** — `github.com/stat-ml/rag_uncertainty` (arXiv:2505.xxxxx). Claim-level factuality-vs-faithfulness UQ + LFQA-датасет с двойной разметкой. ⚠ **нет лицензии** → **reference**.

**Open-weight модели для allowlist (§23.33):**
- [ ] LLM: Llama-3.3-70B / 3.1-8B, Qwen2.5 / Qwen3 (30B-A3B, 4B), Mistral / Magistral-Small-2509, DeepSeek, GPT-OSS.
- [ ] VLM (парсинг/фигуры): Qwen2.5-VL-7B, olmOCR-2-7B-1025, MinerU2.5 (1.2B), InternVL2, GraniteDocling/SmolDocling, PaddleOCR-VL (0.9B).
- [ ] Embeddings/rerankers: BAAI/bge-m3, Qwen3-Embedding-4B, Qwen3-Reranker-4B, NV-Embed-v2, GritLM, Contriever.
- [ ] Materials backbones: MatSciBERT, MatBERT, MaterialsBERT, LLaMat/LLaMat-Chat.

**Benchmarks/datasets в golden/eval (§18.6/§23.31):** OmniDocBench, olmOCR-Bench (парсинг); SciNLP (⚠ CC BY-NC), MatSciNLP (extraction); LitQA2, MACBENCH, LLM4Mat-Bench (QA); FaithJudge/HHEM, HalluMatData (faithfulness); ZESHEL, GLADIS (entity linking); MatScholar (корпус/NER).

**Критерий приёмки:** каждая позиция со статусом **adopt** заведена в §21 (способ вендоринга + проверка LICENSE) и имеет задачу-интеграцию в профильном разделе; каждая **benchmark**-позиция включена в §23.31 как бейзлайн/лидерборд с воспроизводимым прогоном; ⚠-позиции (нет лицензии / non-commercial / закрытый компонент) НЕ вендорятся as-is — только reference или замена на open-weight аналог (§23.33); каталог пересматривается при смене онтологии/моделей.
---


## 24. «Научный клубок» — доменная адаптация под горно-металлургические R&D

Раздел добавляет к базовой Knowledge-Graph архитектуре предметную специализацию для горно-металлургических исследований. Он закрывает требования к единой карте знаний R&D: связывает публикации, патенты, внутренние отчёты, протоколы экспериментов, технологические решения, материалы/вещества, оборудование, экспертов, лаборатории, выводы и рекомендации. Главный результат раздела — система должна отвечать на сложные инженерно-научные запросы вида «материал + процесс + условия + география + временной диапазон + числовые ограничения» с доказательствами, уровнем достоверности, датой актуализации и различением отечественной/зарубежной практики.

Раздел не заменяет существующие подсистемы §1–§23, а расширяет их: доменная онтология — §3, ingestion — §5, extraction — §6, units — §7, ER — §8, retrieval — §12, agent — §13, API — §14, frontend — §17, evaluation — §18, security — §19, integrations — §20, Definition of Done — §22.

Затрагиваемые компоненты:
- `packages/kg_schema/` — доменные labels/relationships/enums/JSON-LD/SHACL для горно-металлургии.
- `packages/kg_extractors/` — ru/en NLP-экстракторы процессов, материалов, параметров, оборудования, выводов, технико-экономических показателей.
- `packages/kg_retrievers/` — шаблоны многопараметрического поиска и сравнительного анализа.
- `apps/agent-service/` — специализированные query plans и tools для R&D-вопросов.
- `apps/frontend/` — экраны «карта знаний», «сравнение технологий», «эксперты», «дашборд покрытия знаний».
- `apps/curation-service/` — экспертная правка графа, верификация выводов, фиксация разногласий.
- `infra/dagster/` — регулярное обновление корпуса, уведомления и пересчёт метрик покрытия.

---

### 24.1 Матрица трассировки требований «Научный клубок» → подсистемы

- [x] Создать `docs/domain/science_ball_requirements_traceability.md`: таблица «требование → раздел плана → сервис/пакет → критерий приёмки → тест/демо».
- [x] Включить в матрицу все проблемные сценарии: потеря институциональной памяти, дублирование литературных обзоров, междисциплинарный поиск, медленное принятие решений, противоречивые выводы.
- [x] Для каждого из четырёх примерных пользовательских запросов завести отдельный acceptance-сценарий с входом, ожидаемым типом ответа, обязательными фильтрами и evidence-требованиями.
- [x] Добавить в `docs/domain/scope.md` границы домена: гидрометаллургия, пирометаллургия, экология, переработка отходов, обогащение, очистка шахтных/оборотных вод, газоочистка, электроэкстракция, кучное выщелачивание.
- [x] Разделить требования на MVP, v1 и post-v1: MVP закрывает загрузку корпуса, граф, evidence, поиск и 4 демонстрационных вопроса; v1 добавляет уведомления, сравнительные таблицы, dashboards, экспертное редактирование и JSON-LD export.
- [x] Зафиксировать набор «не потерять при реализации»: source, confidence, date актуализации, geography, numeric ranges, review status, expert/lab ownership.
- [x] Добавить чек-лист «что считается доказанным ответом»: есть минимум 1 источник, указаны страницы/таблицы/ячейки, confidence, дата актуализации и статус верификации.
- [x] Включить карту зависимостей между предметными областями: вода ↔ обогащение, электролит ↔ электроэкстракция, штейн/шлак ↔ распределение Au/Ag/МПГ, газоочистка ↔ SO₂.

**Критерий приёмки:** все требования из постановки присутствуют в traceability-матрице; для каждого требования указан владелец реализации и проверяемый тест; 4 примерных запроса имеют формализованные acceptance-cases.

---

### 24.2 Расширение доменной онтологии под горно-металлургию

- [ ] Расширить `kg_ontology.yaml` новыми классами: `Ore`, `OreBody`, `Deposit`, `Concentrate`, `Matte`, `Slag`, `Tailings`, `MineWater`, `ProcessWater`, `Electrolyte`, `Catholyte`, `Anolyte`, `GasStream`, `FlueGas`, `LeachSolution`, `PregnantLeachSolution`, `Raffinate`, `Waste`, `TechnogenicGypsum`, `CoalWaste`.
- [ ] Добавить классы технологических процессов: `DesalinationProcess`, `WaterTreatment`, `MineWaterInjection`, `Electrowinning`, `Electrorefining`, `Leaching`, `HeapLeaching`, `Bioleaching`, `Flotation`, `FlashSmelting`, `FluidizedBedFurnaceProcess`, `GasCleaning`, `SO2Removal`, `WasteProcessing`.
- [ ] Добавить классы технологических решений: `TechnologySolution`, `FlowSheet`, `CirculationScheme`, `ElectrolyteFeedingScheme`, `CatholyteCirculationMode`, `DiaphragmCellDesign`, `ChargeFeedingMethod`, `GasCleaningScheme`, `WaterInjectionScheme`.
- [ ] Добавить классы оборудования: `ElectrowinningCell`, `DiaphragmCell`, `NickelCathode`, `ElectrolyteDistributor`, `Pump`, `FlashSmeltingFurnace`, `FluidizedBedFurnace`, `GasCleaningUnit`, `ReverseOsmosisUnit`, `IonExchangeUnit`, `DeepInjectionWell`, `Thickener`, `FilterPress`, `TailingsFacility`.
- [ ] Добавить классы параметров и свойств: `Concentration`, `TotalDissolvedSolids`, `FlowVelocity`, `FlowRate`, `CurrentDensity`, `Voltage`, `Temperature`, `Pressure`, `pH`, `Eh`, `Recovery`, `DistributionCoefficient`, `PartitionRatio`, `RemovalEfficiency`, `CAPEX`, `OPEX`, `NPV`, `PaybackPeriod`, `SpecificEnergyConsumption`.
- [ ] Добавить классы контекста: `Geography`, `Country`, `Region`, `ClimateZone`, `Facility`, `Plant`, `Mine`, `Smelter`, `Refinery`, `PracticeType` (`domestic|foreign|global|unknown`).
- [ ] Добавить классы knowledge-output: `Recommendation`, `Limitation`, `ApplicabilityCondition`, `ConsensusFinding`, `Disagreement`, `KnowledgeGap`, `TechnologyComparison`.
- [ ] Добавить связи: `treats_water`, `removes_contaminant`, `injects_into_horizon`, `circulates_electrolyte`, `feeds_electrolyte_to_cell`, `operates_in_climate`, `implemented_in_country`, `has_technoeconomic_indicator`, `has_applicability_condition`, `has_limitation`, `recommends_solution`, `compares_with`, `has_practice_type`.
- [ ] Добавить связи распределения металлов: `distributes_between`, `partitioned_to_phase`, `has_distribution_coefficient`, где фазы включают `Matte`, `Slag`, `Gas`, `MetalPhase`.
- [ ] Добавить enum `MetallurgicalDomain`: `hydrometallurgy`, `pyrometallurgy`, `environment`, `water_treatment`, `waste_processing`, `mineral_processing`, `electrometallurgy`.
- [ ] Добавить enum `PracticeGeography`: `russia`, `cis`, `foreign`, `global`, `unknown`; связать его с фильтрами поиска.
- [ ] Добавить enum `EvidenceStrength`: `peer_reviewed`, `patent`, `internal_report`, `experiment_protocol`, `standard`, `expert_comment`, `unverified`.
- [ ] Обновить constraints/indexes Neo4j под новые labels и поля: `country`, `region`, `practice_type`, `domain`, `updated_at`, `evidence_strength`, numeric-поля параметров.
- [ ] Сгенерировать документацию онтологии `docs/domain/metallurgy_ontology.md` с диаграммой «материал → процесс → оборудование → параметр → результат → evidence».

**Критерий приёмки:** LinkML/Pydantic-схема валидируется; все новые labels/relationships попадают в `/api/v1/graph/schema`; seed-граф содержит минимум по одному примеру для воды, электроэкстракции никеля, ПВП/плавки, кучного выщелачивания, шахтных вод и газоочистки SO₂.

---

### 24.3 Таксономия, словари и синонимы RU/EN

- [x] Создать `packages/kg_schema/resources/domain_taxonomy/` с YAML-словарями: `materials.yaml`, `processes.yaml`, `equipment.yaml`, `properties.yaml`, `units.yaml`, `geography.yaml`, `technology_solutions.yaml`.
- [x] В `processes.yaml` добавить RU/EN-синонимы: `электроэкстракция|electrowinning`, `электролизное извлечение`, `electroextraction`; `ПВП|печь взвешенной плавки|flash smelting furnace`; `fluidized bed furnace|печь кипящего слоя`.
- [x] Добавить синонимы для водоподготовки: `обессоливание|desalination`, `обратный осмос|reverse osmosis`, `ионный обмен|ion exchange`, `электродиализ|electrodialysis`, `нанофильтрация|nanofiltration`, `известкование|lime softening`.
- [x] Добавить синонимы для загрязнителей и компонентов: `сульфаты|sulfates|SO4`, `хлориды|chlorides|Cl`, `кальций|Ca`, `магний|Mg`, `натрий|Na`, `сухой остаток|TDS|total dissolved solids`.
- [x] Добавить синонимы для электроэкстракции никеля: `католит|catholyte`, `анолит|anolyte`, `диафрагменная ячейка|diaphragm cell`, `никелевый катод|nickel cathode`, `циркуляция электролита|electrolyte circulation`.
- [x] Добавить синонимы для пирометаллургии: `штейн|matte`, `шлак|slag`, `МПГ|PGM|platinum group metals`, `Au|золото`, `Ag|серебро`, `Cu matte|медный штейн`, `Ni matte|никелевый штейн`.
- [x] Добавить синонимы для экологии и газоочистки: `SO₂|сернистый газ|sulfur dioxide`, `flue gas|отходящий газ`, `scrubber|скруббер`, `FGD|flue gas desulfurization`, `известняковая очистка|limestone scrubbing`.
- [x] Добавить geo-словарь стран и регионов: Россия, Казахстан, Китай, Финляндия, Канада, Австралия, Чили, ЮАР, ЕС, США; поддержать группировку `domestic|foreign|cis|global`.
- [x] Добавить словарь климатов: `cold climate|холодный климат`, `arctic`, `subarctic`, `continental`, `permafrost`, связать с heap leaching и эксплуатационными ограничениями.
- [x] Включить отраслевой глоссарий из предоставляемых материалов как отдельный импортируемый source, с возможностью ручной правки экспертами.
- [x] Реализовать тесты синонимов: каждый RU-термин резолвится в canonical entity, каждый canonical entity имеет минимум один RU и один EN alias.
- [x] Добавить endpoint `GET /api/v1/domain/glossary?q=&lang=&type=` для UI и агента.

**Критерий приёмки:** поиск `ПВП`, `печь взвешенной плавки` и `fluidized bed furnace` возвращает одну canonical-сущность; запросы на русском и английском дают сопоставимые результаты; glossary endpoint возвращает canonical id, aliases, domain и source.

---

### 24.4 Числовые ограничения, единицы и отраслевые диапазоны

- [x] Расширить units-модуль поддержкой `мг/л`, `мг/дм³`, `г/л`, `мг/Нм³`, `м³/ч`, `м/с`, `см/с`, `л/мин`, `т/сут`, `кг/т`, `кВт·ч/т`, `%`, `ppm`, `ppb`, `мА/см²`, `А/м²`, `мВ`, `В`, `мПа`, `атм`, `бар`.
- [x] Задать canonical units: концентрации воды → `mg/L`, TDS → `mg/L`, расход → `m3/h`, скорость потока → `m/s`, производительность → `t/day`, SO₂ → `mg/Nm3` или `%vol`, current density → `A/m2`, CAPEX/OPEX → `currency/unit`.
- [x] Поддержать эквивалентность `мг/л` и `мг/дм³` для водных растворов.
- [x] Добавить парсинг числовых условий: `≤1000 мг/дм³`, `200–300 мг/л`, `<200 мг/л`, `от 100 т/сут`, `за последние 5 лет`, `скорость потока 0.1–0.3 м/с`.
- [x] Реализовать `RangeConstraint` DTO: `parameter_id`, `operator`, `value`, `min`, `max`, `unit`, `normalized_value`, `normalized_unit`, `source_span`.
- [x] Добавить отраслевые sanity ranges: pH 0–14, TDS >0, recovery 0–100%, removal efficiency 0–100%, current density >0, distribution coefficient >0, CAPEX/OPEX ≥0.
- [x] Добавить поддержку валют и годов для технико-экономических показателей: валюта, база года, пересчёт не выполнять автоматически без указанного индекса; помечать `currency_year_missing`.
- [x] Добавить обработку «сухой остаток» как `TotalDissolvedSolids` и связь с water-treatment suitability.
- [x] Добавить извлечение многоионного состава воды: `SO4`, `Cl`, `Ca`, `Mg`, `Na` с концентрациями, единицами и матрицей применимости методов.
- [x] Реализовать тестовый набор `tests/domain/numeric_constraints_water.jsonl` для запроса с сульфатами/хлоридами/Ca/Mg/Na 200–300 мг/л и TDS ≤1000 мг/дм³.
- [x] Реализовать тестовый набор `tests/domain/numeric_constraints_electrowinning.jsonl` для скорости циркуляции католита, плотности тока, температуры, pH и расхода.
- [x] В query planner добавить нормализацию числовых диапазонов до canonical units перед Cypher/Qdrant/OpenSearch фильтрами.

**Критерий приёмки:** запрос `сульфаты <200 мг/л` и `sulfates <200 mg/L` строит одинаковый numeric filter; пример с `≤1000 мг/дм³` корректно нормализуется в `mg/L`; значения без единицы или с неоднозначной валютой уходят в review/gap.

---

### 24.5 Импорт предоставляемых материалов и корпоративного корпуса

- [x] Создать ingestion-профиль `metallurgy_rnd_corpus`: внутренние отчёты, статьи, обзоры, патенты, диссертации, протоколы экспериментов, нормативные материалы, справочники материалов/оборудования/единиц.
- [x] Поддержать загрузку анонимизированного корпуса внутренних отчётов и статей с сохранением `source_type=internal_report|article|review|patent|thesis|standard|experiment_protocol`.
- [x] Поддержать импорт каталога экспериментов с метаданными: материал, режим, установка, параметры, результат, дата, лаборатория, ответственный эксперт, файл-протокол.
- [x] Поддержать импорт справочников: материалы, вещества, оборудование, свойства, единицы измерения, технологические теги.
- [x] Поддержать импорт перечня сотрудников и лабораторий: ФИО, роль, организация, лаборатория, области экспертизы, проекты, контакты, уровень доступа.
- [x] Поддержать импорт таксономии тематических тегов и привязку тегов к документам/экспериментам/экспертам.
- [x] Добавить `source_owner`, `lab`, `confidentiality_level`, `access_policy`, `retention_policy`, `document_version`, `updated_at` в source registry.
- [x] Реализовать дедупликацию корпоративных документов по `file_hash`, `title`, `authors`, `year`, `internal_doc_id`.
- [x] Реализовать batch-ingestion с отчётом: сколько документов распознано, сколько таблиц/экспериментов/фактов извлечено, сколько ушло в review.
- [x] Обеспечить импорт патентов с полями `publication_number`, `priority_date`, `assignee`, `country`, `claims`, `legal_status`.
- [x] Обеспечить импорт нормативных документов с полями `standard_id`, `jurisdiction`, `effective_date`, `status`.
- [x] Реализовать манифест загрузки `domain_ingest_manifest.json` для воспроизводимости демо-корпуса.

**Критерий приёмки:** предоставленный демо-набор импортируется одной командой; для каждого источника есть owner/lab/access policy; каталог экспериментов создаёт узлы Experiment/Sample/Measurement/Equipment/Expert; batch-report показывает извлечённые факты и review-задачи.

---

### 24.6 Доменное NLP-извлечение сущностей, связей и выводов

- [x] Расширить NER labels: `WaterComposition`, `Ion`, `Pollutant`, `Electrolyte`, `Catholyte`, `Anolyte`, `Matte`, `Slag`, `PGM`, `Furnace`, `GasCleaningUnit`, `InjectionHorizon`, `TechnologySolution`, `TechnoEconomicIndicator`.
- [x] Извлекать связи `method → applies_to → material/water_stream`, `method → removes → contaminant`, `experiment → showed → effect`, `author/expert → expert_in → domain`, `solution → implemented_in → geography`.
- [x] Извлекать условия применения: климат, температура, расход, концентрация, pH, Eh, pressure, current density, plant capacity, cold-climate constraints.
- [x] Извлекать технологические эффекты: removal efficiency, recovery, metal yield, partition coefficient, SO₂ reduction, TDS decrease, CAPEX/OPEX impact, energy consumption.
- [x] Извлекать выводы и рекомендации из текстов: `recommended`, `not recommended`, `applicable`, `limited_by`, `requires_pilot`, `contradicts_previous`.
- [x] Разделять факты эксперимента и обзорные claims: экспериментальные measurement-факты требуют protocol/evidence; обзорные рекомендации требуют citation и confidence.
- [x] Для таблиц извлекать заголовки, единицы, строки экспериментов, материалы, параметры и результаты; сохранять `table_id/row/col` для evidence.
- [x] Для патентов извлекать technology solution, independent/dependent claims, equipment конструкцию, claimed effect, географию патента.
- [x] Для нормативных документов извлекать требования, предельные концентрации, применимость по стране/юрисдикции и дату актуальности.
- [x] Добавить extractor для фраз сравнений: `A лучше B`, `A more effective than B`, `lower CAPEX`, `not suitable for cold climate`.
- [x] Добавить review-trigger для критичных чисел: концентрации, температуры, скорости потока, экономические показатели, recovery, SO₂ emission limits.
- [x] Сформировать golden набор RU/EN фрагментов для каждого доменного процесса: water desalination, catholyte circulation, Au/Ag/PGM partition, mine-water injection, SO₂ removal, heap leaching cold climate.

**Критерий приёмки:** на golden-фрагментах precision/recall доменных сущностей ≥ заданного порога; каждый извлечённый числовой факт имеет span и unit; каждый вывод/рекомендация связан с источником и `EvidenceStrength`.

---

### 24.7 Модель верификации знаний и уровни достоверности

- [x] Добавить `KnowledgeClaim`/`Recommendation` поля: `source_id`, `evidence_ids`, `evidence_strength`, `confidence`, `verified_by`, `review_status`, `updated_at`, `valid_until`, `geography_scope`, `applicability_scope`.
- [x] Определить правила confidence aggregation: peer-reviewed + experiment protocol выше, single internal note ниже, expert correction может повысить статус до `accepted`.
- [x] Добавить шкалу достоверности: `confirmed`, `likely`, `conflicting`, `weakly_supported`, `unverified`, `obsolete`.
- [x] Добавить поле `date_actualized`: дата последней проверки факта или рекомендации.
- [x] Реализовать правило устаревания: патенты/стандарты/экономические показатели требуют периодической актуализации; просроченные факты помечаются `needs_update`.
- [x] Реализовать evidence inspector для Recommendation: показать источники, страницы, таблицы, кто подтвердил, когда, какие есть ограничения.
- [x] Реализовать contradiction policy: конфликтующие выводы не затираются, а связываются через `CONTRADICTS`/`Disagreement` с причинами и evidence.
- [x] Добавить review queue типы: `critical_numeric_value`, `unverified_recommendation`, `obsolete_source`, `conflicting_practice`, `missing_geography`, `missing_applicability_condition`.
- [x] Добавить отчёт `knowledge_verification_report`: доля verified/reviewed/pending/obsolete по каждому домену.

**Критерий приёмки:** каждый ответ агента показывает уровень достоверности и источники; противоречивые выводы отображаются как disagreements, а не как один «средний» ответ; просроченные источники помечаются и попадают в review.

---

### 24.8 География, отечественная/зарубежная практика и временные диапазоны

- [x] Добавить `Geography`-узлы и поля: country, region, facility, mine/plant, jurisdiction, practice_type (`russia|cis|foreign|global|unknown`).
- [x] Автоматически классифицировать практику как отечественную или зарубежную по стране реализации, стране публикации, assignee патента или facility location.
- [x] Добавить фильтр `practice_type` во все search/graph/experiment endpoints.
- [x] Добавить фильтры `country`, `region`, `jurisdiction`, `climate_zone`, `facility_type`.
- [x] Поддержать временные фильтры: publication year, experiment date, patent priority date, standard effective date, source updated_at, `last_n_years`.
- [x] Реализовать query parser для фраз `за последние 5 лет`, `в России и за рубежом`, `мировая практика`, `отечественная практика`, `foreign practice`.
- [x] Добавить визуальное разделение отечественных и зарубежных решений в сравнительных таблицах и графе.
- [x] Для mine-water injection добавить отдельные поля: horizon depth, formation type, injection pressure, jurisdiction, environmental restrictions.
- [x] Для cold-climate heap leaching добавить climate-zone facets и условия: температура воздуха, промерзание, сезонность, heating/insulation solution.
- [x] Добавить тесты: запрос «применялись в России и за рубежом» возвращает две группы результатов с отдельными evidence и метриками.

**Критерий приёмки:** пользователь может отфильтровать результаты по `domestic` vs `foreign`; запрос `за последние 5 лет` ограничивает источники правильным временным окном; geography/practice_type присутствует в citations и export.

---

### 24.9 Шаблоны многопараметрических запросов и доменные query plans

- [x] Реализовать Cypher template `water_desalination_suitability(material_stream, ions, concentrations, target_tds, facility_type, geography)` для выбора методов обессоливания.
- [x] Реализовать template `nickel_catholyte_circulation_solutions(equipment, circulation_scheme, flow_velocity, current_density, geography)` для электроэкстракции никеля.
- [x] Реализовать template `precious_metals_partitioning(metals, matte_type, slag_type, years, process, temperature)` для распределения Au/Ag/МПГ между штейном и шлаком.
- [x] Реализовать template `mine_water_deep_injection(geography, horizon_depth, water_composition, capex_opex, regulation)` для российской/зарубежной практики закачки.
- [x] Реализовать template `so2_removal_methods(gas_stream, so2_concentration, removal_efficiency, byproduct, geography)` для газоочистки.
- [x] Реализовать template `cold_climate_heap_leaching(ore_type, climate_zone, regime, recovery, season)` для связи холодного климата, режима и выхода металла.
- [x] Добавить agent query plans для 4 примерных требований: entity resolution → numeric normalization → structured retrieval → hybrid fallback → evidence assembly → synthesis → graph/table payload.
- [x] Поддержать comparative query: `вариант A vs вариант B`, `отечественная практика vs мировая практика`, `RO vs ion exchange`.
- [x] Поддержать multi-hop запросы: `материал → процесс → оборудование → результат → эксперт/лаборатория`.
- [x] Поддержать отрицательные/gap-запросы: `нет экспериментов для холодный климат + кучное выщелачивание + никелевая руда`.
- [x] Добавить fallback: если structured query не нашёл фактов, запускать hybrid/GraphRAG и явно сообщать, что найден обзорный/неструктурированный evidence.
- [x] Покрыть шаблоны unit/integration tests на seed-графе.

**Критерий приёмки:** все 4 примерных запроса из постановки выполняются через agent/API и возвращают структурированный ответ с evidence, таблицей и/или графом; structured templates не используют свободный Cypher без guardrails.

---

### 24.10 Поиск, навигация и визуализация доменной карты знаний

- [x] Добавить типовые graph views: `материал → процесс → оборудование → результат`, `метод → загрязнитель → качество воды`, `эксперимент → режим → измерение → evidence`, `эксперт → лаборатория → область компетенции`.
- [x] Добавить визуальные кодировки: отечественная практика vs зарубежная; verified vs unverified; contradiction; missing numeric parameter; stale source.
- [x] Добавить фильтры графа: domain, process, material, equipment, geography, year, evidence_strength, confidence, review_status, numeric ranges.
- [x] Реализовать подсветку пробелов: нет экспериментов для комбинации material/process/condition; есть только зарубежные источники; нет технико-экономических показателей; нет пилотных данных.
- [x] Реализовать подсветку противоречий: разные рекомендации по скорости циркуляции католита, разные distribution coefficients, conflicting removal efficiency.
- [x] Добавить `Expert/Lab` panel: связанные эксперты, лаборатории, проекты, документы, количество подтверждённых фактов.
- [x] Добавить просмотр цепочки evidence: claim → evidence → document/table/page/span → reviewer decision.
- [x] Реализовать сохранённые представления: например `Nickel electrowinning catholyte circulation`, `Mine water desalination`, `SO2 removal`, `PGM partitioning`.
- [x] Добавить экспорт graph snapshot в PNG/SVG и JSON-LD.
- [x] Добавить graph performance guard: при >1000 узлов переключаться на community view/Sigma fallback.

**Критерий приёмки:** графический ответ на примерный запрос показывает цепочку material/process/equipment/result/evidence; gaps/contradictions выделяются визуально; пользователь может отфильтровать граф по географии, году, процессу и confidence.

---

### 24.11 Аналитика и синтез ответов «литературный обзор»

- [x] Реализовать answer synthesizer для формата «литературный обзор»: группировка источников по методу, году, географии, уровню детализации, evidence_strength.
- [x] Автоматически выделять consensus findings: выводы, подтверждённые несколькими независимыми источниками.
- [x] Автоматически выделять disagreements: разные значения, разные рекомендации, разные области применимости.
- [x] Для каждого метода показывать: principle, applicability, input conditions, performance metrics, limitations, capex/opex if available, source count, confidence.
- [x] Для water-treatment отвечать матрицей: метод × удаляемые компоненты × диапазон TDS/ионов × применимость к обогатительной фабрике × ограничения.
- [x] Для catholyte circulation отвечать матрицей: схема подачи/циркуляции × оборудование × flow velocity/current density × достоинства/риски × evidence.
- [x] Для partitioning отвечать таблицей: metal × matte type × slag composition × temperature/process × distribution coefficient/recovery × source.
- [x] Для mine-water injection отвечать таблицей: country/project × depth/horizon × water composition × capex/opex × regulatory notes × source.
- [x] Добавить блок `Что неизвестно/не найдено`: комбинации условий без экспериментов или с низким coverage.
- [x] Добавить блок `Что проверить пилотно`: условия с низкой достоверностью или сильной зависимостью от локальных параметров.
- [x] В ответе явно разделять `подтверждённые факты`, `обзорные выводы`, `рекомендации`, `гипотезы/похожие кейсы`.
- [x] Каждое утверждение в synthesis привязывать к citation/evidence или помечать как unsupported и не включать в финальный ответ.

**Критерий приёмки:** для запроса «литературный обзор по SO₂ removal» ответ содержит группы методов, consensus/disagreement, evidence counts и gaps; unsupported claims отсутствуют по verifier/eval.

---

### 24.12 Рекомендации, похожие кейсы и экспертная навигация

- [x] Реализовать рекомендации технологий из смежных областей: например методы обессоливания mine water ↔ process water reuse ↔ tailings water treatment.
- [x] В рекомендациях указывать reason: similarity of composition, process condition match, equipment availability, geography/climate analogy, prior lab experience.
- [x] Реализовать поиск похожих кейсов по vector + graph features: composition, process, equipment, numeric ranges, climate/geography, outcome.
- [x] Добавить `ExpertRecommendation`: эксперты/команды, которые работали с аналогичными задачами; считать по publications, reports, experiments, curation actions.
- [x] Реализовать `lab_capability_profile`: оборудование лаборатории, процессы, материалы, подтверждённые эксперименты, активность.
- [x] Добавить agent tool `recommend_experts(query_context)` и endpoint `GET /api/v1/domain/experts/recommend`.
- [x] В UI показывать «К кому обратиться»: эксперт, лаборатория, релевантные документы, чем подтверждена компетенция.
- [x] Добавить caution: экспертные рекомендации не раскрываются внешним партнёрам без соответствующего доступа.
- [x] Добавить feedback loop: пользователь может отметить рекомендацию полезной/неполезной; это влияет на ranking.

**Критерий приёмки:** для каждого примерного запроса система предлагает релевантные похожие кейсы и экспертов/лаборатории с evidence; внешний партнёр не видит restricted expert/contact details.

---

### 24.13 Сравнительный анализ технологий

- [x] Реализовать сущность `TechnologyComparison` с полями: alternatives, parameters, normalized_units, scores, evidence_ids, created_by, created_at.
- [x] Добавить сравнительные параметры: эффективность, recovery, removal efficiency, CAPEX, OPEX, energy consumption, cold-climate applicability, environmental constraints, maturity level, domestic availability.
- [x] Реализовать таблицы сравнения для методов обессоливания: RO, nanofiltration, ion exchange, electrodialysis, precipitation/lime softening, evaporation/crystallization, hybrid schemes.
- [x] Реализовать таблицы сравнения для catholyte circulation: feed distribution, circulation velocity, cell geometry, diaphragm design, pump/flow control, impact on cathode quality.
- [x] Реализовать таблицы сравнения для SO₂ removal: wet scrubber, dry/semi-dry sorbent injection, regenerative processes, sulfuric acid production, gypsum byproduct.
- [x] Реализовать таблицы сравнения для mine-water injection: deep well injection, treatment-before-injection, reinjection to mine workings, monitoring requirements.
- [x] Поддержать пользовательский выбор критериев и весов с сохранением view.
- [x] Обязательно показывать source count и confidence по каждой ячейке; если evidence нет — показывать gap, а не пустое значение.
- [x] Поддержать экспорт сравнительной таблицы в Markdown, PDF, Excel/CSV и JSON-LD.
- [x] Добавить тест `technology_comparison_acceptance`: каждая ячейка либо имеет evidence_ids, либо помечена gap.

**Критерий приёмки:** пользователь строит таблицу сравнения технологий по эффективности/CAPEX/климату/экологии; все числовые значения нормализованы; каждая ячейка прослеживается до evidence или gap.

---

### 24.14 Управление доступом, чувствительные данные и внешний партнёр

- [x] Расширить RBAC ролями из постановки: `researcher`, `analyst`, `project_manager`, `admin`, `external_partner`, `curator`.
- [x] Для source/document/evidence/claim добавить `confidentiality_level`: `public`, `internal`, `restricted`, `commercial_secret`, `partner_visible`.
- [x] Реализовать row-level filtering: пользователь видит только документы/факты/evidence, разрешённые его ролью и access_policy.
- [x] В агенте запрещать включать restricted evidence в ответ пользователю без доступа; вместо этого показывать «есть внутренние источники, доступ ограничен».
- [x] Реализовать redaction snippets для внешних партнёров: скрывать ФИО, контакты, коммерческие показатели, внутренние IDs.
- [x] Логировать запросы, просмотры evidence, экспорт, скачивание документов, изменение графа.
- [x] Добавить audit events для сравнительных таблиц и экспорта результатов.
- [x] Реализовать approval flow для публикации внутреннего вывода во внешний отчёт.
- [x] Поддержать политики ИБ: запрет на выгрузку restricted данных в публичные LLM; allowlist open-source/approved models.
- [x] Добавить security tests: внешний партнёр не получает internal snippets, даже если вопрос переформулирован adversarially.

**Критерий приёмки:** один и тот же запрос для researcher и external_partner возвращает разный, корректно отфильтрованный набор evidence; audit log фиксирует просмотр и экспорт; restricted snippets не утекли в agent answer.

---

### 24.15 Дашборды руководителя и метрики покрытия знаний

- [x] Реализовать dashboard `Knowledge Coverage`: по направлениям hydrometallurgy, pyrometallurgy, ecology, waste processing, mineral processing.
- [x] Показать coverage metrics: число источников, экспериментов, verified facts, gaps, contradictions, stale facts, review backlog.
- [x] Реализовать матрицу `material × process × condition × property`: количество evidence, latest update, confidence, coverage status.
- [x] Реализовать dashboard по активностям команд: публикации/отчёты/эксперименты/curation actions по лабораториям и экспертам.
- [x] Реализовать «зоны риска»: темы с малым количеством источников, противоречивыми выводами, отсутствующими технико-экономическими показателями, устаревшими источниками.
- [x] Добавить фильтры dashboard: период, домен, лаборатория, география, тип источника, уровень достоверности.
- [x] Реализовать drill-down из dashboard в graph/explorer/evidence.
- [x] Добавить scheduled report: еженедельная сводка руководителю по новым источникам, новым contradictions, закрытым gaps.
- [x] Добавить export dashboard snapshot в PDF/PNG.
- [x] Включить dashboard в Definition of Done доменной готовности.

**Критерий приёмки:** руководитель видит покрытие знаний по каждому направлению, активность команд и зоны риска; клик по метрике открывает конкретные документы/эксперименты/evidence.

---

### 24.16 Экспорт, отчёты, JSON-LD и уведомления

- [x] Реализовать экспорт ответа агента в Markdown с citations, evidence snippets, tables, gaps, confidence.
- [x] Реализовать экспорт отчёта в PDF с титульным листом, методикой поиска, таблицами, графом, источниками и disclaimer по достоверности.
- [x] Реализовать экспорт фактов/подграфа в JSON-LD с контекстом доменной онтологии.
- [x] Реализовать экспорт сравнительных таблиц в CSV/XLSX/Markdown/PDF.
- [x] Добавить `report_template` для технического задания: problem, input conditions, compared technologies, recommendation, risks, evidence.
- [x] Реализовать notification subscriptions: пользователь подписывается на тему/material/process/geo; система уведомляет о новых публикациях, экспериментах, contradictions, stale facts.
- [x] Добавить notification channels: email, in-app, webhook; хранить delivery log.
- [x] Реализовать digest: daily/weekly summary по интересующим темам.
- [x] Уведомлять эксперта при появлении review task в его области компетенции.
- [x] Уведомлять руководителя о new high-risk contradiction и critical gap.
- [x] В уведомлениях учитывать access_policy: не отправлять restricted snippets тем, у кого нет доступа.

**Критерий приёмки:** пользователь экспортирует обзор в PDF/Markdown/JSON-LD; подписка на тему `nickel electrowinning catholyte` создаёт уведомление при новом источнике или review task; уведомления соблюдают права доступа.

---

### 24.17 Нефункциональные требования: производительность, точность, надёжность, расширяемость

- [x] Провести нагрузочный тест: до 1 млн сущностей в графе, сложный запрос с обходом 3–4 уровней и числовыми фильтрами отвечает за 3–5 секунд для p95 при прогретых индексах.
- [x] Добавить performance budget по типам запросов: structured graph, hybrid search, comparison table, graph expand, dashboard load.
- [x] Создать synthetic large graph generator для домена: water, electrolysis, leaching, smelting, gas cleaning, waste processing.
- [x] Проверить индексы Neo4j/Qdrant/OpenSearch для `domain`, `material`, `process`, `geography`, `year`, `numeric ranges`, `evidence_strength`.
- [x] Ввести accuracy gates для критичных чисел: концентрации, температуры, скорости, экономические показатели; ошибка unit/value extraction считается blocker.
- [x] Добавить robust import tests: битые PDF, сканы, таблицы с объединёнными ячейками, RU/EN смешанный текст, патентные формулы, старые отчёты.
- [x] Добавить graceful failure: если extraction не уверен, факт не попадает в verified-answer без review.
- [x] Обеспечить модульность новых доменов: добавление редкоземельных элементов, sensor data, новых entity types через schema extension без переписывания core.
- [x] Добавить compatibility tests после расширения онтологии: старые queries и demos из §22 продолжают проходить.
- [x] Добавить мониторинг качества extraction по доменам и языкам: RU vs EN, reports vs papers vs patents.

**Критерий приёмки:** p95 сложного domain query ≤5 секунд на тестовом объёме; критичные numeric extraction тесты проходят без ошибок; добавление нового domain vocabulary не ломает существующие pipelines.

---

### 24.18 Доменный golden dataset и приёмочные сценарии

- [x] Создать `packages/kg_eval/data/domain_science_ball/` с 4 основными acceptance-вопросами из постановки и эталонными ответами.
- [x] Добавить water desalination golden case: состав воды SO4/Cl/Ca/Mg/Na 200–300 мг/л, target TDS ≤1000 мг/дм³, facility=concentrator.
- [x] Добавить nickel electrowinning golden case: circulation of catholyte, flow velocity, cell/electrolyte feeding solutions, optimal speed evidence.
- [x] Добавить precious metals partitioning golden case: Au/Ag/PGM between Cu/Ni matte and slag, last 5 years, experiments and publications.
- [x] Добавить mine-water injection golden case: Russia vs foreign practices, technical/economic indicators, regulatory notes.
- [x] Добавить extra cases: SO₂ removal methods, cold-climate heap leaching, gypsum/waste processing, coal waste valorization.
- [x] Для каждого case хранить expected entities, numeric constraints, expected filters, minimum evidence count, expected table columns, expected gaps.
- [x] Добавить adversarial cases: неоднозначная единица, отсутствующая география, конфликтующие значения, restricted source, outdated standard.
- [x] Добавить benchmark metrics: answer faithfulness, citation precision, numeric accuracy, geo-filter accuracy, gap recall, contradiction recall.
- [x] Интегрировать domain golden eval в release gate §22.
- [x] Сохранять eval report в MLflow и `docs/eval/domain_science_ball_report.md`.

**Критерий приёмки:** все 4 обязательных запроса проходят e2e через API/agent/UI; ответы содержат evidence, numeric filters, geography/time filters и confidence; domain eval входит в CI/release gate.

---

### 24.19 FAIR, стандарты, нормативы и JSON-LD/RDF-совместимость

- [x] Задокументировать FAIR-политику для научных данных: findable, accessible, interoperable, reusable применительно к документам, экспериментам, фактам, evidence.
- [x] Каждому документу, эксперименту, факту, evidence и recommendation присваивать стабильный ID и machine-readable metadata.
- [x] Реализовать JSON-LD context для доменной онтологии: Material, Process, Equipment, Measurement, Evidence, Geography, Recommendation.
- [x] Поддержать экспорт подграфа в JSON-LD без включения restricted evidence для пользователей без доступа.
- [x] Добавить `source_license`/`usage_rights`/`access_policy` в metadata.
- [x] Добавить поддержку нормативных материалов как отдельного `Standard`/`Regulation` source type с jurisdiction/effective_date/status.
- [x] Добавить правила актуализации нормативов: устаревшие стандарты не используются в рекомендациях без warning.
- [x] Поддержать SHACL-валидацию ключевых constraints для обмена данными: required evidence, unit, geography for practice claims, confidence.
- [x] Создать `docs/domain/fair_and_standards.md` с правилами использования и обмена данными.

**Критерий приёмки:** любой экспортированный подграф имеет JSON-LD context и stable IDs; FAIR metadata заполнены для seed-корпуса; нормативный источник с устаревшей датой помечается warning.

---

### 24.20 Ручная корректировка графа экспертами

- [x] В UI добавить режим expert edit: исправить сущность, связь, параметр, единицу, географию, confidence, recommendation.
- [x] Каждая правка создаёт `CurationEvent` с actor, reason, before/after, timestamp.
- [x] Защитить expert-corrected fields от автоматической перезаписи при re-ingestion.
- [x] Поддержать expert comments на facts/recommendations/technology comparisons.
- [x] Поддержать workflow `propose → review → accept/reject` для внешних партнёров или младших аналитиков.
- [x] Добавить action `mark_as_domestic_practice`, `mark_as_foreign_practice`, `set_applicability_condition`, `add_limitation`, `resolve_contradiction`, `annotate_gap`.
- [x] Добавить expert correction impact: после правки обновлять Qdrant/OpenSearch payload, graph views, dashboards, notifications.
- [x] Показывать историю изменений на карточке entity/fact/recommendation.
- [x] Добавить bulk-edit для однотипных aliases/географии/тегов.

**Критерий приёмки:** эксперт исправляет скорость циркуляции католита или применимость метода; правка видна в ответах, не перезаписывается автоматикой, отражается в audit и history.

---

### 24.21 Технологические рекомендации из требований и совместимость альтернатив

- [ ] Зафиксировать в `docs/adr/0024-domain-technology-stack.md`, что primary graph store остаётся Neo4j, но доменные требования допускают future portability к Amazon Neptune и JanusGraph; описать, какие Cypher/GDS/APOC-зависимости мешают прямой миграции.
- [ ] Добавить в §21 каталог reference-репозиториев/ссылок для `Amazon Neptune` и `JanusGraph`; для Neptune зафиксировать managed-service integration как reference, а не vendored source.
- [ ] Для JanusGraph описать mapping property graph labels/edges/indexes и ограничения по Gremlin-запросам для доменных templates.
- [ ] Добавить task на проверку `Cypher ↔ Gremlin` portability для 5 доменных запросов: water desalination, catholyte circulation, partitioning, mine-water injection, SO₂ removal.
- [ ] Зафиксировать primary NLP stack для RU/EN: GLiNER/MatSciBERT/LLM extractors из основного плана + optional domain adapters `DeepPavlov`, `spaCy`, `ruBERT` для русскоязычных документов.
- [ ] Добавить evaluation spike `ru_nlp_stack_benchmark`: сравнить DeepPavlov, spaCy ru pipeline, ruBERT/SlavicBERT и текущий GLiNER/LLM на 200 размеченных RU-фрагментах из горно-металлургического корпуса.
- [ ] Добавить задачи интеграции `DeepPavlov` как optional extractor backend с тем же `Extractor` protocol, disabled by default.
- [ ] Добавить задачи интеграции `spaCy`/`spacy-ru` для sentence segmentation, abbreviation expansion и rule-based matching русских техтерминов.
- [ ] Добавить задачи интеграции `ruBERT`/SentenceTransformer ru models для semantic retrieval и entity-resolution aliases на русском языке.
- [ ] Зафиксировать primary search stack: Qdrant + OpenSearch; добавить compatibility note, что требования допускают Elasticsearch и Vespa как альтернативы.
- [ ] Добавить benchmark task `search_backend_comparison`: OpenSearch vs Elasticsearch vs Vespa на доменном наборе запросов с numeric/facet filters.
- [ ] Для Vespa описать схему документов: text, embeddings, numeric fields, geo/practice facets, evidence fields, и сравнить возможность hybrid ranking/fusion.
- [ ] Для Elasticsearch описать mapping parity с OpenSearch и миграционные риски лицензирования/версий.
- [ ] Расширить ontology governance: OWL/RDF/SHACL остаются interoperability/export layer, а operational graph — property graph; описать границу, чтобы не строить полный SPARQL-first стек без необходимости.
- [ ] Реализовать SHACL-shapes для доменных critical constraints: Recommendation must have evidence; TechnologySolution must have applicability condition; Practice claim must have geography; Measurement must have unit or missing_unit gap.
- [ ] Реализовать RDF/JSON-LD export smoke-test для подграфов domain examples; проверить, что экспорт не включает restricted evidence без доступа.
- [ ] Добавить `Vespa/Elasticsearch/Neptune/JanusGraph/DeepPavlov/spaCy/ruBERT` в `third_party/CATALOG.md` со статусом `reference|benchmark|optional` и причиной выбора.
- [ ] Добавить к domain DoD требование: выбранный primary stack закрывает все функциональные требования, а альтернативы оценены и задокументированы, даже если не внедрены.

**Критерий приёмки:** ADR по технологическому стеку показывает, какие рекомендованные технологии внедряются, какие остаются optional/reference/benchmark; RU NLP benchmark выполнен на доменном golden-наборе; SHACL/JSON-LD interoperability тесты проходят; альтернативы поиска и графовых БД не блокируют primary delivery.

---

### 24.22 Доменный Definition of Done

- [x] Создать `docs/DEFINITION_OF_DONE_DOMAIN_SCIENCE_BALL.md` с чек-листом доменной готовности.
- [x] Закрыть acceptance 4 обязательных запросов: water desalination, catholyte circulation, Au/Ag/PGM partitioning, mine-water injection.
- [x] Для каждого обязательного запроса продемонстрировать: natural-language query, parsed entities/constraints, retrieved facts, answer, table, graph, evidence inspector, export.
- [x] Проверить RU/EN parity: русская и английская формулировки возвращают сопоставимые результаты.
- [x] Проверить domestic/foreign filtering для минимум 2 сценариев.
- [x] Проверить numeric range filtering для минимум 4 параметров: concentration, temperature, flow velocity, CAPEX/OPEX или recovery.
- [x] Проверить contradiction/gap display для минимум 3 доменных gaps/contradictions.
- [x] Проверить RBAC external_partner vs researcher на restricted internal reports.
- [x] Проверить dashboard руководителя и scheduled notifications.
- [x] Приложить запись полного доменного демо и eval report к release artifact.

**Критерий приёмки:** доменный release разрешён только при закрытых задачах 24.1–24.22, зелёном domain eval и рабочем демо по всем обязательным запросам.
---


## 25. Confidence-of-absence: extractor-recall-aware анализ пробелов

Раздел добавляет слой **confidence-of-absence** для gap analysis: система больше не трактует отсутствие связи в графе как автоматический факт «эксперимент не проводился». Отсутствие наблюдения должно быть разделено на настоящий R&D-пробел, вероятный пропуск извлечения, ретрагированные данные или неопределённый случай. Слой моделирует recall собственного extractor-а по контекстам, использует coverage-телеметрию, MENTIONS-lineage и калиброванные/эвристические приоры, а затем аннотирует пробелы вероятностями `p_truly_absent` и `p_extractor_missed`.

Подсистема должна быть полностью аддитивной: существующий `detect_gaps` не переписывается, LLM-only-proposes governance не меняется, ingestion остаётся идемпотентным, все новые факты имеют content-stable IDs, система работает офлайн, а graph-query шаблоны имеют одинаковую семантику на embedded и server backend.

Затрагиваемые области: `domain/schemas.py`, `storage/base.py`, `storage/sqlite_meta.py`, `storage/postgres_meta.py`, `storage/graph_queries.py`, `domain/ontology.py`, `agents/extraction.py`, `agents/ingestion_graph.py`, `ingestion/catalog.py`, `ingestion/coverage_log.py`, `analytics/extractor_recall.py`, `analytics/absence_confidence.py`, `agents/query_graph.py`, `api/main.py`, `service.py`, `evals/metrics.py`, `evals/run_extraction_eval.py`, `frontend/src/components/ConflictsGaps.tsx`, `frontend/src/api/types.ts`, `frontend/src/lib/glossary.ts`, `tests/test_absence_foundation.py`.

---

### 25.1 Архитектурные инварианты и scope подсистемы

- [x] Зафиксировать в `docs/adr/0025-confidence-of-absence.md`, что отсутствие связи в графе не равно доказанному отсутствию эксперимента.
- [x] Описать problem statement: обычный graph gap может быть настоящим пробелом, ошибкой извлечения, эффектом ретракции или недостатком покрытия корпуса.
- [x] Зафиксировать принцип sibling-слоя: `analytics/absence_confidence.py` обогащает результаты gap analysis, но не переписывает `detect_gaps`.
- [x] Зафиксировать governance-инвариант: LLM может только предлагать факты/claim-кандидаты, а принятие идёт через `proposal → validate → review`.
- [x] Зафиксировать ingestion-инвариант: все новые телеметрические и графовые записи идемпотентны, content-stable и безопасны при повторном прогоне.
- [x] Зафиксировать offline-инвариант: без LLM и внешних сервисов слой работает, честно фиксируя prose-miss контексты как низкий recall.
- [x] Зафиксировать server-parity: SQLite/embedded и PostgreSQL/server реализации MetaStore должны иметь одинаковые таблицы, методы и semantics.
- [x] Зафиксировать graph-query parity: новые именованные шаблоны реализуются один раз в `GraphQueryMixin`, а backend-specific слои только исполняют примитивы.
- [x] Зафиксировать, что все эвристические priors имеют `calibrated=false` до запуска gold-калибровки.
- [x] Добавить risk note: слой снижает ложные R&D-гипотезы, но не доказывает абсолютное отсутствие эксперимента без достаточного покрытия и калибровки.

**Критерий приёмки:** ADR принят; подсистема описана как аддитивный confidence-layer; unit/integration-тесты подтверждают, что старый `detect_gaps` и существующие query templates работают без изменений.

---

### 25.2 Расширение модели `Gap` и absence-verdict schema

- [ ] В `domain/schemas.py::Gap` добавить опциональное поле `p_truly_absent: float | None`.
- [ ] В `domain/schemas.py::Gap` добавить опциональное поле `p_extractor_missed: float | None`.
- [ ] В `domain/schemas.py::Gap` добавить поле `absence_verdict` с enum `{genuine_gap, possible_miss, retracted, abstain}`.
- [ ] В `domain/schemas.py::Gap` добавить поле `absence_meta: dict` для объяснения сигналов, thresholds, recall context и calibration state.
- [ ] Все новые поля сделать `None`/пустыми по умолчанию, чтобы существующие producers/consumers gap-объектов не ломались.
- [ ] Добавить Pydantic/typing validation: вероятности должны быть в диапазоне `[0, 1]`, если заполнены.
- [ ] Добавить helper `is_absence_annotated(gap)` для UI/API, чтобы отличать старые gap-записи от обогащённых.
- [ ] Добавить serialisation compatibility tests для старых gap payload без absence-полей.
- [ ] Добавить миграцию OpenAPI/TS types для новых полей `Gap`.
- [ ] Добавить backward-compatible JSON snapshot тесты на старые ответы `/gaps`.

**Критерий приёмки:** старые gap payload валидируются без новых полей; новые поля корректно сериализуются в API и frontend types; вероятность вне `[0,1]` отклоняется тестом.

---

### 25.3 Provenance-lineage наблюдений и extraction-run join keys

- [ ] Расширить `assemble_observation_proposal` необязательными аргументами `extraction_run_id` и `extractor`.
- [ ] Штамповать `extraction_run_id` в props узла `Observation`.
- [ ] Штамповать `extractor` в props узла `Observation`.
- [ ] Штамповать `extractor_version` в props узла `Observation`.
- [ ] Обеспечить join-ключ от принятого факта к конкретному прогону extraction и recall-контексту.
- [ ] Для структурного каталога добавлять `extraction_run_id` при создании наблюдений из catalog rows.
- [ ] Для документного LangGraph-пути добавлять `extraction_run_id` при создании observation proposals.
- [ ] Убедиться, что soft-retracted observations сохраняют provenance и доступны только absence-слою при `include_retracted=true`.
- [ ] Добавить тест, что обычная аналитика по-прежнему скрывает retracted observations.
- [ ] Добавить тест, что absence-слой видит retracted observations и классифицирует их отдельно.

**Критерий приёмки:** каждое Observation, созданное новым pipeline, имеет `extraction_run_id`, `extractor`, `extractor_version`; retracted observations не попадают в обычные результаты, но доступны absence-layer.

---

### 25.4 MetaStore: coverage telemetry и extractor recall registry

- [ ] В `storage/base.py` расширить протокол MetaStore методом `log_coverage`.
- [ ] В `storage/base.py` расширить протокол MetaStore методом `coverage_stats`.
- [ ] В `storage/base.py` расширить протокол MetaStore методом `save_recall_prior`.
- [ ] В `storage/base.py` расширить протокол MetaStore методом `get_recall_priors`.
- [ ] В SQLite MetaStore добавить idempotent-таблицу `extraction_coverage`.
- [ ] В PostgreSQL MetaStore добавить idempotent-таблицу `extraction_coverage` с той же схемой.
- [ ] В SQLite MetaStore добавить idempotent-таблицу `extractor_recall`.
- [ ] В PostgreSQL MetaStore добавить idempotent-таблицу `extractor_recall` с той же схемой.
- [ ] Добавить уникальные ключи/UPSERT semantics для повторных прогонов extraction coverage.
- [ ] Добавить миграции для обеих БД и rollback-safe создание таблиц.
- [ ] Добавить тест parity: SQLite и PostgreSQL возвращают одинаковые `coverage_stats` на одном seed-наборе.
- [ ] Добавить тест parity: SQLite и PostgreSQL возвращают одинаковые recall priors после `save_recall_prior`.

**Критерий приёмки:** обе реализации MetaStore поддерживают новые методы; повторное логирование одного coverage event не создаёт дублей; server-parity тесты зелёные.

---

### 25.5 Coverage logging в ingestion pipeline

- [ ] Создать `ingestion/coverage_log.py` как side-channel логгер покрытия extraction.
- [ ] Логировать для каждого extraction run ключ контекста: `source_type`, `kind`, `parser_version`, `extractor_version`.
- [ ] Логировать denominator `seen_segments`: сколько сегментов данного контекста extractor увидел.
- [ ] Логировать numerator `emitted_facts`: сколько сегментов дали observation/fact.
- [ ] Сделать coverage logging best-effort: ошибка логирования не должна ломать ingestion.
- [ ] Инструментировать LangGraph-узел `extract_candidates` для document_text/chunk контекстов.
- [ ] Инструментировать `ingestion/catalog.py` для `catalog_row` и `document_table_row` контекстов.
- [ ] Логировать `seen=emitted` для структурного каталога, если каждая строка ожидаемо даёт факт.
- [ ] Логировать `seen>0, emitted=0` для прозы без LLM extraction как честный blind spot.
- [ ] Добавить aggregate report по seed-корпусу: `document_text/chunk`, `document_table_row`, `catalog_row`.
- [ ] Добавить тест, что отключённый coverage logger не меняет результат ingestion.
- [ ] Добавить тест, что coverage stats собираются даже при отсутствии фактов из прозы.

**Критерий приёмки:** на seed-корпусе видны denominator/numerator по модальностям; coverage logging не влияет на ingestion outcome; failures coverage side-channel логируются, но не останавливают pipeline.

---

### 25.6 Извлечение из прозы и offline-safe prose claims

- [ ] Включить ранее неактивный `llm_claims_from_text` в `extract_candidates` для prose chunks.
- [ ] Пропускать prose claim-кандидаты через тот же governance-путь `proposal → validate → review`.
- [ ] Не создавать новые EvidenceSpan для prose claim, если можно переиспользовать EvidenceSpan исходного чанка.
- [ ] При отсутствии LLM не извлекать prose facts, но логировать coverage как `seen > 0, emitted = 0`.
- [ ] Помечать offline-prose контекст как высокий `p_missed` через recall prior fallback.
- [ ] Добавить флаг `llm_prose_claims_enabled` в config.
- [ ] Добавить feature-flag test: при `false` prose chunks не дают facts, но дают coverage telemetry.
- [ ] Добавить feature-flag test: при `true` prose chunks создают claim proposals с EvidenceSpan.
- [ ] Добавить regression test, что prose extraction не обходит validation/review.
- [ ] Добавить synthetic case: факт есть только в prose, structured extraction его пропускает, absence-layer классифицирует `possible_miss`.

**Критерий приёмки:** prose extraction безопасно отключается; при включении генерирует только governed proposals; отсутствие LLM честно отражается в coverage и повышает miss-risk.

---

### 25.7 MENTIONS-lineage для документов, материалов и свойств

- [ ] Добавить/активировать graph node/step `link_mentions` в ingestion graph.
- [ ] Создавать ребро `Document — MENTIONS → Material` по всем сегментам документа, включая прозу.
- [ ] Создавать ребро `Document — MENTIONS → Property` по всем сегментам документа, включая прозу.
- [ ] В `ingestion/catalog.py` штамповать MENTIONS для материалов из catalog rows.
- [ ] В `ingestion/catalog.py` штамповать MENTIONS для свойств из catalog rows.
- [ ] Не использовать MENTIONS как доказательство измерения; это только сигнал обсуждения темы.
- [ ] Обеспечить additive semantics: старые query templates игнорируют MENTIONS, если не запрошено явно.
- [ ] Добавить MENTIONS в ontology/relationship registry, если там была только константа без runtime наполнения.
- [ ] Добавить тест: документ, где есть материал и свойство, но нет Observation, получает MENTIONS без Observation.
- [ ] Добавить тест: absence-layer интерпретирует MENTIONS без Observation как candidate `possible_miss`, а не как `genuine_gap`.

**Критерий приёмки:** MENTIONS-рёбра создаются для prose/table/catalog сегментов; они не ломают существующие templates; absence-layer использует их как сигнал вероятного пропуска извлечения.

---

### 25.8 Новые graph-query templates для coverage и near-miss анализа

- [ ] В `storage/graph_queries.py` реализовать `_tpl_documents_mentioning_material_without_property` в `GraphQueryMixin`.
- [ ] Шаблон должен принимать material и опциональное property constraint.
- [ ] Шаблон должен возвращать документы, где есть MENTIONS, и флаг `has_observation`.
- [ ] Интерпретировать `MENTIONS && !has_observation` как likely extractor blind spot candidate.
- [ ] В `storage/graph_queries.py` реализовать `_tpl_regime_coverage_for_material` в `GraphQueryMixin`.
- [ ] Шаблон должен возвращать по каждому run/material regime список измеренных свойств.
- [ ] Использовать `regime_coverage_for_material` как denominator для near-miss gaps.
- [ ] Зарегистрировать оба шаблона в `domain/ontology.py::GRAPH_TEMPLATES`.
- [ ] Сохранить Cypher в registry как документацию намерения, даже если runtime выполняет backend-neutral primitives.
- [ ] Добавить NetworkX/embedded тесты обоих шаблонов.
- [ ] Добавить Neo4j/server тесты обоих шаблонов.
- [ ] Добавить parity тест: embedded и server backend возвращают одинаковые результаты на seed-графе.

**Критерий приёмки:** оба шаблона доступны из template registry, работают на NetworkX и Neo4j и дают одинаковую семантику; MENTIONS-without-observation case обнаруживается.

---

### 25.9 Fix parity для временных фильтров и coverage queries

- [ ] Исправить `PostgresMetaStore.search_experiments`, чтобы он уважал `time_min_lo`.
- [ ] Исправить `PostgresMetaStore.search_experiments`, чтобы он уважал `time_min_hi`.
- [ ] Сверить поведение временных фильтров с SQLite/embedded реализацией.
- [ ] Добавить regression test: catalog/coverage запрос с time range возвращает одинаковые experiment IDs в SQLite и PostgreSQL.
- [ ] Добавить regression test на пустой time range.
- [ ] Добавить regression test на open-ended time range: только lower bound.
- [ ] Добавить regression test на open-ended time range: только upper bound.
- [ ] Проверить, что absence-map не смешивает режимы за пределами заданного temporal scope.

**Критерий приёмки:** SQLite и PostgreSQL имеют одинаковую semantics временных фильтров; старое расхождение coverage/catalog запросов устранено.

---

### 25.10 Extractor recall priors из coverage telemetry

- [ ] Создать `analytics/extractor_recall.py`.
- [ ] Реализовать построение recall prior по контексту `(source_type, kind, parser_version, extractor_version)`.
- [ ] Сохранять modality priors: `catalog_row ≈ 0.98`, `table_row ≈ 0.90`.
- [ ] Сохранять prose chunk prior `≈0.55` при включённом LLM extraction.
- [ ] Сохранять prose chunk prior `≈0.15` в offline/no-LLM режиме.
- [ ] Считать observed yield `emitted/seen` и показывать его рядом с recall prior.
- [ ] Не смешивать observed yield с recall prior напрямую: отсутствие measurable fact в prose не равно false negative.
- [ ] Добавлять metadata `calibrated=false`, `method="heuristic_modality_prior"` для эвристических priors.
- [ ] Реализовать `recall_for_context()` с fallback: exact key → modality average → default prior.
- [ ] Реализовать persistence в таблицу `extractor_recall` для SQLite/PostgreSQL.
- [ ] Реализовать persistence в `data/store/extractor_recall.json` для быстрого чтения.
- [ ] Реализовать service method `extractor_recall_report(rebuild=True)`.
- [ ] Добавить tests для exact lookup, modality fallback и default fallback.
- [ ] Добавить tests, что calibrated priors позже имеют приоритет над heuristic priors.

**Критерий приёмки:** recall report строится из coverage telemetry; priors сохраняются в MetaStore и JSON; все heuristic priors явно помечены `calibrated=false`.

---

### 25.11 Absence-confidence layer и карта неизвестного

- [ ] Создать `analytics/absence_confidence.py` как sibling-модуль к `gaps.py`.
- [ ] Не изменять основную функцию `detect_gaps`; absence-layer должен только аннотировать gaps.
- [ ] Реализовать `annotate_gaps(gaps, context)` для enrichment `missing_property_measurement` gaps.
- [ ] Реализовать `absence_confidence(material, property)` для одной ячейки `(material, property)`.
- [ ] Реализовать `absence_map(materials, properties)` для матрицы материалов × свойств.
- [ ] Объединить три сигнала: existing observations, retracted observations, MENTIONS-without-observation.
- [ ] Классифицировать `present`, если есть неретрагированное observation.
- [ ] Классифицировать `retracted`, если observation были, но soft-retracted.
- [ ] Классифицировать `genuine_gap`, если observation нет и комбинация не упоминается ни в одном документе.
- [ ] Классифицировать `possible_miss`, если observation нет, но документ MENTIONS комбинацию.
- [ ] Классифицировать `abstain`, если miss probability в средней зоне и уверенности недостаточно.
- [ ] Реализовать thresholds `POSSIBLE_MISS_AT=0.60` и `GENUINE_GAP_AT=0.25` как config values.
- [ ] Использовать recall priors из `analytics/extractor_recall.py`, fallback должен работать без предварительного rebuild.
- [ ] Всегда возвращать `calibrated` status в `absence_meta`.
- [ ] Считать `p_truly_absent` и `p_extractor_missed` для gap-аннотации.
- [ ] Добавить histogram verdicts в `absence_map`.
- [ ] Реализовать v1 granularity на уровне `(material, property)`.
- [ ] Добавить explicit TODO для per-run mention/extraction granularity в фазе 6+.

**Критерий приёмки:** absence-layer отличает настоящий gap от likely extractor miss; missing-property gaps обогащаются вероятностями, verdict и meta; слой работает без rebuild priors через fallback.

---

### 25.12 Работа с ретракциями и include_retracted semantics

- [ ] Расширить `_run_observations` параметром `include_retracted: bool = False`.
- [ ] По умолчанию оставить старую semantics: retracted observations скрыты для обычной аналитики.
- [ ] При `include_retracted=true` возвращать soft-retracted observations только для absence-layer.
- [ ] В absence-layer отдельным verdict считать `retracted`, а не `genuine_gap` и не `possible_miss`.
- [ ] Сохранять metadata ретракции: кто/когда/почему отозвал observation.
- [ ] Не учитывать retracted observations в ranking/recommendation как active facts.
- [ ] Добавить test: retracted-only ячейка получает verdict `retracted`.
- [ ] Добавить test: обычный search не возвращает retracted observation как present.

**Критерий приёмки:** ретрагированные данные классифицируются отдельно и не смешиваются с настоящими gaps или missed extraction; старые query paths не меняют поведение.

---

### 25.13 Service/API интеграция и query graph self-check

- [ ] В `service.py` добавить метод `extractor_recall_report(rebuild=True)`.
- [ ] В `service.py` добавить метод `absence_map(...)`.
- [ ] В `service.py` добавить метод `absence_confidence(...)`.
- [ ] Обновить `gaps_search()` так, чтобы он опционально аннотировал gaps absence-verdict fields.
- [ ] В `api/main.py` добавить read-only endpoint `POST /gaps/absence`.
- [ ] Endpoint `/gaps/absence` должен возвращать `absence_map` и/или annotated gaps без mutation side effects.
- [ ] В `agents/query_graph.py` обновить узел `analyze_conflicts_and_gaps`, чтобы он вызывал `annotate_gaps`.
- [ ] Добавить в `self_check` summary по absence: сколько likely genuine gaps, possible misses, retracted, abstain.
- [ ] В agent answer synthesis добавить warning, если gap имеет high `p_extractor_missed`.
- [ ] Не рекомендовать R&D-гипотезу как «неизученную», если verdict `possible_miss` или `abstain`.
- [ ] Добавить API schema tests для новых fields.
- [ ] Добавить e2e test: `/gaps/absence` на seed-корпусе возвращает expected verdict distribution.

**Критерий приёмки:** gap search/API/query graph возвращают absence-aware gaps; self-check явно сообщает риск пропуска извлечения; endpoint read-only и не меняет граф.

---

### 25.14 UI: ConflictsGaps и глоссарий absence confidence

- [ ] В `frontend/src/api/types.ts` добавить поля `p_truly_absent`, `p_extractor_missed`, `absence_verdict`, `absence_meta` в тип `Gap`.
- [ ] В `frontend/src/lib/glossary.ts` добавить словарную статью `absence_confidence`.
- [ ] В `frontend/src/components/ConflictsGaps.tsx` добавить chip verdict: `реальный пробел` для `genuine_gap`.
- [ ] Добавить chip verdict: `возможно пропуск извлечения` для `possible_miss`.
- [ ] Добавить chip verdict: `ретрагировано` для `retracted`.
- [ ] Добавить chip verdict: `неопределённо` для `abstain`.
- [ ] Показать строку `риск пропуска извлечения N%` на каждой карточке gap.
- [ ] Показывать статус `калибровано` или `эвристика` по `absence_meta.calibrated`.
- [ ] Показывать краткое обоснование verdict: MENTIONS, recall prior, coverage context, retraction state.
- [ ] Добавить `InfoDot`/tooltip для explanation `absence_confidence`.
- [ ] Добавить фильтр gaps по `absence_verdict`.
- [ ] Добавить сортировку gaps по `p_extractor_missed` и `p_truly_absent`.
- [ ] Добавить visual warning: `possible_miss` не должен отображаться как обычный «белый пробел».
- [ ] Покрыть UI unit tests/render tests для каждого verdict.

**Критерий приёмки:** пользователь видит, является ли gap настоящим пробелом, вероятным miss, ретракцией или неопределённым случаем; UI объясняет calibrated/heuristic status и позволяет фильтровать verdicts.

---

### 25.15 Answerability metrics и no-data evaluation

- [ ] В `evals/metrics.py` реализовать `no_data_recall`.
- [ ] В `evals/metrics.py` реализовать `no_data_precision`.
- [ ] В `evals/metrics.py` реализовать `false_gap_rate`.
- [ ] В `evals/metrics.py` реализовать USP-метрику `no_data_genuine_gap_rate`.
- [ ] Ограничить answerability metrics data-bearing intents; исключить `competence_search`, если он возвращает рейтинг, а не факты.
- [ ] Определить labels для истинного отсутствия данных vs пропуск extraction.
- [ ] Добавить confusion matrix по verdicts: genuine_gap/possible_miss/retracted/abstain.
- [ ] Добавить seed expected metrics snapshot: `no_data_recall`, `false_gap_rate`, `no_data_genuine_gap_rate`.
- [ ] Логировать answerability metrics в eval report и MLflow.
- [ ] Добавить regression test: если данные есть, система не должна заявлять false gap.
- [ ] Добавить regression test: no-data ячейка с MENTIONS должна уходить в `possible_miss`, а не в `genuine_gap`.

**Критерий приёмки:** eval показывает качество распознавания истинного отсутствия данных; false gap rate контролируется release gate; metrics работают только для релевантных data-bearing intents.

---

### 25.16 Extraction-recall evaluation и gold dataset

- [ ] Создать `evals/run_extraction_eval.py`.
- [ ] Создать `evals/datasets/gold_extraction.json` с размеченными фактами, которые должны извлекаться.
- [ ] В gold dataset явно разделить modalities: `table_row`, `chunk`/prose, `catalog_row`.
- [ ] Реализовать attribution `observation_extracted_from` по evidence к `doc_id + modality`.
- [ ] Считать recall = `extracted / expected` по каждой modality.
- [ ] Считать overall recall по всем modalities.
- [ ] Намеренно не считать precision, если deterministic paths не имеют FP labels; зафиксировать это в eval docs.
- [ ] Добавить offline expected behavior: `table_row` recall высокий, `chunk/prose` recall низкий без LLM.
- [ ] Добавить вывод blind-spot report: какие modalities дают miss risk.
- [ ] Добавить CLI arguments: path to gold, backend, extraction_run_id, output report.
- [ ] Добавить tests для attribution fact → evidence → modality.
- [ ] Добавить CI smoke-test на маленьком gold dataset.

**Критерий приёмки:** extraction-recall eval выдаёт recall по modalities и overall; prose blind spot становится измеримым, а не скрытым; gold dataset подключён к absence calibration.

---

### 25.17 Калибровка recall priors на gold-наборе

- [ ] В `analytics/extractor_recall.py` реализовать `calibrate_recall(gold_dataset, extraction_results)`.
- [ ] В `service.py` реализовать `calibrate_extractor_recall(...)`.
- [ ] Калибровка должна заменять heuristic priors калиброванными priors по modality/context.
- [ ] Проставлять `calibrated=true`, `method="gold_calibrated"` для калиброванных priors.
- [ ] Хранить `recall_raw` рядом со сглаженным recall.
- [ ] Использовать сглаживание Джеффриса `(k + 0.5) / (n + 1)` для малых выборок.
- [ ] Избегать ложной уверенности при `0/0` и малом n.
- [ ] Обновить `recall_for_context()`: calibrated priors своей modality имеют приоритет над heuristic fallback.
- [ ] Протянуть `calibrated=true` в `absence_map`, `absence_confidence`, `self_check.absence`.
- [ ] Добавить report: до/после calibration, raw recall, smoothed recall, n, confidence warnings.
- [ ] Добавить tests для Jeffreys smoothing edge cases.
- [ ] Добавить tests, что после calibration absence-layer показывает `calibrated=true`.

**Критерий приёмки:** после запуска calibration absence outputs используют калиброванные priors и явно показывают `calibrated=true`; малые выборки не дают экстремальную ложную уверенность.

---

### 25.18 Тестовый фундамент, offline suite и seed-корпус

- [ ] Создать `tests/test_absence_foundation.py`.
- [ ] Покрыть фазу 0: schema extension fields на `Gap` backward-compatible.
- [ ] Покрыть фазу 1: Observation provenance stamping.
- [ ] Покрыть фазу 2: MetaStore coverage/recalled tables для SQLite.
- [ ] Покрыть фазу 2: MetaStore coverage/recalled tables для PostgreSQL.
- [ ] Покрыть фазу 3: coverage logging document path.
- [ ] Покрыть фазу 3: coverage logging catalog path.
- [ ] Покрыть фазу 3: prose chunks seen/emitted telemetry.
- [ ] Покрыть фазу 4: extractor recall heuristic priors и JSON persistence.
- [ ] Покрыть фазу 5: absence verdicts present/retracted/genuine_gap/possible_miss/abstain.
- [ ] Покрыть фазу 5: `/gaps/absence` read-only API.
- [ ] Покрыть фазу 5: query graph `self_check.absence` summary.
- [ ] Покрыть фазу 6: answerability metrics.
- [ ] Покрыть фазу 6: extraction-recall eval by modality.
- [ ] Покрыть фазу 6: gold calibration and calibrated flag propagation.
- [ ] Довести offline-tests до минимум 22 тестов, отражающих phases 0–6.
- [ ] Добавить deterministic seed corpus с cases: present, genuine gap, possible miss, retracted, abstain.
- [ ] Добавить snapshot expected distribution для seed: counts по verdicts.
- [ ] Запускать suite без сетевых вызовов и без LLM.

**Критерий приёмки:** `tests/test_absence_foundation.py` содержит полный offline regression suite phases 0–6; тесты проходят без LLM и внешней сети; seed distribution стабильна.

---

### 25.19 Документация, ограничения v1 и дальнейшее развитие

- [ ] Создать `docs/absence_confidence/README.md` с объяснением p_truly_absent, p_extractor_missed и absence_verdict.
- [ ] Задокументировать, что v1 verdict считается на уровне `(material, property)`.
- [ ] Задокументировать, что run-level/per-segment attribution пропусков — задача следующей фазы.
- [ ] Задокументировать limitation: маленький gold-набор требует доверительных интервалов и осторожной интерпретации.
- [ ] Добавить TODO: расширить gold-набор и считать доверительные интервалы Уилсона на recall.
- [ ] Добавить TODO: per-run mention/extraction granularity для точного указания, какой run/segment мог пропустить факт.
- [ ] Добавить TODO: benchmark GNN-based link prediction как потенциальная замена/усиление current link-prediction ranking.
- [ ] Добавить TODO: калибровать на реальном production-корпусе, а не только на seed-demo.
- [ ] Добавить user-facing glossary entry: «реальный пробел» vs «возможный пропуск извлечения».
- [ ] Добавить runbook: как rebuild recall priors, как запускать calibration, как интерпретировать abstain.

**Критерий приёмки:** limitations явно видны команде и пользователям; дальнейшее развитие оформлено как roadmap без смешивания с v1 acceptance.

---

### 25.20 Definition of Done для confidence-of-absence

- [ ] Gap schema backward-compatible и содержит absence-поля.
- [ ] Observation provenance содержит extraction run lineage.
- [ ] Coverage telemetry собирается для prose, table rows и catalog rows.
- [ ] Extractor recall priors строятся, сохраняются и имеют heuristic/calibrated status.
- [ ] MENTIONS-lineage наполнен для documents/materials/properties и используется absence-layer.
- [ ] Graph query templates для mention-without-observation и regime coverage работают на embedded/server backend.
- [ ] Absence-layer различает `present`, `retracted`, `genuine_gap`, `possible_miss`, `abstain`.
- [ ] Gap search, query graph и API возвращают annotated gaps.
- [ ] UI показывает verdict chips, miss risk, calibrated/heuristic status и explanation.
- [ ] Answerability metrics и extraction-recall eval входят в eval suite.
- [ ] Calibration на gold-наборе протягивает `calibrated=true` во все outputs.
- [ ] Offline regression suite phases 0–6 зелёный.
- [ ] Документация объясняет ограничения v1 и не позволяет трактовать `possible_miss` как «тему не изучали».

**Критерий приёмки:** раздел 25 считается закрытым только если система может на одном и том же seed-корпусе показать настоящие пробелы отдельно от likely extractor misses, ретракций и неопределённых случаев, а все verdicts имеют explainable provenance и calibration status.
