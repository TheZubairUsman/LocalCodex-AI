from __future__ import annotations

import re
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


def duckduckgo_search(query: str) -> str:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=10) as response:
            html = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return f"Search failed: {exc}"

    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
    cleaned = []
    for snippet in snippets[:5]:
        text = re.sub(r"<[^>]+>", "", snippet).strip()
        if text:
            cleaned.append(text)
    return "\n".join(cleaned) if cleaned else "No search results."


def multi_search(query: str) -> str:
    return duckduckgo_search(query)
