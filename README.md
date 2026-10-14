# Bambu Plotter

Turn a Bambu Lab printer into a pen plotter, with a page that tells you what to
do at each step: when to put the pen in, how to set its height, and where the
paper is on the bed.

Draw handwritten-style text (letters, poems), trace PNG/JPEG images, or plot
SVGs.

## Running it

```bash
bun install
uv run fastapi dev app/main.py
```

Open http://localhost:8000. The Vite dev server is started for you.

To try it without a printer, run it in simulated mode. G-code is printed to the
terminal instead of being sent:

```bash
BAMBU_PLOTTER_FAKE=1 uv run fastapi dev app/main.py
```

## The printer

- Turn on **LAN Only mode** and **Developer mode** on the printer. The IP
  address and access code are on the same screen.
- Settings are saved to `~/.config/bambu-plotter/settings.json`. On first run
  they're imported from bambucuts' `~/.bambucuts.conf` if it exists.
- Tested in simulation with the A1 mini bed size; A1 and P1 bed sizes are
  available too.

## How it works

The printer doesn't report where its head is, so the app keeps track of it from
the G-code it sends:

1. **Home X/Y.** After this the head position is known (the head is parked in
   the middle of the bed). Z is never homed, because homing Z would drive the
   nozzle (and the pen next to it) into the bed.
2. **Pen height.** You lower the pen until it touches the paper and the app
   calls that Z=0. The pen travels `Lift` mm above it and draws at `Press` mm
   below it.
3. **Paper corners.** You move the pen tip over the paper's top-left (and
   bottom-right) corner. Corners are recorded where the *pen* is, so the pen's
   offset from the nozzle never matters.

Plots are sent over MQTT as `gcode_line` commands in chunks of about 150 lines.
Each chunk ends with an `M73 P<n>` marker, which the printer echoes back as
`mc_percent` once it gets there. That's how progress is tracked, and how
stopping works: no more chunks are sent, and the pen is lifted once the ones
already queued have run.

Approach and protocol details are borrowed from
[bambu-cuts](https://github.com/unrelatedlabs/bambu-cuts).

## Layout

- `app/printer.py`: MQTT connection, moves, head tracking, the plot runner
- `app/design.py`: text (Hershey single-stroke fonts), SVG and image tracing to strokes
- `app/plot.py`: layout on the paper, stroke ordering, G-code
- `app/camera.py`: snapshots from the printer camera
- `frontend/`: the React page (Inertia)
