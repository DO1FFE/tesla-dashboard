// Tesla Browser Detection
// Override options: set window.FORCE_TESLA_SELECT = true, add
// data-force-tesla-select on <body>, or use ?force_tesla_select=1 to force-enable.
function isTeslaSelectForced() {
    if (window.FORCE_TESLA_SELECT === true) {
        return true;
    }
    if (document.body && document.body.hasAttribute('data-force-tesla-select')) {
        return true;
    }
    var search = '';
    try {
        search = window.location && window.location.search ? window.location.search : '';
    } catch (err) {
        search = '';
    }
    if (search) {
        var params = new URLSearchParams(search);
        var value = params.get('force_tesla_select');
        if (value && /^(1|true|yes)$/i.test(value)) {
            return true;
        }
    }
    return false;
}

function hasTeslaUaData() {
    if (!navigator.userAgentData || !Array.isArray(navigator.userAgentData.brands)) {
        return false;
    }
    return navigator.userAgentData.brands.some(function(brand) {
        return brand && typeof brand.brand === 'string' && /tesla/i.test(brand.brand);
    });
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
    return /Tesla\//i.test(ua) || /TeslaBrowser/i.test(ua) || /QtCarBrowser/i.test(ua);
}

window.isTeslaSelectForced = isTeslaSelectForced;
window.isTeslaBrowser = isTeslaBrowser;
