# Third-party components

- **pyvirtualcam 0.15.x** — GPL-2.0. Source: <https://github.com/letmaik/pyvirtualcam>. The application source is distributed under GPL-2.0; see `LICENSE`.
- **UnityCapture DirectShow filter** — separate Windows driver, not bundled. Its repository describes the filter as MIT-licensed and the Unity plugin as zlib-licensed: <https://github.com/schellingb/UnityCapture>. Install only from the official project source.
- **FFmpeg via imageio-ffmpeg** — the Windows binary is included by the PyInstaller build. FFmpeg build configurations and codecs have their own LGPL/GPL licensing; inspect the exact binary's `-version` output and the imageio-ffmpeg distribution notices before redistributing a built EXE. Project: <https://github.com/imageio/imageio-ffmpeg>.
- **NumPy** — BSD 3-Clause: <https://numpy.org/license/>.
- **Pillow** — HPND/PIL license: <https://github.com/python-pillow/Pillow/blob/main/LICENSE>.
- **OpenCV (`opencv-python-headless`)** — Apache-2.0: <https://github.com/opencv/opencv-python> and <https://github.com/opencv/opencv/blob/4.x/LICENSE>.
- **sounddevice** — MIT: <https://github.com/spatialaudio/python-sounddevice>. It uses PortAudio; the Windows wheel/runtime carries its own notices: <https://github.com/PortAudio/portaudio/blob/master/LICENSE.txt>.
- **Python/Tkinter** — Python Software Foundation license; Tk is separately licensed. Official notices are supplied by the Python distribution.

This source bundle does not include the UnityCapture or VB-CABLE drivers. The Windows build script downloads Python packages from PyPI when run. Review all bundled third-party license/notice requirements before redistributing a built executable.
