"""Tra web cho Peto Agent bản desktop: một lần gọi Grok bắt buộc tìm web, trả kết quả theo dạng API tìm kiếm của DeepSeek.

Bản desktop (bản fork DeepSeek Harness) có công cụ web_search lấy kết quả từ một "nhà cung cấp tìm kiếm"; nhà cung cấp
Peto gọi cổng ``POST /api/agent/v1/search``, cổng gọi hàm này. Kết quả theo đúng dạng API tìm kiếm của DeepSeek
(``results``: url, title, snippet, summary, date), nên thẻ tìm kiếm và đoạn chữ model đọc giống hệt khi dùng DeepSeek.

Nguồn chỉ lấy từ chính lượt tìm của xAI (``action.sources`` và trích dẫn ``url_citation``). Tóm tắt và ngày đăng do Grok
viết từ trang đã tìm; URL nào Grok viết ra mà lượt tìm không trả về thì bị bỏ.
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlsplit, urlunsplit

from core.config import AGENT_MODEL, AI_PROVIDER
from shared.web_search import normalize_sources

from .agent import _clip, _dump, xai_client
from .base import ProviderError

logger = logging.getLogger("peto_web.agent")

MAX_SUMMARY_CHARS = 600
MAX_SNIPPET_CHARS = 200
MAX_DATE_CHARS = 40
MAX_OUTPUT_TOKENS = 4000


def search_prompt(count: int) -> str:
    """Chỉ dẫn của lượt tìm: model chỉ được chọn và tóm tắt trang đã tìm thấy, trả JSON."""
    return f"""You are the web search backend of a coding agent. Search the web for the query you are given, then
reply with JSON only, without prose or a code fence:
{{"results": [{{"url": "...", "title": "...", "summary": "...", "date": null}}]}}

- List up to {count} pages this search actually returned, most relevant first. Never list a URL the search did not return.
- title: the page's own title.
- summary: one to three sentences on what the page says that is relevant to the query, in the page's language. Only
  what the page says; no opinions or advice.
- date: the page's publication or last-updated date as shown in the search result (prefer YYYY-MM-DD), else null.
- When nothing relevant turns up, reply {{"results": []}}."""


def _key(url: str) -> str:
    """So khớp URL bỏ qua phần #… và dấu / cuối, vì model hay viết lại URL như vậy."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def _text(value: object, limit: int) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _snippet(summary: str) -> str:
    if len(summary) <= MAX_SNIPPET_CHARS:
        return summary
    return summary[:MAX_SNIPPET_CHARS].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def _found(output: list[dict]) -> tuple[bool, list[dict]]:
    """Lượt trả lời có thật sự tìm web không, và các trang lượt tìm trả về (kể cả trang được trích dẫn)."""
    searched = False
    candidates: list[dict] = []
    for item in output:
        if item.get("type") == "web_search_call":
            searched = True
            action = item.get("action") if isinstance(item.get("action"), dict) else {}
            candidates.extend(source for source in action.get("sources") or [] if isinstance(source, dict))
        elif item.get("type") == "message":
            for part in item.get("content") or []:
                for note in part.get("annotations") or [] if isinstance(part, dict) else []:
                    if isinstance(note, dict) and note.get("type") == "url_citation":
                        candidates.append({"url": note.get("url"), "title": note.get("title")})
    return searched, normalize_sources(candidates)


def _answer(output: list[dict]) -> list[dict]:
    text = "".join(part.get("text", "") for item in output if item.get("type") == "message"
                   for part in item.get("content") or [] if isinstance(part, dict) and part.get("type") == "output_text")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return []
    try:
        parsed = json.loads(text[start:end + 1])
    except ValueError:
        return []
    rows = parsed.get("results") if isinstance(parsed, dict) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def results_from_output(output: list[dict], count: int) -> list[dict] | None:
    """Kết quả dạng DeepSeek từ đầu ra của lượt tìm; None khi lượt đó không tìm web."""
    searched, sources = _found(output)
    if not searched:
        return None
    allowed = {_key(source["url"]): source for source in sources}
    results: list[dict] = []
    seen: set[str] = set()
    for row in _answer(output):
        url = row.get("url")
        key = _key(url) if isinstance(url, str) else ""
        source = allowed.get(key)
        if source is None or key in seen:
            continue
        seen.add(key)
        summary = _text(row.get("summary"), MAX_SUMMARY_CHARS)
        date = _text(row.get("date"), MAX_DATE_CHARS)
        host = urlsplit(source["url"]).hostname
        title = source["title"] if source["title"] != host else _text(row.get("title"), 200) or source["title"]
        results.append({"url": source["url"], "title": title, "snippet": _snippet(summary), "summary": summary,
                        "date": date or None})
    # Trang lượt tìm trả về mà model không nêu vẫn là kết quả thật, chỉ thiếu tóm tắt.
    for key, source in allowed.items():
        if key not in seen:
            results.append({"url": source["url"], "title": source["title"], "snippet": "", "date": None})
    return results[:count]


