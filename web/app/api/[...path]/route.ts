import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const API_URL = process.env.API_URL ?? "http://localhost:8080";

async function proxy(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  const { path } = await ctx.params;
  const url = `${API_URL}/${path.join("/")}${req.nextUrl.search}`;
  const hasBody = !["GET", "HEAD"].includes(req.method);

  try {
    const upstream = await fetch(url, {
      method: req.method,
      headers: {
        "content-type": req.headers.get("content-type") ?? "application/json",
        accept: req.headers.get("accept") ?? "*/*",
      },
      body: hasBody ? req.body : undefined,
      // @ts-expect-error duplex is required by Node fetch for streamed request bodies
      duplex: hasBody ? "half" : undefined,
      cache: "no-store",
      signal: req.signal,
    });
    const headers = new Headers(upstream.headers);
    headers.delete("content-encoding");
    headers.delete("content-length");
    headers.set("Cache-Control", "no-cache, no-transform");
    headers.set("X-Accel-Buffering", "no");
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Upstream API unreachable";
    return Response.json(
      { detail: `API unavailable: ${message}` },
      { status: 502 }
    );
  }
}

export {
  proxy as GET,
  proxy as POST,
  proxy as DELETE,
  proxy as PUT,
  proxy as PATCH,
};
