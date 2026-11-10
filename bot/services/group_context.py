"""Bounded, ephemeral text received from Telegram; no database or historical API access."""

import json
import time
from collections import OrderedDict

MAX_CHATS = 256
MAX_MESSAGES = 50
MAX_AGE = 3600
MAX_CONTEXT = 24000
MAX_TEXT = 1200


class RecentMessages:
    def __init__(self):
        self.chats = OrderedDict()

    def _prune(self):
        cutoff = time.monotonic() - MAX_AGE
        for key, rows in list(self.chats.items()):
            rows[:] = [row for row in rows if row[0] > cutoff]
            if not rows:
                del self.chats[key]

    def remember(self, message):
        self._prune()
        if not message.from_user or message.from_user.is_bot or message.sender_chat:
            return
        text = message.text or message.caption
        if not text:
            return
        key = (message.chat.id, message.message_thread_id)
        rows = self.chats.setdefault(key, [])
        rows[:] = [row for row in rows if row[1]["id"] != message.message_id]
        author = message.from_user
        rows.append((time.monotonic(), {
            "id": message.message_id,
            "at": message.date.isoformat(),
            "author": author.full_name[:100],
            "username": (author.username or "")[:64],
            "text": text[:MAX_TEXT],
        }))
        rows.sort(key=lambda row: row[1]["id"])
        del rows[:-MAX_MESSAGES]
        self.chats.move_to_end(key)
        while len(self.chats) > MAX_CHATS:
            self.chats.popitem(last=False)

    def context(self, message):
        self._prune()
        key = (message.chat.id, message.message_thread_id)
        rows = [row[1] for row in self.chats.get(key, []) if row[1]["id"] < message.message_id]
        quoted = message.reply_to_message
        if quoted and quoted.from_user and not quoted.from_user.is_bot and (quoted.text or quoted.caption):
            # An explicit reply can supply a message the bot did not receive before.
            rows = [row for row in rows if row["id"] != quoted.message_id]
            rows.append({"id": quoted.message_id, "at": quoted.date.isoformat(),
                         "author": quoted.from_user.full_name[:100],
                         "username": (quoted.from_user.username or "")[:64],
                         "text": (quoted.text or quoted.caption)[:MAX_TEXT], "replied_to": True})
        rows = rows[-MAX_MESSAGES:]
        while rows:
            result = json.dumps(rows, ensure_ascii=False)
            if len(result) <= MAX_CONTEXT:
                return result
            rows.pop(0)
        return "[]"

    def forget(self, chat_id):
        for key in list(self.chats):
            if key[0] == chat_id:
                del self.chats[key]


recent = RecentMessages()
