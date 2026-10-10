import asyncio
import logging
import os
import tempfile

from aiogram import Bot, F, Router
from aiogram.enums import ChatType, ContentType
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, ForceReply, Message
from aiogram.utils.chat_action import ChatActionSender

from bot.handlers.account import report
from aiogram.filters import Command

from bot.keyboards import (
    TOPIC_REPLIES,
    advice_keyboard,
    agenda_keyboard,
    created_keyboard,
    delete_keyboard,
    done_keyboard,
    settings_keyboard,
    topic_keyboard,
    expand_ids,
    proposal_item_keyboard,
    proposal_keyboard,
    rated,
    reminder_set_keyboard,
    targets_keyboard,
    updated_keyboard,
    with_rating,
)
from bot.services import site
from bot.services.backend import BackendError, backend
from bot.services.speech import recognize_audio
from bot.services.text_extractors import extract_document
from bot.templates import messages

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)
logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 20 * 1024 * 1024
DOCUMENT_TYPES = (".pdf", ".docx")


async def deliver(message: Message, reply: dict) -> None:
    app_url = await site.app_url()
    kind = reply.get("kind")
    rating = reply.get("message_id")
    if kind == "proposal":
        await message.answer(messages.proposal(reply), reply_markup=proposal_markup(reply))
    elif kind == "delete_proposal":
        await message.answer(messages.delete_proposal(reply), reply_markup=delete_keyboard(reply["draft_id"], reply["count"]))
    elif kind in ("created", "updated"):
        await message.answer(messages.created(reply), reply_markup=result_keyboard(reply, app_url))
    elif kind == "completed":
        await message.answer(messages.completed(reply), reply_markup=with_rating(None, rating))
    elif kind == "agenda" and reply.get("mark"):
        await message.answer(messages.done_list(reply), reply_markup=done_keyboard(reply, reply.get("scope") or "today"))
    elif kind == "agenda":
        await message.answer(messages.agenda(reply), reply_markup=with_rating(agenda_keyboard(reply.get("scope"), app_url), rating))
    elif kind == "stats":
        await message.answer(messages.stats(reply), reply_markup=with_rating(None, rating))
    elif kind == "help":
        await message.answer(messages.help_sections(reply))
    elif kind == "advice":
        await message.answer(messages.advice(reply), reply_markup=advice_keyboard(len(reply.get("items") or []), rating))
    elif kind == "reminders":
        await message.answer(messages.reminder_settings(None, reply["settings"]), reply_markup=settings_keyboard(reply["settings"], app_url))
    elif kind == "reminder":
        await message.answer(messages.reminder_set(reply), reply_markup=with_rating(reminder_set_keyboard(reply.get("reminders") or []), rating))
    elif kind == "topic":
        await message.answer(messages.topic(reply), reply_markup=topic_keyboard())
    elif kind == "answer":
        await message.answer(messages.answer(reply["text"]), reply_markup=with_rating(None, rating))
    elif kind == "not_found":
        await message.answer(messages.not_found(reply["text"]), reply_markup=with_rating(None, rating))
    elif kind in ("edit_error", "cancelled"):
        await message.answer(messages.answer(reply["text"]))
    else:
        await message.answer(messages.nothing(), reply_markup=with_rating(None, rating))


def proposal_markup(reply: dict):
    return proposal_keyboard(reply["draft_id"], len(reply["events"]), is_change(reply), messages.target_title(reply))


def is_change(reply: dict) -> bool:
    return any(event.get("event_id") for event in reply["events"])


def result_keyboard(reply: dict, app_url: str | None):
    """"Отменить" removes new tasks only; a confirmed change of an existing task is not undone this way."""
    if reply.get("kind") == "updated":
        return updated_keyboard(reply["events"], app_url)
    return created_keyboard(reply.get("event_ids") or [], reply["events"], app_url)


async def ask(message: Message, text: str) -> None:
    try:
        async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
            reply = await backend.chat(message.chat.id, text)
    except BackendError as error:
        if error.status == 503 and "Assistant" in error.detail:
            await message.answer(messages.assistant_unavailable())
        elif error.status == 429:
            # The backend says which limit was reached and when the assistant answers again
            await message.answer(error.detail)
        else:
            await report(message, error)
        return
    await deliver(message, reply)


async def ensure_linked(message: Message) -> bool:
    try:
        await backend.profile(message.chat.id)
    except BackendError as error:
        await report(message, error)
        return False
    return True


@router.message(F.text & ~F.text.startswith("/"))
async def text_message(message: Message) -> None:
    await ask(message, message.text)


