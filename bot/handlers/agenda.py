from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.handlers.account import report
from bot.keyboards import MENU_TODAY, MENU_TOMORROW, MENU_WEEK, SCOPES, agenda_keyboard
from bot.services import site
from bot.services.backend import BackendError, backend
from bot.templates import messages

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)

MENU_SCOPES = {MENU_TODAY: "today", MENU_TOMORROW: "tomorrow", MENU_WEEK: "week"}


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
    if callback.message.text and callback.message.text.startswith("☀️"):
        await callback.message.answer(text, reply_markup=keyboard)
    else:
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest:
            pass
    await callback.answer()
