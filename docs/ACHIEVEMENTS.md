# Научный клубок — журнал достижений (session log)

*Что построено за интенсивную сессию разработки. Для рассказа/демо и передачи.*

Дата среза: 2026-07-03 · Ветка `main` · всё запушено.

---

## Одной строкой

Полнофункциональная **knowledge-graph платформа для горно-металлургического R&D**:
живой продукт со стриминговым чат-ассистентом, доказательной базой на каждое число,
графом на 66k узлов, **полным серверным стеком** (Neo4j + Qdrant + OpenSearch), **SSO
через authentik** с ролевым разграничением, и **905 модулями / 9302 зелёными тестами**.

## Метрики (на срез)

| Показатель | Значение |
|---|---|
| Задач плана помечено | **1924 / 3283 (58.6%)** — всё по строгой верификации |
| Зелёных тестов | **10558** |
| Модулей (src `.py`) | **1020** |
| Коммитов за сессию | **142** |
| Живые сервисы | API :8000 · UI :3000 · authentik :9100 · Neo4j :7687 · Qdrant :6333 · OpenSearch :9200 |
| Лицензии | только OSS/permissive (§7.5): AGPL/GPL/LGPL/EPL/MPL/Apache-2.0/MIT |
| LLM | только open-source (Qwen / DeepSeek / Mistral через OpenRouter) |

---

## Что работает вживую (демо-путь)

1. **Красивая авторизация** (`http://localhost:3000`): брендированный экран входа с
   анимированным «клубком», кнопкой SSO (authentik) и карточками ролей.
2. **authentik SSO** (`:9100`): OSS identity-provider, OIDC-приложение и **6 RBAC-групп**
   провизионятся автоматически blueprint'ом; группы маппятся на роли (highest-privilege-wins).
3. **Ролевое разграничение**: внешний партнёр теряет доступ к «Пробелам и рискам»; каждый
   запрос несёт Bearer/роль; бэкенд принимает и authentik-RS256, и dev-JWT.
4. **Стриминговый чат** (вкладка «Диалог»): многоходовой диалог, **SSE токен-за-токеном**,
   история сессий, каждый ответ = evidence-first вид + инлайн-граф.
5. **Guardrails достоверности**: любое число в ответе без ссылки `[n]` помечается,
   `verified=false`, достоверность режется ≤0.5 (проверено: реальный ответ пометил 9 чисел).
6. **Граф знаний** (canvas «клубок»): таскается мышью, зумится колесом, полный экран,
   сэмплинг до 600 узлов, визуальные кодировки §5.2.3.
7. **OSS-LLM синтез**: deepseek-chat-v3 через OpenRouter даёт цитированные ответы на русском.

---

## Крупные вехи сессии

### 1. Полный серверный стек (переход с embedded на server-профиль)
- Подняты 6 инфра-контейнеров (Neo4j 5.26, Qdrant, OpenSearch 2.17, Postgres, valkey, MinIO).
- Написаны 3 live-тестированных стора: **Neo4jGraphStore** (drop-in для Kuzu, все 17 методов),
  **QdrantServerStore**, **OpenSearchKeywordStore**.
- **Мигрировано 66 027 узлов / 208 378 рёбер** Kuzu→Neo4j точь-в-точь; 18 247 чанков
  переиндексированы в Qdrant + OpenSearch.
- `store_factory` / `retrieval_factory` переключают backend по `RUNTIME_PROFILE`.
- Приложение работает на живом Neo4j+Qdrant+OpenSearch, проверено end-to-end.

### 2. authentik SSO + роли + красивый логин (§19)
- authentik-server/worker + свой postgres в compose (:9100), blueprint провизионит
  OIDC-app + 6 групп.
- Бэкенд `auth_oidc.py`: валидация RS256 через JWKS, маппинг групп→ролей.
- Фронт `LoginView` + персист-сессия + ролевой nav + user-чип с выходом.

### 3. Стриминговый чат-UI + guardrails (§14.4 / §13.16)
- `ChatView` на живом §14.4-бэкенде (SSE), реюз `AnswerView`/`GraphView`.
- `answer_validator` вкорячен в verifier: «ни одного числа без evidence».

### 4. SOTA-методы из статей (§23.35)
- Каталог `docs/reference/sota_catalog_2025_2026.md` (Docling/MinerU/olmOCR, LightRAG/
  HippoRAG/PathRAG, MatKG, PaperQA2/HalluMat/FaithJudge …) с сохранением всех ⚠-лицензий.
- Реализованы ядра методов как embedded-модули (каждый цитирует статью): LightRAG dual-level,
  HippoRAG-2 personalized-PageRank memory, PathRAG flow-pruning, PaperQA2 contradiction,
  HalluMat contradiction-graph, FaithJudge-lite, OmniDocBench-score, LELA linking, KAG
  logical-form. *(см. `packages/kg_retrievers` + `packages/kg_eval`)*

