# LangChain и LangGraph (Python): исчерпывающее руководство

> Практический справочник по построению LLM-приложений и агентов на **LangChain** и **LangGraph** (Python).
> Все примеры и имена API сверены с живой документацией и актуальными версиями пакетов на момент составления
> (**LangChain 1.x / langchain-core 1.x, LangGraph 1.x**; экосистема 1.0 вышла 22.10.2025). Пояснения — на русском,
> код и имена API — на английском, как в реальном коде.

## Что это и зачем

- **LangChain** — библиотека компонентов для работы с LLM: единый интерфейс к моделям чата, промпт-шаблоны,
  инструменты (tools), структурированный вывод, ретриверы и RAG, а также язык композиции **LCEL** (`Runnable`),
  которым эти компоненты собираются в цепочки.
- **LangGraph** — низкоуровневый фреймворк для **stateful**-приложений и **агентов** в виде графа: состояние с
  reducer'ами, узлы и рёбра, циклы и ветвление, персистентность (checkpointers), стриминг, human-in-the-loop,
  подграфы и мультиагентные архитектуры. В LangChain 1.x именно LangGraph лежит в основе агентов
  (`create_agent` / `create_react_agent`).

Практическое правило: **простые линейные пайплайны** (prompt → model → parser) удобно писать на **LCEL**; как только
появляются **циклы, ветвление, память между шагами, ожидание человека или несколько агентов** — переходите на
**LangGraph**.

## Как читать

Разделы 1–8 — это LangChain (основы, модели, промпты, LCEL, tools, RAG, память).
Разделы 9–19 — это LangGraph (граф состояния, узлы/рёбра, стриминг, персистентность, **подграфы**,
human-in-the-loop, готовые и мультиагентные архитектуры, деплой). Каждый раздел самодостаточен и содержит рабочие
примеры кода.

## Быстрый старт (установка)

```bash
# базовый набор: LangChain (тянет langchain-core и langgraph) + провайдер
pip install -U langchain "langchain[anthropic]" langgraph
# либо через uv
uv add langchain "langchain[anthropic]" langgraph

# ключи провайдеров и (опционально) трейсинг LangSmith
export ANTHROPIC_API_KEY=...      # или OPENAI_API_KEY=...
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=...
```

```python
from langchain.chat_models import init_chat_model

model = init_chat_model("claude-sonnet-4-6", model_provider="anthropic")
print(model.invoke("Привет! Кратко: что такое LangGraph?").content)
```

## Оглавление

