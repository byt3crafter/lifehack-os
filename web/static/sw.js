/**
 * LifeHack OS — Service Worker
 *
 * Strategy:
 *   - API calls (/api/*)     : Network-first, fall back to a minimal offline response
 *   - Static assets          : Cache-first (versioned cache, stale served instantly)
 *   - Navigation (HTML pages): Network-first, fall back to cached shell
 */

const CACHE_VERSION = 'lifehack-v1';
const STATIC_CACHE  = `${CACHE_VERSION}-static`;
const DYNAMIC_CACHE = `${CACHE_VERSION}-dynamic`;

// Resources to pre-cache on install (the app shell)
const PRECACHE_URLS = [
  '/',
  '/static/manifest.json',
];

// ─── Install ────────────────────────────────────────────────────────────────

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(PRECACHE_URLS);
    })
  );
  // Activate the new SW immediately without waiting for old tabs to close
  self.skipWaiting();
});

// ─── Activate ───────────────────────────────────────────────────────────────

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith('lifehack-') && key !== STATIC_CACHE && key !== DYNAMIC_CACHE)
          .map((key) => caches.delete(key))
      )
    )
  );
  // Take control of all open clients immediately
  self.clients.claim();
});

// ─── Fetch ──────────────────────────────────────────────────────────────────

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== location.origin) return;

  // API requests: network-first, no caching (always fresh data)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request, null));
    return;
  }

  // Auth routes: always network (never cache login/logout)
  if (url.pathname.startsWith('/auth/')) {
    return;
  }

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // Navigation (HTML): network-first, fall back to cached shell
  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request, '/'));
    return;
  }
});

// ─── Strategies ─────────────────────────────────────────────────────────────

/**
 * Cache-first: serve from cache, fetch & update cache on miss.
 */
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
    return new Response('Offline — resource not cached', { status: 503 });
  }
}

/**
 * Network-first: try network, fall back to cache or fallbackUrl.
 */
async function networkFirst(request, fallbackUrl) {
  try {
    const response = await fetch(request);

    // Cache successful non-API GET responses for offline fallback
    if (response.ok && request.method === 'GET' && !request.url.includes('/api/')) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, response.clone());
    }

    return response;
  } catch {
    // Network failed — try cache
    const cached = await caches.match(request);
    if (cached) return cached;

    // Fall back to shell URL (e.g. "/") for navigation requests
    if (fallbackUrl) {
      const shell = await caches.match(fallbackUrl);
      if (shell) return shell;
    }

    // Final fallback for API calls when offline
    if (request.url.includes('/api/')) {
      return new Response(
        JSON.stringify({ error: 'Offline — no network connection', offline: true }),
        {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        }
      );
    }

    return new Response('You are offline and this page is not cached.', { status: 503 });
  }
}
