const SHELL = 'storyspeak-reader-v25';
const FILES = [
  './', './index.html', './styles.css', './app.js', './dictionary.js',
  './catalog.json', './tts/index.json', './manifest.webmanifest',
  './assets/icon-192.png', './assets/icon-512.png'
];
const SHELL_PATHS = new Set(FILES.map(file => new URL(file, self.registration.scope).pathname));

self.addEventListener('install', event => event.waitUntil(
  caches.open(SHELL).then(cache => cache.addAll(FILES)).then(() => self.skipWaiting())
));
self.addEventListener('activate', event => event.waitUntil((async () => {
  for (const name of await caches.keys()) {
    if ((name.startsWith('storyspeak-shell-') || name.startsWith('storyspeak-reader-')) && name !== SHELL) {
      await caches.delete(name);
    }
  }
  await self.clients.claim();
})()));
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== location.origin) return;
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(async () =>
      (await (await caches.open(SHELL)).match('./index.html')) || Response.error()
    ));
  } else if ([
    new URL('./tts/index.json', self.registration.scope).pathname,
    new URL('./catalog.json', self.registration.scope).pathname,
    new URL('./dictionary.js', self.registration.scope).pathname
  ].includes(url.pathname)) {
    event.respondWith(fetch(request).then(async response => {
      if (response.ok) (await caches.open(SHELL)).put(request, response.clone());
      return response;
    }).catch(async () => (await caches.open(SHELL)).match(request) || Response.error()));
  } else if (SHELL_PATHS.has(url.pathname)) {
    event.respondWith(caches.open(SHELL).then(async cache =>
      (await cache.match(request)) || fetch(request)
    ));
  }
  // Os pacotes de história só entram no cache se o usuário clicar em Baixar.
});

// O player cacheia os MP3 estáticos apenas após clique ou download explícito.
