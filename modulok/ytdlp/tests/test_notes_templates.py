"""Note rendering, the template language, and surgical frontmatter updates."""

import pytest

from msp import notes, schema, templates
from msp.templates import TemplateError
from msp.yamlio import parse_frontmatter

BASE = dict(
    source_id="zanza-abc123",
    title="Az ókori Athén",
    provider="Zanza",
    url="https://zanza.tv/tortenelem/az-okori-athen",
    media_file="video.mp4",
    downloaded_at="2026-09-04T10:00:00+00:00",
)


def test_source_note_matches_the_specified_schema():
    values = notes.build_source_values(**BASE, subject="Történelem", language="hu")
    text = notes.render_source_note(values)
    front, body = parse_frontmatter(text, origin="source.md")

    assert front["type"] == "source"
    assert front["source_type"] == "video"
    assert front["pipeline_status"] == "downloaded"      # never plain 'status'
    assert "status" not in front                         # would collide with the vault's Status:
    assert front["transcript_file"] == "transcript.md"
    assert body.startswith("\n# Az ókori Athén")         # blank line then H1


def test_optional_fields_are_omitted_when_unknown_but_language_stays_null():
    values = notes.build_source_values(**BASE)
    front, _ = parse_frontmatter(notes.render_source_note(values), origin="s")
    assert "resolution" not in front and "uploader" not in front and "subject" not in front
    assert "language" in front and front["language"] is None


def test_duration_is_rendered_in_both_forms():
    values = notes.build_source_values(**BASE, duration_seconds=612)
    front, _ = parse_frontmatter(notes.render_source_note(values), origin="s")
    assert front["duration"] == "00:10:12"
    assert front["duration_seconds"] == 612


def test_transcript_note_uses_the_renamed_link_fields():
    values = notes.build_transcript_values(
        source_id="zanza-abc123", title="Az ókori Athén", media_file="video.mp4", language="hu",
    )
    front, body = parse_frontmatter(notes.render_transcript_note(values), origin="t")
    assert front["source_note"] == "[[source]]"     # not 'source:' (vault page anchor)
    assert front["media"] == "[[video.mp4]]"
    assert front["transcript_status"] == "pending"
    assert front["transcript_postprocessed"] is False
    assert "— Transcript" in body
    assert "placeholder" in body


def test_titles_with_quotes_survive_the_yaml_round_trip():
    values = notes.build_source_values(**{**BASE, "title": 'Az "ókori" Athén: 1. rész'})
    front, _ = parse_frontmatter(notes.render_source_note(values), origin="s")
    assert front["title"] == 'Az "ókori" Athén: 1. rész'


@pytest.mark.parametrize("dangerous", ["no", "yes", "2024-01-01", "null", "1080"])
def test_scalar_looking_titles_stay_strings(dangerous):
    values = notes.build_source_values(**{**BASE, "title": dangerous})
    front, _ = parse_frontmatter(notes.render_source_note(values), origin="s")
    assert front["title"] == dangerous


def test_unknown_status_values_are_rejected_early():
    with pytest.raises(ValueError):
        notes.build_source_values(**BASE, pipeline_status="whatever")
    with pytest.raises(ValueError):
        notes.build_transcript_values(source_id="a", title="t", media_file="v.mp4",
                                      transcript_status="whatever")


def test_template_drops_optional_lines_but_keeps_explicit_null():
    rendered = templates.render("---\na: {{a}}\nb: {{b}}\n---\n", {"a": None})
    assert "a: null" in rendered
    assert "b:" not in rendered


def test_template_reports_missing_body_placeholders():
    with pytest.raises(TemplateError):
        templates.render("---\na: {{a}}\n---\n\n{{missing}}\n", {"a": 1})


def test_user_template_overrides_the_builtin(tmp_path):
    (tmp_path / "source.md").write_text("---\ntype: {{type}}\n---\n\nCUSTOM {{title}}\n", encoding="utf-8")
    values = notes.build_source_values(**BASE)
    text = notes.render_source_note(values, tmp_path)
    assert "CUSTOM Az ókori Athén" in text


def test_empty_user_template_falls_back_to_the_builtin(tmp_path):
    (tmp_path / "source.md").write_text("   \n", encoding="utf-8")
    text = notes.render_source_note(notes.build_source_values(**BASE), tmp_path)
    assert "pipeline_status" in text


def test_update_frontmatter_is_surgical(tmp_path):
    path = tmp_path / "source.md"
    notes.write_source_note(path, notes.build_source_values(**BASE, subject="Történelem"))
    original = path.read_text(encoding="utf-8")

    notes.update_frontmatter(path, {"pipeline_status": "metadata_only", "reviewed_by": "owner"})
    front, body = notes.read_note(path)

    assert front["pipeline_status"] == "metadata_only"
    assert front["reviewed_by"] == "owner"
    assert front["subject"] == "Történelem"
    assert body == original.split("---\n", 2)[2]   # the body is untouched


def test_update_frontmatter_preserves_manual_comments(tmp_path):
    path = tmp_path / "note.md"
    path.write_text('---\ntype: "source"\n# a manual comment\nkeep: "me"\n---\n\nbody\n', encoding="utf-8")
    notes.update_frontmatter(path, {"type": "source"})
    text = path.read_text(encoding="utf-8")
    assert "# a manual comment" in text
    assert 'keep: "me"' in text


def test_replace_body_keeps_frontmatter(tmp_path):
    path = tmp_path / "transcript.md"
    notes.write_transcript_note(path, notes.build_transcript_values(
        source_id="s", title="T", media_file="video.mp4"))
    notes.replace_body(path, "[00:00:00]\n\nszöveg\n")
    front, body = notes.read_note(path)
    assert front["source_id"] == "s"
    assert "[00:00:00]" in body


def test_schema_and_template_agree_on_required_fields():
    """Every required schema field must actually appear in the rendered note."""
    values = notes.build_source_values(**BASE)
    front, _ = parse_frontmatter(notes.render_source_note(values), origin="s")
    for name in schema.required_field_names(schema.SOURCE_FIELDS):
        assert name in front, name

    tvalues = notes.build_transcript_values(source_id="s", title="T", media_file="video.mp4")
    tfront, _ = parse_frontmatter(notes.render_transcript_note(tvalues), origin="t")
    for name in schema.required_field_names(schema.TRANSCRIPT_FIELDS):
        assert name in tfront, name


def test_shipped_template_files_match_the_builtin_defaults(real_project_root):
    source = (real_project_root / "templates" / "source.md").read_text(encoding="utf-8")
    transcript = (real_project_root / "templates" / "transcript.md").read_text(encoding="utf-8")
    assert source == templates.DEFAULT_SOURCE_TEMPLATE
    assert transcript == templates.DEFAULT_TRANSCRIPT_TEMPLATE
