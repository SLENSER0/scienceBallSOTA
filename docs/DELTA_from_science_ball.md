# DELTA — что перенести из `science_ball` в `scienceBallSOTA`

> **Назначение.** Единственный файл, по которому видно **разницу** между прототипом
> `science_ball` (плоский пакет `materials_kg/`, лог разработки в `build.md`) и этим SOTA-
> монорепо, и по которому можно **строить только то, что здесь реально не хватает** — не
> перечитывая весь `build.md`. Это план портирования, **не** код.
>
> **Как пользоваться.** (1) Создать ветку от `main` (`git switch -c feat/absence-value-benchmark
> main`); (2) брать задачи ниже сверху вниз (HIGH → MEDIUM → LOW); (3) для каждой смотреть
> «Источник в `science_ball`» как референс поведения, `Цель (SOTA)` — куда класть код,
> `**Критерий приёмки:**` — когда закрывать; (4) перед PR прогнать `make check`. Ничего из
> раздела **«Уже есть — не переносить»** не трогать.
>
> Источник истины по поведению: `../science_ball/build.md` §32 (confidence-of-absence),
> §33 (бенчмарк), §33.9 (live-LLM регрессия), §33.10 (N1/N2/N3). Конвенции — как в
> `docs/FULL_SYSTEM_TASKS_science_ball.md` (§-ссылки, чекбоксы, `**Критерий приёмки:**`; русская
> проза, английские идентификаторы; Conventional Commits; trunk-based, ветка от `main`).

---

## 0. Итог различия (одним абзацем)

SOTA **уже** содержит зрелый слой confidence-of-absence (§25): те же вердикты
`present/covered/retracted/possible_miss/genuine_gap/abstain`, те же пороги
`POSSIBLE_MISS_AT=0.60 / GENUINE_GAP_AT=0.25`, байесовский постериор
(`confidence_of_absence.py`), Beta-сглаженные эмпирические recall-приоры из телеметрии
(`recall_priors.py`), MENTIONS-линию (`mentions_lineage.py`), слепые зоны
(`blindspot_report.py`), ретракции (`retractions.py`) и **более богатый**, чем в прототипе,
gap-подсистему (`gap_lifecycle/trends/dashboard/scoring/coverage_matrix`). **Фундамент — не
пробел.** Реальная разница — это недавняя работа `science_ball` по укреплению USP: различение
**«упомянуто ↔ измерено»**, **честный прозовый приор**, **проза → Observation** и **весь бенчмарк
Track C** (синтетический корпус с архетипами + классификационная оценка + калибровка). Проверено
grep’ом (0 совпадений `value_in_mention` / `TRUE_MISS` / `FALSE_MISS` / `measurable_in_source`) и
чтением `absence_signals.py`, `recall_priors.py`, `packages/kg_eval/`.

## 1. Таблица различий

| # | Возможность (`science_ball`) | Статус в SOTA | Куда в SOTA | Действие |
|---|---|---|---|---|
| N2 | value-in-mention гейт вердикта | **отсутствует** | `kg_retrievers/absence_signals.py` + `kg_extractors` + config | **строить** |
| A7 | offline value-детектор `value_present_in_text` | **отсутствует** | `kg_retrievers/value_in_mention.py` (новый) | **строить** |
| N1 | честный committed-recall прозовый приор | **иначе** (SOTA — эмпирический Beta-приор) | `kg_retrievers/recall_priors.py` + config | **адаптировать, не копировать** |
| N3 | проза → review-gated Observation | **частично / проверить** | `kg_extractors`, `apps/ingestion-service` | **сначала проверить**, потом добить |
| §33 | бенчмарк Track C (absence-классификация) | **отсутствует** | `packages/kg_eval/absence_eval.py` (новый) | **строить** |
| §33 | синт. корпус с архетипами (Dataset 1) | **отсутствует** | `packages/kg_eval/datasets/synthetic.py` | **строить** |
| §33 | схемы `AbsenceCell/Prediction/REALITIES` | **отсутствует** | `packages/kg_eval/schemas.py` | **строить** |
| §33 | калибровка Brier/ECE/AUROC | **отсутствует** | `packages/kg_eval/calibration.py` | **строить** |
| A2 | Track-A: gold↔extracted matching | **частично** | `packages/kg_eval/matching.py` | **строить** |
| A3 | guardrail «приор vs измеренный recall» | **частично** | `packages/kg_eval/guardrails.py` | **строить** |
| A5 | cross-profile регресс-гвард | **отсутствует** | `packages/kg_eval/run_benchmark.py` | **строить** |
| A1 | profile-aware findings в отчёте | **частично** | `packages/kg_eval/reports.py` | **строить** |
| — | active-learning рекомендатель (BO/GP) | отсутствует | `kg_retrievers/active_learning.py` | опционально |
| — | link-prediction (Adamic–Adar) | отсутствует | `kg_retrievers/link_prediction.py` | опционально |
| — | decision-history / outdated-decision | отсутствует | `apps/curation-service` | опционально |
| — | conformal-фильтр фактичности ответа | иначе | `apps/agent-service` | опционально |
| ✓ | ядро вердикта absence, telemetry, MENTIONS-линия | **эквивалентно** | — | **не трогать** |

