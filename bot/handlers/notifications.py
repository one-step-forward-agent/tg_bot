import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import settings
from bot.i18n import using
from bot.keyboards import checkin_keyboard, deadline_keyboard, digest_keyboard, evening_keyboard, friend_keyboard, reminder_keyboard
from bot.services.backend import BackendError, backend
from bot.templates import messages

router = Router()
logger = logging.getLogger(__name__)


def keyboard_for(item: dict):
    if item.get("kind") == "reminder":
        return reminder_keyboard(item["id"], item.get("url"), item.get("event_id"))
    if item.get("kind") == "custom":
        # A reminder the user asked for ("напомни через 10 минут …"): it can be put off
        return reminder_keyboard(item["id"], None)
    if item.get("kind") == "digest":
        return digest_keyboard()
    if item.get("kind") == "checkin":
        return checkin_keyboard(item["id"], item.get("payload"))
    if item.get("kind") == "evening":
        return evening_keyboard(item["id"], item.get("payload"))
    if item.get("kind") in ("friend", "friend_start"):
        # A friend's task, its start or an invitation: the card in the payload says which buttons
        return friend_keyboard((item.get("payload") or {}).get("card"))
    if item.get("kind") == "deadline":
        return deadline_keyboard(item.get("event_id"), item.get("url"))
    return None


async def deliver(bot: Bot, item: dict) -> None:
    with using(item.get("language")):
        await send(bot, item)


CAPTION_LIMIT = 1024


async def send(bot: Bot, item: dict) -> None:
    try:
        attached = (item.get("payload") or {}).get("file")
        if isinstance(attached, dict):
            await send_with_file(bot, item, attached)
        else:
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


async def send_with_file(bot: Bot, item: dict, attached: dict) -> None:
    """"Пришли этот файл в 21:00": the file comes as a document, the reminder's text as its caption (or just above
    it when too long for one). A file already gone still leaves the reminder's text."""
    try:
        content = await backend.notification_file(item["id"])
    except BackendError as error:
        logger.warning("File of notification %s is not available: %s", item["id"], error.detail)
        await bot.send_message(item["chat_id"], item["text"], reply_markup=keyboard_for(item))
        return
    document = BufferedInputFile(content, filename=str(attached.get("name") or "file"))
    if len(item["text"]) <= CAPTION_LIMIT:
        await bot.send_document(item["chat_id"], document, caption=item["text"], reply_markup=keyboard_for(item))
        return
    await bot.send_message(item["chat_id"], item["text"])
    await bot.send_document(item["chat_id"], document, reply_markup=keyboard_for(item))


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
        await callback.answer(messages.outdated("command"), show_alert=True)
        return
    try:
        _, notification_id, minutes = callback.data.split(":")
        await backend.snooze(int(notification_id), callback.message.chat.id, int(minutes))
    except (ValueError, BackendError):
        await callback.answer(messages.short("snooze_failed"), show_alert=True)
        return
    try:
        await callback.message.edit_text(f"{callback.message.html_text}\n\n<i>{messages.snoozed(int(minutes))}</i>", reply_markup=None)
    except TelegramBadRequest:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(messages.snoozed(int(minutes)))


@router.callback_query(F.data.startswith("rd:"))
async def reminder_done(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer(messages.outdated(), show_alert=True)
        return
    try:
        await backend.complete(callback.message.chat.id, int(callback.data.split(":")[1]))
    except (ValueError, BackendError):
        await callback.answer(messages.short("mark_failed"), show_alert=True)
        return
    try:
        await callback.message.edit_text(f"{callback.message.html_text}\n\n✅ <i>{messages.short('done_label')}</i>", reply_markup=None)
    except TelegramBadRequest:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(messages.short("done"))


@router.callback_query(F.data.startswith("ci:"))
async def checkin_answer(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer(messages.outdated(), show_alert=True)
        return
    try:
        _, notification_id, action = callback.data.split(":")
        result = await backend.checkin(int(notification_id), callback.message.chat.id, action)
    except (ValueError, BackendError):
        await callback.answer(messages.short("try_again"), show_alert=True)
        return
    try:
        await callback.message.edit_text(f"{callback.message.html_text}\n\n<i>{messages.checkin_result(result)}</i>", reply_markup=None)
    except TelegramBadRequest:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
