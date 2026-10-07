"""Safe ADB USB bridge for the Android StreamBridge media endpoints.

Only TCP ports 8554/8555 are managed. Existing forwards are reused when they
match exactly; conflicts are never removed or overwritten.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

PORTS = (8554, 8555)
HLS_URL = "http://127.0.0.1:8555/live.m3u8"
RTSP_URL = "rtsp://127.0.0.1:8554/live"
HEALTH_URL = "http://127.0.0.1:8555/health"


class AdbBridgeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AdbDevice:
    serial: str
    state: str


class AdbBridgeManager:
    """Manage only this product's two documented Android media forwards."""

    def __init__(
        self,
        adb_path: str | None = None,
        *,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        health_probe: Callable[[str], bool] | None = None,
        timeout: float = 8.0,
    ) -> None:
        self.adb_path = self._resolve_adb(adb_path)
        self._runner = runner
        self._health_probe = health_probe or self._probe_health
        self.timeout = timeout
        self.device_serial: str | None = None
        self.connected = False
        self._owned_forwards: set[int] = set()

    @staticmethod
    def _resolve_adb(explicit: str | None) -> str:
        candidates = [explicit, os.environ.get("ADB_PATH")]
        if os.environ.get("ANDROID_HOME"):
            candidates.append(str(Path(os.environ["ANDROID_HOME"]) / "platform-tools" / "adb.exe"))
        if os.environ.get("LOCALAPPDATA"):
            candidates.append(str(Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk" / "platform-tools" / "adb.exe"))
        candidates.append(shutil.which("adb"))
        for candidate in candidates:
            if candidate and (Path(candidate).is_file() or shutil.which(candidate)):
                return candidate
        return "adb"

    def _run(self, *args: str) -> str:
        try:
            result = self._runner(
                [self.adb_path, *args], capture_output=True, text=True,
                timeout=self.timeout, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError as exc:
            raise AdbBridgeError("ADB_NOT_FOUND", f"لم يُعثر على adb. ثبّت Android Platform Tools أو عيّن ADB_PATH. ({self.adb_path})") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbBridgeError("ADB_TIMEOUT", "انتهت مهلة ADB؛ افحص الكابل وUSB debugging ثم أعد المحاولة.") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise AdbBridgeError("ADB_FAILED", detail or f"adb {' '.join(args)} فشل برمز {result.returncode}")
        return (result.stdout or "").strip()

    def devices(self) -> list[AdbDevice]:
        output = self._run("devices", "-l")
        rows: list[AdbDevice] = []
        for line in output.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and not line.lstrip().startswith("*"):
                rows.append(AdbDevice(parts[0], parts[1]))
        return rows

    def _forward_map(self) -> dict[int, tuple[str, str]]:
        output = self._run("forward", "--list")
        forwards: dict[int, tuple[str, str]] = {}
        for line in output.splitlines():
            parts = line.split()
            if len(parts) != 3 or not parts[1].startswith("tcp:"):
                continue
            try:
                local_port = int(parts[1][4:])
            except ValueError:
                continue
            forwards[local_port] = (parts[0], parts[2])
        return forwards

    def connect(self) -> str:
        self._run("start-server")
        devices = self.devices()
        if not devices:
            raise AdbBridgeError("ADB_NO_DEVICE", "لم يُكتشف هاتف. وصّل كابل USB وفعّل USB debugging.")
        if len(devices) != 1:
            detail = ", ".join(f"{d.serial} ({d.state})" for d in devices)
            raise AdbBridgeError("ADB_MULTIPLE_DEVICES", f"اكتُشفت عدة أجهزة ({detail})؛ افصل الزائد واترك جهازًا واحدًا فقط.")
        device = devices[0]
        if device.state == "unauthorized":
            raise AdbBridgeError("ADB_UNAUTHORIZED", "الهاتف غير مصرّح به. افتح الشاشة ووافق على نافذة USB debugging؛ لا يمكن تجاوز الموافقة.")
        if device.state != "device":
            raise AdbBridgeError("ADB_OFFLINE", f"حالة جهاز ADB هي {device.state}. افحص الكابل ثم أعد التوصيل.")

        if self.device_serial and self.device_serial != device.serial:
            self._remove_owned(self.device_serial, self._owned_forwards)
            self._owned_forwards.clear()
        prior_owned = self._owned_forwards if self.device_serial == device.serial else set()

        forwards = self._forward_map()
        created: set[int] = set()
        try:
            for port in PORTS:
                existing = forwards.get(port)
                expected = (device.serial, f"tcp:{port}")
                if existing:
                    if existing != expected:
                        raise AdbBridgeError("ADB_FORWARD_CONFLICT", f"منفذ tcp:{port} مستخدم بتحويل آخر ({existing[0]} → {existing[1]}). لم أغيّر التحويل الموجود.")
                    continue
                self._run("-s", device.serial, "forward", "--no-rebind", f"tcp:{port}", f"tcp:{port}")
                created.add(port)
            if not self._health_probe(HEALTH_URL):
                raise AdbBridgeError("ANDROID_BRIDGE_NOT_READY", "تم إنشاء نفق USB لكن بوابة Android غير جاهزة. ابدأ Stream Bridge على الهاتف وتحقق من HLS/RTSP.")
        except Exception:
            self._remove_owned(device.serial, created)
            raise

        self.device_serial = device.serial
        self._owned_forwards = set(prior_owned) | created
        self.connected = True
        return f"اتصال USB جاهز · {device.serial} · RTSP 8554 / HLS 8555"

    def verify(self) -> bool:
        if not self.connected or not self.device_serial:
            return False
        devices = self.devices()
        if not any(d.serial == self.device_serial and d.state == "device" for d in devices):
            self.connected = False
            return False
        for port in PORTS:
            if self._forward_map().get(port) != (self.device_serial, f"tcp:{port}"):
                self.connected = False
                return False
        if not self._health_probe(HEALTH_URL):
            self.connected = False
            return False
        return True

    def disconnect(self) -> None:
        if self.device_serial:
            self._remove_owned(self.device_serial, self._owned_forwards)
        self._owned_forwards.clear()
        self.device_serial = None
        self.connected = False

    def _remove_owned(self, serial: str, ports: Sequence[int] | set[int]) -> None:
        for port in ports:
            try:
                if self._forward_map().get(port) == (serial, f"tcp:{port}"):
                    self._run("-s", serial, "forward", "--remove", f"tcp:{port}")
            except AdbBridgeError:
                # Do not let cleanup of an owned forward mask the original failure.
                continue

    @staticmethod
    def _probe_health(url: str) -> bool:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "StreamBridge-Windows/USB"})
            with urllib.request.urlopen(request, timeout=3) as response:
                return 200 <= response.status < 300
        except (OSError, urllib.error.URLError, TimeoutError):
            return False
