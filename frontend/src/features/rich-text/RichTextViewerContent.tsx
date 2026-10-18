import { useEffect } from "react";
import { EditorContent, useEditor } from "@tiptap/react";

import "@/components/tiptap-templates/simple/tiptap-theme";
import "@/components/tiptap-node/list-node/list-node.scss";
import "@/components/tiptap-node/paragraph-node/paragraph-node.scss";
import "@/components/tiptap-templates/simple/simple-editor.scss";

import { richTextExtensions } from "./extensions";
import { normalizeDoc, sameDoc, type RichDoc } from "./rich-model";

/**
 * Read-only rendering of a rich value with the editor's own schema (lazy
 * chunk). ProseMirror builds the DOM from the JSON: no HTML strings, no
 * dangerouslySetInnerHTML.
 */
export default function RichTextViewerContent({ doc, label }: { doc: RichDoc; label?: string }) {
  const editor = useEditor({
    immediatelyRender: true,
    editable: false,
    extensions: richTextExtensions({ editable: false }),
    content: normalizeDoc(doc),
    editorProps: {
      attributes: {
        role: "document",
        ...(label ? { "aria-label": label } : {}),
        class: "rich-text-viewer-content",
      },
      // Links open in a new tab from the read-only view.
      handleClickOn: (_view, _pos, _node, _nodePos, event) => {
        const anchor = (event.target as HTMLElement | null)?.closest("a");
        if (anchor?.href) {
          window.open(anchor.href, "_blank", "noopener,noreferrer");
          return true;
        }
        return false;
      },
    },
  });

  useEffect(() => {
    if (editor && !editor.isDestroyed && !sameDoc(editor.getJSON(), doc)) {
      editor.commands.setContent(normalizeDoc(doc), { emitUpdate: false });
    }
  }, [editor, doc]);

  return (
    <div className="rich-text-viewer">
      <EditorContent editor={editor} />
    </div>
  );
}
