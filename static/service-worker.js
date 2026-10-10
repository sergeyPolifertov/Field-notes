var CACHE_NAME = 'notebook-v1';
var urlsToCache = [
    '/',
    '/static/manifest.json',
    '/static/icon-192.png',
    '/static/icon-512.png'
];

// Установка сервис-воркера и кэширование файлов
self.addEventListener('install', function(event) {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(function(cache) {
                console.log('Кэширование файлов');
                return cache.addAll(urlsToCache);
            })
    );
});

// Обработка запросов — сначала кэш, потом сеть
self.addEventListener('fetch', function(event) {
    event.respondWith(
        caches.match(event.request)
            .then(function(response) {
                if (response) {
                    return response; // Вернуть из кэша
                }
                return fetch(event.request); // Иначе загрузить из сети
            })
    );
});

// Обновление кэша при изменении версии
self.addEventListener('activate', function(event) {
    event.waitUntil(
        caches.keys().then(function(cacheNames) {
            return Promise.all(
                cacheNames.filter(function(cacheName) {
                    return cacheName !== CACHE_NAME;
                }).map(function(cacheName) {
                    return caches.delete(cacheName);
                })
            );
        })
    );
});