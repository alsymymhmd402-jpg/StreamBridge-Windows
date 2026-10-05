"""Pure helpers for StreamBridge: URL validation, FFmpeg commands and frame FX."""
from __future__ import annotations

from io import BytesIO
from urllib.parse import urlsplit

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SUPPORTED_SCHEMES = {"http", "https", "rtsp", "rtsps"}
AUDIO_SAMPLE_RATE = 48_000
AUDIO_CHANNELS = 2


class InvalidStreamUrl(ValueError):
    """Raised when an input is not a direct HTTP(S)/RTSP(S) URL."""


def validate_stream_url(value: str) -> str:
    """Validate URL syntax only; FFmpeg performs the actual reachability check."""
    raw = (value or "").strip()
    if not raw:
        raise InvalidStreamUrl("Enter a direct RTSP, HLS/M3U8, or HTTP(S) stream URL.")
    try:
        parsed = urlsplit(raw)
        scheme = parsed.scheme.lower()
        if scheme not in SUPPORTED_SCHEMES or not parsed.hostname:
            raise InvalidStreamUrl("Use a complete http(s):// or rtsp(s):// URL.")
        _ = parsed.port
    except ValueError as exc:
        if isinstance(exc, InvalidStreamUrl):
            raise
        raise InvalidStreamUrl("The URL or port is malformed.") from exc
    return raw


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def build_ffmpeg_command(
    ffmpeg_path: str,
    url: str,
    width: int,
    height: int,
    fps: int,
    speed: float = 1.0,
) -> list[str]:
    """Build a raw BGR24 pipe command, optionally changing video playback speed."""
    parsed = urlsplit(validate_stream_url(url))
    speed = clamp(speed, 0.98, 1.03)
    vf = (
        f"setpts=PTS/{speed:.5f},"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=bgr24"
    )
    cmd = [
        ffmpeg_path, "-hide_banner", "-loglevel", "error", "-nostdin",
        "-fflags", "nobuffer", "-flags", "low_delay",
        "-probesize", "1000000", "-analyzeduration", "1000000",
        "-rw_timeout", "15000000",
    ]
    if parsed.scheme.lower() in {"rtsp", "rtsps"}:
        cmd += ["-rtsp_transport", "tcp"]
    else:
        cmd += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
    cmd += [
        "-i", url,
        "-an", "-vf", vf,
        "-fps_mode", "cfr", "-r", str(fps),
        "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1",
    ]
    return cmd


def build_audio_ffmpeg_command(
    ffmpeg_path: str,
    url: str,
    *,
    speed: float = 1.0,
    pitch: float = 1.0,
    volume: float = 0.8,
    sample_rate: int = AUDIO_SAMPLE_RATE,
    channels: int = AUDIO_CHANNELS,
) -> list[str]:
    """Decode source audio to interleaved float PCM; pitch is shifted with duration compensation."""
    parsed = urlsplit(validate_stream_url(url))
    speed = clamp(speed, 0.98, 1.03)
    pitch = clamp(pitch, 0.98, 1.03)
    volume = clamp(volume, 0.0, 1.0)
    pitch_compensation = 1.0 / pitch
    af = (
        f"asetrate={sample_rate}*{pitch:.5f},aresample={sample_rate},"
        f"atempo={pitch_compensation:.5f},atempo={speed:.5f},volume={volume:.3f}"
    )
    cmd = [
        ffmpeg_path, "-hide_banner", "-loglevel", "error", "-nostdin",
        "-flags", "low_delay",
        "-probesize", "1000000", "-analyzeduration", "1000000",
        "-rw_timeout", "15000000",
    ]
    if parsed.scheme.lower() in {"rtsp", "rtsps"}:
        cmd += ["-rtsp_transport", "tcp"]
    else:
        cmd += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
    cmd += [
        "-i", url, "-map", "0:a:0?", "-vn", "-af", af,
        "-ac", str(channels), "-ar", str(sample_rate),
        "-f", "f32le", "pipe:1",
    ]
    return cmd


