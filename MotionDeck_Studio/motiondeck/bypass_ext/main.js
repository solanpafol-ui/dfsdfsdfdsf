(() => {
    const seed = (() => {
        let v = 0;
        try { v = Number(sessionStorage.getItem('md_fp') || 0); } catch (e) {}
        if (!v) {
            v = Math.floor(Math.random() * 0xffffff) + 1;
            try { sessionStorage.setItem('md_fp', String(v)); } catch (e) {}
        }
        return v;
    })();

    const define = (obj, key, value) => {
        try { Object.defineProperty(obj, key, { get: () => value, configurable: true }); } catch (e) {}
    };

    // --- automation tell
    define(navigator, 'webdriver', undefined);

    // --- locale / platform shape
    define(navigator, 'languages', ['fr-FR', 'fr', 'en-US', 'en']);
    define(navigator, 'hardwareConcurrency', 8);
    define(navigator, 'deviceMemory', 8);
    define(navigator, 'plugins', [1, 2, 3, 4, 5].map(() => ({ name: 'pdf' })));

    // --- canvas: flip a few LSBs, deterministic per session
    const noise = (data) => {
        for (let i = 0; i < 24 && i * 7 + 3 < data.length; i++) {
            const at = (seed + i * 977) % data.length;
            data[at] = (data[at] & 0xfe) | ((seed >> (i % 8)) & 1);
        }
        return data;
    };
    const gid = CanvasRenderingContext2D.prototype.getImageData;
    CanvasRenderingContext2D.prototype.getImageData = function () {
        const out = gid.apply(this, arguments);
        try { noise(out.data); } catch (e) {}
        return out;
    };
    const tdu = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function () {
        try {
            const ctx = this.getContext('2d');
            if (ctx) {
                const d = gid.call(ctx, 0, 0, this.width, this.height);
                noise(d.data);
                ctx.putImageData(d, 0, 0);
            }
        } catch (e) {}
        return tdu.apply(this, arguments);
    };

    // --- webgl renderer strings
    const VENDOR = 0x9245, RENDERER = 0x9246;
    for (const proto of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
        if (!proto) continue;
        const gp = proto.prototype.getParameter;
        proto.prototype.getParameter = function (p) {
            if (p === VENDOR) return 'Google Inc. (NVIDIA)';
            if (p === RENDERER) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060, Direct3D11)';
            return gp.apply(this, arguments);
        };
    }

    // --- region stamp, before the app's own boot reads it
    try {
        sessionStorage.setItem('country_code', 'FR');
        sessionStorage.setItem('region', 'EU');
    } catch (e) {}
})();