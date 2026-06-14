// Minimal Service Worker for Installable PWA
// NO CACHING - Always fetches from network

const CACHE_NAME = 'djacc-minimal-cache-v1';

self.addEventListener('install', (event) => {
    // Skip waiting to activate immediately
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    // Take control of all pages immediately
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
    // Always fetch from the network.
    // If offline, it will naturally fail, which is exactly what we want for an accounting app without offline sync.
    event.respondWith(
        fetch(event.request)
    );
});
