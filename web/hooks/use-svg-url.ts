"use client";

import { useMemo, useEffect } from "react";

/** Stable blob URL for an SVG string; revoked when the SVG changes or on unmount. */
export function useSvgUrl(svg: string | null | undefined): string | null {
  const url = useMemo(() => {
    if (!svg) return null;
    return URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  }, [svg]);

  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [url]);

  return url;
}
