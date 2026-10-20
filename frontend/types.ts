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
  saved_calibration: { x: number | null; y: number | null; z: number | null; xy_homed: boolean; z_zeroed: boolean } | null;
  z_zeroed: boolean;
  paper_top_left: Point | null;
  paper_bottom_right: Point | null;
  pen_up: number;
  pen_pressure: number;
  draw_speed: number;
  job: Job | null;
};

export type Align = "left" | "center" | "right";

/** A stretch of text in one style. No font or size means the design's own. */
export type Run = { text: string; font: string | null; size: number | null; bold: boolean; italic: boolean; underline: boolean };
export type Paragraph = { align: Align; runs: Run[] };

export type Design = {
  kind: "text" | "image" | "svg";
  text: string;
  doc: Paragraph[] | null;
  font: string;
  size: number;
  line_spacing: number;
  align: Align;
  margin: number;
  fit: boolean;
  image_mode: "outline" | "fill" | "edges" | "spiral" | "circles" | "squiggle" | "crosshatch";
  threshold: number;
  invert: boolean;
  spacing: number;
  gamma: number;
  rotation: number;
  scale: number;
  offset_x: number;
  offset_y: number;
  upload_name: string | null;
};

export type Preview = {
  d: string;
  bounds?: [number, number, number, number] | null;
  width: number;
  height: number;
  strokes: number;
  draw_mm?: number;
  estimated_seconds?: number;
  overflow?: boolean;
  /** How the drawing was put on the paper: turned and scaled around the middle of `box`, then moved. */
  frame?: { box: [number, number, number, number]; scale: number; fit: number; rotation: number; offset: [number, number] } | null;
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
