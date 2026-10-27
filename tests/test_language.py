"""The bot speaks the language chosen on the Deyla site; before linking, the language of the Telegram app."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot import i18n, keyboards
from bot.handlers import notifications
from bot.services.backend import BackendError
from bot.templates import messages


def test_templates_follow_the_language():
    with i18n.using("en"):
        assert "What I can do" in messages.help_text()
        assert messages.format_lead(60) == "1 h" and messages.format_lead(1440) == "1 day"
        assert messages.short("saved") == "Saved ✓"
        stats = messages.stats({"today": {"total": 0}, "days": [], "total": 0})
        assert "<b>Today</b>: no tasks" in stats
    assert "Что я умею" in messages.help_text()


def test_the_menu_is_in_the_language_and_both_languages_still_work():
    with i18n.using("en"):
        first_row = [button.text for button in keyboards.main_menu().keyboard[0]]
        assert first_row == ["📅 Today", "🗓 Tomorrow", "📆 Week"]
    # A keyboard sent before the switch stays on the screen: its buttons still answer
    assert "📅 Сегодня" in keyboards.MENU_TODAY and "📅 Today" in keyboards.MENU_TODAY


async def test_the_language_comes_from_the_site(monkeypatch):
    from bot.services import backend as backend_module

    i18n._cache.clear()
    monkeypatch.setattr(backend_module.backend, "profile", AsyncMock(return_value={"language": "en"}))
    assert await i18n.language_of(SimpleNamespace(id=101, language_code="ru")) == "en"


async def test_before_linking_the_telegram_language_is_used(monkeypatch):
    from bot.services import backend as backend_module

    i18n._cache.clear()
    monkeypatch.setattr(backend_module.backend, "profile", AsyncMock(side_effect=BackendError(404, "Telegram chat is not linked")))
    assert await i18n.language_of(SimpleNamespace(id=102, language_code="en-US")) == "en"
    assert await i18n.language_of(SimpleNamespace(id=103, language_code="uk")) == "ru"


async def test_a_notification_gets_buttons_in_its_language(monkeypatch):
    bot = SimpleNamespace(send_message=AsyncMock())
    monkeypatch.setattr(notifications.backend, "ack_notification", AsyncMock())
    await notifications.deliver(bot, {"id": 1, "chat_id": 5, "text": "🔔 Reminder", "kind": "custom", "language": "en"})
    markup = bot.send_message.call_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].text == "⏰ +10 min"
