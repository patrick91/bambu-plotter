"""Talking to the printer over its local MQTT broker.

The printer never reports where the toolhead is, so we keep track of it
ourselves from the G-code we send. That only works once X/Y have been homed
(position is then known) and the pen has touched the paper (Z is then known).
Until then the UI only offers the moves that are safe without that knowledge.
"""

import json
import os
import re
import ssl
import threading
import time
from dataclasses import dataclass, field

import paho.mqtt.client as mqtt

from . import settings as settings_module
from .settings import Calibration, Settings

# Pretend there's a printer: G-code is logged instead of sent. Handy for trying
# the app out, and for working on it without a printer nearby.
FAKE = os.environ.get("BAMBU_PLOTTER_FAKE") == "1"

# The printer is considered gone when it hasn't reported for this long.
STALE_AFTER = 15.0

Z_SPEED = 900.0

# An A1 mini answers "success" to gcode_line messages it then never runs: a
# 2.9 KB message into an idle printer, and 1.5 KB messages sent while others
# were still queued. It seems to have one ~2 KB buffer for incoming G-code, so
# plots are sent one message at a time, each well under that.
MAX_MESSAGE_BYTES = 1500


@dataclass
class Chunk:
    lines: list[str]
    # Where the pen is once the chunk has run.
    end: tuple[float, float]


@dataclass
class Job:
    name: str
    total_lines: int
    status: str = "running"  # running | stopping | done | stopped | failed
    done_lines: int = 0
    message: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    estimated_seconds: float = 0.0


