# Бот «Про Финансы Ясно» (MAX)

Первая версия бота для канала [Про Финансы Ясно].

Принцип: **минимальный первый сценарий — максимальная готовность к расширению**.

## Сценарий v1

```
Новый подписчик → приветствие → кнопка «Получить полезные материалы»
→ переход в бот (?start=materials) → выдача материалов в ЛС
→ предложение задать вопрос → сохранение обращения (Новая заявка)
```

## Стек

- Python 3.12+
- FastAPI (webhook)
- SQLAlchemy 2 (async) + SQLite (dev) / PostgreSQL (prod)
- Тонкий HTTP-клиент к `platform-api2.max.ru`

## Быстрый старт

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e .

copy .env.example .env          # заполните MAX_BOT_TOKEN и BOT_USERNAME
python -m app.tools.build_ca_bundle   # сертификаты Минцифры для TLS
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> MAX API использует TLS-сертификаты Минцифры. Без `certs/ca-bundle.pem` будет ошибка `CERTIFICATE_VERIFY_FAILED`.
При старте приложение создаёт таблицы и заливает seed-контент (тексты, кнопки, материалы).

### Long polling (для локальной разработки)

```bash
python -m app.polling
```

## Админка

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Откройте http://localhost:8000/admin/

Логин/пароль по умолчанию: `admin` / `admin123` (из `.env`: `ADMIN_USERNAME` / `ADMIN_PASSWORD`). Учётка хранится в таблице `admin_users`.

Команда `/admin` в боте присылает ссылку администраторам из `ADMIN_PLATFORM_USER_IDS` (MAX `user_id`, несколько через запятую: `5600001,18473332`). Если доступа нет — бот ответит вашим `user_id`, его нужно добавить в `.env` и перезапустить. На сервере также задайте публичный `ADMIN_PUBLIC_URL` (не `localhost`).

Разделы v1: обзор, тексты, **меню /**, **кнопки**, обращения, материалы, настройки, пользователи.
Новые разделы добавляются в `app/admin/views/` и подключаются в `app/admin/__init__.py`.

Меню бота в MAX синхронизируется из раздела «Меню /» (кнопка «Синхронизировать с MAX» или при старте приложения).

Webhook и long polling одновременно использовать нельзя.

### Webhook (production)

1. Поднимите HTTPS endpoint.
2. Укажите `WEBHOOK_URL` и `WEBHOOK_SECRET` в `.env`.
3. Зарегистрируйте подписку:

```bash
python -m app.register_webhook
```

## Конфигурация

| Слой | Что хранится |
|------|----------------|
| `.env` | токен, БД, webhook secret, режим |
| БД (`messages`, `buttons`, `materials`, `settings`) | тексты, ссылки, кнопки, материалы |

Имя бота, URL deep link и тексты меняются **без правок кода**.

## Структура

```
app/
  config.py           # техническая конфигурация
  main.py             # FastAPI + webhook
  db/models/          # users, materials, messages, buttons, leads, events, consents…
  max_api/            # адаптер MAX API
  services/           # контент, шаблоны, пользователи, лиды, события
  scenarios/          # модули сценариев (расширяемые)
  handlers/           # маршрутизация Update
  seed/               # начальный контент из ТЗ
```

## Важные настройки в БД / seed

- `bot_display_name` — название бота
- `useful_materials_deeplink` — deep link с `?start=materials`
- `useful_materials_url` — отдельный URL материалов (если нужен)
- сообщения: `new_subscriber_welcome`, `materials_sent`, `question_request`
- кнопка: `useful_materials`

## Критерии приёмки (чеклист)

1. Новый подписчик → приветствие + кнопка  
2. Deep link `materials` → автовыдача после старта  
3. Материалы только в ЛС, по `sort_order`  
4. Смена URL в settings без деплоя кода  
5. Смена текста в `messages` без деплоя кода  
6. Вопрос → lead со статусом `new`  
7. Повтор события → без дублей  

## Spike MAX (обязательно на стенде)

Проверьте, что бот может отправить ЛС по `user_id` сразу после `user_added` в канале **до** нажатия «Начать».  
Если платформа запрещает — приветствие нужно перенести на канал/комментарий с deep link (архитектура это допускает).

## Docker (сервер: админка + бот)

На сервере без домена поднимаются три сервиса: PostgreSQL, веб (админка) и long polling бота.

```bash
cp .env.example .env
# заполните MAX_BOT_TOKEN, BOT_USERNAME, ADMIN_PASSWORD, ADMIN_SECRET_KEY
# ADMIN_PUBLIC_URL=http://IP_СЕРВЕРА:8000/admin

docker compose up -d --build
```

- Админка: `http://IP_СЕРВЕРА:8000/admin/` (логин из `.env`)
- Бот: контейнер `bot` тянет обновления через long polling (публичный URL не нужен)
- БД: только внутри сети compose (`db:5432`)

Полезные команды:

```bash
docker compose logs -f web bot
docker compose restart bot
docker compose stop bot          # если переходите на webhook
docker compose down              # остановить всё (данные Postgres в volume pgdata)
```

Webhook и long polling одновременно нельзя. Для webhook оставьте только `web`, укажите `WEBHOOK_URL` и выполните регистрацию внутри контейнера:

```bash
docker compose stop bot
docker compose exec web python -m app.register_webhook
```
