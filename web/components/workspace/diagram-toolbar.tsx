"use client";

import { useState } from "react";
import { Code2, Copy, Download, GitCompare } from "lucide-react";
import { toast } from "sonner";
import type { DiagramResult } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CodeEditorDialog } from "@/components/workspace/code-editor-dialog";
import { CompareDialog } from "@/components/workspace/compare-dialog";
import { downloadPng, downloadSvg, downloadText } from "@/lib/svg";

type Props = {
  diagram: DiagramResult;
  previous: DiagramResult | null;
  conversationId: number;
  userId: string;
  /** When true, only icon actions (for embedding next to zoom). */
  compact?: boolean;
};

export function DiagramToolbar({
  diagram,
  previous,
  conversationId,
  userId,
  compact = false,
}: Props) {
  const [editOpen, setEditOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const consistent = diagram.is_valid && !(diagram.warnings?.length);

  const actions = (
    <>
      <Button
        size="icon-sm"
        variant="ghost"
        onClick={() => {
          navigator.clipboard.writeText(diagram.plantuml);
          toast.success("Copied PlantUML");
        }}
        aria-label="Copy PlantUML"
      >
        <Copy />
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger
          className="inline-flex size-7 items-center justify-center rounded-md hover:bg-muted"
          aria-label="Download"
        >
          <Download className="h-4 w-4" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            onClick={() =>
              diagram.svg && downloadSvg(`${diagram.kind}.svg`, diagram.svg)
            }
          >
            SVG
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() =>
              diagram.svg && downloadPng(`${diagram.kind}.png`, diagram.svg)
            }
          >
            PNG
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() =>
              downloadText(`${diagram.kind}.puml`, diagram.plantuml, "text/plain")
            }
          >
            PlantUML
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Button
        size="icon-sm"
        variant="ghost"
        onClick={() => setEditOpen(true)}
        aria-label="Edit code"
      >
        <Code2 />
      </Button>
      <Button
        size="icon-sm"
        variant="ghost"
        disabled={!previous}
        onClick={() => setCompareOpen(true)}
        aria-label="Compare versions"
      >
        <GitCompare />
      </Button>
      <CodeEditorDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        diagram={diagram}
        conversationId={conversationId}
        userId={userId}
      />
      <CompareDialog
        open={compareOpen}
        onOpenChange={setCompareOpen}
        previous={previous}
        current={diagram}
      />
    </>
  );

  if (compact) {
    return <div className="flex items-center gap-0.5">{actions}</div>;
  }

  return (
    <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
      {!diagram.is_valid && (
        <Badge variant="destructive" className="rounded-full">
          invalid
        </Badge>
      )}
      {diagram.is_valid && !consistent && (
        <Badge
          variant="outline"
          className="rounded-full border-amber-400 bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100"
        >
          inconsistent
        </Badge>
      )}
      {diagram.reused && (
        <Badge variant="outline" className="rounded-full text-muted-foreground">
          reused
        </Badge>
      )}
      <div className="ml-auto flex gap-0.5">{actions}</div>
    </div>
  );
}
