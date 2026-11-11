import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useWatch, type UseFormReturn } from "react-hook-form";
import { AlertCircle, CheckCircle2, Loader2, Send, Sparkles, Trash2, X } from "lucide-react";

import { AI_FLAGS_KEY } from "@/components/forms/ai-flags";
import { countRequiredFilled } from "@/components/forms/form-values";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { useAiFill, useClearAiFill, useSendAiFill } from "@/hooks/queries";
import {
  ApiError,
  MAX_AI_FILL_MESSAGE_CHARS,
  type AiFillMessage,
  type AiFillProposal,
  type AiFillQuestion,
  type DocumentFormValues,
  type TemplateField,
} from "@/lib/api";
import { cn } from "@/lib/utils";

import type { AiFillAssistant } from "./ai-fill-context";
import {
  applyFillProposals,
  buildFormState,
  canSend,
  examplePrompts,
  nextSendBody,
  progressText,
  stageLabel,
  summarizeTurn,
  summaryText,
  turnLimitMessage,
} from "./fill-model";

interface AiAssistantPanelProps {
  documentId: number;
  fields: TemplateField[];
  form: UseFormReturn<DocumentFormValues>;
  assistant: AiFillAssistant;
  /** The form is saving or generating: no new turn meanwhile. */
  disabled: boolean;
  /** Jump to a field of the form (switches to the form on small screens). */
  onShowField: (fieldName: string) => void;
  /** Save the draft (same as the form's own button). */
  onSave: () => void;
  onClose: () => void;
}

const KIND_HINTS: Partial<Record<AiFillQuestion["kind"], string>> = {
  conflict: "You gave two different answers",
  more_detail: "A little more detail helps",
};

/**
 * V1.7 P2.2: the AI fill assistant chat beside the draft form. The user
 * writes what they know; each reply is put into the form as PROPOSALS
 * (unsaved, never over a field the user wrote) and may ask up to three
 * questions. Saving stays the user's step.
 */
