"""Font discovery and resolution for Pillow.

Pillow needs a font *file*, while the GUI works with family names.  This module
maps ``(family, bold, italic)`` to a concrete file (and face index for ``.ttc``
collections).  It knows:

* the bundled DejaVu Sans fonts (always available, full coverage of Ω µ ° × ¼ –),
* system fonts in the standard macOS / Linux / Windows font directories.

The system index is built lazily with fontTools and cached on disk.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path

from PIL import ImageFont

from etiknivo.i18n import tr

log = logging.getLogger(__name__)
# fontTools warns about small flaws in system font files (for example "1 extra
# bytes in post.stringData array" for some macOS fonts) when it reads their
# tables.  The fonts work fine and the user cannot fix them, so only real
# errors from fontTools reach the log.
logging.getLogger("fontTools").setLevel(logging.ERROR)

FALLBACK_FAMILY = "DejaVu Sans"
_BUNDLED = {
    "DejaVu Sans": {
        (False, False): "DejaVuSans.ttf",
        (True, False): "DejaVuSans-Bold.ttf",
        (False, True): "DejaVuSans-Oblique.ttf",
        (True, True): "DejaVuSans-BoldOblique.ttf",
    },
    "DejaVu Sans Condensed": {
        (False, False): "DejaVuSansCondensed.ttf",
        (True, False): "DejaVuSansCondensed-Bold.ttf",
        (False, True): "DejaVuSansCondensed-Oblique.ttf",
        (True, True): "DejaVuSansCondensed-BoldOblique.ttf",
    },
}
_FONT_SUFFIXES = {".ttf", ".otf", ".ttc"}


@dataclass(frozen=True)
class FontFace:
    """A concrete font face, plus flags for synthetic styling when the family
    has no real bold/italic variant."""

    path: str
    index: int = 0
    family: str = FALLBACK_FAMILY
    synthetic_bold: bool = False
    synthetic_italic: bool = False


def bundled_font_path(filename: str) -> str:
    return str(resources.files("etiknivo.fonts").joinpath(filename))


def system_font_dirs() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        dirs = [Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"),
                Path("/Library/Fonts"), home / "Library/Fonts"]
    elif sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR", "C:/Windows"))
        dirs = [windir / "Fonts", home / "AppData/Local/Microsoft/Windows/Fonts"]
    else:
        dirs = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), home / ".fonts",
                home / ".local/share/fonts"]
    return [d for d in dirs if d.is_dir()]


def _style_flags(subfamily: str, ttfont) -> tuple[bool, bool]:  # type: ignore[no-untyped-def]
    sub = subfamily.lower()
    bold = any(w in sub for w in ("bold", "black", "heavy")) and "semibold" not in sub
    italic = "italic" in sub or "oblique" in sub
    try:  # OS/2 fsSelection is more reliable when present
        fs = ttfont["OS/2"].fsSelection
        bold = bold or bool(fs & 0x20)
        italic = italic or bool(fs & 0x01)
    except Exception:  # noqa: BLE001 - optional table
        pass
    return bold, italic


def _scan_file(path: Path) -> list[dict]:
    from fontTools.ttLib import TTCollection, TTFont

    entries: list[dict] = []
    try:
        fonts = (TTCollection(str(path), lazy=True).fonts if path.suffix.lower() == ".ttc"
                 else [TTFont(str(path), lazy=True)])
    except Exception as exc:  # noqa: BLE001 - corrupt/unsupported font files are skipped
        log.debug(tr("Lettertype overgeslagen %s: %s"), path, exc)
        return entries
    for idx, f in enumerate(fonts):
        try:
            name = f["name"]
            family = (name.getDebugName(16) or name.getDebugName(1) or "").strip()
            sub = (name.getDebugName(17) or name.getDebugName(2) or "Regular").strip()
            if not family or family.startswith("."):
                continue
            bold, italic = _style_flags(sub, f)
            entries.append({"family": family, "style": sub, "bold": bold, "italic": italic,
                            "path": str(path), "index": idx})
        except Exception as exc:  # noqa: BLE001
            log.debug(tr("Lettertype overgeslagen %s#%d: %s"), path, idx, exc)
    return entries


class FontRegistry:
    """Thread-safe registry of available font families."""

    def __init__(self, cache_file: Path | None = None, scan_system: bool = True) -> None:
        self._cache_file = cache_file
        self._scan_system = scan_system
        self._faces: dict[str, list[dict]] = {}
        self._lock = threading.Lock()
        self._scanned = False

    # -- indexing ----------------------------------------------------------------

    def _ensure_index(self) -> None:
        with self._lock:
            if self._scanned:
                return
            entries: list[dict] = []
            if self._scan_system:
                entries = self._load_or_scan()
            faces: dict[str, list[dict]] = {}
            for e in entries:
                faces.setdefault(e["family"], []).append(e)
            self._faces = faces
            self._scanned = True

    def _load_or_scan(self) -> list[dict]:
        files: dict[str, float] = {}
        for d in system_font_dirs():
            for root, _dirs, names in os.walk(d):
                for n in names:
                    p = Path(root) / n
                    if p.suffix.lower() in _FONT_SUFFIXES:
                        try:
                            files[str(p)] = p.stat().st_mtime
                        except OSError:
                            pass
        cached: dict = {}
        if self._cache_file and self._cache_file.exists():
            try:
                cached = json.loads(self._cache_file.read_text("utf-8"))
            except (OSError, ValueError):
                cached = {}
        entries: list[dict] = []
        new_cache: dict = {}
        for path, mtime in files.items():
            hit = cached.get(path)
            if hit and hit.get("mtime") == mtime:
                found = hit["entries"]
            else:
                found = _scan_file(Path(path))
            new_cache[path] = {"mtime": mtime, "entries": found}
            entries.extend(found)
        if self._cache_file and new_cache != cached:
            try:
                self._cache_file.parent.mkdir(parents=True, exist_ok=True)
                self._cache_file.write_text(json.dumps(new_cache), "utf-8")
            except OSError as exc:
                log.debug(tr("Lettertypecache niet opgeslagen: %s"), exc)
        return entries

    # -- queries -------------------------------------------------------------------

    def families(self) -> list[str]:
        self._ensure_index()
        names = set(self._faces) | set(_BUNDLED)
        return sorted(names, key=str.casefold)

    def resolve(self, family: str, bold: bool = False, italic: bool = False) -> FontFace:
        """Find the best face for *family*; fall back to bundled DejaVu Sans."""
        if family in _BUNDLED:
            return FontFace(bundled_font_path(_BUNDLED[family][(bold, italic)]), 0, family)
        self._ensure_index()
        faces = self._faces.get(family)
        if not faces:
            return FontFace(bundled_font_path(_BUNDLED[FALLBACK_FAMILY][(bold, italic)]), 0,
                            FALLBACK_FAMILY)

        def score(e: dict) -> tuple[int, int]:
            s = (e["bold"] == bold) * 2 + (e["italic"] == italic) * 2
            plain = e["style"].lower() in ("regular", "roman", "book", "normal", "bold",
                                           "italic", "bold italic", "oblique", "bold oblique")
            return s, int(plain)

        best = max(faces, key=score)
        return FontFace(best["path"], best["index"], family,
                        synthetic_bold=bold and not best["bold"],
                        synthetic_italic=italic and not best["italic"])

    @staticmethod
    def fallback(bold: bool = False, italic: bool = False) -> FontFace:
        return FontFace(bundled_font_path(_BUNDLED[FALLBACK_FAMILY][(bold, italic)]), 0,
                        FALLBACK_FAMILY)


@lru_cache(maxsize=64)
def _codepoints(path: str, index: int) -> frozenset[int]:
    from fontTools.ttLib import TTFont

    try:
        f = TTFont(path, fontNumber=index, lazy=True)
        cmap = f.getBestCmap() or {}
        return frozenset(cmap)
    except Exception:  # noqa: BLE001
        return frozenset()


def missing_glyphs(face: FontFace, text: str) -> str:
    """Characters of *text* that *face* cannot render (whitespace ignored)."""
    cps = _codepoints(face.path, face.index)
    if not cps:
        return ""
    return "".join(sorted({c for c in text if not c.isspace() and ord(c) not in cps}))


@lru_cache(maxsize=256)
def pil_font(path: str, index: int, size_px: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=max(1.0, size_px), index=index,
                              layout_engine=ImageFont.Layout.BASIC)


_default_registry: FontRegistry | None = None


def default_registry() -> FontRegistry:
    global _default_registry
    if _default_registry is None:
        cache = None
        try:
            from etiknivo.settings import data_dir

            cache = data_dir() / "font_cache.json"
        except Exception:  # noqa: BLE001
            pass
        _default_registry = FontRegistry(cache)
    return _default_registry


def set_default_registry(reg: FontRegistry) -> None:
    global _default_registry
    _default_registry = reg