def _input(query: str, question: str | None) -> list[dict]:
    text = f"Query: {query}"
    if question:
        text += f"\nThe user's question that led to this search, for relevance only: {question}"
    return [{"role": "user", "content": [{"type": "input_text", "text": text}]}]


def _mock_output(query: str, count: int) -> list[dict]:
    """Lượt tìm giả lập đi qua đúng bộ đọc kết quả, để chạy mock và test giống thật."""
    if "__error__" in query:
        raise ProviderError("Tìm web giả lập gặp lỗi.", retryable=True)
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:40] or "ket-qua"
    sources = [{"url": f"https://example.com/{slug}", "title": f"{query} — Example"},
               {"url": f"https://example.org/{slug}", "title": f"Tìm hiểu {query}"}]
    answer = {"results": [{"url": sources[0]["url"], "title": sources[0]["title"],
                           "summary": f"Trang mẫu nói về {query}.", "date": "2026-11-01"},
                          {"url": "https://invented.example/khong-co", "title": "Không có trong lượt tìm",
                           "summary": "Model tự viết.", "date": None}]}
    return [{"type": "web_search_call", "status": "completed", "action": {"type": "search", "query": query, "sources": sources}},
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer, ensure_ascii=False)}]}]


async def _xai_output(instructions: str, items: list[dict]) -> tuple[list[dict], dict]:
    from openai import APIConnectionError, APIStatusError, AuthenticationError, RateLimitError

    client = await xai_client()
    try:
        response = await client.responses.create(
            model=AGENT_MODEL, instructions=instructions, input=items,
            # Bắt buộc gọi công cụ: lượt này chỉ để tìm web, không được trả lời bằng trí nhớ của model.
            tools=[{"type": "web_search"}], tool_choice="required",
            include=["web_search_call.action.sources"], reasoning={"effort": "low"},
            max_output_tokens=MAX_OUTPUT_TOKENS, store=False,
        )
    except AuthenticationError as err:
        logger.warning("xAI từ chối xác thực khi tra web cho agent (HTTP %s)", err.status_code)
        raise ProviderError("Kết nối AI của Peto đã hết hạn. Người quản trị cần đăng nhập lại.") from err
    except RateLimitError as err:
        logger.warning("xAI giới hạn lượt khi tra web cho agent: %s", _clip(err.message))
        raise ProviderError("Dịch vụ AI đang nhận nhiều yêu cầu quá. Đợi chút rồi thử lại nhé.", retryable=True) from err
    except APIConnectionError as err:
        logger.warning("Không kết nối được xAI khi tra web cho agent: %s", _clip(err.message))
        raise ProviderError("Máy chủ Peto chưa kết nối được dịch vụ AI. Thử lại sau chút nhé.", retryable=True) from err
    except APIStatusError as err:
        logger.warning("xAI trả lỗi HTTP %s khi tra web cho agent: %s", err.status_code, _clip(err.message))
        raise ProviderError("Dịch vụ AI chưa tra web được lần này. Thử lại nhé.", retryable=err.status_code >= 500) from err
    if getattr(response, "status", "completed") != "completed":
        logger.warning("xAI kết thúc lượt tra web với trạng thái %s", _clip(getattr(response, "status", "")))
        raise ProviderError("Lượt tra web chưa xong. Thử lại nhé.", retryable=True)
    usage = getattr(response, "usage", None)
    ticks = getattr(usage, "cost_in_usd_ticks", None)
    return [_dump(item) for item in response.output or []], {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        **({"cost_ticks": ticks} if isinstance(ticks, int) and not isinstance(ticks, bool) else {}),
    }


async def web_lookup(query: str, count: int, question: str | None = None) -> tuple[list[dict], dict]:
    """Tìm ``query`` bằng Grok; trả (kết quả dạng DeepSeek, usage). ProviderError khi không tìm được."""
    if AI_PROVIDER == "mock":
        output = _mock_output(query, count)
        usage = {"input_tokens": len(query) // 4 + 1, "output_tokens": 40}
    else:
        output, usage = await _xai_output(search_prompt(count), _input(query, question))
    results = results_from_output(output, count)
    if results is None:
        logger.warning("Lượt tra web cho agent kết thúc mà không gọi công cụ tìm web")
        raise ProviderError("Peto chưa tìm được trên web lần này. Thử lại nhé.", retryable=True)
    return results, usage
