from unittest.mock import AsyncMock, MagicMock

from aiogram.types import CallbackQuery, Message

from bot import keyboards
from bot.handlers import friends, notifications
from bot.services.backend import BackendError
from bot.templates import messages
from tests.test_ui import assert_telegram_html

REQUEST = {
    "kind": "friend_task",
    "task_id": 7,
    "actions": ["accept", "reject", "block"],
    "text": "📨 **Маша <3** просит вас сделать задачу\n**Купить хлеб**\n🕒 завтра, 18:00–19:00\n_Ждёт ответа_",
}


def buttons(markup) -> list[str]:
    return [button.callback_data for row in (markup.inline_keyboard if markup else []) for button in row]


def test_friend_cards_have_their_buttons():
    assert buttons(keyboards.friend_keyboard(REQUEST)) == ["ft:7:a", "ft:7:r", "ft:7:b"]
    assert buttons(keyboards.friend_keyboard({**REQUEST, "actions": ["cancel", "check_off"]})) == ["ft:7:c", "ft:7:off"]
    assert keyboards.friend_keyboard({**REQUEST, "actions": []}) is None
    invite = {"kind": "friend_invite", "friend_id": 3, "actions": ["accept_friend", "decline_friend"], "text": "x"}
    assert buttons(keyboards.friend_keyboard(invite)) == ["fi:3:a", "fi:3:d"]
    text = messages.friend_card(REQUEST)
    assert_telegram_html(text)
    assert "<b>Купить хлеб</b>" in text and "&lt;3" in text
    # A notification's buttons come from the card in its payload
    item = {"id": 1, "kind": "friend_start", "payload": {"card": {**REQUEST, "actions": ["start"]}}}
    assert buttons(notifications.keyboard_for(item)) == ["ft:7:s"]


def callback(data: str) -> CallbackQuery:
    message = MagicMock(spec=Message)
    message.chat = MagicMock(id=42)
    message.edit_text = AsyncMock()
    message.edit_reply_markup = AsyncMock()
    query = MagicMock(spec=CallbackQuery)
    query.data = data
    query.message = message
    query.answer = AsyncMock()
    return query


async def test_a_button_redraws_the_card(monkeypatch):
    answered = {**REQUEST, "actions": [], "text": "**Купить хлеб**\n_Вы приняли — задача в календаре_"}
    call = AsyncMock(return_value=answered)
    monkeypatch.setattr(friends.backend, "friend_task", call)
    query = callback("ft:7:a")
    await friends.friend_task(query)
    call.assert_awaited_once_with(42, 7, "accept")
    text = query.message.edit_text.await_args.args[0]
    assert "<i>Вы приняли" in text and query.message.edit_text.await_args.kwargs["reply_markup"] is None


async def test_an_answered_task_says_so_and_loses_its_buttons(monkeypatch):
    monkeypatch.setattr(friends.backend, "friend_task", AsyncMock(side_effect=BackendError(409, "Задача уже принята")))
    query = callback("ft:7:r")
    await friends.friend_task(query)
    query.answer.assert_awaited_once_with("Задача уже принята", show_alert=True)
    query.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)


async def test_team_task_buttons_go_to_the_team(monkeypatch):
    card = {"kind": "team_task", "task_id": 5, "actions": ["accept", "reject"], "text": "**Отчёт**"}
    assert buttons(keyboards.friend_keyboard(card)) == ["tt:5:a", "tt:5:r"]
    assert buttons(keyboards.friend_keyboard({**card, "actions": ["done"]})) == ["tt:5:d"]
    call = AsyncMock(return_value={**card, "actions": ["done"]})
    monkeypatch.setattr(friends.backend, "team_task", call)
    await friends.friend_task(callback("tt:5:a"))
    call.assert_awaited_once_with(42, 5, "accept")
