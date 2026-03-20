/**
 * LifeHack OS — Service Worker (PWA)
 *
 * Strategy:
 *   - API calls (/api/*)     : Network-only (always fresh data, no stale cache)
 *   - Static assets (/static): Cache-first (fast loads)
 *   - Navigation (HTML)      : Network-first, fall back to cached app shell
 *   - Uploads (/uploads)     : Cache-first (images don't change)
 */

const CACHE_VERSION = 'lifehack-v3';
const STATIC_CACHE  = `${CACHE_VERSION}-static`;

const PRECACHE_URLS = [
  '/',
  '/static/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/icon.svg',
];

// ─── Install ────────────────────────────────────────────────────────────────

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

// ─── Activate ───────────────────────────────────────────────────────────────

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith('lifehack-') && key !== STATIC_CACHE)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// ─── Fetch ──────────────────────────────────────────────────────────────────

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin
  if (url.origin !== location.origin) return;

  // API: always network, never cache
  if (url.pathname.startsWith('/api/')) return;

  // Auth routes: always network
  if (url.pathname === '/login' || url.pathname === '/logout' || url.pathname === '/register') return;

  // Static assets + uploads: cache-first
  if (url.pathname.startsWith('/static/') || url.pathname.startsWith('/uploads/')) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // Navigation: network-first with shell fallback
  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request));
    return;
  }
});

// ─── Strategies ─────────────────────────────────────────────────────────────

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('', { status: 503 });
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;

    // Fall back to cached shell
    const shell = await caches.match('/');
    if (shell) return shell;

    return new Response('Offline', { status: 503 });
  }
}
