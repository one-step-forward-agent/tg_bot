import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, LinkPreviewOptions

from bot.config import settings
from bot.handlers import account, agenda, chat, notifications
from bot.services.backend import backend

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="today", description="План на сегодня"),
    BotCommand(command="tomorrow", description="План на завтра"),
    BotCommand(command="week", description="Ближайшие 7 дней"),
    BotCommand(command="done", description="Отметить выполненные задачи"),
    BotCommand(command="stats", description="Статистика выполнения"),
    BotCommand(command="reminders", description="Настройки напоминаний"),
    BotCommand(command="help", description="Что я умею"),
    BotCommand(command="unlink", description="Отключить Telegram от Dayla"),
]


async def main() -> None:
    bot = Bot(
        settings.TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview=LinkPreviewOptions(is_disabled=True)),
    )
    dispatcher = Dispatcher()
    dispatcher.include_routers(account.router, agenda.router, notifications.router, chat.router)
    await bot.set_my_commands(COMMANDS)
    await bot.set_my_description(
        "Dayla — ИИ-ассистент для планирования. Пишите планы словами или голосом, "
        "спрашивайте о расписании и получайте напоминания. Подключите аккаунт на сайте Dayla."
    )
    await bot.set_my_short_description("Планируйте день за минуту: чат, расписание и напоминания")
    worker = asyncio.create_task(notifications.worker(bot))
    try:
        logger.info("Starting Telegram polling")
        await dispatcher.start_polling(bot)
    finally:
        worker.cancel()
        await backend.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