1. [1. Обзор экосистемы и установка](#1-обзор-экосистемы-и-установка)
2. [2. Модели чата и сообщения](#2-модели-чата-и-сообщения)
3. [3. Промпты (Prompt Templates)](#3-промпты-prompt-templates)
4. [4. LCEL: Runnable и композиция цепочек](#4-lcel-runnable-и-композиция-цепочек)
5. [5. Структурированный вывод и парсеры](#5-структурированный-вывод-и-парсеры)
6. [6. Инструменты (Tools) и tool calling](#6-инструменты-tools-и-tool-calling)
7. [7. Retrieval и RAG](#7-retrieval-и-rag)
8. [8. Память и история сообщений](#8-память-и-история-сообщений)
9. [9. LangGraph: введение, StateGraph, базовый пример](#9-langgraph-введение-stategraph-базовый-пример)
10. [10. Состояние графа: схемы, Annotated, reducers](#10-состояние-графа-схемы-annotated-reducers)
11. [11. Узлы, рёбра и маршрутизация](#11-узлы-рёбра-и-маршрутизация)
12. [12. Запуск и стриминг графа](#12-запуск-и-стриминг-графа)
13. [13. Персистентность и чекпоинтеры](#13-персистентность-и-чекпоинтеры)
14. [14. Подграфы (Subgraphs)](#14-подграфы-subgraphs)
15. [15. Human-in-the-loop (человек в цикле)](#15-human-in-the-loop-человек-в-цикле)
16. [16. Готовые агенты: create_react_agent и ToolNode](#16-готовые-агенты-create_react_agent-и-toolnode)
17. [17. Мультиагентные архитектуры](#17-мультиагентные-архитектуры)
18. [18. Долговременная память: Store (BaseStore)](#18-долговременная-память-store-basestore)
19. [19. Деплой, LangSmith, отладка и лучшие практики](#19-деплой-langsmith-отладка-и-лучшие-практики)

---


## 1. Обзор экосистемы и установка

### 1.1. LangChain и LangGraph: назначение и как они соотносятся

Экосистема делится на два взаимодополняющих слоя.

- **LangChain** — библиотека для работы с языковыми моделями: единый интерфейс к чат-моделям, эмбеддингам, векторным хранилищам, инструментам (tools), парсерам вывода и промптам. Начиная с версии 1.0 центральным высокоуровневым API стал агент, создаваемый через `create_agent` (архитектура ReAct/tool-calling с поддержкой middleware). LangChain отвечает на вопрос «как единообразно вызывать разные LLM и собирать из них цепочки».

- **LangGraph** — низкоуровневый фреймворк оркестрации для построения **stateful**-приложений в виде графа. Он даёт явный контроль над состоянием, ветвлениями, циклами, персистентностью (checkpointers), human-in-the-loop, стримингом и восстановлением после сбоев. LangGraph отвечает на вопрос «как выстроить сложный, долгоживущий, управляемый рабочий процесс из узлов и рёбер».

Соотношение простое: **`create_agent` из LangChain построен поверх LangGraph** (пакет `langchain` в v1 напрямую зависит от `langgraph` и тянет его автоматически). Для типовых агентов достаточно LangChain; когда нужна нестандартная топология (несколько агентов, сложные условные переходы, ручные точки прерывания, точный контроль над состоянием) — вы спускаетесь на уровень LangGraph. Оба проекта достигли стабильных мажорных релизов 1.0 22 октября 2025 года и придерживаются семантического версионирования (никаких ломающих изменений внутри линейки 1.x до 2.0).

> **Когда что использовать.** Прототип, RAG, простой tool-calling агент — LangChain (`create_agent`, `init_chat_model`). Продуктовый multi-agent, воркфлоу с ветвлением/циклами, паузами на подтверждение оператора и долговременной памятью — LangGraph. На практике их обычно используют вместе.

### 1.2. Состав пакетов

Экосистема намеренно разбита на мелкие пакеты, чтобы можно было ставить только нужное и не тянуть тяжёлые зависимости.

| Пакет | Назначение |
|---|---|
| `langchain-core` | Базовые абстракции и интерфейсы: `Runnable`, `BaseChatModel`, сообщения, `PromptTemplate`, `OutputParser`, content blocks. Минимум зависимостей — от него зависят все остальные пакеты. |
| `langchain` | Высокоуровневый слой: `create_agent`, `init_chat_model`, middleware, стандартные вспомогательные конструкции. Зависит от `langchain-core` и `langgraph`. |
| `langchain-openai`, `langchain-anthropic`, `langchain-google-genai`, `langchain-aws`, … | Провайдерские интеграции. Каждый провайдер вынесен в отдельный пакет с собственными зависимостями (SDK провайдера). |
| `langchain-community` | Обширный набор community-интеграций (сторонние загрузчики документов, векторные БД, инструменты). |
| `langchain-classic` | «Легаси»-функциональность, вынесенная из `langchain` в 1.0: устаревшие цепочки (`LLMChain`, `ConversationChain`), старые ретриверы, indexing API, модуль `hub`, ре-экспорты из `langchain-community`. Нужен только при миграции старого кода. |
| `langgraph` | Ядро графового фреймворка: `StateGraph`, компиляция, исполнение, стриминг. |
| `langgraph-prebuilt` | Готовые компоненты (например, `ToolNode`, `create_react_agent`); тянется как зависимость `langgraph`. |
| `langgraph-checkpoint` | Базовый интерфейс checkpointer'ов + in-memory реализация (`InMemorySaver`, импортируется из `langgraph.checkpoint.memory`). |
| `langgraph-checkpoint-sqlite`, `langgraph-checkpoint-postgres` | Персистентные бэкенды для состояния графа (SQLite / Postgres). Ставятся отдельно. |
| `langsmith` | SDK для трассировки, оценки и мониторинга (LangSmith). Приходит автоматически как транзитивная зависимость `langchain-core`, то есть ставится вместе с `langchain`. |
| `langgraph-cli` | CLI для локального запуска и деплоя приложений через LangGraph Platform (`langgraph dev`, `langgraph build`). |
| `langgraph-sdk` | Клиент для программного обращения к развёрнутому LangGraph-серверу. |

#### Актуальные версии (по состоянию на середину 2026)

- `langchain` — линейка **1.x** (например, 1.3.x).
- `langchain-core` — линейка **1.x** (например, 1.4.x).
- `langgraph` — линейка **1.x** (например, 1.2.x).
- Требуется **Python 3.10+** (поддерживается вплоть до 3.13/3.14).

Точные номера уточняйте на PyPI перед установкой — минорные версии выходят часто. Обратите внимание: у вспомогательных пакетов нумерация независимая (`langgraph-prebuilt` — в линейке 1.x, а `langgraph-checkpoint` — в своей, на середину 2026 это 4.x), поэтому не ждите одинаковых номеров. Гарантия отсутствия ломающих изменений действует внутри мажорной линейки 1.x.

### 1.3. Установка

Ставьте не «всё сразу», а ядро плюс нужных провайдеров. Провайдерские зависимости удобно подтягивать через **extras** пакета `langchain`.

#### Через pip

```bash
# Ядро + агентный слой (langchain уже тянет langchain-core и langgraph)
pip install -U langchain

# Провайдеры через extras (ставят соответствующий langchain-<provider>)
pip install -U "langchain[openai]"       # -> langchain-openai
pip install -U "langchain[anthropic]"    # -> langchain-anthropic
pip install -U "langchain[google-genai]" # -> langchain-google-genai

# Либо провайдерский пакет напрямую
pip install -U langchain-anthropic

# LangGraph и персистентность (langgraph уже приходит с langchain;
# ставьте явно, чтобы зафиксировать/поднять версию или работать без langchain)
pip install -U langgraph
pip install -U langgraph-checkpoint-postgres   # опционально, для Postgres
pip install -U "langgraph-cli[inmem]"          # опционально, локальный dev-сервер
```

#### Через uv (быстрый современный менеджер)

```bash
uv add "langchain[anthropic]" langgraph
# или в разовом окружении:
uv pip install -U langchain langchain-anthropic langgraph
```

> **Частая ошибка.** `ModuleNotFoundError: No module named 'langchain_openai'` означает, что установлено ядро, но не поставлен провайдерский пакет. Решение — доставить `langchain[openai]` или `langchain-openai`. Не пытайтесь импортировать чат-модели «из воздуха»: интеграции живут в отдельных пакетах.

> **Про версии.** `langchain` (v1) уже зависит от совместимого `langgraph`, поэтому обычно достаточно поставить `langchain`. Держите `langgraph` и его спутники (`langgraph-prebuilt`, `langgraph-checkpoint`) во взаимно совместимых версиях — при этом их номера не совпадают из-за независимой нумерации. Рассинхронизация несовместимых версий — источник ошибок вида `ImportError`/`cannot import name ...` при обновлении. При проблемах фиксируйте версии явно (`langgraph==1.x.y`).

### 1.4. API-ключи и переменные окружения

Провайдерские пакеты читают ключи из переменных окружения. Ключи **никогда** не хардкодьте в коде — используйте окружение или менеджер секретов; локально удобен файл `.env` с `python-dotenv`.

| Переменная | Назначение |
|---|---|
| `OPENAI_API_KEY` | Ключ OpenAI (для `langchain-openai`). |
| `ANTHROPIC_API_KEY` | Ключ Anthropic / Claude (для `langchain-anthropic`). |
| `GOOGLE_API_KEY` | Ключ Google Gemini (для `langchain-google-genai`). |
| `LANGSMITH_TRACING` | `"true"` — включить трассировку в LangSmith. |
| `LANGSMITH_API_KEY` | Ключ LangSmith. |
| `LANGSMITH_PROJECT` | Проект, в который пишутся трейсы (если не задан — `default`). |
| `LANGSMITH_ENDPOINT` | URL региона (например, `https://eu.api.smith.langchain.com` для EU). |

```bash
# .env  (файл переменных окружения, не Python-код)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=my-project
```

```python
from dotenv import load_dotenv

load_dotenv()  # подхватывает .env в os.environ до создания моделей
```

> **Про устаревшие имена.** Ранее использовались переменные с префиксом `LANGCHAIN_*` (`LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`, `LANGCHAIN_ENDPOINT`). Они всё ещё распознаются ради обратной совместимости, но в новом коде предпочтителен префикс `LANGSMITH_*`.

### 1.5. `init_chat_model` — универсальная инициализация модели

`init_chat_model` — рекомендованный способ создать чат-модель, не привязываясь жёстко к классу конкретного провайдера. Функция принимает имя модели, определяет провайдера (или вы задаёте его явно) и возвращает готовый объект `BaseChatModel`.

```python
from langchain.chat_models import init_chat_model

# Провайдер выводится автоматически по имени модели
model = init_chat_model("gpt-4o")

# Явно через префикс "{provider}:{model}" — самый надёжный вариант
model = init_chat_model("anthropic:claude-sonnet-4-5")

# Или отдельным аргументом model_provider
model = init_chat_model("claude-sonnet-4-5", model_provider="anthropic")

response = model.invoke("Объясни, что такое LangGraph, в двух предложениях.")
print(response.content)
```

> **Про имена моделей.** Идентификаторы вроде `gpt-4o` и `claude-sonnet-4-5` передаются провайдерскому SDK как есть, поэтому новые модели работают сразу, без обновления LangChain. Актуальный идентификатор всегда сверяйте с документацией провайдера.

#### Ключевые аргументы

| Аргумент | Описание |
|---|---|
| `model` | Идентификатор модели (обязательный), опционально с префиксом провайдера. |
| `model_provider` | Провайдер (`openai`, `anthropic`, `google_genai`, `bedrock`, `bedrock_converse`, …), если он не задан префиксом. |
| `temperature`, `max_tokens`, `timeout`, `max_retries` | Стандартные параметры генерации/устойчивости, пробрасываются в модель. |
| `configurable_fields` | Делает часть параметров переключаемыми во время выполнения (см. ниже). |
| `config_prefix` | Префикс для конфигурируемых полей при нескольких моделях в одном пайплайне. |

**Что возвращается:** экземпляр чат-модели, поддерживающий единый Runnable-интерфейс (`.invoke`, `.stream`, `.batch`, `.bind_tools`, `.with_structured_output`). Это позволяет менять провайдера, не переписывая остальной код.

#### Конфигурируемая модель (выбор провайдера в рантайме)

```python
from langchain.chat_models import init_chat_model

# Модель, у которой поля можно переопределять во время вызова
configurable = init_chat_model(
    "openai:gpt-4o",
    configurable_fields=("model", "model_provider", "temperature"),
)

# Тот же объект — разные модели по конфигу
answer_openai = configurable.invoke(
    "Привет!",
    config={"configurable": {"model": "openai:gpt-4o-mini"}},
)
answer_anthropic = configurable.invoke(
    "Привет!",
    config={"configurable": {"model": "anthropic:claude-sonnet-4-5"}},
)
```

> **Требование.** Провайдерский пакет должен быть установлен: для `init_chat_model("openai:...")` нужен `langchain-openai`, для `anthropic:...` — `langchain-anthropic`. Иначе — `ImportError` в момент инициализации.

> **Устаревший приём.** Прямое создание объектов вида `ChatOpenAI(...)` / `ChatAnthropic(...)` по-прежнему работает и уместно, когда нужны специфичные для провайдера параметры. Но для переносимого кода предпочтительнее `init_chat_model`.

### 1.6. Краткое введение в LangSmith

**LangSmith** — платформа наблюдаемости (observability) и оценки для LLM-приложений: трассировка каждого вызова модели/инструмента, отладка агентов, датасеты и автоматические оценки (evaluators), мониторинг в проде. Работает как с LangChain/LangGraph, так и с «голыми» вызовами SDK.

Включается декларативно, без изменения кода приложения — достаточно переменных окружения:

```python
import os
from langchain.chat_models import init_chat_model

os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_API_KEY"] = "lsv2_..."
os.environ["LANGSMITH_PROJECT"] = "quickstart"

model = init_chat_model("openai:gpt-4o")
model.invoke("Проверка трассировки")  # вызов автоматически появится в LangSmith
```

Установка SDK (обычно уже приходит с `langchain` через `langchain-core`):

```bash
pip install -U langsmith
```

После этого трейсы доступны в веб-интерфейсе LangSmith. Для команд без облака есть self-hosted вариант, а для регионов вне США задаётся `LANGSMITH_ENDPOINT`.

### 1.7. Итоговая шпаргалка «когда что»

- **Нужен единый доступ к разным LLM** → `langchain` + `init_chat_model` + провайдерский пакет.
- **Простой агент с инструментами / RAG** → `create_agent` из `langchain` (`from langchain.agents import create_agent`).
- **Сложный воркфлоу, состояние, циклы, human-in-the-loop, память** → `langgraph` (+ checkpointer).
- **Наблюдаемость, отладка, оценка качества** → `langsmith` (переменные `LANGSMITH_*`).
- **Локальный запуск/деплой графа как сервиса** → `langgraph-cli` / LangGraph Platform.
- **Старый код на v0.x** → `langchain-classic` для миграции, затем перевод на v1-API.


---


## 2. Модели чата и сообщения

Модель чата (chat model) — центральный компонент LangChain: она принимает на вход список сообщений и возвращает сообщение ассистента. Все модели чата наследуются от `BaseChatModel` и реализуют интерфейс `Runnable`, поэтому у них единый набор методов (`invoke`, `stream`, `batch` и их async-аналоги), они одинаково встраиваются в цепочки (LCEL) и в графы LangGraph.

### 2.1. BaseChatModel и провайдеры

Конкретные модели живут в отдельных пакетах-интеграциях. Устанавливать и импортировать нужно именно провайдерский пакет:

```python
# pip install langchain-openai langchain-anthropic
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

llm_openai = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_anthropic = ChatAnthropic(model="claude-sonnet-4-6", max_tokens=1024)
```

Ключи API берутся из переменных окружения (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) либо передаются явно через `api_key=...`.

> Устаревшее: импорт `from langchain.chat_models import ChatOpenAI` и классы из `langchain_community.chat_models` — deprecated. Используйте отдельные пакеты `langchain_openai`, `langchain_anthropic` и т. д. Также устарели методы `predict`, `predict_messages` и вызов модели как функции (`__call__`) — вместо них применяйте `invoke`.

### 2.2. init_chat_model — универсальная инициализация

`init_chat_model` создаёт модель по строковому идентификатору, не привязывая код к конкретному классу. Это удобно, когда провайдер выбирается конфигурацией или флагом.

```python
from langchain.chat_models import init_chat_model
# init_chat_model живёт в пакете `langchain` (модуль langchain.chat_models.base).
# В langchain_core его нет — там только базовые классы вроде BaseChatModel.

# Явный провайдер через префикс "<provider>:<model>"
model = init_chat_model("openai:gpt-4o-mini", temperature=0)

# Провайдер отдельным аргументом
model = init_chat_model("claude-sonnet-4-6", model_provider="anthropic", max_tokens=1024)

model.invoke("Привет!")
```

Сигнатура (упрощённо):

```python
init_chat_model(
    model: str | None = None,
    *,
    model_provider: str | None = None,
    configurable_fields: Literal["any"] | list[str] | tuple[str, ...] | None = None,
    config_prefix: str | None = None,
    **kwargs,  # temperature, max_tokens, timeout, max_retries, base_url, ...
) -> BaseChatModel
```

Поддерживаемые префиксы провайдеров: `openai`, `anthropic`, `google_vertexai`/`google_genai`, `bedrock`/`bedrock_converse`, `azure_openai`, `cohere`, `mistralai`, `fireworks`, `groq`, `deepseek`, `xai`, `ollama`, `huggingface` и др. Если префикс не указан, LangChain пытается угадать провайдера по имени модели (`gpt-...` → OpenAI, `claude-...` → Anthropic, `gemini-...` → Google).

#### Конфигурируемые модели

Если задать `configurable_fields`, функция возвращает не саму модель, а «отложенную» обёртку — конкретные параметры выбираются в момент вызова через `config`:

```python
configurable = init_chat_model(
    temperature=0,
    configurable_fields=("model", "model_provider"),
)

configurable.invoke(
    "Объясни рекурсию",
    config={"configurable": {"model": "openai:gpt-4o-mini"}},
)
```

Ключи в `config["configurable"]` совпадают с именами полей; если задать `config_prefix="first"`, они станут `first_model`, `first_model_provider` и т. д. Соответствующий провайдерский пакет (`langchain-openai`, `langchain-anthropic`, ...) всё равно должен быть установлен.

### 2.3. Типы сообщений

Сообщения описывают диалог. Базовые классы находятся в `langchain_core.messages` (в новых версиях доступен также реэкспорт `langchain.messages`):

```python
from langchain_core.messages import (
    SystemMessage, HumanMessage, AIMessage, ToolMessage, AIMessageChunk,
)
```

| Класс | Роль | Назначение |
|-------|------|------------|
| `SystemMessage` | `system` | Инструкции и контекст поведения модели (обычно первое сообщение). |
| `HumanMessage` | `human`/`user` | Ввод пользователя. |
| `AIMessage` | `ai`/`assistant` | Ответ модели: текст, `tool_calls`, метаданные. |
| `ToolMessage` | `tool` | Результат выполнения инструмента; обязателен `tool_call_id`. |

```python
messages = [
    SystemMessage("Ты — лаконичный ассистент."),
    HumanMessage("Столица Франции?"),
]
ai_msg = model.invoke(messages)   # -> AIMessage
print(ai_msg.content)             # "Париж"
```

`ToolMessage` возвращает в модель результат вызванного инструмента и связывается с ним по идентификатору. Значение `tool_call_id` должно совпадать с `id` соответствующего вызова из `AIMessage.tool_calls`:

```python
tool_msg = ToolMessage(content="Sunny, 22°C", tool_call_id="call_123", name="get_weather")
```

#### Кортежи и словари вместо классов

Вместо объектов можно передавать кортежи `(role, content)` или словари в формате OpenAI — это короче для простых случаев:

```python
# Кортежи (role, content)
model.invoke([
    ("system", "Отвечай на русском."),
    ("human", "Что такое HTTP?"),
])

# Словари OpenAI-формата
model.invoke([
    {"role": "system", "content": "Отвечай кратко."},
    {"role": "user", "content": "2+2?"},
])

# Одна строка = один HumanMessage
model.invoke("Просто вопрос без системного промпта")
```

Допустимые роли: `system`, `human`/`user`, `ai`/`assistant`, `tool`. Классы-объекты предпочтительны, когда нужны tool calls, мультимодальность или доступ к метаданным.

### 2.4. invoke / stream / batch и их async-варианты

Все модели реализуют единый интерфейс `Runnable`:

| Метод | Что делает | Возвращает |
|-------|-----------|-----------|
| `invoke(input)` | Один синхронный вызов | `AIMessage` |
| `stream(input)` | Потоковая генерация по токенам | генератор `AIMessageChunk` |
| `batch(inputs)` | Пакет входов параллельно | `list[AIMessage]` |
| `ainvoke` / `astream` / `abatch` | Async-аналоги | те же типы (через `await` / `async for`) |

```python
# invoke
ai = model.invoke("Назови три цвета")

# stream — чанки складываются оператором "+"
full = None
for chunk in model.stream("Расскажи короткую историю"):
    print(chunk.content, end="", flush=True)
    full = chunk if full is None else full + chunk   # аккумулируем AIMessageChunk

# batch — параллельная обработка; степень параллелизма через config
answers = model.batch(
    ["Вопрос 1", "Вопрос 2", "Вопрос 3"],
    config={"max_concurrency": 5},
)
```

Async-версии нужны в веб-серверах (FastAPI) и в async-узлах LangGraph:

```python
import asyncio

async def main():
    ai = await model.ainvoke("Привет")
    async for chunk in model.astream("Считай до пяти"):
        print(chunk.content, end="")
    results = await model.abatch(["a", "b"])

asyncio.run(main())
```

Дополнительно доступен `astream_events` (актуальна schema `v2`; `v1` в новых версиях удалена) — детальный поток событий по всей цепочке/графу (полезен для UI и трассировки).

### 2.5. Ключевые параметры моделей

Задаются в конструкторе или в `init_chat_model`, часть можно переопределить на лету через `.bind(...)`:

| Параметр | Смысл | Примечание |
|----------|-------|-----------|
| `temperature` | Случайность/креативность (0 — детерминированнее) | Некоторые reasoning-модели OpenAI (o1/o3, gpt-5) поддерживают только значение по умолчанию. |
| `max_tokens` | Максимум токенов в ответе | У Anthropic есть значение по умолчанию (1024); задавайте явно под свою задачу. |
| `timeout` | Таймаут запроса, сек | Защита от зависаний. |
| `max_retries` | Число повторов при ошибках сети/ratelimit | У `ChatOpenAI`/`ChatAnthropic` по умолчанию 2. |
| `top_p`, `stop`, `seed` | Стандартные параметры сэмплирования | Поддержка зависит от провайдера. |
| `model_kwargs` | Провайдер-специфичные поля | Передаются «как есть». |

```python
model = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.2,
    max_tokens=512,
    timeout=30,
    max_retries=3,
)

# Разовое переопределение параметров для конкретного пайплайна
strict = model.bind(temperature=0, stop=["\n\n"])
```

### 2.6. usage_metadata и response_metadata

У каждого `AIMessage` есть два поля с метаданными.

`usage_metadata` — стандартизированный по провайдерам подсчёт токенов:

```python
ai = model.invoke("Привет!")
print(ai.usage_metadata)
# {'input_tokens': 8, 'output_tokens': 12, 'total_tokens': 20,
#  'input_token_details': {'cache_read': 0}, 'output_token_details': {'reasoning': 0}}
```

`response_metadata` — «сырые» данные провайдера (не унифицированы):

```python
print(ai.response_metadata)
# OpenAI:    {'token_usage': {...}, 'model_name': ..., 'system_fingerprint': ..., 'finish_reason': 'stop', 'logprobs': None}
# Anthropic: {'id': ..., 'model': ..., 'stop_reason': 'end_turn', 'stop_sequence': None, 'usage': {...}}
```

При стриминге токены складываются вместе с чанками; для OpenAI usage приходит только если явно попросить:

```python
gathered = None
for chunk in ChatOpenAI(model="gpt-4o-mini").stream("Привет", stream_usage=True):
    gathered = chunk if gathered is None else gathered + chunk
print(gathered.usage_metadata)   # суммарные токены за стрим
```

Для сквозного подсчёта по нескольким вызовам/моделям есть callback-менеджер `get_usage_metadata_callback` (либо обработчик `UsageMetadataCallbackHandler`):

```python
from langchain_core.callbacks import get_usage_metadata_callback

with get_usage_metadata_callback() as cb:
    model.invoke("раз")
    model.invoke("два")
print(cb.usage_metadata)   # агрегат по всем вызовам внутри контекста
```

### 2.7. Мультимодальный ввод (кратко)

Мультимодальный контент передаётся списком content-блоков внутри `HumanMessage`. Изображение/файл можно задать URL, base64 или (у некоторых провайдеров) идентификатором:

```python
from langchain_core.messages import HumanMessage

# URL-вариант: type="image" и ключ "url"
msg = HumanMessage(content=[
    {"type": "text", "text": "Что изображено на картинке?"},
    {"type": "image", "url": "https://example.com/cat.jpg"},
])
model.invoke([msg])

# base64-вариант: ключ "base64" + обязательный "mime_type"
msg_b64 = HumanMessage(content=[
    {"type": "text", "text": "Опиши изображение"},
    {"type": "image", "base64": "<...>", "mime_type": "image/png"},
])
model.invoke([msg_b64])
```

> Формат стандартных content-блоков обновился: в актуальных версиях используется `{"type": "image", "url": ...}` и `{"type": "image", "base64": ..., "mime_type": ...}`. Старый вид из langchain-core 0.3 с полями `source_type` и `data` (`{"type": "image", "source_type": "base64", "data": ...}`) считается устаревшим.

Поддерживаются также блоки `file` (PDF), `audio`, `video` — доступность зависит от конкретной модели. Проверяйте, что у выбранного провайдера есть vision/audio-возможности.

### 2.8. Кэширование ответов (кратко)

Кэш экономит вызовы и деньги: одинаковый запрос к модели возвращается из хранилища. Включается глобально через `set_llm_cache`:

```python
from langchain_core.globals import set_llm_cache
from langchain_core.caches import InMemoryCache

set_llm_cache(InMemoryCache())     # кэш в памяти процесса
model.invoke("Один и тот же запрос")  # второй такой же вызов — из кэша
```

Персистентный кэш в SQLite:

```python
# pip install langchain-community
from langchain_community.cache import SQLiteCache
set_llm_cache(SQLiteCache(database_path=".langchain.db"))
```

Кэшем можно управлять на уровне конкретной модели параметром `cache`: `cache=True` использует глобальный кэш, `cache=False` отключает его для этой модели, `cache=<BaseCache>` подставляет своё хранилище. Важно: кэш срабатывает по точному совпадению входа и параметров, а при стриминге экономия ограничена (обычно кэшируется финальный результат, а не потоковая выдача). Для «похожих» запросов используют семантический кэш (например, на векторном хранилище) — это отдельная тема.


---


## 3. Промпты (Prompt Templates)

Промпт-шаблоны — это объекты, которые превращают входные переменные в готовый текст (или в список сообщений), пригодный для передачи в модель. Они являются полноценными `Runnable`, то есть их можно вызывать через `.invoke()` и комбинировать с моделью через оператор `|` (LCEL). Все базовые классы живут в пакете `langchain_core.prompts`. В новом коде импортируйте именно из `langchain_core.prompts` — это канонический путь. Исторически те же имена реэкспортировались из `langchain.prompts`; этот путь работал в LangChain 0.x ради обратной совместимости, но в LangChain 1.0 пакет `langchain` был существенно урезан, а подобные legacy-реэкспорты вынесены в отдельный пакет `langchain_classic`, поэтому полагаться на `langchain.prompts` больше не стоит.

```python
from langchain_core.prompts import (
    PromptTemplate,
    ChatPromptTemplate,
    MessagesPlaceholder,
    FewShotPromptTemplate,
    FewShotChatMessagePromptTemplate,
)
```

### 3.1. PromptTemplate (строковый шаблон)

`PromptTemplate` формирует одну строку. По умолчанию используется синтаксис f-string (`{variable}`).

```python
from langchain_core.prompts import PromptTemplate

prompt = PromptTemplate.from_template(
    "Переведи фразу на {language}: {text}"
)

# Синхронная подстановка -> строка
print(prompt.format(language="английский", text="Привет, мир"))
# 'Переведи фразу на английский: Привет, мир'

# Как Runnable -> объект PromptValue (а не строка!)
value = prompt.invoke({"language": "немецкий", "text": "Доброе утро"})
print(value.to_string())
```

`from_template()` автоматически извлекает имена переменных из шаблона, поэтому явно перечислять `input_variables` не нужно. Полная форма конструктора полезна, когда вы хотите переопределить формат или задать переменные вручную:

```python
prompt = PromptTemplate(
    template="Ответь на {question}",
    input_variables=["question"],
    template_format="f-string",  # также: "mustache", "jinja2"
)
```

Допустимые значения `template_format` — `"f-string"` (по умолчанию), `"mustache"` и `"jinja2"`. Для `jinja2` требуется установленный пакет `jinja2`, и его стоит применять только к доверенным шаблонам (движок может исполнять произвольные выражения).

Ключевое различие: `.format(...)` возвращает готовую строку, а `.invoke(...)` возвращает объект `StringPromptValue` с методами `.to_string()` и `.to_messages()`. Внутри LCEL всегда работает `.invoke()`, поэтому модель получает `PromptValue`, а не сырую строку — chat-модели корректно интерпретируют его как одно сообщение пользователя (`StringPromptValue.to_messages()` возвращает единственный `HumanMessage`).

**Типичные ошибки.** Если в шаблоне встречаются фигурные скобки, не относящиеся к переменным (например, пример JSON), их нужно экранировать удвоением: `{{` и `}}`. Иначе f-string-парсер попытается трактовать `{...}` как переменную и выбросит `KeyError`. Для промптов с большим количеством литеральных скобок удобнее `template_format="mustache"`, где переменные пишутся как `{{name}}`, а одиночные скобки не требуют экранирования.

### 3.2. ChatPromptTemplate (шаблон сообщений)

Для chat-моделей нужен не текст, а список типизированных сообщений (system / human / ai). Это делает `ChatPromptTemplate`. Основной способ создания — `from_messages()`, принимающий список сообщений, где каждое задаётся кортежем `(role, template)`.

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "Ты — помощник, отвечающий кратко на {language}."),
    ("human", "{question}"),
])

messages = prompt.invoke(
    {"language": "русском", "question": "Что такое LCEL?"}
).to_messages()
# [SystemMessage(...), HumanMessage(...)]
```

Допустимые роли: `"system"`, `"human"` (синоним `"user"`), `"ai"` (синоним `"assistant"`). Вместо кортежа можно передавать и готовые объекты сообщений (`SystemMessage`, `HumanMessage` из `langchain_core.messages`) или экземпляры `SystemMessagePromptTemplate` / `HumanMessagePromptTemplate` — но кортежная форма компактнее и на практике предпочтительна.

Метод `from_template()` у `ChatPromptTemplate` создаёт шаблон из одного human-сообщения — это удобное сокращение для простейших случаев:

```python
prompt = ChatPromptTemplate.from_template("Кратко объясни: {topic}")
```

### 3.3. MessagesPlaceholder (вставка списка сообщений)

`MessagesPlaceholder` резервирует место в списке сообщений, куда во время вызова подставляется целый список готовых сообщений. Это основной механизм для передачи истории диалога или промежуточных шагов агента.

```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

prompt = ChatPromptTemplate.from_messages([
    ("system", "Ты — вежливый ассистент."),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{question}"),
])

result = prompt.invoke({
    "history": [
        HumanMessage(content="Как тебя зовут?"),
        AIMessage(content="Я ассистент."),
    ],
    "question": "А что ты умеешь?",
})
```

Полезные аргументы: `optional=True` делает переменную необязательной (если её не передали, вставляется пустой список — удобно для первого хода диалога), а `n_messages` (тип `PositiveInt | None`) ограничивает число подставляемых сообщений, оставляя последние `n`.

Начиная с современных версий LangChain существует краткая форма-синоним прямо внутри `from_messages` — кортеж `("placeholder", "{history}")`. Обратите внимание на нюанс: эта краткая форма создаёт `MessagesPlaceholder(variable_name="history", optional=True)`, то есть переменная становится **необязательной**. Полная запись `MessagesPlaceholder("history")` по умолчанию, наоборот, обязательна (`optional=False`), и её точный эквивалент — `MessagesPlaceholder("history", optional=True)`:

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", "Ты — ассистент."),
    ("placeholder", "{history}"),  # == MessagesPlaceholder("history", optional=True)
    ("human", "{question}"),
])
```

### 3.4. Подстановка переменных и partial-переменные

Иногда часть переменных известна заранее и не должна запрашиваться при каждом вызове. Метод `.partial()` возвращает новый шаблон с уже зафиксированными значениями; остальные переменные подставляются позже.

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", "Ты пишешь в стиле: {style}."),
    ("human", "{question}"),
])

formal_prompt = prompt.partial(style="официально-деловой")
# Теперь при вызове нужен только question:
formal_prompt.invoke({"question": "Опиши погоду."})
```

`partial()` принимает не только строки, но и функции без аргументов — они вычисляются в момент форматирования. Это классический приём для «живых» значений вроде текущей даты:

```python
from datetime import datetime

def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

prompt = PromptTemplate.from_template(
    "Сегодня {today}. Ответь на вопрос: {question}"
).partial(today=_today)

# today пересчитывается при каждом форматировании
prompt.format(question="Какой сегодня день недели?")
```

То же значение можно передать через аргумент `partial_variables` в конструкторе. Если partial-переменная останется незаполненной callable-функцией, а обычная переменная не передана при вызове — будет `KeyError` с именем недостающей переменной.

### 3.5. Few-shot: примеры в промпте

Few-shot-подход добавляет в промпт несколько демонстрационных примеров «вход → выход», чтобы задать модели формат и стиль ответа.

#### FewShotPromptTemplate (строковый вариант)

Используется с обычными (не chat) моделями. Каждый пример форматируется отдельным `example_prompt`, затем все примеры склеиваются между `prefix` и `suffix`.

```python
from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate

examples = [
    {"input": "happy", "output": "sad"},
    {"input": "tall", "output": "short"},
]

example_prompt = PromptTemplate.from_template("Input: {input}\nOutput: {output}")

few_shot = FewShotPromptTemplate(
    examples=examples,
    example_prompt=example_prompt,
    prefix="Подбери антоним к слову.",
    suffix="Input: {word}\nOutput:",
    input_variables=["word"],
    example_separator="\n\n",
)

print(few_shot.format(word="big"))
```

Ключевые аргументы: `examples` (список словарей) **или** `example_selector` (динамический выбор — см. ниже); `example_prompt` — шаблон одного примера; `prefix` / `suffix` — текст до и после блока примеров; `input_variables` — переменные, встречающиеся в `suffix`/`prefix`; `example_separator` — разделитель между примерами.

#### FewShotChatMessagePromptTemplate (chat-вариант)

Для chat-моделей примеры оформляются как пары сообщений (human → ai). Здесь `example_prompt` — это уже `ChatPromptTemplate`, описывающий формат одного примера, а сам few-shot-блок затем встраивается в итоговый `ChatPromptTemplate`.

```python
from langchain_core.prompts import (
    ChatPromptTemplate,
    FewShotChatMessagePromptTemplate,
)

examples = [
    {"input": "2+2", "output": "4"},
    {"input": "2+3", "output": "5"},
]

# Шаблон одного примера: пара human/ai
example_prompt = ChatPromptTemplate.from_messages([
    ("human", "{input}"),
    ("ai", "{output}"),
])

few_shot = FewShotChatMessagePromptTemplate(
    example_prompt=example_prompt,
    examples=examples,
)

final_prompt = ChatPromptTemplate.from_messages([
    ("system", "Ты — калькулятор, отвечай только числом."),
    few_shot,                       # разворачивается в набор human/ai сообщений
    ("human", "{input}"),
])

final_prompt.invoke({"input": "3+3"}).to_messages()
```

`few_shot` при форматировании разворачивается в последовательность сообщений-примеров, которые вставляются между системным сообщением и финальным вопросом.

#### Example selectors (выбор примеров)

Когда примеров много, подставлять их все нецелесообразно (растут токены и стоимость). Селекторы примеров выбирают подмножество под конкретный запрос. Они находятся в `langchain_core.example_selectors`:

- `LengthBasedExampleSelector` — берёт столько примеров, сколько влезает в бюджет по длине.
- `SemanticSimilarityExampleSelector` — выбирает семантически ближайшие к входу примеры (нужны embeddings и векторное хранилище).
- `MaxMarginalRelevanceExampleSelector` — как предыдущий, но балансирует релевантность и разнообразие.

```python
from langchain_core.example_selectors import SemanticSimilarityExampleSelector
from langchain_core.prompts import FewShotChatMessagePromptTemplate, ChatPromptTemplate
from langchain_openai import OpenAIEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore

example_selector = SemanticSimilarityExampleSelector.from_examples(
    examples,                       # список словарей с примерами
    OpenAIEmbeddings(),             # модель эмбеддингов
    InMemoryVectorStore,            # КЛАСС векторного хранилища (не экземпляр)
    k=2,                            # сколько примеров подобрать
    input_keys=["input"],           # по каким полям примеров считать сходство
)

few_shot = FewShotChatMessagePromptTemplate(
    example_selector=example_selector,
    example_prompt=ChatPromptTemplate.from_messages([
        ("human", "{input}"),
        ("ai", "{output}"),
    ]),
    # input_variables объявляет входные переменные шаблона;
    # при вызове их значения передаются селектору для поиска примеров
    input_variables=["input"],
)
```

Здесь важно различать два параметра. `input_keys` в `from_examples` указывает, по каким полям примеров вычислять эмбеддинги для поиска сходства (без него берётся конкатенация всех полей примера, включая `output`). А `input_variables` у `FewShotChatMessagePromptTemplate` перечисляет входные переменные самого шаблона — именно их значения при вызове и передаются селектору. Аргумент `vectorstore_cls` (третий позиционный) — это **класс** хранилища (`type[VectorStore]`), а не готовый экземпляр: `from_examples` сам вызовет у него `from_texts(...)`.

Обратите внимание: указываются **либо** `examples`, **либо** `example_selector`, но не оба одновременно (это проверяется валидатором `check_examples_and_selector`). Раньше селекторы импортировались из `langchain.prompts` — сейчас канонический путь `langchain_core.example_selectors`.

### 3.6. Композиция промпта с моделью через LCEL

Главное преимущество промпт-шаблонов — их встраивание в цепочку LCEL оператором `|`. Промпт форматирует вход, результат (`PromptValue`) уходит в модель, а `StrOutputParser` при желании извлекает чистый текст из ответа.

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

prompt = ChatPromptTemplate.from_messages([
    ("system", "Ты — эксперт по {domain}."),
    ("human", "{question}"),
])
model = ChatOpenAI(model="gpt-4o-mini", temperature=0)

chain = prompt | model | StrOutputParser()

answer = chain.invoke({"domain": "Python", "question": "Что такое GIL?"})
print(answer)  # строка с ответом модели
```

Собранная цепочка сама является `Runnable`, поэтому поддерживает `.invoke()`, `.batch()`, `.stream()` и их async-аналоги (`.ainvoke()` и т. д.) без дополнительного кода.

**Об устаревшем.** Ранее промпт связывали с моделью через `LLMChain(llm=..., prompt=...)`. Этот класс объявлен устаревшим (deprecated), а в LangChain 1.0 вынесен в отдельный пакет `langchain_classic` — вместо него используйте конвейер `prompt | model`. Он прозрачнее, лучше стримит и без изменений работает как синхронно, так и асинхронно.

### Краткий чек-лист

| Задача | Что использовать |
| --- | --- |
| Один текстовый промпт | `PromptTemplate.from_template` |
| Диалог system/human/ai | `ChatPromptTemplate.from_messages` |
| Вставить историю сообщений | `MessagesPlaceholder` или `("placeholder", "{history}")` |
| Зафиксировать часть переменных | `.partial(...)` |
| Примеры для обычной модели | `FewShotPromptTemplate` |
| Примеры для chat-модели | `FewShotChatMessagePromptTemplate` |
| Динамический подбор примеров | `*ExampleSelector` из `langchain_core.example_selectors` |
| Связать промпт с моделью | LCEL: `prompt \| model \| parser` |


---


## 4. LCEL: Runnable и композиция цепочек

LCEL (LangChain Expression Language) — это декларативный способ собирать компоненты LangChain в «цепочки» (chains). В основе LCEL лежит единый интерфейс `Runnable`: любой объект, реализующий этот интерфейс (модель, промпт-шаблон, парсер вывода, ретривер, обычная функция), можно вызывать одинаково и соединять с другими такими объектами оператором `|`.

По состоянию на LangChain 1.0 (2025–2026) LCEL остаётся штатным и рекомендуемым способом описывать линейные и умеренно ветвящиеся потоки данных. Для агентных сценариев, циклов, ветвлений с состоянием, human-in-the-loop и персистентности официальная рекомендация — переходить на LangGraph (см. подраздел «Когда LCEL, а когда LangGraph»).

### 4.1. Интерфейс Runnable

Базовый класс `Runnable` находится в `langchain_core.runnables`. Он задаёт стандартный набор методов, синхронных и асинхронных.

| Метод | Назначение |
|-------|-----------|
| `invoke(input, config=None)` | Один вход → один выход |
| `stream(input, config=None)` | Потоковый вывод по частям (генератор чанков) |
| `batch(inputs, config=None)` | Список входов → список выходов (параллельно) |
| `ainvoke` / `astream` / `abatch` | Асинхронные версии перечисленных методов |
| `astream_events(input, ...)` | Поток структурированных событий обо всех вложенных шагах |
| `with_config` / `with_retry` / `with_fallbacks` / `bind` | Конфигурирование и обёртки (возвращают новый `Runnable`) |

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

prompt = ChatPromptTemplate.from_template("Переведи на английский: {text}")
model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
parser = StrOutputParser()

chain = prompt | model | parser

# invoke: один вход -> одна строка
print(chain.invoke({"text": "Привет, мир"}))

# batch: несколько входов, выполняются параллельно
print(chain.batch([{"text": "кот"}, {"text": "собака"}]))

# stream: печатаем токены по мере генерации
for chunk in chain.stream({"text": "длинный текст"}):
    print(chunk, end="", flush=True)
```

`batch` по умолчанию распараллеливает вызовы через пул потоков; степень параллелизма ограничивается через `config={"max_concurrency": 5}`. `batch_as_completed` возвращает результаты по мере готовности (парами `(index, output)`, где `output` может быть и исключением, если `return_exceptions=True`), что удобно, когда порядок не важен.

### 4.2. Оператор `|` и RunnableSequence

Оператор `|` перегружен: `a | b` создаёт `RunnableSequence`, где выход `a` подаётся на вход `b`. Это и есть основной способ композиции.

```python
from langchain_core.runnables import RunnableSequence

# Эквивалентные записи:
chain = prompt | model | parser
chain = RunnableSequence(prompt, model, parser)
```

Конструктор `RunnableSequence` принимает шаги как позиционные аргументы (`*steps`), поэтому запись `RunnableSequence(prompt, model, parser)` корректна. Любой обычный callable (функция, lambda) в контексте `|` автоматически оборачивается в `RunnableLambda`, а обычный `dict` — в `RunnableParallel`. Поэтому явно писать `RunnableSequence(...)` почти никогда не нужно — используйте `|`.

Типичная ошибка: несовпадение типов между шагами. Выход `ChatModel` — это `AIMessage`, а не `str`; чтобы получить строку, добавьте `StrOutputParser()`. Второй частый промах — передать в `invoke` строку вместо словаря, если первый шаг цепочки — `ChatPromptTemplate` с переменными.

### 4.3. RunnableParallel — параллельные ветви (dict)

`RunnableParallel` выполняет несколько `Runnable` над одним и тем же входом и возвращает `dict` с их результатами. Ветви исполняются параллельно (в потоках синхронно, через `asyncio` — асинхронно).

```python
from langchain_core.runnables import RunnableParallel

joke = ChatPromptTemplate.from_template("Шутка про {topic}") | model | parser
fact = ChatPromptTemplate.from_template("Факт про {topic}") | model | parser

parallel = RunnableParallel(joke=joke, fact=fact)

result = parallel.invoke({"topic": "кофе"})
# {"joke": "...", "fact": "..."}
```

Голый `dict` автоматически превращается в `RunnableParallel` только тогда, когда он участвует в LCEL-композиции — стоит внутри `|` или является шагом цепочки: `{"a": chain_a, "b": chain_b} | next_step` работает как ожидается. Но сам по себе обычный `dict` — это НЕ `Runnable` и у него нет метода `.invoke`; чтобы вызвать набор ветвей отдельно (как в примере выше), оборачивайте его в явный `RunnableParallel(...)` или скармливайте в цепочку через `|`.

### 4.4. RunnablePassthrough и `.assign`

`RunnablePassthrough` пропускает вход без изменений. Основное применение — сохранить исходные данные, одновременно добавив к ним новые поля.

- `RunnablePassthrough()` — вернуть вход как есть.
- `RunnablePassthrough.assign(**kwargs)` — добавить в словарь-вход новые ключи, вычисленные из этого же входа (исходные ключи сохраняются).

```python
from langchain_core.runnables import RunnablePassthrough

retriever = ...  # некий ретривер, возвращающий документы

rag_chain = (
    RunnablePassthrough.assign(
        context=lambda x: retriever.invoke(x["question"])
    )
    | ChatPromptTemplate.from_template(
        "Ответь на вопрос по контексту.\n\nКонтекст: {context}\n\nВопрос: {question}"
    )
    | model
    | parser
)

rag_chain.invoke({"question": "Что такое LCEL?"})
```

Здесь на входе словарь `{"question": ...}`; после `assign` появляется ещё ключ `context`, а `question` остаётся доступен для промпта. Без `assign` (при использовании обычного `dict`) исходные поля потерялись бы, если их не перечислить явно. Родственный класс `RunnablePick` (`RunnablePassthrough.pick`) выбирает подмножество ключей.

### 4.5. RunnableLambda — произвольная функция как Runnable

`RunnableLambda` оборачивает обычную функцию (или корутину) в `Runnable`. Функция должна принимать ровно один позиционный аргумент (вход); при необходимости вторым аргументом можно принять `config`.

```python
from langchain_core.runnables import RunnableLambda

def add_lengths(x: dict) -> dict:
    return {**x, "n": len(x["text"])}

chain = RunnableLambda(add_lengths) | (lambda d: d["n"] * 2)
chain.invoke({"text": "hello"})  # 10
```

Важный нюанс асинхронности: если передать в `RunnableLambda` синхронную функцию, её `ainvoke` выполнит эту функцию в пуле потоков. Для настоящей неблокирующей работы передавайте `async def`-функцию — тогда доступен нативный `ainvoke`. Можно передать обе реализации: `RunnableLambda(sync_fn, afunc=async_fn)`.

### 4.6. RunnableBranch — ветвление по условию

`RunnableBranch` реализует маршрутизацию: перебирает пары `(condition, runnable)` и выполняет первый `runnable`, чьё условие вернуло истину; последний аргумент — ветка по умолчанию.

```python
from langchain_core.runnables import RunnableBranch

branch = RunnableBranch(
    (lambda x: "перевод" in x["task"], translate_chain),
    (lambda x: "резюме" in x["task"], summarize_chain),
    default_chain,  # если ни одно условие не сработало
)
branch.invoke({"task": "перевод", "text": "..."})
```

Часто вместо `RunnableBranch` предпочитают более читаемую кастомную функцию в `RunnableLambda`, возвращающую нужный `Runnable` (LCEL поддерживает такую «динамическую» маршрутизацию). Но если ветвление разрастается до состояния, циклов или нескольких точек принятия решений — это сигнал переходить на LangGraph.

### 4.7. RunnableConfig и модификаторы: with_config, with_retry, with_fallbacks, bind

`RunnableConfig` (`langchain_core.runnables.config`) — это словарь конфигурации, который пронизывает весь вызов. Ключевые поля: `run_name`, `tags`, `metadata`, `callbacks`, `max_concurrency`, `recursion_limit`, `configurable`. Он передаётся в любой метод через аргумент `config=...`.

```python
result = chain.invoke(
    {"text": "hi"},
    config={"run_name": "demo", "tags": ["prod"], "metadata": {"user": "u1"}},
)
```

**`.with_config(...)`** — «приклеивает» конфиг к `Runnable`, чтобы не передавать его при каждом вызове:

```python
traced = chain.with_config(tags=["experiment-A"], run_name="A")
```

**`.with_retry(...)`** — автоматический ретрай при исключениях (экспоненциальная пауза):

```python
robust = model.with_retry(
    retry_if_exception_type=(Exception,),
    stop_after_attempt=3,
    wait_exponential_jitter=True,
)
```

**`.with_fallbacks([...])`** — запасные `Runnable`, если основной упал с исключением:

```python
primary = ChatOpenAI(model="gpt-4o")
backup = ChatOpenAI(model="gpt-4o-mini")
model_with_fallback = primary.with_fallbacks([backup])
```

**`.bind(**kwargs)`** — фиксирует аргументы вызова нижележащего `Runnable` (например, параметры модели), не меняя интерфейс цепочки:

```python
# Зафиксировать stop-последовательность и temperature у модели
bound = model.bind(stop=["\n\n"], temperature=0)
```

Для привязки инструментов к чат-модели используйте специализированный метод `model.bind_tools([...])` — он сам приводит функции/схемы к нужному формату tool-calling, тогда как «сырой» `.bind(tools=...)` требует уже подготовленных спецификаций.

Для конфигурации во время исполнения существуют `configurable_fields` (менять отдельные параметры) и `configurable_alternatives` (подставлять целые альтернативные компоненты); значения задаются через `config={"configurable": {...}}`.

```python
from langchain_core.runnables import ConfigurableField

configurable_model = ChatOpenAI(model="gpt-4o-mini").configurable_fields(
    temperature=ConfigurableField(id="llm_temperature")
)
configurable_model.invoke("hi", config={"configurable": {"llm_temperature": 0.9}})
```

Все эти методы возвращают **новый** `Runnable` (`with_config`/`bind` — `RunnableBinding`, `with_retry` — `RunnableRetry`, `with_fallbacks` — `RunnableWithFallbacks`) и не мутируют исходный — их можно свободно комбинировать в цепочке.

### 4.8. Стриминг и асинхронность в LCEL

Ключевое преимущество LCEL — потоковость и async «из коробки»: собранная цепочка автоматически поддерживает `stream/astream`, даже если вы про это не думали. Токены модели транслируются наружу через все промежуточные шаги, если те не буферизуют вход целиком (например, `StrOutputParser` стримит, а парсер, которому нужен полный JSON, — нет).

```python
import asyncio

async def main():
    # Асинхронный потоковый вывод токенов
    async for chunk in chain.astream({"text": "напиши хайку"}):
        print(chunk, end="", flush=True)

    # Асинхронный батч
    outs = await chain.abatch([{"text": "a"}, {"text": "b"}])
    print(outs)

asyncio.run(main())
```

Для детального наблюдения за внутренними шагами (какая модель начала/закончила, какой инструмент вызван, промежуточные токены) используйте **`astream_events`**. Параметр `version` по умолчанию равен `v2` — это актуальная рекомендуемая схема. `v1` оставлен для обратной совместимости и будет объявлен устаревшим (deprecated) в версии 0.4.0; `v3` — новая типизированная схема на «блоках контента» (content blocks), пока в статусе beta и поддерживается лишь отдельными классами (`BaseChatModel` и `CompiledGraph` из LangGraph), а на обычном `Runnable` вызывает `NotImplementedError`.

```python
async def watch():
    async for event in chain.astream_events({"text": "hi"}):  # version="v2" по умолчанию
        kind = event["event"]  # напр. "on_chat_model_stream", "on_parser_end"
        if kind == "on_chat_model_stream":
            print(event["data"]["chunk"].content, end="", flush=True)
```

Каждое событие — это `dict` с полями `event`, `name`, `run_id`, `parent_ids` (список идентификаторов родительских runnable, начиная с v2), `tags`, `metadata`, `data`. Ранее применявшийся `astream_log` считается низкоуровневым; для новых задач предпочитайте `astream_events`.

Практические замечания:
- Не смешивайте синхронные и асинхронные вызовы: в async-коде используйте `ainvoke/astream`, чтобы не блокировать событийный цикл.
- Стриминг «ломается», если в середине цепочки стоит шаг, требующий полного входа (агрегирующая функция, парсер целого JSON). Ставьте такие шаги как можно позже.

### 4.9. Когда LCEL, а когда LangGraph

LCEL идеально подходит, когда поток данных — по сути **направленный ациклический граф** без сложного состояния: «промпт → модель → парсер», RAG, параллельные ветви, простая маршрутизация. Код получается компактным и декларативным.

Переходите на **LangGraph**, когда появляется хотя бы что-то из перечисленного:

- **Циклы и итеративность**: агент, который вызывает инструменты в цикле «think → act → observe» до достижения цели.
- **Явное состояние**, разделяемое между шагами и накапливаемое (в LCEL состояние приходится «протаскивать» через словари и `assign`, что быстро становится громоздким).
- **Условные переходы и много точек принятия решений**, ветвления с возвратами назад.
- **Human-in-the-loop**, паузы и возобновление (`interrupt`), персистентность через checkpointer.
- **Долгоживущие процессы**, стриминг состояния (`stream_mode`), тайм-тревел и отладка шагов.

Практическое правило от команды LangChain: LangChain (включая LCEL) — это «строительные блоки», а LangGraph — оркестратор для агентных и многошаговых процессов с состоянием. При этом внутри узлов графа LangGraph вы по-прежнему используете LCEL-цепочки: подходы дополняют друг друга, а не исключают. В LangChain 1.0 высокоуровневые агенты (`create_agent` из `langchain.agents`) построены поверх LangGraph, тогда как ручную сборку линейных пайплайнов удобнее всего описывать именно на LCEL.

Sources:
- [LangChain (Python) overview — docs.langchain.com](https://docs.langchain.com/oss/python/langchain/overview)
- [astream_events — LangChain Reference](https://reference.langchain.com/python/langchain-core/runnables/base/Runnable/astream_events)
- [Streaming — Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/streaming)


---


## 5. Структурированный вывод и парсеры

Языковые модели по своей природе возвращают свободный текст. Но в реальных приложениях нам почти всегда нужен предсказуемый машиночитаемый результат: объект с полями, список, число, JSON. Для этого в LangChain есть два принципиально разных механизма:

1. **`model.with_structured_output(...)`** — использует нативные возможности провайдера (tool/function calling или JSON-режим). Модель «сама» отдаёт валидированную структуру. Это рекомендуемый способ для современных чат-моделей.
2. **Output-парсеры** (`StrOutputParser`, `JsonOutputParser`, `PydanticOutputParser` и т. д.) — постобработка текстового ответа: парсинг строки в объект уже на стороне клиента. Приём более старый и универсальный, работает даже с моделями без поддержки tool calling.

Ниже разберём оба подхода, их отличия и обработку ошибок.

### 5.1. `with_structured_output`

`with_structured_output` — метод чат-модели (`BaseChatModel`), который возвращает новый `Runnable`. На вход вы даёте *схему*, а на выходе получаете не `AIMessage`, а сразу объект нужного типа.

Сигнатура (упрощённо):

```python
model.with_structured_output(
    schema,                 # Pydantic-класс, TypedDict, dataclass или dict с JSON Schema
    *,
    method="function_calling",  # "function_calling" | "json_mode" | "json_schema"
    include_raw=False,
    strict=None,
    **kwargs,
)
```

#### Схема на основе Pydantic `BaseModel`

Самый надёжный вариант: описание полей + автоматическая валидация типов. Docstring класса и `Field(description=...)` передаются модели как подсказки — их стоит заполнять содержательно, это заметно повышает качество.

```python
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model

class Person(BaseModel):
    """Информация о человеке, извлечённая из текста."""
    name: str = Field(description="Полное имя")
    age: int | None = Field(default=None, description="Возраст в годах, если указан")
    hobbies: list[str] = Field(default_factory=list, description="Список увлечений")

model = init_chat_model("gpt-4o-mini", model_provider="openai")
structured_model = model.with_structured_output(Person)

result = structured_model.invoke("Меня зовут Анна, мне 29, люблю бег и книги.")
print(type(result), result)
# <class '__main__.Person'> name='Анна' age=29 hobbies=['бег', 'книги']
```

Возвращается **экземпляр `Person`** — уже провалидированный объект, к полям которого можно обращаться через точку (`result.name`).

> Примечание про версии Pydantic. Современный LangChain (0.3+ и v1) работает на Pydantic **v2**. Импортируйте `from pydantic import BaseModel`, а не устаревшее `from langchain_core.pydantic_v1 import BaseModel` (этот shim оставлен только для обратной совместимости; в 0.3 он помечен deprecated, а в LangChain v1 использовать его не следует).

#### Схема на основе `TypedDict`

Если валидация Pydantic не нужна и достаточно обычного словаря — используйте `TypedDict`. Для описания полей применяют `Annotated` с текстовой подсказкой (форма `Annotated[тип, значение_по_умолчанию, "описание"]`).

```python
from typing_extensions import TypedDict, Annotated

class Person(TypedDict):
    """Информация о человеке."""
    name: Annotated[str, ..., "Полное имя"]
    age: Annotated[int | None, None, "Возраст, если указан"]

structured_model = model.with_structured_output(Person)
result = structured_model.invoke("Иван, 40 лет")
print(type(result), result)   # <class 'dict'> {'name': 'Иван', 'age': 40}
```

Здесь возвращается обычный **`dict`** — без валидации на этапе выполнения. `TypedDict` и `Annotated` берите из `typing_extensions`: так подсказки полей корректно читаются во всех поддерживаемых версиях Python.

#### Схема на основе JSON Schema

Можно передать «сырую» JSON Schema как словарь. Полезно, когда схема генерируется динамически или приходит извне.

```python
json_schema = {
    "title": "Person",
    "description": "Информация о человеке",
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Полное имя"},
        "age": {"type": ["integer", "null"], "description": "Возраст"},
    },
    "required": ["name"],
}

structured_model = model.with_structured_output(json_schema)
result = structured_model.invoke("Пётр, 33")   # тоже вернётся dict
```

#### Аргумент `method`

| Значение | Как работает | Когда использовать |
|---|---|---|
| `"function_calling"` | Схема оформляется как «инструмент», модель вызывает его через tool calling. Значение по умолчанию для большинства провайдеров. | Универсальный выбор для моделей с поддержкой tools. |
| `"json_schema"` | Нативный structured output провайдера с жёстким соблюдением схемы (OpenAI Structured Outputs, Gemini и т. п.). | Новейшие модели; максимальная гарантия соответствия схеме. |
| `"json_mode"` | Провайдерский «JSON mode»: модель обязана вернуть валидный JSON, но саму схему не гарантирует. Требует, чтобы вы **сами** описали ожидаемый формат в промпте. | Модели без tool calling, но с JSON-режимом. |

```python
# json_mode: обязательно упомяните структуру в промпте
model_json = model.with_structured_output(Person, method="json_mode")
model_json.invoke(
    "Верни JSON с полями name и age. Текст: Мария, 25 лет."
)
```

Параметр `strict=True` (для `json_schema`/`function_calling` у поддерживающих провайдеров) включает строгую проверку схемы на стороне провайдера — модель физически не сможет вернуть лишние или недостающие поля.

#### Аргумент `include_raw`

По умолчанию (`include_raw=False`) при ошибке парсинга бросается исключение, и вы теряете исходный ответ. Если поставить `include_raw=True`, метод вернёт **словарь** с тремя ключами:

- `"raw"` — исходное `AIMessage` от модели;
- `"parsed"` — распарсенная структура (или `None`, если не удалось);
- `"parsing_error"` — исключение (или `None`).

```python
robust_model = model.with_structured_output(Person, include_raw=True)
out = robust_model.invoke("Свободный текст без явных данных")

if out["parsing_error"]:
    print("Не удалось распарсить:", out["parsing_error"])
    print("Сырой ответ:", out["raw"].content)
else:
    person = out["parsed"]
    print(person.name)
```

Это лучшая практика для продакшена: вы никогда не теряете сырой ответ и можете логировать/обрабатывать сбои, а не ловить неожиданное исключение.

### 5.2. Output-парсеры

Парсеры — это `Runnable`, которые ставятся в конец цепочки (LCEL) и превращают текстовый ответ модели в нужный тип. Все они наследуются от `BaseOutputParser` и имеют метод `get_format_instructions()`.

#### `StrOutputParser`

Простейший парсер: берёт `AIMessage` и возвращает его `.content` как строку. Незаменим, когда нужен просто текст в конце цепочки.

```python
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_template("Расскажи факт про {topic}")
chain = prompt | model | StrOutputParser()
print(chain.invoke({"topic": "океан"}))   # обычная строка
```

#### `PydanticOutputParser`

Парсит текст в Pydantic-модель. В отличие от `with_structured_output`, он **не использует** tool calling — модель должна вернуть JSON в тексте, а инструкции о формате вы добавляете в промпт через `get_format_instructions()`.

```python
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

class Person(BaseModel):
    name: str = Field(description="Полное имя")
    age: int = Field(description="Возраст")

parser = PydanticOutputParser(pydantic_object=Person)

prompt = PromptTemplate(
    template="Извлеки данные.\n{format_instructions}\nТекст: {query}\n",
    input_variables=["query"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)

chain = prompt | model | parser
person = chain.invoke({"query": "Ольга, 31 год"})
print(person.name, person.age)   # экземпляр Person
```

`get_format_instructions()` возвращает готовый текст с JSON-схемой модели, который «объясняет» LLM ожидаемый формат. Подставляйте его через `partial_variables`, чтобы не передавать вручную при каждом вызове.

#### `JsonOutputParser`

Парсит ответ в `dict`/`list`. Можно (необязательно) передать `pydantic_object` — тогда `get_format_instructions()` сгенерирует инструкции по этой схеме, но результат всё равно будет словарём (без строгой валидации Pydantic).

```python
from langchain_core.output_parsers import JsonOutputParser

parser = JsonOutputParser(pydantic_object=Person)
prompt = PromptTemplate(
    template="{format_instructions}\nТекст: {query}",
    input_variables=["query"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)
chain = prompt | model | parser
print(chain.invoke({"query": "Дмитрий, 45"}))   # {'name': 'Дмитрий', 'age': 45}
```

Важное преимущество `JsonOutputParser` — поддержка **стриминга частичного JSON**: при `chain.stream(...)` он отдаёт постепенно достраивающиеся словари, что удобно для UI.

### 5.3. Сравнение подходов

| Критерий | `with_structured_output` (tool/function calling) | Парсинг текста (`*OutputParser`) |
|---|---|---|
| Механизм | Нативные tools/JSON-mode провайдера | Модель пишет JSON в текст, клиент парсит |
| Нужна поддержка tools у модели | Да (кроме `json_mode`) | Нет |
| Надёжность формата | Высокая (особенно `strict`/`json_schema`) | Ниже, зависит от промпта |
| Инструкции в промпте | Не нужны (кроме `json_mode`) | Нужны (`get_format_instructions()`) |
| Валидация | Есть (Pydantic) | Есть только у `PydanticOutputParser` |
| Стриминг частичных объектов | Ограничен | Хорош у `JsonOutputParser` |

**Рекомендация:** для современных моделей (OpenAI, Anthropic, Gemini) используйте `with_structured_output`. Парсеры выбирайте, когда модель не поддерживает tool calling, когда нужен потоковый частичный JSON или когда вы хотите тонкий контроль над промптом и постобработкой.

> Примечание про новый API агентов. В LangChain v1 у функции `create_agent` (`from langchain.agents import create_agent`) есть параметр `response_format`, принимающий стратегии `ToolStrategy` / `ProviderStrategy` (`from langchain.agents.structured_output import ToolStrategy, ProviderStrategy`) или прямо тип-схему. Если передать схему напрямую, LangChain сам выберет `ProviderStrategy` для моделей с нативным structured output и `ToolStrategy` в остальных случаях. Структурированный ответ доступен в `result["structured_response"]`. Это надстройка для агентов; на уровне отдельной модели канонический способ по-прежнему `with_structured_output`.

### 5.4. Обработка ошибок валидации и парсинга

При несоответствии формата возможны два типа исключений:

- `pydantic.ValidationError` — данные распарсились как JSON, но не прошли валидацию Pydantic;
- `langchain_core.exceptions.OutputParserException` — не удалось разобрать текст в JSON.

```python
from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError

try:
    person = chain.invoke({"query": "невнятный текст"})
except OutputParserException as e:
    print("Модель вернула невалидный JSON:", e)
except ValidationError as e:
    print("JSON не соответствует схеме:", e)
```

На практике `PydanticOutputParser` обычно оборачивает ошибку валидации в `OutputParserException`, а «голый» `pydantic.ValidationError` чаще всплывает из `with_structured_output`; ловить оба типа — надёжная защитная практика.

Для `with_structured_output` предпочтительный способ — уже упомянутый `include_raw=True`: он не бросает исключение, а кладёт ошибку в `parsing_error`.

#### `OutputFixingParser` (кратко)

Если базовый парсер упал, `OutputFixingParser` берёт кривой вывод и отправляет его обратно в LLM с просьбой исправить формат, после чего парсит повторно. Оборачивает любой другой парсер.

```python
from langchain_core.output_parsers import PydanticOutputParser
# 0.3.x: from langchain.output_parsers import OutputFixingParser
# LangChain v1: from langchain_classic.output_parsers import OutputFixingParser
from langchain_classic.output_parsers import OutputFixingParser

base_parser = PydanticOutputParser(pydantic_object=Person)
fixing_parser = OutputFixingParser.from_llm(parser=base_parser, llm=model)

# Даже слегка сломанный JSON будет исправлен через дополнительный вызов модели
person = fixing_parser.parse('{"name": "Анна", "age": "тридцать"}')
```

> Импорт. `OutputFixingParser` и родственный `RetryOutputParser` — легаси-парсеры. В LangChain **v1** они вынесены в отдельный пакет: `from langchain_classic.output_parsers import ...` (нужно установить `langchain-classic`). Старый путь `from langchain.output_parsers import OutputFixingParser` в v1 ещё работает, но помечен deprecated и выдаёт предупреждение; в ветке 0.3.x он остаётся штатным. `RetryOutputParser` дополнительно передаёт исходный промпт, что помогает восстановить *семантически* пропущенные поля, а не только синтаксис.

**Стоимость.** `OutputFixingParser` и `RetryOutputParser` делают дополнительный запрос к модели. Не злоупотребляйте ими: для надёжного формата обычно достаточно `method="json_schema"`/`strict=True` в `with_structured_output`, а «чинилку» держите как fallback на редкие сбои.


---


## 6. Инструменты (Tools) и tool calling

Инструмент (tool) — это обёртка вокруг Python-функции с описанием и схемой аргументов, которую можно передать языковой модели. Модель сама не выполняет код: она лишь **решает**, какой инструмент вызвать и с какими аргументами, а фактический вызов делаете вы (или готовый агент). Каждый инструмент — это наследник `BaseTool` с четырьмя ключевыми свойствами:

- `name` — имя, которое видит модель;
- `description` — описание назначения (обычно берётся из docstring);
- `args_schema` — Pydantic-схема аргументов;
- `func` / `coroutine` — синхронная и асинхронная реализация.

Базовые импорты (стабильны с версии `langchain-core` 0.1 и работают в 0.3 / 1.x):

```python
from langchain_core.tools import tool, StructuredTool, BaseTool, ToolException
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
```

> Примечание об импортах. В LangChain 1.x появились «зонтичные» реэкспорты `from langchain.tools import tool` и `from langchain.messages import ToolMessage`. Они удобны, но каноничным и наиболее переносимым остаётся пакет `langchain_core`. В примерах ниже используется именно он.

### 6.1. Декоратор `@tool`

Самый быстрый способ создать инструмент — декорировать функцию. **Docstring и type hints обязательны**: из аннотаций типов строится `args_schema`, а docstring становится `description`, по которому модель выбирает инструмент. Плохое описание — главная причина того, что модель не вызывает нужный tool или передаёт неверные аргументы.

```python
from langchain_core.tools import tool

@tool
def multiply(a: int, b: int) -> int:
    """Multiply two integers and return the product."""
    return a * b

print(multiply.name)         # multiply
print(multiply.description)  # Multiply two integers and return the product.
print(multiply.args)         # {'a': {'title': 'A', 'type': 'integer'}, 'b': {...}}
```

Вызвать инструмент можно как обычный `Runnable` — через `.invoke()` со словарём аргументов:

```python
multiply.invoke({"a": 6, "b": 7})   # 42
```

#### Ключевые аргументы декоратора

| Аргумент | Назначение |
|---|---|
| `name_or_callable` | Переопределить имя: `@tool("web_search")`. |
| `description` | Явное описание вместо docstring. |
| `args_schema` | Своя Pydantic-схема аргументов (см. 6.3). |
| `return_direct` | Вернуть результат сразу, без повторного вызова модели (см. 6.6). |
| `response_format` | `"content"` (по умолчанию) или `"content_and_artifact"` (см. 6.8). |
| `parse_docstring` | Разобрать Google-style docstring и вытащить описания аргументов. |
| `infer_schema` | Строить схему из аннотаций автоматически (по умолчанию `True`). |

Пример с `parse_docstring=True` — описания аргументов попадут в схему и будут видны модели:

```python
@tool(parse_docstring=True)
def get_weather(city: str, units: str = "celsius") -> str:
    """Get the current weather for a city.

    Args:
        city: Name of the city, e.g. "Berlin".
        units: Temperature units, "celsius" or "fahrenheit".
    """
    return f"20 degrees in {city}"
```

При `parse_docstring=True` docstring должен быть валидным Google-style, иначе поднимется ошибка; отключить строгую проверку можно через `error_on_invalid_docstring=False`.

### 6.2. `StructuredTool.from_function`

`StructuredTool.from_function` даёт больше контроля, чем декоратор, и удобен, когда нужно задать sync- и async-реализацию вместе или собрать инструмент программно (например, в фабрике/цикле).

```python
from langchain_core.tools import StructuredTool

def search(query: str, top_k: int = 5) -> str:
    """Search the knowledge base."""
    return f"top {top_k} results for {query!r}"

async def asearch(query: str, top_k: int = 5) -> str:
    return f"top {top_k} results for {query!r}"

search_tool = StructuredTool.from_function(
    func=search,
    coroutine=asearch,          # своя async-реализация
    name="kb_search",
    description="Search the internal knowledge base by query.",
    return_direct=False,
    handle_tool_error=True,     # см. 6.7
)
```

Основные параметры: `func`, `coroutine`, `name`, `description`, `args_schema`, `return_direct`, `response_format`, `handle_tool_error`, `infer_schema`. Если передать только `coroutine`, инструмент будет вызываться исключительно через `ainvoke` (синхронный `invoke` поднимет `NotImplementedError`).

### 6.3. `args_schema` через Pydantic

Явная Pydantic-модель нужна, когда важны точные описания полей, значения по умолчанию, ограничения (`Literal`, `Field(ge=..., le=...)`) или псевдонимы. Именно `description` полей сильнее всего влияет на качество генерации аргументов.

```python
from pydantic import BaseModel, Field
from typing import Literal
from langchain_core.tools import tool

class WeatherInput(BaseModel):
    """Input schema for the weather tool."""
    city: str = Field(description="City name, e.g. 'Paris'.")
    units: Literal["celsius", "fahrenheit"] = Field(
        default="celsius", description="Temperature units."
    )

@tool(args_schema=WeatherInput)
def get_weather(city: str, units: str = "celsius") -> str:
    """Get the current weather for a city."""
    return f"18 {units} in {city}"
```

Важно использовать `from pydantic import BaseModel` (Pydantic v2). Старый импорт `from langchain_core.pydantic_v1 import BaseModel` устарел и удалён в langchain-core 1.0.

### 6.4. Привязка инструментов к модели: `bind_tools`

Чтобы модель «узнала» об инструментах, их привязывают через `model.bind_tools([...])`. Метод поддерживают все провайдеры с function calling (`ChatOpenAI`, `ChatAnthropic` и др.). Он возвращает **новый** объект модели — исходный не мутируется.

```python
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model="gpt-4o", temperature=0)
tools = [multiply, get_weather]
model_with_tools = model.bind_tools(tools)

ai_msg = model_with_tools.invoke("What is 6 times 7?")
print(ai_msg.tool_calls)
# [{'name': 'multiply', 'args': {'a': 6, 'b': 7},
#   'id': 'call_abc123', 'type': 'tool_call'}]
```

Полезный параметр — `tool_choice`: `"auto"` (по умолчанию), `"any"`/`"required"` (обязательно вызвать хоть один инструмент), `"none"` (запретить вызовы), либо имя конкретного инструмента, чтобы принудить его вызов. Конкретный набор допустимых значений зависит от провайдера, но эти алиасы LangChain нормализует автоматически.

Модель возвращает `AIMessage`, у которого заполнен список `.tool_calls` — каждый элемент это словарь с ключами `name`, `args`, `id`, `type`. Если модель решила ответить текстом, `.tool_calls` будет пустым.

### 6.5. Полный цикл tool calling (вручную)

Классический цикл: модель возвращает `tool_calls` → вы выполняете инструменты → формируете `ToolMessage` с тем же `tool_call_id` → повторно вызываете модель, чтобы она сформулировала финальный ответ. Соответствие `tool_call_id` критично: по нему модель связывает результат с конкретным вызовом.

```python
from langchain_core.messages import HumanMessage, ToolMessage

tools_by_name = {t.name: t for t in tools}

messages = [HumanMessage("What is 6 times 7? Also weather in Paris?")]
ai_msg = model_with_tools.invoke(messages)
messages.append(ai_msg)

# Выполняем каждый запрошенный инструмент
for call in ai_msg.tool_calls:
    selected = tools_by_name[call["name"]]
    # Передаём tool_call целиком -> инструмент вернёт готовый ToolMessage
    tool_msg = selected.invoke(call)
    messages.append(tool_msg)

# Повторный вызов модели с результатами инструментов
final = model_with_tools.invoke(messages)
print(final.content)
```

Тонкость: если передать в `tool.invoke(call)` **весь словарь** tool_call (с ключами `name`/`args`/`id`/`type`), инструмент сам вернёт объект `ToolMessage` с корректно проставленным `tool_call_id`. Если же передать только `call["args"]`, вы получите «сырой» результат и `ToolMessage` придётся собирать самому:

```python
result = selected.invoke(call["args"])
messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
```

На практике этот цикл повторяют в `while`, пока в очередном `AIMessage` есть `tool_calls`. В LangGraph этот же цикл предоставляется «из коробки» готовым узлом `ToolNode` и агентом `create_agent` (см. раздел про агентов); при работе через граф с памятью не забывайте про `checkpointer`.

### 6.6. `return_direct`

`return_direct=True` означает: как только инструмент отработал, вернуть его результат пользователю напрямую, **не** отправляя его обратно в модель. Полезно, когда вывод инструмента и есть финальный ответ (например, точная сумма заказа), и не нужно тратить лишний вызов LLM.

```python
@tool(return_direct=True)
def get_order_status(order_id: str) -> str:
    """Return the shipping status of an order."""
    return f"Order {order_id}: shipped, arrives in 2 days."
```

Флаг учитывается агентами/`ToolNode`; в ручном цикле (6.5) поведение реализуете сами, проверяя `tool.return_direct`.

### 6.7. `ToolException` и обработка ошибок

Внутри инструмента для «ожидаемых» ошибок используют `ToolException` — это сигнал, что вызов не удался, но агент должен продолжить работу, а не падать. Поведение задаёт `handle_tool_error`:

```python
from langchain_core.tools import StructuredTool, ToolException

def get_city(country: str) -> str:
    if country == "Atlantis":
        raise ToolException(f"Unknown country: {country}")
    return "capital city"

city_tool = StructuredTool.from_function(
    func=get_city,
    handle_tool_error="Please provide a real country name.",
)
```

Значения `handle_tool_error`:

- `False` (по умолчанию) — исключение пробрасывается наружу;
- `True` — текст исключения возвращается в `ToolMessage`;
- `str` — фиксированная строка-заглушка;
- `Callable[[ToolException], str]` — функция, формирующая текст ошибки для модели.

Аналогично `handle_validation_error` обрабатывает ошибки валидации входных аргументов (`ValidationError`).

> В агентах LangChain 1.x ошибки инструментов принято перехватывать через middleware — декоратор `wrap_tool_call` (`from langchain.agents.middleware import wrap_tool_call`). Он оборачивает вызов на уровне агента, получает `ToolCallRequest` и может вернуть собственный `ToolMessage` (например, с `tool_call_id=request.tool_call["id"]`). При этом `ToolException` + `handle_tool_error` из `langchain_core` по-прежнему поддерживаются и остаются основным механизмом на уровне отдельного инструмента (в том числе вне агентов).

### 6.8. `response_format="content_and_artifact"`

По умолчанию `response_format="content"`: то, что вернул инструмент, целиком идёт в `content` сообщения `ToolMessage` (модель это видит). Иногда нужно вернуть модели краткое текстовое резюме, но при этом сохранить «сырой» тяжёлый объект (документы, DataFrame, байты) для остального кода — не показывая его LLM. Для этого `response_format="content_and_artifact"`, а функция возвращает кортеж `(content, artifact)`:

```python
from langchain_core.tools import tool

@tool(response_format="content_and_artifact")
def search_docs(query: str) -> tuple[str, list[dict]]:
    """Search documents and return a summary plus raw hits."""
    raw = [{"id": 1, "text": "..."}, {"id": 2, "text": "..."}]
    summary = f"Found {len(raw)} documents for {query!r}."
    return summary, raw   # (content -> модели, artifact -> в код)

call = {"name": "search_docs", "args": {"query": "gpu"},
        "id": "call_1", "type": "tool_call"}
msg = search_docs.invoke(call)
print(msg.content)    # 'Found 2 documents for 'gpu'.'
print(msg.artifact)   # [{'id': 1, ...}, {'id': 2, ...}]
```

Чтобы `ToolMessage` получил поле `artifact`, инструмент нужно вызывать, передавая **весь** tool_call (как в примере), а не только `args`.

### 6.9. `InjectedToolArg` и `InjectedState` (кратко)

Иногда инструменту нужны данные, которые **не должна** генерировать модель: `user_id`, токен доступа, соединение с БД, текущее состояние графа. Такие аргументы помечают как инъектируемые — они исключаются из `args_schema`, показываемой модели, и подставляются вашим кодом при выполнении.

`InjectedToolArg` — аргумент подставляется вами вручную в ручном цикле:

```python
from typing import Annotated
from langchain_core.tools import tool, InjectedToolArg

@tool
def update_cart(item: str, user_id: Annotated[str, InjectedToolArg]) -> str:
    """Add an item to the user's cart."""
    return f"Added {item} to cart of {user_id}"

# Модель заполняет только 'item'; 'user_id' подставляем сами:
call = {"name": "update_cart", "args": {"item": "book"},
        "id": "c1", "type": "tool_call"}
call["args"]["user_id"] = "user-42"
print(update_cart.invoke(call).content)
```

`InjectedState` (из `langgraph.prebuilt`) делает то же самое для агентов LangGraph: в аргумент автоматически подставляется состояние графа при выполнении через `ToolNode`.

```python
from typing import Annotated
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

@tool
def summarize(query: str, state: Annotated[dict, InjectedState]) -> str:
    """Summarize the conversation so far."""
    return f"{len(state['messages'])} messages about {query}"
```

> Об устаревании. В LangChain/LangGraph 1.x введён единый интерфейс доступа к контексту — `ToolRuntime`. Он импортируется как `from langchain.tools import ToolRuntime` (эквивалент — `from langgraph.prebuilt import ToolRuntime`) и через один параметр `runtime` даёт `runtime.state`, `runtime.context`, `runtime.store`, `runtime.tool_call_id` (а также `runtime.config`, `runtime.stream_writer` и др.). В официальной документации 1.x прежние точечные аннотации `InjectedState` / `InjectedStore` / `InjectedToolCallId` и функция `get_runtime()` помечены как legacy — для нового кода рекомендуется `ToolRuntime`. При этом `InjectedToolArg` и `InjectedState` продолжают работать.

Тот же `summarize`, переписанный под `ToolRuntime` (рекомендуемый способ для 1.x-агентов):

```python
from langchain.tools import tool, ToolRuntime

@tool
def summarize(query: str, runtime: ToolRuntime) -> str:
    """Summarize the conversation so far."""
    messages = runtime.state["messages"]
    return f"{len(messages)} messages about {query} (call {runtime.tool_call_id})"
```

Параметр `runtime` не входит в `args_schema` и не виден модели — фреймворк подставляет его автоматически при выполнении инструмента внутри агента/`ToolNode`.

### Лучшие практики

- Давайте инструментам говорящее имя и подробный docstring — это буквально «промпт» для выбора инструмента.
- Всегда указывайте type hints; для нетривиальных входов задавайте `args_schema` с `Field(description=...)`.
- Возвращайте компактный результат; тяжёлые данные — через `content_and_artifact`.
- Секреты и состояние передавайте через `InjectedToolArg` / `InjectedState` / `ToolRuntime`, а не как обычные аргументы модели.
- Ожидаемые сбои оформляйте через `ToolException` + `handle_tool_error`, чтобы агент не падал.
- Строго сохраняйте соответствие `tool_call_id` между `AIMessage.tool_calls` и `ToolMessage`.


---


## 7. Retrieval и RAG

**RAG** (Retrieval-Augmented Generation) — это приём, при котором перед вызовом LLM мы находим релевантные фрагменты внешних данных (документов) и подкладываем их в промпт как контекст. Так модель отвечает не «по памяти», а опираясь на ваши данные, что снижает галлюцинации и позволяет работать со свежей и приватной информацией.

Канонический pipeline состоит из двух фаз:

1. **Индексация (offline):** загрузка документов (loaders) → разбиение на чанки (splitters) → векторизация (embeddings) → сохранение в векторное хранилище (vector store).
2. **Извлечение и генерация (online):** запрос → поиск похожих чанков (retriever) → форматирование контекста → prompt → LLM → парсер.

> **О путях импортов.** Начиная с LangChain 0.2 пакет разбит на модули: базовые абстракции — в `langchain_core`, интеграции — в отдельных пакетах (`langchain_openai`, `langchain_chroma`, `langchain_community` и т. д.). В LangChain **1.0** (октябрь 2025) этот принцип усилен: устаревшие «цепочки» из старого `langchain.chains` (включая хелперы из раздела 7.8) вынесены в отдельный пакет **`langchain-classic`**, а в основной `langchain` добавлены `create_agent` и middleware. Установка для примеров ниже:
> `pip install langchain langchain-core langchain-community langchain-text-splitters langchain-openai langchain-chroma langchain-classic faiss-cpu pypdf beautifulsoup4`
> (пакет `langchain-classic` нужен только для готовых хелперов из 7.8; для DirectoryLoader с настройками по умолчанию дополнительно потребуется `unstructured`.)

### 7.1. Класс `Document`

`Document` — базовая единица данных во всём RAG-стеке. У него два ключевых поля:

- `page_content: str` — текст фрагмента;
- `metadata: dict` — произвольные метаданные (источник, страница, заголовок и т. п.), которые используются для цитирования и фильтрации при поиске.

```python
from langchain_core.documents import Document

doc = Document(
    page_content="LangGraph — библиотека для построения stateful-агентов на графах.",
    metadata={"source": "docs/intro.md", "page": 1, "topic": "langgraph"},
)

print(doc.page_content)          # текст
print(doc.metadata["source"])    # docs/intro.md
```

Есть также необязательное поле `id` (идентификатор в хранилище). Все loaders возвращают `list[Document]`, а все splitters и vector stores работают именно с этими объектами.

### 7.2. Загрузчики (Document Loaders)

Загрузчики читают данные из источника и возвращают `list[Document]`. Живут они в `langchain_community.document_loaders`. У каждого loader есть методы `.load()` (загрузить всё сразу) и `.lazy_load()` (ленивый генератор — предпочтителен для больших объёмов).

```python
from langchain_community.document_loaders import (
    WebBaseLoader,
    PyPDFLoader,
    DirectoryLoader,
)

# 1. Веб-страница (использует requests + BeautifulSoup4)
web_loader = WebBaseLoader("https://python.langchain.com/docs/introduction/")
web_docs = web_loader.load()

# 2. PDF: один Document на страницу, номер страницы попадает в metadata["page"]
pdf_loader = PyPDFLoader("./data/report.pdf")   # требует пакет pypdf
pdf_docs = pdf_loader.load()

# 3. Каталог файлов по маске
dir_loader = DirectoryLoader(
    "./data",
    glob="**/*.md",          # рекурсивно все .md
    show_progress=True,
)
dir_docs = dir_loader.load()
```

**Ключевые аргументы и заметки:**

- `WebBaseLoader` принимает как одну строку-URL, так и список URL. Параметр `bs_kwargs` позволяет передать настройки в `BeautifulSoup` (например, парсить только нужные теги через `SoupStrainer`), `header_template` — задать HTTP-заголовки.
- `PyPDFLoader` разбивает PDF постранично. Для сканов нужен OCR: `PyPDFLoader(..., extract_images=True)` прогоняет картинки через `rapidocr-onnxruntime` (пакет надо доустановить), либо берите специализированный loader.
- `DirectoryLoader` по умолчанию использует `UnstructuredLoader` (требует установленный пакет `unstructured`). Класс парсера можно заменить через `loader_cls`: например, `loader_cls=TextLoader` для простых текстов (не забудьте `loader_kwargs={"encoding": "utf-8"}`, иначе на Windows/UTF-8 бывают ошибки декодирования). Параметр `use_multithreading=True` ускоряет загрузку.

Всего в LangChain сотни loaders (CSV, Notion, S3, Confluence и т. д.) — все они возвращают унифицированный `Document`.

### 7.3. Сплиттеры: `RecursiveCharacterTextSplitter`

Целые документы почти всегда слишком велики для контекста модели и «размывают» эмбеддинг. Поэтому их режут на чанки. Рекомендуемый splitter по умолчанию — `RecursiveCharacterTextSplitter` из пакета `langchain_text_splitters`. Он пытается резать по «естественным» границам: сначала по абзацам (`\n\n`), затем по строкам (`\n`), словам (` `) и только в крайнем случае по символам — так контекст сохраняется максимально целостным.

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,        # макс. размер чанка (по умолчанию — в символах)
    chunk_overlap=200,      # «нахлёст» между соседними чанками
    add_start_index=True,   # записать позицию чанка в metadata["start_index"]
)

# split_documents сохраняет и переносит metadata исходных Document
chunks = splitter.split_documents(pdf_docs)

# split_text работает с «сырой» строкой и возвращает list[str]
raw_chunks = splitter.split_text("очень длинный текст ...")
```

**Ключевые аргументы:**

| Аргумент | Назначение |
| --- | --- |
| `chunk_size` | Верхняя граница размера чанка. |
| `chunk_overlap` | Сколько символов дублировать между чанками, чтобы не «разрывать» мысль на границе. Обычно 10–20% от `chunk_size`. |
| `separators` | Список разделителей в порядке приоритета (по умолчанию `["\n\n", "\n", " ", ""]`). |
| `length_function` | Функция измерения длины. По умолчанию `len` (символы). Для точного учёта токенов используйте `RecursiveCharacterTextSplitter.from_tiktoken_encoder(...)`. |
| `add_start_index` | Добавить смещение чанка в метаданные. |

**Лучшие практики:** нет «правильного» размера — подбирайте эмпирически (частая отправная точка — `chunk_size=1000`, `chunk_overlap=200`). Для кода есть фабрика `RecursiveCharacterTextSplitter.from_language(language=Language.PYTHON, ...)` (где `Language` импортируется из `langchain_text_splitters`), которая знает синтаксические границы конкретного языка.

### 7.4. Embeddings

Эмбеддинги превращают текст в вектор чисел; близкие по смыслу тексты дают близкие векторы. Интерфейс `Embeddings` имеет два метода: `embed_documents(list[str])` (для индексации) и `embed_query(str)` (для запроса).

```python
from langchain_openai import OpenAIEmbeddings

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
# ключ берётся из переменной окружения OPENAI_API_KEY

vec = embeddings.embed_query("Что такое RAG?")
print(len(vec))   # размерность вектора, напр. 1536
```

На практике `embed_documents`/`embed_query` редко вызывают вручную — их дергает vector store. Модель эмбеддингов должна быть **одна и та же** при индексации и при поиске. Локальные бесплатные альтернативы: `HuggingFaceEmbeddings` (пакет `langchain-huggingface`), `OllamaEmbeddings` (пакет `langchain-ollama`).

### 7.5. Векторные хранилища (Vector Stores)

Vector store хранит векторы и метаданные и умеет искать ближайших соседей. Основные способы создания:

- `VectorStore.from_documents(documents, embedding, ...)` — построить хранилище из готовых `Document`;
- `.add_documents(documents)` — дозаписать в существующее;
- `.similarity_search(query, k=4)` — вернуть `k` наиболее похожих `Document`;
- `.similarity_search_with_score(query, k=4)` — то же, но с оценкой близости.

#### `InMemoryVectorStore` — для разработки и тестов

Хранит всё в обычном словаре в памяти и считает косинусную близость через numpy. Не требует внешних зависимостей — идеален для прототипов и юнит-тестов.

```python
from langchain_core.vectorstores import InMemoryVectorStore

store = InMemoryVectorStore.from_documents(chunks, embedding=embeddings)
results = store.similarity_search("Как устроен pipeline RAG?", k=4)
for d in results:
    print(d.metadata.get("source"), "->", d.page_content[:80])
```

#### `Chroma` — локальная персистентная БД

Пакет `langchain-chroma` (актуальный путь импорта; старый `langchain_community.vectorstores.Chroma` устарел). Умеет сохранять данные на диск.

```python
from langchain_chroma import Chroma

vectorstore = Chroma.from_documents(
    documents=chunks,
    embedding=embeddings,               # в from_documents параметр называется embedding
    collection_name="my_docs",
    persist_directory="./chroma_db",    # данные сохранятся на диск
)

# Повторное открытие уже существующей коллекции без переиндексации:
vectorstore = Chroma(
    collection_name="my_docs",
    embedding_function=embeddings,      # в конструкторе — embedding_function
    persist_directory="./chroma_db",
)
```

> Примечание: в актуальных версиях явный вызов `vectorstore.persist()` больше не нужен (и удалён) — при указании `persist_directory` данные пишутся автоматически.

#### `FAISS` — быстрый локальный индекс от Meta

Пакет-зависимость: `faiss-cpu` (или `faiss-gpu`). Сохранение/загрузка — через `save_local`/`load_local`.

```python
from langchain_community.vectorstores import FAISS

db = FAISS.from_documents(chunks, embeddings)
db.save_local("faiss_index")

# Загрузка. allow_dangerous_deserialization=True обязателен, т.к. индекс
# десериализуется через pickle — используйте только для доверенных файлов.
db = FAISS.load_local(
    "faiss_index",
    embeddings,
    allow_dangerous_deserialization=True,
)
```

**Как выбирать:** `InMemoryVectorStore` — прототип/тесты; `FAISS` — быстрый локальный поиск без сервера; `Chroma` — локальная БД с удобным персистом и фильтрами; для продакшена рассмотрите `PGVector`, `Qdrant`, `Pinecone`, `Milvus` (интерфейс тот же).

### 7.6. Ретриверы (`as_retriever`)

`Retriever` — это унифицированный объект (`Runnable`), у которого есть метод `.invoke(query) -> list[Document]`. Любой vector store превращается в retriever методом `as_retriever()`. Ретривер — «мостик» между хранилищем и LCEL-цепочкой.

```python
retriever = vectorstore.as_retriever(
    search_type="similarity",          # "similarity" | "mmr" | "similarity_score_threshold"
    search_kwargs={"k": 4},            # сколько документов вернуть
)

docs = retriever.invoke("Что такое эмбеддинги?")   # list[Document]
```

**Параметры `as_retriever`:**

- `search_type`:
  - `"similarity"` (по умолчанию) — просто ближайшие соседи;
  - `"mmr"` (Maximal Marginal Relevance) — балансирует релевантность и разнообразие, чтобы избежать почти одинаковых чанков;
  - `"similarity_score_threshold"` — возвращает только документы выше порога.
- `search_kwargs` — словарь параметров поиска:
  - `k` — число документов;
  - `fetch_k` и `lambda_mult` — для MMR (`lambda_mult=0` — максимум разнообразия, `1` — максимум релевантности);
  - `score_threshold` — для порогового режима;
  - `filter` — фильтр по метаданным, например `{"topic": "langgraph"}`.

```python
retriever = vectorstore.as_retriever(
    search_type="mmr",
    search_kwargs={"k": 5, "fetch_k": 20, "lambda_mult": 0.5,
                   "filter": {"topic": "langgraph"}},
)
```

> Устаревшее: методы `vectorstore.get_relevant_documents(query)` и `retriever.get_relevant_documents(query)` признаны deprecated — используйте `.invoke(query)` (у ретривера — `Runnable`-интерфейс с `.invoke()`, `.ainvoke()`, `.batch()`).

### 7.7. Сборка RAG-цепочки на LCEL

LCEL (LangChain Expression Language) позволяет собрать RAG вручную из «кирпичиков» через оператор `|`. Это самый прозрачный и гибкий способ: вы полностью контролируете форматирование контекста и промпт. В LangChain 1.0 LCEL и `Runnable` остаются частью ядра и полностью поддерживаются.

```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

prompt = ChatPromptTemplate.from_messages([
    ("system",
     "Ты ассистент. Отвечай ТОЛЬКО на основе контекста ниже. "
     "Если ответа в контексте нет — скажи, что не знаешь.\n\nКонтекст:\n{context}"),
    ("human", "{question}"),
])

# Превращаем list[Document] в одну строку для подстановки в {context}
def format_docs(docs):
    return "\n\n".join(d.page_content for d in docs)

rag_chain = (
    {
        "context": retriever | format_docs,
        "question": RunnablePassthrough(),
    }
    | prompt
    | llm
    | StrOutputParser()
)

answer = rag_chain.invoke("Чем MMR отличается от обычного similarity-поиска?")
print(answer)
```

Что здесь происходит: входная строка-вопрос параллельно (а) уходит в `retriever`, чей результат прогоняется через `format_docs`, попадая в `{context}`, и (б) через `RunnablePassthrough()` попадает в `{question}`. Далее заполненный `prompt` идёт в `llm`, а `StrOutputParser` извлекает из ответа чистый текст. Поскольку это `Runnable`, цепочка «из коробки» поддерживает `.invoke()`, `.stream()`, `.batch()` и async-аналоги.

### 7.8. Готовые хелперы: `create_retrieval_chain` и `create_stuff_documents_chain`

Если не нужен полный ручной контроль, LangChain даёт две фабрики, которые собирают ту же логику короче.

> **Важно (LangChain 1.0+).** В релизе 1.0 (октябрь 2025) весь модуль `langchain.chains` вместе с этими фабриками переехал в отдельный пакет **`langchain-classic`**. Старый импорт `from langchain.chains import ...` в 1.0 больше не работает и даёт `ModuleNotFoundError: No module named 'langchain.chains'`. Поэтому:
> 1. поставьте пакет: `pip install langchain-classic`;
> 2. импортируйте из `langchain_classic.*` (см. код ниже).
>
> Сами фабрики продолжают поддерживаться, но для новых проектов LangChain рекомендует либо ручной LCEL (раздел 7.7), либо агентный (agentic) RAG — на LangGraph или через `create_agent` с retrieval-инструментом.

- **`create_stuff_documents_chain(llm, prompt)`** — «набивает» (stuff) все найденные документы в переменную `{context}` промпта и вызывает LLM. Промпт **обязан** содержать плейсхолдер `{context}` (имя переменной можно переопределить аргументом `document_variable_name`).
- **`create_retrieval_chain(retriever, combine_docs_chain)`** — оборачивает всё: берёт вход `{"input": ...}`, зовёт retriever, подставляет документы в document-chain. Возвращает dict с ключами `input`, `context` (найденные `Document`) и `answer`.

```python
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "Ответь на вопрос, используя контекст:\n\n{context}"),
    ("human", "{input}"),
])

combine_docs_chain = create_stuff_documents_chain(llm, prompt)
retrieval_chain = create_retrieval_chain(retriever, combine_docs_chain)

result = retrieval_chain.invoke({"input": "Что такое chunk_overlap?"})
print(result["answer"])           # ответ модели
print(result["context"])          # список Document-источников (удобно для цитирования)
```

**Когда что использовать:** ручной LCEL — когда нужен нестандартный формат контекста, свои метаданные в промпте или сложная маршрутизация; `create_*`-хелперы — для быстрого стандартного RAG, где важно из коробки получать список источников (`context`) для показа пользователю (учитывайте, что они живут в `langchain-classic`).

> Устаревшее: классы `RetrievalQA`, `ConversationalRetrievalChain`, `load_qa_chain` считаются legacy и в LangChain 1.0 тоже перенесены в `langchain-classic`. В новых проектах используйте LCEL или пару `create_retrieval_chain` + `create_stuff_documents_chain`, а для диалогового RAG с историей и инструментами — агентов на **LangGraph** (либо `create_agent` из основного пакета `langchain`).


---


## 8. Память и история сообщений

Языковые модели по своей природе **stateless** (без состояния): каждый вызов `invoke` независим, и модель «помнит» предыдущие реплики только потому, что мы сами передаём их в запросе. Чтобы бот вёл связный диалог, нужно где-то хранить историю сообщений и подмешивать её в следующий промпт. Именно это и называют «памятью» (memory). В экосистеме LangChain есть два поколения инструментов для этой задачи:

- **Legacy-подход** — классы `*Memory` (например `ConversationBufferMemory`) и обёртка `RunnableWithMessageHistory` поверх `BaseChatMessageHistory`. Они работают, но признаны устаревшими.
- **Современный подход** — персистентность **LangGraph** через checkpointer'ы (в том числе поверх готового агента `create_agent`). Именно её рекомендуют для всех новых проектов (см. раздел о персистентности и checkpointer'ах).

Ниже разбираем оба, начиная с фундамента — истории сообщений.

### 8.1. Концепция истории чата

История чата — это упорядоченный список объектов-сообщений (`HumanMessage`, `AIMessage`, `SystemMessage`, `ToolMessage`), привязанный к конкретной сессии/пользователю. Логика диалога всегда одинакова:

1. загрузить историю сессии;
2. добавить к ней новое сообщение пользователя;
3. отправить всю историю в модель;
4. получить ответ и дописать его в историю;
5. сохранить историю обратно в хранилище.

LangChain выделяет отдельную абстракцию для шагов «загрузить/сохранить» — `BaseChatMessageHistory`.

### 8.2. BaseChatMessageHistory и InMemoryChatMessageHistory

`BaseChatMessageHistory` — это абстрактный интерфейс хранилища сообщений одной сессии. Ключевые члены:

| Член | Назначение |
|------|-----------|
| `messages` (property) | вернуть все сообщения сессии как `list[BaseMessage]` |
| `add_message(message)` / `add_messages(messages)` | добавить одно/несколько сообщений |
| `add_user_message(...)`, `add_ai_message(...)` | хелперы для быстрого добавления |
| `clear()` | очистить историю |
| `aadd_messages`, `aget_messages`, `aclear` | асинхронные аналоги |

`InMemoryChatMessageHistory` — простейшая реализация, хранящая сообщения в оперативной памяти процесса. Удобна для тестов и прототипов, но данные теряются при перезапуске.

```python
from langchain_core.chat_history import (
    BaseChatMessageHistory,
    InMemoryChatMessageHistory,
)

history = InMemoryChatMessageHistory()
history.add_user_message("Привет! Меня зовут Аня.")
history.add_ai_message("Приятно познакомиться, Аня!")

print(history.messages)
# [HumanMessage(content='Привет! Меня зовут Аня.'),
#  AIMessage(content='Приятно познакомиться, Аня!')]
```

Для продакшена существуют персистентные реализации `BaseChatMessageHistory` в отдельных пакетах интеграций (например `RedisChatMessageHistory`, `SQLChatMessageHistory`, `PostgresChatMessageHistory`, `FileChatMessageHistory` и т.д.). Их API идентичен, меняется только бэкенд хранения. При необходимости легко написать свою реализацию: достаточно унаследоваться от `BaseChatMessageHistory` и реализовать `messages` и `add_messages`/`clear`.

### 8.3. RunnableWithMessageHistory

Вручную дёргать `history.messages` перед каждым вызовом и дописывать ответ — рутинно. `RunnableWithMessageHistory` автоматизирует это: оборачивает произвольный `Runnable` (обычно `prompt | model`) и на каждый вызов сам подгружает историю нужной сессии, подставляет её в вход, а после ответа дописывает и вопрос, и ответ обратно в хранилище.

**Импорт:**

```python
from langchain_core.runnables.history import RunnableWithMessageHistory
```

**Ключевые аргументы конструктора:**

| Аргумент | Что делает |
|----------|-----------|
| `runnable` | оборачиваемая цепочка (`prompt | model`) или сама модель |
| `get_session_history` | фабрика `(session_id) -> BaseChatMessageHistory`; вызывается на каждый `invoke` |
| `input_messages_key` | ключ во входном dict, куда кладётся новое сообщение пользователя |
| `history_messages_key` | ключ, под которым историю подставят в промпт (должен совпадать с `MessagesPlaceholder`) |
| `output_messages_key` | ключ выхода, если `runnable` возвращает dict (для моделей обычно не нужен) |
| `history_factory_config` | список `ConfigurableFieldSpec`, если ключ сессии сложнее одного `session_id` |

Полный рабочий пример с плейсхолдером для истории:

```python
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory

# Простое in-memory хранилище сессий (в проде — Redis/Postgres/...)
store: dict[str, InMemoryChatMessageHistory] = {}

def get_session_history(session_id: str) -> InMemoryChatMessageHistory:
    if session_id not in store:
        store[session_id] = InMemoryChatMessageHistory()
    return store[session_id]

prompt = ChatPromptTemplate.from_messages([
    ("system", "Ты дружелюбный ассистент. Отвечай кратко."),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{question}"),
])

model = ChatAnthropic(model="claude-sonnet-4-5")
chain = prompt | model

chain_with_history = RunnableWithMessageHistory(
    chain,
    get_session_history,
    input_messages_key="question",
    history_messages_key="history",
)

cfg = {"configurable": {"session_id": "user-42"}}

print(chain_with_history.invoke({"question": "Меня зовут Аня."}, config=cfg).content)
print(chain_with_history.invoke({"question": "Как меня зовут?"}, config=cfg).content)
# -> модель помнит имя, потому что история сессии "user-42" сохранена
```

**Как передаётся идентификатор сессии.** По умолчанию нужный ключ передаётся в `config` под `configurable.session_id`. Значение уходит в `get_session_history`, поэтому вызовы с разными `session_id` не пересекаются, а без `session_id` вы получите ошибку конфигурации.

**Несколько ключей идентификации.** Если сессия определяется парой значений (например `user_id` + `conversation_id`), переопределите `history_factory_config`:

```python
from langchain_core.runnables import ConfigurableFieldSpec

chain_with_history = RunnableWithMessageHistory(
    chain,
    get_session_history,  # теперь принимает (user_id, conversation_id)
    input_messages_key="question",
    history_messages_key="history",
    history_factory_config=[
        ConfigurableFieldSpec(
            id="user_id", annotation=str, name="User ID",
            description="Идентификатор пользователя", default="", is_shared=True,
        ),
        ConfigurableFieldSpec(
            id="conversation_id", annotation=str, name="Conversation ID",
            description="Идентификатор диалога", default="", is_shared=True,
        ),
    ],
)

cfg = {"configurable": {"user_id": "u1", "conversation_id": "c1"}}
```

**Типичные ошибки:**

- `history_messages_key` не совпадает с `variable_name` у `MessagesPlaceholder` — история «не долетает» до промпта.
- Забыли `input_messages_key` при dict-входе — обёртка не понимает, какое поле является новым сообщением.
- Не передали `session_id` (или кастомные ключи) в `configurable` — исключение.
- Общий `store` в памяти в многопроцессном/serverless-окружении не разделяется между воркерами — нужен внешний бэкенд.

> **Примечание об устаревании.** `RunnableWithMessageHistory` и старые классы `ConversationBufferMemory`, `ConversationBufferWindowMemory`, `ConversationSummaryMemory` и т.п. считаются legacy. `RunnableWithMessageHistory` помечен как deprecated (в его docstring прямо указано: удалить планируется в мажорной версии `2.0.0`, а вместо него рекомендована персистентность LangGraph). Для нового кода вместо них используйте persistence LangGraph — см. п. 8.5.

### 8.4. trim_messages — ограничение размера контекста

История растёт, и рано или поздно упирается в лимит контекстного окна модели (или в бюджет по стоимости). `trim_messages` обрезает список сообщений до заданного размера по токенам или по количеству сообщений.

**Импорт и сигнатура:**

```python
from langchain_core.messages import trim_messages
```

```python
trim_messages(
    messages,                 # список сообщений (или опустите, чтобы получить Runnable)
    *,
    max_tokens: int,          # верхняя граница
    token_counter,            # как считать: "approximate" | callable | чат-модель | len
    strategy: str = "last",   # "last" (оставить свежие) или "first" (оставить ранние)
    allow_partial: bool = False,
    include_system: bool = False,  # не выкидывать системное сообщение
    start_on=None,            # тип, с которого должна начинаться обрезанная история
    end_on=None,              # тип, на котором она должна заканчиваться
    text_splitter=None,
) -> list[BaseMessage]
```

**Про `token_counter`.** Можно передать:

- строку `"approximate"` — быстрый приближённый счётчик (внутри — `count_tokens_approximately`); идеален «на горячем пути», когда точность не критична;
- функцию `Callable[[list[BaseMessage]], int]` (или `Callable[[BaseMessage], int]`);
- саму чат-модель — тогда используется её `get_num_tokens_from_messages()` (точнее, но медленнее и может стоить запросов);
- `len` — чтобы считать не токены, а количество сообщений.

**Полезные флаги:** `include_system=True` сохраняет системный промпт даже при агрессивной обрезке; `start_on="human"` гарантирует, что усечённая история начнётся с человеческого сообщения (важно, чтобы не начинать с «висящего» `AIMessage`/`ToolMessage`); `end_on=("human", "tool")` отсекает всё после последнего сообщения нужного типа.

**Пример — прямой вызов:**

```python
from langchain_core.messages import (
    SystemMessage, HumanMessage, AIMessage, trim_messages,
)
from langchain_core.messages.utils import count_tokens_approximately

messages = [
    SystemMessage("Ты полезный ассистент."),
    HumanMessage("Привет!"),
    AIMessage("Здравствуйте!"),
    HumanMessage("Расскажи анекдот."),
    AIMessage("Заходит как-то Runnable в бар..."),
    HumanMessage("А ещё?"),
]

trimmed = trim_messages(
    messages,
    max_tokens=60,
    strategy="last",
    token_counter=count_tokens_approximately,  # или token_counter="approximate"
    include_system=True,
    start_on="human",
)
```

**Пример — как Runnable в цепочке.** Если вызвать `trim_messages` **без** аргумента `messages`, вернётся `Runnable`, который можно поставить в конвейер перед моделью:

```python
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model="gpt-4o-mini")

trimmer = trim_messages(
    max_tokens=64,
    strategy="last",
    token_counter=model,        # точный подсчёт токенами модели
    include_system=True,
    start_on="human",
)

chain = trimmer | model
chain.invoke(messages)
```

Тот же `trimmer` удобно вставлять внутрь цепочки, оборачиваемой `RunnableWithMessageHistory`, — так вы одновременно храните полную историю, но в модель отправляете только её «хвост», влезающий в контекст. Для очень длинных диалогов обрезки часто недостаточно — тогда применяют суммаризацию (сжатие старых сообщений в краткое резюме), но это уже за рамками `trim_messages`.

### 8.5. Рекомендация: персистентность LangGraph вместо legacy Memory

Для новых проектов LangChain официально рекомендует **не** использовать классы `*Memory` и `RunnableWithMessageHistory`, а строить диалог как граф LangGraph с **checkpointer'ом**. Checkpointer сам сохраняет всё состояние графа (включая список сообщений) после каждого шага и восстанавливает его по `thread_id`. Это даёт из коробки: персистентность, продолжение диалога, ветвление, time-travel и human-in-the-loop — без ручной возни с `get_session_history`.

Проще всего это получить на готовом агенте. В LangChain 1.0 фабрикой такого агента стала функция `create_agent` из пакета `langchain.agents` (она построена поверх LangGraph и добавляет систему middleware). Ранее для этой роли использовался `create_react_agent` из `langgraph.prebuilt`; в LangGraph 1.0 он объявлен **устаревшим (deprecated)** и заменён именно на `create_agent`, поэтому в новом коде импортируйте `create_agent`.

Минимальный пример:

```python
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver  # в проде: SqliteSaver / PostgresSaver

checkpointer = InMemorySaver()
agent = create_agent(
    model="anthropic:claude-sonnet-4-5",
    tools=[],
    checkpointer=checkpointer,
)

config = {"configurable": {"thread_id": "user-42"}}
agent.invoke({"messages": [{"role": "user", "content": "Меня зовут Аня."}]}, config)
agent.invoke({"messages": [{"role": "user", "content": "Как меня зовут?"}]}, config)
# агент помнит имя: состояние треда "user-42" восстановлено checkpointer'ом
```

Строка `model="anthropic:claude-sonnet-4-5"` в формате `"<провайдер>:<модель>"` разворачивается через `init_chat_model`; можно передать и уже созданный экземпляр модели, например `ChatAnthropic(model="claude-sonnet-4-5")`. Обратите внимание, что `checkpointer` обязателен — без него состояние между вызовами не сохранится, и `thread_id` в `config` тоже обязателен для восстановления треда.

Обратите внимание на терминологическую параллель: в legacy-подходе сессия задавалась `configurable.session_id`, а в LangGraph роль ключа диалога играет `configurable.thread_id`. Персистентные checkpointer'ы (`SqliteSaver` из `langgraph.checkpoint.sqlite`, `PostgresSaver` из `langgraph.checkpoint.postgres`) заменяют внешние реализации `BaseChatMessageHistory`. `trim_messages` при этом остаётся полезным и в LangGraph — его вызывают в middleware-хуке `before_model` (или в отдельном узле графа) перед обращением к модели, чтобы держать контекст в рамках лимита; для автоматической суммаризации истории у `create_agent` есть готовый `SummarizationMiddleware` из `langchain.agents.middleware`.

Подробно про checkpointer'ы, `thread_id`, сохранение и восстановление состояния — см. отдельный раздел о персистентности LangGraph.


---


## 9. LangGraph: введение, StateGraph, базовый пример

LangGraph — это библиотека для построения приложений на LLM в виде **графов вычислений с состоянием** (stateful graphs). Она входит в экосистему LangChain, но устанавливается и версионируется отдельно (`pip install langgraph`), а с LangChain интегрируется через общие типы сообщений (`langchain_core.messages`) и любые `Runnable`. LangGraph — это низкоуровневый «движок оркестрации»: он не навязывает готовую структуру агента, а даёт примитивы (узлы, рёбра, состояние, checkpointer), из которых собираются агенты, RAG-конвейеры, multi-agent системы и произвольные рабочие процессы.

### 9.1. Зачем графы, если есть цепочки и агенты

Линейная цепочка (`prompt | model | parser`, LCEL) прекрасно решает задачи вида «вход → серия преобразований → выход». Но как только логика перестаёт быть прямой, LCEL становится тесной:

- **Циклы.** Агент, который вызывает инструмент, смотрит на результат и решает вызвать ещё один инструмент, — это цикл `model → tools → model → ...`, повторяющийся неизвестное заранее число раз. В линейной цепочке цикла нет.
- **Ветвление и маршрутизация.** Нужно направить запрос по разным веткам в зависимости от классификации, наличия ошибки, доверия к ответу и т. п.
- **Управляемость (control).** Монолитный агент (например, старый `AgentExecutor`) — это «чёрный ящик»: внутренний цикл «думай-действуй» скрыт, вмешаться в него между шагами трудно. Граф, наоборот, делает каждый шаг явным узлом, поэтому им можно управлять.
- **Персистентность (persistence).** Граф умеет сохранять своё состояние после каждого шага через checkpointer, что даёт возможность продолжить прерванный диалог, откатиться назад (time-travel) и хранить память между сессиями.
- **Human-in-the-loop.** Благодаря персистентности выполнение можно поставить на паузу (`interrupt`), показать состояние человеку, дождаться правки или подтверждения и продолжить с того же места.
- **Стриминг.** Граф стримит не только токены модели, но и промежуточные обновления состояния и события узлов.

Вывод: если задача сводится к прямому конвейеру — берите LCEL. Как только появляются циклы, условная маршрутизация, долгоживущее состояние или контроль человека — это территория LangGraph.

### 9.2. Ключевые понятия

LangGraph оперирует четырьмя базовыми сущностями.

#### State (состояние)

**State** — это общая «доска», через которую узлы обмениваются данными. Схема состояния объявляется чаще всего как `TypedDict` (можно также `dataclass` или Pydantic `BaseModel`). Каждый узел получает текущее состояние и возвращает **частичное** обновление — словарь только с теми ключами, которые он хочет изменить.

Как именно применяется обновление, определяет **reducer** — функция слияния. По умолчанию reducer — это перезапись (новое значение затирает старое). Чтобы вместо перезаписи *накапливать* значения, ключ аннотируют через `Annotated[type, reducer]`. Самый частый reducer — `add_messages` из `langgraph.graph.message`: он добавляет новые сообщения к списку (а не заменяет его) и корректно обрабатывает ID и обновления сообщений.

```python
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class State(TypedDict):
    # add_messages -> новые сообщения ДОБАВЛЯЮТСЯ к списку
    messages: Annotated[list, add_messages]
    # без аннотации -> значение ПЕРЕЗАПИСЫВАЕТСЯ
    counter: int
```

#### Node (узел)

**Node** — это единица работы, обычная Python-функция (или `Runnable`). Сигнатура узла: первым аргументом — состояние, опционально `config: RunnableConfig` и (в LangGraph ≥ 0.6) `runtime: Runtime` (из `langgraph.runtime`) для доступа к run-scoped контексту (`runtime.context`). Обязателен только первый аргумент.

```python
def my_node(state: State) -> dict:
    # читаем состояние, возвращаем ЧАСТИЧНОЕ обновление
    return {"counter": state["counter"] + 1}
```

Ключевой принцип: узел **не мутирует** входное состояние на месте, а возвращает словарь-патч. Всё остальное (слияние через reducer) делает движок.

#### Edge (ребро)

**Edge** задаёт поток управления — какой узел выполнять следующим.

- `add_edge(a, b)` — статическое (безусловное) ребро: после `a` всегда идёт `b`.
- `add_conditional_edges(a, routing_fn, mapping)` — условное ребро: функция-маршрутизатор `routing_fn(state)` возвращает метку (или список меток), а `mapping` сопоставляет метку с именем следующего узла.

Специальные узлы `START` и `END` (импортируются из `langgraph.graph`) обозначают вход в граф и его завершение. Ребро `START → X` задаёт точку входа; ребро `Y → END` — точку выхода.

#### Компиляция

Сборка графа (`StateGraph`) — это только «чертёж». Перед запуском его нужно **скомпилировать** методом `.compile()`. Компиляция проверяет структуру (нет ли висящих узлов, задана ли точка входа), подключает checkpointer/interrupt-и и возвращает исполняемый объект `CompiledStateGraph`, который сам является `Runnable` — у него есть `invoke`, `stream`, `ainvoke`, `astream`, `batch` и т. д.

### 9.3. Ментальная модель: super-steps и передача сообщений (Pregel)

LangGraph под капотом реализует модель, вдохновлённую **Google Pregel** и BSP (Bulk Synchronous Parallel). Выполнение идёт дискретными тактами — **super-steps**:

1. В начале такта активны узлы, к которым «пришли сообщения» (по входящим рёбрам).
2. Все активные узлы такта выполняются **параллельно** и независимо, читая состояние на начало такта.
3. По завершении такта их обновления **слитно** применяются к состоянию (каждый ключ — своим reducer'ом). Только после этого начинается следующий такт, где активируются узлы-получатели.

Узел, не получивший ни одного «сообщения» в текущем такте, простаивает. Когда в очередной такт не активируется ни один узел (все пути дошли до `END`), граф завершается. Из этой модели следуют два практических вывода: во-первых, порядок применения обновлений внутри одного такта не гарантирован, поэтому для параллельно пишущих в один ключ узлов нужен коммутативный reducer; во-вторых, число тактов ограничено параметром `recursion_limit` (по умолчанию 25) — защита от бесконечных циклов.

### 9.4. Полный минимальный рабочий пример

Соберём граф из двух узлов: первый увеличивает счётчик и добавляет сообщение, второй — дописывает ещё одно сообщение.

```python
from typing import Annotated
from typing_extensions import TypedDict

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages


# 1. Схема состояния
class State(TypedDict):
    messages: Annotated[list, add_messages]
    counter: int


# 2. Узлы: принимают state, возвращают частичное обновление
def node_a(state: State) -> dict:
    return {
        "counter": state["counter"] + 1,
        "messages": [AIMessage(content="Привет из node_a")],
    }


def node_b(state: State) -> dict:
    return {
        "counter": state["counter"] + 1,
        "messages": [AIMessage(content=f"node_b видит counter={state['counter']}")],
    }


# 3. Сборка графа
builder = StateGraph(State)
builder.add_node("node_a", node_a)
builder.add_node("node_b", node_b)

builder.add_edge(START, "node_a")   # точка входа
builder.add_edge("node_a", "node_b")
builder.add_edge("node_b", END)     # точка выхода

# 4. Компиляция
graph = builder.compile()

# 5. Запуск
result = graph.invoke({
    "messages": [HumanMessage(content="старт")],
    "counter": 0,
})

print(result["counter"])            # -> 2
for m in result["messages"]:
    print(type(m).__name__, m.content)
```

`invoke` возвращает **финальное состояние целиком** (словарь по схеме `State`). Обратите внимание: благодаря reducer'у `add_messages` список `messages` накопил все три сообщения (исходное `HumanMessage` + два `AIMessage`), а не был перезаписан.

Чтобы наблюдать промежуточные обновления по мере выполнения, используйте стриминг:

```python
for chunk in graph.stream(
    {"messages": [HumanMessage(content="старт")], "counter": 0},
    stream_mode="updates",  # отдаёт {имя_узла: обновление} после каждого узла
):
    print(chunk)
```

Полезные режимы: `stream_mode="updates"` (что изменил каждый узел), `"values"` (полное состояние после каждого шага), `"messages"` (токены LLM по мере генерации). Можно передать и список режимов — тогда `stream` отдаёт кортежи `(mode, chunk)`.

#### Условная маршрутизация (короткий пример)

Ниже — отдельный самостоятельный фрагмент (не для того же `builder`, что выше: у одного узла нельзя одновременно держать безусловное ребро `add_edge("node_a", "node_b")` и условные рёбра из `node_a`).

```python
from typing import Literal


def router(state: State) -> Literal["node_b", "__end__"]:
    return "node_b" if state["counter"] < 3 else END


builder.add_conditional_edges("node_a", router)
```

Если функция-маршрутизатор возвращает имена узлов напрямую (как здесь), третий аргумент `mapping` не нужен; он требуется, когда `router` возвращает произвольные метки, которые надо сопоставить с узлами. Аннотация возврата `Literal[...]` не обязательна для работы, но помогает LangGraph нарисовать все возможные ветви на диаграмме (`END` — это строковая константа `"__end__"`, поэтому её и указывают в `Literal`).

### 9.5. Визуализация графа

У скомпилированного графа есть метод `get_graph()`, возвращающий его структуру, которую можно отрисовать в Mermaid:

```python
# ASCII/текст Mermaid — удобно логировать и вставлять в Markdown
print(graph.get_graph().draw_mermaid())

# PNG (bytes). В Jupyter:
from IPython.display import Image
Image(graph.get_graph().draw_mermaid_png())

# Либо сохранить в файл:
png_bytes = graph.get_graph().draw_mermaid_png()
with open("graph.png", "wb") as f:
    f.write(png_bytes)
```

По умолчанию `draw_mermaid_png()` рендерит диаграмму через публичный сервис mermaid.ink (`MermaidDrawMethod.API`, нужен доступ в интернет). Для оффлайн-рендеринга передайте `draw_method=MermaidDrawMethod.PYPPETEER` (потребует локального браузера/зависимостей). Метод `draw_mermaid_png` поддерживает и оформление: `curve_style`, `node_colors=NodeStyles(...)`, `background_color`, `padding`. Классы `MermaidDrawMethod`, `CurveStyle` и `NodeStyles` импортируются из `langchain_core.runnables.graph` (в старых версиях класс стилей назывался `NodeColors` — теперь это `NodeStyles`, при этом сам параметр по-прежнему называется `node_colors`).

### 9.6. Типичные ошибки и лучшие практики

- **Запуск без `compile()`.** У объекта `StateGraph` (builder) нет `invoke`. Исполняемым он становится только после `.compile()`.
- **Мутация состояния на месте.** Не делайте `state["messages"].append(...)`. Узел должен *возвращать* патч-словарь — движок сам сольёт его через reducer.
- **Забытый reducer для накопления.** Если ключ должен накапливаться (сообщения, документы, логи), обязательно аннотируйте его: `Annotated[list, add_messages]` или свой reducer `Annotated[list, operator.add]`. Иначе новое значение просто затрёт старое.
- **Возврат ключа не из схемы.** Обновление с ключом, которого нет в `State`, приведёт к ошибке — узлы могут писать только в объявленные поля.
- **Бесконечный цикл.** При циклах в графе следите за условием выхода; иначе на такте `recursion_limit` (по умолчанию 25) поднимется `GraphRecursionError`. Лимит меняется в конфиге: `graph.invoke(inp, {"recursion_limit": 50})` (именно на верхнем уровне config, не внутри `configurable`).
- **Точки входа/выхода.** Ребро от `START` задаёт вход; без него граф не знает, с чего начать. Более старые (legacy) методы `set_entry_point("x")` / `set_finish_point("x")` эквивалентны `add_edge(START, "x")` / `add_edge("x", END)` — в новом коде предпочитайте явные рёбра с `START`/`END`.

#### Заметки об устаревшем

- Раньше state-схему и типы контекста задавали позиционно и через `config_schema`. В LangGraph ≥ 0.6 параметр `config_schema` конструктора `StateGraph` **устарел** в пользу `context_schema` (доступ к run-scoped данным — через объект `Runtime` в сигнатуре узла: `runtime.context`), а совместимость сохраняется до v2.0. Для базовых графов, показанных выше, ничего из этого не требуется.
- Импорт `from langgraph.graph import StateGraph, START, END` — актуальный и стабильный. `add_messages` берётся из `langgraph.graph.message`.

Такой минимальный граф — фундамент для всего дальнейшего: добавляя узлы с вызовом LLM и инструментов, условные рёбра, checkpointer и `interrupt`, вы наращиваете из него полноценного агента, не теряя контроля над каждым шагом выполнения.


---


## 10. Состояние графа: схемы, Annotated, reducers

Состояние (state) — это центральное понятие `StateGraph`. Это структура данных, которую граф передаёт между узлами: каждый узел получает текущее состояние на вход и возвращает частичный апдейт, а среда исполнения LangGraph применяет этот апдейт к общему состоянию по правилам, заданным в схеме. Правильно спроектированная схема состояния определяет, какие поля (каналы) существуют, какого они типа, как объединяются конкурирующие записи и что попадает на вход/выход графа.

### 10.1. Определение схемы состояния

Схема — это класс, описывающий набор каналов состояния. LangGraph поддерживает три способа: `TypedDict`, Pydantic `BaseModel` и `dataclass`.

#### TypedDict (рекомендуемый вариант по умолчанию)

```python
from typing_extensions import TypedDict  # или from typing import TypedDict (Python 3.12+)

class State(TypedDict):
    foo: int
    bar: list[str]
```

`TypedDict` — самый лёгкий и быстрый вариант: это обычный `dict` во время исполнения, без валидации. Внутри узла состояние доступно как словарь: `state["foo"]`. Аннотации типов используются только для статической проверки и для извлечения reducers. Рекомендуется импортировать `TypedDict` из `typing_extensions`: на Python < 3.12 версия из стандартного `typing` не всегда корректно сохраняет метаданные `Annotated`, из-за чего reducer может не подхватиться.

#### dataclass

```python
from dataclasses import dataclass, field

@dataclass
class State:
    foo: int
    bar: list[str] = field(default_factory=list)  # значение по умолчанию
```

`dataclass` удобен, когда нужны значения по умолчанию. Обратите внимание: внутри узла к полям dataclass-состояния обращаются через атрибут — `state.foo`, а не `state["foo"]`.

#### Pydantic BaseModel

```python
from pydantic import BaseModel

class State(BaseModel):
    foo: int
    bar: list[str] = []
```

Pydantic даёт валидацию входных данных на этапе выполнения (в том числе рекурсивную для вложенных моделей), но с накладными расходами на производительность. Валидация срабатывает при входе в граф и при применении апдейтов узлов. Доступ к полям — тоже через атрибут: `state.foo`.

> Примечание. Высокоуровневая фабрика агентов `create_agent` из пакета `langchain` (LangChain 1.0) требует, чтобы схема состояния была `TypedDict`, наследующим `AgentState` (`from langchain.agents import AgentState`). Pydantic `BaseModel` и `dataclass` в качестве состояния агента она не поддерживает — это ограничение именно `create_agent`, а не самого `StateGraph`, где допустимы все три вида схем. (Функция `create_react_agent` из `langgraph.prebuilt` — устаревший предшественник `create_agent`.)

### 10.2. Reducers и `Annotated[type, reducer]`

По умолчанию (без reducer) апдейт узла **полностью перезаписывает** значение канала. Если узел вернул `{"foo": 2}`, старое значение `foo` заменяется на `2`.

Reducer — это функция `(current_value, update_value) -> new_value`, которая определяет, как объединить прежнее значение канала с новым. Reducer привязывается к каналу через `typing.Annotated`: первый аргумент — тип, второй — функция-reducer.

```python
from typing import Annotated
from typing_extensions import TypedDict
from operator import add

class State(TypedDict):
    foo: int                       # без reducer -> перезапись
    bar: Annotated[list[str], add] # reducer=operator.add -> конкатенация списков
```

Теперь при исходном `{"bar": ["hi"]}` и апдейте узла `{"bar": ["bye"]}` итог будет `{"bar": ["hi", "bye"]}`: `operator.add` для списков делает конкатенацию.

Reducer особенно важен, когда несколько узлов пишут в один канал параллельно (например, при веерном ветвлении/`Send`): без reducer это приведёт к ошибке `InvalidUpdateError` из-за конфликтующих одновременных записей, а с reducer типа `add` результаты аккуратно сольются.

#### Собственный reducer

Reducer — любая функция двух аргументов. Учтите, что при самой первой записи `current` может быть `None` (канал ещё не инициализирован), поэтому reducer должен это обрабатывать:

```python
from typing import Annotated
from typing_extensions import TypedDict

def merge_dicts(current: dict | None, update: dict) -> dict:
    return {**(current or {}), **update}

class State(TypedDict):
    counters: Annotated[dict, merge_dicts]
```

#### Reducer `add_messages`

Для каналов с сообщениями чата используют специализированный reducer `add_messages`. Он умнее простой конкатенации: добавляет новые сообщения в список, но при совпадении `id` — **заменяет** (или удаляет через `RemoveMessage`) существующее сообщение, а также автоматически десериализует переданные `dict`/кортежи `(role, content)` в объекты сообщений LangChain.

```python
from typing import Annotated
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage       # классический стабильный путь
# из свежих версий (LangChain 1.0) также доступно: from langchain.messages import AnyMessage
from langgraph.graph.message import add_messages

class GraphState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    llm_calls: int
```

### 10.3. Встроенный `MessagesState`

Так как канал `messages` встречается почти в каждом чат-графе, LangGraph предоставляет готовую схему `MessagesState` с единственным полем `messages: Annotated[list[AnyMessage], add_messages]`. Её удобно расширять наследованием, добавляя свои поля:

```python
from langgraph.graph import MessagesState

class State(MessagesState):
    documents: list[str]
    summary: str
```

Так вы получаете корректно настроенный канал `messages` «из коробки» и добавляете собственные каналы (`documents`, `summary`) рядом.

### 10.4. Как узлы возвращают частичные апдейты и как они мёржатся

Узел получает всё состояние, но возвращает **только те ключи, которые изменяет** — частичный словарь (partial update). Ключи, которых нет в возвращаемом словаре, остаются без изменений.

```python
def my_node(state: State) -> dict:
    # обновляем только 'messages'; 'documents' не трогаем
    return {"messages": [{"role": "assistant", "content": "готово"}]}
```

Здесь канал `messages` снабжён reducer'ом `add_messages`, поэтому переданный dict автоматически превратится в `AIMessage` и допишется к истории, а не перезапишет её.

Механика применения апдейта для каждого ключа:

- если у канала **есть** reducer — вызывается `reducer(current, update)` (например, `add_messages` дописывает сообщение);
- если reducer **нет** — значение канала перезаписывается целиком;
- ключи, отсутствующие в возвращённом словаре, сохраняют прежнее значение;
- вернуть `None` или пустой `dict` из узла — валидно и означает «ничего не менять».

Именно поэтому не нужно (и не следует) возвращать всё состояние целиком — достаточно дельты.

### 10.5. Значения по умолчанию

- **`TypedDict`** не поддерживает значения по умолчанию: если канал не пришёл во входных данных и ни один узел в него не записал, обращение к нему внутри узла даст `KeyError`. Универсальный приём — назначить каналу reducer, который подставляет дефолт при `current is None` (см. `merge_dicts` выше), либо гарантировать инициализацию в стартовом узле.
- **`dataclass`** — используйте `field(default_factory=list)` для изменяемых типов и обычные значения для неизменяемых.
- **Pydantic `BaseModel`** — задавайте дефолты прямо в объявлении поля (`bar: list[str] = []`), при этом Pydantic ещё и провалидирует значения.

### 10.6. Несколько схем: overall / input / output и приватные каналы

Внутреннее состояние графа может быть шире, чем то, что пользователь передаёт на вход и получает на выходе. LangGraph позволяет задать отдельные схемы:

- **overall (state\_schema)** — полная внутренняя схема, объединяющая все каналы;
- **input\_schema** — что принимает `invoke()` (входные ключи фильтруются по ней);
- **output\_schema** — что возвращает `invoke()` (выход фильтруется по ней);
- **приватные каналы** — промежуточные каналы, которыми обмениваются отдельные узлы; их не обязательно включать в overall-схему — достаточно, чтобы узел объявил такой канал в аннотации возвращаемого типа.

```python
from typing_extensions import TypedDict
from langgraph.graph import START, END, StateGraph

class InputState(TypedDict):
    user_input: str

class OutputState(TypedDict):
    graph_output: str

class OverallState(TypedDict):
    foo: str
    user_input: str
    graph_output: str

class PrivateState(TypedDict):
    bar: str

def node_1(state: InputState) -> OverallState:
    return {"foo": state["user_input"] + " name"}

def node_2(state: OverallState) -> PrivateState:
    # пишем в приватный канал 'bar' — он не входит в OverallState
    return {"bar": state["foo"] + " is"}

def node_3(state: PrivateState) -> OutputState:
    return {"graph_output": state["bar"] + " Lance"}

builder = StateGraph(
    OverallState,
    input_schema=InputState,
    output_schema=OutputState,
)
builder.add_node("node_1", node_1)
builder.add_node("node_2", node_2)
builder.add_node("node_3", node_3)
builder.add_edge(START, "node_1")
builder.add_edge("node_1", "node_2")
builder.add_edge("node_2", "node_3")
builder.add_edge("node_3", END)

graph = builder.compile()
print(graph.invoke({"user_input": "My"}))
# {'graph_output': 'My name is Lance'}
```

Ключевые моменты:

- узел может писать в любой канал общего состояния графа, даже если этого канала нет в его входной схеме;
- приватный канал (`bar`) становится доступен следующему узлу, который объявляет его в своей входной аннотации;
- на выходе `invoke()` вернёт только ключи из `output_schema` (`graph_output`), а `user_input`, `foo`, `bar` останутся внутренними.

### 10.7. Сигнатура конструктора `StateGraph` и устаревшие аргументы

Актуальная сигнатура (LangGraph v0.6+):

```python
from langgraph.graph import StateGraph

builder = StateGraph(
    state_schema,              # обязательный: полная (overall) схема состояния
    context_schema=None,       # опц. (2-й позиционный или kw): схема run-scoped контекста
    input_schema=None,         # опц., kw-only: схема входа
    output_schema=None,        # опц., kw-only: схема выхода
)
```

Точная сигнатура: `StateGraph(state_schema, context_schema=None, *, input_schema=None, output_schema=None)`. То есть `state_schema` и `context_schema` можно передавать позиционно, а `input_schema`/`output_schema` — только по ключевому имени (после `*`). Run-scoped контекст передаётся при запуске: `graph.invoke(inputs, context={...})`, а внутри узла доступен через объект `Runtime`.

| Параметр | Назначение |
|----------|------------|
| `state_schema` | Полная внутренняя схема (первый позиционный аргумент, обязателен) |
| `input_schema` | Ограничивает набор входных ключей `invoke()` |
| `output_schema` | Ограничивает набор возвращаемых `invoke()` ключей |
| `context_schema` | Тип неизменяемого run-scoped контекста (доступ через `Runtime`) |

Замечания об устаревшем:

- Старые ключевые имена `input=` и `output=` в конструкторе переименованы в `input_schema=` и `output_schema=`; прежние всё ещё принимаются как deprecated-алиасы, но в новом коде используйте `*_schema`.
- Аргумент `config_schema` объявлен устаревшим в v0.6.0 (поддержка будет удалена в v2.0.0) — вместо него применяйте `context_schema`.

### 10.8. Типичные ошибки и лучшие практики

- **`InvalidUpdateError` при параллельных записях в один канал.** Возникает, когда несколько узлов (или `Send`) одновременно пишут в канал без reducer. Решение — добавить reducer (`operator.add`, `add_messages` или свой).
- **`KeyError` при чтении неинициализированного канала (`TypedDict`).** Инициализируйте канал во входных данных/стартовом узле либо задайте reducer с дефолтом на `None`.
- **Возврат полного состояния вместо дельты.** Возвращайте из узла только изменённые ключи — это и корректнее, и эффективнее.
- **Мутация значений на месте.** Не мутируйте вложенные объекты состояния «на месте» — возвращайте новые значения; reducer должен возвращать новый объект, а не изменять `current`.
- **Смешение стилей доступа.** Для `TypedDict` — `state["foo"]`, для `dataclass`/Pydantic — `state.foo`; не путайте их.
- **Выбор схемы.** По умолчанию берите `TypedDict` (скорость), Pydantic — когда критична валидация входа, `dataclass` — когда нужны удобные значения по умолчанию.


---


## 11. Узлы, рёбра и маршрутизация

Граф в LangGraph — это ориентированный граф, вершины которого (узлы) выполняют работу, а рёбра задают, какой узел выполнится следующим. Логику строит `StateGraph`: вы добавляете узлы через `add_node`, соединяете их рёбрами через `add_edge` и `add_conditional_edges`, а затем вызываете `compile()`, чтобы получить исполняемый `Runnable`. В этом разделе разбираются сигнатура узла, все виды рёбер, класс `Command`, `Send` API для динамического fan-out и правила параллельного выполнения с reducer'ами.

### Узлы: `add_node`

Узел — это обычная Python-функция (или `Runnable`), которая получает текущее состояние и возвращает частичное обновление состояния.

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig


class State(TypedDict):
    question: str
    answer: str


def answer_node(state: State) -> dict:
    # Возвращаем ТОЛЬКО те ключи, которые надо обновить, а не всё состояние.
    return {"answer": f"Ответ на: {state['question']}"}


builder = StateGraph(State)
builder.add_node("answer", answer_node)   # явное имя
builder.add_node(answer_node)             # имя выведется из имени функции: "answer_node"
```

**Сигнатура узла.** Полная сигнатура — `node(state, config)`; оба варианта ниже допустимы, LangGraph по интроспекции определит, нужен ли узлу `config`:

```python
def node_a(state: State) -> dict: ...
def node_b(state: State, config: RunnableConfig) -> dict: ...
```

- `state` — текущее состояние (обычно `TypedDict`, `dataclass` или Pydantic-модель, объявленная в `StateGraph(State)`).
- `config` — `RunnableConfig`: содержит `configurable` (например `thread_id`), метаданные шага (`config["metadata"]["langgraph_step"]`), `callbacks` и т. п. Через него удобно пробрасывать зависимости, не попадающие в состояние.

В современных версиях LangGraph появился ещё один способ доступа к рантайму — тип `Runtime` (`from langgraph.runtime import Runtime`), который несёт `context`, `store` и `stream_writer` (а также `previous` и `execution_info`). Узел может принять его аргументом — `node(state, runtime)` или `node(state, config, runtime)` — либо получить внутри функции через `get_runtime()` (`from langgraph.runtime import get_runtime`). Это пришло на смену передаче произвольных данных через `config["configurable"]`: теперь статический контекст запуска задаётся типизированной схемой контекста.

**Что возвращает узел.** Словарь с обновлениями по ключам состояния. По умолчанию значение по ключу *перезаписывается*; если ключ снабжён reducer'ом (см. ниже), обновление комбинируется. Узел может вернуть `None` (пустое обновление) или, вместо словаря, объект `Command` (обновление + переход одновременно).

**Аргументы `add_node`.** Помимо `name` и функции, полезны:
- `metadata` — произвольные метаданные узла;
- `retry_policy` (`from langgraph.types import RetryPolicy`) — повтор узла при исключениях (можно передать и последовательность политик);
- `cache_policy` (`from langgraph.types import CachePolicy`) — кэширование результата узла (чтобы кэш реально работал, при компиляции нужно подключить бэкенд кэша: `builder.compile(cache=...)`);
- `defer=True` — отложить выполнение узла до завершения всех «веток» текущего супершага (полезно для fan-in/агрегации);
- `destinations` — подсказка о возможных целях (`dict` или кортеж имён) для визуализации, если узел возвращает `Command`.

**Типичные ошибки.** Возврат всего состояния вместо дельты (лишняя работа и конфликты); возврат неизвестного ключа (в strict-схемах будет ошибка); мутация `state` in-place вместо возврата нового словаря — состояние следует считать иммутабельным.

### Рёбра и константы `START` / `END`

`START` и `END` — служебные виртуальные узлы. `START` обозначает точку входа, `END` — завершение соответствующей ветки.

```python
from langgraph.graph import START, END
```

**Прямые (безусловные) рёбра — `add_edge`.** После узла-источника управление всегда переходит к узлу-приёмнику.

```python
builder.add_edge(START, "answer")   # точка входа
builder.add_edge("answer", END)     # завершение
```

Можно задать несколько исходящих рёбер из одного узла — тогда все приёмники выполнятся параллельно (см. раздел про fan-out). Есть и утилита `add_sequence([...])` для быстрого построения линейной цепочки узлов.

### Условные рёбра — `add_conditional_edges`

Когда следующий узел зависит от состояния, используют `add_conditional_edges(source, path, path_map=None)`. Функция-маршрутизатор `path` получает состояние (и, опционально, `config` / `runtime`) и возвращает имя следующего узла — либо список имён (тогда несколько веток запустятся параллельно).

```python
from typing import Literal


def route(state: State) -> Literal["retry", "finish"]:
    return "finish" if state["answer"] else "retry"


builder.add_conditional_edges("answer", route)
```

**`path_map`** сопоставляет «сырые» значения, возвращаемые маршрутизатором, с именами узлов. Это удобно, когда `route` возвращает булево, число или доменную метку, а также помогает LangGraph правильно построить граф для визуализации:

```python
def route(state: State) -> bool:
    return bool(state["answer"])


builder.add_conditional_edges(
    "answer",
    route,
    {True: "finish", False: "retry"},  # значение -> имя узла
)
```

Маршрутизатор может вернуть `END`, чтобы завершить ветку, или список (`["node_a", "node_b"]`) для параллельного запуска. `add_conditional_edges(START, route)` задаёт условную точку входа. Важно: каждый набор условных рёбер идентифицируется именем, которое по умолчанию берётся из имени функции `path`. Из одного источника можно задать несколько наборов условных рёбер, но с *разными* именами; повторный вызов для того же `source` с функцией того же имени вызовет `ValueError` (а не «тихо» перезапишет предыдущий набор).

### `Command`: обновление состояния и переход одновременно

Класс `Command` позволяет из тела узла одновременно обновить состояние (`update`) и указать следующий узел (`goto`), заменяя связку «узел + условное ребро». Импорт — из `langgraph.types` (`from langgraph.types import Command`); из `langgraph.graph` он не экспортируется.

```python
from typing import Literal
from langgraph.types import Command


def router_node(state: State) -> Command[Literal["retry", "finish"]]:
    if state["answer"]:
        return Command(update={"question": ""}, goto="finish")
    return Command(update={"answer": "retry"}, goto="retry")
```

Аннотация возвращаемого типа `Command[Literal[...]]` не обязательна для работы, но настоятельно рекомендуется: по ней LangGraph достраивает рёбра для отрисовки графа (иначе укажите `destinations` в `add_node`).

**Поля `Command`:**
- `update` — дельта состояния (как обычный возврат узла; уважает reducer'ы);
- `goto` — имя узла, список имён, `END` или объект(ы) `Send`;
- `graph` — в каком графе искать цель `goto`. По умолчанию текущий граф; `Command.PARENT` направляет в ближайший родительский граф (нужно для перехода из подграфа в узел родителя).

```python
def subgraph_node(state: State) -> Command[Literal["parent_next"]]:
    return Command(
        update={"answer": "из подграфа"},
        goto="parent_next",
        graph=Command.PARENT,   # цель — узел родительского графа
    )
```

`Command` также применяют для возобновления после `interrupt`: `graph.invoke(Command(resume=value), config)` передаёт значение в приостановленный узел (human-in-the-loop). Для этого граф должен быть скомпилирован с checkpointer'ом (`builder.compile(checkpointer=...)`), а в `config` — указан `thread_id`: без сохранённого состояния возобновить прерванный запуск нельзя.

**`Command` vs условные рёбра.** Берите `Command`, когда нужно *в одном узле* и обновить состояние, и решить, куда идти (особенно с переходом в родительский граф). Условные рёбра предпочтительны, когда маршрутизация — чистая функция состояния без побочного обновления, и вы хотите держать логику ветвления отдельно от узлов.

### `Send` API: динамический fan-out и map-reduce

`Send` (из `langgraph.types`) позволяет во время выполнения породить произвольное число экземпляров одного узла, каждому передав *своё* состояние. Число веток заранее не известно — классический map-reduce, где «map» распараллеливается, а «reduce» собирает результаты.

```python
import operator
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send


class OverallState(TypedDict):
    topics: list[str]
    jokes: Annotated[list[str], operator.add]   # reducer для сборки результатов


def continue_to_jokes(state: OverallState):
    # Для каждого элемента — отдельный вызов узла "generate_joke" со своим payload.
    return [Send("generate_joke", {"topic": t}) for t in state["topics"]]


def generate_joke(state: dict) -> dict:
    return {"jokes": [f"Шутка про {state['topic']}"]}


builder = StateGraph(OverallState)
builder.add_node("generate_joke", generate_joke)
builder.add_conditional_edges(START, continue_to_jokes)   # fan-out
builder.add_edge("generate_joke", END)
graph = builder.compile()
```

Ключевой момент: `Send("node_name", payload)` — это не общий `state`, а именно данные для конкретного экземпляра узла. Поэтому целевой узел получает свой `payload` как входное состояние (в примере он читает `state["topic"]`, хотя ключа `topic` нет в `OverallState`), а результаты сходятся обратно в общий ключ через reducer. `Send` можно возвращать из функции условного ребра или как значение `goto` внутри `Command`.

### Параллельные узлы (fan-out / fan-in) и reducer'ы

Если из одного узла выходит несколько рёбер (или маршрутизатор вернул список), все приёмники выполняются параллельно в рамках одного «супершага» (superstep). Их результаты применяются к состоянию в конце супершага. Пока ветки пишут в *разные* ключи, конфликтов нет. Но если несколько параллельных узлов пишут в *один и тот же* ключ, без reducer'а LangGraph бросит `InvalidUpdateError` — он не знает, как объединить конкурентные записи.

Reducer задаётся через `Annotated[тип, функция_слияния]` в схеме состояния:

```python
import operator
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage


class State(TypedDict):
    which: str
    aggregate: Annotated[list[str], operator.add]        # конкатенация списков
    messages: Annotated[list[AnyMessage], add_messages]  # умное слияние сообщений
```

- Без reducer'а — новое значение перезаписывает старое (последняя запись побеждает; при параллелизме — ошибка конфликта).
- `operator.add` — складывает/конкатенирует (списки, числа): идеально для сбора результатов fan-out.
- `add_messages` — специализированный reducer для истории чата: добавляет новые сообщения, дедуплицирует и обновляет по `id`, поддерживает `RemoveMessage`.

Для fan-in часто используют отдельный узел-агрегатор, к которому ведут рёбра из всех параллельных веток; чтобы он гарантированно выполнился после всех веток (в том числе разной длины), помечайте его `add_node(..., defer=True)`.

```python
builder.add_edge(START, "branch_a")
builder.add_edge(START, "branch_b")   # branch_a и branch_b идут параллельно
builder.add_edge("branch_a", "collect")
builder.add_edge("branch_b", "collect")  # fan-in в общий узел
builder.add_edge("collect", END)
```

**Лучшие практики.** Возвращайте из узлов минимальную дельту. Для любого ключа, в который могут писать параллельные ветки или несколько `Send`, обязательно задавайте reducer. Аннотируйте узлы, возвращающие `Command`, через `Command[Literal[...]]` — это и документация, и корректная визуализация графа. Разделяйте ответственность: чистую маршрутизацию оставляйте условным рёбрам, а совмещённое «обновить + перейти» отдавайте `Command`. И помните, что имена узлов в `goto`, `path_map` и `Send` должны точно совпадать с именами, под которыми узлы зарегистрированы в `add_node`.


---


## 12. Запуск и стриминг графа

После того как граф собран и скомпилирован (`graph = builder.compile(...)`), у вас есть объект `CompiledStateGraph`, который реализует стандартный интерфейс `Runnable` из `langchain_core`. Это значит, что запускать граф можно теми же методами, что и любую цепочку LangChain: `invoke`, `ainvoke`, `stream`, `astream`, `batch`, `astream_events`. Дополнительно у скомпилированного графа есть методы инспекции состояния (`get_state`, `get_state_history`, `update_state`), доступные только при подключённом чекпоинтере.

### 12.1. `invoke` / `ainvoke`

`graph.invoke(input, config=None, ...)` запускает граф синхронно от `START` до `END` и возвращает **финальное состояние целиком** (словарь, соответствующий вашей схеме `State`). `ainvoke` — его асинхронный аналог (`await graph.ainvoke(...)`).

```python
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict

class State(TypedDict):
    topic: str
    joke: str

def make_joke(state: State) -> dict:
    return {"joke": f"Шутка про {state['topic']}"}

builder = StateGraph(State)
builder.add_node("make_joke", make_joke)
builder.add_edge(START, "make_joke")
builder.add_edge("make_joke", END)
graph = builder.compile()

result = graph.invoke({"topic": "котов"})
print(result)          # {'topic': 'котов', 'joke': 'Шутка про котов'}
```

Ключевые моменты:

- На вход подаётся `input` в формате входной схемы графа. Значения по умолчанию/каналы, которых нет во входе, заполняются автоматически.
- Возвращается **только последнее** значение состояния. Если нужны промежуточные шаги — используйте `stream` (см. ниже) или `get_state_history`.
- `invoke` внутри — это, по сути, `stream(..., stream_mode="values")` с возвратом последнего элемента.

### 12.2. `config`: `configurable`, `recursion_limit`, `thread_id`

Вторым позиционным аргументом всех методов запуска идёт `config` — словарь `RunnableConfig`. Наиболее важные ключи:

| Ключ | Назначение |
|------|-----------|
| `configurable` | Произвольные runtime-параметры. Здесь живёт `thread_id` (идентификатор диалога для чекпоинтера), а также любые ваши настраиваемые значения. |
| `recursion_limit` | Максимальное число «супершагов» (итераций) графа. **По умолчанию 25.** Это *верхнеуровневый* ключ, а не часть `configurable`. |
| `tags`, `metadata`, `run_name` | Метаданные для трассировки (LangSmith), фильтрации событий. |
| `callbacks` | Список колбэков LangChain. |

```python
config = {
    "configurable": {"thread_id": "session-42", "user_id": "u-7"},
    "recursion_limit": 50,
}
result = graph.invoke({"topic": "котов"}, config=config)
```

`thread_id` обязателен, если граф скомпилирован с чекпоинтером — именно по нему сохраняется и восстанавливается состояние диалога.

`recursion_limit` защищает от бесконечных циклов. При превышении лимита выбрасывается `GraphRecursionError`:

```python
from langgraph.errors import GraphRecursionError

try:
    graph.invoke({"topic": "котов"}, config={"recursion_limit": 10})
except GraphRecursionError:
    print("Граф не завершился за 10 шагов")
```

> **Примечание о доступе к config внутри узла.** Чтобы прочитать `configurable` внутри узла, добавьте узлу аргумент `config: RunnableConfig`. В актуальных версиях LangGraph для типизированных runtime-зависимостей появился отдельный механизм `Runtime`/`context`: схема задаётся при компиляции (`builder.compile(..., context_schema=Context)`, где `Context` — датакласс), само значение передаётся аргументом `context=` в `invoke`/`stream` (`graph.invoke(input, context=Context(user_id="u-7"))`), а внутри узла читается через параметр `runtime: Runtime[Context]` (доступ — `runtime.context`). Это пришло на смену передаче статических зависимостей через `config["configurable"]`. При этом `recursion_limit` по-прежнему передаётся через `config`, а не через `context`.

### 12.3. `stream` / `astream` и параметр `stream_mode`

`graph.stream(input, config=None, *, stream_mode="values", ...)` возвращает итератор, который выдаёт данные по мере выполнения графа. `astream` — асинхронная версия (`async for chunk in graph.astream(...)`). Параметр `stream_mode` определяет, **что именно** выдаётся.

| `stream_mode` | Что выдаётся |
|---------------|--------------|
| `"values"` | Полное состояние графа после каждого шага (по умолчанию). |
| `"updates"` | Только дельта — что вернул очередной узел: `{"имя_узла": {изменённые_поля}}`. |
| `"messages"` | Кортежи `(message_chunk, metadata)` — потоковые токены LLM. |
| `"custom"` | Произвольные данные, отправленные из узла через `get_stream_writer()`. |
| `"checkpoints"` | События сохранения чекпоинтов — состояние после очередного супершага (payload по смыслу совпадает с тем, что отдаёт `get_state`). |
| `"tasks"` | События старта и завершения задач узлов (вход задачи и её результат). |
| `"debug"` | Максимально подробная отладочная информация о каждом шаге. |

(`"checkpoints"` и `"tasks"` — более новые режимы; ранее эти события были доступны только внутри `"debug"`.)

#### `"values"` — полное состояние

```python
for state in graph.stream({"topic": "котов"}, stream_mode="values"):
    print(state)   # весь словарь State после каждого шага
```

#### `"updates"` — только изменения

Удобно, когда важно, *какой узел* и *что именно* обновил:

```python
for chunk in graph.stream({"topic": "котов"}, stream_mode="updates"):
    for node_name, update in chunk.items():
        print(node_name, "->", update)
```

#### Несколько режимов одновременно

Если передать `stream_mode` списком, каждый выдаваемый элемент становится кортежем `(mode, chunk)`, где `mode` — строка с именем режима:

```python
for mode, chunk in graph.stream(
    {"topic": "котов"},
    stream_mode=["updates", "custom", "messages"],
):
    if mode == "updates":
        print("UPDATE:", chunk)
    elif mode == "custom":
        print("CUSTOM:", chunk)
    elif mode == "messages":
        message_chunk, metadata = chunk
        print("TOKEN:", message_chunk.content)
```

> Для одиночного режима префикс `mode` **не** добавляется — выдаётся сам `chunk` (кроме `"messages"`, который всегда является 2-кортежем `(chunk, metadata)`).

> Стриминг из подграфов: передайте `subgraphs=True`, тогда каждый элемент получит дополнительный префикс-namespace (кортеж), указывающий, из какого подграфа пришли данные.

> **Новее (опционально).** В актуальных версиях у `stream`/`astream` появился параметр `version`. По умолчанию сохраняется классическое поведение, описанное выше. При `version="v2"` каждый выдаваемый элемент — единый словарь `StreamPart` вида `{"type": <режим>, "ns": <namespace>, "data": <данные>}`, и режимы тогда различают по `chunk["type"]`, а не по позиции в кортеже. Все примеры ниже используют поведение по умолчанию.

#### `"messages"` — потоковая передача токенов LLM

Режим `"messages"` перехватывает токены **любой** LLM внутри графа (в любом узле) и выдаёт их по мере генерации. Каждый элемент — кортеж `(message_chunk, metadata)`:

- `message_chunk` — объект `AIMessageChunk` (у него есть `.content`, чанки можно складывать через `+`);
- `metadata` — словарь с контекстом, важнейшие поля: `metadata["langgraph_node"]` (из какого узла) и `metadata["tags"]`.

```python
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

model = ChatOpenAI(model="gpt-4o-mini")

def call_model(state: State) -> dict:
    resp = model.invoke([HumanMessage(content=f"Расскажи про {state['topic']}")])
    return {"joke": resp.content}

# ... сборка графа с узлом call_model ...

for message_chunk, metadata in graph.stream(
    {"topic": "котов"},
    stream_mode="messages",
):
    if metadata["langgraph_node"] == "call_model" and message_chunk.content:
        print(message_chunk.content, end="", flush=True)
```

Обратите внимание: даже если внутри узла вызывается `model.invoke(...)` (а не `model.stream(...)`), в режиме `"messages"` LangGraph всё равно перехватывает токены через колбэки и отдаёт их по мере генерации. Фильтрация по `metadata["langgraph_node"]` или по `tags` (`model.with_config(tags=["joke_llm"])`) позволяет выводить токены только от нужной модели, если LLM в графе несколько. При этом провайдер должен поддерживать стриминг — для `ChatOpenAI` токены приходят автоматически, но некоторые модели требуют явного `streaming=True`.

#### `"custom"` — стриминг произвольных данных через `get_stream_writer()`

Иногда нужно транслировать наружу собственный прогресс: «загружаю документы», «обработано 3 из 10» и т.п. Для этого внутри узла берут writer и вызывают его как функцию:

```python
from langgraph.config import get_stream_writer

def process(state: State) -> dict:
    writer = get_stream_writer()
    writer({"status": "начал обработку"})
    for i in range(3):
        writer({"progress": i})
    writer({"status": "готово"})
    return {"joke": "..."}

for chunk in graph.stream({"topic": "котов"}, stream_mode="custom"):
    print(chunk)   # {'status': 'начал обработку'}, {'progress': 0}, ...
```

Альтернатива — объявить у узла аргумент `writer: StreamWriter`; LangGraph подставит его сам. Этот вариант работает в том числе на Python < 3.11 в async-коде, где `get_stream_writer()` может не находить контекст:

```python
from langgraph.types import StreamWriter

def process(state: State, writer: StreamWriter) -> dict:
    writer({"status": "работаю"})
    return {"joke": "..."}
```

> **Актуальность импорта.** Функция берётся из `langgraph.config`: `from langgraph.config import get_stream_writer`. Тип `StreamWriter` — из `langgraph.types`. Оба доступны в текущих версиях LangGraph. Вызов writer'а — это no-op, если граф запущен не в режиме `stream_mode="custom"` (или без него в списке режимов). В новом API тот же writer доступен и как `runtime.stream_writer` при использовании механизма `Runtime`.

#### `"debug"` — подробная трассировка

Режим `"debug"` выдаёт события с полями `type` (`"task"`, `"task_result"`, `"checkpoint"`), `timestamp`, `step` и `payload`. Полезен для отладки порядка выполнения узлов и содержимого чекпоинтов:

```python
for event in graph.stream({"topic": "котов"}, stream_mode="debug"):
    print(event["type"], event["step"])
```

### 12.4. `astream_events` (кратко)

`astream_events` — низкоуровневый асинхронный API, отдающий **все** события жизненного цикла каждого `Runnable` внутри графа: старт/поток/конец моделей, инструментов, узлов, парсеров. Указывайте `version="v2"`:

```python
async for event in graph.astream_events({"topic": "котов"}, version="v2"):
    kind = event["event"]
    if kind == "on_chat_model_stream":
        chunk = event["data"]["chunk"]
        if chunk.content:
            print(chunk.content, end="", flush=True)
```

Имена событий имеют вид `on_[тип]_(start|stream|end)`: `on_chat_model_stream` — токен LLM, `on_tool_start`/`on_tool_end` — вызовы инструментов, `on_chain_start` — вход в узел. Каждый event содержит `event["name"]`, `event["data"]`, `event["metadata"]` (в т.ч. `langgraph_node`), `event["tags"]`. Для большинства практических задач `stream_mode="messages"` проще и достаточен; `astream_events` берут, когда нужна максимально гранулярная картина (например, отдельно ловить вызовы инструментов и токены).

> **Про `version`.** В актуальных версиях `langchain-core` значение `version="v2"` используется **по умолчанию**, но указывать его явно — по-прежнему хорошая практика. Формат `"v1"` устарел и подлежит удалению; кроме того, в свежих версиях появился новый (пока экспериментальный) `"v3"` с протоколом на основе content-block'ов, но для большинства задач нужен именно `"v2"`.

### 12.5. Инспекция состояния: `get_state` и `get_state_history`

Эти методы работают только при скомпилированном с чекпоинтером графе и требуют `thread_id` в `configurable`.

`graph.get_state(config)` возвращает **текущий** снимок состояния потока — объект `StateSnapshot`:

```python
from langgraph.checkpoint.memory import InMemorySaver

graph = builder.compile(checkpointer=InMemorySaver())
config = {"configurable": {"thread_id": "session-42"}}
graph.invoke({"topic": "котов"}, config=config)

snapshot = graph.get_state(config)
print(snapshot.values)   # текущее состояние (словарь)
print(snapshot.next)     # кортеж узлов, которые выполнятся следующими
```

Поля `StateSnapshot`:

| Поле | Значение |
|------|----------|
| `values` | Текущие значения состояния (словарь). |
| `next` | Кортеж имён узлов, запланированных к выполнению следующими (пусто, если граф завершён). |
| `config` | Config этого снимка, включая `checkpoint_id`. |
| `metadata` | Метаданные чекпоинта (`source`, `step`, `writes` и т.д.). |
| `created_at` | Временная метка создания. |
| `parent_config` | Config родительского (предыдущего) чекпоинта. |
| `tasks` | Кортеж `PregelTask` — запланированные задачи, в т.ч. прерывания (`interrupts`). |

`graph.get_state_history(config)` возвращает итератор снимков `StateSnapshot` **в обратном порядке** (от самого свежего к самому раннему). Это основа для отладки, «отмотки» (time-travel) и возобновления:

```python
for snap in graph.get_state_history(config):
    print(snap.metadata["step"], snap.values, "next:", snap.next)
```

Чтобы возобновить выполнение с конкретной точки, возьмите `config` нужного снимка (в нём есть `checkpoint_id`) и передайте его в `invoke`/`stream`:

```python
history = list(graph.get_state_history(config))
target = history[2]                        # какой-то прошлый чекпоинт
graph.invoke(None, config=target.config)   # продолжить с этого состояния
```

Передача `None` в качестве входа означает «не давать новый вход, продолжить с сохранённого состояния» — типичный приём при возобновлении после прерывания (`interrupt`) или при time-travel. Асинхронные аналоги: `aget_state` и `aget_state_history`.

### 12.6. Практические заметки и типичные ошибки

- **`stream` не «показывает токены» сам по себе.** По умолчанию `stream_mode="values"`/`"updates"` выдаёт состояние после каждого *узла*, а не токены. Для токенов нужен `stream_mode="messages"` или `astream_events`.
- **Нет `thread_id` при чекпоинтере** → ошибка вроде `ValueError: Checkpointer requires ... thread_id`. Всегда кладите `thread_id` в `configurable`.
- **`recursion_limit` не в `configurable`.** Кладите его на верхний уровень `config`, иначе он будет проигнорирован, и вы получите дефолтные 25 шагов.
- **`GraphRecursionError`** обычно означает реальный бесконечный цикл в логике условных рёбер, а не слишком маленький лимит — сначала проверьте условия завершения, и только потом повышайте лимит.
- **Устаревшее.** Ранее для custom-стриминга использовали только инъекцию `writer: StreamWriter`; сейчас предпочтителен `get_stream_writer()` (из `langgraph.config`). Для `astream_events` используйте `version="v2"` (сейчас это значение по умолчанию) — `"v1"` устарел и подлежит удалению. Классы чекпоинтеров тоже переименовывались (`MemorySaver` → `InMemorySaver`, при этом старое имя пока сохранено как алиас); проверяйте актуальные импорты `langgraph.checkpoint.*` под вашу версию.


---


## 13. Персистентность и чекпоинтеры

Персистентность в LangGraph — это встроенный слой сохранения состояния графа. Она реализуется через объект-**checkpointer**, который вы передаёте в `compile()`. Как только у скомпилированного графа появляется чекпоинтер, LangGraph после **каждого супершага** (super-step) автоматически сохраняет полный снимок состояния (checkpoint) в хранилище. Именно этот механизм превращает граф из «однократной функции» в объект с памятью, который умеет продолжать разговор, возобновляться после сбоя, приостанавливаться для участия человека и «путешествовать во времени».

### 13.1. Зачем нужен checkpointer

Чекпоинтер лежит в основе сразу нескольких ключевых возможностей LangGraph:

- **Память потока (thread-level memory).** Состояние сохраняется под ключом `thread_id`. Повторный вызов графа с тем же `thread_id` подхватывает предыдущее состояние (например, накопленную историю `messages`), поэтому модель «помнит» диалог между запросами.
- **Возобновление после сбоя (durable execution).** Если процесс упал в середине выполнения, при следующем запуске граф стартует не с нуля, а с последнего успешного чекпоинта.
- **Human-in-the-loop (HITL).** Прерывания (`interrupt()` / `interrupt_before` / `interrupt_after`) требуют сохранения состояния: граф останавливается, ждёт ввода человека и позже возобновляется ровно с той же точки. Без чекпоинтера прерывания невозможны.
- **Time travel (путешествие во времени).** Можно получить всю историю чекпоинтов, вернуться к любому из них и «переиграть» ветку выполнения с другими данными.

> Важно различать два слоя памяти. **Checkpointer** — это память *внутри одного потока* (`thread_id`): состояние графа, история шагов. Для памяти *между потоками* (например, факты о пользователе, общие для всех его диалогов) используется отдельный интерфейс **Store** (`langgraph.store.*`), который передаётся в `compile(store=...)`. В этом разделе речь только о чекпоинтерах.

### 13.2. InMemorySaver (MemorySaver)

Самый простой чекпоинтер держит все данные в оперативной памяти процесса. Он идеален для юнит-тестов, прототипов и примеров в ноутбуках, но **теряет всё при перезапуске** и не годится для продакшена.

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, MessagesState

def chatbot(state: MessagesState):
    # ... вызов LLM ...
    return {"messages": [("ai", "Привет!")]}

builder = StateGraph(MessagesState)
builder.add_node("chatbot", chatbot)
builder.add_edge(START, "chatbot")

checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": "user-42"}}
graph.invoke({"messages": [("user", "Меня зовут Боб")]}, config)
# Второй вызов с тем же thread_id — состояние помнит первый:
graph.invoke({"messages": [("user", "Как меня зовут?")]}, config)
```

> **Об именах.** `MemorySaver` — это исторический алиас; в актуальных версиях канонический класс называется `InMemorySaver` (оба импортируются из `langgraph.checkpoint.memory`). В новом коде предпочтительнее `InMemorySaver`.

`InMemorySaver` входит в базовый пакет `langgraph-checkpoint` (устанавливается вместе с `langgraph`), отдельная зависимость не нужна. Он поддерживает и синхронный, и асинхронный API (`ainvoke`, `astream`), поэтому его удобно использовать в тестах любого стиля.

### 13.3. Персистентные чекпоинтеры

Для реального сохранения между перезапусками используются чекпоинтеры на базе БД. Они лежат в отдельных пакетах, которые нужно установить дополнительно.

| Чекпоинтер | Импорт | Пакет (pip) | Когда использовать |
|---|---|---|---|
| `InMemorySaver` / `MemorySaver` | `langgraph.checkpoint.memory` | `langgraph-checkpoint` (встроен) | Тесты, прототипы |
| `SqliteSaver` | `langgraph.checkpoint.sqlite` | `langgraph-checkpoint-sqlite` | Локальная разработка, embedded-приложения |
| `AsyncSqliteSaver` | `langgraph.checkpoint.sqlite.aio` | `langgraph-checkpoint-sqlite` | То же, но в async-коде (`aiosqlite`) |
| `PostgresSaver` | `langgraph.checkpoint.postgres` | `langgraph-checkpoint-postgres` | Продакшен |
| `AsyncPostgresSaver` | `langgraph.checkpoint.postgres.aio` | `langgraph-checkpoint-postgres` | Продакшен, async-серверы |

#### SqliteSaver / AsyncSqliteSaver

```python
from langgraph.checkpoint.sqlite import SqliteSaver

# from_conn_string возвращает КОНТЕКСТНЫЙ МЕНЕДЖЕР, а не сам saver:
with SqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "user-42"}}
    graph.invoke({"messages": [("user", "Привет")]}, config)
```

Строка `":memory:"` создаёт SQLite-базу в оперативной памяти (полезно для тестов, но без персистентности между процессами). Асинхронный вариант работает поверх `aiosqlite`:

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

async with AsyncSqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)
    await graph.ainvoke({"messages": [("user", "Привет")]},
                        {"configurable": {"thread_id": "user-42"}})
```

Если вы создаёте соединение сами (без `from_conn_string`), можно передать объект `sqlite3.Connection` прямо в конструктор: `SqliteSaver(conn)`. При этом задавайте `check_same_thread=False`, если граф вызывается из разных потоков.

#### PostgresSaver / AsyncPostgresSaver

Для продакшена рекомендуется Postgres. Требуется установленный `psycopg` (v3). При ручном создании соединения обязательно указывайте `autocommit=True` и `row_factory=dict_row`.

```python
from langgraph.checkpoint.postgres import PostgresSaver

DB_URI = "postgresql://user:pass@localhost:5432/mydb?sslmode=disable"

with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup()          # ОБЯЗАТЕЛЬНО при первом запуске!
    graph = builder.compile(checkpointer=checkpointer)
    graph.invoke({"messages": [("user", "Привет")]},
                 {"configurable": {"thread_id": "user-42"}})
```

Асинхронный вариант:

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
    await checkpointer.setup()    # await для async-версии
    graph = builder.compile(checkpointer=checkpointer)
    await graph.ainvoke({"messages": [("user", "Привет")]},
                        {"configurable": {"thread_id": "user-42"}})
```

#### Метод .setup() — когда он нужен

Здесь важно различать Postgres- и SQLite-чекпоинтеры — требования к `.setup()` у них разные.

**Postgres (`PostgresSaver` / `AsyncPostgresSaver`) требует однократного явного вызова `.setup()`** перед первым использованием: он создаёт нужные таблицы (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`) и накатывает миграции схемы. Если пропустить `.setup()`, первый же запрос упадёт с ошибкой вроде `relation "checkpoints" does not exist`.

**SQLite (`SqliteSaver` / `AsyncSqliteSaver`) вызывать `.setup()` вручную не нужно.** Эти чекпоинтеры создают таблицы автоматически (лениво) при первом же обращении к БД — вызов `setup()` зашит внутрь их методов (`get`/`put`/`list` и async-аналогов). Явный вызов не является ошибкой (он идемпотентен), но и не требуется; в исходниках он помечен как внутренний («should not be called directly by the user»). Именно поэтому в примере с `SqliteSaver` выше `.setup()` нигде не вызывается — и это корректно.

Типичные ошибки:

- **Postgres: забыли `.setup()`** → отсутствуют таблицы, первый же запрос падает с `relation "checkpoints" does not exist`. Вызывайте `.setup()` один раз при инициализации приложения (повторные вызовы безопасны, миграции идемпотентны).
- **Для async-Postgres забыли `await checkpointer.setup()`** → корутина не выполнится и таблицы не создадутся.
- **Postgres без `autocommit=True`** при ручном соединении → `setup()` не зафиксирует создание таблиц.
- **`from_conn_string(...)` использован без `with`** → вы получите контекстный менеджер, а не сам чекпоинтер; соединение не откроется. Всегда оборачивайте в `with` / `async with` или управляйте жизненным циклом соединения вручную.

> В долгоживущем веб-сервере (FastAPI и т. п.) не открывайте `with`-блок на каждый запрос. Создайте пул соединений (`psycopg_pool.ConnectionPool` / `AsyncConnectionPool`), передайте его в `PostgresSaver(pool)` один раз при старте, вызовите `setup()`, и переиспользуйте на всё время жизни приложения.

### 13.4. thread_id и конфигурация

Каждый вызов графа с чекпоинтером **обязан** содержать `thread_id` в `config`:

```python
config = {"configurable": {"thread_id": "any-string-id"}}
graph.invoke(inputs, config)
```

`thread_id` — это идентификатор «беседы» или «сессии»: все чекпоинты одного потока связаны в цепочку. Разные `thread_id` полностью изолированы друг от друга. Практические замечания: для Postgres держите `thread_id` короче 255 символов; генерируйте их через `uuid4()` для новых сессий; забытый `thread_id` при наличии чекпоинтера приведёт к ошибке.

Дополнительно в `configurable` можно указать `checkpoint_id` (конкретный снимок) и `checkpoint_ns` (пространство имён, используется для вложенных подграфов; по умолчанию `""`).

### 13.5. StateSnapshot: чтение состояния

Метод `graph.get_state(config)` возвращает объект **`StateSnapshot`** (`from langgraph.types import StateSnapshot`) — именованный кортеж с полями:

| Поле | Что содержит |
|---|---|
| `values` | Текущие значения состояния (словарь каналов) |
| `next` | Кортеж имён узлов, которые выполнятся на следующем шаге (пусто `()` — граф завершён) |
| `config` | Конфиг этого чекпоинта, включая его `checkpoint_id` |
| `metadata` | Метаданные: `source` (`input`/`loop`/`update`/`fork`), `step`, `parents` (и др.) |
| `created_at` | Временная метка (ISO) создания снимка |
| `parent_config` | Конфиг родительского чекпоинта (или `None` для первого) |
| `tasks` | Кортеж `PregelTask` — задачи текущего шага (тут же видны прерывания и ошибки) |
| `interrupts` | Кортеж `Interrupt` — активные прерывания, ожидающие разрешения (для HITL) |

```python
config = {"configurable": {"thread_id": "user-42"}}
snapshot = graph.get_state(config)

print(snapshot.values)   # {'messages': [...]}
print(snapshot.next)     # () если граф завершён, иначе ('node_name',)
print(snapshot.tasks)    # задачи/прерывания текущего шага
```

Поле `next` — самый быстрый способ понять, «завис» ли граф на прерывании (тогда `next` укажет на узел, ожидающий возобновления).

### 13.6. update_state: ручное изменение состояния

`graph.update_state(config, values, as_node=None)` позволяет вручную записать значения в состояние потока, создав новый чекпоинт. Это основа для HITL (человек правит промежуточный результат перед продолжением).

```python
graph.update_state(
    config,
    {"messages": [("user", "Исправленный ввод")]},
    as_node="chatbot",   # опционально: «как будто» запись сделал этот узел
)
```

Ключевые моменты:

- `values` применяются к состоянию по тем же правилам, что и обычные возвраты узлов — через **reducer** соответствующего канала. Например, для `messages` с редьюсером `add_messages` новое сообщение будет *добавлено*, а не заменит список (а чтобы обновить конкретное сообщение — присвойте ему тот же `id`).
- `as_node` определяет, «от имени» какого узла сделана запись; от этого зависит, какие рёбра сработают дальше и что окажется в `next`.
- Метод возвращает обновлённый `config` с новым `checkpoint_id`.

### 13.7. Time travel: история и перезапуск с чекпоинта

Метод `graph.get_state_history(config)` возвращает **итератор `StateSnapshot`** по всем чекпоинтам потока — от самого свежего к самому старому. Это позволяет исследовать всю траекторию выполнения и вернуться к любой точке.

```python
config = {"configurable": {"thread_id": "user-42"}}

history = list(graph.get_state_history(config))
for snap in history:
    print(snap.metadata.get("step"), snap.next,
          snap.config["configurable"]["checkpoint_id"])
```

Чтобы «отмотать» выполнение назад и переиграть его, возьмите `config` нужного снимка (в нём уже есть `checkpoint_id`) и передайте его в новый запуск. Ввод `None` означает «продолжить с сохранённого состояния, ничего не добавляя»:

```python
# Выбираем чекпоинт, с которого хотим переиграть:
target = history[2]
fork_config = target.config   # содержит {"thread_id": ..., "checkpoint_id": ...}

# Запуск с конкретного checkpoint_id воспроизведёт всё до него,
# а затем продолжит выполнение с этой точки:
for event in graph.stream(None, fork_config, stream_mode="values"):
    print(event)
```

Если перед перезапуском изменить состояние через `update_state` на выбранном чекпоинте, вы создадите **новую ветку (fork)** истории — исходная траектория сохранится, а выполнение пойдёт по новому пути с обновлёнными данными. Это удобно для отладки, экспериментов с промптами и сценариев «а что, если».

> Когда в `config` присутствует `checkpoint_id`, LangGraph «проигрывает» уже сохранённые шаги из хранилища (не вызывая узлы заново) вплоть до этого чекпоинта, а дальше выполняет граф по-настоящему. Без `checkpoint_id` берётся последний чекпоинт потока.

### 13.8. Что именно сохраняется между вызовами

В каждом чекпоинте LangGraph сериализует и хранит:

- **значения всех каналов состояния** (`channel_values`) — то, что вы видите в `snapshot.values`;
- **версии каналов** (`channel_versions`) — служебная информация о том, какие узлы что «видели» (нужна для корректного возобновления и параллельных веток);
- **pending writes** — записи, сделанные узлами на текущем шаге, но ещё не применённые (важно для восстановления после сбоя посреди супершага, чтобы не терять и не дублировать работу);
- **метаданные** (`source`, `step`, `parents` и т. п.) и связь `parent_config` → образует цепочку/дерево чекпоинтов.

Сериализация по умолчанию выполняется через `JsonPlusSerializer` (поддерживает объекты LangChain, Pydantic-модели и др.; под капотом использует `ormsgpack` с запасным JSON-форматом). Для чувствительных данных можно подключить шифрующий сериализатор (`EncryptedSerializer`, например `EncryptedSerializer.from_pycryptodome_aes(...)`). В целях безопасности при работе с внешней/недоверенной БД рекомендуется ограничивать десериализацию (переменная окружения `LANGGRAPH_STRICT_MSGPACK=true` включает строгий режим, либо задайте явный список разрешённых модулей через `allowed_msgpack_modules`), чтобы скомпрометированная БД не привела к выполнению произвольного кода. Обязательно используйте `langgraph-checkpoint` ≥ 3.0, где закрыта RCE-уязвимость десериализации (CVE-2025-64439).

Не сохраняются: сами объекты LLM/инструментов, открытые сетевые соединения и любые несериализуемые значения — их нельзя класть в состояние. Храните в состоянии только данные, а не «живые» ресурсы.


---


## 14. Подграфы (Subgraphs)

**Подграф (subgraph)** — это отдельный скомпилированный граф LangGraph, который используется как часть другого, «родительского» графа. По сути это граф внутри графа: узлом родителя становится не обычная функция, а целый исполняемый пайплайн со своими узлами, рёбрами, состоянием и (при необходимости) собственной логикой ветвления.

Зачем нужны подграфы:

- **Инкапсуляция.** Сложный кусок логики (например, цикл «сгенерируй → проверь → исправь») прячется за одним узлом. Родительский граф остаётся простым и читаемым.
- **Повторное использование.** Один и тот же подграф можно подключить к нескольким родительским графам или несколько раз к одному.
- **Мультиагентные системы.** Каждый агент реализуется как самостоятельный граф (со своим набором инструментов и состоянием), а «супервизор» или маршрутизатор оркеструет их, подключая как подграфы. Это основной архитектурный приём для multi-agent.
- **Раздельная разработка и тестирование.** Подграф компилируется и тестируется независимо (`subgraph.invoke(...)`), а потом встраивается в целое.

Ключевой вопрос при встраивании — **как соотносятся схемы состояния родителя и подграфа**. От этого зависит, каким из двух способов подключать подграф.

### 14.1. Способ 1. Скомпилированный подграф как узел (общие ключи состояния)

Если родитель и подграф имеют **хотя бы один общий ключ состояния**, через который они «общаются», скомпилированный подграф можно передать прямо в `add_node` — как если бы это была обычная функция-узел.

```python
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END


# --- Общая схема состояния (один ключ foo используется и там, и там) ---
class State(TypedDict):
    foo: str


# --- Подграф ---
def subgraph_node_1(state: State) -> dict:
    return {"foo": "hi! " + state["foo"]}


subgraph_builder = StateGraph(State)
subgraph_builder.add_node("subgraph_node_1", subgraph_node_1)
subgraph_builder.add_edge(START, "subgraph_node_1")
subgraph_builder.add_edge("subgraph_node_1", END)
subgraph = subgraph_builder.compile()          # ВАЖНО: подграф надо СКОМПИЛИРОВАТЬ

# --- Родительский граф ---
builder = StateGraph(State)
builder.add_node("node_1", subgraph)           # передаём сам compiled subgraph как узел
builder.add_edge(START, "node_1")
builder.add_edge("node_1", END)
graph = builder.compile()

print(graph.invoke({"foo": "world"}))
# {'foo': 'hi! world'}
```

Что здесь происходит:

- В `add_node("node_1", subgraph)` передаётся не функция, а **уже скомпилированный** `CompiledStateGraph`. Компиляция подграфа обязательна — «сырой» `StateGraph` (builder) как узел не годится.
- С точки зрения родителя `node_1` — это обычный узел: он получает на вход состояние родителя и возвращает апдейт. Внутри LangGraph прогоняет все узлы подграфа.
- **Проходят только общие (пересекающиеся) ключи.** Родитель передаёт подграфу значения общих каналов; по завершении подграф возвращает наверх только те же общие ключи. Внутренние ключи подграфа, которых нет в схеме родителя, наружу не «протекают».

> Важно про reducers. Если общий ключ в схеме родителя имеет reducer (например, `Annotated[list, add]`), то апдейт, вернувшийся из подграфа, применяется к состоянию родителя через **этот reducer родителя**. Это удобно, но легко забыть и получить неожиданное объединение вместо перезаписи.

### 14.2. Способ 2. Вызов подграфа внутри функции-узла (разные схемы состояния)

Если у родителя и подграфа **разные схемы** и общих ключей нет (или их отображение нетривиально), напрямую как узел подграф добавить нельзя — LangGraph автоматически сопоставляет только одноимённые каналы. Решение: обернуть вызов подграфа в обычную функцию-узел и **вручную преобразовать** состояние на входе и на выходе.

```python
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END


# --- Схема подграфа: ключ bar ---
class SubgraphState(TypedDict):
    bar: str


def subgraph_node_1(state: SubgraphState) -> dict:
    return {"bar": "hi! " + state["bar"]}


subgraph_builder = StateGraph(SubgraphState)
subgraph_builder.add_node("subgraph_node_1", subgraph_node_1)
subgraph_builder.add_edge(START, "subgraph_node_1")
subgraph_builder.add_edge("subgraph_node_1", END)
subgraph = subgraph_builder.compile()


# --- Схема родителя: ДРУГОЙ ключ foo ---
class State(TypedDict):
    foo: str


def call_subgraph(state: State) -> dict:
    # 1) parent state -> subgraph input
    subgraph_input = {"bar": state["foo"]}
    # 2) запускаем подграф как обычный runnable
    subgraph_output = subgraph.invoke(subgraph_input)
    # 3) subgraph output -> parent state
    return {"foo": subgraph_output["bar"]}


builder = StateGraph(State)
builder.add_node("node_1", call_subgraph)      # узлом становится ОБЁРТКА, а не сам подграф
builder.add_edge(START, "node_1")
builder.add_edge("node_1", END)
graph = builder.compile()

print(graph.invoke({"foo": "world"}))
# {'foo': 'hi! world'}
```

Здесь `call_subgraph` — это «переходник» (adapter): он маппит `parent.foo -> subgraph.bar`, вызывает `subgraph.invoke(...)` и маппит результат обратно `subgraph.bar -> parent.foo`. Такой подход даёт полный контроль над трансформацией и позволяет, например, отфильтровать/переименовать поля, собрать вход из нескольких ключей родителя, обогатить результат.

> Про `config`. Внутри узла мы вызываем `subgraph.invoke(subgraph_input)` **без явного `config`** — и это правильно. LangGraph (через механизм LangChain Runnable) автоматически пробрасывает контекст текущего запуска во вложенные вызовы, поэтому подграф наследует чекпойнтер и настройки родителя, а `interrupt()` внутри подграфа продолжает работать. Передавать `config` вручную нужно лишь тогда, когда вы намеренно хотите дать подграфу отдельный `thread_id` (в связке с `checkpointer=True`, см. 14.4).

**Как выбирать способ:**

| Ситуация | Способ |
|---|---|
| Есть общие ключи, схемы совместимы | Способ 1: `add_node("name", subgraph)` |
| Схемы разные / нужна трансформация вход-выход | Способ 2: обёртка с `subgraph.invoke(...)` |
| Нужно вызвать подграф несколько раз / условно / собрать вход из многих полей | Способ 2 |

### 14.3. Стриминг из подграфов

По умолчанию `graph.stream(...)` показывает шаги **только верхнего уровня** — подграф выглядит как один шаг. Чтобы увидеть, что происходит **внутри** подграфов, передайте `subgraphs=True`.

```python
for chunk in graph.stream(
    {"foo": "world"},
    stream_mode="updates",
    subgraphs=True,          # включаем «заглядывание» внутрь подграфов
):
    print(chunk)
```

При `subgraphs=True` каждый элемент стрима — это **кортеж `(namespace, data)`** (а не просто `data`, как без флага):

```
((), {'node_1': ...})                                  # шаг верхнего уровня
(('node_1:6f8...uuid',), {'subgraph_node_1': ...})     # шаг ВНУТРИ подграфа
```

- `namespace` — кортеж-путь до места, где запущен подграф. Пустой кортеж `()` — это корневой (родительский) граф. Непустой, например `('node_1:<uuid>',)`, означает узел подграфа; `<uuid>` — идентификатор конкретного запуска этого подграфа.
- При многоуровневой вложенности `namespace` удлиняется: `('parent_node:id', 'child_node:id')`.
- Флаг `subgraphs=True` комбинируется с любым `stream_mode` (`updates`, `values`, `messages`, `custom`, `debug`). На содержимое `data` внутри кортежа это не влияет — добавляется только элемент `namespace` впереди.

> Практика. Из-за того, что при `subgraphs=True` формат меняется на кортеж, распаковывайте его явно: `for namespace, data in graph.stream(..., subgraphs=True):`. Забытый флаг — типичная причина «почему я не вижу внутренних шагов агента».

### 14.4. Персистентность подграфов и просмотр их состояния

Это одно из самых частых мест ошибок.

**Checkpointer подграфу отдельно передавать НЕ нужно.** Достаточно скомпилировать с чекпойнтером **родительский** граф — подграф автоматически **наследует** чекпойнтер родителя в рамках вызова. Не вызывайте `subgraph_builder.compile(checkpointer=...)` со своим сейвером «на всякий случай».

```python
from langgraph.checkpoint.memory import InMemorySaver   # раньше назывался MemorySaver

# подграф компилируется БЕЗ чекпойнтера
subgraph = subgraph_builder.compile()

# чекпойнтер — только у родителя
checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": "1"}}
graph.invoke({"foo": "world"}, config)
```

Тонкости параметра `checkpointer` при компиляции подграфа (`subgraph_builder.compile(...)`):

- **не указан (по умолчанию)** — подграф наследует чекпойнтер родителя; его состояние видно в рамках текущего вызова, работают `interrupt()` и инспекция состояния.
- **`checkpointer=True`** — подграф получает **собственную персистентность по потоку (thread)**: он «помнит» предыдущие вызовы между запусками. Нужно, когда подграф-субагент должен сохранять память между обращениями.
- **`checkpointer=False`** — персистентность для подграфа **отключена**: чекпойнты подграфа не сохраняются, а значит и посмотреть его состояние через родителя нельзя.

**Как посмотреть состояние подграфа.** Обычный `graph.get_state(config)` возвращает только состояние верхнего уровня. Чтобы добраться до состояния подграфа, передайте `subgraphs=True` — тогда состояние подграфа окажется в `tasks[i].state` соответствующей задачи:

```python
state = graph.get_state(config, subgraphs=True)

# состояние верхнего уровня
print(state.values)

# состояние подграфа, «висящего» на задаче (например, после interrupt внутри подграфа)
subgraph_snapshot = state.tasks[0].state     # это вложенный StateSnapshot
print(subgraph_snapshot.values)
print(subgraph_snapshot.next)                # какие узлы подграфа выполнятся следующими
```

Аналогично `graph.get_state_history(config)` даёт историю верхнего уровня. Важное ограничение: инспекция состояния подграфа возможна только если LangGraph может **статически обнаружить** подграф — то есть он добавлен как узел (Способ 1) или вызывается внутри узла (Способ 2). При наследуемой (per-invocation) персистентности `get_state(config, subgraphs=True)` показывает состояние подграфа **только для текущего вызова и пока подграф «остановлен»** (например, на `interrupt()`): после нормального завершения подграфа его задача исчезает из `tasks`, и вложенного `StateSnapshot` там уже не будет. Для подграфа, скомпилированного с `checkpointer=True`, его состояние по потоку доступно и вне прерывания.

### 14.5. Многоуровневая вложенность

Подграфы вкладываются на любую глубину: родитель → ребёнок → внук. На каждом уровне применяется тот же выбор из двух способов. Пример с разными схемами на каждом уровне (Способ 2 на каждой границе):

```python
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END


# --- Внук (grandchild) ---
class GrandChildState(TypedDict):
    my_grandchild_key: str


def grandchild_node(state: GrandChildState) -> dict:
    return {"my_grandchild_key": state["my_grandchild_key"] + ", how are you"}


gc_builder = StateGraph(GrandChildState)
gc_builder.add_node("grandchild_node", grandchild_node)
gc_builder.add_edge(START, "grandchild_node")
gc_builder.add_edge("grandchild_node", END)
grandchild = gc_builder.compile()


# --- Ребёнок (child) вызывает внука через обёртку ---
class ChildState(TypedDict):
    my_child_key: str


def call_grandchild(state: ChildState) -> dict:
    gc_input = {"my_grandchild_key": state["my_child_key"]}
    gc_output = grandchild.invoke(gc_input)
    return {"my_child_key": gc_output["my_grandchild_key"] + " today?"}


child_builder = StateGraph(ChildState)
child_builder.add_node("call_grandchild", call_grandchild)
child_builder.add_edge(START, "call_grandchild")
child_builder.add_edge("call_grandchild", END)
child = child_builder.compile()


# --- Родитель (parent) вызывает ребёнка через обёртку ---
class ParentState(TypedDict):
    my_key: str


def call_child(state: ParentState) -> dict:
    child_output = child.invoke({"my_child_key": state["my_key"]})
    return {"my_key": child_output["my_child_key"]}


parent_builder = StateGraph(ParentState)
parent_builder.add_node("call_child", call_child)
parent_builder.add_edge(START, "call_child")
parent_builder.add_edge("call_child", END)
parent = parent_builder.compile()

print(parent.invoke({"my_key": "Hi"}))
# {'my_key': 'Hi, how are you today?'}
```

При стриминге такой конструкции с `subgraphs=True` `namespace` будет отражать полный путь вложенности (`('call_child:id', 'call_grandchild:id')`).

### 14.6. Типичные ошибки и подводные камни

- **Забыли скомпилировать подграф.** В `add_node` должен идти результат `builder.compile()`, а не сам `StateGraph`-builder.
- **Нет общих ключей, но подключаете Способом 1.** Если схемы не пересекаются, вход/выход просто не пройдут через границу (значения потеряются или узел получит неполное состояние). При разных схемах используйте Способ 2 с явной трансформацией.
- **Явный отдельный checkpointer у подграфа.** Не передавайте свой сейвер в `compile()` подграфа, если хотите обычного наследования — достаточно чекпойнтера у родителя. Осознанно используйте `checkpointer=True` (память между вызовами) или `checkpointer=False` (отключить), понимая последствия.
- **Не видно внутренних шагов при стриминге.** Нужен `subgraphs=True`; и помните, что тогда элементы стрима — кортежи `(namespace, data)`.
- **`get_state` не показывает подграф.** Без `subgraphs=True` вы видите только верхний уровень; инспекция подграфа требует, чтобы он был статически обнаружим (узел или вызов внутри узла), и включённой персистентности. При наследуемом чекпойнтере вложенное состояние видно, только пока подграф прерван.
- **Конфликт одновременных записей.** Если и родитель, и подграф пишут в один и тот же общий ключ на одном шаге без reducer, можно получить ошибку конкурентного обновления (`InvalidUpdateError`). Для «складываемых» полей задавайте reducer (`Annotated[list, add]`).
- **Рекурсия и лимит шагов.** Глубокая или циклическая вложенность увеличивает число супершагов; при необходимости повышайте `recursion_limit` в `config`, иначе получите `GraphRecursionError`.
- **Устаревшие имена.** `InMemorySaver` — актуальное имя in-memory чекпойнтера из `langgraph.checkpoint.memory`; `MemorySaver` оставлен как алиас для совместимости. Импорты графа берите из `langgraph.graph` (`StateGraph`, `START`, `END`).


---


## 15. Human-in-the-loop (человек в цикле)

Human-in-the-loop (HITL, «человек в цикле») — это механизм, который позволяет **остановить выполнение графа**, показать человеку промежуточное состояние (или запрос) и **продолжить работу** после того, как человек ответит, подтвердит, отредактирует данные или отклонит действие. Это ключевой инструмент для надёжных агентов: перед необратимыми операциями (отправка письма, платёж, изменение данных в БД, вызов внешнего API) можно вставить контрольную точку с участием человека.

В LangGraph есть два независимых механизма:

| Механизм | Что это | Когда использовать |
|---|---|---|
| **Динамические прерывания** — `interrupt()` внутри узла | Пауза в произвольной точке кода узла с передачей данных наружу | Продакшн-логика: approve/reject, ввод данных, ревью инструментов |
| **Статические точки останова** — `interrupt_before` / `interrupt_after` | Пауза до/после указанных узлов, объявленная при `compile()` или в вызове | Отладка, инспекция и ручное редактирование состояния |

### Обязательные требования: checkpointer и thread_id

HITL **не работает без чекпоинтера**: чтобы «заморозить» граф и потом продолжить, состояние должно быть сохранено. И нужен стабильный `thread_id` в `config` — он играет роль курсора: тот же `thread_id` возобновляет тот же диалог/поток, новый — начинает с нуля.

```python
from langgraph.checkpoint.memory import InMemorySaver  # для тестов/прототипов
# В продакшне (ставятся отдельными пакетами):
#   from langgraph.checkpoint.postgres import PostgresSaver  # langgraph-checkpoint-postgres
#   from langgraph.checkpoint.sqlite import SqliteSaver      # langgraph-checkpoint-sqlite

checkpointer = InMemorySaver()          # раньше назывался MemorySaver (алиас сохранён)
graph = builder.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": "user-42"}}  # обязательный стабильный id
```

> Примечание: `InMemorySaver` хранит данные в оперативной памяти и теряет их при перезапуске процесса — для реального HITL берите `SqliteSaver`/`PostgresSaver`. Долговечные чекпоинтеры обычно создаются через `.from_conn_string(...)` и работают как контекстные менеджеры, а при первом запуске требуют `checkpointer.setup()`:
>
> ```python
> from langgraph.checkpoint.postgres import PostgresSaver
>
> DB_URI = "postgresql://user:pass@localhost:5432/db"
> with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
>     checkpointer.setup()                 # создаёт служебные таблицы (один раз)
>     graph = builder.compile(checkpointer=checkpointer)
>     # ... работа с graph внутри блока with
> ```

### Динамические прерывания: `interrupt()` и `Command(resume=...)`

```python
from langgraph.types import interrupt, Command
```

`interrupt(value)` принимает любое **JSON-сериализуемое** значение, выбрасывает его наружу (в результат вызова графа) и приостанавливает выполнение. При возобновлении граф вызывается повторно с `Command(resume=<ответ>)`, и это значение становится **возвращаемым значением** вызова `interrupt()`.

Полный рабочий пример — редактирование текста человеком:

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver


class State(TypedDict):
    text: str


def human_node(state: State) -> State:
    edited = interrupt({
        "text_to_revise": state["text"],
        "question": "Отредактируйте текст и верните новую версию",
    })
    return {"text": edited}


builder = StateGraph(State)
builder.add_node("human_node", human_node)
builder.add_edge(START, "human_node")
builder.add_edge("human_node", END)

graph = builder.compile(checkpointer=InMemorySaver())
config = {"configurable": {"thread_id": "1"}}

# 1) Первый запуск — упираемся в interrupt, граф встаёт на паузу
result = graph.invoke({"text": "исходный текст"}, config=config)
print(result["__interrupt__"])
# (Interrupt(value={'text_to_revise': 'исходный текст', 'question': ...}, id='...'),)

# 2) Возобновление: значение resume попадает в return interrupt()
final = graph.invoke(Command(resume="отредактированный текст"), config=config)
print(final["text"])   # 'отредактированный текст'
```

### Как читать значение прерывания и возобновлять

Прерывание доступно несколькими способами:

- **Из результата `invoke`** — по специальному ключу `result["__interrupt__"]`. Это кортеж объектов `Interrupt`, у каждого есть `.value` (то, что вы передали в `interrupt(...)`) и `.id` (идентификатор).
- **Из `stream`** — в потоке появится чанк `{"__interrupt__": (Interrupt(...),)}`:

  ```python
  for chunk in graph.stream({"text": "..."}, config=config):
      if "__interrupt__" in chunk:
          intr = chunk["__interrupt__"][0]
          print("Нужен ввод:", intr.value)
  ```

- **Через снапшот состояния** — `graph.get_state(config)`:

  ```python
  snapshot = graph.get_state(config)
  print(snapshot.next)        # какие узлы стоят на очереди, например ('human_node',)
  print(snapshot.interrupts)  # активные Interrupt для этого потока
  ```

  Атрибут `snapshot.interrupts` доступен в актуальных версиях LangGraph и агрегирует ожидающие прерывания по всем задачам шага. На более низком уровне те же данные лежат в `snapshot.tasks[0].interrupts` (полезно, если нужно знать, какой именно узел встал на паузу, или в старых версиях без `snapshot.interrupts`).

Возобновление всегда одно и то же: повторный вызов `graph.invoke(Command(resume=value), config)` (или `graph.stream(...)`) с **тем же** `thread_id`.

#### Важно: узел перезапускается целиком

При возобновлении LangGraph **перезапускает весь узел с начала**, а не «с той строки, где стоял `interrupt()`». Значение `resume` подставляется в соответствующий вызов `interrupt()`, но весь код узла до этого вызова выполняется заново. Отсюда правила:

- Выносите **побочные эффекты** (запись в БД, отправка запроса) *после* `interrupt()` или делайте их идемпотентными — иначе они выполнятся дважды.
- **Не** оборачивайте `interrupt()` в «голый» `try/except` — внутри используется механизм исключений (`interrupt()` возбуждает служебное исключение `GraphInterrupt`, которое должно свободно всплыть наружу).
- **Не** пропускайте вызовы `interrupt()` по условию между запусками: сопоставление ответов идёт по порядку/индексу.
- Для валидации ввода используйте условные рёбра, а **не** `while True` внутри узла.

### Паттерны HITL

#### Approve / Reject (подтвердить/отклонить)

Узел может вернуть `Command(goto=...)` и направить граф в зависимости от решения человека.

```python
from typing import Literal
from langgraph.types import interrupt, Command


def approval_node(state: State) -> Command[Literal["execute", "cancel"]]:
    decision = interrupt({
        "action": state["pending_action"],
        "question": "Выполнить это действие?",
    })
    if decision == "approve":
        return Command(goto="execute")
    return Command(goto="cancel")

# Возобновление:
graph.invoke(Command(resume="approve"), config=config)
```

#### Редактирование состояния (edit state)

Человек видит сгенерированный контент и возвращает исправленную версию, которая записывается обратно в состояние:

```python
def review_draft(state: State):
    corrected = interrupt({
        "instruction": "Проверьте и при необходимости исправьте черновик",
        "draft": state["draft"],
    })
    return {"draft": corrected}
```

#### Ревью tool calls (проверка вызовов инструментов)

`interrupt()` можно вызывать прямо **внутри инструмента** — так человек утверждает, редактирует или отклоняет конкретный вызов перед его исполнением. Частая схема: `accept` / `edit` / `reject`.

```python
from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
def book_hotel(hotel_name: str) -> str:
    """Забронировать отель по названию."""
    response = interrupt({
        "tool": "book_hotel",
        "args": {"hotel_name": hotel_name},
        "question": "Подтвердите или отредактируйте вызов инструмента",
    })

    if response["type"] == "accept":
        pass
    elif response["type"] == "edit":
        hotel_name = response["args"]["hotel_name"]
    elif response["type"] == "reject":
        return f"Отменено пользователем: {response.get('reason', '')}"

    return f"Отель '{hotel_name}' успешно забронирован."
```

Возобновление: `graph.invoke(Command(resume={"type": "edit", "args": {"hotel_name": "Hilton"}}), config)`.

> Если в одном ответе модели несколько tool calls и `interrupt()` срабатывает сразу в нескольких инструментах, прерываний будет несколько — их возобновляют словарём `{interrupt_id: value}` (см. раздел о параллельных прерываниях ниже).

#### Запрос ввода у человека (с валидацией)

Если ответ нужно проверять, зацикливайте узел **через условные рёбра**, а не через `while` внутри узла (иначе состояние прерываний собьётся):

```python
def collect_age(state: State):
    question = state.get("pending") or "Укажите возраст:"
    answer = interrupt(question)          # вызывается один раз за проход
    if isinstance(answer, int) and answer > 0:
        return {"age": answer, "pending": None}
    return {"pending": f"'{answer}' некорректно. Введите положительное число."}


def route(state: State) -> str:
    return END if state.get("age") is not None else "collect_age"


builder.add_conditional_edges("collect_age", route, ["collect_age", END])
```

### Несколько `interrupt` в одном узле (кратко)

Если в **одном узле** несколько вызовов `interrupt()`, LangGraph сопоставляет переданные `resume`-значения с прерываниями **по порядку** их вызова. Каждый `Command(resume=...)` «закрывает» очередной `interrupt()`; узел перезапускается, уже полученные ответы возвращаются мгновенно, а выполнение доходит до следующего неотвеченного `interrupt()`.

```python
def two_questions(state: State):
    name = interrupt("Как вас зовут?")   # 1-й проход остановится здесь
    age = interrupt("Сколько вам лет?")  # 2-й проход остановится здесь
    return {"name": name, "age": age}

# graph.invoke(Command(resume="Иван"), config)  -> вернёт вопрос про возраст
# graph.invoke(Command(resume=42), config)      -> узел завершится
```

Если же прерывания сработали **в параллельных узлах одновременно**, в `result["__interrupt__"]` будет несколько объектов `Interrupt`. Возобновлять нужно **словарём** `{interrupt_id: value}`:

```python
result = graph.invoke(inputs, config=config)
resume_map = {i.id: answer_for(i.value) for i in result["__interrupt__"]}
graph.invoke(Command(resume=resume_map), config=config)
```

### Статические точки останова: `interrupt_before` / `interrupt_after`

Это более простой и грубый механизм: граф останавливается **до** или **после** указанных узлов, не передавая наружу данные. Значения возобновления не нужны — продолжение делается вызовом с `None`. Удобно для отладки и ручного вмешательства в состояние.

При компиляции:

```python
graph = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["tools"],   # пауза перед узлом tools
    interrupt_after=[],           # можно указать и узлы для паузы после
)

config = {"configurable": {"thread_id": "42"}}
graph.invoke(inputs, config=config)     # дойдёт до точки останова и встанет

# Инспекция и (опционально) правка состояния вручную:
snapshot = graph.get_state(config)
print(snapshot.next)                    # ('tools',) — граф стоит перед tools
graph.update_state(config, {"some_key": "new value"})

# Продолжение — вход None (а не Command(resume=...)):
graph.invoke(None, config=config)
```

Те же параметры можно передать и при запуске: `invoke`/`stream` принимают `interrupt_before` / `interrupt_after` как runtime-аргументы, переопределяя (дополняя) заданные при `compile()`:

```python
graph.invoke(inputs, config=config, interrupt_before=["tools"])
graph.invoke(None, config=config)       # продолжить
```

В качестве значения можно указать список имён узлов или `"*"` — останавливаться на каждом узле.

> Отличие от динамического `interrupt()`: статические точки **не** возвращают `__interrupt__` с полезной нагрузкой и возобновляются входом `None`; факт паузы определяется по непустому `snapshot.next`. Динамический `interrupt()` — это рекомендованный способ для продуктовой логики, а `interrupt_before`/`interrupt_after` — прежде всего инструмент отладки.

> Об устаревшем: раньше динамическую паузу делали через `raise NodeInterrupt(...)` из узла. Сейчас `NodeInterrupt` считается устаревшим — предпочтительна функция `interrupt()` из `langgraph.types`: она поддерживает передачу данных и корректное возобновление через `Command(resume=...)`.

### Лучшие практики и типичные ошибки

- **Всегда** задавайте `checkpointer` и стабильный `thread_id` — без них HITL молча не сработает.
- Передавайте в `interrupt()` только JSON-сериализуемые данные (dict со всем контекстом, который нужен человеку для решения).
- Помните о перезапуске узла: побочные эффекты — после `interrupt()` и/или идемпотентные.
- Не меняйте число/порядок вызовов `interrupt()` между запусками одного узла.
- Для нескольких параллельных прерываний возобновляйте `Command(resume={id: value})`, для последовательных в одном узле — по одному `Command(resume=value)` за проход.
- В продакшне используйте долговечный чекпоинтер (`PostgresSaver`/`SqliteSaver`), а не `InMemorySaver`.


---


## 16. Готовые агенты: create_react_agent и ToolNode

LangGraph поставляет пакет `langgraph.prebuilt` с готовыми «кирпичами» для сборки ReAct-агентов: фабрику `create_react_agent`, узел исполнения инструментов `ToolNode` и функцию-роутер `tools_condition`. ReAct-цикл прост: модель либо отвечает пользователю финальным сообщением, либо просит вызвать один или несколько инструментов (`tool_calls`); инструменты исполняются, их результаты (`ToolMessage`) возвращаются модели, и цикл повторяется, пока модель не перестанет запрашивать инструменты.

> **Статус API (важно).** В LangGraph 1.0 функция `create_react_agent` из `langgraph.prebuilt` помечена **deprecated** (категория `LangGraphDeprecatedSinceV10`) и по плану будет удалена в 2.0. Рекомендуемая замена — `create_agent` из пакета `langchain` (`langchain.agents`), построенная поверх того же LangGraph, но с гибкой системой middleware. Тем не менее `create_react_agent` пока полностью рабочая, широко используется и остаётся отличной моделью для понимания устройства агента. `ToolNode` и `tools_condition` не устарели и применяются как самостоятельные примитивы (в том числе внутри `create_agent`). Ниже подробно разобран `create_react_agent`, а в конце — переход на `create_agent`.

### 16.1. Быстрый старт: create_react_agent

```python
from langchain.chat_models import init_chat_model
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

@tool
def get_weather(city: str) -> str:
    """Вернуть текущую погоду в указанном городе."""
    return f"В городе {city} солнечно, +25°C."

model = init_chat_model("openai:gpt-4o-mini")  # можно передать и строкой прямо в агент

agent = create_react_agent(
    model=model,
    tools=[get_weather],
    prompt="Ты — вежливый ассистент по погоде.",
)

result = agent.invoke({"messages": [{"role": "user", "content": "Погода в Москве?"}]})
print(result["messages"][-1].content)
```

`create_react_agent` возвращает **`CompiledStateGraph`** — обычный LangGraph-граф (он же `Runnable`), поэтому у него есть методы `invoke`, `ainvoke`, `stream`, `astream`, а также поддержка чекпоинтеров, стриминга и подграфов.

### 16.2. Аргументы create_react_agent

| Аргумент | Тип | Назначение |
|---|---|---|
| `model` | `str \| BaseChatModel \| Callable` | Модель чата, строковый идентификатор (`"openai:gpt-4o"`) или callable для динамического выбора модели по контексту. Внутри агента к модели автоматически применяется `bind_tools`. |
| `tools` | `Sequence[BaseTool \| Callable \| dict] \| ToolNode` | Список инструментов или готовый `ToolNode`. Пустой список даёт агента без инструментов (просто цикл с моделью). |
| `prompt` | `str \| SystemMessage \| Callable \| Runnable \| None` | Системный промпт / модификатор входа модели (см. 16.4). |
| `response_format` | `Schema \| tuple \| None` | Схема структурированного финального ответа; кладётся в `structured_response` (см. 16.5). |
| `pre_model_hook` | `RunnableLike \| None` | Узел перед вызовом модели (тримминг/суммаризация истории). |
| `post_model_hook` | `RunnableLike \| None` | Узел после вызова модели (guardrails, human-in-the-loop, валидация). Только `version="v2"`. |
| `state_schema` | `type \| None` | Схема состояния; по умолчанию `AgentState`. Должна содержать `messages` и `remaining_steps`. |
| `context_schema` | `type \| None` | Схема неизменяемого runtime-контекста (`config_schema` в старых версиях). |
| `checkpointer` | `Checkpointer \| None` | Сохранение состояния одного треда (память диалога). |
| `store` | `BaseStore \| None` | Долговременное хранилище, общее для разных тредов. |
| `interrupt_before` / `interrupt_after` | `list[str] \| None` | Прерывания до/после узлов (`"agent"`, `"tools"`). |
| `version` | `Literal["v1","v2"]` | `v1` — все `tool_calls` в одном узле; `v2` — каждый вызов как отдельная задача (`Send`). По умолчанию `v2`. |
| `name` | `str \| None` | Имя скомпилированного графа (полезно для мульти-агентных подграфов). |
| `debug` | `bool` | Подробный лог исполнения. |

> **Об устаревших аргументах.** Раньше системный промпт задавался через `messages_modifier`, затем через `state_modifier` — оба **удалены**, используйте `prompt`. Аргумент `config_schema` переименован в `context_schema`.

### 16.3. Структура состояния агента (AgentState)

По умолчанию агент работает со схемой `AgentState`, у которой два обязательных канала:

- **`messages`** — история сообщений (`list[BaseMessage]`) с reducer `add_messages`: новые сообщения добавляются, а не перезаписывают историю.
- **`remaining_steps`** — счётчик оставшихся шагов рекурсии (managed-канал). Если шагов не хватает, а модель всё ещё просит инструменты, агент аккуратно завершает работу, а не падает по `GraphRecursionError`.

Результат `invoke` — это финальное состояние: `result["messages"]` содержит всю переписку, `result["messages"][-1]` — финальный `AIMessage`.

### 16.4. Кастомизация промпта

`prompt` принимает четыре формы:

```python
from langchain_core.messages import SystemMessage

# 1) Строка -> станет SystemMessage в начале истории
create_react_agent(model, tools, prompt="Отвечай кратко.")

# 2) Готовый SystemMessage
create_react_agent(model, tools, prompt=SystemMessage(content="Отвечай кратко."))

# 3) Callable: получает всё состояние, возвращает список сообщений для модели
def prompt(state) -> list:
    user_name = state.get("user_name", "друг")
    system = SystemMessage(content=f"Обращайся к пользователю по имени {user_name}.")
    return [system] + state["messages"]

create_react_agent(model, tools, prompt=prompt, state_schema=CustomState)  # см. 16.6

# 4) Runnable / ChatPromptTemplate
```

Callable-форма — самый мощный вариант: она видит любые дополнительные поля состояния и позволяет собирать динамический системный промпт на каждом шаге.

### 16.5. Структурированный финальный ответ (response_format)

Если нужен не свободный текст, а типизированный объект, передайте Pydantic/`TypedDict`-схему:

```python
from pydantic import BaseModel

class WeatherReport(BaseModel):
    city: str
    temperature_c: int
    conditions: str

agent = create_react_agent(model, [get_weather], response_format=WeatherReport)

result = agent.invoke({"messages": [{"role": "user", "content": "Погода в Сочи?"}]})
report: WeatherReport = result["structured_response"]
```

Модель должна поддерживать `with_structured_output`. Можно передать кортеж `(system_prompt, schema)` — отдельный промпт для шага структурирования. В LangGraph это делается дополнительным LLM-вызовом после завершения ReAct-цикла.

### 16.6. Кастомная схема состояния

Чтобы прокинуть свои поля (и читать их в `prompt` или инструментах), расширьте `AgentState`:

```python
from langgraph.prebuilt.chat_agent_executor import AgentState

class CustomState(AgentState):
    user_name: str          # своё поле; messages и remaining_steps наследуются

agent = create_react_agent(model, tools, state_schema=CustomState, prompt=prompt)
agent.invoke({"messages": [...], "user_name": "Анна"})
```

Инструмент может читать состояние и хранилище через инъекции — эти аргументы не видны модели, LangGraph подставляет их сам:

```python
from typing import Annotated
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState, InjectedStore
from langgraph.store.base import BaseStore

@tool
def whoami(state: Annotated[dict, InjectedState]) -> str:
    """Вернуть имя текущего пользователя."""
    return state["user_name"]

@tool
def remember(fact: str, store: Annotated[BaseStore, InjectedStore]) -> str:
    """Сохранить факт в долговременную память."""
    store.put(("facts",), "last", {"text": fact})   # store.put(namespace, key, value)
    return "ок"
```

### 16.7. pre_model_hook и post_model_hook

`pre_model_hook` выполняется перед моделью — типичное применение — обрезка длинной истории:

```python
from langchain_core.messages.utils import trim_messages, count_tokens_approximately

def pre_model_hook(state):
    trimmed = trim_messages(
        state["messages"],
        strategy="last",
        token_counter=count_tokens_approximately,
        max_tokens=512,
        start_on="human",
        end_on=("human", "tool"),
    )
    # llm_input_messages -> подменяет вход модели, НЕ переписывая state["messages"]
    return {"llm_input_messages": trimmed}

agent = create_react_agent(model, tools, pre_model_hook=pre_model_hook)
```

Ключ `llm_input_messages` влияет только на вход модели; если вернуть `messages` (например, со списком `RemoveMessage`), меняется само состояние. `post_model_hook` (только `version="v2"`) выполняется после ответа модели — используйте для валидации, guardrails или человека-в-контуре.

### 16.8. Память: checkpointer и store

```python
from langgraph.checkpoint.memory import InMemorySaver   # для продакшена: Sqlite/Postgres Saver
from langgraph.store.memory import InMemoryStore

agent = create_react_agent(model, tools, checkpointer=InMemorySaver(), store=InMemoryStore())

config = {"configurable": {"thread_id": "user-42"}}
agent.invoke({"messages": [{"role": "user", "content": "Меня зовут Пётр."}]}, config)
agent.invoke({"messages": [{"role": "user", "content": "Как меня зовут?"}]}, config)  # помнит
```

С чекпоинтером **обязателен** `thread_id` в `config`: он определяет, какую ветку истории продолжать. `checkpointer` хранит состояние одного диалога, `store` — данные, общие для всех тредов (долговременная память). `InMemorySaver` — это тот же класс, что раньше назывался `MemorySaver` (старое имя оставлено как алиас).

### 16.9. ToolNode: исполнение tool_calls и обработка ошибок

`ToolNode` — самостоятельный узел, который берёт `tool_calls` из **последнего** `AIMessage`, параллельно вызывает соответствующие инструменты и возвращает список `ToolMessage`.

```python
from langchain_core.messages import AIMessage
from langgraph.prebuilt import ToolNode

tool_node = ToolNode([get_weather])

msg = AIMessage(content="", tool_calls=[
    {"name": "get_weather", "args": {"city": "Казань"}, "id": "call_1", "type": "tool_call"},
])
tool_node.invoke({"messages": [msg]})
# -> {"messages": [ToolMessage(content="...", tool_call_id="call_1", name="get_weather")]}
```

Каждый `ToolMessage` несёт `tool_call_id`, равный `id` соответствующего вызова из `AIMessage` — именно по нему модель сопоставляет результат с запросом.

Обработка ошибок задаётся аргументом `handle_tool_errors`:

| Значение | Поведение |
|---|---|
| `True` (по умолчанию) | Ловит любое исключение, возвращает его текст в `ToolMessage` (модель может «переиграть» вызов). |
| строка | Возвращает фиксированный текст ошибки. |
| кортеж исключений, напр. `(ValueError,)` | Ловит только указанные типы, остальные пробрасывает. |
| функция `Callable[[Exception], str]` | Формирует текст ошибки самостоятельно. |
| `False` | Не ловит — исключение прерывает граф. |

```python
ToolNode([get_weather], handle_tool_errors="Не удалось выполнить инструмент, уточните запрос.")
```

Прочие аргументы: `name` (имя узла, по умолчанию `"tools"`) и `messages_key` (канал с сообщениями, по умолчанию `"messages"`).

### 16.10. tools_condition и ручная сборка агента

`tools_condition` — готовая функция-роутер для `add_conditional_edges`. Она смотрит на последнее сообщение: если в нём есть `tool_calls` — возвращает `"tools"`, иначе `END`. Полностью эквивалентный `create_react_agent` граф собирается так:

```python
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

tools = [get_weather]
model_with_tools = model.bind_tools(tools)

def call_model(state: MessagesState):
    return {"messages": [model_with_tools.invoke(state["messages"])]}

builder = StateGraph(MessagesState)
builder.add_node("agent", call_model)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)  # "agent" -> "tools" или END
builder.add_edge("tools", "agent")                        # результаты инструментов -> обратно модели
graph = builder.compile()
```

`MessagesState` — встроенная схема с единственным каналом `messages` и reducer `add_messages`. Ручная сборка нужна, когда стандартного ReAct-цикла недостаточно (несколько моделей, ветвления, кастомная маршрутизация).

> **Примечание.** `tools_condition` по умолчанию маршрутизирует именно в узел с именем `"tools"`; если узел инструментов назван иначе, передайте свой роутер или переименуйте узел.

### 16.11. Вызов и стриминг

```python
inp = {"messages": [{"role": "user", "content": "Погода в Питере и Москве?"}]}

# updates: инкрементальные апдейты по узлам ("agent", "tools")
for chunk in agent.stream(inp, stream_mode="updates"):
    print(chunk)

# messages: токены LLM по мере генерации — кортеж (message_chunk, metadata)
for token, metadata in agent.stream(inp, stream_mode="messages"):
    if token.content:
        print(token.content, end="", flush=True)

# values: полное состояние после каждого шага
for state in agent.stream(inp, stream_mode="values"):
    print(state["messages"][-1])
```

- `stream_mode="updates"` — что записал каждый узел (удобно для логов/трейсинга шагов).
- `stream_mode="messages"` — потоковые токены модели; элемент — кортеж `(chunk, metadata)`, где `metadata["langgraph_node"]` показывает узел-источник.
- `stream_mode="values"` — полный снимок состояния после каждого шага.
- Можно передать список режимов: `stream_mode=["updates", "messages"]` — тогда элементы приходят как `(mode, data)`.

Для асинхронного кода используйте `await agent.ainvoke(...)` и `async for ... in agent.astream(...)`.

### 16.12. Отличие от устаревшего AgentExecutor

Классический стек `langchain` — `AgentExecutor` вместе с `initialize_agent` / старой `create_react_agent(llm, tools, prompt)` из `langchain.agents` — это **другой** механизм (совпадение имён случайно и часто путает):

- Старый ReAct парсил текст модели по шаблону `Thought/Action/Action Input/Observation` (промпт из hub, `hwchase17/react`), тогда как LangGraph-агент использует нативные `tool_calls` модели — надёжнее и без парсинга строк.
- `AgentExecutor` — «чёрный ящик» с ограниченной наблюдаемостью; LangGraph-агент — это граф с состоянием, чекпоинтингом, стримингом токенов, прерываниями и human-in-the-loop «из коробки».
- `initialize_agent` и `AgentExecutor` в 1.0 считаются legacy (перенесены в пакет `langchain-classic`); новые проекты на них строить не стоит.

### 16.13. Переход на langchain.agents.create_agent (1.0)

Актуально рекомендуемая замена `create_react_agent`:

```python
from langchain.agents import create_agent

agent = create_agent(
    model="openai:gpt-4o-mini",
    tools=[get_weather],
    system_prompt="Ты — вежливый ассистент по погоде.",
)
result = agent.invoke({"messages": [{"role": "user", "content": "Погода в Москве?"}]})
```

Ключевые отличия от `create_react_agent`:

- Вместо `prompt` — аргумент `system_prompt` (принимает `str` или `SystemMessage`).
- Вместо `pre_model_hook`/`post_model_hook` — **middleware** с хуками жизненного цикла: `before_agent`, `before_model`, `wrap_model_call`, `after_model`, `after_agent`, а также `wrap_tool_call` для инструментов и декоратор `@dynamic_prompt` для динамического системного промпта; несколько middleware компонуются в цепочку. (Ранний альфа-хук `modify_model_request` переименован в `wrap_model_call`.)
- Есть готовые middleware: `SummarizationMiddleware` (сжатие истории), `HumanInTheLoopMiddleware` (подтверждение вызовов инструментов) и др.
- `checkpointer`, `store`, `response_format`, `context_schema` сохраняются; `state_schema` для `create_agent` рекомендуется задавать через `TypedDict` (Pydantic-схемы состояния не поддерживаются).

```python
from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.memory import InMemorySaver

agent = create_agent(
    model="openai:gpt-4o-mini",
    tools=[get_weather],
    middleware=[
        SummarizationMiddleware(
            model="openai:gpt-4o-mini",
            trigger=("tokens", 1000),   # порог запуска суммаризации
            keep=("messages", 20),      # сколько последних сообщений сохранить
        )
    ],
    checkpointer=InMemorySaver(),
)
```

> **О параметрах `SummarizationMiddleware`.** Текущий API использует `trigger` и `keep`, которые принимают кортежи `("tokens", N)`, `("messages", N)` или `("fraction", 0.0–1.0)` (для `trigger` допустимы также список условий-ИЛИ и словарь условий-И). Прежние аргументы `max_tokens_before_summary` и `messages_to_keep` **устарели** — они пока принимаются как deprecated-kwargs, но в новом коде используйте `trigger`/`keep`.

> **Примечание о версиях.** В переходный период 1.x путь импорта и набор middleware менялись между релизами `langchain` / `langchain-classic`, а часть сообщений о депрекации указывала неточные импорты. Перед использованием сверяйтесь с актуальной документацией (`reference.langchain.com`, `docs.langchain.com`) и версией установленного пакета. Пока `create_react_agent` работает — переходить на `create_agent` можно постепенно; API-контракт по состоянию (`messages`) и вызову (`invoke`/`stream`) у обеих фабрик совпадает.


---


## 17. Мультиагентные архитектуры

Когда один агент обрастает десятками инструментов, длинными системными промптами и разнородными обязанностями, он начинает ошибаться в выборе инструмента, «забывать» контекст и плохо масштабироваться. Мультиагентный подход разбивает задачу на несколько специализированных агентов, каждый со своим набором инструментов, промптом и (при необходимости) своей моделью. В LangGraph каждый агент — это обычно узел графа или отдельный подграф, а координация между ними строится на передаче управления (handoff) и общем состоянии.

### 17.1. Обзор паттернов

LangGraph выделяет несколько канонических топологий координации:

| Паттерн | Кто решает, кому передать управление | Типичная реализация | Когда применять |
| --- | --- | --- | --- |
| **Network** (сеть) | Каждый агент может вызвать любого другого («many-to-many») | Узлы графа, возвращающие `Command(goto=...)` | Слабо структурированные задачи, где маршрут заранее не известен |
| **Supervisor** (супервизор) | Один центральный агент-роутер | `langgraph-supervisor` / супервизор как узел с handoff-инструментами | Большинство продакшн-сценариев: понятная маршрутизация и отладка |
| **Hierarchical** (иерархия, «команды команд») | Супервизоры на нескольких уровнях | Вложенные подграфы-супервизоры | Много агентов, которые логично сгруппировать в команды |
| **Swarm** (рой) | Агенты передают управление напрямую друг другу; активный агент запоминается | `langgraph-swarm` | Длинные диалоги, где пользователь общается то с одним, то с другим специалистом |

Ключевое различие: в **supervisor** пользователь всегда «говорит» с супервизором, который делегирует работу; в **swarm** активным становится тот агент, которому передали управление, и следующий ход пользователя обрабатывает именно он.

### 17.2. Handoffs: передача управления через `Command`

Механизм, лежащий в основе всех паттернов, — объект `Command` из `langgraph.types`. Узел (или инструмент) может вернуть `Command`, который одновременно задаёт **куда идти** (`goto`) и **как обновить состояние** (`update`).

```python
from langgraph.types import Command

def agent_node(state) -> Command:
    return Command(
        goto="researcher",              # имя следующего узла
        update={"messages": [...]},     # частичный апдейт состояния
    )
```

Когда агент оформлен как **подграф**, простого `goto` недостаточно: узел внутри подграфа не «видит» узлы родительского графа. Чтобы передать управление на уровень родителя, указывают `graph=Command.PARENT`:

```python
from langgraph.types import Command

return Command(
    goto="other_agent",
    update={"messages": [...]},
    graph=Command.PARENT,   # навигация в РОДИТЕЛЬСКОМ графе
)
```

#### Handoff-инструмент

Чаще всего передачу управления оформляют как **инструмент** (tool), который LLM-агент вызывает сам. Инструмент возвращает `Command`, а `ToolNode` внутри агента умеет обрабатывать такой возврат. Каноническая фабрика handoff-инструмента:

```python
from typing import Annotated
from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import ToolMessage
from langgraph.prebuilt import InjectedState
from langgraph.graph import MessagesState
from langgraph.types import Command


def create_handoff_tool(*, agent_name: str, description: str | None = None):
    name = f"transfer_to_{agent_name}"
    description = description or f"Передать управление агенту {agent_name}."

    @tool(name, description=description)
    def handoff_tool(
        state: Annotated[MessagesState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        tool_message = ToolMessage(
            content=f"Управление передано агенту {agent_name}.",
            name=name,
            tool_call_id=tool_call_id,
        )
        return Command(
            goto=agent_name,                                  # имя целевого агента
            update={"messages": state["messages"] + [tool_message]},
            graph=Command.PARENT,                             # выходим в родительский граф
        )

    return handoff_tool
```

Разберём важные детали:

- **`InjectedState`** и **`InjectedToolCallId`** — аннотации, благодаря которым LangGraph подставит текущее состояние и `tool_call_id` автоматически; в схему инструмента, видимую модели, эти аргументы не попадают (модель их «не видит»). Импорты актуальны: `InjectedState` берётся из `langgraph.prebuilt`, а `tool`/`InjectedToolCallId` — из `langchain_core.tools`.
- В декораторе `@tool(name, description=description)` первым позиционным аргументом задаётся имя инструмента, а `description` — это штатный именованный параметр декоратора `tool` (переопределяет описание из докстринга).
- В `update` обязательно добавляется **`ToolMessage`** с тем же `tool_call_id`, что и вызвавший `AIMessage` с `tool_call`. Провайдеры (Anthropic, OpenAI и др.) требуют, чтобы каждый tool-call был закрыт tool-ответом; без этого следующий вызов модели упадёт с ошибкой о «висящем» tool-call.
- `goto=agent_name` вместе с `graph=Command.PARENT` перебрасывает исполнение на узел `agent_name` родительского графа.

> Примечание об актуальном API. В LangChain v1 у инструментов появился объект `ToolRuntime` (`from langchain.tools import tool, ToolRuntime`), через который доступны `runtime.state`, `runtime.tool_call_id`, `runtime.config` и т.п. — это более новая альтернатива паре `InjectedState`/`InjectedToolCallId`. Оба варианта рабочие; в примерах готовых библиотек (`langgraph-swarm`) исторически используется вариант с инъекциями.

### 17.3. Агенты как подграфы, передача состояния и сообщений

В мультиагентной системе каждый агент — это обычно откомпилированный граф (подграф). Готового агента создают через `create_react_agent` (из `langgraph.prebuilt`) либо через `create_agent` (из `langchain.agents`, рекомендуемый способ в LangChain v1). Обратите внимание, что в `create_agent` параметр системного промпта называется `system_prompt` (в `create_react_agent` — `prompt`). В обоих случаях получается полноценный `Pregel`/`CompiledStateGraph`, который можно встроить как узел или передать в фабрики `create_supervisor`/`create_swarm`.

Состояние между агентами передаётся через **общие каналы состояния**. Если все агенты используют схему на базе `MessagesState` (канал `messages` с reducer `add_messages`), то история диалога — это единый разделяемый список сообщений: апдейт от одного агента виден следующему. Именно поэтому в handoff-инструменте мы дописываем сообщения в `messages`, а не заводим отдельный канал. (Reducer `add_messages` дедуплицирует сообщения по их `id`, поэтому повторная передача `state["messages"] + [tool_message]` не создаёт дубликатов.)

Важный нюанс — **сколько** внутренних сообщений агента попадает в общую историю. В `langgraph-supervisor` это регулируется параметром `output_mode`:

- `output_mode="last_message"` (по умолчанию) — в общую историю добавляется только финальное сообщение агента;
- `output_mode="full"` — добавляется вся внутренняя «переписка» агента (все его tool-вызовы и ответы).

`last_message` экономит токены, но скрывает промежуточные рассуждения от других агентов; `full` даёт полную прозрачность ценой роста контекста.

### 17.4. Паттерн Network (сеть)

Простейшая реализация — граф, где каждый агент-узел через LLM решает, кому передать управление, возвращая `Command(goto=...)`. Маршрутизация не централизована.

```python
from typing import Literal
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.types import Command

model = ChatOpenAI(model="gpt-4o")

def agent_a(state: MessagesState) -> Command[Literal["agent_b", "__end__"]]:
    # ... вызов модели, решение о маршруте ...
    response = model.invoke(state["messages"])
    goto = "agent_b" if "delegate" in response.content.lower() else END
    return Command(goto=goto, update={"messages": [response]})

def agent_b(state: MessagesState) -> Command[Literal["agent_a", "__end__"]]:
    response = model.invoke(state["messages"])
    return Command(goto=END, update={"messages": [response]})

builder = StateGraph(MessagesState)
builder.add_node("agent_a", agent_a)
builder.add_node("agent_b", agent_b)
builder.add_edge(START, "agent_a")
graph = builder.compile()
```

Аннотация возвращаемого типа `Command[Literal[...]]` нужна, чтобы LangGraph корректно построил рёбра и отрисовал граф; в `Literal` перечисляют возможные значения `goto`. Значение `END` — это строковая константа `"__end__"`, поэтому его допустимо указывать и как `END`, и как строковый литерал (в аннотации выше используется явный `"__end__"`, чтобы не смущать статические анализаторы, которые не любят переменные внутри `Literal`). Здесь агенты — узлы одного графа, поэтому `graph=Command.PARENT` не требуется.

### 17.5. Паттерн Supervisor и библиотека `langgraph-supervisor`

Пакет `langgraph-supervisor` (`pip install langgraph-supervisor`) даёт готовую фабрику `create_supervisor`, которая строит граф: центральный супервизор с handoff-инструментами на каждого агента, куда управление возвращается после выполнения задачи.

Сигнатура (основные параметры, порядок как в исходнике):

```python
create_supervisor(
    agents: list[Pregel],                # список агентов-подграфов
    *,
    model: LanguageModelLike,            # модель супервизора-роутера
    tools=None,                          # доп. инструменты самого супервизора
    prompt=None,                         # системный промпт супервизора
    response_format=None,                # структурированный ответ
    pre_model_hook=None,                 # хук перед вызовом модели
    post_model_hook=None,                # хук после вызова модели
    state_schema=None,                   # кастомная схема состояния
    context_schema=None,                 # схема runtime-контекста
    output_mode="last_message",          # "last_message" | "full"
    add_handoff_messages=True,           # добавлять ли сообщения о передаче
    handoff_tool_prefix=None,            # префикс имён handoff-инструментов
    add_handoff_back_messages=None,      # сообщения о возврате к супервизору
    supervisor_name="supervisor",
    ...
) -> StateGraph                          # результат нужно .compile()
```

Полный рабочий пример супервизора с двумя агентами:

```python
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph_supervisor import create_supervisor

model = ChatOpenAI(model="gpt-4o")

# --- инструменты агентов ---
def add(a: float, b: float) -> float:
    """Сложить два числа."""
    return a + b

def multiply(a: float, b: float) -> float:
    """Умножить два числа."""
    return a * b

def web_search(query: str) -> str:
    """Найти информацию в интернете (заглушка)."""
    return f"Результаты поиска по запросу: {query}"

# --- специализированные агенты ---
math_agent = create_react_agent(
    model=model,
    tools=[add, multiply],
    name="math_expert",                 # имя обязательно и должно быть уникальным
    prompt="Ты эксперт по математике. Все вычисления делай только через инструменты.",
)

research_agent = create_react_agent(
    model=model,
    tools=[web_search],
    name="research_expert",
    prompt="Ты эксперт-исследователь. Находи факты в интернете.",
)

# --- супервизор ---
workflow = create_supervisor(
    agents=[math_agent, research_agent],
    model=model,
    prompt=(
        "Ты — супервизор, управляющий двумя агентами:\n"
        "- math_expert: любые вычисления;\n"
        "- research_expert: поиск фактов в интернете.\n"
        "Делегируй задачу подходящему агенту. Сам вычисления и поиск не выполняй."
    ),
    output_mode="last_message",
)

# компиляция (можно с checkpointer для памяти между вызовами)
app = workflow.compile(checkpointer=InMemorySaver())

config = {"configurable": {"thread_id": "1"}}
result = app.invoke(
    {"messages": [{"role": "user",
                   "content": "Найди население Москвы и Санкт-Петербурга и сложи их."}]},
    config,
)
for m in result["messages"]:
    m.pretty_print()
```

Как это работает: супервизор получает запрос, вызывает handoff-инструмент `transfer_to_research_expert`, тот исполняет поиск и возвращает управление супервизору; затем супервизор делегирует сложение `math_expert` и формирует финальный ответ. Все агенты пишут в общий канал `messages`.

Частые ошибки:
- **Забыли `name`** у агента — `create_supervisor` не сможет сгенерировать корректные имена handoff-инструментов (и упадёт на дублирующихся именах).
- **Забыли `.compile()`** — `create_supervisor` возвращает `StateGraph`, а не готовый к `invoke` объект.
- **Нет `checkpointer`**, но нужна память между репликами пользователя — тогда история не сохранится между вызовами `invoke`.

### 17.6. Паттерн Swarm и библиотека `langgraph-swarm`

Пакет `langgraph-swarm` (`pip install langgraph-swarm`) реализует децентрализованную топологию: агенты передают управление напрямую, а система запоминает «активного» агента в состоянии (`active_agent`). При следующем сообщении пользователя разговор продолжает именно активный агент, а не стартовый.

```python
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph_swarm import create_swarm, create_handoff_tool

model = ChatOpenAI(model="gpt-4o")

transfer_to_bob = create_handoff_tool(
    agent_name="Bob",
    description="Передать управление Bob для вопросов о погоде.",
)
transfer_to_alice = create_handoff_tool(
    agent_name="Alice",
    description="Передать управление Alice для математических задач.",
)

def multiply(a: float, b: float) -> float:
    """Умножить два числа."""
    return a * b

alice = create_react_agent(
    model,
    tools=[multiply, transfer_to_bob],
    prompt="Ты Alice, специалист по математике.",
    name="Alice",
)
bob = create_react_agent(
    model,
    tools=[transfer_to_alice],
    prompt="Ты Bob, отвечаешь на вопросы о погоде (можно выдумывать).",
    name="Bob",
)

workflow = create_swarm([alice, bob], default_active_agent="Alice")
# checkpointer ОБЯЗАТЕЛЕН, иначе active_agent не сохранится между вызовами
app = workflow.compile(checkpointer=InMemorySaver())

config = {"configurable": {"thread_id": "1"}}
app.invoke({"messages": [{"role": "user", "content": "Сколько будет 3 умножить на 4?"}]}, config)
# следующий ход обработает уже Bob, если Alice передала ему управление
app.invoke({"messages": [{"role": "user", "content": "А какая сегодня погода?"}]}, config)
```

Особенности `langgraph-swarm`:
- `default_active_agent` — обязательный keyword-only параметр `create_swarm`, задаёт, кто отвечает первым.
- `create_handoff_tool` импортируется прямо из `langgraph_swarm` (в отличие от «ручной» фабрики из раздела 17.2) и принимает `agent_name` и опциональный `description`.
- Схема состояния по умолчанию — `SwarmState` (расширение `MessagesState` полем `active_agent: str | None`); при кастомной схеме добавьте маршрутизатор через `add_active_agent_router`.
- **`checkpointer` обязателен** для сохранения `active_agent` между вызовами — без него рой каждый раз начинает со стартового агента.

### 17.7. Паттерн Hierarchical («команды команд»)

Когда агентов много, их группируют в команды, каждая со своим супервизором, а над ними ставят супервизор верхнего уровня. Поскольку откомпилированный супервизор — это тоже граф, его можно передать как «агента» в супервизор уровнем выше. Каждой команде задают уникальное имя через `.compile(name=...)`, чтобы супервизор верхнего уровня смог построить на них handoff-инструменты:

```python
research_team = create_supervisor(
    [research_agent, web_agent], model=model, supervisor_name="research_team",
).compile(name="research_team")

writing_team = create_supervisor(
    [writer_agent, editor_agent], model=model, supervisor_name="writing_team",
).compile(name="writing_team")

top = create_supervisor(
    [research_team, writing_team],           # команды выступают как агенты
    model=model,
    supervisor_name="top_supervisor",
).compile()
```

Так строится дерево: верхний супервизор выбирает команду, супервизор команды — конкретного исполнителя. Каждый уровень изолирует свою логику маршрутизации, что упрощает отладку и масштабирование.

### 17.8. Лучшие практики и типичные ошибки

- **Начинайте с супервизора.** Он проще в отладке и предсказуемее по маршрутизации; переходите к swarm/network, только когда централизация становится узким местом.
- **Давайте агентам уникальные `name`.** На именах строятся handoff-инструменты и маршруты.
- **Закрывайте tool-call через `ToolMessage`** с совпадающим `tool_call_id` — иначе провайдер вернёт ошибку о незакрытом вызове инструмента.
- **Следите за `output_mode`.** `full` раздувает контекст; `last_message` может скрыть нужные детали от других агентов.
- **Не забывайте `.compile()` и `checkpointer`.** Для swarm памяти checkpointer критичен; для supervisor — нужен, если требуется многоходовой диалог.
- **Согласуйте схемы состояния.** Ключи, которые вы обновляете через `Command.update`, должны существовать и в графе-родителе, и в целевом агенте.
- **Об устаревшем.** `create_react_agent` из `langgraph.prebuilt` в LangChain v1 помечен как устаревший (deprecated) в пользу `create_agent` из `langchain.agents`; старый путь ещё работает и по-прежнему используется в примерах самих библиотек `langgraph-supervisor`/`langgraph-swarm`. При переходе на `create_agent` учтите, что параметр `prompt` там переименован в `system_prompt`, а pre/post-хуки заменены системой middleware. Версии библиотек молодые (на июль 2026: `langgraph-supervisor` 0.0.31, `langgraph-swarm` 0.1.0), поэтому перед использованием сверяйтесь с актуальной сигнатурой в справочнике `reference.langchain.com`.


---


## 18. Долговременная память: Store (BaseStore)

`Store` — это отдельный от чекпоинтера механизм персистентности в LangGraph, предназначенный для **долговременной памяти**, которая живёт *между* потоками (threads), сессиями и пользователями. Если чекпоинтер сохраняет полный снимок состояния графа для одного конкретного `thread_id`, то `Store` хранит произвольные документы в иерархических пространствах имён (namespaces) и умеет искать по ним, в том числе семантически.

### 18.1. Зачем нужен Store и чем он отличается от checkpointer

Это ключевое различие, которое важно понять сразу:

| | Checkpointer (кратковременная память) | Store / BaseStore (долговременная память) |
|---|---|---|
| Что хранит | Полный снимок `state` графа (super-step) | Произвольные JSON-документы (`dict`) |
| Область видимости | Один `thread_id` (одна беседа) | Любые namespaces: пользователь, приложение, ассистент |
| Живёт | В пределах одного потока | Между потоками, сессиями и пользователями |
| Доступ | Автоматически через `configurable.thread_id` | Явно: `put` / `get` / `search` по namespace и key |
| Поиск | Нет | Есть, включая семантический поиск |
| Типовой пример | История сообщений текущего диалога | «Пользователь любит пиццу», факты о клиенте, профиль |

Проще говоря: чекпоинтер отвечает на вопрос «на чём мы остановились в *этом* разговоре», а `Store` — на вопрос «что мы вообще знаем про *этого пользователя* поверх всех разговоров». Их часто используют вместе:

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

checkpointer = InMemorySaver()   # кратковременная память одного thread
store = InMemoryStore()          # долговременная память между threads

graph = builder.compile(checkpointer=checkpointer, store=store)
```

### 18.2. Импорты и базовые классы

```python
from langgraph.store.base import BaseStore, Item, SearchItem  # интерфейс и модели данных
from langgraph.store.memory import InMemoryStore              # реализация в памяти
```

`BaseStore` — абстрактный интерфейс. Реализации:

- `InMemoryStore` (`langgraph.store.memory`) — хранит всё в оперативной памяти. Идеально для разработки, тестов и ноутбуков; данные теряются при перезапуске процесса. Для удобства он же реэкспортируется как `from langgraph.store import InMemoryStore`.
- `PostgresStore` / `AsyncPostgresStore` (`langgraph.store.postgres`; async-версия также доступна как `langgraph.store.postgres.aio.AsyncPostgresStore`) — продакшн-хранилище на PostgreSQL.
- `RedisStore` / `AsyncRedisStore` (`langgraph.store.redis`) — на Redis.

> Примечание об устаревшем: раньше встречалось `InMemoryStore(embedding_function=...)`. В актуальных версиях семантический поиск настраивается через параметр `index=...` (см. ниже), а не через `embedding_function`.

### 18.3. Namespaces (кортежи) и ключи

Каждый документ адресуется двумя вещами:

- **namespace** — кортеж строк, например `("user_123", "memories")` или `("app", "user_123", "preferences")`. Это иерархия, похожая на путь в файловой системе; по префиксу namespace потом можно искать.
- **key** — строка, уникальная в пределах namespace (например, UUID или осмысленный идентификатор).

Значение (`value`) — это всегда `dict`, сериализуемый в JSON.

```python
import uuid
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()

user_id = "user_123"
namespace = (user_id, "memories")

# запись
store.put(namespace, str(uuid.uuid4()), {"text": "Пользователь любит пиццу", "type": "food"})
store.put(namespace, "profile", {"name": "Мария", "lang": "ru"})
```

### 18.4. Основные операции: put, get, search, delete

Сигнатуры (синхронные; у каждой есть async-двойник с префиксом `a`: `aput`, `aget`, `asearch`, `adelete`, `alist_namespaces`):

```python
store.put(namespace, key, value, index=None, *, ttl=None)      # создать/перезаписать
store.get(namespace, key, *, refresh_ttl=None) -> Item | None   # получить один документ
store.search(namespace_prefix, *, query=None, filter=None,
             limit=10, offset=0, refresh_ttl=None) -> list[SearchItem]
store.delete(namespace, key)                                    # удалить
store.list_namespaces(*, prefix=None, suffix=None,
                      max_depth=None, limit=100, offset=0)       # перечислить namespaces
```

Что возвращается:

- `get()` — объект `Item` или `None`, если ключа нет. У `Item` есть атрибуты: `namespace`, `key`, `value` (тот самый `dict`), `created_at`, `updated_at`.
- `search()` — список `SearchItem`. Это тот же `Item`, но с дополнительным полем `score` (релевантность при семантическом поиске; `None`, если поиск был без `query`).

```python
# get
item = store.get(namespace, "profile")
if item is not None:
    print(item.value["name"])   # "Мария"
    print(item.created_at)      # datetime создания

# search без query — фильтрация по namespace-префиксу и по полям value
results = store.search((user_id, "memories"), filter={"type": "food"}, limit=5)
for r in results:
    print(r.key, r.value, r.score)  # score = None (запрос без семантики)

# delete
store.delete(namespace, "profile")
```

Параметр `filter` — это словарь для точного сопоставления по полям `value` (например `{"type": "food"}`). Параметр `ttl` (в минутах) задаёт время жизни записи, если реализация store его поддерживает; `refresh_ttl` при чтении продлевает срок жизни.

### 18.5. Семантический поиск

Чтобы `search(..., query="...")` возвращал документы по смысловой близости, store нужно создать с конфигурацией индексации `index`. Она описывает, чем и как эмбеддить документы.

```python
from langchain.embeddings import init_embeddings
from langgraph.store.memory import InMemoryStore

embeddings = init_embeddings("openai:text-embedding-3-small")  # объект Embeddings

store = InMemoryStore(
    index={
        "embed": embeddings,   # модель эмбеддингов (объект Embeddings, строка или функция)
        "dims": 1536,          # размерность векторов, должна совпадать с моделью
        "fields": ["text"],    # какие поля value эмбеддить; по умолчанию ["$"] — весь документ
    }
)

store.put(("user_123", "memories"), "1", {"text": "Я люблю пиццу"})
store.put(("user_123", "memories"), "2", {"text": "Небо сегодня ясное"})

# семантический поиск по запросу
items = store.search(("user_123", "memories"), query="Я голоден", limit=1)
print(items[0].value["text"])  # "Я люблю пиццу"
print(items[0].score)          # число: чем выше, тем ближе по смыслу
```

Ключевые моменты по `index`:

- `embed` может быть: объектом `Embeddings` из LangChain, строкой-идентификатором (`"openai:text-embedding-3-small"`), либо собственной функцией `(list[str]) -> list[list[float]]` (есть и async-вариант).
- `dims` обязателен и должен точно соответствовать размерности выбранной модели (например, `1536` для `text-embedding-3-small`).
- `fields` управляет тем, какие части документа индексируются. Можно указывать вложенные пути (`"user.bio"`). Спецзначение `["$"]` (по умолчанию) — эмбеддить весь документ целиком.

**Переопределение индексации на уровне записи.** Аргумент `index` у `put()` позволяет для конкретного документа выбрать другие поля или вовсе отключить эмбеддинг:

```python
# эмбеддить только поле "memory" этого документа
store.put(namespace, "1", {"memory": "любит пиццу", "context": "ужин"}, index=["memory"])

# не индексировать этот документ вовсе (будет доступен только через get/filter)
store.put(namespace, "2", {"system": "служебная запись"}, index=False)
```

Если `store` создан **без** `index`, вызов `search(..., query=...)` не упадёт, но `query` будет проигнорирован (семантического ранжирования не произойдёт) — вернётся обычная выборка по namespace/filter со `score = None`.

### 18.6. Доступ к store внутри узлов графа

Есть три рабочих способа получить store в узле.

**Способ 1. Инъекция через сигнатуру узла.** Если в узле объявить параметр `store: BaseStore`, LangGraph подставит store, переданный в `compile(store=...)`:

```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.store.base import BaseStore
from langchain_core.runnables import RunnableConfig

def call_model(state: MessagesState, config: RunnableConfig, *, store: BaseStore):
    user_id = config["configurable"]["user_id"]
    namespace = ("memories", user_id)
    memories = store.search(namespace, query=str(state["messages"][-1].content))
    info = "\n".join(m.value["text"] for m in memories)
    # ... используем info в промпте
    return {"messages": [...]}

builder = StateGraph(MessagesState)
builder.add_node("call_model", call_model)
builder.add_edge(START, "call_model")
builder.add_edge("call_model", END)
graph = builder.compile(store=store)

graph.invoke(
    {"messages": [{"role": "user", "content": "привет"}]},
    {"configurable": {"thread_id": "t1", "user_id": "user_123"}},
)
```

**Способ 2. `get_store()`.** Функция `get_store` достаёт store из контекста выполнения без изменения сигнатуры узла:

```python
from langgraph.config import get_store

def my_node(state):
    store = get_store()                       # тот же store, что передан в compile(store=...)
    val = store.get(("values",), "foo").value["bar"]
    return {"foo": val + 1}
```

> Важно: `get_store()` использует `contextvars` и в асинхронном режиме корректно работает только на Python >= 3.11. В синхронном режиме ограничения нет.

**Способ 3. Runtime-инъекция (рекомендуемый в актуальных версиях).** Store доступен через объект `Runtime`, туда же попадает и типизированный `context` графа:

```python
import uuid
from langgraph.graph import MessagesState
from langgraph.runtime import Runtime
from dataclasses import dataclass

@dataclass
class Context:
    user_id: str

async def call_model(state: MessagesState, runtime: Runtime[Context]):
    namespace = (runtime.context.user_id, "memories")
    memories = await runtime.store.asearch(namespace, query=state["messages"][-1].content, limit=3)
    await runtime.store.aput(namespace, str(uuid.uuid4()), {"text": "предпочитает тёмную тему"})
```

Схема контекста объявляется при сборке графа, а само значение передаётся при вызове через аргумент `context`, а не через `configurable`:

```python
builder = StateGraph(MessagesState, context_schema=Context)
# ...
graph.invoke(
    {"messages": [{"role": "user", "content": "привет"}]},
    {"configurable": {"thread_id": "t1"}},
    context=Context(user_id="user_123"),
)
```

### 18.7. Store в create_agent / create_react_agent и в инструментах

Префилд-агент принимает `store` как аргумент; store прокидывается во все узлы и инструменты агента. В актуальных версиях (LangChain 1.0+) высокоуровневый конструктор агента — это `create_agent` из пакета `langchain.agents`:

```python
from langchain.agents import create_agent

agent = create_agent(model, tools=[...], store=store, checkpointer=checkpointer)
```

> Устаревшее: `from langgraph.prebuilt import create_react_agent` по-прежнему работает и тоже принимает `store`/`checkpointer`, но помечен как deprecated в пользу `create_agent` (у последнего гибкая система middleware). В части `store`/`checkpointer` их сигнатуры совместимы.

Чтобы **инструмент** мог читать/писать в долговременную память, есть два подхода.

`get_store()` внутри тела инструмента (просто и не засоряет схему для LLM):

```python
import uuid
from langchain_core.tools import tool
from langgraph.config import get_store

@tool
def save_memory(text: str) -> str:
    """Сохранить факт о пользователе."""
    store = get_store()
    store.put(("memories",), str(uuid.uuid4()), {"text": text})
    return "сохранено"
```

Либо аннотация `InjectedStore` — store подставится в аргумент, но при этом будет скрыт от модели (LLM не увидит его в схеме инструмента):

```python
from typing import Annotated
from langchain_core.tools import tool
from langgraph.store.base import BaseStore
from langgraph.prebuilt import InjectedStore

@tool
def search_memories(query: str, *, store: Annotated[BaseStore, InjectedStore()]) -> str:
    """Найти релевантные факты о пользователе."""
    items = store.search(("memories",), query=query, limit=3)
    return "\n".join(i.value["text"] for i in items)
```

> В новых версиях, помимо `InjectedStore`, инструмент может получать среду выполнения через зарезервированный аргумент `runtime` (`ToolRuntime`) и обращаться к `runtime.store` — это постепенно вытесняет громоздкую `Annotated[..., InjectedStore()]`-форму. Оба варианта пока рабочие.

### 18.8. Типичные ошибки и лучшие практики

- **Забыли передать store в `compile(store=...)` / `create_agent(store=...)`.** Тогда `get_store()` и инъекция вернут `None`/ошибку. Store не создаётся автоматически.
- **`dims` не совпадает с моделью эмбеддингов** — семантический поиск будет падать или давать мусор. Держите `dims` синхронным с моделью.
- **Путают уровни памяти.** Историю текущего диалога хранит чекпоинтер (по `thread_id`), а факты о пользователе — store (по namespace с `user_id`). Не пытайтесь класть профиль пользователя в state отдельного thread.
- **Изоляция пользователей через namespace.** Всегда включайте `user_id` (или tenant) в namespace, например `(user_id, "memories")`, чтобы поиск одного пользователя не задевал данные другого.
- **`value` должен быть JSON-сериализуемым** `dict`. Не кладите туда произвольные объекты.
- **`InMemoryStore` не персистентен.** Для продакшна используйте `PostgresStore`/`RedisStore` и не забудьте однократно вызвать `store.setup()` (или `await store.setup()`) для создания таблиц/индексов.
- **Батчинг и async.** Для высоконагруженных сценариев используйте async-методы (`aput`, `asearch`) и групповые операции `batch` / `abatch`, чтобы не блокировать событийный цикл.


---


## 19. Деплой, LangSmith, отладка и лучшие практики

Этот раздел закрывает жизненный цикл графа после того, как логика написана: как поднять его как настоящий сервис, как включить наблюдаемость через LangSmith, как отлаживать выполнение и какие типовые ошибки runtime отравляют жизнь чаще всего. Всё, что ниже, ориентировано на актуальные версии `langgraph` (1.x), `langgraph-cli` и `langsmith`.

### 19.1. LangGraph Platform и `langgraph-cli`

LangGraph Platform (с конца 2025 года в документации также фигурирует под названием **LangSmith Deployment**) — это способ запустить граф как долгоживущий HTTP-сервер с персистентностью, очередью задач, потоковой отдачей и API управления «ассистентами» и «тредами». Локально и в CI всё это обслуживает пакет `langgraph-cli`.

```bash
# CLI + локальный dev-сервер без Docker (inmem)
pip install -U "langgraph-cli[inmem]"
```

#### Файл `langgraph.json`

Точка входа для CLI. Кладётся в корень проекта; CLI по умолчанию ищет именно `langgraph.json` в текущем каталоге.

```json
{
  "dependencies": ["."],
  "graphs": {
    "agent": "./src/my_app/graph.py:graph"
  },
  "env": "./.env",
  "python_version": "3.12"
}
```

Ключевые поля:

| Поле | Назначение |
|------|-----------|
| `dependencies` | Список зависимостей: локальные пакеты (`"."`, `"./libs/foo"`) и/или PyPI-имена (`"langchain_openai"`). Обязательно. |
| `graphs` | Словарь `имя_графа -> "путь/к/файлу.py:переменная"`. Переменная — это скомпилированный граф (`CompiledStateGraph`) либо фабрика (в т.ч. async), возвращающая граф. Обязательно. |
| `env` | Путь к `.env` или объект с переменными окружения. |
| `python_version` | Версия рантайма (`"3.11"`, `"3.12"`, `"3.13"`). |
| `dockerfile_lines` | Дополнительные строки, инъецируемые в сгенерированный `Dockerfile`. |
| `store` | Конфигурация долговременного `Store` (например индексация эмбеддингов для семантического поиска, TTL). |
| `checkpointer` | Конфигурация бэкенда чекпоинтера и TTL (для персистентности тредов на платформе). |
| `auth` | Путь к кастомной аутентификации (`./auth.py:auth`). |
| `http` | Настройки HTTP-приложения (кастомные роуты, CORS, middleware). |

Важно: в `graphs` указывается именно граф-объект (результат `builder.compile()`), а не сам `StateGraph`. При деплое на Platform **не нужно** передавать свой checkpointer/store в `compile()` — платформа подставит продакшн-персистентность сама. Локально же для сохранения состояния checkpointer необходим (см. 19.4).

#### Команды CLI

```bash
langgraph dev         # лёгкий dev-сервер в памяти, hot-reload, без Docker
langgraph build       # собрать Docker-образ приложения
langgraph up          # поднять сервер в Docker (Postgres + Redis в контейнерах)
langgraph dockerfile  # сгенерировать Dockerfile из langgraph.json
langgraph deploy      # (beta) собрать и задеплоить образ в LangSmith Deployment
```

- `langgraph dev` — основной инструмент разработки. Поднимает in-memory сервер (`--host`, `--port`, по умолчанию `2024`), автоматически перезагружает граф при изменениях кода (`--no-reload` отключает) и сразу даёт ссылку на LangGraph Studio для визуальной отладки. Docker не требуется.
- `langgraph up` — запуск полноценного стека в контейнерах, максимально близкий к продакшену: сервер + Postgres (checkpointer/store) + Redis (очередь). Нужен только Docker — Postgres и Redis поднимаются автоматически как контейнеры. Полезные флаги: `-p/--port` (по умолчанию `8123`), `--watch` (перезапуск при изменениях), `--wait`, `--postgres-uri` (внешняя БД).
- `langgraph build` / `langgraph dockerfile` — сборка образа и генерация `Dockerfile` для собственного пайплайна деплоя.
- `langgraph deploy` — команда в статусе beta: собирает образ и публикует его в управляемый сервис (с подкомандами `deploy list`, `deploy logs` и т.п.). Классический путь деплоя — через control plane / UI LangSmith (собрать образ `langgraph build`, запушить в реестр, задеплоить из панели).

> Устаревшее: раньше для трейсинга требовались переменные с префиксом `LANGCHAIN_*` (`LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`) — сейчас канонический префикс `LANGSMITH_*` (`LANGSMITH_TRACING`, `LANGSMITH_API_KEY`); старые имена ещё поддерживаются ради обратной совместимости. Локальную разработку теперь ведут через `langgraph dev` из пакета `langgraph-cli[inmem]`.

#### Assistants API (кратко)

Развёрнутый граф — это «шаблон». **Assistant** — это именованная конфигурация поверх графа (модель, промпт, `configurable`-параметры), версионируемая независимо от кода. Клиент работает с ассистентами и тредами:

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:2024")

assistant = await client.assistants.create(
    graph_id="agent",
    config={"configurable": {"model_name": "gpt-4o"}},
)
thread = await client.threads.create()

async for chunk in client.runs.stream(
    thread["thread_id"],
    assistant["assistant_id"],
    input={"messages": [{"role": "user", "content": "Привет"}]},
    stream_mode="values",
):
    print(chunk.data)
```

Треды хранят историю (через checkpointer платформы), поэтому диалог автоматически персистентен между запусками.

### 19.2. LangSmith: трейсинг и наблюдаемость

LangSmith — сервис для трейсинга, отладки и оценки LLM-приложений. Для базового трейсинга код менять не нужно: достаточно переменных окружения.

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY="lsv2_pt_..."           # ключи LangSmith имеют префикс lsv2_
export LANGSMITH_PROJECT="my-project"            # необязательно, иначе "default"
# для не-US регионов:
# export LANGSMITH_ENDPOINT="https://eu.api.smith.langchain.com"
```

| Переменная | Назначение |
|-----------|-----------|
| `LANGSMITH_TRACING` | `true` включает автоматический трейсинг. |
| `LANGSMITH_API_KEY` | Ключ доступа к LangSmith (префикс `lsv2_pt_` / `lsv2_sk_`). |
| `LANGSMITH_PROJECT` | Имя проекта, куда пишутся трейсы. |
| `LANGSMITH_ENDPOINT` | URL API (EU/APAC/self-hosted). |

Любой вызов LangChain/LangGraph (`Runnable.invoke`, `graph.invoke/stream`, чат-модели, инструменты) при `LANGSMITH_TRACING=true` автоматически шлёт трейсы: видны узлы, тайминги, вход/выход состояния, промпты, токены и ошибки. Это работает без правок кода.

#### Декоратор `@traceable`

Для произвольного Python-кода вне LangChain (свои функции, вызовы SDK) используется декоратор `@traceable` из пакета `langsmith`.

```python
from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import OpenAI

client = wrap_openai(OpenAI())  # оборачивает клиент, чтобы вызовы попадали в трейс

@traceable(run_type="retriever")
def retrieve(query: str) -> list[str]:
    return ["doc1", "doc2"]

@traceable  # run_type="chain" по умолчанию
def pipeline(question: str) -> str:
    docs = retrieve(question)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"{question}\n{docs}"}],
    )
    return resp.choices[0].message.content
```

`@traceable` создаёт узел (run) в текущем трейсе, вкладывает вложенные вызовы иерархически и логирует входы/выходы/исключения. `run_type` бывает `"chain"`, `"llm"`, `"tool"`, `"retriever"`, `"prompt"`, `"parser"`. Метаданные и теги добавляются через `@traceable(metadata={...}, tags=[...])`.

> Тонкость: сам по себе `@traceable` пишет трейс только когда включён трейсинг (`LANGSMITH_TRACING=true`) — иначе это фактически no-op. Для точечного включения без глобальной переменной есть контекст-менеджер `from langsmith import tracing_context` → `with tracing_context(enabled=True): ...`.

### 19.3. Отладка графа

#### Визуализация: `draw_mermaid`

Скомпилированный граф умеет рисовать себя. Это первое, что стоит сделать при непонятной маршрутизации.

```python
print(graph.get_graph().draw_mermaid())          # Mermaid-текст в консоль

# PNG (по умолчанию через mermaid.ink API; можно локально через pyppeteer):
png = graph.get_graph().draw_mermaid_png()
with open("graph.png", "wb") as f:
    f.write(png)
```

Для XRay-детализации подграфов: `graph.get_graph(xray=True)`.

#### `stream_mode="debug"`

Режим потоковой отдачи, показывающий низкоуровневые события выполнения: задачи (`task`), их результаты (`task_result`) и точки checkpoint. Незаменим, когда узел «молча» не отрабатывает.

```python
for event in graph.stream(
    {"messages": [("user", "hi")]},
    config={"configurable": {"thread_id": "1"}},
    stream_mode="debug",
):
    print(event["type"], event["step"], event.get("payload", {}).get("name"))
```

`stream_mode` можно передать списком (`["values", "debug"]`) — тогда каждый элемент приходит кортежем `(mode, data)`, помеченным типом.

#### История состояния: `get_state_history`

При наличии checkpointer можно поднять полную историю чекпоинтов треда — это основа для отладки и time-travel (перезапуск с прошлой точки).

```python
config = {"configurable": {"thread_id": "1"}}

# текущее состояние
snapshot = graph.get_state(config)
print(snapshot.values, snapshot.next)   # next — какие узлы выполнятся дальше

# вся история (от новых к старым)
for state in graph.get_state_history(config):
    print(state.config["configurable"]["checkpoint_id"], state.next)

# time-travel: возобновить с конкретного чекпоинта
graph.invoke(None, config={"configurable": {
    "thread_id": "1",
    "checkpoint_id": "<нужный checkpoint_id>",
}})
```

#### Тестирование

Граф детерминистичен по структуре, поэтому тестируется как обычный код. Полезные приёмы: узлы — чистые функции (легко юнит-тестировать по отдельности), `InMemorySaver` в тестах вместо Postgres, фейковые модели.

```python
from langchain_core.messages import AIMessage
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langgraph.checkpoint.memory import InMemorySaver

def test_graph_reaches_end():
    fake = GenericFakeChatModel(messages=iter([AIMessage(content="ok")]))
    graph = build_graph(model=fake).compile(checkpointer=InMemorySaver())
    out = graph.invoke({"messages": []},
                       config={"configurable": {"thread_id": "t1"}})
    assert out["messages"][-1].content == "ok"
```

### 19.4. Типичные ошибки runtime

#### `GraphRecursionError` — превышен `recursion_limit`

Граф выполнил больше «супершагов», чем разрешено (по умолчанию 25), не дойдя до `END`. Обычно это признак цикла без корректного условия выхода. Лечение — либо чинить логику маршрутизации, либо (осознанно) поднять лимит:

```python
from langgraph.errors import GraphRecursionError

try:
    graph.invoke(inputs, config={"recursion_limit": 100})
except GraphRecursionError:
    print("Граф зациклился — проверьте условные рёбра и условие выхода")
```

`recursion_limit` — это ключ верхнего уровня в `config`, **не** внутри `configurable`.

#### `InvalidUpdateError` — конкурентные записи без reducer

Возникает, когда два узла в одном супершаге пишут в один и тот же ключ состояния, а для него не задан reducer. LangGraph не знает, как объединить значения.

```python
from typing import Annotated
from operator import add
from typing_extensions import TypedDict

# БЫЛО: параллельные узлы пишут в state["items"] -> InvalidUpdateError
class State(TypedDict):
    items: list[str]

# СТАЛО: reducer add конкатенирует списки из разных веток
class State(TypedDict):
    items: Annotated[list[str], add]
```

Для сообщений используйте `Annotated[list, add_messages]` из `langgraph.graph.message`. Та же ошибка появляется при веерном ветвлении (в т.ч. через `Command(goto=[...])`), когда несколько параллельных веток пишут в один ключ без совместимого reducer.

#### Забытый checkpointer при `interrupt`

`interrupt()` замораживает граф и требует персистентности, чтобы восстановиться при возобновлении. Без checkpointer возобновление невозможно.

```python
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver

def approve(state):
    decision = interrupt({"question": "Подтвердить?"})   # пауза
    return {"approved": decision == "yes"}

graph = builder.compile(checkpointer=InMemorySaver())    # без этого — ошибка

cfg = {"configurable": {"thread_id": "1"}}
graph.invoke({...}, cfg)                    # остановится на interrupt
graph.invoke(Command(resume="yes"), cfg)    # тот же thread_id — возобновление
```

Правила: (1) без checkpointer `interrupt` не работает; (2) возобновление идёт через `Command(resume=...)`; (3) `thread_id` при паузе и возобновлении должен совпадать; (4) узел, содержащий `interrupt`, после resume выполняется с начала — не держите в нём необратимых сайд-эффектов до вызова `interrupt`.

> На Platform checkpointer подставляется автоматически, поэтому в `compile()` его передавать не нужно; локально — обязательно.

#### Циклы без условия выхода

Ребро, безусловно возвращающее в предыдущий узел, гарантирует `GraphRecursionError`. Всегда завершайте цикл условным ребром, ведущим в `END`:

```python
from langgraph.graph import StateGraph, START, END

def should_continue(state) -> str:
    if len(state["messages"]) > 6 or state.get("done"):
        return END
    return "agent"

builder.add_conditional_edges("agent", should_continue, ["tools", END])
```

### 19.5. Лучшие практики структурирования

- **Узлы — маленькие чистые функции.** Один узел = один осмысленный шаг. Сигнатура `(state) -> dict` (или `(state, config)`, а в 1.x — ещё и `(state, runtime)` для доступа к `Runtime`), возврат — только изменившиеся ключи, а не весь `state`. Меньше состояния мутируется — легче тестировать и трейсить.
- **Состояние проектируйте явно.** `TypedDict` (или Pydantic-модель) с говорящими полями; reducer'ы для всех ключей, куда может писать более одного узла; отдельными `input`/`output`-схемами ограничивайте публичный контракт графа.
- **Разделяйте слои.** Бизнес-логику и вызовы инструментов держите в обычных функциях, а узлы — тонкими адаптерами над ними. Это упрощает юнит-тесты и переиспользование.
- **Маршрутизация — через условные рёбра.** Явные функции-роутеры с `Literal`-возвращаемыми значениями читаемее, чем ветвление внутри узлов, и лучше видны на диаграмме.
- **Конфигурируемость через `configurable`.** Модель, температуру, промпты выносите в `config["configurable"]` — это же то, что параметризует Assistants на Platform.
- **Готовые агенты.** Для стандартного ReAct-агента используйте `create_agent` из `langchain.agents` (актуальная замена устаревшего `create_react_agent` из `langgraph.prebuilt`) — меньше шаблонного кода, плюс система middleware.
- **Наблюдаемость с первого дня.** Включайте `LANGSMITH_TRACING` уже в разработке; `langgraph dev` + Studio дают визуальный степпинг, а `get_state_history` — time-travel по багам.
- **Идемпотентность и таймауты.** Проектируйте узлы так, чтобы повторное выполнение (после resume/ретрая) не ломало данные; для внешних вызовов задавайте таймауты и стратегию ретраев на уровне узла.
