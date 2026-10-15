"""Listing-page discovery: a subject or topic page -> the video pages under it.

``download.py --crawl https://zanza.tv/tortenelem`` stages every video that page
leads to. This module only *finds* those pages; staging them is the ordinary
batch path (:func:`msp.pipeline.ingest_crawl`), so duplicate protection, subject
detection, quality and transcription behave exactly as for a ``urls.txt``.

What the crawler does, and deliberately nothing more:

* it stays on the start page's host and below its path - ``/tortenelem``
  reaches ``/tortenelem/az-okori-hellasz/...`` but never ``/irodalom`` - and
  follows at most ``crawl.max_depth`` links;
* it reads robots.txt first, never fetches a page robots.txt disallows, and
  waits between requests: ``crawl.delay_seconds`` or the site's own
  ``Crawl-delay``, whichever is longer;
* it names itself honestly (``crawl.user_agent``) and sends no cookie and no
  credential. A page behind a login is therefore not found: a redirect that
  leaves the start page's scope is dropped, never followed;
* a page is a video page when its HTML matches ``crawl.embed_patterns`` (an
  embedded player). Video pages are leaves - their links are not followed.

Nothing here is site-specific; patterns and limits live in config/config.yaml.
"""

from __future__ import annotations

import logging
import re
import ssl
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Callable
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from .config import Config
from .downloader import CERTIFICATE_HINT
from .errors import CertificateError, CrawlError, CrawlLimitError, NetworkError
from .logging_setup import get_logger, info_event, warn_event

#: Larger responses are cut off; no listing page comes near this.
MAX_PAGE_BYTES = 5 * 1024 * 1024

#: Links that are obviously files, not pages, are never fetched.
SKIPPED_EXTENSIONS = frozenset({
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".zip", ".rar",
    ".mp3", ".mp4", ".m4a", ".webm", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
})


# ---------------------------------------------------------------------------
# fetching
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Page:
    """One answered request. ``url`` is where it ended up after redirects."""

    url: str
    status: int
    content_type: str = ""
    text: str = ""

    @property
    def is_html(self) -> bool:
        return 200 <= self.status < 300 and "html" in self.content_type.lower()


Fetcher = Callable[[str], Page]


def _ssl_context() -> ssl.SSLContext:
    """certifi's CA bundle when available - python.org macOS builds ship none."""
    try:
        import certifi
    except ImportError:  # pragma: no cover - certifi is a project dependency
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


class HttpFetcher:
    """Plain GET: honest User-Agent, TLS verified, no cookies, no credentials."""

    def __init__(self, config: Config) -> None:
        self._user_agent = config.crawl.user_agent
        self._timeout = config.download.socket_timeout
        self._context = _ssl_context()

    def __call__(self, url: str) -> Page:
        request = urllib.request.Request(url, headers={
            "User-Agent": self._user_agent,
            "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.8",
        })
        try:
            with urllib.request.urlopen(request, timeout=self._timeout, context=self._context) as response:
                body = response.read(MAX_PAGE_BYTES)
                charset = response.headers.get_content_charset() or "utf-8"
                try:
                    text = body.decode(charset, errors="replace")
                except LookupError:
                    text = body.decode("utf-8", errors="replace")
                return Page(response.geturl(), response.status,
                            response.headers.get("Content-Type", ""), text)
        except urllib.error.HTTPError as exc:
            exc.close()
            return Page(exc.geturl() or url, exc.code)
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                raise CertificateError(
                    f"TLS certificate verification failed for {url}: {exc.reason}",
                    hint=CERTIFICATE_HINT,
                ) from exc
            raise NetworkError(f"Cannot reach {url}: {exc.reason}") from exc
        except OSError as exc:  # timeouts, connection resets
            raise NetworkError(f"Cannot reach {url}: {exc}") from exc


def create_fetcher(config: Config) -> Fetcher:
    return HttpFetcher(config)