---

## 2. HIGH — ядро USP-разницы (строить первым)

Все флаги — **opt-in, по умолчанию OFF**, чтобы существующие пины поведения SOTA оставались
зелёными (тот же принцип, что в `science_ball` §33.10).

- [x] **D1. Offline value-детектор** — `packages/kg_retrievers/src/kg_retrievers/value_in_mention.py`
  (новый). Функция `value_present_in_text(text, aliases) -> bool`: предложение, называющее
  свойство И содержащее числовой токен И без cue-фраз отрицания/отсрочки (RU-стемы «не измер»,
  «не провод», «запланир», «отсутств»… + EN «not measured», «future work»…), cue’ы привязаны к
  границе слова; пустой список алиасов → `False` (свойство не локализуемо). Задокументировать
  предельные случаи (клаузо-уровневое отрицание, «любая цифра»).
  *Источник:* `science_ball/materials_kg/analytics/value_in_mention.py`, build.md §33.10 (A7).
  **Критерий приёмки:** юнит-тест RU+EN: «значение указано» → True, «лишь названо/не измеряли» →
  False, кросс-свойство и пустые алиасы → False; работает без LLM.

- [x] **D2. `value_present` на прозовом ребре MENTIONS** — в `kg_extractors`/`apps/ingestion-service`
  при создании `Document→(MENTIONS)→Property` (via=`ingest`) прогонять D1 по тексту сегмента и
  писать `value_present: bool` в свойства ребра. Каталожные/структурные рёбра — **без** флага.
  *Источник:* `science_ball` `ingestion_graph.link_mentions`, build.md §33.10 (N2).
  **Критерий приёмки:** после ингеста прозы, где значение указано → `value_present=True`; где лишь
  названо → `False`; ре-ингест **обновляет** флаг (идемпотентно, паритет embedded/Neo4j —
  ср. фикс `EmbeddedGraphStore.upsert_relationship` в `science_ball`).

- [x] **D3. Opt-in value-гейт вердикта** — `kg_retrievers/absence_signals.py`: параметр
  `value_gate` (по умолчанию off) + config-флаг `absence_value_gate`. Читать **только прозовые**
  (via=`ingest`) рёбра, упоминающие И материал И свойство; понижать `possible_miss → genuine_gap`
  **только при полном положительном свидетельстве**: все прозовые упоминания помечены и ни одно не
  содержит значения. Любое непомеченное прозовое ребро (или только каталог) → `None` → **не
  понижать** (дисциплина «не понижать по незнанию»).
  *Источник:* `absence_confidence._mention_value_present` + гейт, build.md §33.10 (N2), фиксы
  находок 12/14.
  **Критерий приёмки:** на синт-корпусе FALSE_MISS→`genuine_gap`, TRUE_MISS→`possible_miss`;
  при `value_gate` off вердикты не меняются (пины зелёные).

- [x] **D4. Схемы бенчмарка** — `packages/kg_eval/src/kg_eval/schemas.py` (новый): `VERDICTS`,
  `REALITIES`, `AbsenceCell` (с **раздельными** `mentioned_in_source` и `measurable_in_source`),
  строгий `AbsencePrediction.correct` (abstain никогда не «верно»), `GoldExtractionFact`,
  `DatasetManifest`. Аддитивно.
  *Источник:* `science_ball/materials_kg/evals/schemas.py`, build.md §33.
  **Критерий приёмки:** dataclasses импортируются и покрыты юнит-тестом контракта `correct`.

