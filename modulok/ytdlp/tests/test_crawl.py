"""Listing-page discovery (--crawl) against a fake site - no network."""

from __future__ import annotations

import pytest
from conftest import FakeDownloader, make_config, make_info

from msp.crawl import Page, crawl, extract_links, normalize_url
from msp.errors import CrawlError, CrawlLimitError, NetworkError
from msp.pipeline import STATUS_DRY_RUN, ingest_crawl

SITE = "https://zanza.tv"
START = f"{SITE}/tortenelem"


def listing(*links: str) -> str:
    anchors = "".join(f'<li><a href="{link}">link</a></li>' for link in links)
    return f"<html><body><ul>{anchors}</ul></body></html>"


def video(video_id: str, *links: str) -> str:
    player = (f'<iframe id="youtubeplayer" src="https://www.youtube.com/embed/{video_id}'
              f'?enablejsapi=1&amp;rel=0"></iframe>')
    return f"<html><body>{player}{listing(*links)}</body></html>"


def zanza_like_pages() -> dict[str, str | Page]:
    """subject -> topics -> videos, plus the traps a real page contains."""
    return {
        START: listing(
            "/tortenelem/okor",
            "/tortenelem/kozepkor",
            "/tortenelem/okor/kiemelt",           # a video linked straight from the subject page
            "/irodalom",                          # another subject
            "https://other.example/tortenelem/x", # another host
            "/tortenelem/okor#top",               # same page, different fragment
            "/tortenelem-archiv",                 # shares the prefix, is not below it
            "/tortenelem/terkep.pdf",             # a file
            "mailto:info@zanza.tv",
        ),
        f"{START}/okor": listing("/tortenelem/okor/athen", "/tortenelem/okor/roma/", START),
        f"{START}/kozepkor": listing("/tortenelem/kozepkor/hunyadiak"),
        f"{START}/okor/kiemelt": video("kiemelt0001", "/tortenelem/okor/csak-innen-linkelt"),
        f"{START}/okor/athen": video("athen000001"),
        f"{START}/okor/roma": video("roma0000001"),
        f"{START}/kozepkor/hunyadiak": video("hunyadiak01"),
        f"{START}/okor/csak-innen-linkelt": video("hidden00001"),
    }


class FakeSite:
    """Answers like a web server; records every request."""

    def __init__(self, pages=None, *, robots: str | Page | None = "User-agent: *\nDisallow: /admin/\n"):
        self.pages = zanza_like_pages() if pages is None else pages
        self.robots = robots
        self.requests: list[str] = []
        self.fail: dict[str, Exception] = {}

    def __call__(self, url: str) -> Page:
        self.requests.append(url)
        if url in self.fail:
            raise self.fail[url]
        if url.endswith("/robots.txt"):
            if self.robots is None:
                return Page(url, 404)
            if isinstance(self.robots, Page):
                return self.robots
            return Page(url, 200, "text/plain", self.robots)
        value = self.pages.get(url)
        if value is None:
            return Page(url, 404, "text/html")
        if isinstance(value, Page):
            return value
        return Page(url, 200, "text/html; charset=utf-8", value)

    @property
    def page_requests(self) -> list[str]:
        return [url for url in self.requests if not url.endswith("/robots.txt")]


class Sleeps(list):
    def __call__(self, seconds: float) -> None:
        self.append(seconds)


@pytest.fixture
def crawl_config(tmp_path):
    return make_config(tmp_path, crawl={"delay_seconds": 0})


def run(config, site, **kwargs):
    return crawl(START, config=config, fetch=site, sleep=kwargs.pop("sleep", Sleeps()), **kwargs)


# --- URLs and links ---------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("https://ZANZA.tv/tortenelem/", "https://zanza.tv/tortenelem"),
    ("https://zanza.tv/tortenelem#top", "https://zanza.tv/tortenelem"),
    ("https://zanza.tv:443//tortenelem//okor", "https://zanza.tv/tortenelem/okor"),
    ("https://zanza.tv/", "https://zanza.tv/"),
    ("https://zanza.tv/lista?page=2", "https://zanza.tv/lista?page=2"),
    ("http://localhost:8080/x", "http://localhost:8080/x"),
    ("mailto:info@zanza.tv", None),
    ("javascript:void(0)", None),
    ("https://zanza.tv:notaport/x", None),
])
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_links_are_absolute_unique_and_in_page_order():
    html = listing("/b", "a", "/b#x", "https://zanza.tv/b/", "mailto:x@y")
    assert extract_links(html, "https://zanza.tv/dir/page") == [
        "https://zanza.tv/b",
        "https://zanza.tv/dir/a",
    ]


