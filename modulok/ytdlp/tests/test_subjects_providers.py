"""Provider identity and subject resolution."""

import pytest

from msp.errors import ConfigError
from msp.providers import host_slug, normalize_host, resolve_provider
from msp.subjects import guess_subject, normalize_subject, resolve_subject


@pytest.mark.parametrize(
    ("url", "slug", "folder"),
    [
        ("https://zanza.tv/tortenelem/az-okori-athen", "zanza", "Zanza"),
        ("https://www.youtube.com/watch?v=abc", "youtube", "YouTube"),
        ("https://youtu.be/abc", "youtube", "YouTube"),
        ("https://m.youtube.com/watch?v=abc", "youtube", "YouTube"),
        ("https://example.org/video/1", "example", "Web"),
    ],
)
def test_provider_resolution(config, url, slug, folder):
    provider = resolve_provider(url, {}, config)
    assert provider.slug == slug
    assert provider.folder_name == folder


def test_an_embedding_site_keeps_its_own_identity(config):
    """zanza.tv hosts no video: yt-dlp resolves to the embedded YouTube page.

    The staged source is still the zanza.tv page that was requested.
    """
    info = {"webpage_url": "https://www.youtube.com/watch?v=kdkQvYe6eS4",
            "extractor_key": "Youtube", "id": "kdkQvYe6eS4"}
    provider = resolve_provider("https://zanza.tv/tortenelem/x/hunyadiak-kora", info, config)
    assert provider.slug == "zanza"
    assert provider.folder_name == "Zanza"


def test_provider_falls_back_to_the_media_url_when_the_request_has_no_host(config):
    provider = resolve_provider("", {"webpage_url": "https://zanza.tv/y"}, config)
    assert provider.slug == "zanza"


def test_subject_comes_from_the_requested_page_not_the_embed(config):
    info = {"webpage_url": "https://www.youtube.com/watch?v=kdkQvYe6eS4"}
    resolution = resolve_subject("https://zanza.tv/tortenelem/x/hunyadiak-kora", info, config)
    assert resolution.name == "Történelem"
    assert resolution.source == "url"


def test_named_extractor_is_used_when_the_host_is_unknown(config):
    provider = resolve_provider("https://videos.example/x", {"extractor_key": "SomeSite"}, config)
    assert provider.display_name == "SomeSite"


def test_host_helpers():
    assert normalize_host("https://WWW.Zanza.TV/x") == "zanza.tv"
    assert host_slug("m.youtube.com") == "youtube"
    assert host_slug("") == ""


def test_subject_normalisation_against_the_taxonomy(config):
    assert normalize_subject("Történelem", config) == ("Történelem", True)
    assert normalize_subject("tortenelem", config) == ("Történelem", True)   # alias
    assert normalize_subject("TÖRTÉNELEM", config) == ("Történelem", True)   # case fold
    assert normalize_subject("tortenelem", config) == ("Történelem", True)   # accent fold
    assert normalize_subject(None, config) == (None, False)
    assert normalize_subject("  ", config) == (None, False)


def test_unknown_subjects_are_kept_but_flagged(config):
    name, known = normalize_subject("Asztrofizika", config)
    assert name == "Asztrofizika"
    assert known is False


def test_alias_can_point_outside_the_taxonomy(config):
    name, known = normalize_subject("matek", config)
    assert name == "Matematika"
    assert known is False    # alias target is not in this test taxonomy


def test_subject_from_url_path(config):
    assert guess_subject("https://zanza.tv/tortenelem/az-okori-athen", {}, config) == \
        ("Történelem", "url")


def test_subject_from_metadata_categories(config):
    assert guess_subject("https://x/y", {"categories": ["Fizika"]}, config) == ("Fizika", "metadata")


def test_heuristics_never_invent_a_new_subject(config):
    assert guess_subject("https://x/random-slug", {"tags": ["vlog", "2024"]}, config) is None


