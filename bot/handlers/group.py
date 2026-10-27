"""Deyla in a group chat (a work chat, a family chat).

Telegram gives a bot in a group only the messages that mention it or answer it, so nothing else is read. Mentioned
— «@dayla_bot запиши: отчёт к пятнице», or as an answer to a colleague's message with the request — Deyla plans it
for the person who asked, in their own calendar. The draft and its buttons go to that person's private chat, and
the group gets one short line: the plan of one member is not shown to everyone.
"""

import logging
import re

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import Message

from bot.handlers.chat import deliver
from bot.services.backend import BackendError, backend
from bot.templates import messages

logger = logging.getLogger(__name__)

router = Router(name="group")
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


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


@router.message(F.text | F.caption)
async def group_message(message: Message, bot: Bot) -> None:
    if not message.from_user or message.from_user.is_bot:
        return
    me = await bot.me()
    text = message.text or message.caption or ""
    replied_to_bot = bool(message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id == me.id)
    if not replied_to_bot and f"@{me.username}".lower() not in text.lower():
        return
    request = request_text(message, me.username, replied_to_bot)
    if not request:
        await message.reply(messages.group_help(me.username))
        return
    # In Telegram a person's private chat with the bot has the person's id: that is the linked Deyla account
    person = message.from_user.id
    try:
        reply = await backend.chat(person, request)
    except BackendError as error:
        if error.status == 404:
            await message.reply(messages.group_not_linked(me.username))
        elif error.status == 429:
            await message.reply(error.detail)
        else:
            logger.warning("Group request of %s failed: %s", person, error.status)
            await message.reply(messages.processing_error())
        return
    try:
        await deliver(PrivateChat(bot, person), reply)
    except TelegramForbiddenError:
        # The person has not started the bot in private, or blocked it
        await message.reply(messages.group_not_linked(me.username))
        return
    await message.reply(messages.group_sent())
