from __future__ import annotations

import re
from typing import Any


_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def render_template(text: str, variables: dict[str, Any] | None = None) -> str:
    """Подставляет {{name}} и другие переменные в текст сообщения."""
    if variables is None:
        return text

    def replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        value = variables.get(key)
        if value is None:
            return ""
        return str(value)

    return _VAR_RE.sub(replacer, text)
