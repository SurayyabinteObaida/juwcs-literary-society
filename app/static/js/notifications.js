/* JUWCS Literary Society — notification UI + FCM registration flow.
 * Loaded on every page (for logged-in users) via base.html. Talks to
 * firebase-init.js (loaded alongside it) for the actual Firebase handles.
 */
(function () {
  "use strict";

  if (!window.JUWCS_USER_AUTHENTICATED) return;

  var CSRF = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  var TOKEN_STORAGE_KEY = "juwcs-fcm-token";
  var DISMISS_STORAGE_KEY = "juwcs-notif-prompt-dismissed-at";
  var DISMISS_COOLDOWN_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

  function apiFetch(url, options) {
    options = options || {};
    options.credentials = "same-origin";
    options.headers = Object.assign({}, options.headers, { "X-CSRFToken": CSRF });
    return fetch(url, options);
  }

  function postJSON(url, body) {
    return apiFetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  }

  // ---------------------------------------------------------------------
  // Opt-in prompt card
  // ---------------------------------------------------------------------

  function shouldShowPrompt() {
    if (!("Notification" in window)) return false;
    if (Notification.permission !== "default") return false;
    var dismissedAt = parseInt(localStorage.getItem(DISMISS_STORAGE_KEY) || "0", 10);
    if (dismissedAt && Date.now() - dismissedAt < DISMISS_COOLDOWN_MS) return false;
    return true;
  }

  function showPrompt() {
    var el = document.getElementById("notif-prompt");
    if (el) el.classList.add("open");
  }

  function hidePrompt() {
    var el = document.getElementById("notif-prompt");
    if (el) el.classList.remove("open");
  }

  function wirePromptButtons() {
    var enableBtn = document.getElementById("notif-prompt-enable");
    var laterBtn = document.getElementById("notif-prompt-later");

    if (enableBtn) {
      enableBtn.addEventListener("click", function () {
        enableBtn.disabled = true;
        enableBtn.textContent = "Enabling…";
        enableNotifications().then(function (ok) {
          hidePrompt();
          if (ok) {
            toast("✓ Notifications Enabled", "You're all set — the Society will keep you posted.");
          }
          enableBtn.disabled = false;
          enableBtn.textContent = "Enable Notifications";
        });
      });
    }
    if (laterBtn) {
      laterBtn.addEventListener("click", function () {
        localStorage.setItem(DISMISS_STORAGE_KEY, String(Date.now()));
        hidePrompt();
      });
    }
  }

  // ---------------------------------------------------------------------
  // Core FCM registration flow
  // ---------------------------------------------------------------------

  function deviceMeta() {
    var ua = navigator.userAgent || "";
    var browser = "Browser";
    if (ua.indexOf("Edg/") > -1) browser = "Edge";
    else if (ua.indexOf("Chrome/") > -1) browser = "Chrome";
    else if (ua.indexOf("Firefox/") > -1) browser = "Firefox";
    else if (ua.indexOf("Safari/") > -1) browser = "Safari";

    var platform = "Desktop";
    if (/Android/i.test(ua)) platform = "Android";
    else if (/iPhone|iPad|iPod/i.test(ua)) platform = "iOS";

    var device = /Mobi|Android|iPhone|iPad/i.test(ua) ? "Mobile" : "Desktop";

    return { browser: browser, device: device, platform: platform };
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return Promise.reject(new Error("no service worker support"));
    return navigator.serviceWorker.register("/firebase-messaging-sw.js", { scope: "/" });
  }

  function enableNotifications() {
    if (!("Notification" in window)) return Promise.resolve(false);

    return Notification.requestPermission().then(function (permission) {
      if (permission !== "granted") return false;
      return registerAndSaveToken();
    }).catch(function (err) {
      console.error("JUWCS notifications: enable failed", err);
      return false;
    });
  }

  function registerAndSaveToken() {
    var fb = window.JUWCSFirebase;
    if (!fb || !fb.supported || !fb.messaging) return Promise.resolve(false);

    return registerServiceWorker().then(function (registration) {
      return import("https://www.gstatic.com/firebasejs/10.13.0/firebase-messaging.js").then(function (mod) {
        return mod.getToken(fb.messaging, {
          vapidKey: fb.vapidKey,
          serviceWorkerRegistration: registration,
        }).then(function (currentToken) {
          if (!currentToken) return false;
          localStorage.setItem(TOKEN_STORAGE_KEY, currentToken);
          var meta = deviceMeta();
          return postJSON("/notifications/register", {
            token: currentToken,
            browser: meta.browser,
            device: meta.device,
            platform: meta.platform,
            csrf_token: CSRF,
          }).then(function (resp) {
            if (!resp.ok) return false;
            updateBellFromServer();
            wireForegroundMessages(mod, fb.messaging);
            return true;
          });
        });
      });
    }).catch(function (err) {
      console.error("JUWCS notifications: token registration failed", err);
      return false;
    });
  }

  function silentlyVerifyExistingRegistration() {
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    var fb = window.JUWCSFirebase;
    if (!fb || !fb.supported) return;
    registerAndSaveToken();
  }

  var foregroundWired = false;
  function wireForegroundMessages(mod, messaging) {
    if (foregroundWired) return;
    foregroundWired = true;
    mod.onMessage(messaging, function (payload) {
      var data = payload.data || {};
      var title = data.title || (payload.notification && payload.notification.title) || "The Literary Society";
      var body = data.body || (payload.notification && payload.notification.body) || "";
      var link = data.link || "/";
      toast(title, body, link);
      updateBellFromServer();
    });
  }

  // ---------------------------------------------------------------------
  // Toasts (foreground notifications)
  // ---------------------------------------------------------------------

  function toast(title, body, link) {
    var container = document.getElementById("notif-toast-container");
    if (!container) return;

    var el = document.createElement("div");
    el.className = "notif-toast";
    el.innerHTML =
      '<div class="notif-toast-title"></div>' +
      '<div class="notif-toast-body"></div>';
    el.querySelector(".notif-toast-title").textContent = title;
    el.querySelector(".notif-toast-body").textContent = body;

    if (link) {
      el.classList.add("clickable");
      el.addEventListener("click", function () {
        window.location.href = link;
      });
    }

    container.appendChild(el);
    requestAnimationFrame(function () { el.classList.add("show"); });

    setTimeout(function () {
      el.classList.remove("show");
      setTimeout(function () { el.remove(); }, 300);
    }, 7000);
  }

  // ---------------------------------------------------------------------
  // Notification bell / center
  // ---------------------------------------------------------------------

  function renderBellItems(items) {
    var list = document.getElementById("notif-list");
    if (!list) return;

    if (!items.length) {
      list.innerHTML = '<div class="notif-empty">No notifications yet.<br>The Society will let you know when something happens.</div>';
      return;
    }

    list.innerHTML = "";
    items.forEach(function (n) {
      var item = document.createElement(n.link ? "a" : "div");
      item.className = "notif-item" + (n.is_read ? "" : " unread");
      if (n.link) item.href = n.link;
      item.dataset.id = n.id;

      var when = timeAgo(n.created_at);

      item.innerHTML =
        '<span class="notif-item-icon">' + n.icon + '</span>' +
        '<span class="notif-item-body">' +
          '<span class="notif-item-title"></span>' +
          '<span class="notif-item-message"></span>' +
          '<span class="notif-item-time"></span>' +
        '</span>';
      item.querySelector(".notif-item-title").textContent = n.title;
      item.querySelector(".notif-item-message").textContent = n.message;
      item.querySelector(".notif-item-time").textContent = when;

      item.addEventListener("click", function () {
        if (!n.is_read) postJSON("/notifications/" + n.id + "/read", {});
      });

      list.appendChild(item);
    });
  }

  function timeAgo(iso) {
    var seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (seconds < 60) return "just now";
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + " min ago";
    var hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + (hours === 1 ? " hour ago" : " hours ago");
    var days = Math.floor(hours / 24);
    if (days < 7) return days + (days === 1 ? " day ago" : " days ago");
    return new Date(iso).toLocaleDateString();
  }

  function updateBadge(count) {
    var badge = document.getElementById("notif-badge");
    if (!badge) return;
    if (count > 0) {
      badge.textContent = count > 99 ? "99+" : String(count);
      badge.classList.add("show");
    } else {
      badge.classList.remove("show");
    }
  }

  function updateBellFromServer() {
    apiFetch("/notifications/list?limit=20").then(function (r) {
      if (!r.ok) return null;
      return r.json();
    }).then(function (data) {
      if (!data) return;
      updateBadge(data.unread_count);
      renderBellItems(data.items);
    }).catch(function () {});
  }

  function wireBell() {
    var toggle = document.getElementById("notif-bell-toggle");
    var panel = document.getElementById("notif-panel");
    var markAll = document.getElementById("notif-mark-all-read");
    if (!toggle || !panel) return;

    function open() {
      panel.classList.add("open");
      toggle.setAttribute("aria-expanded", "true");
      updateBellFromServer();
    }
    function close() {
      panel.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    }

    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      panel.classList.contains("open") ? close() : open();
    });
    document.addEventListener("click", function (e) {
      if (panel.classList.contains("open") && !panel.contains(e.target) && e.target !== toggle) close();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });

    if (markAll) {
      markAll.addEventListener("click", function () {
        postJSON("/notifications/read-all", {}).then(updateBellFromServer);
      });
    }
  }

  // ---------------------------------------------------------------------
  // Logout: best-effort unregister this browser before navigating away, so
  // a different account logging in on the same machine never inherits a
  // stale, still-enabled push subscription.
  // ---------------------------------------------------------------------

  function wireLogoutUnregister() {
    var logoutLink = document.querySelector(".nav-logout");
    if (!logoutLink) return;

    logoutLink.addEventListener("click", function (e) {
      var storedToken = localStorage.getItem(TOKEN_STORAGE_KEY);
      if (!storedToken) return; // nothing to clean up, let the click proceed normally

      e.preventDefault();
      var href = logoutLink.href;
      localStorage.removeItem(TOKEN_STORAGE_KEY);

      postJSON("/notifications/unregister", { token: storedToken })
        .catch(function () {})
        .then(function () { window.location.href = href; });

      // Safety net in case the request hangs.
      setTimeout(function () { window.location.href = href; }, 800);
    });
  }

  // ---------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------

  document.addEventListener("DOMContentLoaded", function () {
    wirePromptButtons();
    wireBell();
    wireLogoutUnregister();
    updateBellFromServer();
  });

  document.addEventListener("juwcs:firebase-ready", function (e) {
    if (!e.detail.supported) return;

    if (Notification.permission === "granted") {
      silentlyVerifyExistingRegistration();
    } else if (shouldShowPrompt()) {
      showPrompt();
    }
  });

  // Service worker -> page messages (e.g. a notification click that
  // happened while this tab existed but wasn't focused).
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener("message", function (event) {
      if (event.data && event.data.type === "juwcs-notification-click") {
        updateBellFromServer();
      }
    });
  }
})();
