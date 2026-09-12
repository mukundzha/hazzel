import concurrent.futures
import html
import ipaddress
import re
import urllib.parse
import urllib.request

from .. import tool_cache

MAX_BYTES = 1_500_000
DEFAULT_MAX_CHARS = 2000
MAX_LINES = 400
TIMEOUT = 15

STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "have", "has", "had",
    "are", "was", "were", "been", "will", "would", "can", "could", "should",
    "about", "into", "over", "after", "before", "between", "through", "more",
    "most", "other", "some", "such", "only", "also", "than", "then", "them",
    "they", "their", "there", "these", "those", "when", "where", "which",
    "while", "your", "you", "our", "all", "any", "each", "her", "him", "his",
    "its", "may", "new", "not", "now", "one", "out", "per", "use", "used",
    "using", "via", "view", "show", "page", "click", "here", "learn",
})

CHROME_PATTERNS = (
    "skip to content", "sign in", "sign up", "log in", "log out", "subscribe",
    "newsletter", "cookie", "privacy policy", "terms of service",
    "all rights reserved", "follow us", "share this", "advertisement",
    "appearance settings", "dismiss alert",
)


def _blocked_host(hostname):
    host = (hostname or "").lower().strip("[]")
    if not host:
        return True
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
        return not ip.is_global
    except ValueError:
        return False


def _html_to_text(page):
    text = re.sub(r"(?is)<(script|style|noscript|template)[^>]*>.*?</\1>", " ", page)
    text = re.sub(r"(?is)<(nav|header|footer|aside|form)[^>]*>.*?</\1>", " ", text)
    main = re.search(r"(?is)<(main|article)[^>]*>(.*)</\1>", text)
    if main:
        text = main.group(2)
    text = re.sub(r"(?i)<\s*br[^>]*>", "\n", text)
    text = re.sub(r"(?i)</\s*(p|div|h[1-6]|li|tr|section|article)[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = []
    seen = set()
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line and line not in seen:
            seen.add(line)
            lines.append(line)
            if len(lines) >= MAX_LINES:
                break
    return "\n".join(lines)


def _keywords(text):
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOPWORDS]


def _condense(lines, query, budget):
    cleaned = [line for line in lines if not any(p in line.lower() for p in CHROME_PATTERNS)]
    if not cleaned:
        cleaned = lines
    query_words = set(_keywords(query or ""))
    freq = {}
    keyed = []
    for line in cleaned:
        words = _keywords(line)
        keyed.append(words)
        for w in words:
            freq[w] = freq.get(w, 0) + 1
    scored = []
    for i, (line, words) in enumerate(zip(cleaned, keyed)):
        if not words:
            continue
        score = sum(1.0 / freq[w] for w in words) / (len(words) ** 0.5)
        score += 10.0 * len(set(words) & query_words)
        scored.append((score, i))
    scored.sort(key=lambda s: (-s[0], s[1]))
    picked = set()
    used = 0
    if cleaned:
        head = cleaned[0][:budget]
        picked.add(0)
        used = len(head)
        cleaned = [head] + cleaned[1:]
    for _, i in scored:
        if i in picked:
            continue
        if used + len(cleaned[i]) + 1 > budget:
            continue
        picked.add(i)
        used += len(cleaned[i]) + 1
    return "\n".join(cleaned[i] for i in sorted(picked))


MAX_URLS = 5


def _fetch_uncached(url, max_chars, query):
    url = url.strip().strip("'\"<>")
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError as error:
        return f"Unsupported URL: {error}."
    if parsed.scheme not in ("http", "https"):
        return f"Unsupported URL scheme: {parsed.scheme or '(none)'}. Use http(s):// URLs."
    if not parsed.netloc or _blocked_host(parsed.hostname):
        return f"Blocked URL: {url}. Only public http(s) hosts are allowed."

    try:
        max_chars = int(max_chars)
    except (TypeError, ValueError):
        max_chars = DEFAULT_MAX_CHARS
    max_chars = max(500, min(max_chars, 20000))

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Hazzel/1.1.0",
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            content_type = ""
            try:
                content_type = str(response.headers.get("Content-Type", "") or "")
            except Exception:
                content_type = ""
            raw = response.read(MAX_BYTES + 1)
    except Exception as error:
        return f"Tool error: cannot fetch URL ({error}). Check the URL and try again."

    truncated = len(raw) > MAX_BYTES
    raw = raw[:MAX_BYTES]
    text = raw.decode("utf-8", errors="replace")
    if "html" in content_type.lower() or "<html" in text[:2000].lower():
        text = _html_to_text(text)
    else:
        text = text.strip()
    total = len(text)
    if total == 0:
        return f"Fetched {url} but found no readable text."
    if total <= max_chars and not truncated:
        return f"Fetched {url} ({total} chars):\n{text}"
    body = _condense(text.splitlines(), query, max_chars)
    out = [f"Fetched {url} ({total} chars):", body]
    out.append(f"[Condensed: showing {len(body)} most relevant of {total} chars]")
    return "\n".join(out)


def _fetch_one(url, max_chars, query):
    try:
        budget = int(max_chars)
    except (TypeError, ValueError):
        budget = DEFAULT_MAX_CHARS
    budget = max(500, min(budget, 20000))
    key = (str(url).strip(), budget, str(query or ""))
    if tool_cache.caching_enabled():
        hit = tool_cache.FETCH.get(key)
        if hit is not None:
            return hit
    result = _fetch_uncached(url, budget, query)
    if tool_cache.caching_enabled() and result.startswith("Fetched "):
        tool_cache.FETCH.set(key, result)
    return result


def fetch_url(url="", max_chars=DEFAULT_MAX_CHARS, query="", urls=None):
    targets = []
    if isinstance(url, list):
        targets.extend(url)
    elif isinstance(url, str) and url.strip():
        targets.append(url)
    if isinstance(urls, list):
        targets.extend(urls)
    elif isinstance(urls, str) and urls.strip():
        targets.append(urls)
    targets = [t for t in targets if isinstance(t, str) and t.strip()]
    if not targets:
        return "URL is required — usage: fetch_url(url, max_chars=5000)."
    if len(targets) == 1:
        return _fetch_one(targets[0], max_chars, query)
    try:
        budget = int(max_chars)
    except (TypeError, ValueError):
        budget = DEFAULT_MAX_CHARS
    budget = max(500, min(budget, 20000))
    picked = targets[:MAX_URLS]
    share = max(500, budget // len(picked))
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(picked), thread_name_prefix="hazzel-fetch") as pool:
        bodies = list(pool.map(lambda t: _fetch_one(t, share, query), picked))
    sections = []
    for i, (target, body) in enumerate(zip(picked, bodies), 1):
        sections.append(f"=== [{i}/{len(picked)}] {target.strip()} ===\n{body}")
    if len(targets) > MAX_URLS:
        sections.append(f"[…{len(targets) - MAX_URLS} more URLs skipped, max {MAX_URLS} per call…]")
    return "\n\n".join(sections)
