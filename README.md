# StreamBridge Windows v1.3.0

Windows bridge for TikTok LIVE Studio: resolves supported share links or direct RTSP/HTTP/HLS sources and sends processed video to a UnityCapture DirectShow virtual camera.

## UnityCapture — official installer

Use the official package; the DLL files must remain beside the batch file:

- [Download UnityCapture ZIP](https://github.com/schellingb/UnityCapture/archive/refs/heads/master.zip)
- [Official instructions](https://github.com/schellingb/UnityCapture)
- [Install.bat source](https://raw.githubusercontent.com/schellingb/UnityCapture/master/Install/Install.bat)

After extracting the ZIP, open `Install\Install.bat` and choose **Run as administrator**. Then restart StreamBridge and select `Unity Video Capture`. Do not download a standalone BAT without the matching `Install` DLL files.

## v1.3.0 changes

- **Mobile Viewframe:** Live Preview is now a centered portrait 9:16 phone frame. The preview uses a center crop to fill the frame without black bars; the outgoing camera resolution and media pipeline remain unchanged.
- **Professional iconography:** navigation now uses custom cyan line SVG assets with packaged PNG runtime copies for Dashboard, Live Preview, Bridge Status, Logs, Media FX, and Settings. Emoji/unicode navigation glyphs were removed.
- **Application icon:** `streambridge.ico` is embedded into the Windows executable and assigned to the Tk window, taskbar, and desktop shortcut generated from the EXE.
- Existing v1.2 features remain: TikTok share-link resolver through optional `yt-dlp`, UnityCapture preflight, live Media FX, and disabled-by-default top-only PK score bar.

## Build and validation

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1 -Mode onefile
```

The build packages the icon assets and runs the automated test suite before PyInstaller. The CI artifact is produced by the Windows x64 workflow. Hardware validation still requires UnityCapture installed on a real Windows PC.
