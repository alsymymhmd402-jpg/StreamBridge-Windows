# StreamBridge Windows v1.1.0

A Windows desktop application that decodes a **direct** RTSP/RTSPS, HLS/M3U8, HTTP, or HTTPS stream and sends video frames to a UnityCapture DirectShow virtual camera. The interface uses a dark neon cyan/red visual style with a left sidebar.

> Share pages (for example, TikTok/YouTube pages) are not resolved by v1.1.0. A complete `https://` share URL may pass the syntax check but still fail to decode; use a direct playable media endpoint or resolve the page to a media URL first.

## What's new in v1.1.0

- Sidebar navigation for **Home**, **Live Preview**, **Bridge Status**, **Logs & Diagnostics**, **Media FX**, and **Settings**, using the dark cyan/red theme carried over from the mobile UI.
- Reliable paste controls: a **Paste** button, `Ctrl+V`, `Shift+Insert`, and a right-click menu on the URL field.
- Brightness, contrast, and hue sliders process frames before they are sent to the virtual camera.
- Optional 0.98×–1.03× playback-speed control, implemented in the FFmpeg video filter chain.
- Optional audio decode and routing with subtle pitch/tempo and volume controls. Audio is sent to a **separate virtual audio device**; the video camera device does not carry audio.
- Hiding/disabling the local preview does not stop decoding or virtual-camera frame delivery.
- A branded “SIGNAL LOST / RECONNECTING” frame is sent to the virtual camera during an input outage.

## Requirements and one-time driver setup

1. Install the **UnityCapture DirectShow filter** from the [official UnityCapture repository](https://github.com/schellingb/UnityCapture). Follow its official installation instructions (the driver is not bundled with this app). After installation, the expected camera name is usually `Unity Video Capture`.
2. For audio pass-through, install a virtual audio cable such as [VB-Audio Virtual Cable](https://vb-audio.com/Cable/). This is optional. In StreamBridge choose the cable's **CABLE Input** playback endpoint; in TikTok LIVE Studio/OBS choose **CABLE Output** as the microphone/audio input.
3. Use a **direct stream URL**. Examples include `https://host.example/live.m3u8` or `rtsp://camera.example/live`. A share page may pass HTTP(S) syntax validation but v1.1.0 does not extract its underlying stream, so FFmpeg may fail to decode it.

## Use

1. Start `StreamBridge.exe`.
2. On Home, paste the stream endpoint into **DIRECT STREAM URL**. Use the Paste button, `Ctrl+V`, or right-click → Paste.
3. Optionally choose output resolution/FPS and the audio device in **Settings**. Resolution/FPS changes apply on the next bridge start.
4. In **Media FX**, enable only the controls you need. Brightness/contrast/hue are live. Speed/pitch changes reinitialize the FFmpeg decoder; the camera sender continues running and emits the reconnect placeholder while it reconnects.
5. Select **START STREAM BRIDGE**. The **Bridge Status** and **Logs & Diagnostics** pages show camera, source, FPS, and audio status. Open **Live Preview** to view frames.
6. Turning **Enable UI Preview** off only stops local preview-frame delivery to the GUI. It does not stop the virtual-camera output thread.
7. In TikTok LIVE Studio or OBS, select **Unity Video Capture** (or the device name configured in Settings) as the camera. If routing audio, select the virtual cable's **CABLE Output** as the microphone.

## Build the Windows EXE from source

Use Windows 10/11 x64 with Python 3.11 x64 installed **with Tcl/Tk**. From PowerShell in this project folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1 -Mode onefile
```

The script creates a virtual environment, installs `requirements-dev.txt` (including FFmpeg, OpenCV, and sounddevice dependencies), imports the GUI, runs the unit tests, and creates `dist\StreamBridge.exe`. Use `-Mode onedir` for a folder-based build.

## Tests and limitations

- Unit tests cover URL validation, FFmpeg filter construction, PCM audio output command construction, image adjustments, signal-loss frames, preview-independent frame delivery, and live speed-change reconfiguration.
- The CI build runs on a Windows x64 runner. Actual UnityCapture device availability, VB-CABLE routing, source-server codec support, and the final camera/microphone selection must still be confirmed on the target Windows PC.
- FFmpeg opens independent decode sessions for video and optional audio, so enabling audio may add network load. Some sources do not expose an audio track or may require authentication/headers unavailable to the app.
- The app requires the third-party UnityCapture driver for video and a separately installed virtual audio driver for audio routing; it does not install drivers or bypass source access controls.

## Technical references

See [technical references](docs/TECHNICAL_REFERENCES.md) and [third-party notices](THIRD_PARTY.md). Main upstream references: [pyvirtualcam](https://github.com/letmaik/pyvirtualcam), [UnityCapture](https://github.com/schellingb/UnityCapture), [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html), [OpenCV image transforms](https://docs.opencv.org/4.13.0/d3/dc1/tutorial_basic_linear_transform.html), and [sounddevice raw streams](https://python-sounddevice.readthedocs.io/en/latest/api/raw-streams.html).