# --- discovery --------------------------------------------------------------

def test_finds_every_video_page_below_the_start_page(crawl_config):
    site = FakeSite()
    result = run(crawl_config, site)
    assert result.video_urls == [
        f"{START}/okor/kiemelt",
        f"{START}/okor/athen",
        f"{START}/okor/roma",
        f"{START}/kozepkor/hunyadiak",
    ]


def test_never_leaves_the_host_or_the_start_path(crawl_config):
    site = FakeSite()
    run(crawl_config, site)
    assert all(url.startswith(f"{START}") or url == f"{SITE}/robots.txt" for url in site.requests)
    assert not any("archiv" in url or url.endswith(".pdf") for url in site.requests)


def test_each_page_is_read_once(crawl_config):
    site = FakeSite()
    run(crawl_config, site)
    assert len(site.requests) == len(set(site.requests))


def test_video_pages_are_leaves(crawl_config):
    site = FakeSite()
    result = run(crawl_config, site)
    assert f"{START}/okor/csak-innen-linkelt" not in site.requests
    assert f"{START}/okor/csak-innen-linkelt" not in result.video_urls


def test_depth_limit(tmp_path):
    config = make_config(tmp_path, crawl={"delay_seconds": 0, "max_depth": 1})
    site = FakeSite()
    result = run(config, site)
    assert result.video_urls == [f"{START}/okor/kiemelt"]
    assert f"{START}/okor/athen" not in site.requests


def test_a_video_page_as_start_page_is_its_own_result(crawl_config):
    site = FakeSite()
    result = crawl(f"{START}/okor/athen", config=crawl_config, fetch=site, sleep=Sleeps())
    assert result.video_urls == [f"{START}/okor/athen"]


# --- politeness -------------------------------------------------------------

def test_robots_txt_disallow_is_honoured(crawl_config):
    site = FakeSite(robots="User-agent: *\nDisallow: /tortenelem/kozepkor\n")
    result = run(crawl_config, site)
    assert f"{START}/kozepkor/hunyadiak" not in result.video_urls
    assert not any("kozepkor" in url for url in site.requests)
    assert result.blocked_by_robots == 1


def test_a_disallowed_start_page_is_an_error(crawl_config):
    site = FakeSite(robots="User-agent: *\nDisallow: /\n")
    with pytest.raises(CrawlError, match="robots.txt"):
        run(crawl_config, site)
    assert site.page_requests == []


def test_a_forbidden_robots_txt_means_stay_away(crawl_config):
    site = FakeSite(robots=Page(f"{SITE}/robots.txt", 403))
    with pytest.raises(CrawlError):
        run(crawl_config, site)
    assert site.page_requests == []


def test_a_missing_robots_txt_allows_everything(crawl_config):
    result = run(crawl_config, FakeSite(robots=None))
    assert len(result.video_urls) == 4


@pytest.mark.parametrize("configured, robots_delay, expected", [(3, 10, 10.0), (12, 10, 12.0), (0, None, 0.0)])
def test_waits_before_every_page_with_the_longer_delay(tmp_path, configured, robots_delay, expected):
    config = make_config(tmp_path, crawl={"delay_seconds": configured})
    robots = "User-agent: *\n" + (f"Crawl-delay: {robots_delay}\n" if robots_delay else "") + "Disallow: /admin/\n"
    site, sleeps = FakeSite(robots=robots), Sleeps()
    result = run(config, site, sleep=sleeps)
    assert result.delay_seconds == expected
    assert sleeps == [expected] * len(site.page_requests)


def test_the_fetcher_names_itself_verifies_tls_and_sends_no_credentials(tmp_path, monkeypatch):
    import io
    import ssl
    import urllib.error
    from email.message import Message

    from msp import crawl as crawl_mod

    sent = {}

    class Response(io.BytesIO):
        status = 200

        def __init__(self, body, url):
            super().__init__(body)
            self._url = url
            self.headers = Message()
            self.headers["Content-Type"] = "text/html; charset=utf-8"

        def geturl(self):
            return self._url

    def urlopen(request, *, timeout, context):
        sent.update(headers=dict(request.header_items()), timeout=timeout, context=context)
        if request.full_url.endswith("/hianyzik"):
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", Message(), None)
        return Response("<a href='/x'>Ókor</a>".encode("utf-8"), request.full_url)

    monkeypatch.setattr(crawl_mod.urllib.request, "urlopen", urlopen)
    config = make_config(tmp_path, crawl={"user_agent": "tester/1.0"})
    fetcher = crawl_mod.HttpFetcher(config)

    page = fetcher(START)
    assert (page.status, page.is_html, "Ókor" in page.text) == (200, True, True)
    headers = {name.lower(): value for name, value in sent["headers"].items()}
    assert headers["user-agent"] == "tester/1.0"
    assert "cookie" not in headers and "authorization" not in headers
    assert sent["context"].verify_mode == ssl.CERT_REQUIRED
    assert sent["timeout"] == config.download.socket_timeout
    assert fetcher(f"{START}/hianyzik").status == 404


