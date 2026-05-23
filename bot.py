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
# НАСТРОЙКИ
# ─────────────────────────────────────────────────────────────────────────────

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "8928167415:AAEgSP4_UVq9hMOF7rFj0RVW65h6jxUonnY")
MANAGER_GROUP_ID: int = int(os.getenv("MANAGER_GROUP_ID", "-5108511404"))
SPREADSHEET_NAME: str = os.getenv("SPREADSHEET_NAME", "Клиенты")
GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

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
    sheet = get_worksheet()
    first_row = sheet.row_values(1)
    if first_row != SHEET_HEADERS:
        sheet.insert_row(SHEET_HEADERS, index=1)
        logger.info("Заголовки таблицы созданы.")

def save_to_sheet(user_id: int, message_id: int, text: str) -> None:
    sheet = get_worksheet()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([user_id, message_id, text, now])
    logger.info(f"Таблица: добавлена строка [{user_id}, {message_id}, ...]")

def find_user_id_by_message_id(message_id: int) -> int | None:
    sheet = get_worksheet()
    all_rows = sheet.get_all_values()
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
    message = update.effective_message
    user = update.effective_user

    logger.info(f"Входящее от клиента {user.id} (@{user.username}): {message.text!r}")

    try:
        forwarded = await context.bot.forward_message(
            chat_id=MANAGER_GROUP_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
        )
    except Exception as e:
        logger.error(f"Не удалось переслать сообщение в группу: {e}")
        return

    text = message.text or message.caption or "[медиафайл без текста]"

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
    message = update.effective_message

    if not message.reply_to_message:
        return

    replied_to_id = message.reply_to_message.message_id
    logger.info(f"Менеджер ответил на message_id={replied_to_id} в группе")

    try:
        user_id = find_user_id_by_message_id(replied_to_id)
    except Exception as e:
        logger.error(f"Ошибка поиска в Google Таблице: {e}")
        return

    if user_id is None:
        logger.info(
            f"message_id={replied_to_id} не найден в таблице — "
            "скорее всего, ответ внутри группы. Пропускаем."
        )
        return

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
    try:
        init_sheet_headers()
    except Exception as e:
        logger.error(f"Не удалось подключиться к Google Таблице при старте: {e}")

    app_telegram = Application.builder().token(BOT_TOKEN).build()

    app_telegram.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & ~filters.COMMAND,
            handle_client_message,
        )
    )

    app_telegram.add_handler(
        MessageHandler(
            filters.Chat(chat_id=MANAGER_GROUP_ID) & filters.REPLY,
            handle_manager_reply,
        )
    )

    logger.info("Бот запущен. Ожидание сообщений...")
    app_telegram.run_polling(allowed_updates=Update.ALL_TYPES)