@router.message(Command("advice", "analysis"))
async def shared_command(message: Message) -> None:
    """Commands the backend understands the same way as the web chat."""
    await ask(message, "/advice" if message.text.startswith("/advice") else "проанализируй мою неделю")


@router.callback_query(F.data.startswith("adv:"))
async def discuss_advice(callback: CallbackQuery) -> None:
    """"Обсудить" under advice: the recommendation becomes the topic, like in the web chat."""
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    try:
        reply = await backend.topic(callback.message.chat.id, int(callback.data.split(":")[1]))
    except (ValueError, BackendError):
        await callback.answer("Совет устарел — запросите советы ещё раз", show_alert=True)
        return
    await callback.message.answer(messages.topic(reply), reply_markup=topic_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("qr:"))
async def quick_reply(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    try:
        text = TOPIC_REPLIES[int(callback.data.split(":")[1])]
    except (ValueError, IndexError):
        await callback.answer()
        return
    await callback.answer()
    await callback.message.answer(f"<i>{messages.esc(text)}</i>")
    await ask(callback.message, text)


@router.message(F.content_type.in_({ContentType.VOICE, ContentType.AUDIO, ContentType.VIDEO_NOTE}))
async def voice_message(message: Message, bot: Bot) -> None:
    if not await ensure_linked(message):
        return
    media = message.voice or message.audio or message.video_note
    if media.file_size and media.file_size > MAX_FILE_BYTES:
        await message.answer(messages.file_too_big())
        return
    path = ""
    try:
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp:
                path = temp.name
            await bot.download(media, destination=path)
            text = await asyncio.to_thread(recognize_audio, path)
    except (ValueError, RuntimeError) as error:
        await message.answer(messages.voice_failed(str(error)))
        return
    except Exception:
        logger.exception("Voice message from %s failed", message.chat.id)
        await message.answer(messages.processing_error())
        return
    finally:
        for leftover in (path, f"{path}.wav"):
            if leftover and os.path.exists(leftover):
                os.unlink(leftover)
    await message.answer(messages.heard(text))
    await ask(message, text)


@router.message(F.document)
async def document_message(message: Message, bot: Bot) -> None:
    document = message.document
    name = document.file_name or "документ"
    if not name.lower().endswith(DOCUMENT_TYPES):
        await message.answer(messages.unsupported_file())
        return
    if document.file_size and document.file_size > MAX_FILE_BYTES:
        await message.answer(messages.file_too_big())
        return
    if not await ensure_linked(message):
        return
    await message.answer(messages.reading_document(name))
    path = ""
    try:
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(name)[1].lower(), delete=False) as temp:
                path = temp.name
            await bot.download(document, destination=path)
            text = await asyncio.to_thread(extract_document, path)
    except Exception:
        logger.exception("Document from %s failed", message.chat.id)
        await message.answer(messages.processing_error())
        return
    finally:
        if path and os.path.exists(path):
            os.unlink(path)
    if not text.strip():
        await message.answer(messages.document_empty())
        return
    await ask(message, text)


@router.message(F.chat.type == ChatType.PRIVATE)
async def other_message(message: Message) -> None:
    if await ensure_linked(message):
        await message.answer(messages.unsupported_message())


@router.callback_query(F.data.startswith("rt:"))
async def rate(callback: CallbackQuery) -> None:
    """👍 / 👎 under an answer; pressing the chosen one again removes the rating."""
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    try:
        _, message_id, value = callback.data.split(":")
        await backend.rate(callback.message.chat.id, int(message_id), int(value))
    except (ValueError, BackendError):
        await callback.answer("Не получилось сохранить оценку", show_alert=True)
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=rated(callback.message.reply_markup, int(message_id), int(value)))
    except TelegramBadRequest:
        pass
    await callback.answer("Спасибо за оценку!" if int(value) else "Оценка снята")


