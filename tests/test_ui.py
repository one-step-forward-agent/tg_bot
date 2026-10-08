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


def test_evening_and_deadline_notifications():
    evening = notifications.keyboard_for({"kind": "evening", "id": 2**31, "payload": {"event_ids": [1, 2], "target_label": "завтра"}})
    data = callback_data(evening)
    assert data[0] == f"ci:{2**31}:move" and "ag:tomorrow" in data
    assert all(len(item.encode()) <= 64 for item in data)
    assert callback_data(notifications.keyboard_for({"kind": "evening", "id": 4, "payload": {"event_ids": []}}))[0] == "ag:tomorrow"
    deadline = notifications.keyboard_for({"kind": "deadline", "id": 3, "event_id": 5, "url": "https://dayla.example/app/events/5"})
    assert callback_data(deadline) == ["rd:5"]


def test_settings_keyboard_has_evening_and_deadlines():
    values = {"enabled": True, "lead_times": [15], "daily_digest_enabled": False, "evening_enabled": True, "deadline_enabled": False}
    data = callback_data(keyboards.settings_keyboard(values, None))
    assert "rs:evening" in data and "rs:deadline" in data
    text = messages.reminder_settings(
        "a@b.c",
        {**values, "daily_digest_time": "09:00:00", "evening_time": "21:00:00", "quiet_hours_enabled": False, "quiet_hours_start": "23:00", "quiet_hours_end": "08:00"},
    )
    assert "Итоги дня: в 21:00" in text and "Дедлайны: выключены" in text


def test_day_text_names_the_weekday():
    today = datetime(2026, 10, 7).date()
    assert messages.day_text(today, today) == "Сегодня, среда, 7 октября"
    assert messages.day_text(today + timedelta(days=1), today) == "Завтра, четверг, 8 октября"
    assert messages.day_text(today + timedelta(days=2), today) == "Пятница, 9 октября"


async def test_change_proposal_and_result(backend):
    change = event(event_id=7, before={"title": "Встреча <с> Анной", "date": NOW.date().isoformat(), "time": "10:00", "end_time": None, "end_date": None}, deadline=f"{TOMORROW.date().isoformat()}T18:00")
    reply = {"kind": "proposal", "draft_id": 42, "events": [change], "answer": None, "note": None}
    message = fake_message()
    await chat.deliver(message, reply)
    text = message.answer.call_args.args[0]
    assert_telegram_html(text)
    assert "Проверьте изменение" in text and "Было: сегодня 10:00" in text and "Дедлайн: завтра 18:00" in text
    assert message.answer.call_args.kwargs["reply_markup"].inline_keyboard[0][0].text == "✅ Сохранить"

    backend.draft_confirm = AsyncMock(return_value={"kind": "updated", "events": [event()], "event_ids": []})
    callback = fake_callback("dr:42:ok")
    await chat.draft_action(callback)
    assert "Изменила" in callback.message.edit_text.call_args.args[0]
    markup = callback.message.edit_text.call_args.kwargs["reply_markup"]
    assert markup is None or not any(data.startswith("undo:") for data in callback_data(markup))  # no undo for a change
    callback.answer.assert_awaited_with("Изменено ✓")


async def test_delete_proposal_and_confirmation(backend):
    reply = {"kind": "delete_proposal", "draft_id": 42, "count": 12, "title": "все задачи", "events": [event()] * 10, "message_id": 5}
    message = fake_message()
    await chat.deliver(message, reply)
    text = message.answer.call_args.args[0]
    assert_telegram_html(text)
    assert "Удалить 12 задач?" in text and "ещё 2" in text
    assert callback_data(message.answer.call_args.kwargs["reply_markup"]) == ["dr:42:ok", "dr:42:no"]

    backend.draft_confirm = AsyncMock(return_value={"kind": "deleted", "count": 12, "text": "Удалила 12 задач."})
    callback = fake_callback("dr:42:ok")
    await chat.draft_action(callback)
    assert "Удалила 12 задач" in callback.message.edit_text.call_args.args[0]
    callback.answer.assert_awaited_with("Удалено ✓")


async def test_answers_can_be_rated(backend):
    message = fake_message()
    await chat.deliver(message, {"kind": "answer", "text": "Привет", "message_id": 2**31})
    markup = message.answer.call_args.kwargs["reply_markup"]
    assert callback_data(markup) == [f"rt:{2**31}:1", f"rt:{2**31}:-1"]
    assert all(len(data.encode()) <= 64 for data in callback_data(markup))

    backend.rate = AsyncMock(return_value={"id": 9, "rating": -1})
    callback = fake_callback("rt:9:-1", text="💬 Привет")
    callback.message.reply_markup = keyboards.with_rating(None, 9)
    await chat.rate(callback)
    backend.rate.assert_awaited_with(100, 9, -1)
    texts = [button.text for row in callback.message.edit_reply_markup.call_args.kwargs["reply_markup"].inline_keyboard for button in row]
    assert texts == ["👍", "👎 ✓"]

    done = fake_message()
    await chat.deliver(done, {"kind": "completed", "text": "Отметила выполненными: 1 ✓", "events": [event()], "message_id": 3})
    assert_telegram_html(done.answer.call_args.args[0])


