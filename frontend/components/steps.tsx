import { router } from "@inertiajs/react";
import clsx from "clsx";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Check,
  ChevronDown,
  ChevronsDown,
  ChevronsUp,
  ChevronUp,
  Home,
  Lock,
} from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";

import type { PageProps, PrinterState } from "@/types";

import { isBusy } from "./bed-view";
import { act, Button, Field, Instruction, inputClass } from "./ui";

type StepStatus = "done" | "current" | "locked";

function Step({
  n,
  title,
  status,
  summary,
  open,
  onToggle,
  children,
}: {
  n: number;
  title: string;
  status: StepStatus;
  summary?: ReactNode;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <section
      className={clsx(
        "rounded-xl border bg-surface transition-shadow",
        status === "current" ? "border-accent/40 shadow-sm ring-1 ring-accent/15" : "border-line",
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        disabled={status === "locked"}
        className="flex w-full items-center gap-3 px-4 py-3 text-left disabled:cursor-default"
      >
        <span
          className={clsx(
            "grid size-7 shrink-0 place-items-center rounded-full text-sm font-semibold",
            status === "done" && "bg-accent text-white",
            status === "current" && "bg-accent/10 text-accent ring-1 ring-accent/40",
            status === "locked" && "bg-sunken text-muted",
          )}
        >
          {status === "done" ? <Check className="size-4" strokeWidth={3} /> : status === "locked" ? <Lock className="size-3.5" /> : n}
        </span>
        <span className="min-w-0 flex-1">
          <span className={clsx("block font-semibold", status === "locked" ? "text-muted" : "text-ink")}>{title}</span>
          {summary && !open && <span className="block truncate text-xs text-muted">{summary}</span>}
        </span>
        {status === "done" && !open && <span className="text-xs font-medium text-accent">Change</span>}
        {status !== "locked" && (
          <ChevronDown className={clsx("size-4 text-muted transition-transform", open && "rotate-180")} />
        )}
      </button>
      {open && status !== "locked" && <div className="space-y-3 px-4 pb-4">{children}</div>}
    </section>
  );
}

export function SetupSteps({ props }: { props: PageProps }) {
  const { printer } = props;
  const paperMarked = Boolean(printer.paper_top_left && printer.paper_bottom_right);
  const done = [printer.connected, printer.xy_homed, printer.z_zeroed, paperMarked];
  const current = done.indexOf(false); // -1 when everything's ready
  const status = (i: number): StepStatus =>
    done[i] ? "done" : i === current ? "current" : current !== -1 && i > current ? "locked" : "current";

  // Steps open on their own as you reach them; you can also reopen done ones.
  const [manual, setManual] = useState<Record<number, boolean>>({});
  const isOpen = (i: number) => manual[i] ?? i === current;
  const toggle = (i: number) => setManual((m) => ({ ...m, [i]: !isOpen(i) }));

  return (
    <div className="space-y-3">
      <Step
        n={1}
        title="Connect to the printer"
        status={status(0)}
        open={isOpen(0)}
        onToggle={() => toggle(0)}
        summary={printer.connected ? `Connected to ${props.connection.ip}` : undefined}
      >
        <ConnectForm props={props} />
      </Step>

      <Step
        n={2}
        title="Home the printer"
        status={status(1)}
        open={isOpen(1)}
        onToggle={() => toggle(1)}
        summary="The printer knows where the pen is"
      >
        {printer.saved_calibration && (
          <div className="space-y-2 rounded-lg border border-line p-3">
            <p className="text-sm">
              <strong>Picking up where you left off?</strong> If the printer has stayed on and nobody has moved the head
              or released the motors, you can keep the previous position
              {printer.saved_calibration.z_zeroed && " and pen height"}.
            </p>
            <div className="flex gap-2">
              <Button size="sm" variant="primary" onClick={() => act("/calibration/restore")}>
                Keep previous set-up
              </Button>
              <Button size="sm" variant="ghost" onClick={() => act("/calibration/forget")}>
                Start fresh
              </Button>
            </div>
          </div>
        )}
        <Instruction>
          <strong>Pen: leave it out for now.</strong> Clear the bed, then press Home. The head lifts 10 mm, finds its
          corner and comes back to the middle of the bed, so from now on the app knows exactly where it is.
        </Instruction>
        <Button variant={printer.saved_calibration ? "secondary" : "primary"} onClick={() => act("/home")} disabled={isBusy(printer)}>
          <Home className="size-4" /> Home X and Y
        </Button>
      </Step>

      <Step
        n={3}
        title="Paper and pen height"
        status={status(2)}
        open={isOpen(2)}
        onToggle={() => toggle(2)}
        summary={`Pen lifts ${printer.pen_up} mm between lines`}
      >
        <ol className="list-decimal space-y-1.5 pl-5 text-sm text-ink">
          <li>Tape your paper to the bed. Its top edge should face the back of the printer.</li>
          <li>
            Move the pen over the paper: click on the paper in the bed picture.
          </li>
          <li>
            <strong>Now put the pen in the holder</strong>, with its tip a few millimetres above the paper.
          </li>
          <li>Lower the head until the tip <em>just</em> touches the paper. Go slowly at the end.</li>
        </ol>
        <ZJog printer={printer} />
        <Button variant="primary" className="w-full" onClick={() => act("/pen/touching")} disabled={!printer.connected || isBusy(printer)}>
          The pen is touching the paper
        </Button>
        <p className="text-xs text-muted">
          This becomes the paper height. The pen then lifts {printer.pen_up} mm, and will only come down to draw.
        </p>
      </Step>

      <Step
        n={4}
        title="Mark the paper"
        status={status(3)}
        open={isOpen(3)}
        onToggle={() => toggle(3)}
        summary={paperMarked ? paperSummary(printer) : undefined}
      >
        <MarkPaper props={props} />
      </Step>
    </div>
  );
}

function paperSummary(p: PrinterState) {
  const w = Math.abs(p.paper_bottom_right!.x - p.paper_top_left!.x);
  const h = Math.abs(p.paper_bottom_right!.y - p.paper_top_left!.y);
  return `${w.toFixed(0)} × ${h.toFixed(0)} mm`;
}

function ConnectForm({ props }: { props: PageProps }) {
  const { printer, connection } = props;
  const [form, setForm] = useState({
    ip: connection.ip,
    serial: connection.serial,
    access_code: "",
    model: printer.bed.model,
  });
  const [submitting, setSubmitting] = useState(false);

  function submit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    router.post("/connect", form, {
      preserveScroll: true,
      preserveState: true,
      onFinish: () => setSubmitting(false),
    });
  }

  if (printer.connected) {
    return (
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="text-muted">
          Connected to <span className="font-mono text-ink">{connection.ip}</span>
        </span>
        <Button size="sm" variant="ghost" onClick={() => act("/disconnect")}>
          Disconnect
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <Instruction>
        On the printer, turn on <strong>LAN Only mode</strong> and <strong>Developer mode</strong> (Settings → Network).
        The IP address and access code are shown on the same screen.
      </Instruction>
      <div className="grid grid-cols-2 gap-3">
        <Field label="IP address">
          <input className={inputClass} value={form.ip} onChange={(e) => setForm({ ...form, ip: e.target.value })} placeholder="192.168.1.50" required />
        </Field>
        <Field label="Printer">
          <select className={inputClass} value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })}>
            {Object.entries(props.models).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="Serial number">
        <input className={inputClass} value={form.serial} onChange={(e) => setForm({ ...form, serial: e.target.value })} required />
      </Field>
      <Field label="Access code" hint={connection.has_access_code ? "Leave empty to use the saved one" : undefined}>
        <input
          className={inputClass}
          type="password"
          value={form.access_code}
          onChange={(e) => setForm({ ...form, access_code: e.target.value })}
          placeholder={connection.has_access_code ? "••••••••" : ""}
          required={!connection.has_access_code}
        />
      </Field>
      <Button type="submit" variant="primary" disabled={submitting}>
        {submitting ? "Connecting…" : "Connect"}
      </Button>
    </form>
  );
}

