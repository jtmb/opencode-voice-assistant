"""Protocol and real worker orchestration, isolating audio device boundaries."""

import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from audio.worker import Worker, command


class FakeSpeech:
    """Represent the model I/O boundary without loading model weights."""

    def synthesize(self, text: str) -> bytes:
        """Encode a test sentence to inspect cancellation behavior."""
        return text.encode()


class FakeAudio:
    """Represent physical audio devices for worker state tests."""

    capture = None

    def __init__(self) -> None:
        """Record only playback counts, not private speech."""
        self.stops = 0
        self.played: list[bytes] = []

    def stop_playback(self) -> None:
        """Count an interruption without stopping any actual task."""
        self.stops += 1

    def play(self, data: bytes, valid: threading.Event) -> None:
        """Record audio only if its cancellation token is still valid."""
        if valid.is_set():
            self.played.append(data)

    def close(self) -> None:
        """Leave real device state untouched."""


@pytest.mark.parametrize(
    "line",
    [
        "{}",
        "[]",
        '{"type":"shell"}',
        '{"type":"configure","epoch":true,"enabled":true}',
        '{"type":"configure","epoch":1,"enabled":"true"}',
        '{"type":"speak","epoch":1,"text":""}',
    ],
)
def test_invalid_commands_are_rejected(line: str) -> None:
    """Reject malformed and non-audio commands at the protocol boundary."""
    with pytest.raises((ValueError, TypeError)):
        command(line)


def test_session_epoch_discards_stale_speech_and_cancels_old_queue() -> None:
    """A session switch cannot leak queued speech into another conversation."""
    audio: Any = FakeAudio()
    speech: Any = FakeSpeech()
    worker = Worker(speech, audio, lambda event: None)
    worker.handle(command('{"type":"configure","epoch":1,"enabled":true}'))
    worker.handle(command('{"type":"speak","epoch":1,"text":"Old reply"}'))
    old_token = worker.play_valid
    worker.handle(command('{"type":"cancel","epoch":2}'))
    assert not old_token.is_set()
    assert worker.pending.empty()
    worker.handle(command('{"type":"speak","epoch":1,"text":"Stale reply"}'))
    assert worker.pending.empty()
    worker.handle(command('{"type":"listen","epoch":2}'))
    assert worker.epoch == 2
    assert worker.enabled and worker.manual
    worker.handle(command('{"type":"configure","epoch":2,"enabled":false}'))
    assert not worker.manual
    assert not worker.enabled
    worker.close()
    assert worker.closed.is_set()


def test_microphone_eof_reports_failure_and_releases_ownership(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failed capture cannot leave a phantom listening state or held lock."""

    class EmptySpeech(FakeSpeech):
        """The recognizer is never fed because the device returns EOF."""

        def recognizer(self, wake: bool = False) -> object:
            """Return a placeholder at the model I/O boundary."""
            return object()

    class EmptyAudio(FakeAudio):
        """Provide a real EOF pipe instead of a microphone device."""

        def record(self) -> subprocess.Popen[bytes]:
            """Create and own an immediately closing device pipe."""
            self.capture = subprocess.Popen([sys.executable, "-c", "pass"], stdout=subprocess.PIPE)
            return self.capture

    monkeypatch.setattr("audio.worker.ROOT", tmp_path)
    events: list[dict[str, str | int]] = []
    audio: Any = EmptyAudio()
    speech: Any = EmptySpeech()
    worker = Worker(speech, audio, events.append)
    worker.handle(command('{"type":"configure","epoch":1,"enabled":true}'))
    worker.start()
    assert worker.closed.wait(3)
    worker.close()
    assert any(
        event.get("type") == "error" and "microphone" in str(event.get("message")).lower()
        for event in events
    )
    assert audio.capture.poll() is not None
