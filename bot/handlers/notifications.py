import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.keyboards import digest_keyboard, reminder_keyboard
from bot.services.backend import BackendError, backend
from bot.templates import messages

router = Router()
logger = logging.getLogger(__name__)


def keyboard_for(item: dict):
    if item.get("kind") == "reminder":
        return reminder_keyboard(item["id"], item.get("url"))
    if item.get("kind") == "digest":
        return digest_keyboard()
    return None


async def deliver(bot: Bot, item: dict) -> None:
    try:
        await bot.send_message(item["chat_id"], item["text"], reply_markup=keyboard_for(item))
    except TelegramRetryAfter as error:
        await backend.ack_notification(item["id"], ok=False, error=f"retry after {error.retry_after}s")
        await asyncio.sleep(error.retry_after)
    except TelegramForbiddenError as error:
        await backend.ack_notification(item["id"], ok=False, error=str(error), chat_unreachable=True)
    except TelegramBadRequest as error:
        await backend.ack_notification(item["id"], ok=False, error=str(error), chat_unreachable="chat not found" in str(error).lower())
    except Exception as error:
        logger.exception("Failed to deliver notification %s", item["id"])
        await backend.ack_notification(item["id"], ok=False, error=str(error))
    else:
        await backend.ack_notification(item["id"], ok=True)
        logger.info("Notification %s (%s) delivered", item["id"], item["kind"])


async def worker(bot: Bot) -> None:
    while True:
        try:
            for item in await backend.claim_notifications():
                await deliver(bot, item)
        except BackendError as error:
            logger.warning("Notification claim failed: %s", error.detail)
        except Exception:
            logger.exception("Notification worker failed")
        await asyncio.sleep(settings.NOTIFICATION_POLL_SECONDS)


@router.callback_query(F.data.startswith("sn:"))
async def snooze(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Это сообщение устарело — отправьте команду ещё раз", show_alert=True)
        return
    try:
        _, notification_id, minutes = callback.data.split(":")
        await backend.snooze(int(notification_id), callback.message.chat.id, int(minutes))
    except (ValueError, BackendError):
        await callback.answer("Не получилось отложить напоминание", show_alert=True)
        return
    try:
        await callback.message.edit_text(f"{callback.message.html_text}\n\n<i>{messages.snoozed(int(minutes))}</i>", reply_markup=None)
    except TelegramBadRequest:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(messages.snoozed(int(minutes)))
