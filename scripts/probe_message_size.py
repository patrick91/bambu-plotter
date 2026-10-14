"""Send motion-free G-code batches of growing size and show which ones the printer runs."""
import json, ssl, time, sys
import paho.mqtt.client as mqtt
cfg = json.load(open(__import__("os").path.expanduser("~/.config/bambu-plotter/settings.json")))
serial = cfg["serial"]
seen = []
def on_message(c, u, msg):
    p = json.loads(msg.payload).get("print", {})
    keys = {k: p[k] for k in ("command", "result", "reason", "mc_percent", "gcode_state", "print_error", "param") if k in p}
    if keys.get("command") not in (None, "push_status") or "mc_percent" in keys or "result" in keys:
        seen.append((round(time.time() - t0, 1), {k: (v if k != 'param' else f'<{len(v)} bytes>') for k, v in keys.items()}))
c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.username_pw_set("bblp", cfg["access_code"]); c.tls_set(cert_reqs=ssl.CERT_NONE); c.tls_insecure_set(True)
c.on_message = on_message
c.connect(cfg["ip"], 8883); c.loop_start(); time.sleep(1)
c.subscribe(f"device/{serial}/report"); time.sleep(1)
t0 = time.time()
def send(lines, label):
    seen.append((round(time.time() - t0, 1), f">>> {label} ({len(lines)} lines, {len(chr(10).join(lines))} bytes)"))
    c.publish(f"device/{serial}/request", json.dumps({"print": {"sequence_id": label, "command": "gcode_line", "param": "\n".join(lines) + "\n"}}))
def pushall(): c.publish(f"device/{serial}/request", json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))
def zero_moves(n, marker):
    # Relative zero-length moves: realistic line length, no motion.
    return ["G91"] + ["G1 X0.00 Y0.00 F3000"] * n + ["G90", f"M73 P{marker} R0"]

for label, lines in [
    ("~1KB", zero_moves(45, 21)),
    ("~2KB", zero_moves(90, 22)),
    ("~3KB", zero_moves(135, 23)),
    ("~4KB", zero_moves(180, 24)),
]:
    send(lines, label)
    for _ in range(6): time.sleep(1); pushall()
c.loop_stop()
for s in seen: print(s)
