"use client";

import {
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import { TransformComponent, TransformWrapper } from "react-zoom-pan-pinch";
import { Maximize2, ZoomIn, ZoomOut } from "lucide-react";
import type { DiagramResult } from "@/lib/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useSvgUrl } from "@/hooks/use-svg-url";

type Props = {
  diagram: DiagramResult;
  /** Extra controls rendered on the same row as zoom (copy, download, …). */
  actions?: ReactNode;
  onRegenerate?: () => void;
};

type FitFn = (options?: {
  mode?: "contain" | "cover";
  animationTime?: number;
}) => Promise<void>;

export function DiagramCanvas({ diagram, actions, onRegenerate }: Props) {
  const url = useSvgUrl(diagram.svg);
  const fitRef = useRef<FitFn | null>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const fittedOnceRef = useRef(false);

  const fitToPage = useCallback((force = false) => {
    const run = () => {
      const el = viewportRef.current;
      if (!el || el.clientWidth < 8 || el.clientHeight < 8) return;
      void fitRef.current?.({ mode: "contain", animationTime: 0 });
      fittedOnceRef.current = true;
    };
    if (!force && fittedOnceRef.current) return;
    // Two frames: dialog flex height often settles after the first paint.
    requestAnimationFrame(() => requestAnimationFrame(run));
  }, []);

  useEffect(() => {
    fittedOnceRef.current = false;
    const el = viewportRef.current;
    if (!el || typeof ResizeObserver === "undefined") {
      fitToPage(true);
      return;
    }
    // Fit while the viewport is still settling; stop after the first success
    // so later window resizes do not wipe the user's zoom.
    const ro = new ResizeObserver(() => {
      if (!fittedOnceRef.current) fitToPage(true);
    });
    ro.observe(el);
    fitToPage(true);
    return () => ro.disconnect();
  }, [fitToPage, diagram.diagram_id, url]);

  if (!diagram.is_valid) {
    return (
      <div className="flex h-full min-h-0 flex-col items-start justify-center gap-3 p-6">
        <Alert variant="destructive" className="w-full max-w-lg">
          <AlertDescription>
            {diagram.error || "Invalid diagram"}
          </AlertDescription>
        </Alert>
        {onRegenerate && (
          <Button
            type="button"
            size="sm"
            className="rounded-full bg-brand-yellow font-semibold text-ink-on-yellow hover:bg-brand-yellow/90"
            onClick={onRegenerate}
          >
            Regenerate this diagram
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {diagram.warnings?.map((w) => (
        <Alert
          key={w}
          className="mx-4 mt-2 shrink-0 border-amber-500/40 text-amber-700 dark:text-amber-300"
        >
          <AlertDescription>{w}</AlertDescription>
        </Alert>
      ))}

      <TransformWrapper
        key={diagram.diagram_id}
        initialScale={1}
        minScale={0.05}
        maxScale={8}
        limitToBounds={false}
        fitOnInit="contain"
        disablePadding
        centerZoomedOut
        wheel={{ step: 0.07 }}
        doubleClick={{ mode: "reset" }}
        panning={{ velocityDisabled: true }}
        keyboard={{ disabled: false, panStep: 48 }}
      >
        {({ zoomIn, zoomOut, fitToView }) => {
          fitRef.current = fitToView;
          return (
            <>
              <div className="flex shrink-0 flex-wrap items-center gap-2 border-b px-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-foreground">
                    {diagram.title || diagram.kind.replaceAll("_", " ")}
                  </p>
                  <p className="text-xs capitalize text-muted-foreground">
                    {diagram.kind.replaceAll("_", " ")}
                  </p>
                </div>
                <div className="flex items-center gap-0.5">
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    onClick={() => zoomIn()}
                    aria-label="Zoom in"
                  >
                    <ZoomIn />
                  </Button>
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    onClick={() => zoomOut()}
                    aria-label="Zoom out"
                  >
                    <ZoomOut />
                  </Button>
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    onClick={() => {
                      fittedOnceRef.current = false;
                      fitToPage(true);
                    }}
                    aria-label="Fit to page"
                  >
                    <Maximize2 />
                  </Button>
                  {actions && (
                    <>
                      <span className="mx-1 h-5 w-px bg-border" aria-hidden />
                      {actions}
                    </>
                  )}
                </div>
              </div>

              <div
                ref={viewportRef}
                className="relative min-h-0 flex-1 overflow-hidden bg-muted/40"
              >
                <TransformComponent
                  wrapperStyle={{ width: "100%", height: "100%" }}
                  contentStyle={{ width: "fit-content", height: "fit-content" }}
                  wrapperClass="cursor-grab active:cursor-grabbing outline-none"
                  contentClass="p-4"
                >
                  {url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={url}
                      alt={diagram.title}
                      draggable={false}
                      onLoad={() => fitToPage(true)}
                      className="block max-w-none select-none rounded-lg bg-white p-3 shadow-sm"
                    />
                  ) : (
                    <div className="text-sm text-muted-foreground">No SVG</div>
                  )}
                </TransformComponent>
              </div>
            </>
          );
        }}
      </TransformWrapper>
    </div>
  );
}
