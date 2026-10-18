/**
 * TemplateOS rich text editor, built from the free (MIT) Tiptap UI "Simple
 * Editor" template (`npx @tiptap/cli@latest add simple-editor`), trimmed to
 * what the generated DOCX can show (V1.7-P2 §2):
 *
 *   undo / redo · bold · italic · underline · strike · highlight · link ·
 *   bullet list · numbered list
 *
 * Removed from the template: headings, image upload, text align, code / code
 * block, blockquote, task list, highlight colours, sub/superscript,
 * horizontal rule, search & replace, theme toggle, typography, and the
 * template's full-page layout and global styles (simple-editor.scss is
 * scoped to .simple-editor-wrapper). No paid Tiptap Cloud features.
 *
 * Controlled by the form: `content` is applied when it differs from what
 * the editor holds (form reset, AI rewrite, restore); every user change is
 * reported through onChange as whitelist-normalized JSON.
 */
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react"
import { EditorContent, EditorContext, useEditor } from "@tiptap/react"

// --- UI Primitives ---
import { Toolbar, ToolbarGroup, ToolbarSeparator } from "@/components/tiptap-ui-primitive/toolbar"

// --- Tiptap Node styles ---
import "@/components/tiptap-node/list-node/list-node.scss"
import "@/components/tiptap-node/paragraph-node/paragraph-node.scss"

// --- Tiptap UI ---
import { HighlightButton } from "@/components/tiptap-ui/highlight-button"
import { LinkPopover } from "@/components/tiptap-ui/link-popover"
import { ListButton } from "@/components/tiptap-ui/list-button"
import { MarkButton } from "@/components/tiptap-ui/mark-button"
import { UndoRedoButton } from "@/components/tiptap-ui/undo-redo-button"

// --- Styles ---
import "@/components/tiptap-templates/simple/tiptap-theme"
import "@/components/tiptap-templates/simple/simple-editor.scss"

import { richTextExtensions } from "@/features/rich-text/extensions"
import { docToPlain, normalizeDoc, sameDoc, type RichDoc } from "@/features/rich-text/rich-model"

export interface SimpleEditorProps {
  content: RichDoc
  onChange: (doc: RichDoc) => void
  onBlur?: () => void
  /** id of the editable element (labels, deep links and error focus target it). */
  id?: string
  ariaLabelledBy?: string
  ariaDescribedBy?: string
  ariaRequired?: boolean
  invalid?: boolean
  /** Read-only, e.g. while the form saves or an AI request runs. */
  disabled?: boolean
  placeholder?: string
  /** Toolbar label for screen readers. */
  toolbarLabel?: string
}

export interface SimpleEditorHandle {
  focus: () => void
}

export const SimpleEditor = forwardRef<SimpleEditorHandle, SimpleEditorProps>(function SimpleEditor(
  {
    content,
    onChange,
    onBlur,
    id,
    ariaLabelledBy,
    ariaDescribedBy,
    ariaRequired,
    invalid,
    disabled = false,
    placeholder,
    toolbarLabel = "Text formatting",
  },
  ref,
) {
  const linkButtonRef = useRef<HTMLButtonElement>(null)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange
  const onBlurRef = useRef(onBlur)
  onBlurRef.current = onBlur

  const editor = useEditor({
    immediatelyRender: true,
    editable: !disabled,
    extensions: richTextExtensions({ placeholder }),
    content,
    editorProps: {
      attributes: {
        ...(id ? { id } : {}),
        role: "textbox",
        "aria-multiline": "true",
        ...(ariaLabelledBy ? { "aria-labelledby": ariaLabelledBy } : {}),
        ...(ariaDescribedBy ? { "aria-describedby": ariaDescribedBy } : {}),
        ...(ariaRequired ? { "aria-required": "true" } : {}),
        "aria-invalid": invalid ? "true" : "false",
        class: "simple-editor",
        spellcheck: "true",
      },
      handleKeyDown: (_view, event) => {
        // Ctrl/Cmd+K opens the link popover (after this keystroke is done,
        // so the popover's focus handling does not see it and close again).
        if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === "k") {
          event.preventDefault()
          window.setTimeout(() => linkButtonRef.current?.click(), 0)
          return true
        }
        return false
      },
    },
    onUpdate: ({ editor: current }) => {
      const raw = current.getJSON()
      const doc = normalizeDoc(raw)
      // The editor accepts some structure the document cannot show (lists
      // nested deeper than 3 levels, e.g. after a paste): show the text the
      // way it will be saved.
      if (docToPlain(raw as RichDoc) !== docToPlain(doc)) {
        current.commands.setContent(doc, { emitUpdate: false })
      }
      onChangeRef.current(doc)
    },
    onBlur: () => onBlurRef.current?.(),
  })

  useImperativeHandle(ref, () => ({ focus: () => void editor?.commands.focus() }), [editor])

  // Outside changes (reset, AI, restore) replace the content; the editor's
  // own updates come back equal and are left alone (no cursor jump).
  useEffect(() => {
    if (!editor || editor.isDestroyed) return
    if (!sameDoc(editor.getJSON(), content)) {
      editor.commands.setContent(content, { emitUpdate: false })
    }
  }, [editor, content])

  useEffect(() => {
    if (editor && !editor.isDestroyed && editor.isEditable === disabled) editor.setEditable(!disabled, false)
  }, [editor, disabled])

  // aria-invalid / aria-describedby follow the form state.
  useEffect(() => {
    if (!editor || editor.isDestroyed) return
    const attributes = { ...(editor.options.editorProps.attributes as Record<string, string>) }
    attributes["aria-invalid"] = invalid ? "true" : "false"
    if (ariaDescribedBy) attributes["aria-describedby"] = ariaDescribedBy
    else delete attributes["aria-describedby"]
    editor.setOptions({ editorProps: { ...editor.options.editorProps, attributes } })
  }, [editor, invalid, ariaDescribedBy])

  return (
    <div className="simple-editor-wrapper" data-invalid={invalid || undefined} data-disabled={disabled || undefined}>
      <EditorContext.Provider value={{ editor }}>
        <Toolbar aria-label={toolbarLabel} aria-controls={id}>
          <ToolbarGroup>
            <UndoRedoButton action="undo" />
            <UndoRedoButton action="redo" />
          </ToolbarGroup>

          <ToolbarSeparator />

          <ToolbarGroup>
            <MarkButton type="bold" />
            <MarkButton type="italic" />
            <MarkButton type="underline" />
            <MarkButton type="strike" />
            <HighlightButton />
            <LinkPopover ref={linkButtonRef} autoOpenOnLinkActive={false} />
          </ToolbarGroup>

          <ToolbarSeparator />

          <ToolbarGroup>
            <ListButton type="bulletList" />
            <ListButton type="orderedList" />
          </ToolbarGroup>
        </Toolbar>

        <EditorContent editor={editor} className="simple-editor-content" />
      </EditorContext.Provider>
    </div>
  )
})