export default function AiAssistantPanel({
  documentId,
  fields,
  form,
  assistant,
  disabled,
  onShowField,
  onSave,
  onClose,
}: AiAssistantPanelProps) {
  const chat = useAiFill(documentId);
  const sendMessage = useSendAiFill(documentId);
  const clearChat = useClearAiFill(documentId);

  const [text, setText] = useState("");
  // question id -> the clicked choice
  const [marked, setMarked] = useState<Record<string, string>>({});
  const [skipped, setSkipped] = useState<ReadonlySet<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  // Required fields the AI stopped asking about, and fields it left alone
  // because the user wrote them (both from the latest turn of this visit).
  const [needsUser, setNeedsUser] = useState<string[]>([]);
  const [leftAlone, setLeftAlone] = useState<string[]>([]);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const messages = useMemo(() => chat.data?.messages ?? [], [chat.data?.messages]);
  const openQuestions = useMemo(
    () => (chat.data?.open_questions ?? []).filter((question) => !skipped.has(question.id)),
    [chat.data?.open_questions, skipped],
  );
  const latestAssistant = useMemo(() => [...messages].reverse().find((m) => m.role === "assistant") ?? null, [messages]);
  const session = chat.data?.session ?? null;
  const pending = sendMessage.isPending;

  const values = useWatch({ control: form.control });
  const required = countRequiredFilled(fields, values as DocumentFormValues);
  const stage = latestAssistant?.stage ?? null;
  const labelOf = (name: string) => fields.find((f) => f.field_name === name)?.field_label?.trim() || name;

  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages.length, pending, openQuestions.length]);

  /** Put a turn's proposals into the form (unsaved); locked fields are left alone. */
  const applyProposals = (proposals: AiFillProposal[], announce: boolean) => {
    const current = form.getValues();
    const result = applyFillProposals(fields, current, proposals, assistant.unlocked);
    for (const name of result.applied) {
      form.setValue(name, result.values[name] as DocumentFormValues[string], { shouldDirty: true, shouldValidate: true });
    }
    if (result.applied.length > 0) {
      form.setValue(AI_FLAGS_KEY, result.values[AI_FLAGS_KEY] as DocumentFormValues[string], { shouldDirty: true });
    }
    assistant.recordApplied(
      result.applied.map((name) => ({
        name,
        proposal: proposals.find((p) => p.field_name === name) as AiFillProposal,
        previous: result.previous[name],
      })),
    );
    assistant.clearUnlocked();
    setLeftAlone(result.skippedLocked);
    if (announce && result.applied.length > 0) {
      toast({
        title: result.applied.length === 1 ? "1 field filled" : `${result.applied.length} fields filled`,
        description: "Review them, then save the draft.",
        duration: 3500,
      });
    }
    return result;
  };

  const send = async () => {
    if (pending || disabled || !canSend(text, openQuestions, marked, skipped)) return;
    setError(null);
    const body = nextSendBody(
      text,
      // Skipped questions are sent so the AI stops asking about them.
      chat.data?.open_questions ?? [],
      marked,
      skipped,
      buildFormState(fields, form.getValues(), assistant.unlocked),
    );
    try {
      const turn = await sendMessage.mutateAsync(body);
      setText("");
      setMarked({});
      setSkipped(new Set());
      setNeedsUser(turn.needs_user);
      applyProposals(turn.assistant_message.proposals, true);
    } catch (err) {
      const limit = turnLimitMessage(err);
      if (limit) setError(limit);
      else if (err instanceof ApiError && err.status === 503) {
        setError("The AI is unavailable right now. Your message is still here; you can also keep filling the form yourself.");
      } else {
        setError(err instanceof Error && err.message ? err.message : "The message could not be sent. Please try again.");
      }
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
    }
  };

  const skip = (question: AiFillQuestion) => {
    setSkipped((current) => new Set(current).add(question.id));
    setMarked((current) => {
      const next = { ...current };
      delete next[question.id];
      return next;
    });
    if (question.field_names[0]) onShowField(question.field_names[0]);
  };

  const clear = async () => {
    if (!window.confirm("Clear this chat? The values in the form stay as they are.")) return;
    try {
      await clearChat.mutateAsync();
      assistant.reset();
      setNeedsUser([]);
      setLeftAlone([]);
      setMarked({});
      setSkipped(new Set());
      setError(null);
    } catch (err) {
      toast({ variant: "destructive", title: "Could not clear the chat", description: err instanceof Error ? err.message : undefined });
    }
  };

  const nearLimit = text.length > MAX_AI_FILL_MESSAGE_CHARS * 0.9;
  const tooLong = text.length > MAX_AI_FILL_MESSAGE_CHARS;
  const sendable = !pending && !disabled && !tooLong && canSend(text, openQuestions, marked, skipped);
  const progressPercent = required.total ? Math.round((required.filled / required.total) * 100) : 100;

  return (
    <section
      aria-label="AI fill assistant"
      className="flex max-h-[calc(100vh-7rem)] min-h-[28rem] flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm"
    >
      <header className="border-b border-slate-100 px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <Sparkles className="h-4 w-4 text-violet-600" aria-hidden="true" />
            AI assistant
          </h2>
          <div className="flex items-center gap-1">
            {session && (
              <button
                type="button"
                onClick={() => void clear()}
                disabled={clearChat.isPending || pending}
                className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs text-slate-500 hover:bg-slate-100 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:opacity-50"
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                Clear chat
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              aria-label="Close the assistant"
              className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </div>
        <div className="mt-2 space-y-1" role="status">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className={cn("font-medium", stage === "ready" ? "text-emerald-700" : "text-slate-700")}>{stageLabel(stage)}</span>
            <span className="text-slate-500">{progressText(required.filled, required.total)}</span>
          </div>
          <div className="h-1 w-full overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
            <div
              className={cn("h-full rounded-full transition-all", stage === "ready" ? "bg-emerald-500" : "bg-violet-500")}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      </header>

      <div ref={listRef} role="log" aria-live="polite" aria-label="Conversation" className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {chat.isLoading && (
          <p className="flex items-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Loading the chat…
          </p>
        )}
        {chat.isError && (
          <p className="text-sm text-red-700" role="alert">
            {chat.error?.message || "The chat could not be loaded."}{" "}
            <button type="button" className="underline" onClick={() => void chat.refetch()}>
              Try again
            </button>
          </p>
        )}

        {chat.isSuccess && messages.length === 0 && !pending && (
          <div className="space-y-3 text-sm text-slate-600">
            <p>
              Write (or paste) everything you know about this document, in your own words. Spelling and grammar do not
              matter. I fill the form, fix the language and ask about anything that is missing or unclear.
            </p>
            <div className="flex flex-col items-start gap-1.5">
              {examplePrompts(fields).map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => {
                    setText(prompt);
                    inputRef.current?.focus();
                  }}
                  className="rounded-full border border-slate-200 px-3 py-1 text-left text-xs text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            isLatestAssistant={message.id === latestAssistant?.id}
            labelOf={labelOf}
            onShowField={onShowField}
            onApplyAgain={pending || disabled ? undefined : () => applyProposals(message.proposals, true)}
          />
        ))}

        {leftAlone.length > 0 && (
          <p className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
            You edited {leftAlone.map(labelOf).join(", ")}, so I left {leftAlone.length === 1 ? "it" : "them"} as{" "}
            {leftAlone.length === 1 ? "it is" : "they are"}. Use “Let AI update” under a field to let me change it.
          </p>
        )}

        {needsUser.length > 0 && (
          <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
            <p className="font-medium">Please fill these yourself:</p>
            <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
              {needsUser.map((name) => (
                <li key={name}>
                  <button type="button" className="text-violet-700 underline underline-offset-2" onClick={() => onShowField(name)}>
                    {labelOf(name)}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {!pending &&
          openQuestions.map((question) => (
            <QuestionCard
              key={question.id}
              question={question}
              choice={marked[question.id]}
              disabled={disabled}
              onChoose={(choice) =>
                setMarked((current) => {
                  const next = { ...current };
                  if (next[question.id] === choice) delete next[question.id];
                  else next[question.id] = choice;
                  return next;
                })
              }
              onSkip={() => skip(question)}
            />
          ))}

        {stage === "ready" && !pending && openQuestions.length === 0 && (
          <div className="flex flex-col gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
            <p className="flex items-start gap-1.5">
              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" aria-hidden="true" />
              I have everything I need. Check the highlighted fields, then save and generate.
            </p>
            {form.formState.isDirty && (
              <Button type="button" size="sm" variant="outline" onClick={onSave} disabled={disabled} className="self-start">
                Save the draft
              </Button>
            )}
          </div>
        )}

        {pending && (
          <p className="flex items-center gap-2 text-sm text-slate-500" role="status">
            <Loader2 className="h-4 w-4 animate-spin text-violet-600" aria-hidden="true" />
            Reading your details… this can take a few seconds.
          </p>
        )}
      </div>

      <footer className="space-y-2 border-t border-slate-100 px-4 py-3">
        {error && (
          <p className="flex items-start gap-1.5 text-xs text-red-700" role="alert">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {error}
          </p>
        )}
        <div className="flex items-end gap-2">
          <label htmlFor="ai-fill-message" className="sr-only">
            Message to the AI assistant
          </label>
          <Textarea
            id="ai-fill-message"
            ref={inputRef}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            rows={3}
            placeholder={
              openQuestions.length > 0 ? "Answer here, or pick a choice above…" : "Tell me about your document…"
            }
            disabled={disabled}
            aria-invalid={tooLong}
            className="max-h-48 min-h-[4.5rem] resize-y text-sm"
          />
          <Button type="button" size="icon" onClick={() => void send()} disabled={!sendable} aria-label="Send">
            {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
        <div className="flex items-start justify-between gap-3 text-[11px] leading-snug text-slate-400">
          <p>
            Enter sends, Shift+Enter starts a new line. Your text is sent to our AI provider (AWS Bedrock) to fill this
            form and is saved with this draft; you can clear it.
          </p>
          {nearLimit && (
            <span className={cn("shrink-0 tabular-nums", tooLong ? "font-medium text-red-600" : "text-slate-500")}>
              {text.length.toLocaleString()} / {MAX_AI_FILL_MESSAGE_CHARS.toLocaleString()}
            </span>
          )}
        </div>
      </footer>
    </section>
  );
}

function MessageBubble({
  message,
  isLatestAssistant,
  labelOf,
  onShowField,
  onApplyAgain,
}: {
  message: AiFillMessage;
  isLatestAssistant: boolean;
  labelOf: (name: string) => string;
  onShowField: (name: string) => void;
  onApplyAgain?: () => void;
}) {
  if (message.role === "user") {
    const choices = message.answers.map((answer) => answer.choice).filter((choice): choice is string => Boolean(choice));
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] space-y-1 rounded-2xl rounded-br-sm bg-slate-800 px-3 py-2 text-sm text-white">
          {choices.map((choice) => (
            <p key={choice} className="text-xs text-slate-300">
              Chose: {choice}
            </p>
          ))}
          {message.content && <p className="whitespace-pre-wrap break-words">{message.content}</p>}
        </div>
      </div>
    );
  }

  const kept = message.proposals.filter((proposal) => proposal.confidence !== "low");
  const summary = summaryText(summarizeTurn(message));
  return (
    <div className="flex justify-start">
      <div className="max-w-[92%] space-y-2 rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800">
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
        {summary && <p className="text-xs font-medium text-violet-700">{summary}</p>}
        {kept.length > 0 && (
          <details className="text-xs text-slate-600">
            <summary className="cursor-pointer select-none hover:underline">Fields I filled</summary>
            <ul className="mt-1 space-y-0.5">
              {kept.map((proposal) => (
                <li key={proposal.field_name} className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => onShowField(proposal.field_name)}
                    className="shrink-0 text-violet-700 underline underline-offset-2"
                  >
                    {labelOf(proposal.field_name)}
                  </button>
                  <span className="min-w-0 truncate text-slate-500">
                    {proposal.items ? proposal.items.join(", ") : proposal.value}
                    {proposal.confidence === "medium" ? " (check)" : ""}
                  </span>
                </li>
              ))}
            </ul>
            {isLatestAssistant && onApplyAgain && (
              <button type="button" onClick={onApplyAgain} className="mt-1 text-violet-700 underline underline-offset-2">
                Apply these suggestions again
              </button>
            )}
          </details>
        )}
      </div>
    </div>
  );
}

function QuestionCard({
  question,
  choice,
  disabled,
  onChoose,
  onSkip,
}: {
  question: AiFillQuestion;
  choice: string | undefined;
  disabled: boolean;
  onChoose: (choice: string) => void;
  onSkip: () => void;
}) {
  const hint = KIND_HINTS[question.kind];
  return (
    <div className="space-y-2 rounded-lg border border-violet-200 bg-violet-50/60 px-3 py-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {question.attempt > 1 && (
          <span className="rounded-full bg-amber-100 px-1.5 py-px text-[10px] font-semibold text-amber-800">Asked again</span>
        )}
        {hint && <span className="text-[11px] text-slate-500">{hint}</span>}
      </div>
      <p className="text-sm font-medium text-slate-900">{question.text}</p>
      {question.choices.length > 0 && (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Choices">
          {question.choices.map((option) => (
            <button
              key={option}
              type="button"
              disabled={disabled}
              aria-pressed={choice === option}
              onClick={() => onChoose(option)}
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
                choice === option
                  ? "border-violet-600 bg-violet-600 text-white"
                  : "border-violet-300 bg-white text-violet-800 hover:bg-violet-100",
              )}
            >
              {option}
            </button>
          ))}
        </div>
      )}
      <button
        type="button"
        onClick={onSkip}
        className="rounded text-xs text-slate-500 underline underline-offset-2 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
      >
        Skip, I'll fill it
      </button>
    </div>
  );
}
