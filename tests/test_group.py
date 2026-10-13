"""Dayla in a group: only a mention or an answer to it is a request, made for the person who wrote it."""

from types import SimpleNamespace

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
    quoted = SimpleNamespace(text="Записала", caption=None, from_user=SimpleNamespace(full_name="Dayla"))
    assert request_text(message("и созвон в 15", reply_to=quoted), "dayla_bot", True) == "и созвон в 15"