def test_resolution_priority(config):
    url = "https://zanza.tv/tortenelem/az-okori-athen"
    assert resolve_subject(url, {}, config, explicit="Fizika").source == "cli"
    assert resolve_subject(url, {}, config, hint="Fizika").name == "Fizika"
    assert resolve_subject(url, {}, config, explicit="Irodalom", hint="Fizika").name == "Irodalom"
    assert resolve_subject(url, {}, config).source == "url"
    assert resolve_subject("https://x/y", {}, config).name == "Besorolatlan"
    assert resolve_subject("https://x/y", {}, config).source == "default"


ZANZA_SUBJECT_SLUGS = {
    "tortenelem": "Történelem",
    "irodalom": "Irodalom",
    "magyar-nyelv": "Magyar nyelv",
    "matematika": "Matematika",
    "filozofia": "Filozófia",
    "etika": "Etika",
    "tarsadalomismeret": "Társadalomismeret",
    "testneveles-es-sport": "Testnevelés és sport",
}


@pytest.mark.parametrize(("slug", "expected"), sorted(ZANZA_SUBJECT_SLUGS.items()))
def test_shipped_config_maps_every_zanza_subject(real_project_root, slug, expected):
    """The eight subject sections zanza.tv actually has (verified 2026-09)."""
    from msp.config import Config

    shipped = Config.load(project_root=real_project_root)
    resolution = resolve_subject(f"https://zanza.tv/{slug}/topic/video", {}, shipped)
    assert resolution.name == expected
    assert resolution.source == "url"
    assert resolution.in_taxonomy is True

# --- keyword inference (last resort) ----------------------------------------

def _keyword_config(tmp_path):
    from conftest import make_config

    return make_config(tmp_path, subjects={
        "keywords": {
            "Történelem": ["középkor", "király", "csata"],
            "Fizika": ["energia", "newton"],
        },
    })


def test_keywords_classify_a_video_that_has_no_subject_anywhere(tmp_path):
    config = _keyword_config(tmp_path)
    result = resolve_subject(
        "https://www.youtube.com/watch?v=abc",
        {"title": "Államok a kora középkorban", "description": "A királyi hatalom kialakulása."},
        config,
    )
    assert result.name == "Történelem"
    assert result.source == "keywords"     # recorded as inferred, not read
    assert result.in_taxonomy


def test_hungarian_suffixes_still_match(tmp_path):
    """Substring matching is what makes 'kozepkorban' match 'kozepkor'."""
    config = _keyword_config(tmp_path)
    result = resolve_subject("https://youtube.com/watch?v=a",
                             {"title": "A középkorban játszódó csaták"}, config)
    assert result.name == "Történelem"


def test_the_subject_with_more_matches_wins(tmp_path):
    config = _keyword_config(tmp_path)
    result = resolve_subject(
        "https://youtube.com/watch?v=a",
        {"title": "Newton és a király", "description": "energia, energia, newton"},
        config,
    )
    assert result.name == "Fizika"


def test_keywords_never_beat_an_explicit_subject(tmp_path):
    config = _keyword_config(tmp_path)
    result = resolve_subject("https://youtube.com/watch?v=a",
                             {"title": "A középkori király"}, config, explicit="Fizika")
    assert result.name == "Fizika"
    assert result.source == "cli"


def test_without_a_match_the_default_subject_is_used(tmp_path):
    config = _keyword_config(tmp_path)
    result = resolve_subject("https://youtube.com/watch?v=a",
                             {"title": "Vlog #42"}, config)
    assert result.name == "Besorolatlan"
    assert result.source == "default"


def test_too_short_keywords_are_refused_by_the_config(tmp_path):
    from conftest import make_config

    with pytest.raises(ConfigError) as excinfo:
        make_config(tmp_path, subjects={"keywords": {"Fizika": ["erő"]}})
    assert "4 characters" in excinfo.value.message
