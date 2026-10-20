"""Load MedlinePlus content into CareChat's knowledge base.

Two sources are supported:

  --topics-xml FILE_OR_URL   The MedlinePlus health topics XML file
                             (download link at https://medlineplus.gov/xml.html).
  --urls FILE                A text file with one MedlinePlus page URL per line,
                             for example lab test pages under
                             https://medlineplus.gov/lab-tests/.

Check MedlinePlus's reuse terms (https://medlineplus.gov/about/using/usingcontent/)
before indexing. Content licensed from third parties must not be copied.

Run from the backend folder:
  python -m scripts.ingest_medlineplus --topics-xml mplus_topics.xml
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from carechat.config import settings  # noqa: E402
from carechat.knowledge import KnowledgeBase  # noqa: E402

ALLOWED_HOST = "medlineplus.gov"


class _TextExtractor(HTMLParser):
    """Collects readable text, skipping scripts, styles and page chrome."""

    SKIP = {"script", "style", "nav", "header", "footer", "noscript", "form"}
    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "div", "section", "br", "tr"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK and not self._skip_depth:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        paragraphs = [" ".join(p.split()) for p in raw.split("\n\n")]
        return "\n\n".join(p for p in paragraphs if len(p) > 30)


def html_to_text(html: str) -> tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(html)
    title = " ".join(parser.title.split()).replace(": MedlinePlus Medical Test", "").replace(": MedlinePlus", "")
    return title, parser.text()


def _read(source: str) -> bytes:
    if source.startswith("http"):
        response = httpx.get(source, follow_redirects=True, timeout=60)
        response.raise_for_status()
        return response.content
    return Path(source).read_bytes()


def ingest_topics_xml(kb: KnowledgeBase, source: str) -> int:
    root = ET.fromstring(_read(source))
    count = 0
    for topic in root.iter("health-topic"):
        if topic.get("language") != "English":
            continue
        summary = topic.findtext("full-summary") or ""
        _, text = html_to_text(summary)
        if text:
            kb.add_document(topic.get("title", ""), topic.get("url", ""), text)
            count += 1
    return count


def ingest_urls(kb: KnowledgeBase, url_file: str) -> int:
    count = 0
    for line in Path(url_file).read_text().splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        if httpx.URL(url).host != ALLOWED_HOST:
            print(f"skip (not {ALLOWED_HOST}): {url}")
            continue
        try:
            title, text = html_to_text(_read(url).decode("utf-8", errors="replace"))
        except httpx.HTTPError as exc:
            print(f"failed: {url} ({exc})")
            continue
        if text:
            kb.add_document(title or url, url, text)
            count += 1
            print(f"indexed: {title}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topics-xml")
    parser.add_argument("--urls")
    parser.add_argument("--db", default=settings.db_path)
    args = parser.parse_args()
    if not args.topics_xml and not args.urls:
        parser.error("give --topics-xml or --urls")
    kb = KnowledgeBase(args.db)
    total = 0
    if args.topics_xml:
        total += ingest_topics_xml(kb, args.topics_xml)
    if args.urls:
        total += ingest_urls(kb, args.urls)
    print(f"Indexed {total} pages. Knowledge base now holds {kb.count()} passages.")


if __name__ == "__main__":
    main()
