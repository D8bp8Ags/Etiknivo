"""Looking for a newer version on GitHub.

Only reads the public release list (no account, nothing is sent except the
request itself).  Etiknivo never downloads or installs anything: the user
gets a link to the release page.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from etiknivo import APP_NAME, __version__
from etiknivo.i18n import tr

REPO = "D8bp8Ags/Etiknivo"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    notes: str = ""


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3' or '1.2' → (1, 2, 3) / (1, 2, 0).  Anything after the
    numbers (like '-beta') is ignored."""
    m = re.match(r"\s*[vV]?(\d+(?:\.\d+)*)", text)
    if not m:
        raise ValueError(text)
    parts = [int(p) for p in m.group(1).split(".")]
    return tuple(parts + [0] * (3 - len(parts)))


def is_newer(latest: str, current: str = __version__) -> bool:
    try:
        return parse_version(latest) > parse_version(current)
    except ValueError:
        return False


def release_from_json(data: dict) -> Release:
    tag = str(data.get("tag_name") or data.get("name") or "")
    try:
        parse_version(tag)
    except ValueError:
        raise UpdateError(tr("Onbekend versienummer: {tag}", tag=tag)) from None
    return Release(tag.lstrip("vV"), str(data.get("html_url") or RELEASES_PAGE),
                   str(data.get("body") or ""))


def fetch_latest(timeout: float = 8.0) -> Release | None:
    """The newest published release, or None when there is none yet.
    Raises :class:`UpdateError` when GitHub cannot be reached."""
    req = urllib.request.Request(LATEST_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{APP_NAME}/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https URL
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise UpdateError(tr("GitHub antwoordde met fout {code}", code=exc.code)) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError(tr("Geen verbinding met GitHub ({error})",
                             error=getattr(exc, "reason", exc))) from exc
    except ValueError as exc:
        raise UpdateError(tr("Onverwacht antwoord van GitHub")) from exc
    return release_from_json(data)
