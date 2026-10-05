import time

from bot.services.backend import BackendError, backend

CACHE_SECONDS = 300
_cache: dict = {"app_url": None, "loaded_at": 0.0}


async def app_url() -> str | None:
    if time.monotonic() - _cache["loaded_at"] < CACHE_SECONDS:
        return _cache["app_url"]
    try:
        config = await backend.public_config()
        _cache["app_url"] = config.get("app_url")
        _cache["loaded_at"] = time.monotonic()
    except BackendError:
        pass
    return _cache["app_url"]
