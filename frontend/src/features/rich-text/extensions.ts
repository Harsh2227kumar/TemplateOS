import { Extension, type AnyExtension, type Editor } from "@tiptap/core";
import { Highlight } from "@tiptap/extension-highlight";
import { Placeholder } from "@tiptap/extensions";
import { StarterKit } from "@tiptap/starter-kit";

import { allowedHref, MAX_LIST_DEPTH } from "./rich-model";

/** How many lists the selection sits in (0 = not in a list). */
function listDepthAtSelection(editor: Editor): number {
  const { $from } = editor.state.selection;
  let lists = 0;
  for (let depth = $from.depth; depth > 0; depth -= 1) {
    const name = $from.node(depth).type.name;
    if (name === "bulletList" || name === "orderedList") lists += 1;
  }
  return lists;
}

/**
 * Tab does not nest a list item deeper than MAX_LIST_DEPTH (the generated
 * document and the backend allow 3 levels).
 */
const ListDepthLimit = Extension.create({
  name: "listDepthLimit",
  priority: 1000,
  addKeyboardShortcuts() {
    return {
      Tab: ({ editor }) => listDepthAtSelection(editor) >= MAX_LIST_DEPTH,
    };
  },
});

/**
 * The editor schema = the backend whitelist (V1.7-P2 §2): paragraphs, hard
 * breaks, bullet / numbered lists; bold, italic, underline, strike, one
 * highlight colour, http(s) / mailto links; undo / redo. Everything else is
 * switched off, so pasted headings, quotes, code or images keep only their
 * text (and normalizeDoc cleans whatever is left before saving).
 */
export function richTextExtensions(options: { placeholder?: string; editable?: boolean } = {}): AnyExtension[] {
  const extensions: AnyExtension[] = [
    StarterKit.configure({
      heading: false,
      codeBlock: false,
      code: false,
      blockquote: false,
      horizontalRule: false,
      dropcursor: false,
      trailingNode: false,
      link: {
        openOnClick: false,
        enableClickSelection: true,
        autolink: true,
        linkOnPaste: true,
        defaultProtocol: "https",
        protocols: ["http", "https", "mailto"],
        isAllowedUri: (url) => allowedHref(url) !== null,
        shouldAutoLink: (url) => allowedHref(url) !== null || allowedHref(`https://${url}`) !== null,
        HTMLAttributes: { rel: "noopener noreferrer nofollow", target: "_blank" },
      },
    }),
    Highlight.configure({ multicolor: false }),
    ListDepthLimit,
  ];
  if (options.editable !== false && options.placeholder) {
    extensions.push(Placeholder.configure({ placeholder: options.placeholder }));
  }
  return extensions;
}
