import { router } from "@inertiajs/react";
import clsx from "clsx";
import type { ButtonHTMLAttributes, ReactNode } from "react";

/** POST an action and refresh only what it can change. */
export function act(url: string, data: Record<string, unknown> = {}, only = ["printer", "notice"]) {
  router.post(url, data as never, { preserveScroll: true, preserveState: true, only });
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
};

export function Button({ variant = "secondary", size = "md", className, ...props }: ButtonProps) {
  return (
    <button
      type="button"
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        {
          primary: "bg-accent text-white hover:bg-accent-strong",
          secondary: "border border-line bg-surface text-ink hover:bg-sunken",
          ghost: "text-muted hover:bg-sunken hover:text-ink",
          danger: "bg-danger text-white hover:opacity-90",
        }[variant],
        { sm: "h-8 px-2.5 text-sm", md: "h-9 px-3.5 text-sm", lg: "h-11 px-5 text-base" }[size],
        className,
      )}
      {...props}
    />
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted/70 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20";

/** A callout telling you what to physically do with the pen or printer. */
export function Instruction({ children, tone = "do" }: { children: ReactNode; tone?: "do" | "warn" }) {
  return (
    <div
      className={clsx(
        "rounded-lg border px-3 py-2.5 text-sm leading-relaxed",
        tone === "do" ? "border-accent/25 bg-accent/5 text-ink" : "border-warn/30 bg-warn/10 text-ink",
      )}
    >
      {children}
    </div>
  );
}

export function formatDuration(seconds: number) {
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))} s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m < 60 ? `${m} min ${s.toString().padStart(2, "0")} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
}
