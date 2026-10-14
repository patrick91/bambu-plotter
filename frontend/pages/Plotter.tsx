import { router, usePoll } from "@inertiajs/react";
import clsx from "clsx";
import { ArrowUpToLine, Camera, CircleAlert, CircleCheck, Info, PenLine, Play, Square, X } from "lucide-react";
import { useEffect, useState } from "react";

import { BedView, isBusy } from "@/components/bed-view";
import { DesignPanel, useDesign } from "@/components/design-panel";
import { SetupSteps } from "@/components/steps";
import { act, Button, formatDuration, Instruction } from "@/components/ui";
import type { PageProps, PrinterState } from "@/types";

export default function Plotter(props: PageProps) {
  const { printer, preview } = props;
  const [design, updateDesign] = useDesign(props.design);
  usePoll(isBusy(printer) ? 700 : 1500, { only: ["printer"] });

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="grid size-8 place-items-center rounded-lg bg-accent text-white">
              <PenLine className="size-4.5" />
            </span>
            <h1 className="text-lg font-semibold tracking-tight">Bambu Plotter</h1>
          </div>
          <ConnectionPill printer={printer} />
        </div>
      </header>

      <Notice notice={props.notice} />

      <main className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[400px_1fr]">
        <div className="space-y-6">
          <div>
            <h2 className="mb-3 text-xs font-semibold tracking-wider text-muted uppercase">Set up</h2>
            <SetupSteps props={props} />
          </div>
          <div>
            <h2 className="mb-3 text-xs font-semibold tracking-wider text-muted uppercase">What to draw</h2>
            <div className="rounded-xl border border-line bg-surface p-4">
              <DesignPanel props={props} design={design} update={updateDesign} />
            </div>
          </div>
        </div>

        <div className="space-y-4 lg:sticky lg:top-6 lg:self-start">
          <div className="rounded-xl border border-line bg-surface p-4">
            <BedView
              printer={printer}
              preview={preview}
              onMoveDrawing={(dx, dy) => updateDesign({ offset_x: round1(design.offset_x + dx), offset_y: round1(design.offset_y + dy) })}
            />
            <div className="mt-3 flex justify-end border-t border-line pt-3">
              <Button onClick={() => act("/pen/lift")} disabled={!printer.connected || printer.job?.status === "stopping"}>
                <ArrowUpToLine className="size-4" /> {isBusy(printer) ? "Stop and lift pen" : "Lift pen"}
              </Button>
            </div>
          </div>
          <PlotPanel props={props} />
          <PenPanel printer={printer} />
          <CameraPanel enabled={printer.connected} />
        </div>
      </main>
    </div>
  );
}

function ConnectionPill({ printer }: { printer: PrinterState }) {
  const busy = isBusy(printer);
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium",
        printer.connected ? "bg-accent/10 text-accent" : "bg-sunken text-muted",
      )}
    >
      <span className={clsx("size-2 rounded-full", printer.connected ? (busy ? "animate-pulse bg-accent" : "bg-accent") : "bg-muted/50")} />
      {printer.connected ? (busy ? "Plotting" : "Connected") : "Not connected"}
    </span>
  );
}

function Notice({ notice }: { notice: PageProps["notice"] }) {
  const [shown, setShown] = useState(notice);
  useEffect(() => {
    if (!notice) return;
    setShown(notice);
    if (notice.kind === "success" || notice.kind === "info") {
      const t = setTimeout(() => setShown(null), 4000);
      return () => clearTimeout(t);
    }
  }, [notice]);
  if (!shown) return null;
  const Icon = shown.kind === "error" || shown.kind === "warning" ? CircleAlert : shown.kind === "success" ? CircleCheck : Info;
  return (
    <div className="mx-auto max-w-7xl px-4 pt-4 sm:px-6">
      <div
        role="status"
        className={clsx(
          "flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5 text-sm",
          shown.kind === "error" && "border-danger/30 bg-danger/10",
          shown.kind === "warning" && "border-warn/30 bg-warn/10",
          (shown.kind === "success" || shown.kind === "info") && "border-accent/25 bg-accent/5",
        )}
      >
        <Icon className={clsx("mt-0.5 size-4 shrink-0", shown.kind === "error" ? "text-danger" : shown.kind === "warning" ? "text-warn" : "text-accent")} />
        <span className="flex-1">{shown.message}</span>
        <button type="button" onClick={() => setShown(null)} className="text-muted hover:text-ink" aria-label="Dismiss">
          <X className="size-4" />
        </button>
      </div>
    </div>
  );
}

