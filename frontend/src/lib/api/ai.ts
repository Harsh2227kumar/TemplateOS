import { request } from "./client";
import type { ImproveTextRequest, ImproveTextResponse } from "./types";

// Matches the backend cap on original_text (MAX_IMPROVE_TEXT_CHARS).
export const MAX_AI_TEXT_CHARS = 5000;

export const aiApi = {
  /** Pass `signal` to cancel the request (e.g. the form was reset meanwhile). */
  improveText: async (
    token: string,
    payload: ImproveTextRequest,
    signal?: AbortSignal,
  ): Promise<ImproveTextResponse> => {
    return request<ImproveTextResponse>(
      "/ai/improve-text",
      { method: "POST", body: JSON.stringify(payload), signal },
      token,
    );
  },
};