### 5. Массовое покрытие плана (grep-based autoscale)
- Пайплайн **grep реального плана → build волнами по 10 → строгая верификация → пометка**.
- ~800 модулей построено за сессию; счётчик двигался только по verified-DONE:
  **1469 → 1575 → 1640 → 1830 → 1909** (44.7% → 58.1%), +440 задач.

---

## Honesty log — что честно НЕ сделано / оговорки

Строгая самопроверка держалась всю сессию. Прямо и без прикрас:

- **Ранние ручные батчи (12–23) выдумывали номера подсекций** (§7.10+, §3.19+ и т.п.),
  которых нет в плане. Код настоящий и протестированный, но задаче не соответствует и НЕ
  помечен. После этого перешёл только на grep-based (сверка с реальным планом).
- **Многие подсекции остаются PARTIAL**: ядро есть, но не хватает конкретных bullet'ов
  (Dockerfile фронта, named networks, `versions.env`, DataHub/OpenMetadata адаптеры,
  реальный Dagster-оркестратор, микросервисы graph/search/extraction/curation).
- **Инфра-задачи требуют поднятия внешних систем** (MLflow-сервер с UI, DataHub, Dagit :3001),
  их acceptance нельзя закрыть чистым модулем.
- **SSO end-to-end клик** (browser-redirect authentik→app) не проверялся headless — проверены
  boot, JWKS, discovery, group→role (unit-тесты). Токен-exchange на бэкенде — заготовка.
- **Инцидент**: cleanup-скрипт по ruff-выводу однажды снёс мой же `auth_oidc.py` (восстановил
  из git). Урок: не запускать массовый `rm`, не отличая огрызки убитых агентов от своих файлов.
- **Session-лимиты** пару раз убивали часть агентов на полпути — интегрировал то, что успело
  собраться зелёным, огрызки отбрасывал по индивидуальной проверке.

## Killer-фичи (4 из 4 — по запросу пользователя)

Все проверены вживую на server-профиле (Neo4j/Qdrant/OpenSearch), фронт на :3000.

1. **Ризонинг в чате.** Reasoning-модели (deepseek-v4-flash, glm-5.2) отдают
   `message.reasoning` — `LLMClient.complete_with_reasoning()` его ловит, `AnswerPayload`
   получил поле `reasoning`, чат-SSE шлёт событие `reasoning` до токенов, а фронт
   показывает сворачиваемую панель «Рассуждение» (open-webui-стиль). Проверено:
   `/query` вернул answer(1454)+reasoning(743) от deepseek-v4-flash.