# --- pages that are not what they seem --------------------------------------

def test_a_redirect_to_a_login_page_is_dropped(crawl_config):
    site = FakeSite()
    site.pages[f"{START}/okor/roma"] = Page(f"{SITE}/user/login", 200, "text/html", video("login000001"))
    result = run(crawl_config, site)
    assert f"{START}/okor/roma" not in result.video_urls
    assert all("login" not in url for url in result.video_urls)


def test_a_start_page_that_redirects_away_is_an_error(crawl_config):
    site = FakeSite()
    site.pages[START] = Page(f"{SITE}/user/login", 200, "text/html", listing())
    with pytest.raises(CrawlError, match="redirects"):
        run(crawl_config, site)


def test_an_unreadable_page_is_skipped_not_fatal(crawl_config):
    site = FakeSite()
    del site.pages[f"{START}/okor/roma"]           # -> 404
    site.fail[f"{START}/okor/athen"] = NetworkError("timed out")
    result = run(crawl_config, site)
    assert result.video_urls == [f"{START}/okor/kiemelt", f"{START}/kozepkor/hunyadiak"]
    assert result.unreadable_pages == 2


def test_an_unreadable_start_page_is_an_error(crawl_config):
    site = FakeSite()
    del site.pages[START]
    with pytest.raises(CrawlError, match="HTTP 404"):
        run(crawl_config, site)
    site.pages[START] = listing()
    site.fail[START] = NetworkError("offline")
    with pytest.raises(NetworkError):
        run(crawl_config, site)


def test_a_non_html_answer_is_not_a_video_page(crawl_config):
    site = FakeSite()
    site.pages[f"{START}/okor/roma"] = Page(f"{START}/okor/roma", 200, "application/json",
                                            "youtube.com/embed/abcdefghijk")
    result = run(crawl_config, site)
    assert f"{START}/okor/roma" not in result.video_urls


# --- limits and re-runs -----------------------------------------------------

def test_already_staged_pages_are_not_read_again(crawl_config):
    site = FakeSite()
    known = {f"{START}/okor/athen", f"{START}/okor/roma"}
    result = run(crawl_config, site, is_known=known.__contains__)
    assert len(result.video_urls) == 4
    assert not known & set(site.requests)


def test_page_limit_aborts(tmp_path):
    config = make_config(tmp_path, crawl={"delay_seconds": 0, "max_pages": 2})
    with pytest.raises(CrawlLimitError, match="max_pages"):
        run(config, FakeSite())


def test_item_limit_aborts_as_soon_as_it_is_exceeded(crawl_config):
    site = FakeSite()
    with pytest.raises(CrawlLimitError) as excinfo:
        run(crawl_config, site, max_items=2)
    assert "--max-items" in (excinfo.value.hint or "")
    assert f"{START}/kozepkor/hunyadiak" not in site.requests


# --- crawl -> staging -------------------------------------------------------

def per_url_downloader() -> FakeDownloader:
    downloader = FakeDownloader()

    def probe(url, *, allow_playlist=False, flat=False):
        downloader.probe_calls.append(url)
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        return make_info(video_id=f"yt-{slug}", title=slug.capitalize(), url=url)

    original_download = downloader.download

    def download(request):
        downloader.info = make_info(video_id=f"yt-{request.url.rsplit('/', 1)[-1]}",
                                    title=request.url.rsplit("/", 1)[-1].capitalize(), url=request.url)
        return original_download(request)

    downloader.probe = probe  # type: ignore[method-assign]
    downloader.download = download  # type: ignore[method-assign]
    return downloader


