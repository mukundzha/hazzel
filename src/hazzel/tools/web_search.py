import html
import re
import urllib.parse
import urllib.request

SEARCH_URL = "https://html.duckduckgo.com/html/"
TIMEOUT = 15
MAX_RESULTS = 10


def _clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return html.unescape(re.sub(r"\s+", " ", text).strip())


def _real_url(href):
    href = html.unescape((href or "").strip())
    if not href:
        return ""
    try:
        parsed = urllib.parse.urlparse(href)
    except ValueError:
        return ""
    if "duckduckgo.com" in (parsed.hostname or ""):
        try:
            qs = urllib.parse.parse_qs(parsed.query)
        except ValueError:
            return href
        if "uddg" in qs and qs["uddg"]:
            return qs["uddg"][0]
    return href


def web_search(query, count=5):
    if not query or not isinstance(query, str) or not query.strip():
        return "Search query is required — usage: web_search(query, count=5)."
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 5
    count = max(1, min(count, MAX_RESULTS))
    body = urllib.parse.urlencode({"q": query.strip()}).encode("utf-8")
    request = urllib.request.Request(
        SEARCH_URL,
        data=body,
        headers={
            "User-Agent": "Hazzel/1.3.3",
            "Accept": "text/html,*/*",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            page = response.read(500_000).decode("utf-8", errors="replace")
    except Exception as error:
        return f"Tool error: web search failed ({error}). Try again or fetch a known URL directly."
    links = re.findall(r'(?is)<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page)
    snippets = re.findall(r'(?is)<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', page)
    if not snippets:
        snippets = re.findall(r'(?is)<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', page)
    results = []
    seen = set()
    for i, (href, title) in enumerate(links):
        url = _real_url(href)
        if not url or url in seen:
            continue
        if not url.startswith(("http://", "https://")):
            continue
        seen.add(url)
        snippet = _clean(snippets[i]) if i < len(snippets) else ""
        results.append((_clean(title) or url, url, snippet))
        if len(results) >= count:
            break
    if not results:
        return f"No results found for: {query.strip()}"
    lines = []
    for i, (title, url, snippet) in enumerate(results, 1):
        lines.append(f"{i}. {title}\n   {url}")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)