function PlotPanel({ props }: { props: PageProps }) {
  const { printer, preview } = props;
  const job = printer.job;
  const running = isBusy(printer);
  const ready = printer.connected && printer.xy_homed && printer.z_zeroed && printer.paper_top_left && printer.paper_bottom_right;

  if (job && running) {
    return (
      <div className="rounded-xl border border-accent/40 bg-surface p-4">
        <div className="mb-2 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="truncate font-semibold">Drawing “{job.name}”</div>
            <div className="text-xs text-muted">
              {formatDuration(job.elapsed)} elapsed · about {formatDuration(Math.max(0, job.estimated_seconds - job.elapsed))} left
            </div>
          </div>
          <Button variant="danger" onClick={() => act("/plot/stop")} disabled={job.status === "stopping"}>
            <Square className="size-3.5" fill="currentColor" /> {job.status === "stopping" ? "Stopping…" : "Stop and lift pen"}
          </Button>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-sunken">
          <div className="h-full rounded-full bg-accent transition-[width] duration-700" style={{ width: `${Math.round(job.progress * 100)}%` }} />
        </div>
        {job.message && <p className="mt-2 text-xs text-muted">{job.message}</p>}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      {job && job.status !== "running" && (
        <p className={clsx("mb-3 text-sm", job.status === "failed" ? "text-danger" : "text-muted")}>
          Last plot: {job.message} ({formatDuration(job.elapsed)})
        </p>
      )}
      {preview.error && <p className="mb-3 text-sm text-danger">{preview.error}</p>}
      {preview.overflow && (
        <div className="mb-3">
          <Instruction tone="warn">Part of the drawing is off the paper, and that part won't be drawn. Make it smaller, or move it back onto the paper.</Instruction>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm">
          {preview.strokes ? (
            <>
              <span className="font-medium">{preview.strokes} strokes</span>
              <span className="text-muted">
                {" "}
                · {((preview.draw_mm ?? 0) / 1000).toFixed(1)} m of ink · about {formatDuration(preview.estimated_seconds ?? 0)}
              </span>
            </>
          ) : (
            <span className="text-muted">Nothing to draw yet</span>
          )}
        </div>
        <Button variant="primary" size="lg" onClick={() => act("/plot/start")} disabled={!ready || !preview.strokes}>
          <Play className="size-4" fill="currentColor" /> Start drawing
        </Button>
      </div>
      {!ready && <p className="mt-2 text-xs text-muted">Finish the set-up steps on the left to start drawing.</p>}
    </div>
  );
}

function PenPanel({ printer }: { printer: PrinterState }) {
  const [values, setValues] = useState({
    pen_up: printer.pen_up,
    pen_pressure: printer.pen_pressure,
    draw_speed: printer.draw_speed,
  });
  const dirty =
    values.pen_up !== printer.pen_up || values.pen_pressure !== printer.pen_pressure || values.draw_speed !== printer.draw_speed;
  const canPen = printer.connected && printer.z_zeroed && !isBusy(printer);

  return (
    <details className="group rounded-xl border border-line bg-surface">
      <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-semibold">
        Pen controls
        <span className="text-xs font-normal text-muted group-open:hidden">test the pen, height, speed</span>
      </summary>
      <div className="space-y-4 px-4 pb-4">
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => act("/pen", { down: true })} disabled={!canPen}>
            Pen down
          </Button>
          <Button size="sm" onClick={() => act("/pen", { down: false })} disabled={!canPen}>
            Pen up
          </Button>
          <Button size="sm" variant="ghost" onClick={() => act("/motors-off")} disabled={!printer.connected || isBusy(printer)}>
            Release motors
          </Button>
        </div>
        <div className="grid grid-cols-3 gap-3 text-sm">
          <NumberField label="Lift (mm)" value={values.pen_up} step={0.5} onChange={(pen_up) => setValues({ ...values, pen_up })} />
          <NumberField label="Press (mm)" value={values.pen_pressure} step={0.1} onChange={(pen_pressure) => setValues({ ...values, pen_pressure })} />
          <NumberField label="Speed (mm/min)" value={values.draw_speed} step={250} onChange={(draw_speed) => setValues({ ...values, draw_speed })} />
        </div>
        <p className="text-xs text-muted">
          Press is how far below the touch point the pen goes while drawing. Raise it if lines are patchy, lower it if
          the pen drags or tears the paper.
        </p>
        <Button size="sm" variant="primary" disabled={!dirty} onClick={() => router.post("/settings", values, { preserveScroll: true, preserveState: true })}>
          Save
        </Button>
      </div>
    </details>
  );
}

function NumberField({ label, value, step, onChange }: { label: string; value: number; step: number; onChange: (v: number) => void }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-muted">{label}</span>
      <input
        type="number"
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 font-mono text-sm tabular-nums focus:border-accent focus:outline-none"
      />
    </label>
  );
}

function CameraPanel({ enabled }: { enabled: boolean }) {
  const [on, setOn] = useState(false);
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!on || !enabled) return;
    let cancelled = false;
    let url: string | null = null;
    async function tick() {
      while (!cancelled) {
        try {
          const res = await fetch("/camera.jpg", { cache: "no-store" });
          if (res.status === 200) {
            const blob = await res.blob();
            if (url) URL.revokeObjectURL(url);
            url = URL.createObjectURL(blob);
            setSrc(url);
          }
        } catch {
          // keep trying while the panel is open
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
    }
    tick();
    return () => {
      cancelled = true;
    };
  }, [on, enabled]);

  return (
    <div className="rounded-xl border border-line bg-surface">
      <button
        type="button"
        onClick={() => setOn(!on)}
        disabled={!enabled}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold disabled:text-muted"
      >
        <span className="flex items-center gap-2">
          <Camera className="size-4" /> Camera
        </span>
        <span className="text-xs font-normal text-muted">{on ? "Hide" : "Show"}</span>
      </button>
      {on && enabled && (
        <div className="px-4 pb-4">
          {src ? (
            <img src={src} alt="Printer camera" className="w-full rounded-lg bg-sunken" />
          ) : (
            <div className="grid aspect-video place-items-center rounded-lg bg-sunken text-sm text-muted">Waiting for the camera…</div>
          )}
        </div>
      )}
    </div>
  );
}

const round1 = (v: number) => Math.round(v * 10) / 10;
