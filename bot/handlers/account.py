import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bot.keyboards import MENU_HELP, MENU_REMINDERS, link_keyboard, main_menu, settings_keyboard
from bot.services import site
from bot.services.backend import BackendError, backend
from bot.templates import messages

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)
logger = logging.getLogger(__name__)


async def send_welcome(message: Message) -> None:
    keyboard = link_keyboard(await site.app_url())
    await message.answer(messages.welcome_unlinked(keyboard is not None), reply_markup=keyboard or ReplyKeyboardRemove())


async def report(message: Message, error: BackendError) -> None:
    if error.not_linked:
        await send_welcome(message)
    else:
        await message.answer(messages.backend_unavailable())


@router.message(CommandStart(deep_link=True))
async def start_with_code(message: Message, command: CommandObject) -> None:
    try:
        profile = await backend.link(command.args or "", message.chat.id, message.from_user.username)
    except BackendError as error:
        await message.answer(messages.link_failed() if error.status in (404, 422) else messages.backend_unavailable())
        return
    await message.answer(messages.linked(profile), reply_markup=main_menu)


@router.message(CommandStart())
async def start(message: Message) -> None:
    try:
        profile = await backend.profile(message.chat.id)
    except BackendError as error:
        await report(message, error)
        return
    await message.answer(messages.welcome_back(profile), reply_markup=main_menu)


@router.message(Command("help"))
@router.message(F.text == MENU_HELP)
async def help_command(message: Message) -> None:
    await message.answer(messages.help_text())


@router.message(Command("unlink"))
async def unlink(message: Message) -> None:
    try:
        await backend.unlink(message.chat.id)
    except BackendError as error:
        await report(message, error)
        return
    await message.answer(messages.account_unlinked(), reply_markup=ReplyKeyboardRemove())


async def render_settings(chat_id: int) -> tuple[str, object]:
    data = await backend.reminder_settings(chat_id)
    return messages.reminder_settings(data["email"], data["settings"]), settings_keyboard(data["settings"], await site.app_url())


@router.message(Command("reminders"))
@router.message(F.text == MENU_REMINDERS)
async def reminders(message: Message) -> None:
    try:
        text, keyboard = await render_settings(message.chat.id)
    except BackendError as error:
        await report(message, error)
        return
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("rs:"))
async def settings_button(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Это сообщение устарело — отправьте команду ещё раз", show_alert=True)
        return
    chat_id = callback.message.chat.id
    try:
        values = (await backend.reminder_settings(chat_id))["settings"]
        action = callback.data.split(":")
        if action[1] == "enabled":
            update = {"enabled": not values["enabled"]}
        elif action[1] == "digest":
            update = {"daily_digest_enabled": not values["daily_digest_enabled"]}
        elif action[1] == "evening":
            update = {"evening_enabled": not values.get("evening_enabled")}
        elif action[1] == "deadline":
            update = {"deadline_enabled": not values.get("deadline_enabled")}
        elif action[1] == "lead" and len(action) == 3 and action[2].isdigit():
            update = {"lead_times": sorted(set(values["lead_times"]) ^ {int(action[2])})}
        else:
            await callback.answer()
            return
        await backend.update_reminder_settings(chat_id, update)
        text, keyboard = await render_settings(chat_id)
    except BackendError as error:
        await callback.answer(messages.backend_unavailable() if not error.not_linked else "Telegram не подключён к Dayla", show_alert=True)
        return
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        pass
    await callback.answer("Сохранено ✓")
