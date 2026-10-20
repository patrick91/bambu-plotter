import { router } from "@inertiajs/react";
import { type JSONContent, Mark, mergeAttributes } from "@tiptap/core";
import Bold from "@tiptap/extension-bold";
import Document from "@tiptap/extension-document";
import Italic from "@tiptap/extension-italic";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import TextAlign from "@tiptap/extension-text-align";
import Underline from "@tiptap/extension-underline";
import { Placeholder, UndoRedo } from "@tiptap/extensions";
import { EditorContent, useEditor, useEditorState } from "@tiptap/react";
import clsx from "clsx";
import { AlignCenter, AlignLeft, AlignRight, Bold as BoldIcon, Dices, Italic as ItalicIcon, Underline as UnderlineIcon } from "lucide-react";
import { useEffect } from "react";

import type { Align, Design, Paragraph as Para, Run } from "@/types";

import type { UpdateDesign } from "./design-panel";

// The plotter's fonts are single pen strokes, which browsers can't show, so
// the editor uses lookalikes. The preview on the paper is the real thing.
const FONT_CSS: Record<string, string> = {
  scripts: 'font-family: "Snell Roundhand", "Segoe Script", "Brush Script MT", cursive',
  cursive: 'font-family: "Apple Chancery", "Segoe Script", cursive',
  futural: "font-family: ui-sans-serif, system-ui, sans-serif",
  rowmans: 'font-family: "Gill Sans", "Trebuchet MS", sans-serif',
  timesr: 'font-family: "Times New Roman", Times, serif',
  timesi: 'font-family: "Times New Roman", Times, serif; font-style: italic',
  gothiceng: 'font-family: "Old English Text MT", "UnifrakturMaguntia", serif',
};

// Letter size on screen per mm on paper.
const PX_PER_MM = 3.2;

const SIZES = [2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30];

/** The font and size of a stretch of text, in a single mark so they combine. */
const Lettering = Mark.create({
  name: "lettering",
  addAttributes() {
    return {
      font: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-font"),
        renderHTML: (a) => (a.font ? { "data-font": a.font, style: FONT_CSS[a.font] ?? "" } : {}),
      },
      size: {
        default: null,
        parseHTML: (el) => Number(el.getAttribute("data-size")) || null,
        renderHTML: (a) => (a.size ? { "data-size": a.size, style: `font-size: ${a.size * PX_PER_MM}px` } : {}),
      },
    };
  },
  parseHTML: () => [{ tag: "span[data-font]" }, { tag: "span[data-size]" }],
  renderHTML: ({ HTMLAttributes }) => ["span", mergeAttributes(HTMLAttributes), 0],
});

const run = (r: Partial<Run> & { text: string }): Run => ({
  text: r.text,
  font: r.font ?? null,
  size: r.size ?? null,
  bold: r.bold ?? false,
  italic: r.italic ?? false,
  underline: r.underline ?? false,
});

/** The design's text as paragraphs, whether or not it's been styled yet. */
export function paragraphsOf(design: Design): Para[] {
  if (design.doc) return design.doc.map((p) => ({ align: p.align, runs: p.runs.map(run) }));
  return design.text.split("\n").map((line) => ({ align: design.align, runs: line ? [run({ text: line })] : [] }));
}

function toParagraphs(json: JSONContent): Para[] {
  return (json.content ?? []).map((p) => ({
    align: (p.attrs?.textAlign as Align | undefined) ?? "left",
    runs: (p.content ?? [])
      .filter((n) => n.type === "text" && n.text)
      .map((n) => {
        const has = (type: string) => n.marks?.some((m) => m.type === type) ?? false;
        const lettering = n.marks?.find((m) => m.type === "lettering")?.attrs;
        return run({ text: n.text!, font: lettering?.font, size: lettering?.size, bold: has("bold"), italic: has("italic"), underline: has("underline") });
      }),
  }));
}

function toContent(paragraphs: Para[]): JSONContent {
  return {
    type: "doc",
    content: paragraphs.map((p) => ({
      type: "paragraph",
      attrs: { textAlign: p.align },
      content: p.runs
        .filter((r) => r.text)
        .map((r) => ({
          type: "text",
          text: r.text,
          marks: [
            ...(r.font || r.size ? [{ type: "lettering", attrs: { font: r.font, size: r.size } }] : []),
            ...(r.bold ? [{ type: "bold" }] : []),
            ...(r.italic ? [{ type: "italic" }] : []),
            ...(r.underline ? [{ type: "underline" }] : []),
          ],
        })),
    })),
  };
}

