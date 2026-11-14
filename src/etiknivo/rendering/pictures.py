"""Images of the user's own on a label: stored as small greyscale PNGs."""

from __future__ import annotations

import base64
import functools
import io
from pathlib import Path

from PIL import Image, ImageOps

#: Longest side kept; the label shows at most about 12 mm (96 dots), so this
#: leaves room for supersampling while keeping the library file small.
MAX_SIDE = 256


class ImageError(ValueError):
    """The file is not an image Etiknivo can read."""


def prepare(img: Image.Image) -> Image.Image:
    """Flatten transparency onto white, make it grey and trim the white border."""
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    img = img.convert("L")
    box = ImageOps.invert(img).point(lambda v: 255 if v > 24 else 0).getbbox()
    if box:
        img = img.crop(box)
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    return img


def encode(img: Image.Image) -> str:
    buf = io.BytesIO()
    prepare(img).save(buf, "PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


#: Largest stored image accepted (pixels per side).  Etiknivo stores at most
#: :data:`MAX_SIDE`; a much larger image in a library file was not made by
#: Etiknivo and is refused rather than decoded (memory, decompression bombs).
MAX_DECODE_SIDE = 4096


def decode(data: str) -> Image.Image | None:
    """The stored image, or None when there is none or it cannot be used.
    Decoded images are cached: every render of the label needs it."""
    if not data:
        return None
    img = _decode(data)
    return img.copy() if img is not None else None


@functools.lru_cache(maxsize=64)
def _decode(data: str) -> Image.Image | None:
    try:
        img = Image.open(io.BytesIO(base64.b64decode(data)))
        if max(img.size) > MAX_DECODE_SIDE:
            return None
        img.load()
        return img.convert("L")
    except (ValueError, OSError, Image.DecompressionBombError):
        return None


def load_file(path: Path) -> str:
    """Read a PNG, JPG, GIF, BMP or TIFF file and return it encoded for a label."""
    try:
        with Image.open(path) as img:
            img.load()
            return encode(img)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ImageError(str(exc)) from exc