# ---------------------------------------------------------------------------
# URLs and links
# ---------------------------------------------------------------------------

def normalize_url(url: str) -> str | None:
    """Canonical form used for de-duplication, or None for a non-http(s) link.

    Lower-case scheme and host, no fragment, no trailing slash, no default port.
    The query is kept: on some sites it is what tells two pages apart.
    """
    try:
        parts = urlsplit(str(url).strip())
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not parts.hostname:
        return None
    netloc = parts.hostname.lower()
    if port and port != {"http": 80, "https": 443}[scheme]:
        netloc += f":{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def _bare_host(host: str) -> str:
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


@dataclass(frozen=True)
class Scope:
    """Same host (``www.`` ignored) and at or below the start page's path."""

    host: str
    prefix: str  # "" means the whole site

    @classmethod
    def of(cls, start_url: str) -> "Scope":
        parts = urlsplit(start_url)
        path = (parts.path or "/").rstrip("/")
        return cls(_bare_host(parts.hostname or ""), path)

    def contains(self, url: str) -> bool:
        parts = urlsplit(url)
        if _bare_host(parts.hostname or "") != self.host:
            return False
        path = parts.path or "/"
        return not self.prefix or path == self.prefix or path.startswith(self.prefix + "/")


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value:
                self.hrefs.append(value.strip())


def _link_pairs(html: str, page_url: str) -> list[tuple[str, str]]:
    """``(normalised, absolute as written)`` for every ``<a href>``, in page order, de-duplicated on the normalised form.

    The as-written form keeps a trailing slash: it is the base its own relative links resolve against
    (``0/`` on ``/x/weeks/`` is ``/x/weeks/0/``, on the normalised ``/x/weeks`` it would be ``/x/0/``).
    """
    parser = _LinkParser()
    parser.feed(html)
    parser.close()
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href in parser.hrefs:
        raw = urljoin(page_url, href).split("#", 1)[0]
        absolute = normalize_url(raw)
        if absolute and absolute not in seen:
            seen.add(absolute)
            links.append((absolute, raw))
    return links


def extract_links(html: str, page_url: str) -> list[str]:
    """Every ``<a href>`` of a page as normalised absolute URLs, in page order."""
    return [absolute for absolute, _ in _link_pairs(html, page_url)]


def _is_file_link(url: str) -> bool:
    return PurePosixPath(urlsplit(url).path).suffix.lower() in SKIPPED_EXTENSIONS


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

def _load_robots(start_url: str, fetch: Fetcher) -> RobotFileParser:
    """Same semantics as RobotFileParser.read(), but through our fetcher."""
    parts = urlsplit(start_url)
    robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    parser = RobotFileParser(robots_url)
    page = fetch(robots_url)
    if page.status in (401, 403):
        parser.disallow_all = True
    elif 200 <= page.status < 300:
        parser.parse(page.text.splitlines())
    else:
        parser.allow_all = True
    return parser


# ---------------------------------------------------------------------------
# the walk (discovery) and the video crawl (one consumer of it)
# ---------------------------------------------------------------------------

@dataclass
class CrawlResult:
    start_url: str
    delay_seconds: float
    video_urls: list[str] = field(default_factory=list)
    pages_fetched: int = 0
    blocked_by_robots: int = 0
    unreadable_pages: int = 0


@dataclass(frozen=True)
class Decision:
    """What the consumer of :func:`walk` wants done with one fetched page.

    ``collect``: hand the page to ``on_page`` (a video page, a tutorial page ...).
    ``follow``: queue its in-scope links (only while below ``crawl.max_depth``).
    """

    collect: bool
    follow: bool


Classifier = Callable[[str, Page], Decision]


