// Barrel: `import { ... } from "@/lib/api"` keeps working after the split.
export * from "./types";
export { API_BASE_URL, ApiError, type FileDownload } from "./client";
export { authApi } from "./auth";
export {
  templateAccessApi,
  templateCatalogApi,
  templatesApi,
  type TemplateLibraryParams,
  type TemplateUploadPayload,
} from "./templates";
export { templatePipelineApi } from "./template-pipeline";
export { documentsApi } from "./documents";
export { splitValidationErrors } from "./validation-errors";
export { aiApi, MAX_AI_TEXT_CHARS } from "./ai";
export { SESSION_EXPIRED_EVENT, clearLegacyAccessToken } from "./session";
