# StreamBridge Windows — Development Handover

**Document status:** Current as of 2026-10-06
**Application baseline:** v1.1.0
**Public repository:** <https://github.com/alsymymhmd402-jpg/StreamBridge-Windows>
**Source baseline used for this handover:** `e0578c1` from the preceding v1.1.0 build repository. This public handover repository is a clean-source copy and will have its own Git commit ID.
**Target platform:** Windows 10/11, x64
**Implementation:** Python 3.11, Tkinter, FFmpeg, pyvirtualcam/UnityCapture, OpenCV, sounddevice/PortAudio

## 1. Project goal and scope

StreamBridge is a Windows desktop bridge that accepts a **direct, decodable media stream URL**, decodes it with a bundled FFmpeg executable, and sends BGR video frames to a system-wide DirectShow virtual camera provided by the separately installed UnityCapture driver. The virtual camera can then be selected as a camera source in TikTok LIVE Studio, OBS, or another DirectShow-compatible application.

The app also offers an optional local UI preview and a separate, optional audio route to a Windows output endpoint such as VB-CABLE. The video camera path and audio path are intentionally separate: UnityCapture receives video frames, while a virtual audio device carries PCM audio to the broadcasting application.

**Important scope boundary:** v1.1.0 does not resolve social-media share pages, install/register device drivers, bypass source access restrictions, or capture browser content. A URL being syntactically valid does not prove that it points to media FFmpeg can decode.

## 2. v1.1.0 implementation status

The following v1.1.0 features are present in source and were covered by the successful Windows CI build/test run:

- Dark cyan/red desktop UI with a left sidebar and six pages: Home/Dashboard, Live Preview, Bridge Status, Logs & Diagnostics, Media FX, and Settings.
- Paste button, `Ctrl+V`, `Shift+Insert`, and a right-click text-entry menu.
- Video controls for brightness, contrast, and hue; optional playback-speed adjustment in the 0.98×–1.03× range.
- Optional audio decoding/routing with small pitch/tempo changes and volume adjustment.
- A signal-loss placeholder labelled **SIGNAL LOST / RECONNECTING** sent to the virtual camera when frames have been absent for the configured timeout.
- A one-slot/latest-frame design so slow UI preview rendering does not accumulate a long frame backlog; hiding the UI preview does not disable virtual-camera frame delivery.
- Runtime logs and status metrics for source state, camera initialization, FPS, frame count, resolution, and the optional audio route.

The v1.1.0 build completed successfully on a Windows x64 GitHub Actions runner in run `37387061263` in the previous build repository. The suite contains **12 unit tests** (9 core tests and 3 engine tests). Additional local smoke checks exercised Tk page construction/navigation and FFmpeg video/audio output against synthetic HTTP-served media. These checks do **not** substitute for testing a real UnityCapture/VB-CABLE installation on the user's PC.

## 3. Architecture and data flow

```text
Direct RTSP(S)/HTTP(S) media URL
                 │
                 ├── Video: FFmpeg subprocess → raw BGR24 frames
                 │                       │
                 │                       ▼
                 │              one-slot decoded-frame queue
                 │                       │
                 │                       ▼
                 │              StreamBridgeEngine thread
                 │                 ├── visual FX (OpenCV)
                 │                 ├── signal-loss placeholder
                 │                 ├── pyvirtualcam → UnityCapture DirectShow
                 │                 └── optional one-slot preview queue → Tk UI
                 │
                 └── Optional audio: separate FFmpeg subprocess → float32 PCM
                                                   │
                                                   ▼
                                         AudioRelay thread
                                                   │
                                                   ▼
                                         sounddevice/PortAudio output
                                                   │
                                                   ▼
                                   VB-CABLE CABLE Input → CABLE Output mic
```

### Thread and process responsibilities

- **Tkinter/UI main thread — `src/streambridge/ui.py`:** Owns widgets, navigation, input, preview display, status updates, and logs. It polls the worker event queue periodically; it does not run FFmpeg decoding on the UI thread.
- **Virtual-camera engine — `StreamBridgeEngine` in `engine.py`:** Opens pyvirtualcam using the `unitycapture` backend, sends frames at the configured camera FPS, applies optional visual effects, emits metrics, and continues output when the preview is hidden.
- **Video decoder — `FFmpegDecoder` in `engine.py`:** Runs FFmpeg as a child process and reads fixed-size raw BGR frames from stdout. It keeps only the latest frame in a bounded queue, reconnects with exponential backoff (1–15 seconds), and restarts the decoder when playback speed changes.
- **Audio relay — `AudioRelay` in `audio.py`:** Runs an independent FFmpeg audio decode process, reads 48 kHz stereo float32 PCM blocks, and writes to a selected PortAudio output endpoint through `sounddevice`. It reconnects and can reconfigure when audio device, pitch, volume, or speed changes.
- **Queues and independence:** The engine's decoded-frame and preview queues each have a maximum size of one. A slow or disabled preview therefore cannot stop the camera sender or create an ever-growing preview backlog. Video and audio are separate FFmpeg sessions and can increase network/CPU use when both are enabled.

