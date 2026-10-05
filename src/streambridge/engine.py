"""Background FFmpeg decoding and UnityCapture output, isolated from the UI thread."""
from __future__ import annotations

import os
import queue
import subprocess
import threading
import time
from typing import Callable

import numpy as np
import pyvirtualcam
from imageio_ffmpeg import get_ffmpeg_exe

from .audio import AudioRelay
from .core import apply_visual_adjustments, build_ffmpeg_command, make_signal_lost_frame, read_exact

WIDTH = 1280
HEIGHT = 720
DEFAULT_SETTINGS = {
    "width": WIDTH,
    "height": HEIGHT,
    "fps": 30,
    "camera_device": "Unity Video Capture",
    "brightness": 0.0,
    "contrast": 1.0,
    "hue_shift": 0.0,
    "speed": 1.0,
    "audio_enabled": False,
    "audio_device": None,
    "audio_pitch": 1.0,
    "audio_volume": 0.8,
}
RECONNECT_MIN_SECONDS = 1.0
RECONNECT_MAX_SECONDS = 15.0
SIGNAL_LOST_AFTER_SECONDS = 2.0


def _replace_latest(target: queue.Queue, item) -> None:
    """Keep only the newest item, so a slow UI/camera never builds latency."""
    try:
        target.put_nowait(item)
        return
    except queue.Full:
        pass
    try:
        target.get_nowait()
    except queue.Empty:
        pass
    try:
        target.put_nowait(item)
    except queue.Full:
        pass


class FFmpegDecoder(threading.Thread):
    """Reads raw BGR frames and reconnects when the input ends or settings change."""

    def __init__(
        self,
        url: str,
        frames: queue.Queue,
        events: queue.Queue,
        stop_event: threading.Event,
        settings_provider: Callable[[], dict] | None = None,
    ):
        super().__init__(name="FFmpegDecoder", daemon=True)
        self.url = url
        self.frames = frames
        self.events = events
        self.stop_event = stop_event
        self.settings_provider = settings_provider or (lambda: dict(DEFAULT_SETTINGS))
        self._process: subprocess.Popen | None = None
        self._process_lock = threading.Lock()
        self._reconfigure = threading.Event()

    def request_reconfigure(self) -> None:
        self._reconfigure.set()
        with self._process_lock:
            proc = self._process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def stop(self) -> None:
        self.stop_event.set()
        with self._process_lock:
            proc = self._process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def run(self) -> None:
        backoff = RECONNECT_MIN_SECONDS
        try:
            ffmpeg = get_ffmpeg_exe()
        except Exception as exc:
            self.events.put(("fatal", f"FFmpeg runtime is missing: {type(exc).__name__}"))
            self.stop_event.set()
            self.events.put(("decoder_finished", None))
            return

        while not self.stop_event.is_set():
            self.events.put(("status", "Connecting to stream…"))
            proc = None
            got_frame = False
            try:
                settings = self.settings_provider()
                width = int(settings["width"])
                height = int(settings["height"])
                cmd = build_ffmpeg_command(
                    ffmpeg, self.url, width, height, int(settings["fps"]), float(settings.get("speed", 1.0))
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
                assert proc.stdout is not None
                frame_bytes = width * height * 3
                while not self.stop_event.is_set():
                    raw = read_exact(proc.stdout, frame_bytes)
                    if raw is None:
                        break
                    frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 3)).copy()
                    _replace_latest(self.frames, frame)
                    if not got_frame:
                        got_frame = True
                        backoff = RECONNECT_MIN_SECONDS
                        self.events.put(("status", "Live stream connected — sending frames"))
                if proc.poll() is None:
                    try:
                        proc.terminate()
                    except OSError:
                        pass
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception as exc:
                self.events.put(("status", f"Stream open failed ({type(exc).__name__}); retrying"))
                if proc and proc.poll() is None:
                    try:
                        proc.kill()
                    except OSError:
                        pass
            finally:
                with self._process_lock:
                    if self._process is proc:
                        self._process = None
                if proc and proc.stdout:
                    try:
                        proc.stdout.close()
                    except OSError:
                        pass

            if self.stop_event.is_set():
                break
            if self._reconfigure.is_set():
                self._reconfigure.clear()
                backoff = RECONNECT_MIN_SECONDS
                self.events.put(("status", "Applying speed setting — reconnecting decoder"))
                continue
            self.events.put(("status", "Signal lost — reconnecting"))
            deadline = time.monotonic() + backoff
            while not self.stop_event.is_set() and not self._reconfigure.is_set() and time.monotonic() < deadline:
                self.stop_event.wait(min(0.1, max(0.0, deadline - time.monotonic())))
            if self.stop_event.is_set():
                break
            if self._reconfigure.is_set():
                self._reconfigure.clear()
                backoff = RECONNECT_MIN_SECONDS
                self.events.put(("status", "Applying speed setting — reconnecting decoder"))
                continue
            backoff = min(RECONNECT_MAX_SECONDS, backoff * 2.0)
        self.events.put(("decoder_finished", None))


