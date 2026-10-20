import { router } from "@inertiajs/react";
import clsx from "clsx";
import { ImageUp, RotateCcw, RotateCw, Type, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { Design, PageProps } from "@/types";

import { TextEditor } from "./text-editor";
import { Field, inputClass } from "./ui";

const DESIGN_PROPS = ["design", "preview", "notice"];

export type UpdateDesign = (patch: Partial<Design>) => void;

/** The drawing being edited, shared by the side panel and the bed view. */
export function useDesign(server: Design): [Design, UpdateDesign] {
  const [design, setDesign] = useState<Design>(server);
  const latest = useRef(design);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const sent = useRef<Design | null>(null);

  // Pick up changes made on the server (new poem, upload switching tabs), but
  // not the server echoing back what we sent: there may be newer typing since.
  const serverKey = `${server.kind}|${server.text}|${JSON.stringify(server.doc)}|${server.upload_name}`;
  useEffect(() => {
    const echo = sent.current && server.kind === sent.current.kind && server.text === sent.current.text && JSON.stringify(server.doc) === JSON.stringify(sent.current.doc) && server.upload_name === latest.current.upload_name;
    if (echo) return;
    latest.current = server;
    setDesign(server);
  }, [serverKey]);

  function update(patch: Partial<Design>) {
    const next = { ...latest.current, ...patch };
    latest.current = next;
    setDesign(next);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      sent.current = latest.current;
      const { upload_name, ...body } = latest.current;
      router.post("/design", body, { preserveScroll: true, preserveState: true, only: DESIGN_PROPS });
    }, 250);
  }

  return [design, update];
}

const TONAL = ["spiral", "circles", "squiggle", "crosshatch"];

