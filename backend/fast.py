"""Speed: small, cacheable images and compressed responses.

Page images are stored as lossless PNGs, around 4 MB a page, for the forensic checks. Screens get a
WebP copy of the same pixel size, around 100 KB, so every box still lands on the same pixels. Heatmap
overlays are smooth, so they're served at half size. Copies are made once and reused. The original
PNG is still available with ?original=true, and reports and checks always use the originals.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from PIL import Image
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger("docuforensic.fast")
IMAGE_CACHE = "public, max-age=86400"
ASSET_CACHE = "public, max-age=31536000, immutable"


def display_copy(src: Path, scale: float = 1.0, quality: int = 82) -> Path:
    """A WebP copy of an image, made on first use. Falls back to the original if conversion fails."""
    out = src.with_name(f"{src.stem}{'.half' if scale < 1 else ''}.view.webp")
    try:
        if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
            return out
        with Image.open(src) as im:
            im.load()
            if scale < 1:
                im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
            tmp = out.with_name(f"{out.name}.{uuid.uuid4().hex[:8]}.tmp")
            im.save(tmp, "WEBP", quality=quality, method=4)
            tmp.replace(out)  # atomic, so a parallel request never reads half a file
        return out
    except Exception as exc:
        log.warning("display copy failed for %s: %s", src.name, type(exc).__name__)
        return src


def warm(paths: list[Path]) -> int:
    """Makes page copies ahead of time, so the first view is fast too."""
    return sum(display_copy(p) != p for p in paths if p.exists())


_SKIP_GZIP = ("/progress", "/image", "/overlays/", "/api/files/", ".pdf", ".png", ".jpg", ".webp", ".woff2")


class CompressText:
    """Gzip for JSON, HTML, JS and CSS. Not for images (already compressed) or the live progress stream."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=1024)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not any(s in scope["path"] for s in _SKIP_GZIP):
            await self.gzip(scope, receive, send)
            return
        await self.app(scope, receive, send)


class CacheAssets:
    """The built site's /assets/ files have content hashes in their names, so they never change."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/assets/"):
            await self.app(scope, receive, send)
            return

        async def with_cache(message) -> None:
            if message["type"] == "http.response.start" and message.get("status") == 200:
                message["headers"] = [*message.get("headers", []), (b"cache-control", ASSET_CACHE.encode())]
            await send(message)

        await self.app(scope, receive, with_cache)
