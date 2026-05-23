# bot.py — Telegram-бот: ретранслятор между клиентами и группой менеджеров

import os
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    ContextTypes,
)

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ─────────────────────────────────────────────────────────────────────────────
# НАСТРОЙКИ — подставьте свои значения через переменные окружения
# или замените строки ниже напрямую
# ─────────────────────────────────────────────────────────────────────────────

# Токен бота от @BotFather
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ID закрытой группы менеджеров (отрицательное число)
MANAGER_GROUP_ID: int = int(os.getenv("MANAGER_GROUP_ID", "-5108511404"))

# Точное название Google Таблицы (как в заголовке документа)
SPREADSHEET_NAME: str = os.getenv("SPREADSHEET_NAME", "YOUR_SPREADSHEET_NAME")

# Путь к JSON-файлу с ключом сервисного аккаунта Google
GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

# Заголовки колонок таблицы: A=user_id, B=message_id, C=text, D=datetime
SHEET_HEADERS = ["user_id", "message_id", "text", "datetime"]

# ─────────────────────────────────────────────────────────────────────────────
# ЛОГИРОВАНИЕ
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# РАБОТА С GOOGLE ТАБЛИЦЕЙ
# ─────────────────────────────────────────────────────────────────────────────

def get_worksheet() -> gspread.Worksheet:
    """Авторизуется в Google API и возвращает первый лист таблицы."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        GOOGLE_CREDENTIALS_FILE, scope
    )
    client = gspread.authorize(creds)
    return client.open(SPREADSHEET_NAME).sheet1


def init_sheet_headers() -> None:
    """
    Проверяет наличие заголовков в первой строке таблицы.
    Если строка пустая или заголовки не совпадают — вставляет их.
    """
    sheet = get_worksheet()
    first_row = sheet.row_values(1)
    if first_row != SHEET_HEADERS:
        sheet.insert_row(SHEET_HEADERS, index=1)
        logger.info("Заголовки таблицы созданы.")


def save_to_sheet(user_id: int, message_id: int, text: str) -> None:
    """
    Добавляет строку в таблицу:
    user_id клиента, message_id пересланного сообщения, текст, дата-время.
    """
    sheet = get_worksheet()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([user_id, message_id, text, now])
    logger.info(f"Таблица: добавлена строка [{user_id}, {message_id}, ...]")


def find_user_id_by_message_id(message_id: int) -> int | None:
    """
    Ищет user_id клиента в таблице по message_id пересланного сообщения
    (колонка B). Возвращает int или None, если запись не найдена.
    """
    sheet = get_worksheet()
    all_rows = sheet.get_all_values()
    # Перебираем строки, пропуская заголовок (первая строка)
    for row in all_rows[1:]:
        if len(row) >= 2 and row[1] == str(message_id):
            return int(row[0])
    return None


# ─────────────────────────────────────────────────────────────────────────────
# ОБРАБОТЧИКИ СООБЩЕНИЙ
# ─────────────────────────────────────────────────────────────────────────────

async def handle_client_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Срабатывает при любом личном сообщении от клиента (не команда).

    Действия:
    1. Пересылает сообщение в группу менеджеров.
    2. Сохраняет в таблицу: user_id, message_id пересланного сообщения, текст, время.
    """
    message = update.effective_message
    user = update.effective_user

    logger.info(f"Входящее от клиента {user.id} (@{user.username}): {message.text!r}")

    # Пересылаем сообщение в группу; forwarded содержит новый message_id уже в группе
    try:
        forwarded = await context.bot.forward_message(
            chat_id=MANAGER_GROUP_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
        )
    except Exception as e:
        logger.error(f"Не удалось переслать сообщение в группу: {e}")
        return

    # Берём текст сообщения; для медиафайлов используем подпись (caption)
    text = message.text or message.caption or "[медиафайл без текста]"

    # Сохраняем привязку: message_id в группе → user_id клиента
    try:
        save_to_sheet(
            user_id=user.id,
            message_id=forwarded.message_id,
            text=text,
        )
    except Exception as e:
        logger.error(f"Ошибка записи в Google Таблицу: {e}")


async def handle_manager_reply(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Срабатывает только на Reply-сообщения менеджера в группе.

    Действия:
    1. Берёт message_id исходного сообщения (то, на которое ответил менеджер).
    2. Находит по нему user_id клиента в Google Таблице.
    3. Пересылает ответ менеджера клиенту в личные сообщения.
    """
    message = update.effective_message

    # Дополнительная защита: reply_to_message гарантирован фильтром filters.REPLY,
    # но на всякий случай проверяем ещё раз
    if not message.reply_to_message:
        return

    replied_to_id = message.reply_to_message.message_id
    logger.info(f"Менеджер ответил на message_id={replied_to_id} в группе")

    # Ищем user_id клиента по сохранённому message_id
    try:
        user_id = find_user_id_by_message_id(replied_to_id)
    except Exception as e:
        logger.error(f"Ошибка поиска в Google Таблице: {e}")
        return

    if user_id is None:
        # Менеджер ответил на сообщение, которое бот не пересылал — игнорируем
        logger.info(
            f"message_id={replied_to_id} не найден в таблице — "
            "скорее всего, ответ внутри группы. Пропускаем."
        )
        return

    # Копируем ответ менеджера клиенту (copy_message сохраняет медиа, стикеры и т.д.)
    try:
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
        )
        logger.info(f"Ответ менеджера успешно отправлен клиенту {user_id}")
    except Exception as e:
        logger.error(f"Не удалось отправить ответ клиенту {user_id}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# ЗАПУСК БОТА
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Проверяем/создаём заголовки таблицы при старте
    try:
        init_sheet_headers()
    except Exception as e:
        logger.error(f"Не удалось подключиться к Google Таблице при старте: {e}")

    app = Application.builder().token(BOT_TOKEN).build()

    # Обработчик личных сообщений от клиентов (любой тип, кроме команд)
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & ~filters.COMMAND,
            handle_client_message,
        )
    )

    # Обработчик Reply-сообщений менеджеров только в нужной группе
    app.add_handler(
        MessageHandler(
            filters.Chat(chat_id=MANAGER_GROUP_ID) & filters.REPLY,
            handle_manager_reply,
        )
    )

    logger.info("Бот запущен. Ожидание сообщений...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
