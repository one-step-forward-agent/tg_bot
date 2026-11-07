from unittest.mock import AsyncMock, MagicMock
from datetime import date

import pytest

from aiogram.types import CallbackQuery, Message

from bot import keyboards
from bot.handlers import friends, notifications
from bot.services.backend import BackendError
from bot.templates import messages
from tests.test_ui import assert_telegram_html

REQUEST = {
    "kind": "friend_task",
    "task_id": 7,
    "actions": ["accept", "reject"],
    "text": "📨 **Маша <3** просит вас сделать задачу\n**Купить хлеб**\n🕒 завтра, 18:00–19:00\n_Ждёт ответа_",
}


def buttons(markup) -> list[str]:
    return [button.callback_data for row in (markup.inline_keyboard if markup else []) for button in row]


def test_friend_cards_have_their_buttons():
    assert buttons(keyboards.friend_keyboard(REQUEST)) == ["ft:7:a", "ft:7:r"]
    # No «не присылать 10 минут» any more; its code still works under older messages
    assert "block" not in keyboards.FRIEND_ACTIONS and keyboards.FRIEND_CODES["b"] == "block"
    reminder = keyboards.friend_keyboard({**REQUEST, "reminder": True, "actions": ["cancel"]})
    assert buttons(reminder) == ["ft:7:c"] and "напоминание" in reminder.inline_keyboard[0][0].text
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
    monkeypatch.setattr(friends.site, "app_url", AsyncMock(return_value="https://deyla.tech"))
    query = callback("tt:5:a")
    await friends.friend_task(query)
    call.assert_not_awaited()
    markup = query.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    assert buttons(markup) == ["tt:5:a0", "tt:5:a1", "tt:5:a2", "tt:5:cal", None, "tt:5:r"]
    await friends.friend_task(callback("tt:5:a1"))
    assert call.await_args.args[:3] == (42, 5, "accept")
    assert call.await_args.args[3] == {"day_offset": 1, "start_time": None}


def test_team_calendar_has_specific_days_and_month_navigation():
    markup = keyboards.team_calendar_keyboard(5, date(2026, 11, 1), date(2026, 11, 7))
    codes = buttons(markup)
    assert "tt:5:d20261107" in codes and "tt:5:d20261130" in codes
    assert "tt:5:d20261106" not in codes
    assert "tt:5:cal202612" in codes and "tt:5:cal202610" not in codes
    assert codes[-1] == "tt:5:a"
    assert all(len(code.encode()) <= 64 for code in codes)
    december = buttons(keyboards.team_calendar_keyboard(5, date(2026, 12, 1), date(2026, 11, 7)))
    assert "tt:5:cal202611" in december and "tt:5:cal202701" in december


async def test_opening_and_navigating_calendar_does_not_accept_task(monkeypatch):
    monkeypatch.setattr(friends.backend, "profile", AsyncMock(return_value={"timezone": "Pacific/Kiritimati", "today": "2026-11-07"}))
    accept = AsyncMock()
    monkeypatch.setattr(friends.backend, "team_task", accept)
    query = callback("tt:5:cal")
    await friends.friend_task(query)
    accept.assert_not_awaited()
    assert query.message.edit_reply_markup.await_args.kwargs["reply_markup"].inline_keyboard
    assert "tt:5:d20261107" in buttons(query.message.edit_reply_markup.await_args.kwargs["reply_markup"])
    query = callback("tt:5:cal203012")
    await friends.friend_task(query)
    codes = buttons(query.message.edit_reply_markup.await_args.kwargs["reply_markup"])
    assert "tt:5:d20301231" in codes and "tt:5:cal203101" in codes
    accept.assert_not_awaited()


async def test_selected_calendar_date_accepts_untimed_without_changing_deadline(monkeypatch):
    call = AsyncMock(return_value={"kind": "team_task", "task_id": 5, "actions": ["done"], "text": "Accepted"})
    monkeypatch.setattr(friends.backend, "team_task", call)
    query = callback("tt:5:d20301217")
    await friends.friend_task(query)
    call.assert_awaited_once_with(42, 5, "accept", {"day": "2030-12-17", "start_time": None})
    query.message.edit_text.assert_awaited_once()


@pytest.mark.parametrize("code", ["d20260230", "calinvalid", "noop"])
async def test_invalid_and_inert_calendar_callbacks_never_accept(monkeypatch, code):
    call = AsyncMock()
    monkeypatch.setattr(friends.backend, "team_task", call)
    monkeypatch.setattr(friends.backend, "profile", AsyncMock(return_value={"timezone": "UTC", "today": "2026-11-07"}))
    await friends.friend_task(callback(f"tt:5:{code}"))
    call.assert_not_awaited()


DRAFT = {
    "kind": "send_draft",
    "draft_id": 12,
    "type": "friend_reminder",
    "actions": ["send", "edit", "cancel"],
    "text": "🔔 Поставить напоминание другу **Олег**?\n**Позвонить врачу**\n🕒 завтра в 09:00\n_Пока не отправлено_",
}


def test_a_draft_has_send_cancel_and_a_link_to_change_it():
    markup = keyboards.send_draft_keyboard(DRAFT, "https://deyla.tech")
    assert buttons(markup) == ["sd:12:s", "sd:12:c", None]
    assert markup.inline_keyboard[1][0].url == "https://deyla.tech/app/assistant"
    assert buttons(keyboards.send_draft_keyboard(DRAFT)) == ["sd:12:s", "sd:12:c"]
    assert keyboards.send_draft_keyboard({**DRAFT, "actions": []}) is None
    assert_telegram_html(messages.friend_card(DRAFT))


def test_friend_change_drafts_name_the_confirmed_operation():
    for operation in ("edit", "cancel"):
        markup = keyboards.send_draft_keyboard({**DRAFT, "operation": operation, "actions": ["send", "cancel"]})
        assert buttons(markup) == ["sd:12:s", "sd:12:c"]
        assert "Подтвердить" in markup.inline_keyboard[0][0].text


async def test_sending_a_draft_turns_it_into_the_friends_card(monkeypatch):
    sent = {**REQUEST, "actions": ["cancel"], "reminder": True, "text": "🔔 Поставила напоминание. Получатель: **Олег**"}
    call = AsyncMock(return_value=sent)
    monkeypatch.setattr(friends.backend, "send_draft", call)
    query = callback("sd:12:s")
    await friends.send_draft(query)
    call.assert_awaited_once_with(42, 12, "send")
    keyboard = query.message.edit_text.await_args.kwargs["reply_markup"]
    assert buttons(keyboard) == ["ft:7:c"]


async def test_a_draft_that_cannot_be_sent_keeps_its_buttons(monkeypatch):
    monkeypatch.setattr(friends.backend, "send_draft", AsyncMock(return_value={"kind": "answer", "text": "Олег попросил пока не присылать задачи"}))
    query = callback("sd:12:s")
    await friends.send_draft(query)
    query.answer.assert_awaited_once_with("Олег попросил пока не присылать задачи", show_alert=True)
    query.message.edit_text.assert_not_awaited()