def test_crawl_stages_every_video_under_the_subject_folder(crawl_config):
    downloader = per_url_downloader()
    summary = ingest_crawl(START, config=crawl_config, downloader=downloader,
                           fetch=FakeSite(), sleep=Sleeps())
    assert (summary.downloaded, summary.failed) == (4, 0)
    folder = crawl_config.output_root / "Zanza" / "Történelem"
    assert sorted(path.name for path in folder.iterdir()) == ["Athen", "Hunyadiak", "Kiemelt", "Roma"]


def test_a_second_crawl_neither_reads_nor_probes_staged_videos(crawl_config):
    downloader = per_url_downloader()
    ingest_crawl(START, config=crawl_config, downloader=downloader, fetch=FakeSite(), sleep=Sleeps())
    downloader.probe_calls.clear()

    site = FakeSite()
    summary = ingest_crawl(START, config=crawl_config, downloader=downloader, fetch=site, sleep=Sleeps())
    assert (summary.downloaded, summary.skipped) == (0, 4)
    assert downloader.probe_calls == []
    assert site.page_requests == [START, f"{START}/okor", f"{START}/kozepkor"]


def test_force_reads_and_downloads_again(crawl_config):
    downloader = per_url_downloader()
    ingest_crawl(START, config=crawl_config, downloader=downloader, fetch=FakeSite(), sleep=Sleeps())
    summary = ingest_crawl(START, config=crawl_config, downloader=downloader, fetch=FakeSite(),
                           sleep=Sleeps(), force=True)
    assert summary.downloaded == 4


def test_downloads_keep_the_crawl_pace(tmp_path):
    config = make_config(tmp_path, crawl={"delay_seconds": 7})
    site, sleeps = FakeSite(), Sleeps()
    ingest_crawl(START, config=config, downloader=per_url_downloader(), fetch=site, sleep=sleeps)
    # one pause per page read, then one between each of the 4 downloads
    assert sleeps == [7.0] * (len(site.page_requests) + 3)


def test_dry_run_crawl_writes_nothing(crawl_config):
    downloader = per_url_downloader()
    summary = ingest_crawl(START, config=crawl_config, downloader=downloader, fetch=FakeSite(),
                           sleep=Sleeps(), dry_run=True)
    assert summary.count(STATUS_DRY_RUN) == 4
    assert not downloader.download_calls
    assert not crawl_config.output_root.exists()


def test_a_page_without_videos_is_an_error(crawl_config):
    site = FakeSite(pages={START: listing("/tortenelem/ures")}, robots=None)
    site.pages[f"{START}/ures"] = listing()
    with pytest.raises(CrawlError, match="No video page"):
        ingest_crawl(START, config=crawl_config, downloader=per_url_downloader(), fetch=site, sleep=Sleeps())


# --- the generic walk (2026-10-14): discovery separate from "what a page is" ---------------------------

def test_walk_with_another_classifier_collects_every_page_and_follows(crawl_config):
    """A later text-page importer: every in-scope HTML page is collected AND followed."""
    from msp.crawl import Decision, walk

    collected: list[str] = []
    walk(START, config=crawl_config, classify=lambda url, page: Decision(collect=True, follow=True),
         on_page=lambda url, page: collected.append(url), fetch=FakeSite(), sleep=Sleeps())
    assert collected[0] == START
    assert f"{START}/okor/athen" in collected and f"{START}/kozepkor" in collected
    assert all(url.startswith(START) for url in collected)


def test_relative_links_resolve_against_the_written_trailing_slash(crawl_config):
    """``0/`` on ``/x/weeks/`` is ``/x/weeks/0``, although the normalised request URL has no trailing slash."""
    pages = {
        "https://cs50.harvard.edu/x/weeks": listing("0/", "ai/", "../syllabus/"),
        "https://cs50.harvard.edu/x/weeks/0": video("UuIEbpQms8o"),
        "https://cs50.harvard.edu/x/weeks/ai": video("aiaiaiaiaia"),
        "https://cs50.harvard.edu/x/syllabus": listing(),
    }
    site = FakeSite(pages, robots=None)
    result = crawl("https://cs50.harvard.edu/x/weeks/", config=crawl_config, fetch=site, sleep=Sleeps())
    assert result.video_urls == ["https://cs50.harvard.edu/x/weeks/0", "https://cs50.harvard.edu/x/weeks/ai"]
    assert "https://cs50.harvard.edu/x/syllabus" not in site.requests


def test_a_stop_request_ends_the_walk(crawl_config):
    site = FakeSite()
    result = crawl(START, config=crawl_config, fetch=site, sleep=Sleeps(), should_stop=lambda: True)
    assert result.video_urls == [] and site.page_requests == []
