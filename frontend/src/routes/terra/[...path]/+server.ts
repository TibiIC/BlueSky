import type { RequestHandler } from './$types';

// Same-origin, allowlisted local bridge; never proxy arbitrary URLs or credentials.
const handle: RequestHandler = async ({ params, request }) => {
 const allowed = new Set(['events', 'global-events', 'api/frame', 'api/global-frame', 'api/control', 'api/timeline', 'api/comparison', 'api/health', 'api/scenario']);
 const path = params.path ?? '';
 if (!allowed.has(path) || (request.method === 'POST' && !['api/control','api/timeline','api/comparison','api/scenario'].includes(path))) return new Response('Not found', { status: 404 });
 try {
  const upstream = await fetch(`http://127.0.0.1:8765/${path}`, {
   method: request.method, signal: request.signal,
   headers: request.method === 'POST' ? { 'Content-Type': 'application/json' } : {},
   body: request.method === 'POST' ? await request.text() : undefined
  });
  return new Response(upstream.body, { status: upstream.status, headers: {
   'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json',
   'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no',
   ...(path.endsWith('events') ? { 'Content-Encoding': 'identity' } : {})
  }});
 } catch { return new Response('TERRA backend unavailable. Run python3 server.py on port 8765.', { status: 502 }); }
};
export const GET = handle;
export const POST = handle;
