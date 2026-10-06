import queue
import threading
import time
import unittest

import numpy as np

from streambridge.engine import HEIGHT, WIDTH, StreamBridgeEngine, StreamPreviewEngine


class FakeCamera:
    def __init__(self, **kwargs):
        self.device = "Fake Unity Video Capture"
        self.backend = "test"
        self.frames_sent = 0
        self.current_fps = 30.0
        self.last_shape = None
        self.last_mean = 0.0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def send(self, frame):
        self.frames_sent += 1
        self.last_shape = frame.shape
        self.last_mean = float(frame.mean())

    def sleep_until_next_frame(self):
        time.sleep(0.002)


class FakeDecoder(threading.Thread):
    def __init__(self, _url, frames, events, stop_event, _settings_provider=None):
        super().__init__(daemon=True)
        self.frames = frames
        self.events = events
        self.stop_event = stop_event
        self.reconfigure_calls = 0

    def request_reconfigure(self):
        self.reconfigure_calls += 1

    def stop(self):
        self.stop_event.set()

    def run(self):
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        self.events.put(("status", "Live stream connected — sending frames"))
        while not self.stop_event.is_set():
            try:
                self.frames.put_nowait(frame)
            except queue.Full:
                try:
                    self.frames.get_nowait()
                    self.frames.put_nowait(frame)
                except queue.Empty:
                    pass
            time.sleep(0.005)


class EngineTests(unittest.TestCase):
    def _make_engine(self, camera, settings=None):
        return StreamBridgeEngine(
            "https://example.test/live.m3u8",
            settings=settings,
            camera_factory=lambda **_kwargs: camera,
            decoder_factory=FakeDecoder,
        )

    def test_virtual_camera_keeps_receiving_when_ui_preview_is_disabled(self):
        camera = FakeCamera()
        engine = self._make_engine(camera)
        engine.set_preview_enabled(False)
        engine.start()
        time.sleep(0.15)
        engine.request_stop()
        engine.join(timeout=3)

        self.assertFalse(engine.is_alive(), "engine should stop cleanly")
        self.assertGreater(camera.frames_sent, 0, "virtual camera must keep receiving frames")
        self.assertTrue(engine.preview_frames.empty(), "disabled preview should not queue UI frames")

    def test_visual_adjustments_reach_the_virtual_camera(self):
        camera = FakeCamera()
        engine = self._make_engine(camera, {"visual_enabled": True, "brightness": 20.0, "contrast": 1.0})
        engine.start()
        time.sleep(0.12)
        engine.request_stop()
        engine.join(timeout=3)
        self.assertGreater(camera.last_mean, 0.0)
        self.assertEqual(camera.last_shape, (HEIGHT, WIDTH, 3))

    def test_speed_change_requests_decoder_reconfiguration(self):
        camera = FakeCamera()
        engine = self._make_engine(camera)
        engine.start()
        deadline = time.monotonic() + 1.0
        while engine.decoder is None and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertIsNotNone(engine.decoder)
        engine.update_adjustments(speed=1.02)
        self.assertEqual(engine.decoder.reconfigure_calls, 1)
        engine.request_stop()
        engine.join(timeout=3)

    def test_preview_engine_runs_without_opening_virtual_camera(self):
        preview = StreamPreviewEngine(
            "https://example.test/live.m3u8",
            decoder_factory=FakeDecoder,
        )
        preview.start()
        deadline = time.monotonic() + 1.0
        while preview.preview_frames.empty() and time.monotonic() < deadline:
            time.sleep(0.01)
        preview.request_stop()
        preview.join(timeout=3)
        self.assertFalse(preview.is_alive(), "preview engine should stop cleanly")
        self.assertFalse(preview.preview_frames.empty(), "preview should receive frames without UnityCapture")


if __name__ == "__main__":
    unittest.main()
