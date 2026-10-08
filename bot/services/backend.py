import aiohttp

from bot.config import settings

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=20)
ASSISTANT_TIMEOUT = aiohttp.ClientTimeout(total=120)


class BackendError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail

    @property
    def not_linked(self) -> bool:
        return self.status == 404


class DaylaBackend:
    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def _request(self, method: str, path: str, json: dict | None = None, timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                base_url=settings.BACKEND_URL.rstrip("/") + "/",
                headers={"X-Bot-Token": settings.BOT_API_TOKEN},
            )
        try:
            async with self._session.request(method, path.lstrip("/"), json=json, timeout=timeout) as response:
                data = await response.json(content_type=None) if response.content_length != 0 else None
                if response.status >= 400:
                    detail = data.get("detail") if isinstance(data, dict) else None
                    raise BackendError(response.status, str(detail or response.reason))
                return data
        except (aiohttp.ClientError, TimeoutError) as error:
            raise BackendError(503, str(error) or "backend unavailable") from error

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def public_config(self) -> dict:
        return await self._request("GET", "/api/public/config")

    async def link(self, code: str, chat_id: int, username: str | None) -> dict:
        return await self._request("POST", "/internal/bot/link", {"code": code, "chat_id": chat_id, "username": username})

    async def unlink(self, chat_id: int) -> None:
        await self._request("POST", f"/internal/bot/unlink/{chat_id}")

    async def profile(self, chat_id: int) -> dict:
        return await self._request("GET", f"/internal/bot/users/{chat_id}")

    async def chat(self, chat_id: int, text: str) -> dict:
        return await self._request("POST", f"/internal/bot/chat/{chat_id}", {"text": text[:50000]}, timeout=ASSISTANT_TIMEOUT)

    async def topic(self, chat_id: int, index: int) -> dict:
        return await self._request("POST", f"/internal/bot/chat/{chat_id}/topic", {"index": index})

    async def rate(self, chat_id: int, message_id: int, value: int) -> dict:
        return await self._request("POST", f"/internal/bot/chat/{chat_id}/messages/{message_id}/rating", {"value": value})

    async def agenda(self, chat_id: int, scope: str) -> dict:
        return await self._request("GET", f"/internal/bot/chat/{chat_id}/agenda/{scope}")

    async def undo(self, chat_id: int, event_ids: list[int]) -> int:
        return (await self._request("POST", f"/internal/bot/chat/{chat_id}/undo", {"event_ids": event_ids}))["deleted"]

    async def draft(self, chat_id: int, draft_id: int) -> dict:
        return await self._request("GET", f"/internal/bot/chat/{chat_id}/drafts/{draft_id}")

    async def draft_edit(self, chat_id: int, draft_id: int, index: int, field: str) -> dict:
        return await self._request("POST", f"/internal/bot/chat/{chat_id}/drafts/{draft_id}/edit", {"index": index, "field": field})

    async def draft_remove(self, chat_id: int, draft_id: int, index: int) -> dict:
        return await self._request("POST", f"/internal/bot/chat/{chat_id}/drafts/{draft_id}/remove", {"index": index})

    async def draft_calendars(self, chat_id: int, draft_id: int, calendars: list[str]) -> dict:
        return await self._request("POST", f"/internal/bot/chat/{chat_id}/drafts/{draft_id}/calendars", {"calendars": calendars})

    async def draft_confirm(self, chat_id: int, draft_id: int) -> dict:
        return await self._request("POST", f"/internal/bot/chat/{chat_id}/drafts/{draft_id}/confirm", timeout=ASSISTANT_TIMEOUT)

    async def draft_cancel(self, chat_id: int, draft_id: int) -> dict:
        return await self._request("POST", f"/internal/bot/chat/{chat_id}/drafts/{draft_id}/cancel")

    async def complete(self, chat_id: int, event_id: int, completed: bool = True) -> dict:
        return await self._request("POST", f"/internal/bot/chat/{chat_id}/events/{event_id}/complete", {"completed": completed})

    async def stats(self, chat_id: int) -> dict:
        return await self._request("GET", f"/internal/bot/chat/{chat_id}/stats")

    async def checkin(self, notification_id: int, chat_id: int, action: str) -> dict:
        return await self._request("POST", f"/internal/bot/notifications/{notification_id}/checkin", {"chat_id": chat_id, "action": action})

    async def reminder_settings(self, chat_id: int) -> dict:
        return await self._request("GET", f"/internal/bot/users/{chat_id}/reminder-settings")

    async def update_reminder_settings(self, chat_id: int, values: dict) -> dict:
        return await self._request("PATCH", f"/internal/bot/users/{chat_id}/reminder-settings", values)

    async def claim_notifications(self, limit: int = 50) -> list[dict]:
        return await self._request("POST", "/internal/bot/notifications/claim", {"limit": limit})

    async def ack_notification(self, notification_id: int, ok: bool, error: str | None = None, chat_unreachable: bool = False) -> None:
        await self._request(
            "POST",
            f"/internal/bot/notifications/{notification_id}/ack",
            {"ok": ok, "error": error, "chat_unreachable": chat_unreachable},
        )

    async def event(self, chat_id: int, event_id: int) -> dict:
        return await self._request("GET", f"/internal/bot/chat/{chat_id}/events/{event_id}")

    async def move(self, chat_id: int, event_id: int, day: str) -> dict:
        return await self._request("POST", f"/internal/bot/chat/{chat_id}/events/{event_id}/move", {"date": day})

    async def move_date(self, chat_id: int, event_id: int) -> dict:
        return await self._request("POST", f"/internal/bot/chat/{chat_id}/events/{event_id}/move-date")

    async def snooze(self, notification_id: int, chat_id: int, minutes: int) -> None:
        await self._request("POST", f"/internal/bot/notifications/{notification_id}/snooze", {"chat_id": chat_id, "minutes": minutes})


backend = DaylaBackend()
