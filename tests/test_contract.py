"""The bot's backend client against a running backend (set DAYLA_CONTRACT_URL, e.g. http://backend:8000)."""

import os
import uuid

import aiohttp
import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DAYLA_CONTRACT_URL"), reason="needs a running backend")


async def test_bot_flow_against_backend(monkeypatch):
    from bot.config import settings
    from bot.services.backend import BackendError, DaylaBackend

    base = os.environ["DAYLA_CONTRACT_URL"]
    monkeypatch.setattr(settings, "BACKEND_URL", base)
    async with aiohttp.ClientSession() as http:
        email = f"bot-{uuid.uuid4().hex[:8]}@example.com"
        async with http.post(f"{base}/auth/register", json={"email": email, "password": "password-123", "timezone": "Europe/Moscow"}) as response:
            token = (await response.json())["access_token"]
        async with http.post(f"{base}/api/telegram/link", headers={"Authorization": f"Bearer {token}"}) as response:
            code = (await response.json())["code"]

    client = DaylaBackend()
    chat_id = uuid.uuid4().int % 10**12
    try:
        assert (await client.link(code, chat_id, "tester"))["email"] == email
        proposal = await client.chat(chat_id, "купить продукты завтра")
        assert proposal["kind"] == "proposal" and proposal["events"][0]["time"] is None
        draft_id = proposal["draft_id"]
        prompt = await client.draft_edit(chat_id, draft_id, 0, "time")
        assert prompt["field"] == "time"
        edited = await client.chat(chat_id, "в 19:30")
        assert edited["events"][0]["time"] == "19:30"
        assert (await client.draft(chat_id, draft_id))["draft_id"] == draft_id
        created = await client.draft_confirm(chat_id, draft_id)
        assert created["kind"] == "created"
        with pytest.raises(BackendError) as gone:
            await client.draft_cancel(chat_id, draft_id)
        assert gone.value.status == 410

        done = await client.complete(chat_id, created["event_ids"][0])
        assert done["completed"] is True
        stats = await client.stats(chat_id)
        assert stats["days"][-1]["total"] >= 0 and "streak" in stats
        tomorrow = await client.agenda(chat_id, "tomorrow")
        assert tomorrow["days"][0]["events"][0]["completed"] is True
        assert (await client.chat(chat_id, "когда у меня стоматолог?"))["kind"] == "not_found"

        removable = await client.chat(chat_id, "каждый вторник в 19:00 бассейн")
        assert removable["events"][0]["recurrence"] == "по вторникам"
        assert (await client.draft_remove(chat_id, removable["draft_id"], 0))["kind"] == "cancelled"

        assert isinstance(await client.claim_notifications(), list)
        settings_reply = await client.reminder_settings(chat_id)
        assert settings_reply["settings"]["checkin_enabled"] is True
        await client.update_reminder_settings(chat_id, {"checkin_enabled": False})
        assert (await client.reminder_settings(chat_id))["settings"]["checkin_enabled"] is False
    finally:
        await client.close()
