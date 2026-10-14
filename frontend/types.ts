export type Point = { x: number; y: number };

export type Job = {
  name: string;
  status: "running" | "stopping" | "done" | "stopped" | "failed";
  progress: number;
  message: string;
  elapsed: number;
  estimated_seconds: number;
};

export type PrinterState = {
  connected: boolean;
  connecting: boolean;
  error: string | null;
  printer_state: string | null;
  bed: { width: number; height: number; model: string };
  head: { x: number | null; y: number | null; z: number | null };
  xy_homed: boolean;
  z_zeroed: boolean;
  paper_top_left: Point | null;
  paper_bottom_right: Point | null;
  pen_up: number;
  pen_pressure: number;
  draw_speed: number;
  job: Job | null;
};

export type Design = {
  kind: "text" | "image" | "svg";
  text: string;
  font: string;
  size: number;
  line_spacing: number;
  align: "left" | "center" | "right";
  margin: number;
  fit: boolean;
  image_mode: "outline" | "fill" | "edges";
  threshold: number;
  invert: boolean;
  spacing: number;
  upload_name: string | null;
};

export type Preview = {
  d: string;
  width: number;
  height: number;
  strokes: number;
  draw_mm?: number;
  estimated_seconds?: number;
  overflow?: boolean;
  error: string | null;
};

export type PageProps = {
  printer: PrinterState;
  connection: { ip: string; serial: string; has_access_code: boolean };
  models: Record<string, string>;
  paper_sizes: Record<string, [number, number]>;
  design: Design;
  preview: Preview;
  fonts: Record<string, string>;
  notice: { kind: "info" | "success" | "warning" | "error"; message: string } | null;
};
