// Tesla-Browser-Erkennung und Wiederherstellung der Desktop-Skalierung.
// Override options: set window.FORCE_TESLA_SELECT = true, add
// data-force-tesla-select on <body>, or use ?force_tesla_select=1 to force-enable.
function getTeslaQueryParameter(name) {
    var search = '';
    try {
        search = window.location && window.location.search ? window.location.search : '';
    } catch (err) {
        search = '';
    }
    if (!search) {
        return '';
    }
    try {
        return new URLSearchParams(search).get(name) || '';
    } catch (err) {
        return '';
    }
}

function isTeslaQueryEnabled(name) {
    return /^(1|true|yes)$/i.test(getTeslaQueryParameter(name));
}

function isTeslaSelectForced() {
    if (window.FORCE_TESLA_SELECT === true) {
        return true;
    }
    if (document.body && document.body.hasAttribute('data-force-tesla-select')) {
        return true;
    }
    return isTeslaQueryEnabled('force_tesla_select');
}

function hasTeslaUaData() {
    if (!navigator.userAgentData || !Array.isArray(navigator.userAgentData.brands)) {
        return false;
    }
    return navigator.userAgentData.brands.some(function(brand) {
        return brand && typeof brand.brand === 'string' && /tesla/i.test(brand.brand);
    });
}

function getTeslaBrowserUserAgent() {
    try {
        return navigator.userAgent || '';
    } catch (err) {
        return '';
    }
}

function hasUpdatedTeslaLinuxUserAgent(ua) {
    return (
        /\(X11; Linux x86_64\)/i.test(ua) &&
        /Chrome\/(?:14[8-9]|1[5-9][0-9])\.0\.0\.0/i.test(ua) &&
        /Safari\/537\.36/i.test(ua)
    );
}

function hasReducedTeslaAndroidUserAgent(ua) {
    return (
        /Linux; Android 10; K/i.test(ua) &&
        /Mobile Safari\/537\.36/i.test(ua)
    );
}

function hasNewTeslaDisplayFingerprint() {
    var ua = getTeslaBrowserUserAgent();
    if (
        !hasUpdatedTeslaLinuxUserAgent(ua) &&
        !hasReducedTeslaAndroidUserAgent(ua)
    ) {
        return false;
    }

    var dpr = Number(window.devicePixelRatio || 1);
    var touchPoints = Number(navigator.maxTouchPoints || 0);
    var screenWidth = Number(window.screen && window.screen.width);
    var screenHeight = Number(window.screen && window.screen.height);
    if (
        !isFinite(dpr) || dpr < 1.30 || dpr > 1.65 ||
        touchPoints < 1 ||
        !isFinite(screenWidth) || !isFinite(screenHeight) ||
        screenWidth <= 0 || screenHeight <= 0
    ) {
        return false;
    }

    var physicalShortSide = Math.min(screenWidth, screenHeight) * dpr;
    var physicalLongSide = Math.max(screenWidth, screenHeight) * dpr;
    return (
        physicalShortSide >= 1120 && physicalShortSide <= 1300 &&
        physicalLongSide >= 1840 && physicalLongSide <= 2020
    );
}

function isTeslaBrowser() {
    if (isTeslaSelectForced()) {
        return true;
    }
    if (hasTeslaUaData()) {
        return true;
    }
    var ua = getTeslaBrowserUserAgent();
    return (
        /Tesla\//i.test(ua) ||
        /TeslaBrowser/i.test(ua) ||
        /QtCarBrowser/i.test(ua) ||
        hasNewTeslaDisplayFingerprint()
    );
}

function setTeslaDesktopScale(scale) {
    var applyScale = function() {
        if (!document.body) {
            return;
        }
        document.body.style.zoom = scale.toFixed(6);
    };

    if (document.body) {
        applyScale();
        return;
    }
    document.addEventListener('DOMContentLoaded', applyScale, {once: true});
}

