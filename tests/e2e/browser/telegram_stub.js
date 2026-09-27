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

  window.Telegram = {
    WebApp: {
      initData: init.initData,
      initDataUnsafe: init.initDataUnsafe,
      version: init.version || '8.0',
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
      safeAreaInset: { top: 0, bottom: 0, left: 0, right: 0 },
      contentSafeAreaInset: { top: 0, bottom: 0, left: 0, right: 0 },
      isClosingConfirmationEnabled: false,
      isVerticalSwipesEnabled: true,
      ready: function () { record.calls.push(['ready']); },
      expand: function () { record.calls.push(['expand']); },
      close: function () { record.calls.push(['close']); },
      setHeaderColor: function () {},
      setBackgroundColor: function () {},
      setBottomBarColor: function () {},
      enableClosingConfirmation: function () {},
      disableClosingConfirmation: function () {},
      enableVerticalSwipes: function () {},
      disableVerticalSwipes: function () { record.calls.push(['disableVerticalSwipes']); },
      onEvent: function () {},
      offEvent: function () {},
      isVersionAtLeast: function () { return true; },
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
