import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { ApiError, templatesApi, type TemplateResponse } from "@/lib/api";
import { UploadZone } from "./UploadZone";

const TOKEN_KEY = "templateos_access_token";

const CATEGORY_OPTIONS = [
  { label: "Notice", value: "notice" },
  { label: "Minutes of Meeting", value: "mom" },
  { label: "Report", value: "report" },
  { label: "Application", value: "application" },
  { label: "Letter", value: "letter" },
  { label: "Certificate", value: "certificate" },
  { label: "Proposal", value: "proposal" },
  { label: "Invoice", value: "invoice" },
  { label: "Custom", value: "custom" },
];

const VISIBILITY_OPTIONS = [
  { label: "Private", value: "private" },
  { label: "Public", value: "public" },
  { label: "Organization", value: "organization" },
  { label: "Department", value: "department" },
  { label: "Group", value: "group" },
];

const INPUT_CLASS =
  "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200";

export function UploadTemplateForm() {
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [visibility, setVisibility] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState<TemplateResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const resetForm = () => {
    setName("");
    setDescription("");
    setCategory("");
    setVisibility("");
    setFile(null);
    setError("");
    setSuccess(null);
    setIsSubmitting(false);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");

    // Client-side validation
    if (name.trim().length === 0) {
      setError("Template name is required");
      return;
    }
    if (name.trim().length > 100) {
      setError("Template name must be 100 characters or fewer");
      return;
    }
    if (category === "") {
      setError("Please select a category");
      return;
    }
    if (visibility === "") {
      setError("Please select a visibility");
      return;
    }
    if (file === null) {
      setError("Please select a .docx file to upload");
      return;
    }

    const token = localStorage.getItem(TOKEN_KEY) ?? "";
    setIsSubmitting(true);
    try {
      const result = await templatesApi.upload(token, {
        file,
        name: name.trim(),
        description: description.trim() || undefined,
        category,
        visibility,
      });
      setSuccess(result);
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "Upload failed. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  // ── Success view ──────────────────────────────────────────────────────────
  if (success) {
    return (
      <div className="space-y-4">
        <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">
          ✓ &ldquo;{success.name}&rdquo; uploaded successfully.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button type="button" onClick={resetForm}>
            Upload Another
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/templates")}
          >
            View Templates
          </Button>
        </div>
      </div>
    );
  }

  // ── Form view ─────────────────────────────────────────────────────────────
  return (
    <form className="space-y-5" onSubmit={handleSubmit} noValidate>
      {/* Template Name */}
      <label className="block text-sm font-medium text-slate-700">
        Template Name <span className="text-red-500">*</span>
        <input
          className={INPUT_CLASS}
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Q3 Project Proposal"
          maxLength={100}
        />
      </label>

      {/* Description */}
      <label className="block text-sm font-medium text-slate-700">
        Description{" "}
        <span className="font-normal text-slate-500">(optional)</span>
        <textarea
          className={`${INPUT_CLASS} resize-none`}
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Briefly describe this template…"
        />
      </label>

      {/* Category */}
      <label className="block text-sm font-medium text-slate-700">
        Category <span className="text-red-500">*</span>
        <select
          className={INPUT_CLASS}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="" disabled>
            Select a category
          </option>
          {CATEGORY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>

      {/* Visibility */}
      <label className="block text-sm font-medium text-slate-700">
        Visibility <span className="text-red-500">*</span>
        <select
          className={INPUT_CLASS}
          value={visibility}
          onChange={(e) => setVisibility(e.target.value)}
        >
          <option value="" disabled>
            Select visibility
          </option>
          {VISIBILITY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>

      {/* File Upload */}
      <div>
        <p className="mb-1 text-sm font-medium text-slate-700">
          DOCX File <span className="text-red-500">*</span>
        </p>
        <UploadZone file={file} onChange={setFile} />
      </div>

      {/* Error banner */}
      {error && (
        <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>
      )}

      {/* Submit */}
      <Button className="w-full" type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Uploading…" : "Upload Template"}
      </Button>
    </form>
  );
}
