const MEDIA_API_URL = process.env.MEDIA_API_URL ?? "http://127.0.0.1:8787";

const ALLOWED_PATHS = [
  /^health$/,
  /^v1\/renders$/,
  /^v1\/jobs\/[a-zA-Z0-9_-]+$/,
  /^v1\/jobs\/[a-zA-Z0-9_-]+\/outputs\/(16x9|9x16)$/,
  /^v1\/tts\/synth$/,
  /^v1\/tts\/audio\/[a-zA-Z0-9_.-]+$/,
];

function isAllowed(path: string) {
  return ALLOWED_PATHS.some((pattern) => pattern.test(path));
}

async function proxy(request: Request, context: RouteContext<"/api/media/[...path]">) {
  const { path: segments } = await context.params;
  const path = segments.join("/");

  if (!isAllowed(path)) {
    return Response.json({ error: "Unsupported media endpoint" }, { status: 404 });
  }

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  try {
    const upstream = await fetch(`${MEDIA_API_URL}/${path}`, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });

    const responseHeaders = new Headers();
    const upstreamType = upstream.headers.get("content-type");
    if (upstreamType) responseHeaders.set("content-type", upstreamType);
    const disposition = upstream.headers.get("content-disposition");
    if (disposition) responseHeaders.set("content-disposition", disposition);

    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      { error: "Media service unavailable", service: MEDIA_API_URL },
      { status: 503 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;

