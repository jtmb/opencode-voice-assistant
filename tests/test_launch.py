"""CLI registration must preserve the user's other plugins and settings."""

import pytest

from scripts.launch import overlay, parse_config


def test_overlay_preserves_plugin_directives_and_existing_inline_preferences() -> None:
    """Adding voice must not replace unrelated TUI extensions."""
    original = {"plugins": ["first", {"package": "second", "options": {"enabled": False}}]}
    result = overlay(original, {"mouse": False}, "/repo/voice-assistant")
    assert result == {"mouse": False, "plugins": [*original["plugins"], "/repo/voice-assistant"]}
    assert len(original["plugins"]) == 2
    assert overlay(original, result, "/repo/voice-assistant") == result


def test_overlay_preserves_explicit_inline_override_and_rejects_invalid_plugins() -> None:
    """The native inline config retains its precedence."""
    assert overlay({"plugins": ["global"]}, {"plugins": ["inline"]}, "/voice")["plugins"] == [
        "inline",
        "/voice",
    ]
    with pytest.raises(ValueError):
        overlay({"plugins": "bad"}, {}, "/voice")


def test_native_jsonc_comments_and_trailing_commas_are_preserved_semantically() -> None:
    """The launcher accepts native CLI JSONC rather than silently dropping plugins."""
    assert parse_config('{ // comment\n "plugins": ["keep",], "mouse": false, }') == {
        "plugins": ["keep"],
        "mouse": False,
    }
