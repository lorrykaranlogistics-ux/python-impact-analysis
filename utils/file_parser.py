from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List


def find_endpoints_in_directory(directory: Path, endpoints: Iterable[str]) -> Dict[str, List[Path]]:
    matches: Dict[str, List[Path]] = {}
    patterns = [re.compile(re.escape(endpoint)) for endpoint in endpoints]
    for path in directory.rglob("*"):
        if not path.is_file() or path.suffix in {".pyc", ".lock"}:
            continue
        if any(part in {"node_modules", ".git", "venv"} for part in path.parts):
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:  # pragma: no cover - ignore unreadable
            continue
        for endpoint, pattern in zip(endpoints, patterns):
            if pattern.search(text):
                matches.setdefault(endpoint, []).append(path)
    return matches
