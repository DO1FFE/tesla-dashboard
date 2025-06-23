var map = L.map('map').setView([51.4556, 7.0116], 13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
}).addTo(map);

var MILES_TO_KM = 1.60934;

// Elements for playback controls
var playBtn = document.getElementById('play-btn');
var stopBtn = document.getElementById('stop-btn');
var speedSel = document.getElementById('speed-select');
var slider = document.getElementById('point-slider');
var playTimeout = null;
var speed = 1;
var marker = null;

function updateInfo(idx) {
    if (!Array.isArray(tripPath) || !tripPath.length) {
        return;
    }
    var point = tripPath[idx];
    var text = [];
    if (point[4]) {
        var date = new Date(point[4]);
        text.push(date.toLocaleString());
    }
    if (point[2] !== null && point[2] !== undefined && point[2] !== '') {
        var kmh = Math.round(point[2] * MILES_TO_KM);
        text.push('Geschwindigkeit: ' + kmh + ' km/h');
    }
    if (point[3] !== null && point[3] !== undefined && point[3] !== '') {
        text.push('Power: ' + point[3] + ' kW');
    }
    document.getElementById('point-info').textContent = text.join(' | ');
}

function updateMarker(idx, center) {
    if (!marker || !Array.isArray(tripPath) || !tripPath.length) {
        return;
    }
    var point = tripPath[idx];
    marker.setLatLng([point[0], point[1]]);
    var angle = 0;
    if (idx > 0) {
        angle = bearing(tripPath[idx - 1], point);
    }
    marker.setRotationAngle(angle);
    updateInfo(idx);
    if (center) {
        map.setView(marker.getLatLng(), map.getZoom());
    }
}

function bearing(p1, p2) {
    var lat1 = p1[0] * Math.PI / 180;
    var lon1 = p1[1] * Math.PI / 180;
    var lat2 = p2[0] * Math.PI / 180;
    var lon2 = p2[1] * Math.PI / 180;
    var y = Math.sin(lon2 - lon1) * Math.cos(lat2);
    var x = Math.cos(lat1) * Math.sin(lat2) -
            Math.sin(lat1) * Math.cos(lat2) * Math.cos(lon2 - lon1);
    var brng = Math.atan2(y, x) * 180 / Math.PI;
    return (brng + 360) % 360;
}

if (Array.isArray(tripPath) && tripPath.length) {
    var coords = tripPath.map(function(p) { return [p[0], p[1]]; });
    var poly = L.polyline(coords, {color: 'blue'}).addTo(map);
    map.fitBounds(poly.getBounds());

    var arrowIcon = L.divIcon({
        html: '<svg width="30" height="30" viewBox="0 0 30 30"><polygon points="15,0 30,30 15,22 0,30" /></svg>',
        className: 'arrow-icon',
        iconSize: [30, 30],
        iconAnchor: [15, 15]
    });

    marker = L.marker(coords[0], {
        icon: arrowIcon,
        rotationAngle: tripHeading,
        rotationOrigin: 'center center'
    }).addTo(map);

    slider.max = tripPath.length - 1;
    slider.value = 0;

    var originalZoom = null;
    var zoomTimeout = null;

    slider.addEventListener('input', function() {
        var idx = parseInt(this.value, 10);
        updateMarker(idx, false);
        var latlng = marker.getLatLng();

        if (originalZoom === null) {
            originalZoom = map.getZoom();
        }
        var maxZoom = typeof map.getMaxZoom === 'function' ? map.getMaxZoom() : 18;
        map.setView(latlng, maxZoom);

        if (zoomTimeout) {
            clearTimeout(zoomTimeout);
        }
        zoomTimeout = setTimeout(function() {
            if (originalZoom !== null) {
                map.setZoom(originalZoom);
                originalZoom = null;
            }
        }, 3000);
    });

    updateMarker(0, true);
}

function stopPlayback() {
    if (playTimeout) {
        clearTimeout(playTimeout);
        playTimeout = null;
    }
}

function stepPlayback(idx) {
    if (!Array.isArray(tripPath) || !tripPath.length) {
        return;
    }
    if (idx >= tripPath.length) {
        stopPlayback();
        return;
    }
    slider.value = idx;
    updateMarker(idx, true);
    if (idx < tripPath.length - 1) {
        var cur = tripPath[idx][4];
        var nxt = tripPath[idx + 1][4];
        var diff = nxt - cur;
        if (!diff || diff < 0) {
            diff = 1000;
        }
        diff = diff / speed;
        playTimeout = setTimeout(function() { stepPlayback(idx + 1); }, diff);
    }
}

if (playBtn) {
    playBtn.addEventListener('click', function() {
        speed = parseFloat(speedSel.value) || 1;
        var startIdx = parseInt(slider.value, 10);
        if (startIdx >= tripPath.length - 1) {
            startIdx = 0;
            slider.value = 0;
            updateMarker(0, true);
        }
        if (!playTimeout) {
            stepPlayback(startIdx);
        }
    });
}

if (stopBtn) {
    stopBtn.addEventListener('click', function() {
        stopPlayback();
    });
}
