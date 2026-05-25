from telegram import Update
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import config
import database

NAME, LAST_NAME, EMAIL, PHONE = range(4)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = database.get_user_by_telegram_id(update.effective_user.id)
    if user:
        await update.message.reply_text(
            f"Вы уже зарегистрированы!\nСсылка на канал: {config.CHANNEL_LINK}"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Добро пожаловать! Давайте зарегистрируем вас на вебинар.\n\nВведите ваше имя:"
    )
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Имя не может быть пустым. Введите имя:")
        return NAME

    context.user_data["first_name"] = text
    await update.message.reply_text("Введите вашу фамилию:")
    return LAST_NAME


async def get_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Фамилия не может быть пустой. Введите фамилию:")
        return LAST_NAME

    context.user_data["last_name"] = text
    await update.message.reply_text("Введите ваш email:")
    return EMAIL


async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Email не может быть пустым. Введите email:")
        return EMAIL

    context.user_data["email"] = text
    await update.message.reply_text("Введите ваш номер телефона:")
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Телефон не может быть пустым. Введите номер телефона:")
        return PHONE

    database.add_user(
        telegram_id=update.effective_user.id,
        first_name=context.user_data["first_name"],
        last_name=context.user_data["last_name"],
        email=context.user_data["email"],
        phone=text,
    )

    await update.message.reply_text(
        f"Вы успешно зарегистрированы на вебинар!\n\nСсылка на канал: {config.CHANNEL_LINK}"
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Регистрация отменена. Напишите /start чтобы начать заново.")
    return ConversationHandler.END


conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        NAME:      [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
        LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_last_name)],
        EMAIL:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
        PHONE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
