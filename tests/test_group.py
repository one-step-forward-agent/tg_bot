"""Deyla in a group: only a mention or an answer to it is a request, made for the person who wrote it."""

from types import SimpleNamespace
from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock

import pytest

from bot.handlers import group
from bot.services.backend import BackendError
from bot.services.group_context import RecentMessages, MAX_CONTEXT, MAX_MESSAGES

from bot.handlers.group import request_text


def message(text, reply_to=None, title="Команда"):
    return SimpleNamespace(text=text, caption=None, reply_to_message=reply_to, chat=SimpleNamespace(title=title))


def test_the_mention_is_taken_out():
    assert request_text(message("@dayla_bot отчёт к пятнице"), "dayla_bot", False) == "отчёт к пятнице"


def test_an_answer_to_a_colleague_carries_their_message():
    quoted = SimpleNamespace(text="Пришлите отчётность к концу квартала", caption=None, from_user=SimpleNamespace(full_name="Сергей"))
    text = request_text(message("@dayla_bot", reply_to=quoted), "dayla_bot", False)
    assert text.startswith("Запланируй это") and "от Сергей" in text and "Пришлите отчётность" in text


def test_an_answer_to_dayla_is_the_request_itself():
    quoted = SimpleNamespace(text="Записала", caption=None, from_user=SimpleNamespace(full_name="Deyla"))
    assert request_text(message("и созвон в 15", reply_to=quoted), "dayla_bot", True) == "и созвон в 15"


def received(text="Tomorrow at 15:00", *, chat=-10, topic=None, mid=1, uid=42):
    return SimpleNamespace(
        text=text, caption=None, chat=SimpleNamespace(id=chat, type="supergroup", title="Team"),
        message_thread_id=topic, message_id=mid, date=datetime.now(timezone.utc), sender_chat=None,
        from_user=SimpleNamespace(id=uid, is_bot=False, full_name="Anna", username="anna"),
        reply_to_message=None, reply=AsyncMock(),
    )


def test_context_is_bounded_and_topics_are_isolated(monkeypatch):
    cache = RecentMessages()
    for mid in range(1, 80):
        cache.remember(received("x" * 3000, mid=mid))
    context = cache.context(received(mid=100))
    rows = json.loads(context)
    assert len(context) <= MAX_CONTEXT and len(rows) <= MAX_MESSAGES
    assert rows[-1]["id"] == 79 and len(rows[-1]["text"]) == 1200
    assert cache.context(received(chat=-11, mid=100)) == "[]"
    assert cache.context(received(topic=2, mid=100)) == "[]"
    monkeypatch.setattr("bot.services.group_context.time.monotonic", lambda: 10**20)
    assert cache.context(received(mid=100)) == "[]"


def test_edits_replace_text_and_removal_clears_all_topics():
    cache = RecentMessages()
    cache.remember(received("old"))
    cache.remember(received("new"))
    cache.remember(received("topic", topic=2))
    assert [row["text"] for row in json.loads(cache.context(received(mid=10)))] == ["new"]
    cache.forget(-10)
    assert not cache.chats


def test_cache_evicts_oldest_topic():
    from bot.services.group_context import MAX_CHATS

    cache = RecentMessages()
    for chat in range(MAX_CHATS + 1):
        cache.remember(received(chat=chat))
    assert len(cache.chats) == MAX_CHATS
    assert cache.context(received(chat=0, mid=10)) == "[]"


async def test_passive_group_middleware_does_not_look_up_accounts(monkeypatch):
    from bot.i18n import LanguageMiddleware

    lookup = AsyncMock()
    monkeypatch.setattr("bot.i18n.language_of", lookup)
    handler = AsyncMock()
    msg = received()
    await LanguageMiddleware()(handler, msg, {"event_from_user": msg.from_user})
    lookup.assert_not_awaited()
    handler.assert_awaited_once()


def test_explicit_reply_supplies_missing_context():
    msg = received(mid=10)
    msg.reply_to_message = received("Friday at noon")
    assert json.loads(RecentMessages().context(msg))[0]["replied_to"] is True


def test_explicit_quote_still_respects_message_limit():
    cache = RecentMessages()
    for mid in range(2, MAX_MESSAGES + 2):
        cache.remember(received("short", mid=mid))
    msg = received(mid=100)
    msg.reply_to_message = received("quoted")
    rows = json.loads(cache.context(msg))
    assert len(rows) == MAX_MESSAGES and rows[-1]["replied_to"] is True


@pytest.fixture
def group_setup(monkeypatch):
    cache = RecentMessages()
    monkeypatch.setattr(group, "recent", cache)
    profile = AsyncMock(return_value={"language": "en"})
    ask = AsyncMock(return_value={"kind": "proposal", "draft_id": 7})
    delivery = AsyncMock()
    monkeypatch.setattr(group.backend, "profile", profile)
    monkeypatch.setattr(group.backend, "group_chat", ask)
    monkeypatch.setattr(group, "deliver", delivery)
    bot = SimpleNamespace(me=AsyncMock(return_value=SimpleNamespace(id=99, username="dayla_bot")), send_message=AsyncMock())
    return cache, profile, ask, delivery, bot


async def test_ordinary_messages_only_enter_buffer(group_setup):
    cache, profile, ask, delivery, bot = group_setup
    await group.group_message(received(), bot)
    profile.assert_not_awaited()
    ask.assert_not_awaited()
    assert "Tomorrow" in cache.context(received(mid=10))


async def test_mention_uses_sender_id_and_answers_privately(group_setup):
    cache, profile, ask, delivery, bot = group_setup
    cache.remember(received("Friday at 15:00"))
    msg = received("@dayla_bot add the meeting with @anna", mid=2, uid=55)
    await group.group_message(msg, bot)
    profile.assert_awaited_once_with(55)
    args = ask.call_args.args
    assert args[:2] == (55, "add the meeting with @anna") and "Friday at 15:00" in args[2]
    assert delivery.call_args.args[0].chat_id == 55
    assert "Sent the answer privately" in msg.reply.call_args.args[0]


async def test_unlinked_sender_cannot_run_assistant(group_setup):
    _, profile, ask, delivery, bot = group_setup
    profile.side_effect = BackendError(404, "not linked")
    await group.group_message(received("@dayla_bot scan the chat"), bot)
    ask.assert_not_awaited()
    delivery.assert_not_awaited()


async def test_similar_username_does_not_trigger(group_setup):
    _, profile, ask, _, bot = group_setup
    await group.group_message(received("@dayla_bot_other scan"), bot)
    profile.assert_not_awaited()
    ask.assert_not_awaited()


async def test_scan_command_and_bot_reply(group_setup):
    _, _, ask, _, bot = group_setup
    await group.group_message(received("/dayla@dayla_bot add Friday meeting"), bot)
    assert ask.call_args.args[1] == "add Friday meeting"
    msg = received("What about tomorrow?", mid=2)
    msg.reply_to_message = received()
    msg.reply_to_message.from_user.id = 99
    await group.group_message(msg, bot)
    assert ask.call_args.args[1] == "What about tomorrow?"


async def test_private_delivery_failure_prevents_actions(group_setup):
    from aiogram.exceptions import TelegramForbiddenError
    from aiogram.methods import SendMessage

    _, _, ask, _, bot = group_setup
    bot.send_message.side_effect = TelegramForbiddenError(method=SendMessage(chat_id=42, text="x"), message="blocked")
    await group.group_message(received("@dayla_bot scan"), bot)
    ask.assert_not_awaited()
