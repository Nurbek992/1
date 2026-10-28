# Чат-бот на n8n

Готовый workflow `chat-bot-workflow.json`: встроенный веб-чат n8n → AI-агент на Claude → ответ в чат. Диалог помнит последние 10 сообщений.

## Состав

| Нода | Назначение |
| --- | --- |
| Chat Trigger | Принимает сообщения из встроенного чат-виджета n8n |
| AI Agent | Формирует ответ по системному промпту |
| Anthropic Chat Model | Модель `claude-sonnet-5-5` |
| Window Buffer Memory | Хранит историю диалога по `sessionId` |

## Установка

1. В n8n: **Workflows → Import from File** и выберите `chat-bot-workflow.json`.
2. Откройте ноду **Anthropic Chat Model** и создайте credential типа *Anthropic API* с вашим API-ключом. Выберите его в ноде.
3. Нажмите **Save**, затем **Publish** (или переключите **Active**).
4. Откройте ссылку **Chat** из ноды Chat Trigger и напишите боту.

## Настройка

- Поведение бота задаётся в поле **System Message** ноды AI Agent.
- Другая модель: поменяйте значение в **Anthropic Chat Model**.
- Длина памяти: параметр **Context Window Length** в Window Buffer Memory.
- Другой канал (Telegram, Slack и т.д.): замените Chat Trigger на нужный триггер, остальные ноды оставьте.

## Важно

- В JSON стоит плейсхолдер `REPLACE_WITH_CREDENTIAL_ID`. n8n заменит его при выборе credential в ноде; в коде API-ключи не хранятся.
- Версии нод соответствуют n8n 1.x с пакетом LangChain-нод. Если импорт ругается на версию, обновите n8n или выберите ноды вручную по тем же типам.