function ZJog({ printer }: { printer: PrinterState }) {
  const disabled = !printer.connected || isBusy(printer);
  const z = (d: number) => act("/jog", { axis: "z", distance: d });
  return (
    <div className="grid grid-cols-2 gap-2">
      <div className="space-y-1.5">
        <span className="text-xs font-medium text-muted">Lower the pen</span>
        <div className="flex gap-1.5">
          <Button size="sm" className="flex-1" onClick={() => z(-5)} disabled={disabled}>
            <ChevronsDown className="size-4" />5
          </Button>
          <Button size="sm" className="flex-1" onClick={() => z(-1)} disabled={disabled}>
            <ChevronDown className="size-4" />1
          </Button>
          <Button size="sm" className="flex-1" onClick={() => z(-0.1)} disabled={disabled}>
            <ChevronDown className="size-4" />0.1
          </Button>
        </div>
      </div>
      <div className="space-y-1.5">
        <span className="text-xs font-medium text-muted">Raise the pen</span>
        <div className="flex gap-1.5">
          <Button size="sm" className="flex-1" onClick={() => z(0.1)} disabled={disabled}>
            <ChevronUp className="size-4" />0.1
          </Button>
          <Button size="sm" className="flex-1" onClick={() => z(1)} disabled={disabled}>
            <ChevronUp className="size-4" />1
          </Button>
          <Button size="sm" className="flex-1" onClick={() => z(5)} disabled={disabled}>
            <ChevronsUp className="size-4" />5
          </Button>
        </div>
      </div>
    </div>
  );
}

