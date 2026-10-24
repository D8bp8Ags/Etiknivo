"""Images of the user's own on a label: stored as small greyscale PNGs."""

from __future__ import annotations

import base64
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


def decode(data: str) -> Image.Image | None:
    if not data:
        return None
    try:
        img = Image.open(io.BytesIO(base64.b64decode(data)))
        img.load()
        return img.convert("L")
    except (ValueError, OSError):
        return None


def load_file(path: Path) -> str:
    """Read a PNG, JPG, GIF, BMP or TIFF file and return it encoded for a label."""
    try:
        with Image.open(path) as img:
            img.load()
            return encode(img)
    except (OSError, ValueError) as exc:
        raise ImageError(str(exc)) from exc
