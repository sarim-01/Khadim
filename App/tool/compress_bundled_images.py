#!/usr/bin/env python3
"""
Resize / recompress images bundled into APK (menu + deals).
Keeps original filenames and extensions so DB paths and pubspec stay valid.

Usage (from repo root or App/):
  python tool/compress_bundled_images.py

Requires: pip install pillow
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

APP_ROOT = Path(__file__).resolve().parent.parent
TARGET_DIRS = [
    APP_ROOT / "assets" / "images" / "menu",
    APP_ROOT / "assets" / "images" / "deals",
]
SKIP_NAMES = {"khaadim_logo_dark.png", "khaadim_logo_light.png", "confirm.png"}

MAX_EDGE = 1024  # px — plenty for phone screens
JPEG_QUALITY = 82


def _flatten_rgba(im: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    if im.mode != "RGBA":
        return im.convert("RGB")
    base = Image.new("RGB", im.size, bg)
    base.paste(im, mask=im.split()[3])
    return base


def _thumbnail_keep_aspect(im: Image.Image, max_edge: int) -> Image.Image:
    im = im.copy()
    im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    return im


def compress_image(path: Path) -> tuple[int, int]:
    """Returns (bytes_before, bytes_after)."""
    before = path.stat().st_size
    ext = path.suffix.lower()
    try:
        with Image.open(path) as im:
            im.load()
            if getattr(im, "is_animated", False):
                return before, before
            thumb = _thumbnail_keep_aspect(im, MAX_EDGE)
            if ext in {".jpg", ".jpeg"}:
                rgb = thumb.convert("RGB")
                tmp = path.with_suffix(path.suffix + ".tmp")
                rgb.save(
                    tmp,
                    format="JPEG",
                    quality=JPEG_QUALITY,
                    optimize=True,
                    progressive=True,
                )
                tmp.replace(path)
            elif ext == ".png":
                rgb = _flatten_rgba(thumb)
                tmp = path.with_suffix(path.suffix + ".tmp")
                rgb.save(tmp, format="PNG", optimize=True)
                tmp.replace(path)
            else:
                return before, before
    except Exception:
        return before, before
    after = path.stat().st_size
    return before, after


def main() -> None:
    total_before = total_after = 0
    count = 0
    for base in TARGET_DIRS:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                continue
            if path.name in SKIP_NAMES:
                continue
            b0, b1 = compress_image(path)
            if b1 < b0:
                total_before += b0
                total_after += b1
                count += 1
    saved_mb = (total_before - total_after) / (1024 * 1024)
    print(f"Compressed {count} images under menu/deals")
    print(f"Approx saved: {saved_mb:.1f} MiB ({total_before} -> {total_after} bytes)")


if __name__ == "__main__":
    main()