class Printer:
    def __init__(self) -> None:
        self.settings: Settings = settings_module.load()
        self._client: mqtt.Client | None = None
        self._lock = threading.RLock()
        self._report: dict = {}
        self._last_report: float | None = None
        self.connecting = False
        self.error: str | None = None

        # Where the pen is, in machine coordinates. None means unknown.
        self.x: float | None = None
        self.y: float | None = None
        self.z: float | None = None
        self.xy_homed = False
        self.z_zeroed = False

        self._sequence = 0
        # The printer's replies to gcode_line commands, by sequence id.
        self._replies: dict[str, dict] = {}

        self.job: Job | None = None
        self._stop_job = threading.Event()

    # -- connection ---------------------------------------------------------

    @property
    def connected(self) -> bool:
        if FAKE:
            return self._last_report is not None
        return (
            self._client is not None and self._last_report is not None and time.time() - self._last_report < STALE_AFTER
        )

    def connect(self, ip: str, serial: str, access_code: str) -> None:
        self.disconnect()
        self.settings.ip, self.settings.serial, self.settings.access_code = (
            ip.strip(),
            serial.strip(),
            access_code.strip(),
        )
        settings_module.save(self.settings)

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set("bblp", self.settings.access_code)
        client.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS_CLIENT)
        client.tls_insecure_set(True)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect

        if FAKE:
            self._last_report = time.time()
            return

        self.connecting = True
        self.error = None
        self._client = client
        try:
            client.connect(self.settings.ip, 8883, keepalive=30)
        except OSError as e:
            self._client = None
            self.connecting = False
            self.error = f"Couldn't reach the printer at {self.settings.ip}: {e}"
            return
        client.loop_start()

        # Wait briefly for the first report so the page renders the right state.
        deadline = time.time() + 5
        while time.time() < deadline and not self.connected and self.error is None:
            time.sleep(0.1)
        self.connecting = False
        if not self.connected and self.error is None:
            self.error = "Connected, but the printer isn't sending status. Is LAN mode on?"

    def disconnect(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
        self._client = None
        self._last_report = None
        # Without a connection we can't trust anything we knew about the head:
        # someone may have moved it by hand. What we knew is still saved, and
        # can be restored after reconnecting.
        self.x = self.y = self.z = None
        self.xy_homed = self.z_zeroed = False

    def remember(self) -> None:
        """Save where the head is, so a restart doesn't mean redoing the setup."""
        calibration = Calibration(x=self.x, y=self.y, z=self.z, xy_homed=self.xy_homed, z_zeroed=self.z_zeroed)
        if calibration != self.settings.calibration and (self.xy_homed or self.z_zeroed):
            self.settings.calibration = calibration
            settings_module.save(self.settings)

    @property
    def saved_calibration(self) -> Calibration | None:
        """A calibration from before, when we don't have one now."""
        c = self.settings.calibration
        if c and (c.xy_homed or c.z_zeroed) and not (self.xy_homed or self.z_zeroed):
            return c
        return None

    def restore_calibration(self) -> None:
        c = self.saved_calibration
        if c is None:
            raise PrinterError("There's no previous position to restore")
        self.x, self.y, self.z = c.x, c.y, c.z
        self.xy_homed, self.z_zeroed = c.xy_homed, c.z_zeroed

    def forget_calibration(self) -> None:
        self.settings.calibration = None
        settings_module.save(self.settings)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self.error = (
                "The printer refused the connection. Check the access code and serial number."
                if reason_code.value in (4, 5, 134, 135)
                else f"Connection failed: {reason_code}"
            )
            return
        client.subscribe(f"device/{self.settings.serial}/report")
        self.request_status()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self.error = f"Lost connection to the printer ({reason_code})"

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
        except ValueError:
            return
        report = payload.get("print")
        if not isinstance(report, dict):
            return
        if report.get("command") == "gcode_line":
            # The printer's answer to a batch of G-code we sent.
            print(
                f"Printer replied to G-code #{report.get('sequence_id')}: {report.get('result')} {report.get('reason', '')}"
            )
            self._replies[str(report.get("sequence_id"))] = report
            return
        with self._lock:
            # Reports are sparse deltas: merge them into what we've seen.
            self._report.update(report)
            self._last_report = time.time()
            self.error = None

    def _publish(self, payload: dict) -> None:
        if self._client is None:
            raise PrinterError("Not connected to the printer")
        self._client.publish(f"device/{self.settings.serial}/request", json.dumps(payload))

    def request_status(self) -> None:
        if FAKE:
            return
        self._publish({"pushing": {"sequence_id": "0", "command": "pushall"}})

    def send(self, *lines: str) -> str:
        """Send G-code lines in one message. Returns its sequence id."""
        if not self.connected:
            raise PrinterError("Not connected to the printer")
        param = "\n".join(lines) + "\n"
        if len(param.encode()) > MAX_MESSAGE_BYTES:
            raise PrinterError(f"G-code message too big for the printer ({len(param)} bytes)")
        if FAKE:
            print("G-code >", " | ".join(lines[:6]), "..." if len(lines) > 6 else "")
            # Echo progress markers back after a moment, like the printer does.
            for marker in re.findall(r"^M73 P(\d+)", "\n".join(lines), re.MULTILINE):
                threading.Timer(0.6, lambda m=marker: self._report.update(mc_percent=int(m))).start()
            return ""
        self._sequence += 1
        sequence_id = str(self._sequence)
        self._publish({"print": {"sequence_id": sequence_id, "command": "gcode_line", "param": param}})
        return sequence_id

    def rejection(self, sequence_id: str) -> str | None:
        """Why the printer refused a batch, if it did."""
        reply = self._replies.get(sequence_id)
        if reply is None or reply.get("result", "").lower() in ("success", "ok", ""):
            return None
        return reply.get("reason") or reply.get("result") or "unknown reason"

    @property
    def report(self) -> dict:
        with self._lock:
            return dict(self._report)

    @property
    def busy(self) -> bool:
        return self.job is not None and self.job.status in ("running", "stopping")

    def _check_idle(self) -> None:
        if self.busy:
            raise PrinterError("Wait for the current plot to finish")

    # -- moves ----------------------------------------------------------------

    def _clamp(self, x: float, y: float) -> tuple[float, float]:
        w, h = self.settings.bed_size
        return min(max(x, 0.0), w), min(max(y, 0.0), h)

    def home(self) -> None:
        """Lift the head a little, home X and Y, and park in the middle of the bed."""
        self._check_idle()
        w, h = self.settings.bed_size
        lines = ["G91", f"G1 Z10 F{Z_SPEED:.0f}", "G90", "G28 X Y", f"G1 X{w / 2:.1f} Y{h / 2:.1f} F6000"]
        self.send(*lines)
        if self.z is not None:
            self.z += 10
        self.x, self.y = w / 2, h / 2
        self.xy_homed = True

    def jog_z(self, dz: float) -> None:
        self._check_idle()
        # Relative, so it's safe even before we know where Z is.
        self.send("G91", f"G1 Z{dz:.2f} F{Z_SPEED:.0f}", "G90")
        if self.z is not None:
            self.z += dz

    def jog_xy(self, dx: float, dy: float) -> None:
        if self.x is None or self.y is None:
            raise PrinterError("Home X/Y first")
        self.move_to(self.x + dx, self.y + dy)

    def move_to(self, x: float, y: float) -> None:
        """Move the pen to (x, y), lifting it first if it might be touching the paper."""
        self._check_idle()
        if not self.xy_homed:
            raise PrinterError("Home X/Y first")
        x, y = self._clamp(x, y)
        lines = ["G90"]
        if self.z is not None and self.z < self.settings.pen_up:
            lines.append(f"G1 Z{self.settings.pen_up:.2f} F{Z_SPEED:.0f}")
            self.z = self.settings.pen_up
        lines.append(f"G1 X{x:.2f} Y{y:.2f} F{self.settings.travel_speed:.0f}")
        self.send(*lines)
        self.x, self.y = x, y

    def set_pen_touching(self) -> None:
        """The pen tip is resting on the paper right now: call that Z=0 and lift."""
        self._check_idle()
        self.send("G92 Z0", "G90", f"G1 Z{self.settings.pen_up:.2f} F{Z_SPEED:.0f}")
        self.z = self.settings.pen_up
        self.z_zeroed = True

    def pen(self, down: bool) -> None:
        self._check_idle()
        if not self.z_zeroed:
            raise PrinterError("Set the pen height first")
        z = -self.settings.pen_pressure if down else self.settings.pen_up
        self.send("G90", f"G1 Z{z:.2f} F{Z_SPEED:.0f}")
        self.z = z

    def motors_off(self) -> None:
        self._check_idle()
        self.send("M18")
        # With the motors off the head can be pushed around: nothing we knew
        # about its position holds any more.
        self.x = self.y = self.z = None
        self.xy_homed = self.z_zeroed = False
        self.forget_calibration()

    def lift(self) -> None:
        """Get the pen off the paper, whatever state we're in."""
        if self.busy:
            # Anything sent now could be dropped by the printer while it's
            # busy; the job lifts the pen as soon as the current chunk is done.
            self.stop_job()
        elif self.z_zeroed:
            self.pen(down=False)
        else:
            self.jog_z(5)

    # -- plotting -------------------------------------------------------------

    def start_job(self, name: str, chunks: list[Chunk], estimated_seconds: float) -> None:
        self._check_idle()
        if not (self.xy_homed and self.z_zeroed):
            raise PrinterError("Finish the setup steps first")
        total = sum(len(c.lines) for c in chunks)
        self.job = Job(name=name, total_lines=total, estimated_seconds=estimated_seconds)
        self._stop_job.clear()
        threading.Thread(target=self._run_job, args=(self.job, chunks), daemon=True).start()

    def stop_job(self) -> None:
        if self.busy and self.job is not None:
            self.job.status = "stopping"
            self.job.message = "Finishing the last few lines, then lifting the pen"
            self._stop_job.set()

    def _marker(self) -> int | None:
        try:
            return int(self.report.get("mc_percent"))
        except TypeError, ValueError:
            return None

    def _run_job(self, job: Job, chunks: list[Chunk]) -> None:
        """Send the chunks one at a time.

        Each chunk ends with an `M73 P<n>` progress marker, which the printer
        echoes back as `mc_percent` in its status report once it reads it.
        Only then is the next chunk sent: the printer silently drops G-code
        that arrives while its buffer is still full (see MAX_MESSAGE_BYTES).
        """
        first = (self._marker() or 0) + 1
        markers = [(first + i) % 99 + 1 for i in range(len(chunks))]

        try:
            for index, chunk in enumerate(chunks):
                if self._stop_job.is_set():
                    break
                # The last chunk waits for motion to finish before its marker,
                # so the job reads as done when the pen has actually stopped.
                tail = ["M400"] if index == len(chunks) - 1 else []
                sequence_id = self.send(*chunk.lines, *tail, f"M73 P{markers[index]} R0")
                self._wait_for_marker(markers[index], sequence_id, first_chunk=job.done_lines == 0)
                job.done_lines += len(chunk.lines)
                self.x, self.y = chunk.end

            stopped = self._stop_job.is_set()
            self.send("G90", f"G1 Z{self.settings.pen_up + 5:.2f} F{Z_SPEED:.0f}")
            self.z = self.settings.pen_up + 5
            job.status = "stopped" if stopped else "done"
            job.message = "Stopped, pen lifted" if stopped else "Finished!"
        except Exception as e:  # noqa: BLE001 - surface anything to the UI
            job.status = "failed"
            job.message = str(e)
            # We don't know how far the printer got: re-home before trusting X/Y.
            self.x = self.y = None
            self.xy_homed = False
            try:
                self.send("G90", f"G1 Z{self.settings.pen_up + 5:.2f} F{Z_SPEED:.0f}")
                self.z = self.settings.pen_up + 5
                job.message += ". The pen has been lifted."
            except PrinterError:
                pass
        finally:
            job.finished_at = time.time()
            self.remember()

    def _wait_for_marker(self, marker: int, sequence_id: str, first_chunk: bool) -> None:
        sent_at = time.time()
        last_poll = 0.0
        while self._marker() != marker:
            if reason := self.rejection(sequence_id):
                raise PrinterError(f"The printer refused the drawing commands: {reason}")
            if not self.connected:
                raise PrinterError("Lost connection to the printer mid-plot")
            if time.time() - sent_at > 60:
                raise PrinterError(
                    "The printer accepted the drawing commands but isn't running them"
                    if first_chunk
                    else "The printer stopped reporting progress"
                )
            # Status reports come every few seconds on their own; ask for them
            # more often so the next chunk goes out promptly.
            if time.time() - last_poll > 0.5:
                self.request_status()
                last_poll = time.time()
            time.sleep(0.05)

    # -- state for the UI ------------------------------------------------------

    def snapshot(self) -> dict:
        report = self.report
        w, h = self.settings.bed_size
        s = self.settings
        job = self.job
        return {
            "connected": self.connected,
            "connecting": self.connecting,
            "error": self.error,
            "printer_state": report.get("gcode_state"),
            "bed": {"width": w, "height": h, "model": s.model},
            "head": {"x": self.x, "y": self.y, "z": self.z},
            "xy_homed": self.xy_homed,
            "saved_calibration": (c.model_dump() if (c := self.saved_calibration) else None),
            "z_zeroed": self.z_zeroed,
            "paper_top_left": s.paper_top_left.model_dump() if s.paper_top_left else None,
            "paper_bottom_right": s.paper_bottom_right.model_dump() if s.paper_bottom_right else None,
            "pen_up": s.pen_up,
            "pen_pressure": s.pen_pressure,
            "draw_speed": s.draw_speed,
            "job": (
                {
                    "name": job.name,
                    "status": job.status,
                    "progress": job.done_lines / job.total_lines if job.total_lines else 1,
                    "message": job.message,
                    "elapsed": (job.finished_at or time.time()) - job.started_at,
                    "estimated_seconds": job.estimated_seconds,
                }
                if job
                else None
            ),
        }


class PrinterError(Exception):
    pass


printer = Printer()
