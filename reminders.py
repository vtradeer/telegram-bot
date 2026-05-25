import logging
import time
from datetime import datetime, timezone

import requests

import config
import database

logger = logging.getLogger(__name__)

REMINDER_OFFSETS = {
    "7d":    7 * 24 * 3600,
    "3d":    3 * 24 * 3600,
    "1d":    24 * 3600,
    "1h":    3600,
    "10m":   600,
    "start": 0,
}

REMINDER_TEXTS = {
    "7d":    "🔔 До вебинара осталась неделя! Ждём вас {date} в 18:00.",
    "3d":    "🔔 До вебинара осталось 3 дня!",
    "1d":    "🔔 Вебинар уже завтра в 18:00!",
    "1h":    "🔔 Вебинар начнётся через час!",
    "10m":   "🔔 Вебинар начнётся через 10 минут!",
    "start": "🔔 Вебинар начинается прямо сейчас! Подключайтесь!",
}


def parse_webinar_datetime(dt_str: str) -> datetime:
    """Парсит строку вида '2026-06-01 18:00' в datetime (UTC)."""
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)


def get_reminder_time(webinar_dt: datetime, offset_seconds: int) -> datetime:
    from datetime import timedelta
    return webinar_dt - timedelta(seconds=offset_seconds)


def _send_message(bot_token: str, chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    response = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    response.raise_for_status()


def check_reminders(bot_token: str):
    webinar_dt = parse_webinar_datetime(config.WEBINAR_DATETIME)
    webinar_date_str = webinar_dt.strftime("%d.%m.%Y")

    while True:
        now = datetime.now(timezone.utc)
        users = database.get_all_users()

        for user in users:
            registered_at = datetime.fromisoformat(user["registered_at"]).replace(tzinfo=timezone.utc)

            for key, offset in REMINDER_OFFSETS.items():
                reminder_time = get_reminder_time(webinar_dt, offset)

                if reminder_time > now:
                    continue
                if registered_at > reminder_time:
                    continue
                if database.is_reminder_sent(user["id"], key):
                    continue

                text = REMINDER_TEXTS[key].format(date=webinar_date_str)
                try:
                    _send_message(bot_token, user["telegram_id"], text)
                    database.mark_reminder_sent(user["id"], key)
                    logger.info("Напоминание %s отправлено пользователю %s", key, user["telegram_id"])
                except requests.HTTPError as e:
                    if e.response is not None and e.response.status_code == 403:
                        logger.warning("Пользователь %s заблокировал бота", user["telegram_id"])
                    else:
                        logger.error("Ошибка при отправке %s пользователю %s: %s", key, user["telegram_id"], e)
                except Exception as e:
                    logger.error("Неожиданная ошибка для пользователя %s: %s", user["telegram_id"], e)

        time.sleep(60)


def run_reminder_loop(bot_token: str):
    logger.info("Запуск цикла напоминаний")
    check_reminders(bot_token)
