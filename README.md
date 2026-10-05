# StreamBridge Windows v1.2.0

A Windows desktop application that resolves supported public share links or accepts direct RTSP/RTSPS, HLS/M3U8, HTTP, or HTTPS streams, then sends processed video to a UnityCapture DirectShow virtual camera.

## What's new in v1.2.0

- **Share-link resolver:** bare `www.tiktok.com/...`, `tiktok.com/...`, and `https://vt.tiktok.com/...` inputs are normalized to HTTPS. TikTok share/live pages are resolved through the optional `yt-dlp` extractor, while direct media URLs remain the fast path.
- **Actionable resolver diagnostics:** the app distinguishes input normalization, share-page extraction failure, and later FFmpeg/network failure. Query strings are redacted in logs.
- **UnityCapture preflight:** the Home page can enumerate the configured UnityCapture backend without opening or modifying a camera. If no camera is registered, the app explains the fix and offers to open the official UnityCapture instructions. Driver installation remains an explicit Windows/UAC action; it is never silent.
- **Media FX stability:** brightness, contrast, hue, playback speed, pitch, and volume continue to apply through the existing debounced live-update path. Speed/pitch changes reconfigure only the relevant decoder/relay; the camera sender continues outputting frames or the reconnect placeholder.
- **PK overlay preparation:** an opt-in top-edge score bar can be composited into outgoing frames using score/round settings. It does not render comments or gifts and is disabled by default.

## Requirements and one-time setup

1. Install the **UnityCapture DirectShow filter** from the [official UnityCapture repository](https://github.com/schellingb/UnityCapture), then confirm that the expected camera name is usually `Unity Video Capture`.
2. For optional audio pass-through, install a virtual audio cable such as [VB-Audio Virtual Cable](https://vb-audio.com/Cable/).
3. Install runtime dependencies from `requirements.txt`; `yt-dlp` is required only when using TikTok share pages. The resolver does not bypass authentication, cookies, geo restrictions, or other access controls.

## Use

1. Start `StreamBridge.exe` and press **Check UnityCapture / Setup** if the camera is not registered.
2. Paste a direct endpoint or a supported TikTok share/live URL. The app normalizes missing `https://` where unambiguous and resolves share pages in a background thread.
3. Start the bridge and select **Unity Video Capture** in TikTok LIVE Studio/OBS.
4. Use **Media FX** for live visual/audio adjustments. Preview visibility is independent of camera delivery.

## Build and tests

Use Windows 10/11 x64 with Python 3.11 x64 and Tcl/Tk:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1 -Mode onefile
```

The build runs the unit suite and creates `dist\StreamBridge.exe`. The GitHub Actions workflow uploads the EXE as a short-retention artifact; binaries are not committed to Git.

The tests cover direct/share URL classification, deterministic direct resolution, FFmpeg command construction, visual/audio processing, PK top-only composition, camera-output independence, and decoder reconfiguration. Real TikTok availability, UnityCapture registration, VB-CABLE routing, and Windows hardware behavior still require validation on an authorized target PC.