async def test_shared_commands_render_like_the_web_chat(backend):
    replies = {
        "stats": {"kind": "stats", "today": {"date": NOW.date().isoformat(), "total": 2, "done": 1, "percent": 50}, "days": [], "total": 2, "done": 1, "percent": 50, "streak": 2, "best_streak": 4, "message_id": 1},
        "help": {"kind": "help", "sections": [{"title": "Планировать", "examples": ["Созвон <завтра>"]}]},
        "advice": {"kind": "advice", "items": [{"kind": "warning", "title": "Скоро дедлайн", "text": "Отчёт"}, {"kind": "info", "title": "Окно", "text": "15:00"}], "message_id": 2},
        "reminders": {"kind": "reminders", "settings": {"enabled": True, "lead_times": [15], "daily_digest_enabled": False, "daily_digest_time": "09:00:00", "evening_enabled": True, "evening_time": "21:00:00", "deadline_enabled": True, "quiet_hours_enabled": False, "quiet_hours_start": "23:00:00", "quiet_hours_end": "08:00:00"}},
        "mark": {"kind": "agenda", "scope": "today", "title": "Сегодня", "mark": True, "days": [{"events": [event()]}]},
        "topic": {"kind": "topic", "title": "Скоро дедлайн", "text": "Отчёт до пятницы"},
    }
    for name, reply in replies.items():
        message = fake_message()
        await chat.deliver(message, reply)
        assert_telegram_html(message.answer.call_args.args[0])
        markup = message.answer.call_args.kwargs.get("reply_markup")
        data = callback_data(markup) if markup else []
        if name == "advice":
            assert data[:2] == ["adv:0", "adv:1"] and "rt:2:1" in data
        if name == "mark":
            assert data[0] == "dt:7:today:1"
        if name == "reminders":
            assert "rs:evening" in data
        if name == "topic":
            assert data == ["qr:0", "qr:1", "qr:2"]
        if name == "help":
            assert "Созвон &lt;завтра&gt;" in message.answer.call_args.args[0]


async def test_discuss_advice_and_quick_reply(backend):
    backend.topic = AsyncMock(return_value={"kind": "topic", "title": "Скоро дедлайн", "text": "Отчёт"})
    callback = fake_callback("adv:1", text="💡 Советы на сегодня")
    await chat.discuss_advice(callback)
    backend.topic.assert_awaited_with(100, 1)
    assert "Обсуждаем" in callback.message.answer.call_args.args[0]

    backend.chat = AsyncMock(return_value={"kind": "answer", "text": "Вот план", "message_id": 3})
    callback = fake_callback("qr:1", text="💡 Обсуждаем")
    await chat.quick_reply(callback)
    backend.chat.assert_awaited_with(100, "Помоги перепланировать")
    assert "Вот план" in callback.message.answer.call_args.args[0]


def test_model_markdown_becomes_telegram_html():
    text = messages.rich(
        "### План на неделю\n**Важно:** сдать *отчёт* до `пятницы`\n- пункт <один>\n* пункт два\n```\ncode **x**\n```\n[ссылка](https://dayla.example/app)"
    )
    assert_telegram_html(text)
    assert "<b>План на неделю</b>" in text and "<b>Важно:</b>" in text and "<i>отчёт</i>" in text
    assert "<code>пятницы</code>" in text and "• пункт &lt;один&gt;" in text and "• пункт два" in text
    assert "<code>code **x**</code>" in text and '<a href="https://dayla.example/app">ссылка</a>' in text
    # Crossed markers cannot become broken HTML: the text falls back to plain
    crossed = messages.rich("**жирный *и** курсив*")
    assert_telegram_html(crossed)
    assert "**" not in crossed
    assert messages.rich("2*3 = 6, файл_имя_тест") == "2*3 = 6, файл_имя_тест"
    assert_telegram_html(messages.answer("**Готово** — вот план"))


TARGETS = [{"slug": "dayla", "title": "Только Dayla"}, {"slug": "yandex", "title": "Яндекс Календарь"}]


async def test_proposal_shows_the_end_and_where_tasks_go(backend):
    many = messages.proposal(proposal_reply(count=2))
    assert "15:00–16:00" in many and "Куда" not in many

    reply = proposal_reply(targets=TARGETS, target="yandex")
    message = fake_message()
    await chat.deliver(message, reply)
    text = message.answer.call_args.args[0]
    assert_telegram_html(text)
    assert "Куда: <b>Dayla и Яндекс Календарь</b>" in text
    assert "dr:42:to" in callback_data(message.answer.call_args.kwargs["reply_markup"])

    backend.draft = AsyncMock(return_value=reply)
    callback = fake_callback("dr:42:to")
    await chat.draft_action(callback)
    markup = callback.message.edit_reply_markup.call_args.kwargs["reply_markup"]
    assert callback_data(markup) == ["dr:42:to:dayla", "dr:42:to:yandex", "dr:42:back"]
    assert markup.inline_keyboard[1][0].text == "✅ Dayla и Яндекс Календарь"

    backend.draft_target = AsyncMock(return_value={**reply, "target": "dayla"})
    callback = fake_callback("dr:42:to:dayla")
    await chat.draft_action(callback)
    backend.draft_target.assert_awaited_with(100, 42, "dayla")
    assert "Куда: <b>Только Dayla</b>" in callback.message.edit_text.call_args.args[0]


def test_created_says_where_the_tasks_went():
    text = messages.created({"kind": "created", "events": [event()], "event_ids": [7], "note": "Добавлено в Яндекс Календарь"})
    assert_telegram_html(text)
    assert "Добавлено в Яндекс Календарь" in text
