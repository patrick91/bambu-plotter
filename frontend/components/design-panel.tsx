import { router } from "@inertiajs/react";
import clsx from "clsx";
import { Dices, ImageUp, Type, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { Design, PageProps } from "@/types";

import { Field, inputClass } from "./ui";

const DESIGN_PROPS = ["design", "preview", "notice"];

export function DesignPanel({ props }: { props: PageProps }) {
  const [design, setDesign] = useState<Design>(props.design);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const fileInput = useRef<HTMLInputElement>(null);

  // Pick up changes made on the server (new poem, upload switching tabs).
  const serverKey = `${props.design.kind}|${props.design.text}|${props.design.upload_name}`;
  useEffect(() => setDesign(props.design), [serverKey]);

  function update(patch: Partial<Design>) {
    const next = { ...design, ...patch };
    setDesign(next);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const { upload_name, ...body } = next;
      router.post("/design", body, { preserveScroll: true, preserveState: true, only: DESIGN_PROPS });
    }, 250);
  }

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
          <div className="relative">
            <textarea
              className={clsx(inputClass, "min-h-56 resize-y font-serif leading-relaxed")}
              value={design.text}
              onChange={(e) => update({ text: e.target.value })}
              placeholder="Write a letter, a poem, a shopping list…"
            />
            <button
              type="button"
              onClick={() => router.post("/design/poem", {}, { preserveScroll: true, preserveState: true, only: DESIGN_PROPS })}
              className="absolute right-2 bottom-3 inline-flex items-center gap-1 rounded-md bg-sunken px-2 py-1 text-xs text-muted hover:text-ink"
            >
              <Dices className="size-3.5" /> Random poem
            </button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Font">
              <select className={inputClass} value={design.font} onChange={(e) => update({ font: e.target.value })}>
                {Object.entries(props.fonts).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Alignment">
              <select className={inputClass} value={design.align} onChange={(e) => update({ align: e.target.value as Design["align"] })}>
                <option value="left">Left</option>
                <option value="center">Centre</option>
                <option value="right">Right</option>
              </select>
            </Field>
            <Range label="Letter size" unit="mm" min={2} max={15} step={0.5} value={design.size} onChange={(size) => update({ size })} />
            <Range label="Line spacing" unit="×" min={1} max={3} step={0.1} value={design.line_spacing} onChange={(line_spacing) => update({ line_spacing })} />
          </div>
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
                <select className={inputClass} value={design.image_mode} onChange={(e) => update({ image_mode: e.target.value as Design["image_mode"] })}>
                  <option value="outline">Outlines of dark areas</option>
                  <option value="fill">Outlines + shading</option>
                  <option value="edges">Edges (for photos)</option>
                </select>
              </Field>
              <Range label="Darkness cut-off" min={10} max={245} step={5} value={design.threshold} onChange={(threshold) => update({ threshold })} />
              {design.image_mode === "fill" && (
                <Range label="Shading lines every" unit="mm" min={0.4} max={3} step={0.1} value={design.spacing} onChange={(spacing) => update({ spacing })} />
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
