import secrets
from typing import Annotated, Literal

from cross_inertia.fastapi import InertiaDep, inertia_exception_handlers
from cross_inertia.fastapi.experimental import inertia_lifespan
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from . import design, plot
from . import settings as settings_module
from .camera import camera
from .printer import PrinterError, printer
from .settings import BED_PRESETS, Point

app = FastAPI(exception_handlers=inertia_exception_handlers(), lifespan=inertia_lifespan)
# Only used by Inertia to carry validation errors across redirects.
app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(16))
app.mount("/static", StaticFiles(directory="static", check_dir=False), name="static")

# Used for the preview until the paper has been marked.
DEFAULT_PAPER = (105.0, 148.0)

PAPER_SIZES = {
    "A6": (105.0, 148.0),
    "A5": (148.0, 210.0),
    "Postcard": (101.6, 152.4),
    "Square 15cm": (150.0, 150.0),
    "Index card": (76.2, 127.0),
}


class Design(BaseModel):
    kind: Literal["text", "image", "svg"] = "text"
    text: str = design.random_poem()
    # The text with its styling. Without it, `text` is drawn all in `font` and `size`.
    doc: list[design.Paragraph] | None = None
    font: str = "scripts"
    size: float = 5.0
    line_spacing: float = 1.6
    align: Literal["left", "center", "right"] = "left"
    margin: float = 12.0
    fit: bool = True
    image_mode: Literal["outline", "fill", "edges", "spiral", "circles", "squiggle", "crosshatch"] = "outline"
    threshold: int = 128
    invert: bool = False
    spacing: float = 0.8
    gamma: float = 1.0

    # Where the drawing sits on the paper, on top of the automatic layout.
    rotation: float = 0.0  # degrees, clockwise
    scale: float = 100.0  # percent
    offset_x: float = 0.0  # mm
    offset_y: float = 0.0  # mm

    def layout_key(self) -> str:
        """Everything except the position, which is cheap to apply."""
        sideways = 45 < abs(self.rotation) % 180 < 135
        return self.model_dump_json(exclude={"rotation", "scale", "offset_x", "offset_y"}) + str(sideways)


class State:
    def __init__(self) -> None:
        # Pick up the last drawing where we left off.
        s = printer.settings
        try:
            self.design = Design.model_validate(s.design) if s.design else Design()
        except ValueError:
            self.design = Design()
        self.upload: bytes | None = None
        self.upload_name: str | None = None
        if s.upload_name:
            try:
                self.upload, self.upload_name = settings_module.UPLOAD_PATH.read_bytes(), s.upload_name
            except OSError:
                pass
        self.notice: tuple[str, str] | None = None  # (kind, message)
        self._cache: tuple[object, list] | None = None
        if not s.design:
            # Even the random starting poem should still be there next time.
            self.save_design()

    def save_design(self) -> None:
        printer.settings.design = self.design.model_dump()
        printer.settings.upload_name = self.upload_name
        settings_module.save(printer.settings)


state = State()


def back(kind: str | None = None, message: str | None = None) -> RedirectResponse:
    if message:
        state.notice = (kind or "info", message)
    return RedirectResponse("/", status_code=303)


def paper_size() -> tuple[float, float]:
    s = printer.settings
    if s.paper_top_left and s.paper_bottom_right:
        return (
            abs(s.paper_bottom_right.x - s.paper_top_left.x),
            abs(s.paper_bottom_right.y - s.paper_top_left.y),
        )
    return DEFAULT_PAPER


def strokes_on_paper() -> tuple[list[design.Stroke], bool, dict | None]:
    """The current design on the paper, ordered for drawing.

    Also says whether some of it was cut off for being outside the paper, and
    how it was moved there: the page draws handles from that, and shifts the
    preview to follow them until a new one arrives.
    """
    d = state.design
    paper_w, paper_h = paper_size()
    placed = laid_out(paper_w, paper_h)
    if not placed:
        return [], False, None
    scale = d.scale / 100
    if d.kind != "text":
        # At 100% a picture fills the paper whichever way it's turned. Text
        # keeps its letter size instead.
        turned = plot.transform(placed, rotation=d.rotation, scale=1, offset=(0, 0))
        x0, y0, x1, y1 = plot.bounds(turned)
        room_w, room_h = paper_w - 2 * d.margin, paper_h - 2 * d.margin
        scale *= min(1.0, room_w / max(x1 - x0, 1e-6), room_h / max(y1 - y0, 1e-6))
    moved = plot.transform(placed, rotation=d.rotation, scale=scale, offset=(d.offset_x, d.offset_y))
    x0, y0, x1, y1 = plot.bounds(moved)
    overflow = x0 < -0.5 or y0 < -0.5 or x1 > paper_w + 0.5 or y1 > paper_h + 0.5
    frame = {
        "box": plot.bounds(placed),
        "scale": scale,
        # How much smaller than asked it had to be to fit, for pictures.
        "fit": scale / (d.scale / 100),
        "rotation": d.rotation,
        "offset": (d.offset_x, d.offset_y),
    }
    return plot.order(plot.clip(moved, paper_w, paper_h)), overflow, frame