export function TextEditor({ design, update, fonts }: { design: Design; update: UpdateDesign; fonts: Record<string, string> }) {
  const editor = useEditor({
    extensions: [
      Document,
      Paragraph,
      Text,
      Bold,
      Italic,
      Underline,
      Lettering,
      UndoRedo,
      TextAlign.configure({ types: ["paragraph"], alignments: ["left", "center", "right"] }),
      Placeholder.configure({ placeholder: "Write a letter, a poem, a shopping list…" }),
    ],
    content: toContent(paragraphsOf(design)),
    immediatelyRender: true,
    onUpdate: ({ editor }) => {
      const doc = toParagraphs(editor.getJSON());
      update({ doc, text: doc.map((p) => p.runs.map((r) => r.text).join("")).join("\n") });
    },
  });

  // Take in text that changed elsewhere, like a new random poem.
  const incoming = JSON.stringify(paragraphsOf(design));
  useEffect(() => {
    if (JSON.stringify(toParagraphs(editor.getJSON())) !== incoming) {
      editor.commands.setContent(toContent(JSON.parse(incoming)), { emitUpdate: false });
    }
  }, [incoming]);

  const state = useEditorState({
    editor,
    selector: ({ editor }) => ({
      bold: editor.isActive("bold"),
      italic: editor.isActive("italic"),
      underline: editor.isActive("underline"),
      font: (editor.getAttributes("lettering").font as string | null) ?? null,
      size: (editor.getAttributes("lettering").size as number | null) ?? null,
      align: (["center", "right"] as const).find((a) => editor.isActive({ textAlign: a })) ?? "left",
    }),
  });

  const size = state.size ?? design.size;
  const sizes = SIZES.includes(size) ? SIZES : [...SIZES, size].sort((a, b) => a - b);
  const chain = () => editor.chain().focus();

  return (
    <div className="overflow-hidden rounded-lg border border-line bg-surface focus-within:border-accent">
      <div className="flex flex-wrap items-center gap-1 border-b border-line bg-sunken/60 p-1.5">
        <select
          aria-label="Font"
          className="h-8 rounded-md border border-line bg-surface px-1.5 text-sm"
          value={state.font ?? design.font}
          onChange={(e) => chain().setMark("lettering", { font: e.target.value }).run()}
        >
          {Object.entries(fonts).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        <select
          aria-label="Letter size"
          className="h-8 rounded-md border border-line bg-surface px-1.5 text-sm tabular-nums"
          value={size}
          onChange={(e) => chain().setMark("lettering", { size: Number(e.target.value) }).run()}
        >
          {sizes.map((s) => (
            <option key={s} value={s}>
              {s} mm
            </option>
          ))}
        </select>
        <Divider />
        <Tool label="Bold (draws each letter twice)" active={state.bold} onClick={() => chain().toggleBold().run()}>
          <BoldIcon className="size-4" />
        </Tool>
        <Tool label="Italic (slants the letters)" active={state.italic} onClick={() => chain().toggleItalic().run()}>
          <ItalicIcon className="size-4" />
        </Tool>
        <Tool label="Underline" active={state.underline} onClick={() => chain().toggleUnderline().run()}>
          <UnderlineIcon className="size-4" />
        </Tool>
        <Divider />
        {(
          [
            ["left", AlignLeft],
            ["center", AlignCenter],
            ["right", AlignRight],
          ] as const
        ).map(([align, Icon]) => (
          <Tool key={align} label={`Align ${align}`} active={state.align === align} onClick={() => chain().setTextAlign(align).run()}>
            <Icon className="size-4" />
          </Tool>
        ))}
        <button
          type="button"
          onClick={() => router.post("/design/poem", {}, { preserveScroll: true, preserveState: true, only: ["design", "preview", "notice"] })}
          className="ml-auto inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs text-muted hover:bg-surface hover:text-ink"
        >
          <Dices className="size-3.5" /> Random poem
        </button>
      </div>
      <EditorContent
        editor={editor}
        className="max-h-[28rem] min-h-56 overflow-y-auto px-3 py-2.5 [&_.ProseMirror]:min-h-52 [&_.ProseMirror]:outline-none [&_p.is-editor-empty:first-child]:before:pointer-events-none [&_p.is-editor-empty:first-child]:before:float-left [&_p.is-editor-empty:first-child]:before:h-0 [&_p.is-editor-empty:first-child]:before:text-muted [&_p.is-editor-empty:first-child]:before:content-[attr(data-placeholder)]"
        style={{ fontSize: design.size * PX_PER_MM, lineHeight: design.line_spacing, ...cssObject(FONT_CSS[design.font]) }}
      />
    </div>
  );
}

function Tool({ label, active, onClick, children }: { label: string; active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      onMouseDown={(e) => e.preventDefault()} // keep the selection in the editor
      onClick={onClick}
      className={clsx("grid size-8 place-items-center rounded-md", active ? "bg-surface text-accent shadow-sm" : "text-muted hover:bg-surface hover:text-ink")}
    >
      {children}
    </button>
  );
}

const Divider = () => <span className="mx-0.5 h-5 w-px bg-line" />;

/** "font-family: x; font-style: y" as a React style object. */
function cssObject(css = ""): React.CSSProperties {
  return Object.fromEntries(
    css
      .split(";")
      .map((part) => part.split(/:(.*)/s).map((s) => s.trim()))
      .filter(([k, v]) => k && v)
      .map(([k, v]) => [k!.replace(/-(\w)/g, (_, c: string) => c.toUpperCase()), v]),
  );
}
