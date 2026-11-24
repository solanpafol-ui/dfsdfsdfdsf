// document_start, isolated world: only job is to get main.js into the page.
(() => {
    const el = document.createElement('script');
    el.src = chrome.runtime.getURL('main.js');
    el.onload = () => el.remove();
    (document.head || document.documentElement).appendChild(el);
})();