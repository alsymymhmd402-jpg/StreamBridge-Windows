"""Audio relay to a Windows output endpoint (for example VB-CABLE's CABLE Input)."""
from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Callable

from imageio_ffmpeg import get_ffmpeg_exe

from .core import AUDIO_CHANNELS, AUDIO_SAMPLE_RATE, build_audio_ffmpeg_command, read_exact

AUDIO_BLOCK_FRAMES = 1024
AUDIO_BLOCK_BYTES = AUDIO_BLOCK_FRAMES * AUDIO_CHANNELS * 4  # float32 PCM


def list_output_devices() -> list[dict[str, object]]:
    """Return PortAudio output endpoints; a virtual cable appears as an output device."""
    import sounddevice as sd

    result = []
    for index, device in enumerate(sd.query_devices()):
        channels = int(device.get("max_output_channels", 0))
        if channels >= AUDIO_CHANNELS:
            result.append({"index": index, "name": str(device.get("name", f"Output {index}")), "channels": channels})
    return result


class AudioRelay(threading.Thread):
    """Decode source audio separately and send it to a selectable PortAudio output endpoint."""

    def __init__(self, url: str, settings_provider: Callable[[], dict], events):
        super().__init__(name="AudioRelay", daemon=True)
        self.url = url
        self.settings_provider = settings_provider
        self.events = events
        self.stop_event = threading.Event()
        self._reconfigure = threading.Event()
        self._process: subprocess.Popen | None = None
        self._process_lock = threading.Lock()
        self._last_error = ""

    def request_reconfigure(self) -> None:
        """Restart the audio decoder when pitch, tempo, volume, or device changes."""
        self._reconfigure.set()
        self._terminate_process()

    def request_stop(self) -> None:
        self.stop_event.set()
        self._terminate_process()

    def _terminate_process(self) -> None:
        with self._process_lock:
            proc = self._process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def _spawn(self, ffmpeg: str, settings: dict) -> subprocess.Popen:
        cmd = build_audio_ffmpeg_command(
            ffmpeg,
            self.url,
            speed=float(settings.get("speed", 1.0)),
            pitch=float(settings.get("audio_pitch", 1.0)),
            volume=float(settings.get("audio_volume", 0.8)),
        )
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "bufsize": 0,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(cmd, **kwargs)
        with self._process_lock:
            self._process = proc
        return proc

    def _clear_process(self, proc: subprocess.Popen | None) -> None:
        with self._process_lock:
            if self._process is proc:
                self._process = None
        if proc:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=0.5)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        proc.kill()
                    except OSError:
                        pass
            if proc.stdout:
                try:
                    proc.stdout.close()
                except OSError:
                    pass

    def run(self) -> None:
        try:
            import sounddevice as sd
            ffmpeg = get_ffmpeg_exe()
        except Exception as exc:
            self.events.put(("audio_error", f"Audio runtime unavailable ({type(exc).__name__})"))
            return

        backoff = 1.0
        last_wait_status = None
        while not self.stop_event.is_set():
            settings = self.settings_provider()
            if not settings.get("audio_enabled") or settings.get("audio_device") is None:
                waiting_status = (
                    "Audio output disabled" if not settings.get("audio_enabled")
                    else "Audio enabled — choose a virtual audio output device"
                )
                if waiting_status != last_wait_status:
                    self.events.put(("audio_status", waiting_status))
                    last_wait_status = waiting_status
                self.stop_event.wait(0.5)
                continue

            last_wait_status = None
            proc = None
            try:
                device_index = int(settings["audio_device"])
                device_info = sd.query_devices(device_index)
                device_name = str(device_info.get("name", f"Output {device_index}"))
                if int(device_info.get("max_output_channels", 0)) < AUDIO_CHANNELS:
                    raise RuntimeError("Selected audio endpoint does not support stereo output")
                with sd.RawOutputStream(
                    samplerate=AUDIO_SAMPLE_RATE,
                    blocksize=AUDIO_BLOCK_FRAMES,
                    device=device_index,
                    channels=AUDIO_CHANNELS,
                    dtype="float32",
                    latency="low",
                ) as output_stream:
                    self.events.put(("audio_status", f"Audio route ready · {device_name}"))
                    proc = self._spawn(ffmpeg, settings)
                    assert proc.stdout is not None
                    first_block = True
                    while not self.stop_event.is_set():
                        current = self.settings_provider()
                        if (
                            not current.get("audio_enabled")
                            or current.get("audio_device") != settings.get("audio_device")
                            or abs(float(current.get("audio_pitch", 1.0)) - float(settings.get("audio_pitch", 1.0))) > 0.0001
                            or abs(float(current.get("audio_volume", 0.8)) - float(settings.get("audio_volume", 0.8))) > 0.001
                            or abs(float(current.get("speed", 1.0)) - float(settings.get("speed", 1.0))) > 0.0001
                        ):
                            break
                        raw = read_exact(proc.stdout, AUDIO_BLOCK_BYTES)
                        if raw is None:
                            break
                        output_stream.write(raw)
                        if first_block:
                            first_block = False
                            backoff = 1.0
                            self.events.put(("audio_status", f"Audio live · {device_name}"))
                reconnect_now = self._reconfigure.is_set()
                self._reconfigure.clear()
                self._clear_process(proc)
                proc = None
                if self.stop_event.is_set():
                    break
                if reconnect_now:
                    continue
                self.events.put(("audio_status", "Audio source ended or has no audio track · retrying"))
            except Exception as exc:
                self._clear_process(proc)
                proc = None
                message = f"Audio route unavailable ({type(exc).__name__}: {exc})"
                if message != self._last_error:
                    self.events.put(("audio_error", message))
                    self._last_error = message
            if not self.stop_event.is_set():
                self.stop_event.wait(backoff)
                backoff = min(8.0, backoff * 2.0)
        self._clear_process(proc)
        self.events.put(("audio_status", "Audio route stopped"))
