"""Snapshots from the A1 / A1 mini / P1 camera.

These printers stream JPEG frames over TLS on port 6000. We only keep the
stream open while someone is looking at it.
"""

import socket
import ssl
import struct
import threading
import time

IDLE_TIMEOUT = 20.0


class Camera:
    def __init__(self) -> None:
        self.frame: bytes | None = None
        self.frame_at = 0.0
        self.error: str | None = None
        self._wanted_at = 0.0
        self._thread: threading.Thread | None = None
        self._target: tuple[str, str] | None = None

    def latest(self, ip: str, access_code: str) -> bytes | None:
        self._wanted_at = time.time()
        if self._target != (ip, access_code) or not (self._thread and self._thread.is_alive()):
            self._target = (ip, access_code)
            self._thread = threading.Thread(target=self._run, args=(ip, access_code), daemon=True)
            self._thread.start()
        return self.frame

    def _run(self, ip: str, access_code: str) -> None:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        auth = struct.pack("<IIII", 0x40, 0x3000, 0, 0)
        auth += b"bblp".ljust(32, b"\0") + access_code.encode().ljust(32, b"\0")
        try:
            with (
                socket.create_connection((ip, 6000), timeout=10) as raw,
                context.wrap_socket(raw, server_hostname=ip) as conn,
            ):
                conn.sendall(auth)
                while time.time() - self._wanted_at < IDLE_TIMEOUT and self._target == (ip, access_code):
                    header = _read_exactly(conn, 16)
                    size = struct.unpack_from("<I", header)[0]
                    self.frame = _read_exactly(conn, size)
                    self.frame_at = time.time()
                    self.error = None
        except (OSError, ConnectionError) as e:
            self.error = f"Camera unavailable: {e}"


def _read_exactly(conn: ssl.SSLSocket, n: int) -> bytes:
    data = bytearray()
    while len(data) < n:
        part = conn.recv(n - len(data))
        if not part:
            raise ConnectionError("camera stream closed")
        data += part
    return bytes(data)


camera = Camera()
