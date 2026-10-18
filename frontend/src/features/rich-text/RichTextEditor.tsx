import { forwardRef } from "react";

import {
  SimpleEditor,
  type SimpleEditorHandle,
  type SimpleEditorProps,
} from "@/components/tiptap-templates/simple/simple-editor";

export type RichTextEditorHandle = SimpleEditorHandle;
export type RichTextEditorProps = SimpleEditorProps;

/**
 * The editor chunk: loaded with React.lazy by RichTextField, so Tiptap and
 * its styles stay out of the main bundle.
 */
const RichTextEditor = forwardRef<RichTextEditorHandle, RichTextEditorProps>(function RichTextEditor(props, ref) {
  return <SimpleEditor {...props} ref={ref} />;
});

export default RichTextEditor;
