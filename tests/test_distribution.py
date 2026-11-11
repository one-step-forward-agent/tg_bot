from unittest.mock import AsyncMock

from bot.handlers import chat
from bot.i18n import using
from bot.keyboards import with_completion_report


async def test_distribution_shows_a_confirmation_for_each_draft(monkeypatch):
    monkeypatch.setattr(chat.site, "app_url", AsyncMock(return_value="https://example.com"))
    message = AsyncMock()
    reply = {"kind": "send_drafts", "text": "Review the distribution", "drafts": [
        {"kind": "send_draft", "draft_id": 101, "type": "team_task", "text": "Task A", "actions": ["send", "cancel"]},
        {"kind": "send_draft", "draft_id": 102, "type": "team_task", "text": "Task B", "actions": ["send", "cancel"]},
    ]}
    await chat.deliver(message, reply)
    assert message.answer.await_count == 3
    for call, identifier in zip(message.answer.call_args_list[1:], (101, 102)):
        callbacks = [button.callback_data for row in call.kwargs["reply_markup"].inline_keyboard for button in row]
        assert f"sd:{identifier}:s" in callbacks


def test_optional_completion_report_link_opens_the_owned_event_page():
    with using("en"):
        keyboard = with_completion_report(None, "https://example.com/", 42)
    [button] = keyboard.inline_keyboard[0]
    assert button.url == "https://example.com/app/events/42?report=1" and "optional" in button.text
    assert with_completion_report(None, None, 42) is None
