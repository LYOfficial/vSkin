from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from typing import Any

class CachedStaticFiles(StaticFiles):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Default cache time: 1 hour (3600 seconds)
        self.cache_max_age = kwargs.pop("cache_max_age", 3600)
        super().__init__(*args, **kwargs)

    async def get_response(self, path: str, scope: Any) -> Response:
        response = await super().get_response(path, scope)
        # Set Cache-Control header
        response.headers["Cache-Control"] = f"public, max-age={self.cache_max_age}"
        return response