### FFmpeg and frame handling

`core.py` validates URL syntax and constructs the FFmpeg commands. RTSP/RTSPS input uses TCP transport. HTTP(S) input uses FFmpeg reconnect options. Video is scaled and padded to the selected camera dimensions while preserving aspect ratio, converted to BGR24, and emitted through a raw pipe. Low-latency flags and bounded probing are configured in the command. Audio is mapped optionally, converted to 48 kHz stereo float32, and filtered independently.

The output defaults to 1280×720 at 30 FPS; Settings offers 720p/1080p and 30/60 FPS. Resolution and FPS are static for one camera session and take effect after restarting the bridge. Brightness/contrast/hue can be changed live. Speed changes restart the decoder; the camera thread remains active and will send the reconnect placeholder while waiting for fresh frames. Pitch/volume changes reconfigure the audio path.

The signal placeholder is used when no decoded frame has arrived within `SIGNAL_LOST_AFTER_SECONDS` (currently 2 seconds). The engine continues sending at the camera cadence while the input decoder attempts to reconnect.

## 4. Repository map

| Path | Responsibility |
|---|---|
| `src/streambridge/ui.py` | Sidebar UI, URL entry/paste, preview, status, logs, Media FX, settings, and event polling. |
| `src/streambridge/core.py` | URL syntax validation, FFmpeg command construction, image adjustments, exact pipe reads, placeholder frame. |
| `src/streambridge/engine.py` | FFmpeg video decoder thread and pyvirtualcam/UnityCapture output loop. |
| `src/streambridge/audio.py` | Optional FFmpeg-to-PortAudio audio relay. |
| `src/streambridge/main.py` | Application entry point and optional command-line URL handling. |
| `run_app.py` | PyInstaller-friendly launcher. |
| `tests/test_core.py` | URL, filter command, image, pipe-read, and placeholder tests. |
| `tests/test_engine.py` | Preview/output independence, visual processing, and speed reconfiguration tests. |
| `requirements.txt` | Runtime Python dependencies. |
| `requirements-dev.txt` | Runtime dependencies plus pytest and PyInstaller. |
| `build_windows.ps1` | Windows one-file/one-directory build, import check, unit tests, and PyInstaller invocation. |
| `.github/workflows/build-windows.yml` | Manual Windows x64 CI build and 14-day EXE artifact upload. |
| `README.md` | User installation/use/build guide. |
| `THIRD_PARTY.md` | Dependency and driver license notes. |
| `docs/TECHNICAL_REFERENCES.md` | Upstream implementation references. |

## 5. Current URL behavior — do not mistake syntax validation for extraction

The supported URL schemes are `http`, `https`, `rtsp`, and `rtsps`. `validate_stream_url()` verifies that the URL has a supported scheme, a host, and a parseable port. It does **not** inspect the page body, verify an HLS manifest, probe the media before starting, or extract a stream URL from a social-media page.

Consequences in the current version:

- A complete direct media URL such as `https://media.example/live/index.m3u8` or `rtsp://camera.example/live` passes syntax validation and is handed to FFmpeg.
- A bare value like `www.example.com/live` has no scheme and currently fails validation; automatic `https://` insertion has not been implemented.
- `https://vt.tiktok.com/...` or `https://www.tiktok.com/@name/live` has a valid HTTP scheme and may pass the syntax check, but is a webpage/share URL, not a guaranteed media manifest. v1.1.0 does not use yt-dlp or another resolver, so FFmpeg commonly fails to decode it.
- A direct `.m3u8`, `.flv`, or other endpoint is only usable when the server actually returns a supported stream and does not require unavailable cookies, headers, or authentication.

The UI's **Invalid direct stream URL** dialog means syntax validation failed. A syntactically accepted link can still fail later at the media/network stage; logs should distinguish those failure classes.

## 6. Active technical issues — next work

### 6.1 UnityCapture camera registration/preflight

