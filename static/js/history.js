var DEFAULT_ZOOM = 18;

var map = L.map('map', { attributionControl: false }).setView([51.4556, 7.0116], DEFAULT_ZOOM);
erstelleAttributionsKontrolle(map);
var kartenAnsichtOptionen = document.querySelectorAll('input[name="map-view"]');
var kartenAnsichtMenu = document.getElementById('map-view-menu');
var layerKonfiguration = erstelleKartenLayerKonfiguration(map, {
    labelsPaneName: 'labels',
    labelsPaneZIndex: 650,
    labelsPanePointerEvents: 'none'
});
var kartenAnsichtLayer = layerKonfiguration.kartenAnsichtLayer;
var aktiveKartenAnsicht = layerKonfiguration.aktiveKartenAnsicht;

aktiveKartenAnsicht = bindeKartenAnsichtOptionen(
    map,
    kartenAnsichtLayer,
    kartenAnsichtOptionen,
    aktiveKartenAnsicht
);

if (kartenAnsichtMenu && L && L.DomEvent) {
    L.DomEvent.disableClickPropagation(kartenAnsichtMenu);
    L.DomEvent.disableScrollPropagation(kartenAnsichtMenu);
    if (kartenAnsichtOptionen.length) {
        var deaktiviereZiehen = function(event) {
            if (event) {
                event.stopPropagation();
            }
            if (map.dragging) {
                map.dragging.disable();
            }
        };
        var aktiviereZiehen = function() {
            if (map.dragging) {
                map.dragging.enable();
            }
        };
        for (var i = 0; i < kartenAnsichtOptionen.length; i++) {
            kartenAnsichtOptionen[i].addEventListener('focus', deaktiviereZiehen);
            kartenAnsichtOptionen[i].addEventListener('blur', aktiviereZiehen);
            kartenAnsichtOptionen[i].addEventListener('pointerdown', deaktiviereZiehen);
            kartenAnsichtOptionen[i].addEventListener('touchstart', deaktiviereZiehen);
        }
    }
}

var MILES_TO_KM = 1.60934;

function normalizeShiftState(shift) {
    if (shift === null || shift === undefined) {
        return null;
    }
    var value;
    if (typeof shift === 'string') {
        value = shift.trim();
    } else {
        try {
            value = String(shift).trim();
        } catch (err) {
            return null;
        }
    }
    if (!value) {
        return null;
    }
    var upper = value.toUpperCase();
    if (upper === 'PARK') {
        return 'P';
    }
    if (upper === 'REVERSE') {
        return 'R';
    }
    return upper;
}

function adjustHeadingForReverse(heading, shift) {
    var numeric = Number(heading);
    if (!isFinite(numeric)) {
        return heading;
    }
    var normalizedHeading = ((numeric % 360) + 360) % 360;
    return normalizedHeading;
}

function computeZoomForSpeed(speedKmh) {
    var zoom = DEFAULT_ZOOM;
    if (speedKmh != null && !isNaN(speedKmh)) {
        var kmh = Math.round(Number(speedKmh));
        if (kmh <= 20) {
            zoom = 18;
        } else if (kmh <= 30) {
            zoom = 17;
        } else if (kmh <= 50) {
            zoom = 16;
        } else if (kmh <= 70) {
            zoom = 15;
        } else if (kmh <= 100) {
            zoom = 14;
        } else {
            zoom = 13;
        }
    }
    return zoom;
}

// Elements for playback controls
var playBtn = document.getElementById('play-btn');
var stopBtn = document.getElementById('stop-btn');
var speedSel = document.getElementById('speed-select');
var slider = document.getElementById('point-slider');
var playTimeout = null;
var speed = 1;
var marker = null;

if (speedSel) {
    speedSel.addEventListener('change', function() {
        speed = parseFloat(speedSel.value) || 1;
    });
}

function updateInfo(idx) {
    if (!Array.isArray(tripPath) || !tripPath.length) {
        return;
    }
    var point = tripPath[idx];
    var text = [];
    if (point[4]) {
        var date = new Date(point[4]);
        text.push(date.toLocaleString('de-DE', { timeZone: 'Europe/Berlin' }));
    }
    if (point[2] !== null && point[2] !== undefined && point[2] !== '') {
        var kmh = Math.round(point[2] * MILES_TO_KM);
        text.push('Geschwindigkeit: ' + kmh + ' km/h');
    }
    if (point[3] !== null && point[3] !== undefined && point[3] !== '') {
        text.push('Power: ' + point[3] + ' kW');
    }
    if (point[6] !== null && point[6] !== undefined && point[6] !== '') {
        text.push('Gang: ' + point[6]);
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
    if (point[5] !== null && point[5] !== undefined && point[5] !== '') {
        angle = point[5];
    } else if (idx > 0) {
        angle = bearing(tripPath[idx - 1], point);
    }
    var gear = point.length >= 7 ? point[6] : null;
    angle = adjustHeadingForReverse(angle, gear);
    marker.setRotationAngle(angle);
    updateInfo(idx);
    if (center) {
        var speedVal = point[2];
        var speedKmh = 0;
        if (speedVal !== null && speedVal !== undefined && speedVal !== '') {
            speedKmh = Number(speedVal) * MILES_TO_KM;
        }
        var zoom = computeZoomForSpeed(speedKmh);
        map.setView(marker.getLatLng(), zoom);
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
        if (playTimeout) {
            stopPlayback(false);
            if (playBtn) {
                playBtn.textContent = 'Play';
            }
        }
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

function stopPlayback(reset) {
    if (playTimeout) {
        clearTimeout(playTimeout);
        playTimeout = null;
    }
    if (reset && Array.isArray(tripPath) && tripPath.length) {
        slider.value = 0;
        updateMarker(0, true);
    }
}

function stepPlayback(idx) {
    if (!Array.isArray(tripPath) || !tripPath.length) {
        return;
    }
    if (idx >= tripPath.length) {
        stopPlayback(false);
        if (playBtn) {
            playBtn.textContent = 'Play';
        }
        return;
    }
    slider.value = idx;
    updateMarker(idx, true);
    if (idx < tripPath.length - 1) {
        var diff = 1000 / speed;
        var t1 = tripPath[idx][4];
        var t2 = tripPath[idx + 1][4];
        if (t1 && t2 && t2 > t1) {
            diff = (t2 - t1) / speed;
        }
        playTimeout = setTimeout(function() { stepPlayback(idx + 1); }, diff);
    }
}

if (playBtn) {
    playBtn.addEventListener('click', function() {
        if (playTimeout) {
            stopPlayback(false);
            playBtn.textContent = 'Play';
            return;
        }

        speed = parseFloat(speedSel.value) || 1;
        var startIdx = parseInt(slider.value, 10);
        if (startIdx >= tripPath.length - 1) {
            startIdx = 0;
            slider.value = 0;
            updateMarker(0, true);
        }
        stepPlayback(startIdx);
        playBtn.textContent = 'Pause';
    });
}

if (stopBtn) {
    stopBtn.addEventListener('click', function() {
        stopPlayback(true);
        if (playBtn) {
            playBtn.textContent = 'Play';
        }
    });
}
