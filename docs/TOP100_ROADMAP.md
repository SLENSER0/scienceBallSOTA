# Топ-100 задач: максимальное улучшение качества + «вау»

Отобрано workflow'ом (9 агентов-аналитиков по разделам плана + ранжирование по влияние-на-качество × вау / усилие). Из 0138 кандидатов → 100.

**Легенда:** `qi` = влияние на качество (1–5) · `w` = вау на демо (1–5) · effort S/M/L · ⚡ = quick-win.

## Сводка по темам

| Тема | Задач | Лучший ранг |
|---|---|---|
| Извлечение и данные | 13 | #1 |
| Единицы и Entity Resolution | 13 | #2 |
| Пробелы · противоречия · absence | 12 | #3 |
| Домен и интеграции | 10 | #4 |
| Фронтенд и визуализация | 14 | #7 |
| Агент и API | 11 | #12 |
| Онтология · граф · инфра | 8 | #20 |
| Governance · метрики · безопасность | 12 | #23 |
| Поиск · GraphRAG · fusion | 7 | #33 |

**Quick-wins (⚡):** 9

## Полный список (по ценности)

| # | Ref | Задача | qi | w | eff | тема |
|---|---|---|---|---|---|---|
| 1 | §6.10/§8.3 | Table-cell Evidence: клик по числу → подсветка точной ячейки исходной таблицы | 5 | 5 | M | Извлечение и данные |
| 2 | §8.8 | Экран ревью ER-кандидатов + GET /entities/candidates?status=review_needed | 5 | 5 | M | Единицы и Entity Resolution |
| 3 | §25.14 | «Карта неизвестного»: absence-verdict в UI пробелов | 5 | 5 | M | Пробелы · противоречия · absence |
| 4 | §23.29 | Reproducible Evidence Pack: экспорт ответа (HTML/PDF/ZIP/JSON) + replay | 5 | 5 | M | Домен и интеграции |
| 5 | §23.34 | Фигуры как evidence: Figure/Image-узлы с bbox из PDF в графе и в инспекторе | 5 | 5 | M | Домен и интеграции |
| 6 | §23.31 | Baseline/ablation бенчмарк: full-system vs plain-RAG/BM25/Neo4j/GraphRAG на golden | 5 | 5 | L | Домен и интеграции |
| 7 | §17.7 | Tool-call timeline агента в чате (resolve→graph→vector→evidence→gap) | 4 | 5 | M | Фронтенд и визуализация |
| 8 | §17.14 | Gap-матрица heatmap material×property на ECharts | 4 | 5 | M | Фронтенд и визуализация |
| 9 | §17.9 | Панель community summaries (GraphRAG) рядом с кластерами | 5 | 4 | M | Фронтенд и визуализация |
| 10 | §7.3 | Кросс-шкальное сравнение твёрдости HV↔HRC↔HB (ASTM E140) в Q&A/Сравнении | 4 | 5 | M | Единицы и Entity Resolution |
| 11 | §7.5 | Apples-to-apples: нормализованные единицы в Сравнении (ksi/N·mm⁻²/MPa → MPa) | 5 | 4 | M | Единицы и Entity Resolution |
| 12 | §13.21 | HITL-уточнение в чате: агент останавливается и переспрашивает | 4 | 5 | M | Агент и API |
| 13 | §13.11 | Предсказание недостающих связей (link prediction, Mode D) | 4 | 5 | M | Агент и API |
| 14 | §25.13 | Честный no-data в чате: self_check.absence + предупреждение о риске пропуска | 5 | 4 | M | Пробелы · противоречия · absence |
| 15 | §25.11 | Value-of-Information ранжирование «карты неизвестного» | 4 | 5 | M | Пробелы · противоречия · absence |
| 16 | §15.9 | План закрытия пробелов: минимальный набор экспериментов | 4 | 5 | M | Пробелы · противоречия · absence |
| 17 | §23.27 | Source trust / retractions / freshness в цитатах и verifier | 5 | 4 | M | Домен и интеграции |
| 18 | §17.9 | Large-graph WebGL режим (Sigma+Graphology) на весь корпус 66k | 4 | 5 | L | Фронтенд и визуализация |
| 19 | §8.10 | Dagster-asset entity_resolution + инкрементальный ER-шаг в ingestion | 5 | 4 | L | Единицы и Entity Resolution |
| 20 | §3.14 | Живой GDS на Neo4j: Louvain-кластеры + nodeSimilarity, раскраска сообществ в 3D-графе | 4 | 5 | L | Онтология · граф · инфра |
| 21 | §3.14 | Предсказание недостающих связей (GDS nodeSimilarity/KNN) — «граф подсказывает вероятные, но неявные связи» | 4 | 5 | L | Онтология · граф · инфра |
| 22 | §8.2 | Бейдж авторитета Materials Project (mp_id + canonical-формула) в Entity Detail ⚡ | 4 | 4 | S | Единицы и Entity Resolution |
| 23 | §22.6 | Непрерывный single-session демо-прогон всех 8 свойств целевой картины (§23) ⚡ | 3 | 5 | S | Governance · метрики · безопасность |
| 24 | §17.14 | Sankey material→regime→property покрытия | 3 | 5 | M | Фронтенд и визуализация |
| 25 | §17.8 | Path search между двумя сущностями (Material↔Property) с подсветкой пути | 4 | 4 | M | Фронтенд и визуализация |
| 26 | §6.7 | Реальный GLiNER ML-NER (веса подключены, не только rule-fallback) | 5 | 3 | M | Извлечение и данные |
| 27 | §6.17 | Extraction eval-дашборд: precision/recall/F1 + span-IoU + cost/latency на golden-наборе | 4 | 4 | M | Извлечение и данные |
| 28 | §7.9 | Подключить полный движок kg_common.units в ingestion + показать registry-версию/метод в Evidence Inspector | 5 | 3 | M | Единицы и Entity Resolution |
| 29 | §7.7 | Флаги SUSPECT_VALUE / statistical_outlier / unit_scale_suspect в Evidence Inspector и очереди курирования | 4 | 4 | M | Единицы и Entity Resolution |
| 30 | §18.9 | RAGAS + DeepEval: faithfulness / hallucination / citation-groundedness | 5 | 3 | M | Governance · метрики · безопасность |
| 31 | §18.4 | Живой MLflow tracking server + UI (experiments extraction/retrieval/answer) | 4 | 4 | M | Governance · метрики · безопасность |
| 32 | §18.3 | Agent trace viewer: дерево node→tool→LLM + кнопка «open trace» в чате | 3 | 5 | M | Governance · метрики · безопасность |
| 33 | §11.8 | Community-cluster граф Mode C в UI (Reagraph/Sigma) | 3 | 5 | M | Поиск · GraphRAG · fusion |
| 34 | §13.11 | Похожие материалы (node similarity, Mode D) как фича | 4 | 4 | M | Агент и API |
| 35 | §13.11 | Детекция аномалий/выбросов измерений (Mode D) | 4 | 4 | M | Агент и API |
| 36 | §13.23 | Панель прозрачности и воспроизводимости прогона | 4 | 4 | M | Агент и API |
| 37 | §13.25 | Живое табло качества (golden + ragas/deepeval) | 5 | 3 | M | Агент и API |
| 38 | §14.9 | Bbox-подсветка evidence на изображении страницы | 4 | 4 | M | Агент и API |
| 39 | §25.6 | Включить LLM-извлечение фактов из прозы (llm_claims_from_text) | 5 | 3 | M | Пробелы · противоречия · absence |
| 40 | §16.6 | Замкнуть контур: резолюция противоречия из UI арбитра | 4 | 4 | M | Пробелы · противоречия · absence |
| 41 | §3.13 | «Похожие материалы/режимы» — vector-search по node embeddings в Entity Detail и Ask | 4 | 4 | M | Онтология · граф · инфра |
| 42 | §3.16 | Визуальные кодировки графа §5.2.3: полые узлы=нет данных, красные рёбра=противоречие, пунктир=inferred, замок=verified | 4 | 4 | M | Онтология · граф · инфра |
| 43 | §23.24 | KG Health Score 0–100 + data-quality scorecard в Admin | 4 | 4 | M | Домен и интеграции |
| 44 | §6.11 | PropertyGraphIndex + SchemaLLMPathExtractor (schema-constrained граф-экстракция) | 5 | 3 | L | Извлечение и данные |
| 45 | §18.5 | Prometheus + Grafana дашборды (latency p95, throughput, LLM-cost, curation) + алерты | 3 | 5 | L | Governance · метрики · безопасность |
| 46 | §17.7 | Единый warning panel: противоречия + low-confidence + gaps + unsupported claims ⚡ | 4 | 3 | S | Фронтенд и визуализация |
| 47 | §6.14 | Узел ExtractorRun (версии моделей/промптов/seed) со связью EXTRACTED_BY на каждый Evidence ⚡ | 4 | 3 | S | Извлечение и данные |
| 48 | §7.6 | Review-таск для неоднозначной единицы (% без wt/at) + gap missing_unit в матрице пробелов ⚡ | 4 | 3 | S | Единицы и Entity Resolution |
| 49 | §10.10 | Provenance-контекст агента в citations: owner/lab/version/freshness ⚡ | 4 | 3 | S | Governance · метрики · безопасность |
| 50 | §12.9 | Включить cross-encoder реранкер в живой retrieval-путь ⚡ | 5 | 2 | S | Поиск · GraphRAG · fusion |
| 51 | §4.7 | Подсветка совпадений (<em>-фрагменты) в результатах поиска ⚡ | 3 | 4 | S | Поиск · GraphRAG · fusion |
| 52 | §3.6 | Панель целостности графа: Cypher-валидатор «0 фактов без Evidence / без id / без schema_version» ⚡ | 4 | 3 | S | Онтология · граф · инфра |
| 53 | §17.7 | Tabs ответа [Summary][Experiments][Evidence][Graph][Gaps][Contradictions] | 4 | 3 | M | Фронтенд и визуализация |
| 54 | §17.8 | Graph query templates: параметрическая форма material_regime_property → граф | 4 | 3 | M | Фронтенд и визуализация |
| 55 | §17.8 | Lasso/box-выделение подграфа → «спросить агента о выделенном» | 3 | 4 | M | Фронтенд и визуализация |
| 56 | §17.13 | Evidence Inspector: parsed-объект, extractor/model version, reviewer decision, ссылка на ребро, prev/next | 4 | 3 | M | Фронтенд и визуализация |
| 57 | §5.7 | OCR-ветка для сканированных PDF (do_ocr, флаг ocr_used) | 4 | 3 | M | Извлечение и данные |
| 58 | §5.10 | Живой Dagster-оркестратор ingestion с пер-стадийным статусом job (parse→store→chunk→extract) | 3 | 4 | M | Извлечение и данные |
| 59 | §5.10 | Batch/bulk-ингест директории с агрегированным отчётом | 3 | 4 | M | Извлечение и данные |
| 60 | §5.7 | Извлечение figure-crops + связка caption→figure + Evidence из подписей рисунков | 3 | 4 | M | Извлечение и данные |
| 61 | §6.9 | Полный ExperimentExtract: различение Claim vs Finding + retry/repair невалидного JSON | 4 | 3 | M | Извлечение и данные |
| 62 | §5.8 | Fallback-цепочка парсеров Marker/Unstructured + ручная правка таблицы как новая версия артефакта | 4 | 3 | M | Извлечение и данные |
| 63 | §6.13 | Confidence-fusion в оркестраторе: boost при согласии rules+LLM, конфликт значений → review | 4 | 3 | M | Извлечение и данные |
| 64 | §8.12 | Golden ER-набор + eval F1 (pairwise/cluster) + CI-гейт регрессии | 4 | 3 | M | Единицы и Entity Resolution |
| 65 | §8.8 | Апгрейд resolve_mention до каскада alias→fulltext→vector(entity_embedding_index)→Splink | 4 | 3 | M | Единицы и Entity Resolution |
| 66 | §8.9 | Undo merge + обратимость (merged_from) в UI курирования | 3 | 4 | M | Единицы и Entity Resolution |
| 67 | §10.7 | Source Catalog в Admin с интерактивным lineage-графом (ELK/dagre) | 3 | 4 | M | Governance · метрики · безопасность |
| 68 | §10.5 | Реальная эмиссия pipeline-lineage из Dagster (end-to-end inputs→outputs) | 4 | 3 | M | Governance · метрики · безопасность |
| 69 | §18.11 | Eval regression-gate + Markdown/HTML отчёт с diff к прошлому прогону | 4 | 3 | M | Governance · метрики · безопасность |
| 70 | §18.6 | Golden dataset 50–100 вопросов по 6 категориям (ru/en) + loader/validator квот | 5 | 2 | M | Governance · метрики · безопасность |
| 71 | §19.10 | LangGraph Studio: граф scientific_agent + live node-trace | 3 | 4 | M | Governance · метрики · безопасность |
| 72 | §22.7 | Сводный CI-gate definition-of-done → GREEN (phase-checks + eval + e2e) | 4 | 3 | M | Governance · метрики · безопасность |
| 73 | §4.7 | Фасетный поисковый экран: OpenSearch aggregations + фильтр-чипы | 3 | 4 | M | Поиск · GraphRAG · fusion |
| 74 | §12.4 | Объяснимость ранжирования: разложение component_scores в UI | 3 | 4 | M | Поиск · GraphRAG · fusion |
| 75 | §4.7 | Числовые range-фасеты: гистограммы temperature_c/time_h + слайдеры | 3 | 4 | M | Поиск · GraphRAG · fusion |
| 76 | §4.11 | Дашборд retrieval-eval: Recall@10/MRR/nDCG hybrid vs bm25/dense, rerank on/off | 4 | 3 | M | Поиск · GraphRAG · fusion |
| 77 | §13.20 | Кросс-сессионная долговременная память (персонализация) | 3 | 4 | M | Агент и API |
| 78 | §14.4 | «Спросить агента о выделенном подграфе» (lasso) | 3 | 4 | M | Агент и API |
| 79 | §14.6 | Визуальный diff графа до/после курирования | 3 | 4 | M | Агент и API |
| 80 | §13.15 | Систематическое обнаружение противоречий для арбитра | 4 | 3 | M | Агент и API |
| 81 | §15.8 | Verifier блокирует неподкреплённые числа + scan_gaps как tool | 4 | 3 | M | Пробелы · противоречия · absence |
| 82 | §16.5 | Авто-генерация review-задач по 6 правилам | 4 | 3 | M | Пробелы · противоречия · absence |
| 83 | §25.16 | Extraction-recall eval по модальностям + gold-набор | 4 | 3 | M | Пробелы · противоречия · absence |
| 84 | §15.5 | Дашборд покрытия: timeline + пробелы по лабам/командам | 3 | 4 | M | Пробелы · противоречия · absence |
| 85 | §16.10 | Graph diff «до/после курирования» в UI | 3 | 4 | M | Пробелы · противоречия · absence |
| 86 | §15.4 | Арбитр: likely-correct по качеству источника + пересечение доверит. интервалов | 3 | 4 | M | Пробелы · противоречия · absence |
| 87 | §9.6 | new_document_sensor: файл в kg-raw → авто-запуск full_ingestion_job → граф растёт вживую | 3 | 4 | M | Онтология · граф · инфра |
| 88 | §3.7 | Версионирование фактов + «никогда не перезаписывать reviewed» + машина времени факта в Entity Detail | 4 | 3 | M | Онтология · граф · инфра |
| 89 | §23.25 | Confidence calibration: reliability-диаграмма, ECE, честные UI-метки уверенности | 4 | 3 | M | Домен и интеграции |
| 90 | §23.22 | Expert feedback loop: кнопки useful/wrong-number/missing-evidence → regression-тест | 4 | 3 | M | Домен и интеграции |
| 91 | §23.17 | Устойчивость к ru/«грязным» документам: детект языка + ru→en cross-lingual поиск | 4 | 3 | M | Домен и интеграции |
| 92 | §23.8 | i18n ru/en фронтенда с переключателем локали (синхрон с языком ответов агента) | 3 | 4 | M | Домен и интеграции |
| 93 | §17.15 | Pipeline/agent DAG на React Flow (source→parse→…→index + LangGraph nodes) со статусами | 3 | 4 | L | Фронтенд и визуализация |
| 94 | §6.8 | MatSciBERT/MatEntityRecognition domain-NER + fusion с GLiNER | 4 | 3 | L | Извлечение и данные |
| 95 | §9.2 | Полный asset-граф Dagster в Dagit (12+ ассетов) — сквозная материализация seed-документа end-to-end | 3 | 4 | L | Онтология · граф · инфра |
| 96 | §23.32 | Collaboration: комментарии/mentions/shared investigation + notification center | 3 | 4 | L | Домен и интеграции |
| 97 | §17.8 | Легенда графа с расшифровкой 8 кодировок и toggle категорий | 3 | 3 | S | Фронтенд и визуализация |
| 98 | §17.11 | Timeline сущности (появление/эксперименты по времени) на ECharts | 3 | 3 | S | Фронтенд и визуализация |
| 99 | §8.13 | ER-метрики в /admin/metrics (auto_merge/review_needed/blocked_overwrite/model_version) | 3 | 3 | S | Единицы и Entity Resolution |
| 100 | §8.6 | Эмиссия new_property_term (schema_change) в очередь ревью при неизвестном свойстве | 3 | 3 | S | Единицы и Entity Resolution |
