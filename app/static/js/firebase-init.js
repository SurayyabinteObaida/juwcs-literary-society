/*
 * JUWCS Literary Society — Firebase initialization module.
 *
 * Reusable module: initializes the Firebase app + FCM messaging instance
 * using the current (modular v9+) Web SDK, loaded as native ES modules
 * from the Firebase-hosted CDN — no bundler needed for this project.
 *
 * Exposes window.JUWCSFirebase = { app, messaging, ready } once loaded, and
 * fires a `juwcs:firebase-ready` event on `document` so other scripts don't
 * have to race the async import.
 */
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.13.0/firebase-app.js";
import {
  getMessaging,
  isSupported,
} from "https://www.gstatic.com/firebasejs/10.13.0/firebase-messaging.js";

async function init() {
  window.JUWCSFirebase = window.JUWCSFirebase || {};

  const supported = await isSupported().catch(function () { return false; });
  if (!supported) {
    // Safari/older browsers, or a non-secure context — FCM simply isn't
    // available here. The rest of the site works fine without it.
    window.JUWCSFirebase.supported = false;
    document.dispatchEvent(new CustomEvent("juwcs:firebase-ready", { detail: { supported: false } }));
    return;
  }

  let configResponse;
  try {
    configResponse = await fetch("/notifications/config.json", { credentials: "same-origin" });
  } catch (e) {
    window.JUWCSFirebase.supported = false;
    document.dispatchEvent(new CustomEvent("juwcs:firebase-ready", { detail: { supported: false } }));
    return;
  }
  if (!configResponse.ok) {
    // Most likely: not logged in yet. The prompt only ever shows to
    // authenticated users, so this module is loaded post-login.
    window.JUWCSFirebase.supported = false;
    document.dispatchEvent(new CustomEvent("juwcs:firebase-ready", { detail: { supported: false } }));
    return;
  }

  const { firebaseConfig, vapidKey } = await configResponse.json();

  const app = initializeApp(firebaseConfig);
  const messaging = getMessaging(app);

  window.JUWCSFirebase.app = app;
  window.JUWCSFirebase.messaging = messaging;
  window.JUWCSFirebase.vapidKey = vapidKey;
  window.JUWCSFirebase.supported = true;

  document.dispatchEvent(new CustomEvent("juwcs:firebase-ready", { detail: { supported: true } }));
}

init();
