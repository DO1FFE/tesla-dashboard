// Tesla Browser Detection
function isTeslaBrowser() {
    var ua = '';
    try {
        ua = navigator.userAgent || '';
    } catch (err) {
        ua = '';
    }
    return /Tesla\//i.test(ua) || /QtCarBrowser/i.test(ua);
}

window.isTeslaBrowser = isTeslaBrowser;
