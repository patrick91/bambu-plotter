import { useEffect, useRef, useState } from "react";

import type { Preview, PrinterState } from "@/types";

import { act } from "./ui";

/**
 * The bed seen from above, with the front of the printer at the bottom.
 * Machine Y grows towards the back, so screen y = height - machine y.
 */
export function BedView({
  printer,
  preview,
  onMoveDrawing,
}: {
  printer: PrinterState;
  preview: Preview;
  onMoveDrawing: (dx: number, dy: number) => void;
}) {
  const { width: W, height: H } = printer.bed;
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<{ x: number; y: number } | null>(null);
  // While dragging, the drawing follows the pointer before the server catches up.
  const [drag, setDrag] = useState<{ start: { x: number; y: number }; dx: number; dy: number } | null>(null);
  const [pending, setPending] = useState<{ dx: number; dy: number } | null>(null);
  useEffect(() => setPending(null), [preview.d]);

  const canMove = printer.connected && printer.xy_homed && !isBusy(printer);
  const { x, y } = printer.head;
  const tl = printer.paper_top_left;
  const br = printer.paper_bottom_right;

  // Without marked paper, sketch the preview in the middle of the bed so you
  // can still see roughly how big it'll be.
  const paperTL = tl ?? { x: (W - preview.width) / 2, y: (H + preview.height) / 2 };
  const sx = br && tl ? Math.sign(br.x - tl.x) || 1 : 1;
  const sy = br && tl ? Math.sign(br.y - tl.y) || -1 : -1;
  const paperMarked = Boolean(tl && br);

  function toMachine(event: React.MouseEvent) {
    const svg = svgRef.current!;
    const pt = svg.createSVGPoint();
    pt.x = event.clientX;
    pt.y = event.clientY;
    const p = pt.matrixTransform(svg.getScreenCTM()!.inverse());
    return { x: clamp(p.x, 0, W), y: clamp(H - p.y, 0, H) };
  }

  const penDown = printer.head.z !== null && printer.head.z <= 0.05;

  // Pointer movement on the bed, in paper millimetres.
  function paperDelta(from: { x: number; y: number }, to: { x: number; y: number }) {
    return { dx: (to.x - from.x) * sx, dy: (to.y - from.y) * sy };
  }
  const shift = drag ?? pending ?? { dx: 0, dy: 0 };
  const b = preview.bounds;

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        viewBox={`-14 -10 ${W + 24} ${H + 24}`}
        className={canMove ? "w-full cursor-crosshair select-none" : "w-full select-none"}
        onMouseMove={(e) => setHover(toMachine(e))}
        onMouseLeave={() => setHover(null)}
        onClick={(e) => {
          if (!canMove) return;
          const p = toMachine(e);
          act("/move", { x: round1(p.x), y: round1(p.y) });
        }}
      >
        <defs>
          <pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse" y={H % 10}>
            <path d="M10 0H0V10" fill="none" stroke="var(--color-grid)" strokeWidth="0.3" />
          </pattern>
        </defs>

        <rect x={0} y={0} width={W} height={H} rx={3} fill="var(--color-bed)" />
        <rect x={0} y={0} width={W} height={H} rx={3} fill="url(#grid)" />

        {[0, 50, 100, 150, 200, 250].filter((v) => v <= W).map((v) => (
          <text key={`x${v}`} x={v} y={H + 7} fontSize={4.5} textAnchor="middle" fill="var(--color-muted)">
            {v}
          </text>
        ))}
        {[0, 50, 100, 150, 200, 250].filter((v) => v <= H).map((v) => (
          <text key={`y${v}`} x={-3} y={H - v + 1.5} fontSize={4.5} textAnchor="end" fill="var(--color-muted)">
            {v}
          </text>
        ))}
        <text x={W / 2} y={H + 12.5} fontSize={4.5} textAnchor="middle" fill="var(--color-muted)" letterSpacing={1}>
          FRONT OF PRINTER
        </text>

        {/* Paper and drawing */}
        <g transform={`translate(${paperTL.x} ${H - paperTL.y}) scale(${sx} ${-sy})`}>
          <rect
            width={preview.width}
            height={preview.height}
            fill="white"
            stroke={paperMarked ? "var(--color-line-strong)" : "var(--color-muted)"}
            strokeWidth={0.5}
            strokeDasharray={paperMarked ? undefined : "3 2"}
            opacity={paperMarked ? 1 : 0.85}
          />
          <g transform={`translate(${shift.dx} ${shift.dy})`}>
            <path
              d={preview.d}
              fill="none"
              stroke="var(--color-ink-line)"
              strokeWidth={0.35}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={paperMarked ? 1 : 0.5}
            />
            {b && (
              <rect
                x={b[0] - 1}
                y={b[1] - 1}
                width={b[2] - b[0] + 2}
                height={b[3] - b[1] + 2}
                fill="transparent"
                stroke={drag ? "var(--color-accent)" : "none"}
                strokeWidth={0.5}
                strokeDasharray="2 1.5"
                className="cursor-move hover:stroke-[var(--color-accent)]"
                onPointerDown={(e) => {
                  e.stopPropagation();
                  e.currentTarget.setPointerCapture(e.pointerId);
                  setDrag({ start: toMachine(e), dx: 0, dy: 0 });
                }}
                onPointerMove={(e) => {
                  if (!drag) return;
                  setDrag({ ...drag, ...paperDelta(drag.start, toMachine(e)) });
                }}
                onPointerUp={() => {
                  if (!drag) return;
                  if (Math.abs(drag.dx) + Math.abs(drag.dy) > 0.2) {
                    setPending({ dx: drag.dx, dy: drag.dy });
                    onMoveDrawing(drag.dx, drag.dy);
                  }
                  setDrag(null);
                }}
                onClick={(e) => e.stopPropagation()}
              />
            )}
          </g>
        </g>

        {tl && <CornerMark x={tl.x} y={H - tl.y} label="top-left" />}
        {br && <CornerMark x={br.x} y={H - br.y} label="bottom-right" />}

        {/* Pen */}
        {x !== null && y !== null && (
          <g transform={`translate(${x} ${H - y})`} style={{ transition: "transform 400ms ease-out" }}>
            <circle r={penDown ? 2.2 : 3.5} fill={penDown ? "var(--color-accent)" : "none"} stroke="var(--color-accent)" strokeWidth={0.8} />
            <path d="M-6 0H-4M4 0H6M0 -6V-4M0 4V6" stroke="var(--color-accent)" strokeWidth={0.8} />
          </g>
        )}

        {canMove && hover && (
          <circle cx={hover.x} cy={H - hover.y} r={2.5} fill="none" stroke="var(--color-accent)" strokeWidth={0.5} strokeDasharray="1 1" />
        )}
      </svg>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span className="font-mono tabular-nums">
          Pen{" "}
          {x !== null && y !== null ? `X ${x.toFixed(1)}  Y ${y.toFixed(1)}` : "X ?  Y ?"}
          {"  "}
          {printer.head.z !== null ? `Z ${printer.head.z.toFixed(2)}` : "Z ?"}
          {printer.z_zeroed && printer.head.z !== null && (penDown ? " (down)" : " (up)")}
        </span>
        <span>
          {canMove
            ? hover
              ? `Click to move the pen to ${hover.x.toFixed(0)}, ${hover.y.toFixed(0)}`
              : "Click anywhere on the bed to move the pen there"
            : !paperMarked
              ? "Dashed: preview of the paper size, not marked yet"
              : ""}
        </span>
      </div>
    </div>
  );
}

function CornerMark({ x, y, label }: { x: number; y: number; label: string }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <circle r={1.6} fill="var(--color-corner)" />
      <text y={-3} fontSize={3.8} textAnchor="middle" fill="var(--color-corner)" fontWeight={600}>
        {label}
      </text>
    </g>
  );
}

export function isBusy(printer: PrinterState) {
  return printer.job?.status === "running" || printer.job?.status === "stopping";
}

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);
const round1 = (v: number) => Math.round(v * 10) / 10;
