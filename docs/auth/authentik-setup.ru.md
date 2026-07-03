# Настройка SSO через authentik (инструкция для администратора)

Документ описывает, что **администратор** должен сделать, чтобы включить
единый вход (SSO) для платформы Science-Ball через
[authentik](https://github.com/goauthentik/authentik) как OIDC‑провайдера, и как
**сопоставить роли и группы с доступом к источникам**, чтобы пользователь не
получал данные из источника, к которому у его роли нет доступа.

Интеграция сделана **опциональной**: пока `OIDC_ENABLED=false`, api‑gateway
работает как раньше (демо‑вход `POST /api/v1/auth/login`, HS256). После включения
шлюз **дополнительно** принимает OIDC‑токены authentik: проверяет их подпись по
JWKS провайдера и сопоставляет claim `groups` с ролью платформы.

Все команды выполняются из корня репозитория.

---

## Обзор архитектуры (что с чем связано)

```
Пользователь → SPA (frontend) → authentik (вход, PKCE) → OIDC access/ID токен
                                                              │
                             Authorization: Bearer <токен>    ▼
                                              api-gateway  →  api_gateway/oidc.py
                                                              • проверка RS256 по JWKS
                                                              • iss / aud / exp
                                                              • claim groups → Role
                                                              • claim groups lab:* → labs
                                                              ▼
                                              RBAC: kg_common.security.clearance
                                              роль → допустимые access_level
                                              (public / internal / restricted)
```

* **Роль** (`groups` → `Role`) определяет, до какого уровня секретности источников
  пользователь допущен (таблица ниже).
* **Лаборатория** (`groups` вида `lab:<id>` → `labs`) определяет доступ к источникам
  с политикой `lab_restricted`.

---

## Шаг 0. Предварительные требования

* Установлены Docker и Docker Compose.
* Скопирован `.env`: `cp .env.example .env`.
* Известно доменное имя/адрес, по которому будет доступен authentik (для локальной
  разработки — `http://localhost:9100`).

---

## Шаг 1. Запустить authentik

authentik поднимается **отдельным overlay‑файлом** (со своими PostgreSQL и Redis),
рядом с основным стеком:

```bash
# 1) Сгенерировать секрет authentik и записать его в .env
echo "AUTHENTIK_SECRET_KEY=$(openssl rand -base64 60 | tr -d '\n')" >> .env
# 2) Задать пароль первого администратора (akadmin) в .env
#    AUTHENTIK_BOOTSTRAP_PASSWORD=<надёжный-пароль>
# 3) Поднять authentik вместе с базовым стеком
docker compose -f infra/docker-compose.yml -f infra/docker-compose.authentik.yml up -d \
  authentik-postgresql authentik-redis authentik-server authentik-worker
```

Проверить готовность: `docker compose ... ps` — сервис `authentik-server` должен
быть `healthy`. UI будет доступен на **http://localhost:9100** (порт 9000 занят
minio; при необходимости поменяйте `AUTHENTIK_HTTP_PORT` в `.env`).

> Тег образа задаётся `AUTHENTIK_TAG` (по умолчанию `2024.12`). Проверьте актуальный
> релиз на https://github.com/goauthentik/authentik/releases и при желании обновите.

---

## Шаг 2. Первый вход

1. Откройте `http://localhost:9100/if/flow/initial-setup/` (или войдите на
   `/if/admin/` как `akadmin` с паролем из `AUTHENTIK_BOOTSTRAP_PASSWORD`).
2. Смените пароль администратора.
3. После настройки уберите `AUTHENTIK_BOOTSTRAP_PASSWORD`/`AUTHENTIK_BOOTSTRAP_TOKEN`
   из `.env` (bootstrap нужен только для первого запуска).

---

## Шаг 3. Создать OAuth2/OIDC‑провайдер

**Applications → Providers → Create → OAuth2/OpenID Provider.** Параметры:

