from datetime import datetime, timedelta
from html.parser import HTMLParser
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from bot import keyboards
from bot.handlers import agenda, chat, notifications
from bot.services.backend import BackendError
from bot.templates import messages

NOW = datetime.now().astimezone()
TOMORROW = (NOW + timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
ALLOWED_TAGS = {"b", "i", "s", "code", "u", "a"}


class TagChecker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []

    def handle_starttag(self, tag, attrs):
        assert tag in ALLOWED_TAGS, tag
        self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack.pop() == tag, tag


def assert_telegram_html(text: str) -> None:
    checker = TagChecker()
    checker.feed(text)
    assert not checker.stack
    assert len(text) <= 4096


def event(title="Встреча <с> Анной", all_day=False, **extra):
    start = TOMORROW if not all_day else TOMORROW.replace(hour=0)
    return {
        "id": 7, "index": 0, "title": title, "start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(),
        "date": start.date().isoformat(), "time": None if all_day else "15:00", "end_time": None, "all_day": all_day,
        "recurrence": None, "completed": False, **extra,
    }


def proposal_reply(count=1, **extra):
    events = [event(f"Задача {index}", index_extra=index) if count > 1 else event() for index in range(count)]
    return {"kind": "proposal", "draft_id": 42, "events": events, "answer": None, "note": None, **extra}


def test_proposal_texts():
    single = messages.proposal(proposal_reply())
    assert_telegram_html(single)
    assert "Встреча &lt;с&gt; Анной" in single and "Добавить" in single
    untimed = messages.proposal({"draft_id": 1, "events": [event(all_day=True, recurrence="по пятницам")], "note": "Изменено ✓"})
    assert "без времени" in untimed and "По пятницам" in untimed and "Изменено" in untimed
    assert_telegram_html(untimed)
    many = messages.proposal(proposal_reply(count=40))
    assert_telegram_html(many)
    assert "Проверьте 40 задач" in many


def test_agenda_marks_completed_and_untimed():
    reply = {"kind": "agenda", "scope": "today", "title": "Сегодня", "date": NOW.date().isoformat(),
             "days": [{"date": NOW.date().isoformat(), "label": "Сегодня", "events": [event(completed=True), event("Купить хлеб", all_day=True)]}]}
    text = messages.agenda(reply)
    assert_telegram_html(text)
    assert "✅ <s>" in text and "без времени" in text
    assert_telegram_html(messages.done_list(reply))


def test_stats_text():
    days = [{"date": (NOW.date() - timedelta(days=6 - offset)).isoformat(), "total": offset, "done": offset // 2, "percent": 50 if offset else 0} for offset in range(7)]
    text = messages.stats({"today": days[-1], "days": days, "total": 21, "done": 9, "percent": 43, "streak": 3})
    assert_telegram_html(text)
    assert "Серия: 3 дня" in text and "9 из 21" in text


def callback_data(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_callback_data_fits_telegram_limit():
    markups = [
        keyboards.proposal_keyboard(2**31, 1),
        keyboards.proposal_keyboard(2**31, 25),
        keyboards.proposal_item_keyboard(2**31, 39),
        keyboards.done_keyboard({"days": [{"events": [event(id=2**31, title="x" * 200)] * 40}]}, "tomorrow"),
        keyboards.checkin_keyboard(2**31, {"event_ids": [1], "target_label": "чт, 15 октября"}),
        keyboards.reminder_keyboard(2**31, None, 2**31),
    ]
    for markup in markups:
        for data in callback_data(markup):
            assert len(data.encode()) <= 64, data
    assert len(keyboards.proposal_keyboard(1, 25).inline_keyboard) == 1 + 4  # 20 numbered buttons, 5 per row
    assert callback_data(keyboards.checkin_keyboard(5, {"event_ids": []}))[0] == "ci:5:ok"


def fake_message(text="") -> MagicMock:
    message = MagicMock()
    message.__class__ = Message  # passes isinstance checks; spec= would hide pydantic fields
    message.chat.id = 100
    message.text = text
    message.html_text = text
    message.answer = AsyncMock()
    message.edit_text = AsyncMock()
    message.edit_reply_markup = AsyncMock()
    return message


def fake_callback(data: str, text="📝 Проверьте задачу") -> MagicMock:
    callback = MagicMock()
    callback.__class__ = CallbackQuery
    callback.data = data
    callback.message = fake_message(text)
    callback.answer = AsyncMock()
    return callback


@pytest.fixture
def backend(monkeypatch):
    fake = MagicMock()
    for module in (chat, agenda, notifications):
        monkeypatch.setattr(module, "backend", fake)
    monkeypatch.setattr(chat.site, "app_url", AsyncMock(return_value="https://dayla.example"))
    monkeypatch.setattr(agenda.site, "app_url", AsyncMock(return_value=None))
    return fake


@pytest.mark.parametrize("kind", ["proposal", "created", "agenda", "answer", "not_found", "edit_error", "cancelled", "nothing"])
async def test_deliver_every_kind(backend, kind):
    replies = {
        "proposal": proposal_reply(),
        "created": {"kind": "created", "events": [event()], "event_ids": [7]},
        "agenda": {"kind": "agenda", "title": "Найденные события", "days": []},
        "answer": {"kind": "answer", "text": "Привет"},
        "not_found": {"kind": "not_found", "text": "Задача не найдена"},
        "edit_error": {"kind": "edit_error", "text": "Не поняла дату"},
        "cancelled": {"kind": "cancelled", "text": "Хорошо"},
        "nothing": {"kind": "nothing"},
    }
    message = fake_message()
    await chat.deliver(message, replies[kind])
    text = message.answer.call_args.args[0]
    assert_telegram_html(text)
    if kind == "proposal":
        assert callback_data(message.answer.call_args.kwargs["reply_markup"])[0] == "dr:42:ok"
    if kind == "not_found":
        assert "Задача не найдена" in text


async def test_draft_confirm_edit_and_gone(backend):
    backend.draft_confirm = AsyncMock(return_value={"kind": "created", "events": [event()], "event_ids": [7, 8]})
    callback = fake_callback("dr:42:ok")
    await chat.draft_action(callback)
    backend.draft_confirm.assert_awaited_with(100, 42)
    assert "Добавила" in callback.message.edit_text.call_args.args[0]
    assert callback_data(callback.message.edit_text.call_args.kwargs["reply_markup"]) == ["undo:7-8"]

    backend.draft_edit = AsyncMock(return_value={"prompt": "Напишите новую дату", "title": "Встреча", "field": "date", "index": 0})
    callback = fake_callback("dr:42:e:0:date")
    await chat.draft_action(callback)
    backend.draft_edit.assert_awaited_with(100, 42, 0, "date")
    callback.message.edit_reply_markup.assert_awaited_with(reply_markup=None)
    assert "Напишите новую дату" in callback.message.answer.call_args.args[0]

    backend.draft_remove = AsyncMock(return_value={"kind": "cancelled", "text": "Черновик пуст"})
    callback = fake_callback("dr:42:rm:0")
    await chat.draft_action(callback)
    assert "Черновик пуст" in callback.message.edit_text.call_args.args[0]
    assert callback.message.edit_text.call_args.kwargs["reply_markup"] is None

    backend.draft_cancel = AsyncMock(side_effect=BackendError(410, "Draft is gone"))
    callback = fake_callback("dr:42:no")
    await chat.draft_action(callback)
    assert callback.answer.call_args.kwargs["show_alert"] is True

    callback = fake_callback("dr:42:sel:3")
    await chat.draft_action(callback)
    markup = callback.message.edit_reply_markup.call_args.kwargs["reply_markup"]
    assert "dr:42:e:3:title" in callback_data(markup)


async def test_toggle_done_and_checkin(backend):
    reply = {"title": "Сегодня", "days": [{"events": [event(completed=True)]}]}
    backend.complete = AsyncMock(return_value=event(completed=True))
    backend.agenda = AsyncMock(return_value=reply)
    callback = fake_callback("dt:7:today:1", text="✅ Отметьте выполненное")
    await agenda.toggle_done(callback)
    backend.complete.assert_awaited_with(100, 7, True)
    assert callback_data(callback.message.edit_text.call_args.kwargs["reply_markup"])[0] == "dt:7:today:0"

    # From a check-in notification the list comes as a new message, the notification stays
    callback = fake_callback("dn:today", text="🕐 Как успеваете?")
    await agenda.done_list(callback)
    callback.message.answer.assert_awaited()
    callback.message.edit_text.assert_not_awaited()

    backend.checkin = AsyncMock(return_value={"moved": 2, "target_label": "завтра"})
    callback = fake_callback("ci:9:move", text="🕐 Как успеваете?")
    await notifications.checkin_answer(callback)
    backend.checkin.assert_awaited_with(9, 100, "move")
    assert "Перенесла 2 задачи на завтра" in callback.message.edit_text.call_args.args[0]

    callback = fake_callback("rd:7", text="🔔 Через 15 мин")
    await notifications.reminder_done(callback)
    assert "Выполнено" in callback.message.edit_text.call_args.args[0]


def test_notification_keyboards():
    assert notifications.keyboard_for({"kind": "checkin", "id": 3, "payload": {"event_ids": [1], "target_label": "завтра"}}).inline_keyboard[0][0].text == "↪️ Перенести на завтра"
    reminder = notifications.keyboard_for({"kind": "reminder", "id": 3, "event_id": 5, "url": None})
    assert "rd:5" in callback_data(reminder)
