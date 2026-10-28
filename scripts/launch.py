#!/usr/bin/env python3
"""Load the TUI plugin without overwriting any OpenCode configuration files."""

import json
import os
import subprocess
import sys
from pathlib import Path


def overlay(config: dict[str, object], inline: dict[str, object], root: str) -> dict[str, object]:
    """Append voice to the effective CLI plugin list, preserving other directives."""
    previous = inline.get("plugins", config.get("plugins", []))
    if not isinstance(previous, list) or not all(
        isinstance(item, (str, dict)) for item in previous
    ):
        raise ValueError("OpenCode CLI plugins must be an array")
    plugins = list(previous)
    if root not in plugins:
        plugins.append(root)
    return {**inline, "plugins": plugins}


def parse_config(text: str) -> dict[str, object]:
    """Use the same JSONC parser as OpenCode, including comments and trailing commas."""
    output = subprocess.check_output(
        ["node", str(Path(__file__).with_name("parse-cli.mjs"))], input=text, text=True
    )
    value: dict[str, object] = json.loads(output)
    return value


def main() -> None:
    """Exec the unmodified installed OpenCode CLI with one inline plugin overlay."""
    root = Path(__file__).resolve().parent.parent
    paths = subprocess.check_output(["opencode", "debug", "paths"], text=True)
    config_dir = next(
        line.split(maxsplit=1)[1] for line in paths.splitlines() if line.split()[:1] == ["config"]
    )
    path = Path(config_dir) / "cli.json"
    config = parse_config(path.read_text()) if path.exists() else {}
    inline = parse_config(os.environ.get("OPENCODE_CLI_CONFIG_CONTENT", "{}"))
    env = {
        **os.environ,
        "OPENCODE_CLI_CONFIG_CONTENT": json.dumps(overlay(config, inline, str(root))),
    }
    os.execvpe("opencode", ["opencode", *sys.argv[1:]], env)


if __name__ == "__main__":
    main()