def laid_out(paper_w: float, paper_h: float) -> list[design.Stroke]:
    """The design placed on the paper by the automatic layout. Cached: tracing images is slow."""
    d = state.design
    key = (d.layout_key(), paper_w, paper_h, id(state.upload))
    if state._cache and state._cache[0] == key:
        return state._cache[1]

    room_w, room_h = paper_w - 2 * d.margin, paper_h - 2 * d.margin
    if d.kind == "text":
        strokes = design.text_strokes(
            d.doc if d.doc is not None else design.plain_paragraphs(d.text, d.align),
            font=d.font,
            size=d.size,
            max_width=room_w,
            line_spacing=d.line_spacing,
        )
        # Text keeps the size asked for, starting at the top-left margin.
        placed = [[(x + d.margin, y + d.margin) for x, y in s] for s in strokes]
    elif state.upload is None:
        placed = []
    elif d.kind == "svg":
        strokes = design.svg_strokes(state.upload)
        placed = plot.place(strokes, paper_w=paper_w, paper_h=paper_h, margin=d.margin, fit=d.fit)
    else:
        # Turned sideways, an image has the paper's height to fill across.
        sideways = 45 < abs(d.rotation) % 180 < 135
        strokes = design.image_strokes(
            state.upload,
            width_mm=room_h if sideways else room_w,
            height_mm=room_w if sideways else room_h,
            mode=d.image_mode,
            threshold=d.threshold,
            invert=d.invert,
            spacing=d.spacing,
            gamma=d.gamma,
        )
        # Already traced at the right size; the rotation-aware fit happens later.
        placed = plot.center(strokes, paper_w, paper_h)

    state._cache = (key, placed)
    return placed


def preview() -> dict:
    paper_w, paper_h = paper_size()
    try:
        strokes, overflow, frame = strokes_on_paper()
    except Exception as e:  # noqa: BLE001 - show any tracing error next to the design
        return {"d": "", "width": paper_w, "height": paper_h, "error": str(e), "strokes": 0}
    draw, _ = plot.length(strokes)
    return {
        "bounds": plot.bounds(strokes) if strokes else None,
        "d": plot.preview_path(strokes),
        "width": paper_w,
        "height": paper_h,
        "strokes": len(strokes),
        "draw_mm": round(draw),
        "estimated_seconds": round(plot.estimate_seconds(strokes, printer.settings)),
        "overflow": overflow,
        "frame": frame,
        "error": None,
    }


@app.get("/")
def index(inertia: InertiaDep):
    notice, state.notice = state.notice, None
    s = printer.settings
    return inertia.render(
        "Plotter",
        {
            "printer": printer.snapshot,
            "connection": {
                "ip": s.ip,
                "serial": s.serial,
                "has_access_code": bool(s.access_code),
            },
            "models": {key: label for key, (label, _, _) in BED_PRESETS.items()},
            "paper_sizes": PAPER_SIZES,
            "design": lambda: state.design.model_dump() | {"upload_name": state.upload_name},
            "preview": preview,
            "fonts": design.FONTS,
            "notice": {"kind": notice[0], "message": notice[1]} if notice else None,
        },
    )


def run(action, success: str | None = None) -> RedirectResponse:
    try:
        action()
    except PrinterError as e:
        return back("error", str(e))
    finally:
        printer.remember()
    return back("success", success) if success else back()


class Connect(BaseModel):
    ip: str
    serial: str
    access_code: str = ""
    model: str = "a1mini"


@app.post("/connect")
def connect(body: Connect):
    if body.model in BED_PRESETS:
        printer.settings.model = body.model
    printer.connect(body.ip, body.serial, body.access_code or printer.settings.access_code)
    if printer.error:
        return back("error", printer.error)
    return back("success", "Connected to the printer")


@app.post("/disconnect")
def disconnect():
    printer.disconnect()
    return back()


@app.post("/home")
def home():
    return run(printer.home)


class Jog(BaseModel):
    axis: Literal["x", "y", "z"]
    distance: float


@app.post("/jog")
def jog(body: Jog):
    if body.axis == "z":
        return run(lambda: printer.jog_z(body.distance))
    dx = body.distance if body.axis == "x" else 0
    dy = body.distance if body.axis == "y" else 0
    return run(lambda: printer.jog_xy(dx, dy))


