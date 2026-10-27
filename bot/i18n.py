"""The bot speaks the language chosen on the Deyla site ("ru" or "en").

The language is set for each update by LanguageMiddleware (and for each notification by the worker), so the
templates and keyboards only ask tr("Сегодня", "Today")."""

import time
from contextlib import contextmanager
from contextvars import ContextVar

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

current: ContextVar[str] = ContextVar("bot_lang", default="ru")

# A chat's language is asked of the backend at most this often: it changes only when the user switches it on the site
CACHE_SECONDS = 60
_cache: dict[int, tuple[str, float]] = {}


def is_en() -> bool:
    return current.get() == "en"


def tr(ru: str, en: str) -> str:
    """The text in the chat's language."""
    return en if is_en() else ru


def plural_en(count: int, one: str, many: str) -> str:
    return one if count == 1 else many


@contextmanager
def using(code: str | None):
    token = current.set("en" if code == "en" else "ru")
    try:
        yield
    finally:
        current.reset(token)


def telegram_language(user: User | None) -> str:
    """Before the account is linked: the language of the Telegram app (Russian for it and its neighbours)."""
    code = (getattr(user, "language_code", None) or "ru").lower()
    return "ru" if code.split("-")[0] in ("ru", "uk", "be", "kk", "uz", "ky") else "en"


def remember(chat_id: int, code: str | None) -> None:
    """The language the backend just said for a chat (a profile, a linked account)."""
    if code in ("ru", "en"):
        _cache[chat_id] = (code, time.monotonic() + CACHE_SECONDS)


async def language_of(user: User | None) -> str:
    from bot.services.backend import BackendError, backend

    if user is None:
        return "ru"
    cached = _cache.get(user.id)
    if cached and cached[1] > time.monotonic():
        return cached[0]
    # The private chat with a user has the user's id: the account is found by it in groups too
    try:
        code = (await backend.profile(user.id)).get("language") or "ru"
    except BackendError:
        code = telegram_language(user)
    _cache[user.id] = (code, time.monotonic() + CACHE_SECONDS)
    return code


class LanguageMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        with using(await language_of(data.get("event_from_user"))):
            return await handler(event, data)
