"""↪️ Перенести: choose a task under the plan, then today / tomorrow / the day after tomorrow / another day."""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

from bot import keyboards
from bot.handlers import agenda
from bot.services.backend import BackendError
from bot.templates import messages
from tests.test_ui import assert_telegram_html, backend, callback_data, event, fake_callback  # noqa: F401

TODAY = datetime.now().astimezone().date()


def test_plan_has_a_move_button():
    assert "mv:today" in callback_data(keyboards.agenda_keyboard("today", None))


def test_move_list_skips_done_tasks():
    reply = {"title": "Сегодня", "days": [{"events": [event(title="Открытая"), {**event(title="Готово"), "id": 8, "completed": True}]}]}
    assert callback_data(keyboards.move_list_keyboard(reply, "today")) == ["mp:7:today", "ag:today"]
    assert_telegram_html(messages.move_list(reply))


def test_options_skip_the_current_day_and_fit_telegram():
    tomorrow_task = event()  # starts tomorrow
    data = callback_data(keyboards.move_options_keyboard(tomorrow_task, "today"))
    assert data == [f"mt:7:{TODAY:%Y%m%d}", f"mt:7:{TODAY + timedelta(days=2):%Y%m%d}", "mo:7:today", "mv:today"]
    labels = [button.text for button in keyboards.move_options_keyboard(tomorrow_task, "today").inline_keyboard[0]]
    assert labels[0].startswith("Сегодня, ") and labels[1].startswith("Послезавтра, ")
    days = keyboards.move_days_keyboard({**tomorrow_task, "id": 2**31}, "week")
    picks = [item for item in callback_data(days) if item.startswith("mt:")]
    assert len(picks) == keyboards.MOVE_PICKER_DAYS and all(len(item.encode()) <= 64 for item in callback_data(days))
    assert picks[0] == f"mt:{2**31}:{TODAY + timedelta(days=3):%Y%m%d}"
    assert callback_data(days)[-2:] == [f"mw:{2**31}", f"mp:{2**31}:week"]
    assert_telegram_html(messages.move_ask(tomorrow_task))


async def test_moving_shows_the_result_with_undo(backend):
    reply = {
        "kind": "updated", "text": "Перенесла «Встреча» на пятница, 10 октября.", "events": [event()],
        "moved": {"event_id": 7, "from": "2026-10-09", "to": "2026-10-10", "from_label": "четверг, 9 октября"},
    }
    backend.move = AsyncMock(return_value=reply)
    callback = fake_callback("mt:7:20261010", text="↪️ Что перенести? · Сегодня")
    await agenda.move_to(callback)
    backend.move.assert_awaited_once_with(100, 7, "2026-10-10")
    text, markup = callback.message.edit_text.call_args.args[0], callback.message.edit_text.call_args.kwargs["reply_markup"]
    assert "Перенесла" in text
    assert_telegram_html(text)
    assert callback_data(markup)[0] == "mt:7:20261009"  # "↩️ Вернуть на четверг, 9 октября"


async def test_same_day_and_gone_task_are_told_plainly(backend):
    backend.move = AsyncMock(return_value={"kind": "answer", "text": "«Встреча» уже стоит на пятница, 10 октября."})
    callback = fake_callback("mt:7:20261010")
    await agenda.move_to(callback)
    callback.answer.assert_awaited_once_with("«Встреча» уже стоит на пятница, 10 октября.", show_alert=True)

    backend.move = AsyncMock(side_effect=BackendError(410, "Event is gone"))
    callback = fake_callback("mt:7:20261010")
    await agenda.move_to(callback)
    callback.answer.assert_awaited_once_with(agenda.GONE, show_alert=True)


async def test_typed_date_asks_for_it(backend):
    backend.move_date = AsyncMock(return_value={"prompt": "Напишите новую дату", "title": "Встреча", "field": "date", "index": 0, "draft_id": 5})
    callback = fake_callback("mw:7")
    await agenda.move_typed(callback)
    sent = callback.message.answer.call_args
    assert "Напишите новую дату" in sent.args[0] and sent.kwargs["reply_markup"].force_reply
