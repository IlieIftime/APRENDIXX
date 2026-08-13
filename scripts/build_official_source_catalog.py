"""Build a reviewed metadata snapshot from official documentation sitemaps.

This script is an explicit release-time tool; the application never downloads
these pages at startup.  It stores only canonical URL, the exact HTML title and
the publisher metadata needed to audit the catalogue.  No body text is copied.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class Family:
    name: str
    sitemap: str
    quota: int
    area: str
    author: str
    catalog_kind: str = "sitemap"
    include: str = ""
    exclude: str = ""


FAMILIES = (
    Family("python", (
               "https://docs.python.org/3/reference/index.html|"
               "https://docs.python.org/3/tutorial/index.html|"
               "https://docs.python.org/3/howto/index.html"
           ), 35,
           "python", "Python Software Foundation", catalog_kind="index",
           include="/3/reference/|/3/tutorial/|/3/howto/", exclude="index.html"),
    Family("pytest", "https://docs.pytest.org/en/stable/contents.html", 25,
           "software-engineering", "pytest contributors", catalog_kind="index",
           include="/en/stable/how-to/|/en/stable/explanation/|/en/stable/reference/|/en/stable/getting-started",
           exclude="changelog|announce|contact"),
    Family("pypa", "https://packaging.python.org/en/latest/", 20,
           "software-engineering", "Python Packaging Authority", catalog_kind="index",
           include="/en/latest/tutorials/|/en/latest/guides/|/en/latest/discussions/|/en/latest/specifications/",
           exclude="contribute|news"),
    Family("nist-dads", "https://xlinux.nist.gov/dads/termsArea.html", 25,
           "classic-algorithms", "National Institute of Standards and Technology",
           catalog_kind="index", include="/dads/HTML/", exclude="index.html"),
    Family("linux", "https://docs.kernel.org/index.html", 25,
           "systems", "Linux kernel documentation contributors", catalog_kind="index",
           exclude="/_sources/|genindex.html|search.html|/index.html"),
    Family("docker", "https://docs.docker.com/sitemap.xml", 20,
           "systems", "Docker documentation team", include="/engine/"),
    Family("postgresql", "https://www.postgresql.org/sitemap.xml", 30,
           "databases", "PostgreSQL Global Development Group",
           include="/docs/current/"),
    Family("pandas", "https://pandas.pydata.org/docs/user_guide/index.html", 25,
           "data-practice", "pandas development team", catalog_kind="index",
           include="/docs/user_guide/", exclude="index.html"),
    Family("mongodb", "https://www.mongodb.com/docs/manual/contents/", 25,
           "databases", "MongoDB documentation team", catalog_kind="index",
           include="/docs/manual/crud/|/docs/manual/aggregation/|/docs/manual/data-modeling/|/docs/manual/core/|/docs/manual/reference/|/docs/manual/administration/"),
    Family("spark", "https://spark.apache.org/sitemap.xml", 20,
           "data-practice", "Apache Spark contributors", include="/docs/latest/",
           exclude="/api/|scaladoc|javadoc"),
    Family("pytorch", "https://pytorch.org/docs/stable/sitemap.xml", 30,
           "deep-learning", "PyTorch contributors", include="/docs/stable/",
           exclude="/generated/exportdb/"),
    Family("sklearn", "https://scikit-learn.org/stable/api/index.html", 30,
           "classical-ml", "scikit-learn developers", catalog_kind="index",
           include="/stable/modules/generated/"),
    Family("tensorflow", "https://www.tensorflow.org/api_docs/python/tf/all_symbols", 20,
           "deep-learning", "TensorFlow authors", catalog_kind="index",
           include="/api_docs/python/tf/"),
    Family("opencv", "https://docs.opencv.org/4.x/", 15,
           "computer-vision", "OpenCV contributors", catalog_kind="index",
           exclude="index.html"),
    Family("spacy", "https://spacy.io/api", 10,
           "natural-language", "Explosion", catalog_kind="index", include="/api/"),
    Family("mlflow", "https://mlflow.org/docs/latest/sitemap.xml", 15,
           "software-engineering", "MLflow contributors",
           include="/docs/latest/api_reference/|/docs/latest/genai/|/docs/latest/ml/|/docs/latest/model-registry/|/docs/latest/tracking/",
           exclude="blog|search|community"),
    Family("owasp", "https://cheatsheetseries.owasp.org/sitemap.xml", 45,
           "cybersecurity-app", "OWASP Cheat Sheet Series contributors",
           include="/cheatsheets/", exclude="/index.html|/Glossary.html"),
    Family("mitre-attack", "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json", 25,
           "cybersecurity-app", "MITRE ATT&CK", catalog_kind="stix"),
    Family("fastapi", "https://fastapi.tiangolo.com/sitemap.xml", 10,
           "web", "FastAPI contributors", include="/tutorial/|/advanced/|/how-to/"),
    Family("kubernetes", "https://kubernetes.io/en/sitemap.xml", 25,
           "systems", "Kubernetes contributors",
           include="/docs/concepts/|/docs/tasks/|/docs/reference/",
           exclude="/blog/|/releases/"),
    Family("w3c-wcag", "https://www.w3.org/WAI/WCAG22/Techniques/", 15,
           "responsible-ai", "World Wide Web Consortium", catalog_kind="index",
           include="/WAI/WCAG22/Techniques/aria/|/WAI/WCAG22/Techniques/css/|/WAI/WCAG22/Techniques/general/|/WAI/WCAG22/Techniques/html/|/WAI/WCAG22/Techniques/pdf/|/WAI/WCAG22/Techniques/scr/"),
    Family("nist-airc", "https://airc.nist.gov/sitemap.xml", 10,
           "responsible-ai", "National Institute of Standards and Technology",
           include="/airmf-resources/airmf/|/airmf-resources/playbook/"),
)
RESERVED_CANONICAL_URLS = frozenset({
    "https://docs.docker.com/get-started/",
    "https://fastapi.tiangolo.com/tutorial/",
    "https://www.postgresql.org/docs/current/",
    "https://docs.pytorch.org/docs/stable/autograd.html",
    "https://numpy.org/doc/stable/",
    "https://pandas.pydata.org/docs/",
    "https://scikit-learn.org/stable/user_guide.html",
    "https://docs.pytest.org/en/latest/getting-started.html",
})


def _request(url: str, *, timeout: float = 30.0) -> bytes:
    request = Request(url, headers={
        "User-Agent": "Aprendix-Official-Catalog-Builder/1.0",
        "Accept": "text/html,application/xml;q=0.9,*/*;q=0.1",
    })
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"unexpected HTTP status {response.status} for {url}")
        return response.read()


def _matches(patterns: str, value: str) -> bool:
    return any(pattern and pattern in value for pattern in patterns.split("|"))


def _sitemap_urls(url: str) -> set[str]:
    root = ET.fromstring(_request(url))
    locations = {
        str(node.text).strip()
        for node in root.iter()
        if node.tag.endswith("loc") and node.text
    }
    if root.tag.endswith("sitemapindex"):
        result: set[str] = set()
        with ThreadPoolExecutor(max_workers=12) as pool:
            for nested in pool.map(_sitemap_urls, sorted(locations)):
                result.update(nested)
        return result
    return locations


def _index_urls(url: str) -> set[str]:
    payload = _request(url).decode("utf-8", errors="strict")
    return {
        urldefrag(urljoin(url, html.unescape(target)))[0]
        for target in re.findall(r'href=["\']([^"\']+)', payload, re.IGNORECASE)
        if not target.startswith(("mailto:", "javascript:"))
    }


def _crawl_index_urls(url: str, *, depth: int = 1) -> set[str]:
    result = _index_urls(url)
    origin = urlsplit(url).netloc.casefold()
    frontier = {
        item for item in result
        if urlsplit(item).netloc.casefold() == origin
        and (item.rstrip("/").endswith("index.html") or item.endswith("/"))
    }
    for _ in range(depth):
        nested: set[str] = set()
        with ThreadPoolExecutor(max_workers=12) as pool:
            for links in pool.map(_index_urls, sorted(frontier)):
                nested.update(links)
        frontier = {
            item for item in nested - result
            if urlsplit(item).netloc.casefold() == origin
            and (item.rstrip("/").endswith("index.html") or item.endswith("/"))
        }
        result.update(nested)
    return result


def _stix_sources(family: Family) -> tuple[dict[str, object], ...]:
    payload = json.loads(_request(family.sitemap).decode("utf-8", errors="strict"))
    rows: list[dict[str, object]] = []
    for item in payload.get("objects", ()):
        if item.get("type") != "attack-pattern":
            continue
        if item.get("revoked") or item.get("x_mitre_deprecated"):
            continue
        reference = next((
            link for link in item.get("external_references", ())
            if link.get("source_name") == "mitre-attack" and link.get("url")
        ), None)
        if reference is None:
            continue
        rows.append({
            "family": family.name,
            "url": str(reference["url"]),
            "title": str(item["name"]),
            "area": family.area,
            "author": family.author,
            "sitemap_url": family.sitemap,
            "headings": (),
        })
    rows.sort(key=lambda row: (str(row["title"]).casefold(), str(row["url"])))
    return tuple(rows[:family.quota])


def _urls(family: Family) -> tuple[str, ...]:
    catalogs = family.sitemap.split("|")
    candidates: set[str] = set()
    for catalog in catalogs:
        candidates.update(
            _crawl_index_urls(catalog)
            if family.catalog_kind == "index"
            else _sitemap_urls(catalog)
        )
    source_host = urlsplit(catalogs[0]).netloc.casefold()
    accepted_hosts = {
        "pytorch.org": {"pytorch.org", "docs.pytorch.org"},
    }.get(source_host, {source_host})
    return tuple(sorted(
        url for url in candidates
        if urlsplit(url).scheme in {"http", "https"}
        and urlsplit(url).netloc.casefold() in accepted_hosts
        and (
            family.catalog_kind != "index"
            or family.name in {"tensorflow", "spacy", "w3c-wcag"}
            or urlsplit(url).path.endswith(("/", ".html"))
        )
        and (not family.include or _matches(family.include, url))
        and (not family.exclude or not _matches(family.exclude, url))
    ))


def _title(
    url: str, *, follow_redirect_page: bool = True,
) -> tuple[str, str, tuple[str, ...]] | None:
    try:
        payload = _request(url, timeout=20.0).decode("utf-8", errors="replace")
    except (OSError, TimeoutError, RuntimeError):
        return None
    match = re.search(r"<title[^>]*>(.*?)</title>", payload, re.IGNORECASE | re.DOTALL)
    if match is None:
        return None
    title = html.unescape(re.sub(r"<[^>]+>", " ", match.group(1)))
    title = " ".join(title.split())
    if title.casefold().startswith("redirecting") and follow_redirect_page:
        redirect = re.search(
            r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)',
            payload, re.IGNORECASE,
        )
        if redirect:
            return _title(
                urljoin(url, html.unescape(redirect.group(1))),
                follow_redirect_page=False,
            )
    if (len(title) < 3 or title.startswith("— ")
            or title.casefold().startswith(("redirecting", "page not found", "404"))):
        return None
    canonical = re.search(
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)',
        payload, re.IGNORECASE,
    )
    if canonical is None:
        canonical = re.search(
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']canonical["\']',
            payload, re.IGNORECASE,
        )
    canonical_url = html.unescape(canonical.group(1)).strip() if canonical else url
    if canonical_url.startswith("/"):
        parts = urlsplit(url)
        canonical_url = f"{parts.scheme}://{parts.netloc}{canonical_url}"
    # MongoDB's public manual currently emits an internal staging host in its
    # canonical tag.  That host is neither public provenance nor a stable
    # reader URL, so retain the exact public URL selected from the official
    # contents index.
    if urlsplit(canonical_url).netloc.casefold().endswith(".corp.mongodb.com"):
        canonical_url = url
    if "/404." in urlsplit(canonical_url).path.casefold():
        return None
    headings: list[str] = []
    for value in re.findall(r"<h[12][^>]*>(.*?)</h[12]>", payload, re.IGNORECASE | re.DOTALL):
        cleaned = html.unescape(re.sub(r"<[^>]+>", " ", value))
        cleaned = " ".join(cleaned.split()).strip("#¶ ")
        if 3 <= len(cleaned) <= 180 and cleaned not in headings:
            headings.append(cleaned)
        if len(headings) >= 6:
            break
    return canonical_url, title, tuple(headings)


def build() -> dict[str, object]:
    records: list[dict[str, str]] = []
    for family in FAMILIES:
        if family.catalog_kind == "stix":
            records.extend(_stix_sources(family))
            continue
        candidates = _urls(family)
        with ThreadPoolExecutor(max_workers=16) as pool:
            titles = pool.map(_title, candidates[: max(family.quota * 3, family.quota + 80)])
            for source_url, result in zip(candidates, titles):
                if result is None:
                    continue
                canonical_url, title, headings = result
                if canonical_url.rstrip("/") in {
                    item.rstrip("/") for item in RESERVED_CANONICAL_URLS
                }:
                    continue
                records.append({
                    "family": family.name,
                    "url": canonical_url,
                    "title": title,
                    "area": family.area,
                    "author": family.author,
                    "sitemap_url": family.sitemap,
                    "headings": headings,
                })
                if sum(item["family"] == family.name for item in records) >= family.quota:
                    break
        family_count = sum(item["family"] == family.name for item in records)
        if family_count != family.quota:
            raise RuntimeError(
                f"{family.name}: expected {family.quota} verified pages, got {family_count}"
            )
    canonical_urls = [item["url"] for item in records]
    if len(canonical_urls) != len(set(canonical_urls)):
        raise RuntimeError("official source snapshot contains duplicate canonical URLs")
    return {
        "generator": "scripts/build_official_source_catalog.py",
        "policy": "official-sitemap-and-html-title-metadata-only",
        "sources": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path,
        default=Path("src/aprendix/application/official_source_catalog.json"),
    )
    args = parser.parse_args()
    payload = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output), "sources": len(payload["sources"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
