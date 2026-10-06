"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import type { TimelineOut } from "@/lib/types";
import { ArchitectureView } from "@/components/workspace/architecture-view";
import { DiagramCanvas } from "@/components/workspace/diagram-canvas";
import { DiagramToolbar } from "@/components/workspace/diagram-toolbar";
import { FeedbackBar } from "@/components/workspace/feedback-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Props = {
  timeline: TimelineOut;
  versionId: number | null;
  selectedTab: string;
  userId: string;
  onVersionChange: (id: number) => void;
  onTabChange: (tab: string) => void;
  onApplyRevision: (comment: string) => void;
  onClose?: () => void;
};

export function DiagramWorkspace({
  timeline,
  versionId,
  selectedTab,
  userId,
  onVersionChange,
  onTabChange,
  onApplyRevision,
}: Props) {
  const versions = timeline.versions;
  const version =
    versions.find((v) => v.id === versionId) || versions[versions.length - 1];
  if (!version) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        No diagrams yet
      </div>
    );
  }
  const idx = versions.findIndex((v) => v.id === version.id);
  const prev = versions.find((v) => v.version_no === version.version_no - 1);
  const problemKinds = version.diagrams
    .filter((d) => !d.is_valid || (d.warnings?.length ?? 0) > 0)
    .map((d) => d.kind);
  const inconsistent = problemKinds.length;

  function goVersion(delta: number) {
    const next = versions[idx + delta];
    if (next) onVersionChange(next.id);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2.5 pr-12">
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">
            {timeline.conversation.title}
          </div>
          <div className="text-[11px] text-muted-foreground">
            Esc to close
          </div>
        </div>
        <div className="flex items-center gap-1 rounded-full border bg-background p-0.5">
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            className="rounded-full"
            disabled={idx <= 0}
            onClick={() => goVersion(-1)}
            aria-label="Previous version"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[5.5rem] px-1 text-center text-xs font-medium tabular-nums">
            Version {version.version_no} of {versions.length}
          </span>
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            className="rounded-full"
            disabled={idx < 0 || idx >= versions.length - 1}
            onClick={() => goVersion(1)}
            aria-label="Next version"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        {inconsistent > 0 && (
          <button
            type="button"
            onClick={() => onTabChange(problemKinds[0])}
            className="rounded-full"
          >
            <Badge
              variant="outline"
              className="cursor-pointer rounded-full border-amber-400 bg-amber-50 text-amber-900 hover:bg-amber-100 dark:bg-amber-950 dark:text-amber-100 dark:hover:bg-amber-900"
            >
              {inconsistent} need review
            </Badge>
          </button>
        )}
      </div>
      <Tabs
        value={selectedTab}
        onValueChange={onTabChange}
        className="flex min-h-0 flex-1 flex-col"
      >
        <div className="border-b bg-muted/40 px-3 py-2">
          <TabsList
            variant="default"
            className="inline-flex h-auto w-auto max-w-full justify-start gap-1 overflow-x-auto rounded-full bg-muted p-1"
          >
            <TabsTrigger
              value="architecture"
              className="h-8 flex-none rounded-full px-3.5 text-sm data-active:bg-foreground data-active:text-background data-active:shadow-none"
            >
              Architecture
            </TabsTrigger>
            {version.diagrams.map((d) => (
              <TabsTrigger
                key={d.kind}
                value={d.kind}
                title={d.title || d.kind}
                className="h-8 flex-none rounded-full px-3.5 text-sm capitalize data-active:bg-foreground data-active:text-background data-active:shadow-none"
              >
                {d.kind.replaceAll("_", " ")}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent
          value="architecture"
          className="min-h-0 flex-1 overflow-auto data-[state=inactive]:hidden"
        >
          {version.design_model ? (
            <ArchitectureView model={version.design_model} />
          ) : (
            <p className="p-4 text-sm text-muted-foreground">
              No design model for this version.
            </p>
          )}
        </TabsContent>
        {version.diagrams.map((d) => {
          const prevDiag =
            prev?.diagrams.find((x) => x.kind === d.kind) || null;
          return (
            <TabsContent
              key={d.kind}
              value={d.kind}
              className="flex min-h-0 flex-1 flex-col data-[state=inactive]:hidden"
            >
              <div className="min-h-0 flex-1 overflow-hidden">
                <DiagramCanvas
                  diagram={d}
                  onRegenerate={() =>
                    onApplyRevision(
                      `regenerate the ${d.kind.replaceAll("_", " ")} diagram`
                    )
                  }
                  actions={
                    <DiagramToolbar
                      diagram={d}
                      previous={prevDiag}
                      conversationId={timeline.conversation.id}
                      userId={userId}
                      compact
                    />
                  }
                />
              </div>
              <FeedbackBar
                userId={userId}
                versionId={version.id}
                diagramId={d.diagram_id}
                onApplyRevision={onApplyRevision}
              />
            </TabsContent>
          );
        })}
      </Tabs>
    </div>
  );
}
