"""JSON-lines audio subprocess. No model requests, tools or conversation history."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import queue
import selectors
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable

from audio.runtime import ROOT, WAKE, EchoAudio, Speech, terminate

Event = dict[str, str | int]
Emit = Callable[[Event], None]


def command(line: str) -> dict[str, object]:
    """Validate the narrow audio-only control protocol."""
    value: object = json.loads(line)
    if not isinstance(value, dict):
        raise TypeError("Command must be an object")
    kind = value.get("type")
    if kind not in {"configure", "listen", "cancel", "speak", "stop_playback", "shutdown"}:
        raise ValueError("Unknown audio command")
    if kind in {"configure", "listen", "cancel", "speak"} and (
        type(value.get("epoch")) is not int or value["epoch"] < 0
    ):
        raise ValueError("Invalid session epoch")
    if kind == "configure" and type(value.get("enabled")) is not bool:
        raise ValueError("Invalid microphone setting")
    if kind == "speak" and (
        not isinstance(value.get("text"), str) or not 0 < len(value["text"]) <= 16384
    ):
        raise ValueError("Invalid speech text")
    return value


class Worker:
    """Coordinate continuous wake detection with interruptible speech playback."""

    def __init__(self, speech: Speech, audio: EchoAudio, emit: Emit) -> None:
        """Start disabled until the TUI selects a session and configures voice."""
        self.speech = speech
        self.audio = audio
        self.emit = emit
        self.closed = threading.Event()
        self.epoch = 0
        self.enabled = False
        self.listen_sequence = 0
        self.manual = False
        self.lock = threading.RLock()
        self.play_valid = threading.Event()
        self.play_valid.set()
        self.pending: queue.Queue[tuple[int, threading.Event, str] | None] = queue.Queue(64)
        self.threads: list[threading.Thread] = []

    def start(self) -> None:
        """Start the two bounded background audio loops."""
        self.threads = [
            threading.Thread(target=self.capture_loop, daemon=True),
            threading.Thread(target=self.playback_loop, daemon=True),
        ]
        for thread in self.threads:
            thread.start()

    def stop_playback(self) -> None:
        """Invalidate queued and in-flight synthesis before stopping the player."""
        with self.lock:
            self.play_valid.clear()
            self.play_valid = threading.Event()
            self.play_valid.set()
            while True:
                try:
                    self.pending.get_nowait()
                except queue.Empty:
                    break
            self.audio.stop_playback()

    def handle(self, value: dict[str, object]) -> None:
        """Apply a validated command without blocking microphone processing."""
        kind = value["type"]
        if kind == "shutdown":
            self.closed.set()
        elif kind == "stop_playback":
            self.stop_playback()
        elif kind in {"configure", "listen", "cancel"}:
            epoch = int(str(value["epoch"]))
            with self.lock:
                if epoch < self.epoch:
                    return
                changed = epoch != self.epoch
                self.epoch = epoch
                if changed or kind == "cancel":
                    self.manual = False
                    self.listen_sequence += 1
                    self.stop_playback()
                if kind == "configure":
                    self.enabled = value["enabled"] is True
                    if not self.enabled:
                        self.manual = False
                        self.listen_sequence += 1
                        self.stop_playback()
                        self.emit({"type": "state", "state": "Microphone off"})
                if kind == "listen":
                    self.manual = True
                    self.listen_sequence += 1
        elif kind == "speak":
            with self.lock:
                if value["epoch"] != self.epoch:
                    return
                try:
                    self.pending.put_nowait((self.epoch, self.play_valid, str(value["text"])))
                except queue.Full:
                    self.stop_playback()
                    self.emit(
                        {"type": "error", "message": "Speech queue is full; playback stopped."}
                    )

    def snapshot(self) -> tuple[int, bool, int, bool]:
        """Read routing and microphone preferences atomically."""
        with self.lock:
            return self.epoch, self.enabled, self.listen_sequence, self.manual

    def playback_loop(self) -> None:
        """Synthesize serially while capture continues on another thread."""
        try:
            while not self.closed.is_set():
                try:
                    item = self.pending.get(timeout=0.2)
                except queue.Empty:
                    continue
                if item is None:
                    return
                epoch, valid, text = item
                if epoch != self.epoch or not valid.is_set():
                    continue
                self.emit({"type": "state", "state": "Speaking"})
                audio = self.speech.synthesize(text)
                if epoch == self.epoch and valid.is_set():
                    self.audio.play(audio, valid)
                if self.pending.empty():
                    self.emit(
                        {
                            "type": "state",
                            "state": "Waiting for hey assistant"
                            if self.enabled
                            else "Microphone off",
                        }
                    )
        except (OSError, RuntimeError, ValueError) as error:
            self.emit({"type": "error", "message": str(error)})
            self.closed.set()

    def capture_loop(self) -> None:
        """Own the microphone lock and switch recognizers after each wake phrase."""
        state = ROOT / "state"
        state.mkdir(exist_ok=True)
        with (state / "microphone.lock").open("a") as ownership:
            while not self.closed.is_set():
                epoch, enabled, sequence, manual = self.snapshot()
                if not enabled and not manual:
                    self.closed.wait(0.1)
                    continue
                try:
                    fcntl.flock(ownership, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    self.emit(
                        {"type": "state", "state": "Microphone owned by another OpenCode TUI"}
                    )
                    self.closed.wait(1)
                    continue
                try:
                    self.capture(epoch, sequence, manual)
                except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
                    self.emit({"type": "error", "message": str(error)})
                    self.closed.set()
                finally:
                    terminate(self.audio.capture)
                    if self.audio.capture and self.audio.capture.stdout:
                        self.audio.capture.stdout.close()
                    fcntl.flock(ownership, fcntl.LOCK_UN)

    def capture(self, epoch: int, sequence: int, manual: bool) -> None:
        """Read PCM continuously; all resulting events retain their session epoch."""
        recorder = self.audio.record()
        if recorder.stdout is None:
            raise RuntimeError("Microphone stream is unavailable")
        listening = manual
        recognizer = self.speech.recognizer(wake=not listening)
        started = time.monotonic()
        heard = False
        self.emit(
            {"type": "state", "state": "Listening" if listening else "Waiting for hey assistant"}
        )
        with selectors.DefaultSelector() as selector:
            selector.register(recorder.stdout, selectors.EVENT_READ)
            while not self.closed.is_set():
                current_epoch, enabled, current_sequence, current_manual = self.snapshot()
                if epoch != current_epoch or sequence != current_sequence:
                    return
                if not enabled and not current_manual:
                    return
                if not selector.select(0.1):
                    if recorder.poll() is not None:
                        raise RuntimeError("The microphone stream stopped")
                    continue
                data = os.read(recorder.stdout.fileno(), 4000)
                if not data:
                    raise RuntimeError("The microphone stream returned no audio")
                final = recognizer.AcceptWaveform(data)
                result = json.loads(recognizer.Result() if final else recognizer.PartialResult())
                text = result.get("text" if final else "partial", "")
                if not listening:
                    if WAKE not in text:
                        continue
                    self.stop_playback()
                    self.emit({"type": "wake", "epoch": epoch})
                    self.emit({"type": "state", "state": "Listening"})
                    listening = True
                    recognizer = self.speech.recognizer()
                    started = time.monotonic()
                    heard = False
                    continue
                if text:
                    heard = True
                    self.emit({"type": "partial", "epoch": epoch, "text": text})
                elapsed = time.monotonic() - started
                if (final and text) or elapsed > 25 or (not heard and elapsed > 8):
                    if not final:
                        text = json.loads(recognizer.FinalResult()).get("text", "")
                    self.emit({"type": "transcript", "epoch": epoch, "text": text})
                    with self.lock:
                        self.manual = False
                    if not enabled:
                        return
                    listening = False
                    recognizer = self.speech.recognizer(wake=True)
                    self.emit({"type": "state", "state": "Waiting for hey assistant"})

    def close(self) -> None:
        """Stop threads and release plugin-owned devices and echo nodes."""
        self.closed.set()
        self.stop_playback()
        terminate(self.audio.capture)
        for thread in self.threads:
            thread.join(timeout=3)
        self.audio.close()


def main() -> None:
    """Read commands until stdin closes, then tear down every audio resource."""
    if os.environ.get("OPENCODE_VOICE_OFFLINE") != "1":
        raise RuntimeError("Start through scripts/audio-worker.sh for offline isolation")
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    output_lock = threading.Lock()

    def emit(event: Event) -> None:
        """Serialize protocol events from multiple audio threads."""
        with output_lock:
            sys.stdout.write(json.dumps(event) + "\n")
            sys.stdout.flush()

    audio = EchoAudio()
    worker: Worker | None = None
    try:
        speech = Speech()
        audio.start()
        worker = Worker(speech, audio, emit)
        signal.signal(
            signal.SIGTERM, lambda _number, _frame: worker.closed.set() if worker else None
        )
        signal.signal(
            signal.SIGINT, lambda _number, _frame: worker.closed.set() if worker else None
        )
        worker.start()
        emit({"type": "ready"})
        buffer = b""
        with selectors.DefaultSelector() as selector:
            selector.register(sys.stdin, selectors.EVENT_READ)
            while not worker.closed.is_set():
                if not selector.select(0.2):
                    continue
                chunk = os.read(sys.stdin.fileno(), 65536)
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > 65536:
                    raise ValueError("Audio command exceeds size limit")
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    worker.handle(command(line.decode()))
    except (OSError, RuntimeError, ValueError, TypeError, subprocess.SubprocessError) as error:
        emit({"type": "error", "message": str(error)})
    finally:
        if worker:
            worker.close()
        else:
            audio.close()


if __name__ == "__main__":
    main()
