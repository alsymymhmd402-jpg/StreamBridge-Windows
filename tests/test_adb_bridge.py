import subprocess
import unittest

from streambridge.adb_bridge import AdbBridgeError, AdbBridgeManager


class FakeAdb:
    def __init__(self, devices="List of devices attached\nphone-1 device product:test model:test\n", forwards=""):
        self.devices_output = devices
        self.forwards = {}
        for line in forwards.splitlines():
            serial, local, remote = line.split()
            self.forwards[int(local.split(":")[1])] = (serial, remote)
        self.calls = []

    def __call__(self, args, **_kwargs):
        self.calls.append(args)
        if args[1:] == ["start-server"]:
            return subprocess.CompletedProcess(args, 0, "daemon started", "")
        if args[1:3] == ["devices", "-l"]:
            return subprocess.CompletedProcess(args, 0, self.devices_output, "")
        if args[1:] == ["forward", "--list"]:
            output = "".join(f"{serial} tcp:{port} {remote}\n" for port, (serial, remote) in self.forwards.items())
            return subprocess.CompletedProcess(args, 0, output, "")
        if len(args) >= 6 and args[1] == "-s" and args[3] == "forward":
            serial = args[2]
            if args[4] == "--no-rebind":
                local_port = int(args[5].split(":")[1])
                remote = args[6]
                if local_port in self.forwards:
                    return subprocess.CompletedProcess(args, 1, "", "already forwarded")
                self.forwards[local_port] = (serial, remote)
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[4] == "--remove":
                local_port = int(args[5].split(":")[1])
                self.forwards.pop(local_port, None)
                return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")


class AdbBridgeTests(unittest.TestCase):
    def make_manager(self, fake, health=True):
        return AdbBridgeManager("adb", runner=fake, health_probe=lambda _url: health)

    def test_connect_creates_only_documented_forwards_and_disconnect_removes_owned(self):
        fake = FakeAdb()
        manager = self.make_manager(fake)
        status = manager.connect()
        self.assertIn("RTSP 8554 / HLS 8555", status)
        self.assertEqual(fake.forwards, {8554: ("phone-1", "tcp:8554"), 8555: ("phone-1", "tcp:8555")})
        self.assertTrue(manager.verify())
        manager.disconnect()
        self.assertEqual(fake.forwards, {})
        self.assertFalse(any("--remove-all" in call for call in fake.calls))

    def test_reuses_matching_preexisting_forwards_without_claiming_them(self):
        fake = FakeAdb(forwards="phone-1 tcp:8554 tcp:8554\nphone-1 tcp:8555 tcp:8555")
        manager = self.make_manager(fake)
        manager.connect()
        manager.disconnect()
        self.assertEqual(len(fake.forwards), 2)
        self.assertFalse(any("--remove" in call for call in fake.calls))

    def test_unauthorized_device_requires_user_approval(self):
        fake = FakeAdb("List of devices attached\nphone-1 unauthorized usb:1-1\n")
        with self.assertRaises(AdbBridgeError) as ctx:
            self.make_manager(fake).connect()
        self.assertEqual(ctx.exception.code, "ADB_UNAUTHORIZED")

    def test_multiple_devices_are_not_selected_implicitly(self):
        fake = FakeAdb("List of devices attached\nphone-1 device\nphone-2 device\n")
        with self.assertRaises(AdbBridgeError) as ctx:
            self.make_manager(fake).connect()
        self.assertEqual(ctx.exception.code, "ADB_MULTIPLE_DEVICES")

    def test_conflicting_forward_is_never_overwritten(self):
        fake = FakeAdb(forwards="other-device tcp:8554 tcp:9999")
        with self.assertRaises(AdbBridgeError) as ctx:
            self.make_manager(fake).connect()
        self.assertEqual(ctx.exception.code, "ADB_FORWARD_CONFLICT")
        self.assertEqual(fake.forwards[8554], ("other-device", "tcp:9999"))

    def test_health_failure_rolls_back_only_new_forwards(self):
        fake = FakeAdb(forwards="phone-1 tcp:8554 tcp:8554")
        with self.assertRaises(AdbBridgeError) as ctx:
            self.make_manager(fake, health=False).connect()
        self.assertEqual(ctx.exception.code, "ANDROID_BRIDGE_NOT_READY")
        self.assertEqual(fake.forwards, {8554: ("phone-1", "tcp:8554")})


if __name__ == "__main__":
    unittest.main()
