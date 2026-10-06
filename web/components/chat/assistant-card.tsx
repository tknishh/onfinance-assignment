"use client";

import { Check } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { DesignModel, MessageOut, VersionOut } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { useSvgUrl } from "@/hooks/use-svg-url";
import { cn } from "@/lib/utils";

function Thumb({
  svg,
  label,
  fullTitle,
  selected,
  onClick,
}: {
  svg: string;
  label: string;
  fullTitle: string;
  selected: boolean;
  onClick: () => void;
}) {
  const url = useSvgUrl(svg);
  return (
    <button
      type="button"
      onClick={onClick}
      title={fullTitle}
      aria-pressed={selected}
      className={cn(
        "relative rounded-xl border p-2 text-left transition",
        selected
          ? "border-transparent bg-accent ring-2 ring-foreground"
          : "border-border bg-card hover:border-foreground/30"
      )}
    >
      {selected && (
        <span className="absolute right-1.5 top-1.5 flex size-5 items-center justify-center rounded-full bg-foreground text-background">
          <Check className="size-3" />
        </span>
      )}
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={url}
          alt={fullTitle}
          className="aspect-[4/3] w-full rounded-lg bg-white object-contain"
        />
      ) : (
        <div className="aspect-[4/3] rounded-lg bg-muted" />
      )}
      <div className="mt-1.5 text-xs font-semibold capitalize text-foreground">
        {label}
      </div>
    </button>
  );
}

function ArchitectureTile({
  model,
  selected,
  onClick,
}: {
  model: DesignModel | null | undefined;
  selected: boolean;
  onClick: () => void;
}) {
  const bits = model
    ? [
        model.components.length
          ? `${model.components.length} components`
          : null,
        model.data_stores.length
          ? `${model.data_stores.length} stores`
          : null,
        model.actors.length ? `${model.actors.length} actors` : null,
      ].filter(Boolean)
    : [];

  return (
    <button
      type="button"
      onClick={onClick}
      title="Architecture"
      aria-pressed={selected}
      className={cn(
        "relative flex flex-col rounded-xl border p-2 text-left transition",
        selected
          ? "border-transparent bg-accent ring-2 ring-foreground"
          : "border-border bg-card hover:border-foreground/30"
      )}
    >
      {selected && (
        <span className="absolute right-1.5 top-1.5 flex size-5 items-center justify-center rounded-full bg-foreground text-background">
          <Check className="size-3" />
        </span>
      )}
      <div className="flex aspect-[4/3] w-full flex-col justify-between rounded-lg bg-muted p-3">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Overview
        </div>
        <div>
          <div className="line-clamp-2 text-sm font-semibold text-foreground">
            {model?.system_name || "Architecture"}
          </div>
          {bits.length > 0 && (
            <div className="mt-1 text-[11px] text-muted-foreground">
              {bits.join(" · ")}
            </div>
          )}
        </div>
      </div>
      <div className="mt-1.5 text-xs font-semibold text-foreground">
        Architecture
      </div>
    </button>
  );
}

function intentLabel(intent: string | null, kinds?: string[]) {
  switch (intent) {
    case "new_design":
      return "Generated";
    case "revise":
      return "Revised";
    case "edit_diagrams":
      return `Edited: ${(kinds || []).join(", ")}`;
    case "add_diagrams":
      return `Added: ${(kinds || []).join(", ")}`;
    case "remove_diagrams":
      return `Removed: ${(kinds || []).join(", ")}`;
    case "question":
      return "Answer";
    default:
      return intent || "Assistant";
  }
}

type Props = {
  message: MessageOut;
  version?: VersionOut;
  selectedVersionId: number | null;
  selectedTab: string;
  viewerOpen: boolean;
  onOpenDiagram: (versionId: number, kind: string) => void;
  onOpenArchitecture: (versionId: number) => void;
};

export function AssistantCard({
  message,
  version,
  selectedVersionId,
  selectedTab,
  viewerOpen,
  onOpenDiagram,
  onOpenArchitecture,
}: Props) {
  const isQuestion = message.intent === "question";
  const isActiveVersion =
    viewerOpen && version != null && selectedVersionId === version.id;
  const diagramCount = version?.diagrams.filter((d) => d.svg).length ?? 0;

  return (
    <div className="space-y-3 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">
          {intentLabel(message.intent, version?.diagram_types)}
        </Badge>
        {version && <Badge variant="outline">v{version.version_no}</Badge>}
        {diagramCount > 0 && (
          <span className="text-xs text-muted-foreground">
            {diagramCount} diagram{diagramCount === 1 ? "" : "s"}
          </span>
        )}
      </div>
      {isQuestion ? (
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content}
          </ReactMarkdown>
        </div>
      ) : (
        <>
          {version?.change_summary ? (
            <p className="text-sm text-muted-foreground">{version.change_summary}</p>
          ) : (
            message.content && (
              <p className="text-sm text-muted-foreground">{message.content}</p>
            )
          )}
          {version && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-2">
              <ArchitectureTile
                model={version.design_model}
                selected={isActiveVersion && selectedTab === "architecture"}
                onClick={() => onOpenArchitecture(version.id)}
              />
              {version.diagrams.map((d) =>
                d.svg ? (
                  <Thumb
                    key={d.diagram_id}
                    svg={d.svg}
                    label={d.kind.replaceAll("_", " ")}
                    fullTitle={d.title || d.kind}
                    selected={isActiveVersion && selectedTab === d.kind}
                    onClick={() => onOpenDiagram(version.id, d.kind)}
                  />
                ) : null
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