def apply_visual_adjustments(
    frame: np.ndarray,
    *,
    brightness: float = 0.0,
    contrast: float = 1.0,
    hue_shift: float = 0.0,
) -> np.ndarray:
    """Apply subtle brightness/contrast and HSV hue controls to one BGR frame."""
    contrast = clamp(contrast, 0.85, 1.15)
    brightness = clamp(brightness, -30.0, 30.0)
    hue_shift = clamp(hue_shift, -10.0, 10.0)
    if abs(brightness) < 0.01 and abs(contrast - 1.0) < 0.001 and abs(hue_shift) < 0.01:
        return frame
    output = cv2.addWeighted(frame, contrast, frame, 0.0, brightness)
    shift_units = int(round(hue_shift * 0.5))  # OpenCV's 8-bit HSV hue spans 0..180.
    if shift_units:
        hsv = cv2.cvtColor(output, cv2.COLOR_BGR2HSV)
        hue = hsv[:, :, 0].astype(np.int16)
        hsv[:, :, 0] = ((hue + shift_units) % 180).astype(np.uint8)
        output = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    return np.ascontiguousarray(output)


def apply_pk_overlay(
    frame: np.ndarray,
    *,
    left_score: int = 0,
    right_score: int = 0,
    round_name: str = "PK ROUND",
) -> np.ndarray:
    """Composite a compact score bar in the top safe area; never renders chat or gifts."""
    output = np.ascontiguousarray(frame.copy())
    height, width = output.shape[:2]
    bar_h = max(34, min(72, height // 9))
    overlay = output[:bar_h].copy()
    cv2.rectangle(overlay, (0, 0), (width, bar_h), (12, 18, 31), -1)
    cv2.addWeighted(overlay, 0.92, output[:bar_h], 0.08, 0, output[:bar_h])
    center = width // 2
    cv2.line(output, (center, 6), (center, bar_h - 6), (37, 225, 230), 2)
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(output, f"{int(left_score)}", (max(12, center - width // 4), bar_h - 18), font, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(output, f"{int(right_score)}", (center + width // 8, bar_h - 18), font, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(output, str(round_name)[:24], (12, max(18, bar_h // 3)), font, 0.42, (41, 225, 230), 1, cv2.LINE_AA)
    return output


def read_exact(stream, byte_count: int) -> bytes | None:
    """Read exactly byte_count bytes, supporting partial pipe reads; return None at EOF."""
    buf = bytearray()
    while len(buf) < byte_count:
        part = stream.read(byte_count - len(buf))
        if not part:
            return None
        buf.extend(part)
    return bytes(buf)


def _font(size: int) -> ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_signal_lost_frame(width: int, height: int, phase: int = 0) -> np.ndarray:
    """Create a BGR placeholder frame for the DirectShow camera during outages."""
    image = Image.new("RGB", (width, height), (8, 13, 25))
    draw = ImageDraw.Draw(image)
    accent = (255, 55, 96)
    cyan = (41, 225, 230)
    margin = max(18, width // 24)
    draw.rounded_rectangle(
        (margin, margin, width - margin, height - margin),
        radius=max(12, width // 48), outline=(37, 49, 68), width=max(2, width // 500)
    )
    cx, cy = width // 2, height // 2 - height // 12
    radius = max(22, min(width, height) // 15)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=accent, width=max(3, width // 240))
    bar_w = max(5, radius // 5)
    draw.rounded_rectangle((cx - bar_w, cy - radius // 2, cx + bar_w, cy + radius // 2), radius=bar_w, fill=accent)
    title = "SIGNAL LOST"
    subtitle = "RECONNECTING" + ("." * (phase % 4))
    title_font = _font(max(22, width // 25))
    sub_font = _font(max(12, width // 55))
    for text, font, y, color in (
        (title, title_font, cy + radius + height // 14, (241, 245, 249)),
        (subtitle, sub_font, cy + radius + height // 14 + height // 11, cyan),
    ):
        box = draw.textbbox((0, 0), text, font=font)
        draw.text((cx - (box[2] - box[0]) // 2, y), text, font=font, fill=color)
    rgb = np.asarray(image, dtype=np.uint8)
    return np.ascontiguousarray(rgb[:, :, ::-1])
