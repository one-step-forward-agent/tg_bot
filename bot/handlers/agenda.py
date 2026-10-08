from datetime import datetime

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, ForceReply, Message

from bot.handlers.account import report
from bot.keyboards import (
    MENU_DONE,
    MENU_STATS,
    MENU_TODAY,
    MENU_TOMORROW,
    MENU_WEEK,
    SCOPES,
    agenda_keyboard,
    done_keyboard,
    move_days_keyboard,
    move_list_keyboard,
    move_options_keyboard,
    moved_keyboard,
)
from bot.services import site
from bot.services.backend import BackendError, backend
from bot.templates import messages

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)

MENU_SCOPES = {MENU_TODAY: "today", MENU_TOMORROW: "tomorrow", MENU_WEEK: "week"}
# Notifications keep their text: buttons on them answer with a new message
NOTIFICATION_PREFIXES = ("☀️", "🕐", "🔔", "🌙", "⏳", "💡")


async def render(chat_id: int, scope: str) -> tuple[str, object]:
    reply = await backend.agenda(chat_id, scope)
    return messages.agenda(reply), agenda_keyboard(scope, await site.app_url())


async def show(message: Message, scope: str) -> None:
    try:
        text, keyboard = await render(message.chat.id, scope)
    except BackendError as error:
        await report(message, error)
        return
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("today"))
async def today(message: Message) -> None:
    await show(message, "today")


@router.message(Command("tomorrow"))
async def tomorrow(message: Message) -> None:
    await show(message, "tomorrow")


@router.message(Command("week"))
async def week(message: Message) -> None:
    await show(message, "week")


@router.message(F.text.in_(MENU_SCOPES))
async def menu(message: Message) -> None:
    await show(message, MENU_SCOPES[message.text])


async def render_done(chat_id: int, scope: str) -> tuple[str, object]:
    reply = await backend.agenda(chat_id, scope)
    return messages.done_list(reply), done_keyboard(reply, scope)


async def replace_or_answer(callback: CallbackQuery, text: str, keyboard) -> None:
    if callback.message.text and callback.message.text.startswith(NOTIFICATION_PREFIXES):
        await callback.message.answer(text, reply_markup=keyboard)
        return
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        pass


@router.message(Command("done"))
@router.message(F.text == MENU_DONE)
async def done(message: Message) -> None:
    try:
        text, keyboard = await render_done(message.chat.id, "today")
    except BackendError as error:
        await report(message, error)
        return
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("stats"))
@router.message(F.text == MENU_STATS)
async def stats(message: Message) -> None:
    try:
        data = await backend.stats(message.chat.id)
    except BackendError as error:
        await report(message, error)
        return
    await message.answer(messages.stats(data))


@router.callback_query(F.data.startswith("dn:"))
async def done_list(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Это сообщение устарело — отправьте /done", show_alert=True)
        return
    scope = callback.data.split(":", 1)[1]
    if scope not in SCOPES:
        await callback.answer()
        return
    try:
        text, keyboard = await render_done(callback.message.chat.id, scope)
    except BackendError as error:
        await callback.answer("Telegram не подключён к Dayla" if error.not_linked else messages.backend_unavailable(), show_alert=True)
        return
    await replace_or_answer(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("dt:"))
async def toggle_done(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Это сообщение устарело — отправьте /done", show_alert=True)
        return
    try:
        _, event_id, scope, value = callback.data.split(":")
        await backend.complete(callback.message.chat.id, int(event_id), value == "1")
        text, keyboard = await render_done(callback.message.chat.id, scope if scope in SCOPES else "today")
    except ValueError:
        await callback.answer()
        return
    except BackendError as error:
        await callback.answer("Задача не найдена — возможно, её удалили" if error.status == 404 else messages.backend_unavailable(), show_alert=True)
        return
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        pass
    await callback.answer("Выполнено ✓" if value == "1" else "Снята отметка")


@router.callback_query(F.data.startswith("ag:"))
async def switch(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Это сообщение устарело — отправьте команду ещё раз", show_alert=True)
        return
    scope = callback.data.split(":", 1)[1]
    if scope not in SCOPES:
        await callback.answer()
        return
    try:
        text, keyboard = await render(callback.message.chat.id, scope)
    except BackendError as error:
        await callback.answer("Telegram не подключён к Dayla" if error.not_linked else messages.backend_unavailable(), show_alert=True)
        return
    await replace_or_answer(callback, text, keyboard)
    await callback.answer()


# ---------- "↪️ Перенести": choose a task, then the day ----------

GONE = "Задача не найдена — возможно, её удалили"


async def _edit(callback: CallbackQuery, text: str, keyboard) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        pass


def _failed(error: BackendError) -> str:
    if error.not_linked:
        return "Telegram не подключён к Dayla"
    return GONE if error.status == 410 else messages.backend_unavailable()


@router.callback_query(F.data.startswith("mv:"))
async def move_list(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Это сообщение устарело — откройте план ещё раз", show_alert=True)
        return
    scope = callback.data.split(":", 1)[1]
    if scope not in SCOPES:
        await callback.answer()
        return
    try:
        reply = await backend.agenda(callback.message.chat.id, scope)
    except BackendError as error:
        await callback.answer(_failed(error), show_alert=True)
        return
    await replace_or_answer(callback, messages.move_list(reply), move_list_keyboard(reply, scope))
    await callback.answer()


@router.callback_query(F.data.startswith("mp:") | F.data.startswith("mo:"))
async def move_choose(callback: CallbackQuery) -> None:
    """"mp" offers today, tomorrow, the day after tomorrow; "mo" — two weeks of days and a typed date."""
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    try:
        kind, event_id, scope = callback.data.split(":")
        event = await backend.event(callback.message.chat.id, int(event_id))
    except ValueError:
        await callback.answer()
        return
    except BackendError as error:
        await callback.answer(GONE if error.status == 404 else _failed(error), show_alert=True)
        return
    scope = scope if scope in SCOPES else "today"
    if kind == "mp":
        await _edit(callback, messages.move_ask(event), move_options_keyboard(event, scope))
    else:
        await _edit(callback, messages.move_days(event), move_days_keyboard(event, scope))
    await callback.answer()


@router.callback_query(F.data.startswith("mt:"))
async def move_to(callback: CallbackQuery) -> None:
    """Move to the chosen day at once — the same button under the result moves it back."""
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    try:
        _, event_id, day = callback.data.split(":")
        target = datetime.strptime(day, "%Y%m%d").date()
        reply = await backend.move(callback.message.chat.id, int(event_id), target.isoformat())
    except ValueError:
        await callback.answer()
        return
    except BackendError as error:
        await callback.answer(_failed(error), show_alert=True)
        return
    if reply.get("kind") != "updated":
        await callback.answer(reply.get("text") or "Готово", show_alert=True)
        return
    await replace_or_answer(callback, messages.moved(reply), moved_keyboard(reply))
    await callback.answer("Перенесла ✓")


@router.callback_query(F.data.startswith("mw:"))
async def move_typed(callback: CallbackQuery) -> None:
    """"✍️ Написать дату": the next message is the new day; Dayla shows the change for confirmation."""
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    try:
        data = await backend.move_date(callback.message.chat.id, int(callback.data.split(":")[1]))
    except (ValueError, IndexError):
        await callback.answer()
        return
    except BackendError as error:
        await callback.answer(_failed(error), show_alert=True)
        return
    await callback.message.answer(messages.edit_prompt(data), reply_markup=ForceReply(input_field_placeholder=data["prompt"][:64]))
    await callback.answer()
