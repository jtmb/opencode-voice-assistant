"""CPU speech models and transient PipeWire audio resources."""

from __future__ import annotations

import io
import json
import os
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
RATE = 16000
WAKE = "hey assistant"


def terminate(process: subprocess.Popen[bytes] | None) -> None:
    """Stop a plugin-owned child and reap it."""
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)


class Speech:
    """Own the two local CPU models, without any conversation state."""

    def __init__(self) -> None:
        """Load installed model files and disable ONNX diagnostics."""
        import onnxruntime as ort
        from piper import PiperVoice
        from piper.config import PiperConfig
        from vosk import Model, SetLogLevel

        ort.disable_telemetry_events()
        SetLogLevel(-1)
        self.model: Any = Model(str(MODELS / "vosk-model-en-us-0.22-lgraph"))
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self.voice: Any = PiperVoice(
            session=ort.InferenceSession(
                str(MODELS / "en_US-lessac-medium.onnx"),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            ),
            config=PiperConfig.from_dict(
                json.loads((MODELS / "en_US-lessac-medium.onnx.json").read_text())
            ),
            download_dir=MODELS,
        )

    def recognizer(self, wake: bool = False) -> Any:
        """Create a recognizer for wake detection or a complete spoken request."""
        from vosk import KaldiRecognizer

        recognizer = KaldiRecognizer(self.model, RATE)
        if wake:
            recognizer.SetGrammar(json.dumps([WAKE, "[unk]"]))
        return recognizer

    def synthesize(self, text: str) -> bytes:
        """Return an in-memory WAV; no recordings or generated speech are saved."""
        from piper.config import SynthesisConfig

        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            self.voice.synthesize_wav(
                text,
                wav,
                syn_config=SynthesisConfig(volume=0.65, noise_scale=0.333, noise_w_scale=0.333),
            )
        return output.getvalue()


class EchoAudio:
    """Route only plugin audio through temporary WebRTC echo cancellation."""

    def __init__(self) -> None:
        """Choose private node names; default device metadata is never changed."""
        self.prefix = f"opencode-voice-{os.getpid()}-{time.monotonic_ns()}"
        self.source = self.prefix + "-source"
        self.sink = self.prefix + "-sink"
        self.module: subprocess.Popen[bytes] | None = None
        self.capture: subprocess.Popen[bytes] | None = None
        self.player: subprocess.Popen[bytes] | None = None
        self.player_lock = threading.Lock()

    def start(self) -> None:
        """Load the echo-canceller in a client that is kept alive until close."""
        arguments = (
            "{ library.name = aec/libspa-aec-webrtc audio.rate = 48000 "
            "aec.args = { webrtc.noise_suppression = false webrtc.transient_suppression = false } "
            "audio.channels = 1 audio.position = [ MONO ] node.latency = 480/48000 "
            f'capture.props = {{ node.name = "{self.prefix}-capture" node.passive = true }} '
            f'source.props = {{ node.name = "{self.source}" node.description = "OpenCode Voice Microphone" '
            "node.virtual = true priority.session = 0 } "
            f'sink.props = {{ node.name = "{self.sink}" node.description = "OpenCode Voice Speaker" '
            "node.virtual = true priority.session = 0 } "
            f'playback.props = {{ node.name = "{self.prefix}-playback" node.passive = true }} }}'
        )
        self.module = subprocess.Popen(
            ["pw-cli", "-m", "load-module", "libpipewire-module-echo-cancel", arguments],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(40):
            if self.module.poll() is not None:
                raise RuntimeError("PipeWire echo cancellation could not start")
            result = subprocess.run(["pw-dump"], capture_output=True, timeout=3, check=True)
            nodes = json.loads(result.stdout)
            names = {node.get("info", {}).get("props", {}).get("node.name") for node in nodes}
            if self.source in names and self.sink in names:
                return
            time.sleep(0.1)
        raise RuntimeError("PipeWire echo-cancellation nodes did not appear")

    def record(self) -> subprocess.Popen[bytes]:
        """Capture 16 kHz signed PCM from the echo-cancelled source."""
        self.capture = subprocess.Popen(
            [
                "pw-cat",
                "--record",
                "--raw",
                "--rate",
                str(RATE),
                "--channels",
                "1",
                "--format",
                "s16",
                "--target",
                self.source,
                "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return self.capture

    def play(self, audio: bytes, valid: threading.Event) -> None:
        """Play WAV into the echo reference sink, unless already interrupted."""
        with self.player_lock:
            if not valid.is_set():
                return
            self.player = subprocess.Popen(
                ["pw-cat", "--playback", "--target", self.sink, "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            player = self.player
        try:
            player.communicate(audio)
            if player.returncode and valid.is_set():
                raise RuntimeError("PipeWire speaker playback failed")
        finally:
            terminate(player)
            with self.player_lock:
                if self.player is player:
                    self.player = None

    def stop_playback(self) -> None:
        """Interrupt audio immediately without affecting OpenCode execution."""
        with self.player_lock:
            terminate(self.player)

    def close(self) -> None:
        """Remove only resources owned by this audio worker."""
        self.stop_playback()
        terminate(self.capture)
        terminate(self.module)
        if self.module and self.module.stdin:
            self.module.stdin.close()
