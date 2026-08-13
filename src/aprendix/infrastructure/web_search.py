"""Bounded HTTPS-only web fallback using DuckDuckGo's static HTML endpoint."""

from __future__ import annotations

import html
import urllib.parse
import urllib.request
from uuid import NAMESPACE_URL, uuid5

from aprendix.application.contracts import (
    Complexity,
    ContentKind,
    EvidenceOrigin,
    SearchEvidenceDTO,
)
from aprendix.application.text_normalization import TextNormalizationService


class SafeDuckDuckGoSearch:
    endpoint = "https://html.duckduckgo.com/html/"

    def __init__(self, *, timeout_seconds: float = 6.0, max_bytes: int = 1_000_000) -> None:
        if not 0.5 <= timeout_seconds <= 20:
            raise ValueError("timeout must be between 0.5 and 20 seconds")
        if not 10_000 <= max_bytes <= 2_000_000:
            raise ValueError("max_bytes is outside the safe range")
        self._timeout = timeout_seconds
        self._max_bytes = max_bytes
        self._normalizer = TextNormalizationService()

    def search(self, query: str, *, max_results: int) -> tuple[SearchEvidenceDTO, ...]:
        query = " ".join(query.split())[:500]
        if not query:
            return ()
        payload = urllib.parse.urlencode({"q": query}).encode("ascii", errors="ignore")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={
                "User-Agent": "Aprendix/1.0 local-learning-search",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            final = urllib.parse.urlparse(response.geturl())
            if final.scheme != "https" or final.hostname not in {"duckduckgo.com", "html.duckduckgo.com"}:
                raise ValueError("unexpected web-search redirect")
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise ValueError("web search returned a non-HTML response")
            response_headers = dict(response.headers.items())
            raw = response.read(self._max_bytes + 1)
            if len(raw) > self._max_bytes:
                raise ValueError("web search response exceeded the size limit")
        document = self._normalizer.decode_web(
            raw,
            headers=response_headers,
            content_type=response_headers.get("Content-Type", ""),
        ).text
        return self._parse(document, max_results=max_results)

    @staticmethod
    def _parse(document: str, *, max_results: int) -> tuple[SearchEvidenceDTO, ...]:
        try:
            from bs4 import BeautifulSoup
        except ImportError as exc:
            raise RuntimeError('web fallback requires the "rag" extra') from exc
        soup = BeautifulSoup(document, "html.parser")
        results: list[SearchEvidenceDTO] = []
        for result in soup.select(".result"):
            link = result.select_one(".result__a")
            snippet = result.select_one(".result__snippet")
            if link is None or snippet is None:
                continue
            href = str(link.get("href") or "")
            parsed = urllib.parse.urlparse(href)
            if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
                target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
            else:
                target = href
            target_parsed = urllib.parse.urlparse(target)
            if target_parsed.scheme != "https" or not target_parsed.hostname:
                continue
            title = " ".join(link.get_text(" ", strip=True).split())[:500]
            excerpt = " ".join(snippet.get_text(" ", strip=True).split())[:4_000]
            if not title or not excerpt:
                continue
            result_id = uuid5(NAMESPACE_URL, f"aprendix:web:{target}")
            results.append(
                SearchEvidenceDTO(
                    id=str(result_id), origin=EvidenceOrigin.WEB,
                    title=html.unescape(title), excerpt=html.unescape(excerpt),
                    source=target[:2_000], relevance=max(0.2, 0.55 - len(results) * 0.04),
                    content_type=ContentKind.THEORY,
                    complexity=Complexity.INTERMEDIATE,
                )
            )
            if len(results) >= max(1, min(max_results, 20)):
                break
        return tuple(results)
