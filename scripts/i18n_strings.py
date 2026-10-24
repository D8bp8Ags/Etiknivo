"""List every text passed to tr() / N_() in the source, for translators.

    uv run python scripts/i18n_strings.py            # all texts
    uv run python scripts/i18n_strings.py --missing  # texts without English translation
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "etiknivo"


def texts(*, formatted: bool = False) -> dict[str, list[str]]:
    """{text: [file:line, ...]} for every literal tr()/N_() argument.

    With *formatted*, only texts that tr() fills with values; in the others
    braces are plain text (such as the {Field} examples)."""
    found: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            name = (node.func.id if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    else node.func.attr if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute) else None)
            if (name in ("tr", "N_") and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                    and (node.keywords or not formatted)):
                where = f"{path.relative_to(SRC.parent)}:{node.lineno}"
                found.setdefault(node.args[0].value, []).append(where)
    return found


def main() -> None:
    sys.path.insert(0, str(SRC.parent))
    from etiknivo.locale.en import EN

    for text, where in texts().items():
        if "--missing" in sys.argv and text in EN:
            continue
        print(f"{text!r}  # {where[0]}")


if __name__ == "__main__":
    main()