**Observed issue:** On a PC without UnityCapture registered, pyvirtualcam can fail during camera creation with an error such as `Virtual camera unavailable: ... No camera registered`. The engine catches the exception and reports a fatal camera error; the UI has a general install reminder, but v1.1.0 does not perform a robust driver/device preflight or install the driver.

**Required follow-up:**

1. Add a non-destructive camera availability check and distinguish “driver missing/no registered camera” from other failures such as device busy or unsupported format.
2. Show clear in-app setup instructions and an official UnityCapture project link. Offer to open the official instructions or installer only after explicit user action; do not silently register/install a system driver or bypass Windows administrator/UAC consent.
3. Preserve the currently configured camera name and explain that `Unity Video Capture` is the default expected device name.
4. Validate the fix on Windows both with the driver absent and with UnityCapture installed, then confirm the device is visible in DirectShow enumeration and selectable in OBS/TikTok LIVE Studio.

### 6.2 Share-page URL extraction and scheme normalization

**Observed issue:** v1.1.0 accepts direct HTTP(S)/RTSP(S) schemes only; it has no page resolver. Bare `www.` links fail before FFmpeg. Full TikTok short/share URLs can pass the syntax check but are not converted into an underlying `.m3u8`/`.flv` stream.

**Required follow-up:**

1. Normalize a bare `www.`/host-only input to HTTPS only when it is unambiguous; retain clear validation for malformed or unsupported URLs.
2. Add a resolver abstraction that classifies direct stream endpoints versus share/web pages and returns actionable progress/errors rather than reporting success merely because the URL was accepted.
3. Evaluate yt-dlp or a maintained platform-specific extraction path. Package and license-check its runtime requirements, and test each supported platform/link type with real examples. Resolver success should be proven by obtaining a media URL and opening it with FFmpeg, not by HTTP 200 on the webpage.
4. Handle expiring signed URLs, redirects, timeouts, cookies/headers, geofencing, unavailable/private/live-ended pages, and extractor failures explicitly. Do not bypass access controls; support only media the user is authorized to access.
5. Add deterministic unit tests with recorded fixtures and opt-in integration tests for actual public links. Do not bake a user's private URL, cookie, credential, or expiring signed manifest into the EXE or repository.

### 6.3 Future roadmap: interactive PK score-bar overlay

Add an optional interactive PK score-bar overlay at the **top edge of the outgoing frame only**. It should show the agreed score/round state and not capture, render, or display chat comments or gift events. This is not implemented in v1.1.0. Before implementation, define the score data source, manual versus remote control, overlay sizing/safe area, styling, and whether the overlay is composited into the outgoing camera frames or preview-only. Keep the overlay independent of the video decoder and test that it cannot interrupt camera output.

## 7. Windows installation and use

