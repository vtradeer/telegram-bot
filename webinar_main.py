import logging
import threading

from telegram.ext import ApplicationBuilder

import config
import database
import handlers
import reminders

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    database.init_db()

    app = ApplicationBuilder().token(config.BOT_TOKEN).build()
    app.add_handler(handlers.conversation_handler)

    threading.Thread(
        target=reminders.run_reminder_loop,
        args=(config.BOT_TOKEN,),
        daemon=True,
    ).start()

    logger.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
