/*
 * JUWCS Literary Society — Firebase Cloud Messaging service worker.
 *
 * Handles PUSH notifications while the site isn't in the foreground tab.
 * Foreground messages are handled separately in static/js/notifications.js
 * via onMessage(), so this file only needs to cover the background case.
 *
 * This file can't use ES module imports (service workers only support
 * modular ESM imports in newer browsers behind a registration flag), so it
 * uses the classic `importScripts` + compat build, which is Firebase's own
 * current documented approach for the messaging service worker.
 */
importScripts("https://www.gstatic.com/firebasejs/10.13.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.13.0/firebase-messaging-compat.js");

// Firebase web config for the "juw-literary-society" project. This is a
// public client identifier, not a secret — safe to ship in a static file.
// (Kept here, not fetched from the backend, because a service worker can't
// make an authenticated fetch to /notifications/config.json before it has
// established a session — see notifications.js for how the same values are
// fetched server-side for the main-thread initializer.)
firebase.initializeApp({
  apiKey: "AIzaSyAlUvVmHvTWfYJlz_S2k7vtV8YiL6sCk-U",
  authDomain: "juw-literary-society.firebaseapp.com",
  projectId: "juw-literary-society",
  storageBucket: "juw-literary-society.firebasestorage.app",
  messagingSenderId: "703301282139",
  appId: "1:703301282139:web:b17eb27d17632a4831527e",
  measurementId: "G-2YWW0LWTFR",
});

const messaging = firebase.messaging();

const DEFAULT_ICON = "/static/img/favicon.svg";

messaging.onBackgroundMessage(function (payload) {
  const data = payload.data || {};
  const title = data.title || (payload.notification && payload.notification.title) || "The Literary Society";
  const body = data.body || (payload.notification && payload.notification.body) || "";
  const link = data.link || "/";

  const options = {
    body: body,
    icon: DEFAULT_ICON,
    badge: DEFAULT_ICON,
    data: { link: link },
    tag: data.type || "juwcs-notification",
  };

  self.registration.showNotification(title, options);
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  const link = (event.notification.data && event.notification.data.link) || "/";

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (windowClients) {
      for (const client of windowClients) {
        try {
          const clientUrl = new URL(client.url);
          if (clientUrl.origin === self.location.origin && "focus" in client) {
            client.postMessage({ type: "juwcs-notification-click", link: link });
            client.focus();
            if (clientUrl.pathname !== link) {
              return client.navigate(link);
            }
            return;
          }
        } catch (e) {
          // ignore malformed client URLs
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(link);
      }
    })
  );
});
