import { useRef, useState } from "react";

import type { Design, Preview } from "@/types";

import type { UpdateDesign } from "./design-panel";

type Drag =
  | { kind: "move"; from: DOMPoint; offset: [number, number] }
  | { kind: "scale"; from: DOMPoint; scale: number }
  | { kind: "rotate"; from: DOMPoint; rotation: number };

/**
 * The paper on its own, as the pen will draw it. Drag the drawing to move it,
 * a corner to resize it, or the round handle on top to turn it.
 *
 * The preview comes from the server and takes a moment to catch up, so in the
 * meantime it's shifted from where the server put it to where the handles are.
 */
export function PaperView({ design, update, preview }: { design: Design; update: UpdateDesign; preview: Preview }) {
  const { width: W, height: H, frame } = preview;
  const svgRef = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<Drag | null>(null);

  function toPaper(e: React.PointerEvent) {
    return new DOMPoint(e.clientX, e.clientY).matrixTransform(svgRef.current!.getScreenCTM()!.inverse());
  }

  let correction = "";
  let corners: DOMPoint[] = [];
  let pivot = new DOMPoint();
  let rotateHandle: DOMPoint | null = null;
  if (frame) {
    const [x0, y0, x1, y1] = frame.box;
    const cx = (x0 + x1) / 2;
    const cy = (y0 + y1) / 2;
    const place = (rotation: number, scale: number, [ox, oy]: [number, number]) =>
      new DOMMatrix().translate(cx + ox, cy + oy).rotate(rotation).scale(scale).translate(-cx, -cy);
    const shown = place(frame.rotation, frame.scale, frame.offset);
    const wanted = place(design.rotation, frame.fit * (design.scale / 100), [design.offset_x, design.offset_y]);
    correction = wanted.multiply(shown.inverse()).toString();
    const pad = 1.5 / Math.max(frame.fit * (design.scale / 100), 0.05);
    corners = [
      [x0 - pad, y0 - pad],
      [x1 + pad, y0 - pad],
      [x1 + pad, y1 + pad],
      [x0 - pad, y1 + pad],
    ].map(([x, y]) => wanted.transformPoint(new DOMPoint(x, y)));
    pivot = wanted.transformPoint(new DOMPoint(cx, cy));
    // Above the middle of the top edge, pointing away from the drawing.
    const topMid = new DOMPoint((corners[0]!.x + corners[1]!.x) / 2, (corners[0]!.y + corners[1]!.y) / 2);
    const away = Math.hypot(topMid.x - pivot.x, topMid.y - pivot.y) || 1;
    rotateHandle = new DOMPoint(topMid.x + ((topMid.x - pivot.x) / away) * 8, topMid.y + ((topMid.y - pivot.y) / away) * 8);
  }

  function start(e: React.PointerEvent, next: Drag) {
    e.stopPropagation();
    svgRef.current!.setPointerCapture(e.pointerId);
    setDrag(next);
  }

  function onMove(e: React.PointerEvent) {
    if (!drag) return;
    const p = toPaper(e);
    if (drag.kind === "move") {
      update({ offset_x: round1(drag.offset[0] + p.x - drag.from.x), offset_y: round1(drag.offset[1] + p.y - drag.from.y) });
    } else if (drag.kind === "scale") {
      const ratio = Math.hypot(p.x - pivot.x, p.y - pivot.y) / Math.max(Math.hypot(drag.from.x - pivot.x, drag.from.y - pivot.y), 0.1);
      update({ scale: Math.round(Math.min(Math.max(drag.scale * ratio, 10), 300)) });
    } else {
      const angle = (q: DOMPoint) => (Math.atan2(q.y - pivot.y, q.x - pivot.x) * 180) / Math.PI;
      let rotation = drag.rotation + angle(p) - angle(drag.from);
      // Shift snaps to 15°.
      rotation = e.shiftKey ? Math.round(rotation / 15) * 15 : Math.round(rotation);
      update({ rotation: wrap(rotation) });
    }
  }

  const handle = 2.2;
  const outline = corners.map((c) => `${c.x},${c.y}`).join(" ");

  return (
    <div>
      <svg
        ref={svgRef}
        viewBox={`-10 -16 ${W + 20} ${H + 26}`}
        className="mx-auto block max-h-[75vh] w-full touch-none select-none"
        onPointerMove={onMove}
        onPointerUp={() => setDrag(null)}
        onPointerCancel={() => setDrag(null)}
      >
        <defs>
          <clipPath id="paper-clip">
            <rect width={W} height={H} />
          </clipPath>
        </defs>
        <rect width={W} height={H} fill="white" stroke="var(--color-line-strong)" strokeWidth={0.3} style={{ filter: "drop-shadow(0 1px 1.5px rgb(0 0 0 / 0.12))" }} />
        <rect
          x={design.margin}
          y={design.margin}
          width={Math.max(0, W - 2 * design.margin)}
          height={Math.max(0, H - 2 * design.margin)}
          fill="none"
          stroke="var(--color-line)"
          strokeWidth={0.3}
          strokeDasharray="1.5 1.5"
        />

        <path
          d={preview.d}
          transform={correction}
          fill="none"
          stroke="var(--color-ink-line)"
          strokeWidth={0.35}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {frame && rotateHandle && (
          <g>
            <polygon
              points={outline}
              fill="transparent"
              stroke="var(--color-accent)"
              strokeWidth={0.3}
              strokeDasharray="1.5 1"
              opacity={drag ? 1 : 0.6}
              className="cursor-move"
              onPointerDown={(e) => start(e, { kind: "move", from: toPaper(e), offset: [design.offset_x, design.offset_y] })}
            />
            <line
              x1={(corners[0]!.x + corners[1]!.x) / 2}
              y1={(corners[0]!.y + corners[1]!.y) / 2}
              x2={rotateHandle.x}
              y2={rotateHandle.y}
              stroke="var(--color-accent)"
              strokeWidth={0.3}
            />
            <circle
              cx={rotateHandle.x}
              cy={rotateHandle.y}
              r={handle}
              fill="white"
              stroke="var(--color-accent)"
              strokeWidth={0.5}
              className="cursor-grab"
              onPointerDown={(e) => start(e, { kind: "rotate", from: toPaper(e), rotation: design.rotation })}
            >
              <title>Drag to turn. Hold Shift to snap to 15°.</title>
            </circle>
            {corners.map((c, i) => (
              <rect
                key={i}
                x={c.x - handle / 2 - 0.4}
                y={c.y - handle / 2 - 0.4}
                width={handle + 0.8}
                height={handle + 0.8}
                rx={0.5}
                fill="white"
                stroke="var(--color-accent)"
                strokeWidth={0.5}
                style={{ cursor: i % 2 ? "nesw-resize" : "nwse-resize" }}
                onPointerDown={(e) => start(e, { kind: "scale", from: toPaper(e), scale: design.scale })}
              >
                <title>Drag to resize</title>
              </rect>
            ))}
          </g>
        )}
      </svg>
      <p className="mt-2 text-center text-xs text-muted">
        {frame
          ? `Drag to move, corners to resize, the round handle to turn. ${design.scale}% · ${design.rotation}°`
          : "Nothing to draw yet."}
      </p>
    </div>
  );
}

/** Keep angles in -180..180, so the slider can show them. */
const wrap = (deg: number) => ((((deg + 180) % 360) + 360) % 360) - 180;
const round1 = (v: number) => Math.round(v * 10) / 10;
