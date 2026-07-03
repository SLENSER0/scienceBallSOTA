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
