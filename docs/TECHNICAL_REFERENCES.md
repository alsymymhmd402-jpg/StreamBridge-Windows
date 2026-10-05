# Technical references

Reviewed on 2026-10-05. These upstream references informed the selected Windows camera backend and the install/build instructions.

## pyvirtualcam

- Official repository: <https://github.com/letmaik/pyvirtualcam>
- API documentation: <https://letmaik.github.io/pyvirtualcam/>
- The API documents `Camera(width, height, fps, fmt=..., device=..., backend=...)`, `send(frame)`, `sleep_until_next_frame()`, and the Windows `unitycapture` backend. The documented UnityCapture device name is `Unity Video Capture` (or the name assigned to the device).
- `PixelFormat.BGR` accepts a frame with shape `(height, width, 3)`. The application therefore sends contiguous BGR24 NumPy arrays at a fixed 1280×720 output size.
- The project README says that pyvirtualcam requires an already installed virtual-camera device; pyvirtualcam itself does not install/register a DirectShow filter.
- The pyvirtualcam repository lists GPL-2.0; this project includes its GPL-2.0 license text and third-party notices.

## UnityCapture

- Official repository and installation instructions: <https://github.com/schellingb/UnityCapture>
- The project describes UnityCapture as a Windows DirectShow filter and instructs users to run `Install.bat` in the `Install` folder to register the capture device. It advises running as Administrator if registration fails; `Uninstall.bat` should be run before moving/removing installed files.
- Its README describes the default output device as `Unity Video Capture`, documents multiple capture devices as an optional separate installation, and reports 1080p/60fps on moderate PCs (with higher resolutions on faster PCs). Those are upstream capabilities, not a guarantee for every host PC or source stream.
- The filter and Unity plugin have separate licenses; the driver is not redistributed in this source bundle.

## v1.1.0 Media FX / audio references

- python-sounddevice Raw streams: <https://python-sounddevice.readthedocs.io/en/latest/api/raw-streams.html> — `RawOutputStream` targets a selected PortAudio output device and its `write()` accepts interleaved raw buffers; v1.1.0 uses this for float32 PCM output to a separately installed virtual audio endpoint.
- FFmpeg filter reference: <https://ffmpeg.org/ffmpeg-filters.html> — `setpts` controls video timestamps; `atempo` controls audio tempo; `asetrate` changes the interpreted sample rate/pitch and `aresample` returns the output to the fixed device sample rate. The app applies a small pitch ratio, compensates duration, then applies playback tempo.
- OpenCV brightness/contrast reference: <https://docs.opencv.org/4.13.0/d3/dc1/tutorial_basic_linear_transform.html> — the documented linear transform is `alpha * frame + beta`; implementation uses OpenCV's optimized array operation, with HSV conversion for hue adjustment.
- Audio architecture constraint: pyvirtualcam/UnityCapture exports video frames, not audio. Audio is therefore routed separately to a Windows virtual audio output such as VB-CABLE; target broadcast software must select the corresponding recording endpoint as its microphone.
