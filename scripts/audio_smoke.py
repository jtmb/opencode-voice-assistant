#!/usr/bin/env python3
"""Verify real speech, echo suppression and interruption on the local laptop."""

from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from audio.runtime import RATE, EchoAudio, Speech, terminate
from audio.worker import Event, Worker


def main() -> None:
    """Exercise the production audio classes inside their offline namespace."""
    if os.environ.get("OPENCODE_VOICE_OFFLINE") != "1":
        args = [
            "bwrap",
            "--unshare-net",
            "--unshare-pid",
            "--bind",
            "/",
            "/",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--die-with-parent",
            "--chdir",
            str(ROOT),
            "--setenv",
            "OPENCODE_VOICE_OFFLINE",
            "1",
            sys.executable,
            str(Path(__file__).resolve()),
        ]
        os.execvp("bwrap", args)
    import numpy as np

    started = time.monotonic()
    speech = Speech()
    report: dict[str, object] = {"model_load_seconds": round(time.monotonic() - started, 3)}
    started = time.monotonic()
    wav_data = speech.synthesize("What is the capital of France?")
    report["sentence_synthesis_seconds"] = round(time.monotonic() - started, 3)
    with wave.open(io.BytesIO(wav_data), "rb") as wav:
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
        positions = (
            np.arange(round(len(samples) * RATE / wav.getframerate())) * wav.getframerate() / RATE
        )
        pcm = np.interp(positions, np.arange(len(samples)), samples).astype("<i2").tobytes()
    recognizer = speech.recognizer()
    recognized = []
    for offset in range(0, len(pcm), 4000):
        if recognizer.AcceptWaveform(pcm[offset : offset + 4000]):
            recognized.append(json.loads(recognizer.Result()).get("text", ""))
    recognized.append(json.loads(recognizer.FinalResult()).get("text", ""))
    transcript = " ".join(recognized)
    assert "capital" in transcript and "france" in transcript, transcript
    report["synthetic_question_recognized"] = True
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=1)
        raise AssertionError("Speech worker has external network access")
    except OSError:
        report["external_network_blocked"] = True
    audio = EchoAudio()
    events: list[Event] = []
    event_lock = threading.Lock()

    def emit(event: Event) -> None:
        """Retain event types for testing without saving microphone transcripts."""
        with event_lock:
            events.append(event)

    worker = Worker(speech, audio, emit)
    try:
        audio.start()
        worker.start()
        worker.handle({"type": "configure", "epoch": 1, "enabled": True})
        deadline = time.monotonic() + 8
        while audio.capture is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert audio.capture is not None, events
        worker.handle(
            {
                "type": "speak",
                "epoch": 1,
                "text": "The local audio system is running. The microphone uses echo cancellation. "
                "The wake phrase is hey assistant. This spoken test should not activate it.",
            }
        )
        deadline = time.monotonic() + 25
        saw_playback = False
        saw_player = False
        while time.monotonic() < deadline:
            with event_lock:
                if any(event.get("state") == "Speaking" for event in events):
                    saw_playback = True
                saw_player = saw_player or audio.player is not None
                completed = saw_player and audio.player is None and worker.pending.empty()
            if completed:
                time.sleep(1)
                break
            time.sleep(0.1)
        assert saw_playback, "No speaker playback occurred"
        with event_lock:
            self_wakes = sum(event["type"] == "wake" for event in events)
        report["self_wake_count"] = self_wakes
        assert self_wakes == 0, "The assistant triggered its own wake detector"
        worker.handle(
            {
                "type": "speak",
                "epoch": 1,
                "text": "This longer reply checks hands-free interruption while local audio is speaking. "
                * 5,
            }
        )
        deadline = time.monotonic() + 12
        while audio.player is None and time.monotonic() < deadline:
            time.sleep(0.05)
        interrupted_player = audio.player
        assert interrupted_player is not None, "Long reply did not start"
        # External playback bypasses our echo reference, simulating a second speaker.
        user_audio = speech.synthesize("Hey assistant.")
        external = subprocess.Popen(
            ["pw-cat", "--playback", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            external.communicate(user_audio, timeout=8)
        finally:
            terminate(external)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with event_lock:
                if any(event["type"] == "wake" for event in events):
                    break
            time.sleep(0.1)
        with event_lock:
            report["external_wake_detected"] = any(event["type"] == "wake" for event in events)
        assert report["external_wake_detected"], "External wake phrase was not recognized"
        assert interrupted_player.poll() is not None and interrupted_player.returncode != 0
        report["playback_interrupted_by_wake"] = True
        worker.handle({"type": "configure", "epoch": 1, "enabled": False})
        deadline = time.monotonic() + 3
        while audio.capture and audio.capture.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert audio.capture is not None and audio.capture.poll() is not None
        report["microphone_released_when_disabled"] = True
        report["passed"] = True
    finally:
        worker.close()
        nodes = json.loads(subprocess.check_output(["pw-dump"]))
        assert not any(
            audio.prefix in str(node.get("info", {}).get("props", {}).get("node.name", ""))
            for node in nodes
        )
        (ROOT / "state").mkdir(exist_ok=True)
        (ROOT / "state" / "audio-smoke.json").write_text(json.dumps(report, indent=2) + "\n")
        sys.stdout.write(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