| Поле | Значение |
|---|---|
| **Name** | `science-ball` |
| **Authorization flow** | `default-provider-authorization-explicit-consent` (или implicit) |
| **Client type** | `Public` (для SPA с PKCE) либо `Confidential` |
| **Client ID** | скопируйте — это `OIDC_CLIENT_ID` |
| **Client Secret** | только для Confidential — это `OIDC_CLIENT_SECRET` |
| **Redirect URIs** | `http://localhost:3000/auth/callback` (адрес SPA, = `OIDC_REDIRECT_URI`) |
| **Signing Key** | любой RSA‑ключ (`authentik Self-signed Certificate`) → токены подписываются **RS256** |
| **Scopes** | `openid`, `email`, `profile`, **и обязательно scope с claim `groups`** (см. Шаг 5) |

Сохраните.

---

## Шаг 4. Создать Application

**Applications → Applications → Create.**

| Поле | Значение |
|---|---|
| **Name** | `Science-Ball` |
| **Slug** | `science-ball` — попадёт в issuer URL |
| **Provider** | выбрать созданный `science-ball` |

**Issuer** платформы будет:
`http://localhost:9100/application/o/science-ball/` — это `OIDC_ISSUER`.
Проверить можно по адресу
`http://localhost:9100/application/o/science-ball/.well-known/openid-configuration`.

---

## Шаг 5. Включить claim `groups` в токене (важно!)

Роли и лаборатории берутся из claim `groups`. По умолчанию его нет в токене.

1. **Customization → Property Mappings.** Убедитесь, что есть маппинг
   *«authentik default OAuth Mapping: OpenID 'groups'»* (он добавляет массив имён
   групп в claim `groups`). Если его нет — создайте **Scope Mapping**:
   * **Scope name:** `groups`
   * **Expression:**
     ```python
     return {"groups": [group.name for group in request.user.ak_groups.all()]}
     ```
2. Вернитесь в **Provider `science-ball` → Advanced protocol settings → Scopes** и
   добавьте scope `groups` в список.

После этого токен будет содержать, например:
`"groups": ["curator", "lab:lab_a"]`.

---

## Шаг 6. Создать группы и пользователей

**Directory → Groups.** Создайте группы, **имена которых совпадают с ролями
платформы**, и (при необходимости) группы лабораторий с префиксом `lab:`.

Роли платформы: `researcher`, `analyst`, `project_manager`, `curator`, `admin`,
`external_partner`.

| Группа authentik | Назначение |
|---|---|
| `admin` | роль admin |
| `curator` | роль curator |
| `project_manager` | роль project_manager |
| `analyst` | роль analyst |
| `researcher` | роль researcher (по умолчанию, если совпадений нет) |
| `external_partner` | роль external_partner |
| `lab:lab_a`, `lab:lab_b`, … | членство в лаборатории (для источников `lab_restricted`) |

**Directory → Users** — создайте пользователей и добавьте их в нужные группы
(роль + одну или несколько лабораторий). Если у пользователя несколько «ролевых»
групп — платформа берёт **самую привилегированную** (admin > project_manager >
curator > analyst > researcher > external_partner).

> **Альтернатива именам‑ролям.** Если ваши группы называются иначе (например
> `kg-admins`), задайте явный маппинг в `.env`:
> `OIDC_GROUP_ROLE_MAP='{"kg-admins":"admin","kg-curators":"curator"}'`.

---

## Шаг 7. Настроить `.env` платформы

Впишите в `.env` значения из authentik:

```bash
OIDC_ENABLED=true
OIDC_ISSUER=http://localhost:9100/application/o/science-ball/
OIDC_CLIENT_ID=<Client ID из Шага 3>
OIDC_CLIENT_SECRET=<Client Secret, если Confidential; иначе пусто>
OIDC_AUDIENCE=<обычно = Client ID; пусто — не проверять>
OIDC_GROUPS_CLAIM=groups
OIDC_REDIRECT_URI=http://localhost:3000/auth/callback
# при нестандартных именах групп:
# OIDC_GROUP_ROLE_MAP={"kg-admins":"admin"}
```

