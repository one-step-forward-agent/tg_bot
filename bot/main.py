import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, LinkPreviewOptions

from bot.config import settings
from bot.handlers import account, agenda, chat, group, notifications
from bot.i18n import LanguageMiddleware
from bot.services.backend import backend

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="today", description="План на сегодня"),
    BotCommand(command="tomorrow", description="План на завтра"),
    BotCommand(command="week", description="Ближайшие 7 дней"),
    BotCommand(command="done", description="Отметить выполненные задачи"),
    BotCommand(command="stats", description="Статистика выполнения"),
    BotCommand(command="advice", description="Советы по плану"),
    BotCommand(command="analysis", description="Анализ недели"),
    BotCommand(command="reminders", description="Настройки напоминаний"),
    BotCommand(command="help", description="Что я умею"),
    BotCommand(command="unlink", description="Отключить Telegram от Deyla"),
]
COMMANDS_EN = [
    BotCommand(command="today", description="Today's plan"),
    BotCommand(command="tomorrow", description="Tomorrow's plan"),
    BotCommand(command="week", description="The next 7 days"),
    BotCommand(command="done", description="Mark tasks done"),
    BotCommand(command="stats", description="Progress"),
    BotCommand(command="advice", description="Advice on the plan"),
    BotCommand(command="analysis", description="The week's analysis"),
    BotCommand(command="reminders", description="Reminder settings"),
    BotCommand(command="help", description="What I can do"),
    BotCommand(command="unlink", description="Disconnect Telegram from Deyla"),
]


async def main() -> None:
    bot = Bot(
        settings.TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview=LinkPreviewOptions(is_disabled=True)),
    )
    dispatcher = Dispatcher()
    # Every answer in the language chosen on the Deyla site
    dispatcher.message.outer_middleware(LanguageMiddleware())
    dispatcher.callback_query.outer_middleware(LanguageMiddleware())
    dispatcher.include_routers(account.router, agenda.router, notifications.router, chat.router, group.router)
    await bot.set_my_commands(COMMANDS)
    # Telegram apps in English see the English menu before the account is linked
    await bot.set_my_commands(COMMANDS_EN, language_code="en")
    await bot.set_my_description(
        "Deyla — ИИ-ассистент для планирования. Пишите планы словами или голосом, "
        "пересылайте билеты и скриншоты, спрашивайте о расписании и получайте напоминания. В рабочем чате упомяните "
        "меня — задача попадёт в ваш календарь. Подключите аккаунт на сайте Deyla."
    )
    await bot.set_my_short_description("Планируйте день за минуту: чат, расписание и напоминания")
    await bot.set_my_description(
        "Deyla is an AI planning assistant. Write your plans in words or by voice, forward tickets and screenshots, "
        "ask about your schedule and get reminders. In a work chat, mention me — the task goes to your calendar. "
        "Connect your account on the Deyla site.",
        language_code="en",
    )
    await bot.set_my_short_description("Plan your day in a minute: chat, schedule and reminders", language_code="en")
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
