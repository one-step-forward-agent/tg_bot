"""Buttons under a friend's task or invitation (backend app.services.friends): the card is redrawn as it is now."""

from datetime import date, datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from bot.keyboards import FRIEND_CODES, friend_keyboard, send_draft_keyboard, team_calendar_keyboard, team_schedule_keyboard, with_completion_report
from bot.i18n import tr
from bot.services import site
from bot.services.backend import BackendError, backend
from bot.templates import messages

router = Router()


async def redraw(callback: CallbackQuery, card: dict) -> None:
    keyboard = friend_keyboard(card)
    if card.get("status") == "done":
        keyboard = with_completion_report(keyboard, await site.app_url(), card.get("calendar_event_id"))
    try:
        await callback.message.edit_text(messages.friend_card(card), reply_markup=keyboard)
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
        if kind == "tt" and code == "noop":
            await callback.answer()
            return
        if kind == "tt" and code == "a":
            await callback.message.edit_reply_markup(reply_markup=team_schedule_keyboard(int(task_id), await site.app_url()))
            await callback.answer(tr("Выберите день выполнения", "Choose a work day"))
            return
        if kind == "tt" and code.startswith("cal"):
            profile = await backend.profile(callback.message.chat.id)
            today = date.fromisoformat(profile["today"])
            month = datetime.strptime(code[3:], "%Y%m").date() if code[3:] else today
            if month.replace(day=1) < today.replace(day=1):
                month = today
            await callback.message.edit_reply_markup(reply_markup=team_calendar_keyboard(int(task_id), month, today))
            await callback.answer(tr("Выберите день выполнения", "Choose a work day"))
            return
        if kind == "tt" and code in ("a0", "a1", "a2"):
            card = await backend.team_task(callback.message.chat.id, int(task_id), "accept", {"day_offset": int(code[1]), "start_time": None})
        elif kind == "tt" and code.startswith("d") and code != "d":
            day = datetime.strptime(code[1:], "%Y%m%d").date()
            card = await backend.team_task(callback.message.chat.id, int(task_id), "accept", {"day": day.isoformat(), "start_time": None})
        else:
            call = backend.team_task if kind == "tt" else backend.friend_task
            card = await call(callback.message.chat.id, int(task_id), FRIEND_CODES[code])
    except (ValueError, KeyError, OverflowError):
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


@router.callback_query(F.data.startswith("sd:"))
async def send_draft(callback: CallbackQuery) -> None:
    """«Отправить» / «Отмена» under a draft: sent, the card becomes the friend's or team's task card."""
    if not isinstance(callback.message, Message):
        await callback.answer(messages.outdated(), show_alert=True)
        return
    try:
        _, draft_id, code = callback.data.split(":")
        card = await backend.send_draft(callback.message.chat.id, int(draft_id), {"s": "send", "c": "cancel"}[code])
    except (ValueError, KeyError):
        await callback.answer()
        return
    except BackendError as error:
        await callback.answer(error.detail if error.status in (404, 409) else messages.backend_unavailable(), show_alert=True)
        if error.status in (404, 409):
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except TelegramBadRequest:
                pass
        return
    if card.get("kind") == "answer":
        # Not sent (the friend paused tasks …): said in words, the draft keeps its buttons
        await callback.answer(card.get("text") or "", show_alert=True)
        return
    keyboard = send_draft_keyboard(card) if card.get("kind") == "send_draft" else friend_keyboard(card)
    try:
        await callback.message.edit_text(messages.friend_card(card), reply_markup=keyboard)
    except TelegramBadRequest:
        pass
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
