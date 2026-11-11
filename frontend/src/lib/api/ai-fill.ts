import { request } from "./client";
import type { AiConfig, AiFillMessageCreate, AiFillSessionRead, AiFillTurnResponse, FitReport } from "./types";

// Matches the backend default (AI_FILL_MAX_MESSAGE_CHARS).
export const MAX_AI_FILL_MESSAGE_CHARS = 8000;

/** V1.7 P2.2: the AI fill assistant of a draft, and the fit check of a version. */
export const aiFillApi = {
  /** Which AI features the UI may offer. */
  config: async (): Promise<AiConfig> => {
    return request<AiConfig>("/system/ai-config");
  },

  /** The stored chat, the questions that can still be answered, and each field's length budget. */
  get: async (documentId: number): Promise<AiFillSessionRead> => {
    return request<AiFillSessionRead>(`/documents/${documentId}/ai-fill`);
  },

  /**
   * One chat turn. The reply holds PROPOSALS: the page puts them into the
   * form and the user saves. 503 = AI unavailable (nothing was stored, keep
   * the typed text); 409 code "turn_limit" = clear the chat to go on.
   */
  send: async (documentId: number, body: AiFillMessageCreate): Promise<AiFillTurnResponse> => {
    return request<AiFillTurnResponse>(`/documents/${documentId}/ai-fill/messages`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** Deletes the chat. The form's values are not touched. */
  clear: async (documentId: number): Promise<void> => {
    return request<void>(`/documents/${documentId}/ai-fill`, { method: "DELETE" });
  },

  /** Pages against the template's baseline and fields over their budget. 404 before the first generate. */
  fitReport: async (documentId: number, version?: number | null): Promise<FitReport> => {
    return request<FitReport>(`/documents/${documentId}/fit-report${version ? `?version=${version}` : ""}`);
  },
};