- [x] **D5. Синтетический корпус с архетипами (Dataset 1)** —
  `packages/kg_eval/src/kg_eval/datasets/synthetic.py` (новый подпакет). Детерминированный
  (content-hash LCG, **без** системного RNG) генератор архетип→reality: PRESENT_TABLE/CATALOG,
  TRUE_MISS (значение в прозе), FALSE_MISS (лишь названо), ABSENT, RETRACTED — где `MENTIONS`
  срабатывает и для TRUE_MISS, и для FALSE_MISS (иначе разницу не измерить); gold-факты с
  флагом `extractable_offline`. Пререквизит D6.
  *Источник:* `science_ball/materials_kg/evals/datasets/synthetic.py`, build.md §33.2.
  **Критерий приёмки:** тот же seed → тот же корпус; `absence_signals` без value-гейта путает
  TRUE_MISS и FALSE_MISS (обе → `possible_miss`) — слабость воспроизводится.

- [x] **D6. Бенчмарк Track C — оценка absence-классификации** —
  `packages/kg_eval/src/kg_eval/absence_eval.py` (новый). Прогон текущего слоя + лестницы
  бейзлайнов (naive_graph / mentions_heuristic / static_modality) по размеченным ячейкам; матрица
  `REALITIES × VERDICTS`, per-class P/R/F1, `macro_f1`, бизнес-метрики (`false_gap_rate`,
  `miss_detection_recall`, `false_possible_miss_rate`, `no_data_recall`); abstain не считается
  верным. Плюс value-методы (oracle-потолок + D1-regex) как в A7.
  *Источник:* `science_ball/materials_kg/evals/absence_eval.py`, build.md §33.4/§33.5.
  **Критерий приёмки:** на синт-корпусе базовый слой даёт `false_possible_miss_rate>0`, value-
  oracle/regex → macro-F1≈1.0, `false_possible_miss_rate=0` (различие value-гейта измеримо).

---

## 3. MEDIUM — полнота бенчмарка и интеграция

- [x] **D7. Калибровка вероятностей** — `packages/kg_eval/src/kg_eval/calibration.py` (чистый numpy):
  `probability_report` (Brier, clipped log-loss, ECE с reliability-бинами, tie-averaged AUROC,
  AUPRC), перцентильные bootstrap-CI, grid-search порогов по cost-matrix на детерминированном
  calib-сплите (в продакшн **не** писать). Скоуп — ячейки без активного obs/ретракции.
  *Источник:* `science_ball/materials_kg/evals/calibration.py`, build.md §33.
  **Критерий приёмки:** метрики совпадают с ручным расчётом на игрушечном векторе; CI
  детерминированы при фиксированном seed.

- [x] **D8. Track-A: семантический matching gold↔extracted** —
  `packages/kg_eval/src/kg_eval/matching.py`. `match_fact` по material+property+value(±tol)+unit
  (alias-aware)+direction+evidence → per-modality `semantic_recall`/`evidence_recall`/
  `value_precision`. Прозовый recall≈0 offline — это **ожидаемо**, не регрессия.
  *Источник:* `science_ball/materials_kg/evals/matching.py`, build.md §33 (Track A / A2).
  **Критерий приёмки:** table/catalog recall=1.0, chunk(проза) recall=0.0 на синт-корпусе offline.

- [x] **D9. Guardrail «приор vs измеренный recall» (A3)** —
  `packages/kg_eval/src/kg_eval/guardrails.py`. `check_recall_priors`: `base_recall(modality)` vs
  измеренный `semantic_recall`; divergence > tolerance(0.30) → `over_tolerance`. Только чтение,
  приоры не переписывать. Зависит от D8.
  *Источник:* `science_ball/materials_kg/evals/guardrails.py`, build.md §33.10 (A3).
  **Критерий приёмки:** при завышенном прозовом приоре vs измеренного 0.0 — флаг ⚠️; иначе ok.