1. Install the UnityCapture DirectShow driver once from the [official UnityCapture repository](https://github.com/schellingb/UnityCapture); the driver is not included in this project or EXE.
2. Start `StreamBridge.exe`, paste a **direct** stream URL on Home, and press **START STREAM BRIDGE**.
3. Select **Unity Video Capture** (or the configured device name) as the camera in TikTok LIVE Studio/OBS.
4. Optional audio: install a virtual audio cable such as VB-CABLE; choose its `CABLE Input` playback endpoint in StreamBridge and `CABLE Output` as the microphone in the broadcast software. The DirectShow video camera does not carry audio.
5. The local UI preview can be hidden. Hiding it is not a stop command and does not stop the virtual-camera output thread.

## 8. Build, test, and CI handoff

### Local Windows build

Use Windows 10/11 x64 and Python 3.11 x64 with Tcl/Tk. From PowerShell at the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1 -Mode onefile
```

The script creates `.venv`, installs `requirements-dev.txt`, checks Tkinter/UI imports, runs the unit suite, then runs PyInstaller with the imageio-ffmpeg, pyvirtualcam, Pillow, OpenCV, sounddevice, and PortAudio data collectors. Output is `dist\StreamBridge.exe`. Use `-Mode onedir` to create an onedir build instead.

To run tests separately after installing dependencies:

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### GitHub Actions

`.github/workflows/build-windows.yml` currently uses `workflow_dispatch` on `windows-latest`, installs Python 3.11 x64, runs `build_windows.ps1`, and uploads `StreamBridge-v1.1.0-Windows-x64` for 14 days. The binary is intentionally excluded from Git; build artifacts should be distributed separately and should not be committed to the source repository.

### Tests and proof boundaries

The 12 unit tests cover:

- Direct URL scheme/host/port acceptance and malformed/unsupported input rejection.
- RTSP-over-TCP and HTTP reconnect command construction, raw BGR output, audio PCM/pitch/tempo filter construction.
- Brightness/hue frame changes, exact pipe reads, and the BGR signal-loss placeholder.
- Camera output continuing while UI preview is disabled, visual adjustments reaching the camera sender, and speed changes requesting decoder reconfiguration.

The automated engine tests use fake camera/decoder objects. They prove worker coordination and frame behavior, **not** actual driver registration. The Windows CI compiles an x64 GUI PE; real camera/audio driver interoperability still needs target-PC validation.

## 9. Security, privacy, and release notes

- Never commit access tokens, cookies, private stream URLs, signed manifests, or user-specific credentials.
- URL query strings can contain temporary signatures. Current logs deliberately redact query strings; preserve that behavior in resolver diagnostics.
- UnityCapture and VB-CABLE are separate drivers and are not redistributed by this repository. Review `THIRD_PARTY.md` before distributing a new build.
- The one-file EXE is large because it bundles FFmpeg/OpenCV and Python runtime dependencies. Prefer Actions artifacts or a file/CDN download for binaries; keep Git focused on source and docs.
- The current GUI EXE is not code-signed. Windows SmartScreen/Defender may show an unverified-publisher warning; do not claim that the build is signed.

## 10. Immediate continuation checklist

1. Read this file and `README.md` before changing behavior.
2. Reproduce camera absence on a Windows machine, capture the exact pyvirtualcam/UnityCapture exception, and implement a user-friendly preflight/setup flow without silently installing the driver.
3. Design a resolver interface and tests before adding yt-dlp. Keep direct stream input working as a fallback.
4. Add tests for direct URL normalization, TikTok share-page classification, resolver success/failure, expired manifests, and FFmpeg opening the resolved source.
5. Run all 12 existing tests plus new tests; run the Windows workflow; test UnityCapture and optional VB-CABLE on a real Windows PC.
6. Only then bump the version and publish a new EXE. Do not claim TikTok page extraction, camera availability, or live preview works until proven on representative real sources/devices.
7. Defer the PK score-bar overlay until the camera preflight and share-link resolver are stable; keep it top-only and exclude comments/gifts.

## 11. Ready-to-paste prompt for a new development conversation

```text
Continue development of the existing StreamBridge Windows project from its current v1.1.0 baseline. First clone/open https://github.com/alsymymhmd402-jpg/StreamBridge-Windows and read DEVELOPMENT_HANDOVER.md and README.md completely; do not recreate the project or assume the previous conversation is available.

The app is a Python 3.11/Tkinter Windows x64 desktop bridge: FFmpeg decodes direct RTSP(S)/HTTP(S) streams to BGR frames; StreamBridgeEngine sends frames through pyvirtualcam to the separately installed UnityCapture DirectShow camera. Audio is an independent optional FFmpeg→sounddevice/PortAudio path to a virtual audio endpoint. UI preview is decoupled from camera output. v1.1.0 has a six-page dark sidebar UI, robust paste controls, live brightness/contrast/hue, subtle speed and audio pitch/volume controls, diagnostics, and a SIGNAL LOST/RECONNECTING camera placeholder. All 12 current unit tests and the Windows x64 CI build passed; fake-device tests do not prove a real driver works.

Continue from the active issues in DEVELOPMENT_HANDOVER.md, in this order:
1) Add a clear, tested UnityCapture camera/driver availability preflight and in-app official install guidance for the current “No camera registered” failure. Never silently install a system driver or bypass UAC.
2) Add optional stream-share URL extraction and unambiguous https:// normalization. Current code validates syntax only: TikTok/YouTube pages are NOT resolved; direct M3U8/RTSP/HTTP playback must remain supported. Design the resolver interface and tests first, then assess yt-dlp/platform extractors, packaging/licensing, timeouts, expiry, and failure reporting. Do not bypass access controls or claim success without opening the resolved URL with FFmpeg.
3) Keep the future PK score-bar overlay as a later roadmap item: overlay only at the top edge, no chat comments or gifts, and no interruption to frame output.

Before editing, inspect the current code and preserve the decoupled decoder/camera/audio threads. Add automated tests, run the Windows Actions workflow, and distinguish unit/CI results from real Windows hardware validation. Update DEVELOPMENT_HANDOVER.md and README.md with every behavior change. Do not commit secrets, cookies, signed stream URLs, user credentials, or EXE artifacts.
```
