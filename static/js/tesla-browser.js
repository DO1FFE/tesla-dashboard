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

function hasNewTeslaDisplayFingerprint() {
    var ua = '';
    try {
        ua = navigator.userAgent || '';
    } catch (err) {
        ua = '';
    }
    if (!/Linux; Android 10; K/i.test(ua) || !/Mobile Safari\/537\.36/i.test(ua)) {
        return false;
    }

    var dpr = Number(window.devicePixelRatio || 1);
    var touchPoints = Number(navigator.maxTouchPoints || 0);
    var screenWidth = Number(window.screen && window.screen.width);
    var screenHeight = Number(window.screen && window.screen.height);
    if (
        !isFinite(dpr) || dpr < 1.45 || dpr > 1.65 ||
        touchPoints < 12 ||
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
    var ua = '';
    try {
        ua = navigator.userAgent || '';
    } catch (err) {
        ua = '';
    }
    return (
        /Tesla\//i.test(ua) ||
        /TeslaBrowser/i.test(ua) ||
        /QtCarBrowser/i.test(ua) ||
        hasNewTeslaDisplayFingerprint()
    );
}

function applyTeslaDesktopViewport() {
    if (
        !isTeslaBrowser() ||
        /^(0|false|no)$/i.test(getTeslaQueryParameter('tesla_desktop'))
    ) {
        return false;
    }

    var dpr = Number(window.devicePixelRatio || 1);
    var screenWidth = Number(window.screen && window.screen.width);
    if (!isFinite(dpr) || dpr <= 1.1 || !isFinite(screenWidth) || screenWidth <= 0) {
        return false;
    }

    var desktopWidth = Math.round(screenWidth * dpr);
    if (desktopWidth < 1000) {
        return false;
    }

    var viewport = document.querySelector('meta[name="viewport"]');
    if (!viewport) {
        return false;
    }
    var initialScale = Math.min(1, 1 / dpr);
    viewport.setAttribute(
        'content',
        'width=' + desktopWidth +
        ', initial-scale=' + initialScale.toFixed(4) +
        ', viewport-fit=cover'
    );

    var root = document.documentElement;
    root.classList.add('tesla-browser', 'tesla-desktop-viewport');
    root.setAttribute('data-tesla-device-pixel-ratio', dpr.toFixed(2));
    root.setAttribute('data-tesla-desktop-width', String(desktopWidth));
    return true;
}

window.isTeslaSelectForced = isTeslaSelectForced;
window.isTeslaBrowser = isTeslaBrowser;
window.hasNewTeslaDisplayFingerprint = hasNewTeslaDisplayFingerprint;
window.applyTeslaDesktopViewport = applyTeslaDesktopViewport;

applyTeslaDesktopViewport();
window.addEventListener('orientationchange', function() {
    window.setTimeout(applyTeslaDesktopViewport, 0);
});