@router.callback_query(F.data.startswith("undo:"))
async def undo(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Это сообщение устарело — отправьте команду ещё раз", show_alert=True)
        return
    try:
        ids = expand_ids(callback.data.split(":", 1)[1])
        deleted = await backend.undo(callback.message.chat.id, ids)
    except (ValueError, BackendError):
        await callback.answer(messages.backend_unavailable(), show_alert=True)
        return
    try:
        await callback.message.edit_text(f"<s>{callback.message.html_text}</s>\n\n{messages.undone(deleted)}", reply_markup=None)
    except TelegramBadRequest:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Отменено" if deleted else "Уже удалено")


@router.callback_query(F.data.startswith("rc:"))
async def cancel_reminder(callback: CallbackQuery) -> None:
    """"Отменить" under a reminder the assistant set."""
    if not isinstance(callback.message, Message):
        await callback.answer("Это сообщение устарело", show_alert=True)
        return
    try:
        reply = await backend.cancel_reminder(callback.message.chat.id, int(callback.data.split(":")[1]))
    except ValueError:
        await callback.answer(messages.backend_unavailable(), show_alert=True)
        return
    except BackendError as error:
        await callback.answer("Напоминание уже пришло или отменено" if error.status == 404 else messages.backend_unavailable(), show_alert=True)
        return
    try:
        await callback.message.edit_text(f"<s>{callback.message.html_text}</s>\n\n{messages.reminder_cancelled(reply['text'])}", reply_markup=None)
    except TelegramBadRequest:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Отменено")


async def _show_proposal(callback: CallbackQuery, reply: dict) -> None:
    if reply.get("kind") == "proposal":
        text, keyboard = messages.proposal(reply), proposal_markup(reply)
    else:
        text, keyboard = messages.proposal_closed(reply.get("text") or "Черновик закрыт"), None
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("dr:"))
async def draft_action(callback: CallbackQuery) -> None:
    """Buttons under a proposal: add, cancel, choose a task, edit a field or remove a task."""
    if not isinstance(callback.message, Message):
        await callback.answer("Это сообщение устарело — отправьте задачу ещё раз", show_alert=True)
        return
    chat_id = callback.message.chat.id
    parts = callback.data.split(":")
    try:
        draft_id, action = int(parts[1]), parts[2]
        if action == "ok":
            reply = await backend.draft_confirm(chat_id, draft_id)
            if reply.get("kind") == "deleted":
                await callback.message.edit_text(f"🗑 <b>{messages.esc(reply['text'])}</b>", reply_markup=None)
                await callback.answer("Удалено ✓")
                return
            keyboard = result_keyboard(reply, await site.app_url())
            try:
                await callback.message.edit_text(messages.created(reply), reply_markup=keyboard)
            except TelegramBadRequest:
                await callback.message.answer(messages.created(reply), reply_markup=keyboard)
            await callback.answer("Изменено ✓" if reply.get("kind") == "updated" else "Добавлено ✓")
        elif action == "no":
            await _show_proposal(callback, await backend.draft_cancel(chat_id, draft_id))
            await callback.answer("Отменено")
        elif action == "sel":
            index = int(parts[3])
            await callback.message.edit_reply_markup(reply_markup=proposal_item_keyboard(draft_id, index))
            await callback.answer(f"Задача {index + 1}: что изменить?")
        elif action == "back":
            await _show_proposal(callback, await backend.draft(chat_id, draft_id))
            await callback.answer()
        elif action == "e":
            data = await backend.draft_edit(chat_id, draft_id, int(parts[3]), parts[4])
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except TelegramBadRequest:
                pass
            await callback.message.answer(messages.edit_prompt(data), reply_markup=ForceReply(input_field_placeholder=data["prompt"][:64]))
            await callback.answer()
        elif action == "to":
            reply = await backend.draft(chat_id, draft_id)
            if len(parts) > 3:
                chosen = reply.get("calendars") or []
                slug = parts[3]
                reply = await backend.draft_calendars(chat_id, draft_id, [item for item in chosen if item != slug] if slug in chosen else [*chosen, slug])
            if reply.get("kind") != "proposal":
                await _show_proposal(callback, reply)
                await callback.answer()
                return
            # The checkboxes stay open for more presses; "Готово" returns to the proposal buttons
            try:
                await callback.message.edit_text(messages.proposal(reply), reply_markup=targets_keyboard(draft_id, reply.get("targets") or [], reply.get("calendars") or []))
            except TelegramBadRequest:
                pass
            await callback.answer("Запомню этот выбор" if len(parts) > 3 else "Куда ещё добавить задачи?")
        elif action == "rm":
            await _show_proposal(callback, await backend.draft_remove(chat_id, draft_id, int(parts[3])))
            await callback.answer("Убрано")
        else:
            await callback.answer()
    except (IndexError, ValueError):
        await callback.answer()
    except BackendError as error:
        if error.status == 410:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except TelegramBadRequest:
                pass
            await callback.answer("Этот черновик уже обработан", show_alert=True)
        elif error.status == 422:
            await callback.answer("Этот календарь больше не подключён", show_alert=True)
        else:
            await callback.answer("Telegram не подключён к Dayla" if error.not_linked else messages.backend_unavailable(), show_alert=True)
