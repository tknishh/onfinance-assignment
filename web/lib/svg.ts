export function svgToBlobUrl(svg: string): string {
  const blob = new Blob([svg], { type: "image/svg+xml" });
  return URL.createObjectURL(blob);
}

export function downloadText(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function downloadSvg(filename: string, svg: string) {
  downloadText(filename, svg, "image/svg+xml");
}

export async function downloadPng(filename: string, svg: string) {
  const url = svgToBlobUrl(svg);
  try {
    const img = new Image();
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error("Failed to load SVG"));
      img.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth * 2 || 1600;
    canvas.height = img.naturalHeight * 2 || 1200;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("No canvas");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/png")
    );
    if (!blob) throw new Error("PNG export failed");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  } finally {
    URL.revokeObjectURL(url);
  }
}
