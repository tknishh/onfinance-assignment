"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { MoreHorizontal, Send, Square, X } from "lucide-react";
import { DiagramTypePicker } from "@/components/chat/diagram-type-picker";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const SEBI_JSON = `{
  "prompt": "I am working on a compliance monitoring solution which will pull in the latest circulars from SEBI and parse them. Once it is parsed into a table of clauses, you will need to extract the following information:\\n1. The new compliance requirements proposed by the regulator\\n2. Gap analysis with my existing compliance setup\\n3. The impact of these new compliance requirements on my organization at an IT and operational level",
  "diagram_types": ["sequential", "component", "class", "activity", "deployment", "use_case"]
}`;

export type ComposerHandle = {
  focus: () => void;
};

type Props = {
  hasConversation: boolean;
  kinds: string[];
  onKindsChange: (v: string[]) => void;
  isStreaming: boolean;
  onSend: (message: string) => void;
  onAbort: () => void;
  draft: string;
  onDraftChange: (v: string) => void;
  jsonMode: boolean;
  onJsonModeChange: (v: boolean) => void;
  onAddKind?: (kind: string) => void;
  /** Transparent shell for landing (grid shows through). */
  embedded?: boolean;
};

export const Composer = forwardRef<ComposerHandle, Props>(function Composer(
  {
    hasConversation,
    kinds,
    onKindsChange,
    isStreaming,
    onSend,
    onAbort,
    draft,
    onDraftChange,
    jsonMode,
    onJsonModeChange,
    onAddKind,
    embedded = false,
  },
  ref
) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => ({
    focus() {
      const el = textareaRef.current;
      if (!el) return;
      el.focus();
      const len = el.value.length;
      el.setSelectionRange(len, len);
    },
  }));

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, embedded ? 120 : 220)}px`;
  }, [draft, embedded]);

  function submit() {
    const msg = draft.trim();
    if (!msg || isStreaming) return;
    onSend(msg);
    onDraftChange("");
  }

  function setJson(next: boolean) {
    onJsonModeChange(next);
    if (next && !draft.trim()) onDraftChange(SEBI_JSON);
  }

  return (
    <div
      className={cn(
        "w-full",
        embedded
          ? "bg-transparent px-4 pb-6 pt-2"
          : "border-t border-border/70 bg-background/90 p-3 backdrop-blur-md sm:p-4"
      )}
    >
      <div
        className={cn(
          "mx-auto w-full max-w-4xl space-y-2.5 rounded-2xl border border-border bg-card p-3 shadow-sm sm:p-4",
          embedded && "bg-card/95"
        )}
      >
        <DiagramTypePicker
          value={kinds}
          onChange={onKindsChange}
          followUp={hasConversation}
          onAddKind={onAddKind}
        />
        <Textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          placeholder={
            hasConversation
              ? "Ask a question or describe a change…"
              : "Describe the software you want to design…"
          }
          className={
            jsonMode
              ? "min-h-[88px] resize-none border-0 bg-transparent font-mono text-xs shadow-none focus-visible:ring-0"
              : "min-h-[48px] resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
          }
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Popover>
              <PopoverTrigger
                render={
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    className="size-8 rounded-full"
                    aria-label="Composer options"
                  />
                }
              >
                <MoreHorizontal className="h-4 w-4" />
              </PopoverTrigger>
              <PopoverContent align="start" className="w-56 p-3">
                <div className="flex items-center justify-between gap-3">
                  <Label htmlFor="json-mode" className="text-sm font-medium">
                    JSON payload
                  </Label>
                  <Switch
                    id="json-mode"
                    checked={jsonMode}
                    onCheckedChange={(v) => setJson(!!v)}
                  />
                </div>
              </PopoverContent>
            </Popover>
            {jsonMode && (
              <button
                type="button"
                onClick={() => setJson(false)}
                className="inline-flex h-7 items-center gap-1 rounded-full border border-border bg-muted px-2.5 text-xs font-medium text-foreground hover:bg-muted/80"
              >
                JSON mode
                <X className="h-3 w-3 text-muted-foreground" />
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            {!isStreaming && (
              <span className="hidden text-[11px] text-muted-foreground sm:inline">
                ⏎ send · ⇧⏎ newline
              </span>
            )}
            {isStreaming ? (
              <Button
                type="button"
                size="sm"
                className="rounded-full bg-foreground px-4 text-background hover:bg-foreground/90"
                onClick={onAbort}
              >
                <Square className="mr-1 h-3.5 w-3.5" />
                Stop
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                className={cn(
                  "rounded-full px-5 font-semibold shadow-sm",
                  draft.trim()
                    ? "bg-brand-yellow text-ink-on-yellow hover:bg-brand-yellow/90"
                    : "cursor-not-allowed bg-muted text-muted-foreground hover:bg-muted"
                )}
                onClick={submit}
                disabled={!draft.trim()}
              >
                <Send className="mr-1 h-3.5 w-3.5" />
                Send
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
});
