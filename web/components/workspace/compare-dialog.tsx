"use client";

import ReactDiffViewer from "react-diff-viewer-continued";
import { useTheme } from "next-themes";
import type { DiagramResult } from "@/lib/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useSvgUrl } from "@/hooks/use-svg-url";

function SvgImg({ svg }: { svg: string | null }) {
  const url = useSvgUrl(svg);
  if (!url) return <div className="text-sm text-muted-foreground">No SVG</div>;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={url}
      alt=""
      className="max-h-64 w-full bg-white object-contain"
    />
  );
}

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  previous: DiagramResult | null;
  current: DiagramResult;
};

export function CompareDialog({ open, onOpenChange, previous, current }: Props) {
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>Compare {current.kind.replaceAll("_", " ")}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <div className="mb-1 text-xs text-muted-foreground">Previous</div>
            <SvgImg svg={previous?.svg ?? null} />
          </div>
          <div>
            <div className="mb-1 text-xs text-muted-foreground">Current</div>
            <SvgImg svg={current.svg} />
          </div>
        </div>
        <div className="max-h-72 overflow-auto rounded border text-xs">
          <ReactDiffViewer
            oldValue={previous?.plantuml || ""}
            newValue={current.plantuml}
            splitView
            useDarkTheme={dark}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