`OIDC_JWKS_URL` можно не задавать — он определяется автоматически из issuer.

---

## Шаг 8. Перезапустить api‑gateway и проверить

```bash
docker compose -f infra/docker-compose.yml up -d api-gateway
# публичная конфигурация OIDC для фронтенда:
curl -s http://localhost:8010/api/v1/auth/oidc/config | jq
# войдя в authentik, фронтенд получит токен; проверьте роль:
curl -s http://localhost:8010/api/v1/auth/me -H "Authorization: Bearer <OIDC-токен>" | jq
# → {"user":"<логин>","role":"<роль по группам>"}
```

Фронтенд использует `/auth/oidc/config` (issuer, client_id, authorization_endpoint)
для запуска потока Authorization Code + PKCE и затем шлёт полученный токен в
`Authorization: Bearer …`.

---

## Роль → уровень доступа к источникам (что кому видно)

Каждый факт/источник помечен уровнем секретности `access_level` (он же
`confidentiality_level` на узле графа): `public` < `internal` < `restricted`.
Роль допущена до своего уровня и **ниже**; более секретные источники **не
попадают в ответ** (шлюз их отфильтровывает, а прямой запрос к доказательству
возвращает `403`).

| Роль | public | internal | restricted |
|---|:---:|:---:|:---:|
| `external_partner` | ✅ | ❌ | ❌ |
| `researcher` | ✅ | ✅ | ❌ |
| `analyst` | ✅ | ✅ | ❌ |
| `project_manager` | ✅ | ✅ | ✅ |
| `curator` | ✅ | ✅ | ✅ |
| `admin` | ✅ | ✅ | ✅ |
| *неизвестная роль* | ✅ | ❌ | ❌ (fail‑closed) |

Кроме уровня секретности, источник может иметь политику `lab_restricted` — тогда
доступ есть только у владельца, `admin` и у пользователей, чьи `labs`
(из групп `lab:*`) пересекаются с разрешёнными лабораториями источника
(`kg_common.security.source_access`).

Правило кодифицировано в `kg_common/security/clearance.py`
(`ROLE_MAX_CLEARANCE`) — при необходимости поменяйте соответствие ролей уровням
там (это единственная точка правды).

### Как помечать источники уровнем доступа

При загрузке документа/каталога укажите уровень на узле (`access_level` в
контрактах данных, `confidentiality_level` — типизированная колонка узла графа).
Непомеченный источник считается `public`. Значение `restricted` (либо legacy
`commercial_secret`) видно только `curator`/`project_manager`/`admin`.

---

## Проверка фильтрации по источникам

```bash
# внешний партнёр не видит internal/restricted сущности в поиске:
curl -s "http://localhost:8010/api/v1/entities/search?q=сплав" \
  -H "X-Role: external_partner"      # (dev-заголовок; в проде — Bearer OIDC)
# прямой доступ к restricted-доказательству ролью ниже допуска → 403:
curl -s -o /dev/null -w "%{http_code}\n" \
  http://localhost:8010/api/v1/evidence/<restricted-ev-id> -H "X-Role: researcher"
# → 403
```

---

## Откат / отключение SSO

Поставьте `OIDC_ENABLED=false` и перезапустите api‑gateway — платформа вернётся к
демо‑входу. Контейнеры authentik можно остановить:
`docker compose -f infra/docker-compose.yml -f infra/docker-compose.authentik.yml stop authentik-server authentik-worker`.

---

## Альтернатива: forward‑auth (Proxy Provider)

Вместо приложения OIDC можно поставить **Proxy Provider** authentik + outpost
перед шлюзом (аутентификация на уровне reverse‑proxy, заголовки `X-authentik-*`).
Это не требует изменений кода, но требует reverse‑proxy (Traefik/nginx). Для
данной платформы штатный путь — OIDC‑приложение (описано выше), потому что RBAC и
фильтрация по источникам уже используют роль/лаборатории из токена.
```
