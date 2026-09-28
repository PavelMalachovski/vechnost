// Telegram's WebApp object, as the Mini App sees it inside Telegram.
//
// Served in place of https://telegram.org/js/telegram-web-app.js, one copy
// per phone, with that phone's signed initData substituted for __INIT__,
// along with what differs between phones: `platform` ("android" on the
// Android phone, "ios" on the iPhone) and the client's Bot API `version`.
// Everything the app calls is here; what it asks Telegram to *do* (open a
// link, share, ask for permission) is recorded on window.__tg so a test can
// read it back instead of Telegram acting on it.
(function () {
  var init = __INIT__;
  var record = { calls: [], links: [] };
  window.__tg = record;

  function button(name) {
    return {
      isVisible: false, isActive: true, text: '',
      show: function () { this.isVisible = true; record.calls.push([name, 'show']); return this; },
      hide: function () { this.isVisible = false; record.calls.push([name, 'hide']); return this; },
      onClick: function (cb) { this._cb = cb; return this; },
      offClick: function () { this._cb = null; return this; },
      setText: function (t) { this.text = t; return this; },
      setParams: function (p) { Object.assign(this, p || {}); return this; },
      enable: function () { this.isActive = true; return this; },
      disable: function () { this.isActive = false; return this; },
      showProgress: function () { return this; },
      hideProgress: function () { return this; }
    };
  }

  function ok(cb, value) { if (typeof cb === 'function') setTimeout(function () { cb(value); }, 0); }

  // Bot API versions compare part by part, as telegram-web-app.js compares
  // them: "7.10" is later than "7.9".
  var version = init.version || '8.0';
  function versionAtLeast(wanted) {
    var have = version.split('.'), want = String(wanted).split('.');
    for (var i = 0; i < Math.max(have.length, want.length); i++) {
      var a = parseInt(have[i] || '0', 10), b = parseInt(want[i] || '0', 10);
      if (a !== b) return a > b;
    }
    return true;
  }
  var HEX = /^#[0-9a-f]{6}$/i;
  // Telegram's script sets these on the page from the client's insets and
  // keeps them current; a phone that passes insets gets them the same way.
  var safeArea = init.safeAreaInset || { top: 0, bottom: 0, left: 0, right: 0 };
  var contentSafeArea = init.contentSafeAreaInset || { top: 0, bottom: 0, left: 0, right: 0 };
  ['top', 'bottom', 'left', 'right'].forEach(function (side) {
    var root = document.documentElement.style;
    root.setProperty('--tg-safe-area-inset-' + side, (safeArea[side] || 0) + 'px');
    root.setProperty('--tg-content-safe-area-inset-' + side, (contentSafeArea[side] || 0) + 'px');
  });

  window.Telegram = {
    WebApp: {
      initData: init.initData,
      initDataUnsafe: init.initDataUnsafe,
      version: version,
      platform: init.platform || 'ios',
      colorScheme: 'dark',
      themeParams: {
        bg_color: '#17212b', text_color: '#f5f5f5', hint_color: '#708499',
        link_color: '#6ab3f3', button_color: '#5288c1', button_text_color: '#ffffff',
        secondary_bg_color: '#232e3c', header_bg_color: '#17212b'
      },
      isExpanded: true,
      viewportHeight: window.innerHeight,
      viewportStableHeight: window.innerHeight,
      safeAreaInset: safeArea,
      contentSafeAreaInset: contentSafeArea,
      isClosingConfirmationEnabled: false,
      isVerticalSwipesEnabled: true,
      ready: function () { record.calls.push(['ready']); },
      expand: function () { record.calls.push(['expand']); },
      close: function () { record.calls.push(['close']); },
      // As telegram-web-app.js: before 6.1 no colours at all; before 6.9 the
      // header takes a theme key and throws on anything else; the bottom bar
      // from 7.10. What the app asked for is recorded.
      setHeaderColor: function (color) {
        if (!versionAtLeast('6.1')) return;
        if (!versionAtLeast('6.9') && color !== 'bg_color' && color !== 'secondary_bg_color') {
          throw Error('WebAppHeaderColorKeyInvalid');
        }
        if (versionAtLeast('6.9') && color !== 'bg_color' && color !== 'secondary_bg_color' && !HEX.test(color)) {
          throw Error('WebAppHeaderColorInvalid');
        }
        record.calls.push(['setHeaderColor', color]);
      },
      setBackgroundColor: function (color) {
        if (!versionAtLeast('6.1')) return;
        record.calls.push(['setBackgroundColor', color]);
      },
      setBottomBarColor: function (color) {
        if (!versionAtLeast('7.10')) return;
        record.calls.push(['setBottomBarColor', color]);
      },
      enableClosingConfirmation: function () {},
      disableClosingConfirmation: function () {},
      enableVerticalSwipes: function () {},
      disableVerticalSwipes: function () { record.calls.push(['disableVerticalSwipes']); },
      onEvent: function () {},
      offEvent: function () {},
      isVersionAtLeast: versionAtLeast,
      openLink: function (url) { record.links.push(url); },
      openTelegramLink: function (url) { record.links.push(url); },
      openInvoice: function (url, cb) { record.links.push(url); ok(cb, 'cancelled'); },
      shareToStory: function (url) { record.links.push(url); },
      showAlert: function (m, cb) { record.calls.push(['showAlert', m]); ok(cb); },
      showConfirm: function (m, cb) { record.calls.push(['showConfirm', m]); ok(cb, true); },
      showPopup: function (p, cb) { record.calls.push(['showPopup', p]); ok(cb, 'ok'); },
      requestWriteAccess: function (cb) { record.calls.push(['requestWriteAccess']); ok(cb, true); },
      sendData: function () {},
      switchInlineQuery: function () {},
      BackButton: button('BackButton'),
      MainButton: button('MainButton'),
      SecondaryButton: button('SecondaryButton'),
      SettingsButton: button('SettingsButton'),
      HapticFeedback: {
        impactOccurred: function () {},
        notificationOccurred: function () {},
        selectionChanged: function () {}
      },
      CloudStorage: {
        setItem: function (k, v, cb) { ok(cb, true); },
        getItem: function (k, cb) { if (cb) setTimeout(function () { cb(null, ''); }, 0); },
        getItems: function (k, cb) { if (cb) setTimeout(function () { cb(null, {}); }, 0); },
        removeItem: function (k, cb) { ok(cb, true); },
        getKeys: function (cb) { if (cb) setTimeout(function () { cb(null, []); }, 0); }
      }
    }
  };
})();