- [x] **D10. Оператор порчи `retract_cells` (Dataset 2)** —
  `packages/kg_eval/src/kg_eval/datasets/corruptions.py`. Минимум вертикальный срез
  `retract_cells` (даёт reality `retracted` через существующий retract-примитив) + `OPERATOR_CATALOG`
  как спецификация остальных операторов.
  *Источник:* build.md §33 (Dataset 2 / A8).
  **Критерий приёмки:** порченые ячейки классифицируются как `retracted`, а не как gap.

- [x] **D11. Loader изолированного прогона + профили** —
  `packages/kg_eval/src/kg_eval/datasets/loader.py`. Контекст-менеджер с валидацией профиля,
  изолированным `MKG_DATA_DIR`, применением порчи, provenance-конвертом, безопасным откатом.
  Переиспользовать паттерн temp-graph seeding из `kg_eval/runner.py`.
  *Источник:* `science_ball/materials_kg/evals/datasets/loader.py`.
  **Критерий приёмки:** прогон не трогает продовый стор; корпус детерминирован по seed.

- [x] **D12. Report + profile-aware findings (A1) + compare** —
  `packages/kg_eval/src/kg_eval/reports.py` (absence-отчёт), стиль как `kg_eval/report.py`.
  report.json/report.md с конвертом воспроизводимости, матрицей, threshold-study, секциями
  A2/A3/A7; **profile-aware** findings (утверждать mention-vs-value путаницу только когда
  `false_possible_miss_rate>0`); `compare()` парных дельт.
  *Источник:* `science_ball/materials_kg/evals/reports.py`, build.md §33.10 (A1).
  **Критерий приёмки:** offline и live-профиль дают разные честные нарративы, без хардкода.

- [x] **D13. Оркестратор + cross-profile регресс-гвард (A5)** —
  `packages/kg_eval/src/kg_eval/run_benchmark.py` + CLI `python -m kg_eval.run_benchmark`.
  `run(track='absence', profile,...)` + `run_regression_check`: пересобрать прозовый приор OFF vs
  ON по одному offline-корпусу, `regression_detected`, если accuracy падает И
  `abstention_jump>=порог`; CLI exit 1 при регрессии (CI-гейт).
  *Источник:* `science_ball/materials_kg/evals/run_benchmark.py`, build.md §33.10 (A5).
  **Критерий приёмки:** тумблер приора детерминированно воспроизводит коллапс (acc↓, abstain↑),
  exit 1.

- [x] **D14. N1 — честный committed-recall прозовый приор (адаптация, НЕ копия)** —
  `kg_retrievers/recall_priors.py` + config `honest_recall_priors` (default off). SOTA уже считает
  recall **эмпирически** (Beta по телеметрии), поэтому: (a) **проверить**, различает ли telemetry-
  ключ «кандидат предложен» vs «Observation записан» — если нет, добавить `kind` (chunk vs table)
  в ключ покрытия, чтобы у прозы был свой знаменатель; (b) opt-in флаг, занижающий прозовый приор к
  committed-floor, когда путь «проза→Observation» выключен; калиброванные/эмпирические-с-данными
  приоры **не** трогать.
  *Источник:* build.md §33.9 (механизм регрессии) + §33.10 (N1).
  **Критерий приёмки:** при выключенном коммите прозы прозовый приор не завышен (guardrail D9 не
  флагует); при включённом — эмпирический приор как есть.

- [x] **D15. Интеграция config/CLI/API** — протянуть три флага (`honest_recall_priors`,
  `absence_value_gate`, `prose_observation_extraction`) через `kg_common` config → absence-слой /
  ingestion; добавить benchmark-подкоманды в `kg_eval`; при необходимости — эндпоинт в
  `apps/api-gateway`. Дефолты — легаси.
  **Критерий приёмки:** флаги по умолчанию off, существующие тесты SOTA зелёные; включение флага
  меняет поведение как ожидается.

---

## 4. N3 — проза → Observation: **сначала проверить, потом достраивать**

SOTA уже извлекает из прозы: `property_extractor.py` (§6.6, упоминания свойств RU/EN — даже без
числа), `processing_extractor.py` (§6.5, методы + параметры temperature/time…), и пайплайн считает
`measurements`. Поэтому **не переписывать вслепую**.