def walk(
    start_url: str,
    *,
    config: Config,
    classify: Classifier,
    on_page: Callable[[str, Page], None],
    fetch: Fetcher | None = None,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
    is_known: Callable[[str], bool] | None = None,
    on_known: Callable[[str], None] | None = None,
    result: CrawlResult | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> CrawlResult:
    """The polite, scoped page walk - discovery only, no opinion on what a page *is*.

    ``classify`` decides per fetched HTML page whether it is collected and/or
    followed; ``on_page`` receives every collected page (it may raise to stop
    the walk, e.g. on a limit). ``is_known`` URLs are not fetched at all and are
    handed to ``on_known`` instead (already staged pages on a re-run).
    ``should_stop`` is polled before every request (a user's stop request).
    Scope, robots.txt, crawl delay, the page limit and redirect handling live
    only here, so another consumer (a text-page importer, say) reuses them.
    """
    logger = logger or get_logger()
    fetch = fetch or create_fetcher(config)
    settings = config.crawl

    start = normalize_url(start_url)
    if start is None:
        raise CrawlError(f"Not an http(s) URL: {start_url}")
    scope = Scope.of(start)

    robots = _load_robots(start, fetch)
    if not robots.can_fetch(settings.user_agent, start):
        raise CrawlError(
            f"robots.txt of {scope.host} does not allow automated reading of {start}",
            hint="The site asks crawlers to stay away from this page, and the pipeline respects that.",
        )
    delay = max(float(settings.delay_seconds), float(robots.crawl_delay(settings.user_agent) or 0))

    info_event(
        logger,
        f"Crawl: {start}  (up to {settings.max_depth} links deep, one page every {delay:g}s)",
        event_name="crawl.start", url=start, delay_seconds=delay, max_depth=settings.max_depth,
    )

    if result is None:
        result = CrawlResult(start_url=start, delay_seconds=delay)
    else:
        result.start_url, result.delay_seconds = start, delay
    # (normalised URL - fetched and de-duplicated, depth, the URL as written - the base of its relative links)
    queue: deque[tuple[str, int, str]] = deque([(start, 0, str(start_url).strip().split("#", 1)[0])])
    seen = {start}

    while queue:
        if should_stop is not None and should_stop():
            warn_event(logger, f"Crawl stopped on request ({len(queue)} pages still queued)",
                       event_name="crawl.stopped", url=start, queued=len(queue))
            break
        url, depth, written = queue.popleft()
        if is_known is not None and is_known(url):
            logger.debug("    already staged, not fetched again: %s", url)
            if on_known is not None:
                on_known(url)
            continue
        if not robots.can_fetch(settings.user_agent, url):
            result.blocked_by_robots += 1
            logger.debug("    robots.txt disallows %s", url)
            continue
        if result.pages_fetched >= settings.max_pages:
            raise CrawlLimitError(
                f"The crawl of {start} reached crawl.max_pages ({settings.max_pages}) "
                f"with {len(queue) + 1} pages still queued.",
                hint="Start from a narrower page, or raise crawl.max_pages in config/config.yaml.",
            )

        sleep(delay)  # robots.txt was the first request
        progress = f"    [{result.pages_fetched + 1} read, {len(queue)} queued] {urlsplit(url).path or '/'}"
        try:
            page = fetch(url)
        except NetworkError as exc:
            if depth == 0:
                raise
            result.pages_fetched += 1
            result.unreadable_pages += 1
            warn_event(logger, f"{progress} - skipped: {exc.message}", event_name="crawl.page_failed", url=url)
            continue
        result.pages_fetched += 1

        final = normalize_url(page.url) or url
        if not scope.contains(final):
            if depth == 0:
                raise CrawlError(
                    f"{start} redirects to {final}.",
                    hint="A page that sends you elsewhere (for example to a login form) cannot be "
                         "crawled; the pipeline never logs in.",
                )
            warn_event(logger, f"{progress} - redirects outside the start page ({final}), skipped",
                       event_name="crawl.page_redirected", url=url, target=final)
            continue
        if final != url and final in seen:
            logger.debug("%s - same page as %s, skipped", progress, final)
            continue
        seen.add(final)

        if not page.is_html:
            if depth == 0:
                raise CrawlError(f"{start} could not be read as a web page (HTTP {page.status}).")
            if 200 <= page.status < 300:
                logger.debug("%s - not a web page (%s), skipped", progress, page.content_type)
            else:
                result.unreadable_pages += 1
                warn_event(logger, f"{progress} - skipped (HTTP {page.status})",
                           event_name="crawl.page_failed", url=url, status=page.status)
            continue

        decision = classify(final, page)
        if decision.collect:
            logger.info("%s - collected", progress)
            on_page(final, page)
        if not decision.follow:
            continue
        if depth >= settings.max_depth:
            logger.info("%s - depth limit reached", progress)
            continue

        new_links = 0
        # relative links resolve against the address the page answered on; without a redirect that is the URL as
        # written (its trailing slash matters), not the normalised one that was requested
        base = page.url if page.url != url else written
        for link, raw in _link_pairs(page.text, base):
            if link in seen or not scope.contains(link) or _is_file_link(link):
                continue
            seen.add(link)
            queue.append((link, depth + 1, raw))
            new_links += 1
        logger.info("%s - listing, %d new link(s)", progress, new_links)

    return result


def video_page_classifier(config: Config) -> Classifier:
    """A page with an embedded player (``crawl.embed_patterns``) is a video page, and a leaf."""
    patterns = [re.compile(pattern, re.IGNORECASE) for pattern in config.crawl.embed_patterns]

    def classify(url: str, page: Page) -> Decision:
        is_video = any(pattern.search(page.text) for pattern in patterns)
        return Decision(collect=is_video, follow=not is_video)

    return classify


def crawl(
    start_url: str,
    *,
    config: Config,
    fetch: Fetcher | None = None,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
    is_known: Callable[[str], bool] | None = None,
    max_items: int | None = None,
    on_video_page: Callable[[str, Page], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> CrawlResult:
    """Collect the video pages reachable from ``start_url``, in site order.

    ``is_known`` marks URLs that are already staged: they count as video pages
    without being fetched again, so re-running a crawl costs only the listing
    pages. The crawl aborts as soon as it finds more than ``max_items`` videos.
    ``on_video_page`` also receives every fetched video page (its HTML), e.g. to
    read the title and the embedded player's URL.
    """
    logger = logger or get_logger()
    limit = max_items if max_items is not None else config.crawl.max_items
    result = CrawlResult(start_url=start_url, delay_seconds=0.0)

    def found(url: str) -> None:
        result.video_urls.append(url)
        if len(result.video_urls) > limit:
            raise CrawlLimitError(
                f"{result.start_url} leads to more than {limit} video pages.",
                hint="Start from a narrower page (a topic instead of a whole subject), "
                     f"raise the limit for this run with --max-items, or change crawl.max_items.",
            )

    def on_page(url: str, page: Page) -> None:
        found(url)
        if on_video_page is not None:
            on_video_page(url, page)

    walk(
        start_url, config=config, classify=video_page_classifier(config), on_page=on_page,
        fetch=fetch, sleep=sleep, logger=logger, is_known=is_known, on_known=found, result=result,
        should_stop=should_stop,
    )

    extras = [f"{result.pages_fetched} pages read"]
    if result.blocked_by_robots:
        extras.append(f"{result.blocked_by_robots} disallowed by robots.txt")
    if result.unreadable_pages:
        extras.append(f"{result.unreadable_pages} unreadable")
    info_event(
        logger,
        f"Crawl found {len(result.video_urls)} video page(s) under {result.start_url} ({', '.join(extras)})",
        event_name="crawl.done", url=result.start_url, videos=len(result.video_urls),
        pages=result.pages_fetched, blocked=result.blocked_by_robots, unreadable=result.unreadable_pages,
    )
    return result