export function XYJog({ printer }: { printer: PrinterState }) {
  const [step, setStep] = useState(10);
  const disabled = !printer.connected || !printer.xy_homed || isBusy(printer);
  const jog = (axis: "x" | "y", sign: number) => act("/jog", { axis, distance: sign * step });
  return (
    <div className="flex items-center gap-4">
      <div className="grid grid-cols-3 gap-1">
        <span />
        <Button size="sm" onClick={() => jog("y", 1)} disabled={disabled} aria-label="Move towards the back">
          <ArrowUp className="size-4" />
        </Button>
        <span />
        <Button size="sm" onClick={() => jog("x", -1)} disabled={disabled} aria-label="Move left">
          <ArrowLeft className="size-4" />
        </Button>
        <span className="grid place-items-center text-[10px] text-muted">{step}mm</span>
        <Button size="sm" onClick={() => jog("x", 1)} disabled={disabled} aria-label="Move right">
          <ArrowRight className="size-4" />
        </Button>
        <span />
        <Button size="sm" onClick={() => jog("y", -1)} disabled={disabled} aria-label="Move towards the front">
          <ArrowDown className="size-4" />
        </Button>
        <span />
      </div>
      <div className="space-y-1">
        <span className="block text-xs font-medium text-muted">Step</span>
        <div className="flex overflow-hidden rounded-lg border border-line">
          {[0.5, 1, 10, 50].map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStep(s)}
              className={clsx("px-2.5 py-1 text-xs", s === step ? "bg-accent text-white" : "bg-surface text-ink hover:bg-sunken")}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function MarkPaper({ props }: { props: PageProps }) {
  const { printer } = props;
  const tl = printer.paper_top_left;
  const br = printer.paper_bottom_right;
  const busy = isBusy(printer);
  const goTo = (p: { x: number; y: number }) => act("/move", p);

  return (
    <div className="space-y-3">
      <Instruction>
        The pen stays lifted. Move it so the tip is right above a corner of the paper, using the arrows or by
        clicking the bed picture, then save that corner.
      </Instruction>
      <XYJog printer={printer} />

      <div className="grid grid-cols-2 gap-2">
        <CornerButton label="Top-left" point={tl} onSet={() => act("/paper/corner", { corner: "top_left" })} onGo={goTo} disabled={busy} />
        <CornerButton
          label="Bottom-right"
          point={br}
          onSet={() => act("/paper/corner", { corner: "bottom_right" })}
          onGo={goTo}
          disabled={busy || !tl}
        />
      </div>

      {tl && (
        <div className="space-y-1.5">
          <span className="text-xs font-medium text-muted">…or skip the bottom-right corner and pick the paper size</span>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(props.paper_sizes).map(([name, [w, h]]) => (
              <Button key={name} size="sm" onClick={() => act("/paper/size", { width: w, height: h })}>
                {name}
              </Button>
            ))}
          </div>
        </div>
      )}
      {tl && br && (
        <Button size="sm" variant="ghost" onClick={() => act("/paper/clear")}>
          Start over
        </Button>
      )}
    </div>
  );
}

function CornerButton({
  label,
  point,
  onSet,
  onGo,
  disabled,
}: {
  label: string;
  point: { x: number; y: number } | null;
  onSet: () => void;
  onGo: (p: { x: number; y: number }) => void;
  disabled: boolean;
}) {
  return (
    <div className="rounded-lg border border-line p-2.5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{label}</span>
        {point && <Check className="size-4 text-accent" />}
      </div>
      <div className="mb-2 font-mono text-xs text-muted">{point ? `${point.x.toFixed(1)}, ${point.y.toFixed(1)}` : "not set"}</div>
      <div className="flex gap-1.5">
        <Button size="sm" variant="primary" className="flex-1" onClick={onSet} disabled={disabled}>
          Pen is here
        </Button>
        {point && (
          <Button size="sm" onClick={() => onGo(point)} disabled={disabled} title="Move the pen back to this corner to check it">
            Go
          </Button>
        )}
      </div>
    </div>
  );
}