- [x] **D16. Аудит: попадает ли числовое значение из прозы в review-gated Observation?**
  Прочитать `apps/ingestion-service/src/ingestion_service/pipeline.py` (`_apply_extraction`,
  `measurements`) и `kg_extractors`. Ответить: (1) извлекается ли **числовое измеренное значение**
  из прозового предложения в `Measurement/Observation` (а не только упоминание свойства)?
  (2) идёт ли оно через review-гейт (не авто-коммит)? Если **оба да** — N3 **уже есть**, задача
  закрывается без кода. Если нет — построить (по образцу `science_ball`
  `extraction.llm_observations_from_text`): opt-in `prose_observation_extraction`, `confidence 0.6`
  (< авто-коммит), `requires_review=True`, content-derived stable_id по всем различающим полям
  **включая материал** (иначе два материала с одинаковым свойством/значением в одном чанке
  схлопнутся — см. фикс находки 5), offline → `[]` no-op.
  *Источник:* build.md §33.10 (N3) + фиксы находок 5.
  **Критерий приёмки:** документирован вывод аудита; при необходимости — прозовое числовое значение
  становится **review-gated** Observation, offline/flag-off = no-op, ре-ингест идемпотентен.

---

## 5. LOW — опциональные порты (не USP-разница)

- [ ] **D17.** Active-learning рекомендатель (numpy RBF-GP + MC Expected Improvement, предложение
  `ExperimentRun` через review-гейт) → `kg_retrievers/active_learning.py` + `apps/agent-service`.
  *Источник:* `science_ball/materials_kg/analytics/active_learning.py`.
- [ ] **D18.** Link-prediction (2-hop Adamic–Adar для приоритизации gap’ов) →
  `kg_retrievers/link_prediction.py`.
- [ ] **D19.** Decision-history + `potentially_outdated` (новые obs после решения) →
  `apps/curation-service`.
- [ ] **D20.** Conformal-фильтр фактичности ответа (калибровка τ на gold) → `apps/agent-service` +
  `kg_eval/calibration.py`. Комплементарен цитатному граундингу.
- [ ] **D21.** Answerability-метрики (`no_data_recall/precision`, `false_gap_rate`) →
  `kg_eval/metrics.py`, только для data-bearing intents.
- [ ] **D22.** Trace-инспекция прогонов LangGraph (`GET /traces` + timeline во фронте) →
  `apps/agent-service` + `apps/frontend`.

---

## 6. Уже есть в SOTA — НЕ переносить (present-equivalent)

Проверено чтением кода — переписывать не нужно, только (опц.) точечно расширить, если сядут D1–D16:

- Ядро вердикта absence (`absence_signals.classify_cell`) — те же пороги/вокабуляр. Опц.: добавить
  `MENTION_MISS_FLOOR`, когда сядут N1/N2.
- Байесовский постериор `confidence_of_absence.py`, Beta-приоры `recall_priors.py` — **лучше**
  скалярного эвристического приора прототипа; N1 = адаптация (D14), не замена.
- Extraction-coverage telemetry (знаменатели recall) — есть; при N1 расширить ключ на `kind`.
- MENTIONS-линия + mentioned-without-observation (`mentions_lineage.py`, `blindspot_report.py`).
- Ретракции (`retractions.py`, `include_retracted`), gap-подсистема
  (`gap_lifecycle/trends/dashboard/scoring/coverage_matrix`) — в прототипе слабее.

---

## 7. Ветка и коммиты (SOTA-конвенции)

```
git switch -c feat/absence-value-benchmark main
# D1..D6 (HIGH) → PR #1 ; D7..D16 (MEDIUM+N3-аудит) → PR #2 ; D17..D22 (LOW) — по желанию
make check   # lint + format-check + tests — перед каждым PR
```
Коммиты — Conventional Commits со scope пакета:
`feat(kg_retrievers): value-in-mention detector + opt-in value gate (port science_ball N2/A7)`,
`feat(kg_eval): absence Track-C benchmark + synthetic archetypes (port science_ball §33)`.
Нетривиальные решения (напр. «прозовый приор: committed vs read-ability») — ADR в `docs/adr/`.

> Все новые возможности — **opt-in, дефолт off**: существующие пины поведения SOTA (§25) должны
> остаться зелёными. Это и есть аддитивный принцип из `science_ball` §33.10.
