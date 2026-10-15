"""HH:MM:SS handling - the video counterpart of the vault's page anchors."""

import pytest

from msp.timestamps import (
    format_timestamp,
    is_valid_timestamp,
    parse_timestamp,
    timestamp_marker,
    video_anchor,
)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "00:00:00"), (9, "00:00:09"), (92, "00:01:32"), (3725, "01:02:05"), (360000, "100:00:00")],
)
def test_format_is_always_zero_padded(seconds, expected):
    assert format_timestamp(seconds) == expected


def test_fractional_seconds_are_truncated_not_rounded():
    assert format_timestamp(92.9) == "00:01:32"


def test_negative_time_is_rejected():
    with pytest.raises(ValueError):
        format_timestamp(-1)


def test_round_trip():
    for seconds in (0, 59, 60, 3599, 3600, 86399):
        assert parse_timestamp(format_timestamp(seconds)) == seconds


@pytest.mark.parametrize("bad", ["1:32", "92s", "00:1:32", "00:60:00", "00:00:60", "", "abc"])
def test_non_conforming_timestamps_are_rejected(bad):
    assert not is_valid_timestamp(bad)
    with pytest.raises(ValueError):
        parse_timestamp(bad)


def test_marker_and_anchor_shape():
    assert timestamp_marker(92) == "[00:01:32]"
    assert video_anchor("video.mp4", 92) == "[[video.mp4#t=00:01:32]]"
