"""The YAML layer: PyYAML when present, a strict minimal reader when not."""

import pytest

from msp import yamlio
from msp.errors import ConfigError, YamlSubsetError

SAMPLE = """
output_root: "./staging"
video:
  max_height: 1080
  preferred_extension: mp4
  format_selector: null
subjects:
  taxonomy:
    - "Történelem"
    - Fizika
  aliases:
    tortenelem: "Történelem"
    "youtube:tab": "YouTube"
flags: [a, "b", 3]
enabled: true
disabled: false
empty:
# comment line
trailing: value  # trailing comment
url: "https://example.com/#anchor"
"""


def test_minimal_reader_matches_pyyaml_on_the_sample():
    assert yamlio.HAVE_PYYAML, "PyYAML should be installed in the dev environment"
    assert yamlio._load_subset(SAMPLE, origin="t") == yamlio.load(SAMPLE)


def test_minimal_reader_matches_pyyaml_on_the_shipped_config(real_project_root):
    text = (real_project_root / "config" / "config.yaml").read_text(encoding="utf-8")
    assert yamlio._load_subset(text, origin="config.yaml") == yamlio.load(text)


def test_scalar_types():
    data = yamlio._load_subset(SAMPLE, origin="t")
    assert data["video"]["max_height"] == 1080
    assert data["video"]["format_selector"] is None
    assert data["enabled"] is True and data["disabled"] is False
    assert data["empty"] is None
    assert data["flags"] == ["a", "b", 3]
    assert data["trailing"] == "value"
    assert data["url"] == "https://example.com/#anchor"
    assert data["subjects"]["aliases"]["youtube:tab"] == "YouTube"


@pytest.mark.parametrize(
    "text",
    [
        "key: &anchor value",
        "key: |\n  block scalar\n",
        "a: 1\n\tb: 2\n",
        "key: {a: 1}",
        "list:\n  - a: 1\n",
    ],
)
def test_minimal_reader_refuses_what_it_cannot_represent(text):
    with pytest.raises(YamlSubsetError) as excinfo:
        yamlio._load_subset(text, origin="t")
    assert "PyYAML" in (excinfo.value.hint or "")


def test_frontmatter_split_and_parse():
    note = '---\ntype: "source"\nsource_id: "zanza-abc"\n---\n\n# Title\n\nbody\n'
    front, body = yamlio.parse_frontmatter(note, origin="note.md")
    assert front == {"type": "source", "source_id": "zanza-abc"}
    assert body.startswith("\n# Title")


def test_missing_frontmatter_is_an_error():
    with pytest.raises(ConfigError):
        yamlio.parse_frontmatter("# just a heading\n", origin="note.md")


def test_frontmatter_must_be_a_mapping():
    with pytest.raises(ConfigError):
        yamlio.parse_frontmatter("---\n- a\n- b\n---\n", origin="note.md")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "null"),
        (True, "true"),
        (False, "false"),
        (12, "12"),
        ("text", '"text"'),
        ('quote"inside', '"quote\\"inside"'),
        ("line\nbreak", '"line\\nbreak"'),
        (["a", 1], '["a", 1]'),
    ],
)
def test_scalar_serialisation(value, expected):
    assert yamlio.to_yaml_scalar(value) == expected


def test_serialised_scalars_round_trip_through_pyyaml():
    for value in ["no", "yes", "2024-01-01", "null", "1080", "Történelem"]:
        rendered = f"key: {yamlio.to_yaml_scalar(value)}"
        assert yamlio.load(rendered)["key"] == value
