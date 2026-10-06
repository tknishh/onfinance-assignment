"use client";

import { AlertCircle, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { LiveState } from "@/lib/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { useSvgUrl } from "@/hooks/use-svg-url";

function Thumb({ svg, title }: { svg: string; title: string }) {
  const url = useSvgUrl(svg);
  if (!url) return <Skeleton className="aspect-[4/3] w-full" />;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={url}
      alt={title}
      className="aspect-[4/3] w-full rounded-lg bg-white object-contain"
    />
  );
}

export function GenerationProgress({ live }: { live: LiveState }) {
  const kinds = Object.keys(live.diagrams);
  const done = kinds.filter((k) => live.diagrams[k]?.status === "done").length;
  const failed = kinds.filter((k) => live.diagrams[k]?.status === "failed").length;
  const generating = kinds.some((k) => live.diagrams[k]?.status === "queued");
  const isQuestion = live.intent?.intent === "question";

  let status: string | null = null;
  if (live.error) status = null;
  else if (isQuestion && !live.answer) status = "Thinking…";
  else if ((generating || live.designModel === null) && !live.answer) {
    status = kinds.length
      ? `Generating diagrams${done ? ` (${done}/${kinds.length})` : "…"}`
      : "Generating…";
  } else if (failed && done + failed === kinds.length) {
    status = `${failed} diagram${failed === 1 ? "" : "s"} failed`;
  }

  return (
    <div className="space-y-3 rounded-xl border bg-card p-4">
      {status && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          {(generating || (isQuestion && !live.answer)) && (
            <Loader2 className="h-4 w-4 animate-spin" />
          )}
          {status}
        </div>
      )}
      {live.answer && (
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{live.answer}</ReactMarkdown>
        </div>
      )}
      {kinds.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-2">
          {Object.entries(live.diagrams).map(([kind, row]) => (
            <div key={kind} className="rounded-xl border p-2">
              {row.status === "queued" && (
                <div className="space-y-1.5">
                  <Skeleton className="aspect-[4/3] w-full rounded-lg" />
                  <div className="text-xs font-semibold capitalize text-muted-foreground">
                    {kind.replaceAll("_", " ")}
                  </div>
                </div>
              )}
              {row.status === "done" && row.data?.svg && (
                <div>
                  <Thumb
                    svg={row.data.svg}
                    title={row.data.title || kind}
                  />
                  <div className="mt-1.5 truncate text-xs font-semibold capitalize text-foreground">
                    {kind.replaceAll("_", " ")}
                  </div>
                </div>
              )}
              {row.status === "failed" && (
                <div className="flex aspect-[4/3] flex-col items-center justify-center gap-2 rounded-lg bg-muted/60 px-3 text-center">
                  <AlertCircle className="h-5 w-5 text-destructive" />
                  <div className="text-xs font-semibold capitalize text-foreground">
                    {kind.replaceAll("_", " ")}
                  </div>
                  <div className="line-clamp-2 text-[11px] text-muted-foreground">
                    Failed
                    {row.data?.error ? ` · ${row.data.error}` : ""}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {live.error && (
        <Alert variant="destructive">
          <AlertDescription>{live.error}</AlertDescription>
        </Alert>
      )}
    </div>
  );
}
