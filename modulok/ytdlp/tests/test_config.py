"""Configuration loading, validation and path resolution."""

import pytest

from msp.config import Config
from msp.errors import ConfigError
from msp.paths import find_project_root, resolve_path


def test_defaults_when_no_file_exists(tmp_path):
    config = Config.from_dict({}, project_root=tmp_path)
    assert config.output_root == tmp_path / "staging"
    assert config.video.max_height == 1080
    assert config.organization.provider_folder is True
    assert config.playlist.enabled is False
    assert config.crawl.max_depth == 2
    assert config.crawl.embed_patterns


def test_shipped_config_loads(real_project_root):
    config = Config.load(project_root=real_project_root)
    assert config.config_path is not None
    assert config.output_root == real_project_root / "staging"
    assert "Történelem" in config.subjects.taxonomy
    assert config.organization.provider_names["zanza.tv"] == "Zanza"
    assert config.crawl.delay_seconds >= 10
    assert config.crawl.max_depth == 2


def test_relative_paths_are_anchored_to_the_project_root(tmp_path):
    config = Config.from_dict({"output_root": "./data/out"}, project_root=tmp_path)
    assert config.output_root == tmp_path / "data" / "out"
    assert config.archive_dir == tmp_path / "archive"
    assert config.log_dir == tmp_path / "logs"


def test_absolute_output_root_is_kept(tmp_path):
    other = tmp_path / "elsewhere"
    config = Config.from_dict({"output_root": str(other)}, project_root=tmp_path)
    assert config.output_root == other


def test_cli_output_root_overrides_the_file(tmp_path):
    config = Config.from_dict({"output_root": "./staging"}, project_root=tmp_path,
                              output_root=str(tmp_path / "cli"))
    assert config.output_root == tmp_path / "cli"


def test_format_selector_merges_by_default(tmp_path):
    config = Config.from_dict({"video": {"max_height": 720, "preferred_extension": "mp4"}},
                              project_root=tmp_path)
    selector = config.video.effective_format_selector
    # separate streams first (that is where >360p lives), pre-muxed as fallback
    assert selector.startswith("bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/")
    assert selector.endswith("best[height<=720][ext=mp4]/best[height<=720]/best")


def test_format_selector_without_merging_is_progressive_only(tmp_path):
    config = Config.from_dict(
        {"video": {"max_height": 720, "preferred_extension": "mp4", "allow_merge": False}},
        project_root=tmp_path,
    )
    assert config.video.effective_format_selector == "best[height<=720][ext=mp4]/best[height<=720]/best"


def test_explicit_format_selector_wins(tmp_path):
    config = Config.from_dict({"video": {"format_selector": "best[height<=480]"}}, project_root=tmp_path)
    assert config.video.effective_format_selector == "best[height<=480]"


@pytest.mark.parametrize("selector", ["bestvideo+bestaudio", "bestvideo[height<=1080]", "best+bestaudio"])
def test_merging_selectors_are_rejected_when_merging_is_off(tmp_path, selector):
    with pytest.raises(ConfigError) as excinfo:
        Config.from_dict(
            {"video": {"format_selector": selector, "allow_merge": False}},
            project_root=tmp_path,
        )
    assert "FFmpeg" in excinfo.value.message or "FFmpeg" in (excinfo.value.hint or "")


@pytest.mark.parametrize("selector", ["bestvideo+bestaudio", "bestvideo[height<=1080]"])
def test_merging_selectors_are_allowed_when_merging_is_on(tmp_path, selector):
    config = Config.from_dict({"video": {"format_selector": selector}}, project_root=tmp_path)
    assert config.video.effective_format_selector == selector


@pytest.mark.parametrize(
    "data",
    [
        {"video": {"max_height": "tall"}},
        {"video": {"max_height": 0}},
        {"metadata": {"save_json": "yes please"}},
        {"logging": {"level": "LOUD"}},
        {"subjects": {"taxonomy": "Történelem"}},
        {"organization": {"provider_names": {"a": 1}}},
        {"playlist": {"max_items": 0}},
        {"crawl": {"max_items": 0}},
        {"crawl": {"delay_seconds": -1}},
        {"crawl": {"embed_patterns": []}},
        {"crawl": {"embed_patterns": ["youtube.com/embed/("]}},
        {"crawl": {"user_agent": ""}},
        {"video": []},
    ],
)
def test_invalid_values_raise_config_error(tmp_path, data):
    with pytest.raises(ConfigError):
        Config.from_dict(data, project_root=tmp_path)


def test_missing_config_file_is_an_error(tmp_path):
    with pytest.raises(ConfigError):
        Config.load(tmp_path / "nope.yaml", project_root=tmp_path)


def test_env_config_pointer_is_validated(tmp_path, monkeypatch):
    monkeypatch.setenv("MSP_CONFIG", str(tmp_path / "missing.yaml"))
    with pytest.raises(ConfigError):
        Config.load(project_root=tmp_path)


def test_project_root_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MSP_PROJECT_ROOT", str(tmp_path))
    assert find_project_root() == tmp_path.resolve()


def test_project_root_prefers_the_config_marker(tmp_path, monkeypatch):
    outer = tmp_path / "outer"
    inner = outer / "inner"
    (inner / "config").mkdir(parents=True)
    (outer / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (inner / "config" / "config.yaml").write_text("output_root: ./staging\n", encoding="utf-8")
    monkeypatch.chdir(inner)
    assert find_project_root() == inner.resolve()


def test_resolve_path_expands_user(tmp_path):
    assert resolve_path("~", tmp_path).is_absolute()


def test_describe_mentions_the_effective_settings(tmp_path):
    text = Config.from_dict({}, project_root=tmp_path).describe()
    assert "output_root" in text and "format" in text
