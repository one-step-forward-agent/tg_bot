# Telegram bot instructions
When available, read `../AGENTS.md` and `../codex-setup/commands.md` for workspace rules.

- aiogram routers in `bot/handlers` handle Telegram interactions; register new routers deliberately in `bot/main.py`. Reuse `bot/keyboards.py`, `bot/templates/messages.py` and `bot/i18n.py` language middleware.
- `bot/services/backend.py` owns aiohttp calls to `/internal/bot/*` using `X-Bot-Token`; business rules and persistence belong in the backend. Coordinate callback payloads, response kinds and errors with backend routes and tests.
- Escape user text for Telegram HTML. Preserve callback ownership, linked-user checks, notification claim/ack/retry/snooze behavior and confirm-before-send cards. Keep file forwarding consistent with the backend attachment limits.
- Use `bot/services/site.py` for site links; authenticated links require `/app`. Responses follow the site's selected user language. Do not replace this with Telegram's language alone.
- Python 3.12: `python -m pip install -r requirements-dev.txt`; `python -m pytest -q`. Clear `DAYLA_CONTRACT_URL` for offline runs; `tests/test_contract.py` is skipped without it. Contract tests create data and require a disposable running backend plus matching bot secret.
- `python -m bot.main` performs real Telegram operations and updates bot metadata; run only with a development bot token and task authorization. Never poll with a production token during checks. Do not log bot tokens or private message contents.
