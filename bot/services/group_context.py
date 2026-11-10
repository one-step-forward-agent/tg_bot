"""Bounded, ephemeral received messages and photo references; downloads happen only on request."""

import json
import time
from collections import OrderedDict

MAX_CHATS = 256
MAX_MESSAGES = 50
MAX_AGE = 3600
MAX_CONTEXT = 24000
MAX_TEXT = 1200
MAX_PHOTOS = 6
MAX_PHOTO_BYTES = 20 * 1024 * 1024


def message_row(message):
    if not message.from_user or message.from_user.is_bot or getattr(message, "sender_chat", None):
        return None
    text = message.text or message.caption or ""
    photos = getattr(message, "photo", None)
    if not text and not photos:
        return None
    author = message.from_user
    row = {"id": message.message_id, "at": message.date.isoformat(),
           "author": author.full_name[:100], "username": (author.username or "")[:64],
           "text": text[:MAX_TEXT]}
    if getattr(message, "reply_to_message", None):
        row["reply_to_id"] = message.reply_to_message.message_id
    if getattr(message, "media_group_id", None):
        row["album_id"] = message.media_group_id
    if photos:
        row["photo"] = {"file_id": photos[-1].file_id, "size": photos[-1].file_size,
                        "filename": f"message-{message.message_id}.jpg"}
    return row


def public_row(row):
    return {**row, **({"photo": {"filename": row["photo"]["filename"]}} if row.get("photo") else {})}


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
        row = message_row(message)
        if row is None:
            return
        key = (message.chat.id, message.message_thread_id)
        rows = self.chats.setdefault(key, [])
        rows[:] = [row for row in rows if row[1]["id"] != message.message_id]
        rows.append((time.monotonic(), row))
        rows.sort(key=lambda row: row[1]["id"])
        del rows[:-MAX_MESSAGES]
        self.chats.move_to_end(key)
        while len(self.chats) > MAX_CHATS:
            self.chats.popitem(last=False)

    def snapshot(self, message):
        self._prune()
        key = (message.chat.id, message.message_thread_id)
        rows = [row[1] for row in self.chats.get(key, []) if row[1]["id"] < message.message_id]
        quoted = message.reply_to_message
        quote_row = message_row(quoted) if quoted else None
        if quote_row:
            # An explicit reply can supply a message the bot did not receive before.
            rows = [row for row in rows if row["id"] != quoted.message_id]
            rows.append({**quote_row, "replied_to": True})
        if getattr(message, "photo", None):
            row = message_row(message)
            if row:
                rows.append(row)
        rows = rows[-MAX_MESSAGES:]
        while rows:
            result = json.dumps([public_row(row) for row in rows], ensure_ascii=False)
            if len(result) <= MAX_CONTEXT:
                return result, [row["photo"] for row in rows if row.get("photo")]
            rows.pop(0)
        return "[]", []

    def context(self, message):
        return self.snapshot(message)[0]

    def forget(self, chat_id):
        for key in list(self.chats):
            if key[0] == chat_id:
                del self.chats[key]


recent = RecentMessages()
