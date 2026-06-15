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

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    
    const urlToOpen = event.notification.data && event.notification.data.url;
    if (!urlToOpen) return;
    
    event.waitUntil(
        clients.matchAll({
            type: 'window',
            includeUncontrolled: true
        }).then(function(windowClients) {
            // Check if there is already an app window open
            for (var i = 0; i < windowClients.length; i++) {
                var client = windowClients[i];
                if (client.url.indexOf(self.location.origin) === 0 && 'focus' in client) {
                    return client.navigate(urlToOpen).then(function(c) {
                        return c.focus();
                    });
                }
            }
            // If no window is open, open a new window
            if (clients.openWindow) {
                return clients.openWindow(urlToOpen);
            }
        })
    );
});