class StreamBridgeEngine(threading.Thread):
    """Feeds UnityCapture steadily; hidden preview never interrupts camera output."""

    def __init__(
        self,
        url: str,
        settings: dict | None = None,
        camera_factory=None,
        decoder_factory=None,
        audio_relay_factory=None,
    ):
        super().__init__(name="VirtualCameraOutput", daemon=True)
        self.url = url
        self.camera_factory = camera_factory or pyvirtualcam.Camera
        self.decoder_factory = decoder_factory or FFmpegDecoder
        self.audio_relay_factory = audio_relay_factory or AudioRelay
        self.stop_event = threading.Event()
        self.preview_enabled = threading.Event()
        self.preview_enabled.set()
        self.events: queue.Queue = queue.Queue()
        self.preview_frames: queue.Queue = queue.Queue(maxsize=1)
        self._decoded_frames: queue.Queue = queue.Queue(maxsize=1)
        self._settings_lock = threading.RLock()
        self._settings = dict(DEFAULT_SETTINGS)
        if settings:
            self._settings.update(settings)
        self.decoder: FFmpegDecoder | None = None
        self.audio_relay: AudioRelay | None = None
        self._last_frame: np.ndarray | None = None
        self._last_frame_at = 0.0
        self._frames_sent = 0

    def settings_snapshot(self) -> dict:
        with self._settings_lock:
            return dict(self._settings)

    def update_adjustments(self, **values) -> None:
        """Apply visual FX live and restart only the relevant decoder for tempo/pitch changes."""
        with self._settings_lock:
            previous = dict(self._settings)
            self._settings.update(values)
            current = dict(self._settings)
        if abs(float(previous.get("speed", 1.0)) - float(current.get("speed", 1.0))) > 0.0001:
            if self.decoder:
                self.decoder.request_reconfigure()
        audio_keys = ("audio_enabled", "audio_device", "audio_pitch", "audio_volume", "speed")
        if any(previous.get(key) != current.get(key) for key in audio_keys) and self.audio_relay:
            self.audio_relay.request_reconfigure()
        if current.get("audio_enabled") and self.audio_relay is None and self.is_alive():
            self._start_audio_relay()

    def set_preview_enabled(self, enabled: bool) -> None:
        if enabled:
            self.preview_enabled.set()
        else:
            self.preview_enabled.clear()
            while True:
                try:
                    self.preview_frames.get_nowait()
                except queue.Empty:
                    break

    def request_stop(self) -> None:
        self.stop_event.set()
        if self.decoder:
            self.decoder.stop()
        if self.audio_relay:
            self.audio_relay.request_stop()

    def _start_audio_relay(self) -> None:
        if self.audio_relay is not None and self.audio_relay.is_alive():
            return
        self.audio_relay = self.audio_relay_factory(self.url, self.settings_snapshot, self.events)
        self.audio_relay.start()

    def _publish_preview(self, frame: np.ndarray) -> None:
        if self.preview_enabled.is_set():
            _replace_latest(self.preview_frames, frame.copy())

    def run(self) -> None:
        initial = self.settings_snapshot()
        width = int(initial.get("width", 1280))
        height = int(initial.get("height", 720))
        fps = int(initial.get("fps", 30))
        device = str(initial.get("camera_device", "Unity Video Capture"))
        self.events.put(("status", "Starting UnityCapture virtual camera…"))
        try:
            with self.camera_factory(
                width=width,
                height=height,
                fps=fps,
                fmt=pyvirtualcam.PixelFormat.BGR,
                backend="unitycapture",
                device=device,
            ) as camera:
                self.events.put(("camera", f"{camera.device} · {camera.backend}"))
                self.events.put(("status", "Virtual camera ready — opening stream"))
                self.decoder = self.decoder_factory(
                    self.url, self._decoded_frames, self.events, self.stop_event, self.settings_snapshot
                )
                self.decoder.start()
                if self.settings_snapshot().get("audio_enabled"):
                    self._start_audio_relay()
                next_metrics = time.monotonic()
                last_placeholder_phase = -1
                placeholder = make_signal_lost_frame(width, height, 0)
                last_preview_at = 0.0
                while not self.stop_event.is_set():
                    now = time.monotonic()
                    try:
                        self._last_frame = self._decoded_frames.get_nowait()
                        self._last_frame_at = now
                    except queue.Empty:
                        pass
                    live = self._last_frame is not None and (now - self._last_frame_at) <= SIGNAL_LOST_AFTER_SECONDS
                    if live:
                        raw_frame = self._last_frame
                        settings = self.settings_snapshot()
                        if settings.get("visual_enabled", True):
                            output = apply_visual_adjustments(
                                raw_frame,
                                brightness=float(settings.get("brightness", 0.0)),
                                contrast=float(settings.get("contrast", 1.0)),
                                hue_shift=float(settings.get("hue_shift", 0.0)),
                            )
                        else:
                            output = raw_frame
                    else:
                        phase = int(now) % 4
                        if phase != last_placeholder_phase:
                            placeholder = make_signal_lost_frame(width, height, phase)
                            last_placeholder_phase = phase
                        output = placeholder
                    camera.send(output)
                    self._frames_sent += 1
                    if self.preview_enabled.is_set() and now - last_preview_at >= 1.0 / 15.0:
                        self._publish_preview(output)
                        last_preview_at = now
                    if now >= next_metrics:
                        self.events.put(("metrics", {
                            "fps": float(camera.current_fps),
                            "frames": int(camera.frames_sent),
                            "signal": "LIVE" if live else "RECONNECTING",
                            "resolution": f"{width}×{height}",
                            "target_fps": fps,
                        }))
                        next_metrics = now + 1.0
                    camera.sleep_until_next_frame()
        except Exception as exc:
            self.events.put(("fatal", f"Virtual camera unavailable: {type(exc).__name__}: {exc}"))
        finally:
            self.request_stop()
            if self.decoder and self.decoder.is_alive():
                self.decoder.join(timeout=2.0)
            if self.audio_relay and self.audio_relay.is_alive():
                self.audio_relay.join(timeout=2.0)
            self.events.put(("finished", self._frames_sent))
