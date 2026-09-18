import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dateutil.rrule import rrulestr

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.database.users.dao import EventDAO, UserDAO
from bot.handlers.incoming import router

logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def reminder_worker(bot: Bot) -> None:
	while True:
		try:
			now = datetime.now(timezone.utc)
			for event in await EventDAO.due_for_reminder(now):
				user = await UserDAO.find_one_or_none(tg_id=event.user_id)
				user_timezone = ZoneInfo(user.timezone) if user and user.timezone else ZoneInfo(settings.TIMEZONE)
				starts_at = event.starts_at.astimezone(user_timezone)
				await bot.send_message(
					event.user_id,
					f"Напоминание: {event.title}\nНачало: {starts_at:%d.%m.%Y %H:%M}",
				)
				if event.recurrence_rule:
					next_starts_at = rrulestr(
						event.recurrence_rule,
						dtstart=event.starts_at,
					).after(event.starts_at)
					if next_starts_at is not None:
						duration = event.ends_at - event.starts_at if event.ends_at else None
						await EventDAO.update(
							event.id,
							starts_at=next_starts_at,
							ends_at=next_starts_at + duration if duration else None,
							reminder_sent=False,
						)
					else:
						await EventDAO.update(event.id, reminder_sent=True)
				else:
					await EventDAO.update(event.id, reminder_sent=True)
				logger.info("Reminder sent for event %s", event.id)
		except Exception:
			logger.exception("Reminder worker failed")
		await asyncio.sleep(60)


async def main() -> None:
	logger.info("Starting bot")
	bot = Bot(settings.TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
	dispatcher = Dispatcher(storage=MemoryStorage())
	dispatcher.include_router(router)
	reminder_task = asyncio.create_task(reminder_worker(bot))

	try:
		logger.info("Starting Telegram polling")
		await dispatcher.start_polling(bot)
	except Exception:
		logger.exception("Telegram polling failed")
		raise
	finally:
		reminder_task.cancel()
		logger.info("Closing bot session")
		await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
