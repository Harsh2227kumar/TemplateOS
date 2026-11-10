import { useMutation } from "@tanstack/react-query";

import { aiApi, type ImproveTextRequest } from "@/lib/api";

export interface ImproveTextVariables {
  payload: ImproveTextRequest;
  /** Cancels the request, e.g. when the form is reset meanwhile. */
  signal?: AbortSignal;
}

/** Rewrite one field's text in an AI style. Results are not cached here. */
export function useImproveText() {
  return useMutation({
    mutationFn: ({ payload, signal }: ImproveTextVariables) => aiApi.improveText(payload, signal),
  });
}
