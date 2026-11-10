import { forwardRef, useCallback } from "react"
import { useEditorState } from "@tiptap/react"

// --- Hooks ---
import { useTiptapEditor } from "@/components/tiptap-hooks/use-tiptap-editor"

// --- Icons ---
import { HighlighterIcon } from "@/components/tiptap-icons/highlighter-icon"

// --- UI Primitives ---
import type { ButtonProps } from "@/components/tiptap-ui-primitive/button"
import { Button } from "@/components/tiptap-ui-primitive/button"

/**
 * Toggles the single highlight colour (TemplateOS keeps one colour: the
 * generated document renders it as a yellow highlight). Replaces the
 * template's multi-colour highlight popover. Shortcut: Ctrl/Cmd+Shift+H.
 */
export const HighlightButton = forwardRef<HTMLButtonElement, Omit<ButtonProps, "type">>(
  ({ onClick, ...buttonProps }, ref) => {
    const { editor } = useTiptapEditor()
    const state = useEditorState({
      editor,
      selector: ({ editor: current }) => ({
        active: current?.isActive("highlight") ?? false,
        can: (current?.isEditable ?? false) && (current?.can().toggleHighlight() ?? false),
      }),
    })
    const active = state?.active ?? false
    const can = state?.can ?? false

    const handleClick = useCallback(
      (event: React.MouseEvent<HTMLButtonElement>) => {
        onClick?.(event)
        if (event.defaultPrevented || !editor) return
        editor.chain().focus().toggleHighlight().run()
      },
      [editor, onClick]
    )

    return (
      <Button
        type="button"
        variant="ghost"
        disabled={!can}
        data-active-state={active ? "on" : "off"}
        data-disabled={!can}
        role="button"
        tabIndex={-1}
        aria-label="Highlight"
        aria-pressed={active}
        tooltip="Highlight"
        onClick={handleClick}
        {...buttonProps}
        ref={ref}
      >
        <HighlighterIcon className="tiptap-button-icon" />
      </Button>
    )
  }
)

HighlightButton.displayName = "HighlightButton"