@app.post("/move")
def move(body: Point):
    return run(lambda: printer.move_to(body.x, body.y))


@app.post("/pen/touching")
def pen_touching():
    return run(printer.set_pen_touching, "Pen height saved. The pen is now lifted.")


class Pen(BaseModel):
    down: bool


@app.post("/pen")
def pen(body: Pen):
    return run(lambda: printer.pen(body.down))


@app.post("/pen/lift")
def pen_lift():
    busy = printer.busy
    return run(printer.lift, "Stopping after the current few lines, then lifting the pen" if busy else None)


@app.post("/calibration/restore")
def calibration_restore():
    return run(printer.restore_calibration, "Using the previous position and pen height")


@app.post("/calibration/forget")
def calibration_forget():
    printer.forget_calibration()
    return back()


@app.post("/motors-off")
def motors_off():
    return run(printer.motors_off)


class Corner(BaseModel):
    corner: Literal["top_left", "bottom_right"]


@app.post("/paper/corner")
def paper_corner(body: Corner):
    if printer.x is None or printer.y is None:
        return back("error", "Home X/Y first so we know where the pen is")
    s = printer.settings
    point = Point(x=printer.x, y=printer.y)
    if body.corner == "top_left":
        s.paper_top_left = point
    else:
        s.paper_bottom_right = point
    settings_module.save(s)
    return back()


class PaperSize(BaseModel):
    width: float
    height: float


@app.post("/paper/size")
def paper_size_preset(body: PaperSize):
    """Work out the bottom-right corner from the top-left and a paper size.

    Assumes the top of the paper faces the back of the printer, which is how
    the bed is drawn on the page.
    """
    s = printer.settings
    if not s.paper_top_left:
        return back("error", "Mark the top-left corner first")
    s.paper_bottom_right = Point(x=s.paper_top_left.x + body.width, y=s.paper_top_left.y - body.height)
    settings_module.save(s)
    return back()


@app.post("/paper/clear")
def paper_clear():
    s = printer.settings
    s.paper_top_left = s.paper_bottom_right = None
    settings_module.save(s)
    return back()


class PenSettings(BaseModel):
    pen_up: float
    pen_pressure: float
    draw_speed: float


@app.post("/settings")
def save_settings(body: PenSettings):
    s = printer.settings
    s.pen_up = min(max(body.pen_up, 1.0), 20.0)
    s.pen_pressure = min(max(body.pen_pressure, 0.0), 2.0)
    s.draw_speed = min(max(body.draw_speed, 300.0), 12000.0)
    settings_module.save(s)
    return back()


@app.post("/design")
def update_design(body: Design):
    state.design = body.model_copy(update={"text": body.text.replace("\r\n", "\n")})
    state.save_design()
    return back()


@app.post("/design/poem")
def new_poem():
    state.design = state.design.model_copy(update={"kind": "text", "text": design.random_poem(), "doc": None})
    state.save_design()
    return back()


@app.post("/design/upload")
async def upload(file: Annotated[UploadFile, File()]):
    data = await file.read()
    name = file.filename or "upload"
    is_svg = name.lower().endswith(".svg") or (file.content_type or "").startswith("image/svg")
    state.upload, state.upload_name = data, name
    state.design = state.design.model_copy(update={"kind": "svg" if is_svg else "image"})
    settings_module.UPLOAD_PATH.parent.mkdir(parents=True, exist_ok=True)
    settings_module.UPLOAD_PATH.write_bytes(data)
    state.save_design()
    if is_svg and design.svg_has_text(data):
        return back(
            "warning",
            "This SVG has text in it, which can't be plotted directly. "
            "Convert text to paths in your editor, or use the Text tab.",
        )
    return back()


@app.post("/plot/start")
def plot_start():
    s = printer.settings
    if not (s.paper_top_left and s.paper_bottom_right):
        return back("error", "Mark the paper first")
    strokes, _, _ = strokes_on_paper()
    if not strokes:
        return back("error", "There's nothing to draw yet")
    name = state.upload_name if state.design.kind != "text" else state.design.text.strip().split("\n")[0][:40]
    chunks = plot.gcode_chunks(strokes, s)
    return run(lambda: printer.start_job(name or "Drawing", chunks, plot.estimate_seconds(strokes, s)))


@app.post("/plot/stop")
def plot_stop():
    printer.stop_job()
    return back()


@app.get("/camera.jpg")
def camera_frame():
    s = printer.settings
    if not s.has_credentials:
        return Response(status_code=404)
    frame = camera.latest(s.ip, s.access_code)
    if frame is None:
        return Response(status_code=204, headers={"X-Camera-Error": camera.error or "starting"})
    return Response(frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
