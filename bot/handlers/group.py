"""Group mentions use recent received text; answers and confirmations stay private."""

import logging
import re
from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramNetworkError
from aiogram.types import ChatMemberUpdated, Message

from bot.handlers.chat import deliver
from bot.services.backend import BackendError, backend
from bot.services.group_context import recent, MAX_PHOTOS, MAX_PHOTO_BYTES
from bot.i18n import using
from bot.templates import messages

logger = logging.getLogger(__name__)

router = Router(name="group")
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


CHAT_SCAN = re.compile(
    r"\bscan\b|сканир|(?:проверь|прочитай|проанализируй|найди).{0,40}(?:чат|переписк|сообщени)"
    r"|(?:из|по)\s+(?:последн\w*\s+)?(?:чат|переписк|сообщени)",
    re.I,
)


class PrivateChat:
    """Stands in for a Message in deliver(): every answer goes to the person's private chat with the bot."""

    def __init__(self, bot: Bot, chat_id: int):
        self.bot = bot
        self.chat_id = chat_id

    async def answer(self, text: str, **kwargs):
        return await self.bot.send_message(self.chat_id, text, **kwargs)


def request_text(message: Message, username: str, replied_to_bot: bool) -> str:
    """The request without the mention; for an answer to someone else's message, that message too."""
    text = message.text or message.caption or ""
    text = re.sub(rf"@{re.escape(username)}\b", " ", text, flags=re.I).strip(" ,:—-\n")
    quoted = message.reply_to_message
    if quoted and not replied_to_bot and (quoted.text or quoted.caption):
        author = quoted.from_user.full_name if quoted.from_user else None
        text = messages.group_quote(text, message.chat.title, author, quoted.text or quoted.caption)
    return text.strip()


@router.message(F.text | F.caption | F.photo)
async def group_message(message: Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.is_bot or message.sender_chat:
        return
    me = await bot.me()
    text = message.text or message.caption or ""
    replied_to_bot = bool(message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id == me.id)
    mention = re.compile(rf"(?<![\w@])@{re.escape(me.username)}\b", re.I)
    command = re.match(rf"^\.?/(?P<command>dayla|scan)@{re.escape(me.username)}\b", text, re.I)
    if not replied_to_bot and not mention.search(text) and not command:
        recent.remember(message)
        return
    request = mention.sub(" ", text[command.end():] if command else text)
    request = request.strip(" ,:—-\n")
    if not request and ((message.reply_to_message and not replied_to_bot) or getattr(message, "photo", None)):
        request = messages.short("plan_this")
    if not request and command and command.group("command").lower() == "scan":
        request = "Scan the recent chat, combining related messages and photos, and prepare calendar drafts for the appointments discussed."
    if not request:
        await message.reply(messages.group_help(me.username))
        return
    # In Telegram a person's private chat with the bot has the person's id: that is the linked Deyla account
    person = message.from_user.id
    try:
        profile = await backend.profile(person)
    except BackendError as error:
        if error.status == 404:
            await message.reply(messages.group_not_linked(me.username))
        elif error.status == 429:
            await message.reply(error.detail)
        else:
            logger.warning("Group request of %s failed: %s", person, error.status)
            await message.reply(messages.processing_error())
        return
    with using(profile.get("language")):
        try:
            context, photos = recent.snapshot(message)
            scanning = bool(command and command.group("command").lower() == "scan") or bool(CHAT_SCAN.search(request))
            if scanning and context == "[]":
                # A model cannot distinguish an empty buffer from missing Telegram permissions,
                # and must not invent meetings or offer to fetch history the Bot API cannot read.
                await bot.send_message(person, messages.group_no_context(me.username))
                await message.reply(messages.group_sent())
                return
            # Check private delivery before the assistant can perform any requested action.
            if len(photos) > MAX_PHOTOS or sum(photo.get("size") or 0 for photo in photos) > MAX_PHOTO_BYTES:
                await bot.send_message(person, messages.group_photos_too_large())
                await message.reply(messages.group_sent())
                return
            await bot.send_message(person, messages.group_processing())
        except TelegramForbiddenError:
            await message.reply(messages.group_not_linked(me.username))
            return
        try:
            if photos:
                files = []
                total = 0
                for photo in photos:
                    with BytesIO() as buffer:
                        await bot.download(photo["file_id"], destination=buffer)
                        data = buffer.getvalue()
                    total += len(data)
                    if total > MAX_PHOTO_BYTES:
                        await bot.send_message(person, messages.group_photos_too_large())
                        await message.reply(messages.group_sent())
                        return
                    files.append((photo["filename"], data))
                reply = await backend.group_chat_photos(person, request, context, files)
            else:
                reply = await backend.group_chat(person, request, context)
            await deliver(PrivateChat(bot, person), reply)
        except BackendError as error:
            if error.status in {413, 422, 429}:
                await bot.send_message(person, messages.answer(error.detail))
                await message.reply(messages.group_sent())
                return
            await message.reply(messages.group_not_linked(me.username) if error.status == 404 else messages.processing_error())
            return
        except TelegramForbiddenError:
            await message.reply(messages.group_not_linked(me.username))
            return
        except (TelegramBadRequest, TelegramNetworkError, TimeoutError):
            await bot.send_message(person, messages.group_photo_failed())
            await message.reply(messages.group_sent())
            return
        await message.reply(messages.group_sent())


@router.edited_message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def group_edit(message: Message) -> None:
    recent.remember(message)


@router.my_chat_member()
async def membership_changed(event: ChatMemberUpdated) -> None:
    if event.new_chat_member.status in {"left", "kicked"}:
        recent.forget(event.chat.id)
