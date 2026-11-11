import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  aiFillApi,
  type AiFillMessageCreate,
  type AiFillSessionRead,
  type AiFillTurnResponse,
  type ApiError,
  type FitReport,
} from "@/lib/api";
import { aiFillKeys, documentKeys } from "@/lib/query/keys";

/** GET /system/ai-config: what the UI may offer. */
export function useAiConfig() {
  return useQuery({
    queryKey: aiFillKeys.config(),
    queryFn: () => aiFillApi.config(),
    staleTime: 5 * 60_000,
    retry: false,
  });
}

/** True when the AI fill assistant can be offered. */
export function useAiFillEnabled(): boolean {
  return useAiConfig().data?.fill_enabled === true;
}

/** The chat of a draft (and its fields' length budgets). */
export function useAiFill(documentId: number, enabled = true) {
  return useQuery<AiFillSessionRead, ApiError>({
    queryKey: aiFillKeys.chat(documentId),
    queryFn: () => aiFillApi.get(documentId),
    enabled: enabled && documentId > 0,
    staleTime: Infinity, // changed only by this page: updated from each turn's response
    retry: false,
  });
}

/**
 * Send one message. The chat cache is extended with the turn; document
 * queries are NOT invalidated (the server saved no values).
 */
export function useSendAiFill(documentId: number) {
  const queryClient = useQueryClient();
  return useMutation<AiFillTurnResponse, ApiError, AiFillMessageCreate>({
    mutationFn: (body) => aiFillApi.send(documentId, body),
    onSuccess: (turn) => {
      queryClient.setQueryData<AiFillSessionRead>(aiFillKeys.chat(documentId), (old) => ({
        session: turn.session,
        messages: [...(old?.messages ?? []), turn.user_message, turn.assistant_message],
        open_questions: turn.assistant_message.questions,
        budgets: old?.budgets ?? [],
      }));
    },
  });
}

export function useClearAiFill(documentId: number) {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, void>({
    mutationFn: () => aiFillApi.clear(documentId),
    onSuccess: () => {
      queryClient.setQueryData<AiFillSessionRead>(aiFillKeys.chat(documentId), (old) => ({
        session: null,
        messages: [],
        open_questions: [],
        budgets: old?.budgets ?? [],
      }));
    },
  });
}

/** The fit report of the latest (or a given) version; refetched after generate. */
export function useFitReport(documentId: number, enabled: boolean, version?: number | null) {
  return useQuery<FitReport, ApiError>({
    queryKey: documentKeys.fit(documentId, version),
    queryFn: () => aiFillApi.fitReport(documentId, version),
    enabled: enabled && documentId > 0,
    retry: false,
  });
}
