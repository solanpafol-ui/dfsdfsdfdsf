const STAMPS = [['country', 'FR'], ['region', 'EU'], ['country_code', 'FR']];

async function stamp() {
    for (const [name, value] of STAMPS) {
        try {
            await chrome.cookies.set({
                url: 'https://dola.com/',
                domain: '.dola.com',
                path: '/',
                name,
                value,
                expirationDate: Date.now() / 1000 + 31536000,
                sameSite: 'lax'
            });
        } catch (e) {}
    }
}

chrome.runtime.onInstalled.addListener(stamp);
chrome.runtime.onStartup.addListener(stamp);