2. **Upload документа → граф + viewer (§17.19).** `POST /documents/upload` (multipart,
   RBAC curator+, guard'ы 64 МБ/типа) гоняет НАСТОЯЩИЙ ingestion-пайплайн
   (`parse_document` + `IngestionPipeline.ingest`) в граф и возвращает 2-hop подграф;
   плюс `/parsed`, `/pages/{n}`, `/graph`, `/reindex` (dedup по хешу). Фронт:
   dropzone + прогресс + подграф (2D/3D) + постраничный parsed-viewer, инвалидация
   кэшей графа/coverage. Проверено: .txt по флотации → 23 узла в Neo4j.
3. **3D-граф wow-режим (§17.18).** `ForceGraph3DView` на react-force-graph-3d (three.js),
   те же §5.2.3-кодировки; `GraphPanel` — переключатель 2D/3D, тяжёлый three.js в
   lazy-чанке (1.37 МБ грузится только при выборе 3D, главный бандл не растёт). Вшит
   в AskView и ChatView.
4. **Мультимодальный deep-research (minimax-m3).** `LLMClient.complete_multimodal()`
   (vision-формат OpenRouter), `POST /research/multimodal` (картинка+вопрос, RBAC,
   guard'ы 12 МБ/типа) → base64 data-URI → minimax/minimax-m3 → структурный разбор.
   Фронт: `MultimodalPanel` (dropzone+preview+анализ). Проверено вживую: график
   «Cu-извлечение vs pH» → модель распознала форму кривой, оси, единицы, подписи.

**Побочный фикс (важный):** fastembed тянул `tokenizers 0.23.1`, а `transformers` за
granite-эмбеддингами требует `<=0.23.0` во время импорта — ломало retrieval `/query`
и 6 тестов. Запинил через `[tool.uv] constraint-dependencies` на 0.22.2 (устраивает и
fastembed `<1.0`, и transformers). Все 52 ранее-красных теста зелёные. Заодно OSS-allowlist
(ADR-0006) расширен провайдерами, которые пользователь выбрал и которые ошибочно
блокировались: `z-ai`/`zhipu` (GLM, MIT), `minimax` (Apache-2.0), `ibm-granite`
(Apache-2.0), `moonshotai` (Apache-2.0). Закрытые (GPT/Claude/Gemini/Grok/Llama) по-прежнему
блокируются — проверено.

## Адверсариальная проверка 5 требований ТЗ + починка (2026-07)

5 параллельных adversarial-агентов (default вердикт «не выполнено», живые пробы по
:8000 + Neo4j) проверили ключевые требования ТЗ. Нашли системные провалы — починил.

| Требование | Было | Стало |
|---|---|---|
| **Параметрические запросы** (материал+процесс+условия+гео+время) | PARTIAL 3/5 — гео и время парсились, но retrieval их **игнорировал** | гео+время **реально фильтруют**; парсер направления времени («после/до/диапазон») |
| **Верификация** (источник+достоверность+**актуализация**) | PARTIAL — дата актуализации = **мёртвый код** | источник+гео+год+**дата актуализации** на каждой цитате (40/40) |
| **Отечественная vs зарубежная + гео-фильтр** | **MISSING** — 0/23414 фактов классиф., фильтра нет | **19 473 факта классиф.**; retriever-фильтр + **явный API-параметр + UI-переключатель** |
| **Числовые диапазоны** (…+**экономика**) | PARTIAL — валютный юнит **выкидывался** | экономические юниты (руб/т, \$/т, млн руб) парсятся+нормализуются |
| **Масштабируемость доменов** | PARTIAL (лучший) — 2/4 домена скелеты | без изменений: все 4 есть, +5-й одним YAML доказан |

**Корневые фиксы:** (1) пропагация provenance Document→Evidence→Measurement
(`scripts/propagate_geography.py` — бэкфилл 19 473 фактов; `pipeline.py` — на будущие
загрузки): country/practice_type/source_year/source_date. (2) `GraphRetriever._passes_geo/
_passes_year` — фильтрация фактов И evidence. (3) парсер: направление времени, стем
«росси» для склонений. (4) `Citation.as_of` + рендер «отеч./заруб. · год · актуал. дата».
(5) явный `geography`-параметр `/query` + сегмент-контрол в AskView. (6) валютные юниты.

**Проверено вживую:** «отеч.» (4449 узлов) ≠ «заруб.» (2012); «после 2015» ≠ «до 2010»;
geo=russia → 0 foreign фактов, geo=foreign → 0 russia; цитаты geography=russia year=2012
актуал.=2026-07-02. **Честные остатки** (в основном данные, не код): библио-заголовки
источников = OCR-огрызки; ~17% фактов без гео + распознавание склонений зарубежных стран;
экономика/экология/отходы разрежены в корпусе; привязка числового порога к конкретному
параметру. Тесты: 731 agent-service + 186 units + 115 ingestion + 53 query — зелёные.

## UI-батч §17 (2026-07, всё live на :3000, коммичено)

Достроил крупнейшие непокрытые экраны фронта на уже-живых backend-эндпоинтах:
- **Entity Detail (§17.11)** — «Сущности»: обзор по типам (/graph/nodes) → свойства +
  1-hop граф связей (2D/3D через GraphPanel, /entities/{id}/neighbors) + история (/history).
- **Curation queue (§17.15)** — «Курирование» (curator+): очередь ревью (/curation/queue),
  утвердить/отклонить (/entities/{id}/status), история по элементу.
- **Admin/Governance (§17.20)** — «Администрирование» (curator+): счётчики узлов/связей,
  распределение по типам (/admin/stats), lineage-прогоны (/admin/lineage), матрица покрытия
  + технико-эконом. размеры, **аналитика графа — центральность** (/admin/graph-algos),
  журнал аудита (/admin/audit).
- **Saved views + экспорт (§17.16)** — «Сохранить вид» (POST/GET /views, с гео-фильтром),
  список сохранённых на пустом Ask; **PNG-экспорт графа** (canvas→toBlob, кнопка Camera);
  **CSV-экспорт** таблицы сравнения (CompareView).
- Пропущен Experiment Explorer (§17.12) — в корпусе 0 узлов Experiment (нет данных).

Все экраны role-gated в NAV; tsc+eslint+build зелёные; эндпоинты проверены 200 через
vite-прокси :3000.

## Как поднять всё заново

```bash
# инфра
docker compose -f infra/docker-compose.yml up -d neo4j qdrant opensearch postgres redis minio \
  authentik-postgres authentik-server authentik-worker
# миграция графа (если var/kuzu есть, а Neo4j пуст)
uv run python scripts/migrate_kuzu_to_neo4j.py && uv run python scripts/index_chunks_server.py
# API (server-профиль + SSO)
RUNTIME_PROFILE=server OIDC_ISSUER="http://localhost:9100/application/o/science-ball/" \
  uv run uvicorn api_gateway.main:app --port 8000
# фронт
cd apps/frontend && npm run dev    # → http://localhost:3000
```