function applyTeslaDesktopViewport() {
    if (
        !isTeslaBrowser() ||
        /^(0|false|no)$/i.test(getTeslaQueryParameter('tesla_desktop'))
    ) {
        return false;
    }

    var dpr = Number(window.devicePixelRatio || 1);
    var innerWidth = Number(window.innerWidth || 0);
    if (!isFinite(dpr) || dpr <= 1.1 || !isFinite(innerWidth) || innerWidth <= 0) {
        return false;
    }

    var desktopWidth = Math.round(innerWidth * dpr);
    if (desktopWidth < 1000) {
        return false;
    }

    var viewport = document.querySelector('meta[name="viewport"]');
    if (!viewport) {
        return false;
    }
    var desktopScale = Math.min(1, 1 / dpr);
    viewport.setAttribute(
        'content',
        'width=device-width, initial-scale=1, viewport-fit=cover'
    );

    var root = document.documentElement;
    root.classList.add('tesla-browser', 'tesla-desktop-viewport');
    root.setAttribute('data-tesla-device-pixel-ratio', dpr.toFixed(2));
    root.setAttribute('data-tesla-desktop-width', String(desktopWidth));
    root.setAttribute('data-tesla-desktop-scale', desktopScale.toFixed(4));
    setTeslaDesktopScale(desktopScale);
    return true;
}

function isPotentialUpdatedTeslaBrowser() {
    var ua = getTeslaBrowserUserAgent();
    return (
        /Tesla\/|TeslaBrowser|QtCarBrowser/i.test(ua) ||
        hasTeslaUaData() ||
        (
            Number(navigator.maxTouchPoints || 0) > 0 &&
            (
                hasUpdatedTeslaLinuxUserAgent(ua) ||
                hasReducedTeslaAndroidUserAgent(ua)
            )
        )
    );
}

function sendTeslaBrowserDiagnostics(viewportApplied) {
    if (!isPotentialUpdatedTeslaBrowser() || typeof window.fetch !== 'function') {
        return;
    }

    var send = function() {
        var visualViewport = window.visualViewport;
        var body = document.body;
        var payload = {
            erkannt: isTeslaBrowser(),
            desktop_ansicht_aktiv: Boolean(viewportApplied),
            device_pixel_ratio: Number(window.devicePixelRatio || 1),
            touchpunkte: Number(navigator.maxTouchPoints || 0),
            bildschirm: {
                breite: Number(window.screen && window.screen.width) || 0,
                hoehe: Number(window.screen && window.screen.height) || 0
            },
            fenster: {
                breite: Number(window.innerWidth || 0),
                hoehe: Number(window.innerHeight || 0),
                aussen_breite: Number(window.outerWidth || 0),
                aussen_hoehe: Number(window.outerHeight || 0)
            },
            sichtbereich: visualViewport ? {
                breite: Number(visualViewport.width || 0),
                hoehe: Number(visualViewport.height || 0),
                skalierung: Number(visualViewport.scale || 1)
            } : null,
            dokument: body ? {
                breite: Number(body.offsetWidth || 0),
                hoehe: Number(body.offsetHeight || 0),
                css_zoom: String(body.style.zoom || '')
            } : null
        };

        window.fetch('/api/browser-diagnostics', {
            method: 'POST',
            credentials: 'same-origin',
            keepalive: true,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        }).catch(function() {});
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            window.setTimeout(send, 0);
        }, {once: true});
        return;
    }
    window.setTimeout(send, 0);
}

window.isTeslaSelectForced = isTeslaSelectForced;
window.isTeslaBrowser = isTeslaBrowser;
window.hasNewTeslaDisplayFingerprint = hasNewTeslaDisplayFingerprint;
window.applyTeslaDesktopViewport = applyTeslaDesktopViewport;

var teslaDesktopViewportApplied = applyTeslaDesktopViewport();
sendTeslaBrowserDiagnostics(teslaDesktopViewportApplied);
window.addEventListener('orientationchange', function() {
    window.setTimeout(applyTeslaDesktopViewport, 0);
});
