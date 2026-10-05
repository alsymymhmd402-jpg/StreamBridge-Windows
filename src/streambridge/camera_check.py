"""Non-destructive UnityCapture availability checks."""
from __future__ import annotations

from dataclasses import dataclass

UNITYCAPTURE_URL = "https://github.com/schellingb/UnityCapture"


@dataclass(frozen=True)
class CameraPreflight:
    available: bool
    devices: tuple[str, ...] = ()
    message: str = ""


def check_unitycapture(camera_name: str = "Unity Video Capture") -> CameraPreflight:
    """Check UnityCapture without sending frames or changing the driver."""
    try:
        import pyvirtualcam

        if hasattr(pyvirtualcam, "list_devices"):
            devices = tuple(str(item) for item in pyvirtualcam.list_devices(backend="unitycapture"))
        else:
            # pyvirtualcam 0.15 has no cross-platform enumeration API. Its backend
            # constructor is used as a short probe; no frame is sent and the camera
            # is closed immediately by the context manager.
            with pyvirtualcam.Camera(width=16, height=16, fps=1, backend="unitycapture", device=camera_name) as camera:
                devices = (str(camera.device),)
    except Exception as exc:
        return CameraPreflight(False, (), f"UnityCapture check failed: {type(exc).__name__}: {exc}")
    wanted = camera_name.strip().lower()
    available = any(item.lower() == wanted for item in devices) or (not wanted and bool(devices))
    if available:
        return CameraPreflight(True, devices, f"UnityCapture camera available: {camera_name}")
    if devices:
        return CameraPreflight(False, devices, f"UnityCapture is registered, but '{camera_name}' was not found.")
    return CameraPreflight(False, devices, "No UnityCapture camera registered. Install the official driver, then retry.")
