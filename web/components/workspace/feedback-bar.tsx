"use client";

import { useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type Props = {
  userId: string;
  versionId: number;
  diagramId: number;
  onApplyRevision: (comment: string) => void;
};

export function FeedbackBar({
  userId,
  versionId,
  diagramId,
  onApplyRevision,
}: Props) {
  const [rating, setRating] = useState<-1 | 1 | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (rating == null) return;
    setBusy(true);
    try {
      await api.feedback({
        user_id: userId,
        version_id: versionId,
        diagram_id: diagramId,
        rating,
        comment: comment || null,
      });
      toast.success("Feedback saved");
      setComment("");
      setRating(null);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const canApply = rating === -1 && comment.trim().length > 0;

  return (
    <div className="flex flex-wrap items-center gap-2 border-t p-3">
      <Button
        size="icon-sm"
        variant="ghost"
        className={cn(
          rating === 1 &&
            "bg-emerald-100 text-emerald-800 hover:bg-emerald-100 dark:bg-emerald-950 dark:text-emerald-200"
        )}
        onClick={() => setRating(1)}
        aria-label="Thumbs up"
        aria-pressed={rating === 1}
      >
        <ThumbsUp />
      </Button>
      <Button
        size="icon-sm"
        variant="ghost"
        className={cn(
          rating === -1 &&
            "bg-red-100 text-red-700 hover:bg-red-100 dark:bg-red-950 dark:text-red-200"
        )}
        onClick={() => setRating(-1)}
        aria-label="Thumbs down"
        aria-pressed={rating === -1}
      >
        <ThumbsDown />
      </Button>
      <Input
        placeholder="Comment (optional)"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        className="h-8 min-w-[8rem] flex-1"
      />
      {canApply && (
        <Button
          size="sm"
          variant="outline"
          className="rounded-full"
          disabled={busy}
          onClick={() => onApplyRevision(comment.trim())}
        >
          Apply as revision
        </Button>
      )}
      <Button
        size="sm"
        className={cn(
          "rounded-full font-semibold",
          rating != null
            ? "bg-brand-yellow text-ink-on-yellow hover:bg-brand-yellow/90"
            : "cursor-not-allowed bg-muted text-muted-foreground hover:bg-muted"
        )}
        onClick={submit}
        disabled={busy || rating == null}
      >
        Submit
      </Button>
    </div>
  );
}
