#!/usr/bin/env python3
"""Install only pinned speech models, optionally reusing verified local files."""

import argparse
import hashlib
import json
import shutil
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICE = "https://huggingface.co/rhasspy/piper-voices/resolve/5041a7a49ae5b3a0f30e6837769eb03fdbb231bd/en/en_US/lessac/medium/"
ASSETS = [
    (
        "vosk-model-en-us-0.22-lgraph.zip",
        "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22-lgraph.zip",
        "d9838b4aaa82a75c4a17f5aca300eaca129aaab2a7cbf951bafbb500eb9c4334",
    ),
    (
        "en_US-lessac-medium.onnx",
        VOICE + "en_US-lessac-medium.onnx",
        "5efe09e69902187827af646e1a6e9d269dee769f9877d17b16b1b46eeaaf019f",
    ),
    (
        "en_US-lessac-medium.onnx.json",
        VOICE + "en_US-lessac-medium.onnx.json",
        "efe19c417bed055f2d69908248c6ba650fa135bc868b0e6abb3da181dab690a0",
    ),
    (
        "MODEL_CARD",
        VOICE + "MODEL_CARD",
        "ce49eb457742208166d399a40cdec2c7fa9db77960930031564ab56f12882645",
    ),
]


def digest(path: Path) -> str:
    """Hash a model without loading its bytes into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    """Acquire verified files, then safely extract the speech recognizer."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse-models", type=Path)
    args = parser.parse_args()
    models = ROOT / "models"
    models.mkdir(exist_ok=True)

    def install(asset: tuple[str, str, str]) -> dict[str, str]:
        """Verify a local candidate before copying or fetching an asset."""
        name, url, expected = asset
        dest = models / name
        if dest.exists() and digest(dest) == expected:
            return {"name": name, "url": url, "sha256": expected}
        candidate = args.reuse_models / name if args.reuse_models else None
        if candidate and not candidate.exists() and name == "MODEL_CARD":
            candidate = args.reuse_models / "piper-voice-MODEL_CARD.txt"
        partial = dest.with_suffix(dest.suffix + ".part")
        if candidate and candidate.is_file() and digest(candidate) == expected:
            shutil.copyfile(candidate, partial)
        else:
            with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
                shutil.copyfileobj(response, output)
        if digest(partial) != expected:
            raise RuntimeError(f"Checksum mismatch: {name}")
        partial.replace(dest)
        return {"name": name, "url": url, "sha256": expected}

    with ThreadPoolExecutor(max_workers=3) as pool:
        manifest = list(pool.map(install, ASSETS))
    if not (models / "vosk-model-en-us-0.22-lgraph" / "am" / "final.mdl").exists():
        with zipfile.ZipFile(models / ASSETS[0][0]) as archive:
            for item in archive.infolist():
                if not (models / item.filename).resolve().is_relative_to(models):
                    raise RuntimeError("Unsafe model archive path")
            archive.extractall(models)
    (models / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
