"""Filename sanitisation, identifiers and the path-traversal guard."""

from pathlib import Path

import pytest

from msp.errors import FilesystemError
from msp.naming import (
    MAX_COMPONENT_BYTES,
    ensure_within,
    make_source_id,
    sanitize_component,
    sanitize_filename,
    sanitize_id_part,
    short_hash,
    slugify,
)


def test_accented_title_is_preserved():
    assert sanitize_component("Az ókori Athén") == "Az ókori Athén"


@pytest.mark.parametrize("raw", ["a/b", "a\\b", "a:b", "a*b", "a?b", 'a"b', "a<b", "a>b", "a|b"])
def test_filesystem_unsafe_characters_are_replaced(raw):
    result = sanitize_component(raw)
    assert result == "a-b"


@pytest.mark.parametrize("raw", ["a[b", "a]b", "a#b", "a^b"])
def test_obsidian_wikilink_breaking_characters_are_replaced(raw):
    """[[ ]] # ^ | would break a wikilink to the file."""
    assert sanitize_component(raw) == "a-b"


def test_control_characters_are_removed():
    assert sanitize_component("a\x00\x1fb") == "a-b"


def test_path_traversal_attempts_cannot_survive():
    for raw in ("../../etc/passwd", "..", ".", "/absolute/path"):
        result = sanitize_component(raw)
        assert "/" not in result
        assert result not in {"..", "."}


def test_empty_and_dot_only_names_fall_back():
    assert sanitize_component("   ") == "untitled"
    assert sanitize_component("...") == "untitled"
    assert sanitize_component("", fallback="fb") == "fb"


def test_windows_reserved_names_are_prefixed():
    assert sanitize_component("CON") == "_CON"
    assert sanitize_component("com1.txt").startswith("_")


def test_long_names_are_truncated_on_a_character_boundary():
    result = sanitize_component("ó" * 300)
    assert len(result.encode("utf-8")) <= MAX_COMPONENT_BYTES
    assert "ó" in result  # not mangled mid-character


def test_sanitize_filename_keeps_extension():
    assert sanitize_filename("video", "MP4") == "video.mp4"
    assert sanitize_filename("a/b", "mp4") == "a-b.mp4"
    assert sanitize_filename("video", None) == "video"


def test_slugify():
    assert slugify("Zanza.tv") == "zanza-tv"
    assert slugify("Történelem") == "tortenelem"
    assert slugify("!!!", fallback="x") == "x"


def test_source_id_uses_the_platform_id():
    assert make_source_id("zanza", "abc123", "https://zanza.tv/x") == "zanza-abc123"


def test_source_id_preserves_case_of_platform_ids():
    # YouTube ids are case sensitive; collapsing them would collide.
    assert make_source_id("youtube", "dQw4w9WgXcQ", "https://y/x") == "youtube-dQw4w9WgXcQ"


def test_source_id_falls_back_to_a_marked_url_hash():
    generated = make_source_id("zanza", None, "https://zanza.tv/x")
    assert generated.startswith("zanza-u")
    assert generated == make_source_id("zanza", "", "https://zanza.tv/x")
    assert generated != make_source_id("zanza", None, "https://zanza.tv/y")


def test_sanitize_id_part_strips_dangerous_characters():
    assert sanitize_id_part("../evil") == "-evil" or "/" not in sanitize_id_part("../evil")
    assert "/" not in sanitize_id_part("a/b")


def test_short_hash_is_stable():
    assert short_hash("x") == short_hash("x")
    assert len(short_hash("x", 8)) == 8


def test_ensure_within_accepts_children_and_rejects_escapes(tmp_path):
    base = tmp_path / "staging"
    base.mkdir()
    assert ensure_within(base, base / "a" / "b") == (base / "a" / "b").resolve()
    with pytest.raises(FilesystemError):
        ensure_within(base, tmp_path / "outside")
    with pytest.raises(FilesystemError):
        ensure_within(base, base / ".." / "outside")
