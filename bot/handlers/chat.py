import asyncio
import logging
import os
import tempfile

from aiogram import Bot, F, Router
from aiogram.enums import ChatType, ContentType
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message
from aiogram.utils.chat_action import ChatActionSender

from bot.handlers.account import report
from bot.keyboards import agenda_keyboard, created_keyboard, expand_ids
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
    if kind == "created":
        await message.answer(messages.created(reply), reply_markup=created_keyboard(reply.get("event_ids") or [], reply["events"], app_url))
    elif kind == "agenda":
        await message.answer(messages.agenda(reply), reply_markup=agenda_keyboard(reply.get("scope"), app_url))
    elif kind == "answer":
        await message.answer(messages.answer(reply["text"]))
    else:
        await message.answer(messages.nothing())


async def ask(message: Message, text: str) -> None:
    try:
        async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
            reply = await backend.chat(message.chat.id, text)
    except BackendError as error:
        if error.status == 503 and "Assistant" in error.detail:
            await message.answer(messages.assistant_unavailable())
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
