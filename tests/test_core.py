import io
import unittest

import numpy as np

from streambridge.core import (
    InvalidStreamUrl,
    apply_visual_adjustments,
    apply_pk_overlay,
    build_audio_ffmpeg_command,
    build_ffmpeg_command,
    make_signal_lost_frame,
    read_exact,
    validate_stream_url,
)
from streambridge.resolver import classify_input_url, normalize_input_url, resolve_stream_url


class StreamCoreTests(unittest.TestCase):
    def test_accepts_direct_web_and_rtsp_streams(self):
        values = [
            "https://example.test/live/index.m3u8?token=abc",
            "http://127.0.0.1:8080/live.m3u8",
            "rtsp://camera.example.test:554/live",
            "rtsps://camera.example.test/live",
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(validate_stream_url(value), value)

    def test_rejects_share_page_without_supported_scheme_and_bad_port(self):
        for value in ("", "tiktok.com/@user/live", "file:///tmp/video.mp4", "ftp://host/video", "http://host:bad/live"):
            with self.subTest(value=value):
                with self.assertRaises(InvalidStreamUrl):
                    validate_stream_url(value)

    def test_builds_tcp_rtsp_command_and_raw_bgr_output(self):
        cmd = build_ffmpeg_command("ffmpeg.exe", "rtsp://host/live", 1280, 720, 30, speed=1.02)
        self.assertIn("-rtsp_transport", cmd)
        self.assertIn("tcp", cmd)
        self.assertIn("bgr24", cmd)
        self.assertIn("PTS/1.02000", cmd[cmd.index("-vf") + 1])
        self.assertEqual(cmd[-2:], ["rawvideo", "pipe:1"])
        self.assertIn("-an", cmd)

    def test_builds_http_reconnect_command(self):
        cmd = build_ffmpeg_command("ffmpeg.exe", "https://host/live.m3u8", 1280, 720, 30)
        self.assertIn("-reconnect", cmd)
        self.assertNotIn("-rtsp_transport", cmd)

    def test_builds_audio_pcm_command_with_subtle_pitch_and_tempo_filters(self):
        cmd = build_audio_ffmpeg_command(
            "ffmpeg.exe", "https://host/live.m3u8", pitch=1.02, speed=0.99, volume=0.65
        )
        self.assertIn("-map", cmd)
        self.assertIn("0:a:0?", cmd)
        self.assertNotIn("nobuffer", cmd)
        self.assertEqual(cmd[cmd.index("-f") + 1], "f32le")
        filters = cmd[cmd.index("-af") + 1]
        self.assertIn("asetrate=48000*1.02000", filters)
        self.assertIn("atempo=0.99000", filters)
        self.assertIn("volume=0.650", filters)

    def test_brightness_adjustment_changes_frame_without_shape_change(self):
        frame = np.zeros((16, 16, 3), dtype=np.uint8)
        adjusted = apply_visual_adjustments(frame, brightness=18, contrast=1.0)
        self.assertEqual(adjusted.shape, frame.shape)
        self.assertEqual(adjusted.dtype, frame.dtype)
        self.assertGreater(int(adjusted.mean()), 0)

    def test_hue_shift_changes_colored_frame(self):
        frame = np.zeros((8, 8, 3), dtype=np.uint8)
        frame[:, :] = (0, 0, 220)  # BGR red
        adjusted = apply_visual_adjustments(frame, hue_shift=8)
        self.assertEqual(adjusted.shape, frame.shape)
        self.assertFalse(np.array_equal(adjusted, frame))

    def test_read_exact_handles_partial_pipe_reads_and_eof(self):
        self.assertEqual(read_exact(io.BytesIO(b"abcdef"), 4), b"abcd")
        self.assertIsNone(read_exact(io.BytesIO(b"ab"), 4))

    def test_signal_lost_placeholder_is_bgr_uint8(self):
        frame = make_signal_lost_frame(320, 180, phase=2)
        self.assertEqual(frame.shape, (180, 320, 3))
        self.assertEqual(frame.dtype, np.uint8)
        self.assertTrue(frame.flags["C_CONTIGUOUS"])

    def test_normalizes_bare_share_links_and_classifies_tiktok(self):
        value = normalize_input_url("www.tiktok.com/@creator/live")
        self.assertEqual(value, "https://www.tiktok.com/@creator/live")
        self.assertEqual(classify_input_url(value), "share_page")
        self.assertEqual(classify_input_url("https://cdn.example/live.m3u8"), "direct")

    def test_direct_resolver_is_deterministic_and_does_not_call_extractor(self):
        result = resolve_stream_url("www.example/live.m3u8")
        self.assertEqual(result.media_url, "https://www.example/live.m3u8")
        self.assertEqual(result.source_kind, "direct")

    def test_pk_overlay_changes_only_frame_pixels_and_preserves_shape(self):
        frame = np.zeros((120, 320, 3), dtype=np.uint8)
        overlay = apply_pk_overlay(frame, left_score=3, right_score=7, round_name="ROUND 1")
        self.assertEqual(overlay.shape, frame.shape)
        self.assertEqual(overlay.dtype, frame.dtype)
        self.assertGreater(int(overlay[:20].mean()), 0)
        self.assertEqual(int(overlay[100:].mean()), 0)


if __name__ == "__main__":
    unittest.main()