export function DesignPanel({ props, design, update }: { props: PageProps; design: Design; update: UpdateDesign }) {
  const fileInput = useRef<HTMLInputElement>(null);

  function upload(file: File) {
    router.post("/design/upload", { file }, { forceFormData: true, preserveScroll: true, preserveState: true, only: DESIGN_PROPS });
  }

  const tabs = [
    { kind: "text", label: "Write", icon: Type },
    { kind: "image", label: "Image", icon: ImageUp },
    { kind: "svg", label: "SVG", icon: Upload },
  ] as const;

  return (
    <div className="space-y-4">
      <div className="flex rounded-lg bg-sunken p-1">
        {tabs.map(({ kind, label, icon: Icon }) => (
          <button
            key={kind}
            type="button"
            onClick={() => update({ kind })}
            className={clsx(
              "flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-sm font-medium transition-colors",
              design.kind === kind ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink",
            )}
          >
            <Icon className="size-4" /> {label}
          </button>
        ))}
      </div>

      {design.kind === "text" ? (
        <div className="space-y-3">
          <TextEditor design={design} update={update} fonts={props.fonts} />
          <p className="text-xs text-muted">
            Select words to change their font and size. The editor uses lookalike fonts; the paper on the right shows exactly what
            the pen will draw.
          </p>
          <Range label="Line spacing" unit="×" min={1} max={3} step={0.1} value={design.line_spacing} onChange={(line_spacing) => update({ line_spacing })} />
        </div>
      ) : (
        <div className="space-y-3">
          <input
            ref={fileInput}
            type="file"
            className="hidden"
            accept={design.kind === "svg" ? ".svg,image/svg+xml" : "image/png,image/jpeg,image/webp,image/gif,image/bmp"}
            onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
          />
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const file = e.dataTransfer.files[0];
              if (file) upload(file);
            }}
            className="flex w-full flex-col items-center gap-1 rounded-xl border-2 border-dashed border-line px-4 py-6 text-sm text-muted hover:border-accent/50 hover:text-ink"
          >
            <Upload className="size-5" />
            {props.design.upload_name && props.design.kind === design.kind ? (
              <span>
                <span className="font-medium text-ink">{props.design.upload_name}</span> · click or drop to replace
              </span>
            ) : (
              <span>Drop {design.kind === "svg" ? "an SVG" : "a PNG or JPEG"} here, or click to choose</span>
            )}
          </button>

          {design.kind === "image" && (
            <div className="grid grid-cols-2 gap-3">
              <Field label="Draw">
                <select
                  className={inputClass}
                  value={design.image_mode}
                  onChange={(e) => {
                    const image_mode = e.target.value as Design["image_mode"];
                    // Shading styles look best with wider line spacing than hatching.
                    const spacing = TONAL.includes(image_mode) && !TONAL.includes(design.image_mode) ? 1.2 : design.spacing;
                    update({ image_mode, spacing });
                  }}
                >
                  <optgroup label="Shading (best for photos)">
                    <option value="spiral">Spiral</option>
                    <option value="circles">Circles</option>
                    <option value="squiggle">Squiggle lines</option>
                    <option value="crosshatch">Crosshatching</option>
                  </optgroup>
                  <optgroup label="Tracing (best for logos and drawings)">
                    <option value="outline">Outlines of dark areas</option>
                    <option value="fill">Outlines + fill</option>
                    <option value="edges">Edges</option>
                  </optgroup>
                </select>
              </Field>
              {TONAL.includes(design.image_mode) ? (
                <Range label="Lighten" unit="×" min={0.5} max={3} step={0.1} value={design.gamma} onChange={(gamma) => update({ gamma })} />
              ) : (
                <Range label="Darkness cut-off" min={10} max={245} step={5} value={design.threshold} onChange={(threshold) => update({ threshold })} />
              )}
              {(design.image_mode === "fill" || TONAL.includes(design.image_mode)) && (
                <Range
                  label={TONAL.includes(design.image_mode) ? "Lines every" : "Fill lines every"}
                  unit="mm"
                  min={0.4}
                  max={4}
                  step={0.1}
                  value={design.spacing}
                  onChange={(spacing) => update({ spacing })}
                />
              )}
              <label className="col-span-2 flex items-center gap-2 text-sm">
                <input type="checkbox" checked={design.invert} onChange={(e) => update({ invert: e.target.checked })} />
                Swap light and dark (for light drawings on a dark background)
              </label>
            </div>
          )}
          {design.kind === "svg" && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={design.fit} onChange={(e) => update({ fit: e.target.checked })} />
              Scale to fill the paper (otherwise keep the SVG's own size)
            </label>
          )}
        </div>
      )}

      <Range label="Margin" unit="mm" min={0} max={30} step={1} value={design.margin} onChange={(margin) => update({ margin })} />

      <div className="space-y-3 border-t border-line pt-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold tracking-wider text-muted uppercase">Position</span>
          <button
            type="button"
            className="text-xs text-muted hover:text-ink disabled:opacity-40"
            disabled={!design.rotation && design.scale === 100 && !design.offset_x && !design.offset_y}
            onClick={() => update({ rotation: 0, scale: 100, offset_x: 0, offset_y: 0 })}
          >
            Reset
          </button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Range label="Size" unit="%" min={10} max={300} step={5} value={design.scale} onChange={(scale) => update({ scale })} />
          <div>
            <Range label="Rotation" unit="°" min={-180} max={180} step={1} value={design.rotation} onChange={(rotation) => update({ rotation })} />
            <div className="mt-1 flex gap-1">
              <button type="button" className="rounded-md bg-sunken px-2 py-0.5 text-xs text-muted hover:text-ink" onClick={() => update({ rotation: wrap(design.rotation - 90) })}>
                <RotateCcw className="inline size-3" /> 90°
              </button>
              <button type="button" className="rounded-md bg-sunken px-2 py-0.5 text-xs text-muted hover:text-ink" onClick={() => update({ rotation: wrap(design.rotation + 90) })}>
                <RotateCw className="inline size-3" /> 90°
              </button>
            </div>
          </div>
        </div>
        <p className="text-xs text-muted">Drag the drawing on the bed picture to move it around the paper.</p>
      </div>
    </div>
  );
}

function Range({
  label,
  unit = "",
  min,
  max,
  step,
  value,
  onChange,
}: {
  label: string;
  unit?: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1 flex justify-between text-xs font-medium text-muted">
        <span>{label}</span>
        <span className="font-mono tabular-nums text-ink">
          {value}
          {unit && ` ${unit}`}
        </span>
      </span>
      <input
        type="range"
        className="w-full accent-[var(--color-accent)]"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}

/** Keep angles in -180..180, so the slider can show them. */
const wrap = (deg: number) => ((((deg + 180) % 360) + 360) % 360) - 180;
