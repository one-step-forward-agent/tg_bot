"""Buttons under a friend's task or invitation (backend app.services.friends): the card is redrawn as it is now."""

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from bot.keyboards import FRIEND_CODES, friend_keyboard
from bot.services.backend import BackendError, backend
from bot.templates import messages

router = Router()


async def redraw(callback: CallbackQuery, card: dict) -> None:
    try:
        await callback.message.edit_text(messages.friend_card(card), reply_markup=friend_keyboard(card))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("ft:") | F.data.startswith("tt:"))
async def friend_task(callback: CallbackQuery) -> None:
    """A friend's task ("ft:") or a team's ("tt:")."""
    if not isinstance(callback.message, Message):
        await callback.answer(messages.outdated(), show_alert=True)
        return
    try:
        kind, task_id, code = callback.data.split(":")
        call = backend.team_task if kind == "tt" else backend.friend_task
        card = await call(callback.message.chat.id, int(task_id), FRIEND_CODES[code])
    except (ValueError, KeyError):
        await callback.answer()
        return
    except BackendError as error:
        # Already answered, cancelled, or the time has passed: the backend says so in words
        await callback.answer(error.detail if error.status in (404, 409) else messages.backend_unavailable(), show_alert=True)
        if error.status in (404, 409):
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except TelegramBadRequest:
                pass
        return
    await redraw(callback, card)
    await callback.answer(messages.short("saved"))


@router.callback_query(F.data.startswith("fi:"))
async def friend_invite(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer(messages.outdated(), show_alert=True)
        return
    try:
        _, friend_id, code = callback.data.split(":")
        card = await backend.friend_invite(callback.message.chat.id, int(friend_id), "accept" if code == "a" else "decline")
    except ValueError:
        await callback.answer()
        return
    except BackendError as error:
        await callback.answer(error.detail if error.status == 404 else messages.backend_unavailable(), show_alert=True)
        return
    await redraw(callback, card)
    await callback.answer(messages.short("saved"))
