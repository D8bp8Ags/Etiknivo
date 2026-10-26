"""Looks for personal details in the repository before they reach GitHub.

    uv run python scripts/privacy_check.py                  # all tracked files
    uv run python scripts/privacy_check.py --commits A..B   # plus author/committer of those commits
    uv run python scripts/privacy_check.py --commit SHA     # idem for single commits (repeatable)
    uv run python scripts/privacy_check.py --build dist/Etiknivo.app   # a built app or zip

Checks every file that git tracks (staged content included) for home folders
with a user name (``/Users/naam``, ``/home/naam``, ``C:\\Users\\naam``), e-mail
addresses, Bluetooth MAC addresses, tokens and private keys, and images for
embedded metadata (EXIF, XMP, PNG text).  With ``--commits`` it also checks
that every commit uses a GitHub no-reply e-mail address.  With ``--build`` it
looks inside a built app (or a zip of one), including the Python modules that
PyInstaller packs into the executable, for this computer's home folder, user
name and host name.

A line that is fine on purpose gets ``privacy: ok`` in a comment.  The
pytest test ``tests/test_privacy.py`` runs the same check; the git hook in
``scripts/hooks/pre-push`` runs it before every push.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import socket
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOW = "privacy: ok"

# Placeholders that may appear in examples; anything else after /Users/ is a real name.
_PLACEHOLDERS = r"(?:naam|name|user|username|gebruiker|you|jij|me|\$USER|\$\{USER\}|<[^>]+>|\.\.\.|…)"
_EMAIL_OK = re.compile(r"@(?:users\.noreply\.github\.com|example\.(?:com|org|net)|[a-z0-9.-]*\.invalid)$",
                       re.IGNORECASE)

TEXT_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("thuismap met gebruikersnaam",
     re.compile(r"(?<![\w~])/(?:Users|home)/(?!" + _PLACEHOLDERS + r"\b)[A-Za-z0-9._-]{2,}")),
    ("Windows-thuismap met gebruikersnaam",
     re.compile(r"[A-Za-z]:(?:\\\\?|/)Users(?:\\\\?|/)(?!" + _PLACEHOLDERS
                + r"\b|Public\b|Default\b)[A-Za-z0-9._ -]{2,}", re.IGNORECASE)),
    ("e-mailadres", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")),
    ("Bluetooth-/MAC-adres",
     re.compile(r"(?<![0-9A-Fa-f:-])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:-])")),
    ("GitHub-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("API-sleutel", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}"
                               r"|xox[abpr]-[A-Za-z0-9-]{10,})")),
    ("private sleutel", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".heic"}
# PNG chunks that only describe pixels; anything else (tEXt, iTXt, zTXt, eXIf, ...) is metadata
_PNG_PIXEL_CHUNKS = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"pHYs", b"sRGB", b"gAMA",
                     b"cHRM", b"iCCP", b"sBIT", b"bKGD", b"hIST", b"sPLT", b"acTL", b"fcTL", b"fdAT"}


@dataclass(frozen=True)
class Finding:
    where: str
    what: str
    text: str

    def __str__(self) -> str:
        return f"{self.where}: {self.what}: {self.text}"


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def tracked_files() -> list[str]:
    """Every file git knows about (staged included), or every file when this
    is not a git checkout."""
    try:
        out = _git("ls-files", "-z", "--cached")
        return [p for p in out.decode("utf-8").split("\0") if p and (ROOT / p).is_file()]
    except (OSError, subprocess.CalledProcessError):
        skip = {".git", ".venv", "__pycache__", ".pytest_cache", "build", "dist"}
        return [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
                if p.is_file() and not skip & set(p.relative_to(ROOT).parts)]


def _content(path: str) -> bytes:
    """The staged version when there is one, so a commit is checked as it will be."""
    try:
        return _git("show", f":{path}")
    except (OSError, subprocess.CalledProcessError):
        return (ROOT / path).read_bytes()


def check_text(where: str, text: str) -> list[Finding]:
    found = []
    for no, line in enumerate(text.splitlines(), 1):
        if ALLOW in line:
            continue
        for what, rule in TEXT_RULES:
            for m in rule.finditer(line):
                hit = m.group(0)
                if what == "e-mailadres" and _EMAIL_OK.search(hit):
                    continue
                if what == "Bluetooth-/MAC-adres" and not set(hit) - set("0:-"):
                    continue  # 00:00:00:00:00:00 is the simulated printer
                found.append(Finding(f"{where}:{no}", what, hit))
    return found


def png_metadata(data: bytes) -> list[str]:
    """Names (and text keys) of the metadata chunks in a PNG."""
    out, i = [], 8
    while i + 8 <= len(data):
        size = int.from_bytes(data[i:i + 4], "big")
        kind = data[i + 4:i + 8]
        if kind not in _PNG_PIXEL_CHUNKS:
            body = data[i + 8:i + 8 + size]
            key = body.split(b"\0", 1)[0][:40].decode("latin-1") if kind in (b"tEXt", b"iTXt", b"zTXt") \
                else ""
            out.append(kind.decode("latin-1") + (f" ({key})" if key else ""))
        i += 12 + size
    return out


def check_image(where: str, data: bytes) -> list[Finding]:
    if data.startswith(b"\x89PNG"):
        return [Finding(where, "metadata in afbeelding", m) for m in png_metadata(data)]
    hits = [tag for tag, marker in (("EXIF", b"Exif\0\0"), ("XMP", b"http://ns.adobe.com/xap/"))
            if marker in data]
    return [Finding(where, "metadata in afbeelding", t) for t in hits]


def check_files(paths: list[str] | None = None) -> list[Finding]:
    found: list[Finding] = []
    for path in paths if paths is not None else tracked_files():
        data = _content(path)
        if Path(path).suffix.lower() in IMAGE_SUFFIXES:
            found += check_image(path, data)
            continue
        if b"\0" in data[:8000]:
            continue  # fonts, icons and other binaries: no text to read
        found += check_text(path, data.decode("utf-8", errors="replace"))
    return found


def check_commits(*revs: str, walk: bool = True) -> list[Finding]:
    """Author and committer of every commit in *revs* must use a GitHub no-reply address.
    With ``walk=False`` only the commits named, not their ancestors."""
    if not revs:
        return []
    try:
        out = _git("log", "--format=%h%x00%an%x00%ae%x00%cn%x00%ce",
                   *([] if walk else ["--no-walk=unsorted"]), *revs, "--")
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.stderr.decode(errors="replace").strip()) from None
    found = []
    for line in out.decode("utf-8", errors="replace").splitlines():
        sha, an, ae, cn, ce = line.split("\0")
        for role, name, mail in (("auteur", an, ae), ("committer", cn, ce)):
            if not mail.lower().endswith("@users.noreply.github.com"):
                found.append(Finding(f"commit {sha}", f"{role} zonder no-reply-adres", f"{name} <{mail}>"))
    return found


def _local_markers() -> list[bytes]:
    """What identifies this computer: home folder, user name (as a path part) and host name."""
    home = str(Path.home())
    marks = {home, home.replace("\\", "/")}
    user = getpass.getuser()
    if len(user) >= 3:
        marks |= {f"/{user}/", f"\\{user}\\"}
    host = socket.gethostname().split(".")[0]
    if len(host) >= 3 and host.lower() not in {"localhost", "runner"}:
        marks.add(host)
    return sorted({m.encode() for m in marks if m and m not in ("/", "/root")})


def _pyinstaller_modules(path: Path):
    """(name, bytes) of everything PyInstaller packed into an executable; nothing
    when the file is not one, or PyInstaller is not installed (uv sync --group build)."""
    try:
        from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
        archive = CArchiveReader(str(path))
    except Exception:  # noqa: BLE001 - not a PyInstaller executable
        return
    for name in archive.toc:
        data = archive.extract(name)
        if not data:
            continue
        yield name, data
        if name.endswith(".pyz"):
            with tempfile.NamedTemporaryFile(suffix=".pyz", delete=False) as tmp:
                tmp.write(data)
            try:
                pyz = ZlibArchiveReader(tmp.name)
                for mod in pyz.toc:
                    code = pyz.extract(mod, raw=True)
                    if code:
                        yield f"{name}/{mod}", code
            finally:
                os.unlink(tmp.name)


def check_build(target: str) -> list[Finding]:
    """Look for this computer's home folder, user name and host name in a built app."""
    marks = _local_markers()
    found: list[Finding] = []

    def scan(where: str, data: bytes) -> None:
        for m in marks:
            if m in data:
                found.append(Finding(where, "gegevens van deze computer", m.decode(errors="replace")))

    def scan_file(where: str, data: bytes) -> None:
        scan(where, data)
        if data[:4] in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"MZ\x90\x00", b"\x7fELF"):
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(data)
            try:
                for name, inner in _pyinstaller_modules(Path(tmp.name)):
                    scan(f"{where} > {name}", inner)
            finally:
                os.unlink(tmp.name)

    root = Path(target)
    if root.is_file() and zipfile.is_zipfile(root):
        with zipfile.ZipFile(root) as z:
            for info in z.infolist():
                scan(f"{root.name}:{info.filename}", info.filename.encode())
                if not info.is_dir():
                    scan_file(f"{root.name}:{info.filename}", z.read(info))
    else:
        for p in sorted(root.rglob("*") if root.is_dir() else [root]):
            if p.is_file() and not p.is_symlink():
                scan_file(p.relative_to(root.parent).as_posix(), p.read_bytes())
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--commits", metavar="RANGE",
                    help="controleer ook auteur/committer, bijv. origin/main..HEAD")
    ap.add_argument("--commit", action="append", default=[], metavar="SHA",
                    help="controleer auteur/committer van deze ene commit (mag vaker)")
    ap.add_argument("--build", metavar="PAD",
                    help="controleer alleen een gebouwde app of zip, bijv. dist/Etiknivo.app")
    args = ap.parse_args(argv)
    if args.build:
        found = check_build(args.build)
        for f in found:
            print(f, file=sys.stderr)
        if found:
            print(f"\nPrivacycontrole: {len(found)} plek(ken) met gegevens van deze computer in "
                  f"{args.build}. Deel deze build niet.", file=sys.stderr)
            return 1
        print(f"Privacycontrole: niets gevonden in {args.build}.")
        return 0
    found = check_files()
    if args.commits:
        found += check_commits(args.commits)
    found += check_commits(*args.commit, walk=False)
    for f in found:
        print(f, file=sys.stderr)
    if found:
        print(f"\nPrivacycontrole: {len(found)} probleem/problemen gevonden. Haal ze weg, of zet "
              f"'{ALLOW}' in een commentaar op de regel als het zo hoort.", file=sys.stderr)
        return 1
    print("Privacycontrole: niets gevonden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
