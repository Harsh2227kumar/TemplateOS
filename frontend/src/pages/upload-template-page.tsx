import { UploadTemplateForm } from "@/components/upload/UploadTemplateForm";

export function UploadTemplatePage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <p className="text-sm font-medium uppercase tracking-wider text-slate-500">
          V1.2 Template Library
        </p>
        <h1 className="mt-2 text-2xl font-semibold">Upload Template</h1>
        <p className="mt-2 text-sm text-slate-600">
          Upload a DOCX file to create a reusable template.
        </p>
      </div>
      <UploadTemplateForm />
    </div>
  );
}
