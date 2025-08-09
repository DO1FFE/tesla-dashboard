function copyUrl() {
    var url = window.location.href;
    navigator.clipboard.writeText(url);
}

document.addEventListener('DOMContentLoaded', function () {
    var btn = document.getElementById('share-button');
    if (btn) {
        btn.addEventListener('click', copyUrl);
    }
});
