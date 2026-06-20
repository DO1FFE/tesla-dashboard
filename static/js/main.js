var currentVehicle = null;
var APP_VERSION = window.APP_VERSION || null;
var MILES_TO_KM = 1.60934;
var announcementRaw = '';
var announcementList = [];
var announcementIndex = 0;
var announcementTimer = null;
var lastConfigJSON = null;
var lastApiInterval = null;
var lastApiIntervalIdle = null;
var statusAbfrageTimer = null;
var parkStartTime = null;
var currentGear = null;
var THERMOMETER_IDS = ['thermometer-inside', 'thermometer-outside', 'thermometer-battery'];
var PARK_GRACE_MS = 5 * 60 * 1000;
var PARKED_MAP_JITTER_METERS = 25;
var ROUTENPUNKT_MAX_SPRUNG_METER = 500 * 1000;
var NAVIGATIONS_ZIEL_NULL_EPSILON = 1e-6;
var STREAM_WIEDERVERBINDUNG_MS = 250;
var streamWiederverbindungsTimer = null;
// Default view if no coordinates are available
var DEFAULT_POS = [51.4556, 7.0116];
var DEFAULT_ZOOM = 18;
var superchargerMarkers = [];
var lastSuperchargerData = null;
var letzteKartenPosition = null;
var letzteKartenRichtung = null;
var letzteZielSignatur = null;
var letztePfadSignatur = null;
var privacyCircle = null;
var letzterReifendruckStatus = {};
var REIFENDRUCK_CACHE_FELDER = [
    'tpms_pressure_fl',
    'tpms_pressure_fr',
    'tpms_pressure_rl',
    'tpms_pressure_rr',
    'tpms_last_seen_pressure_time_fl',
    'tpms_last_seen_pressure_time_fr',
    'tpms_last_seen_pressure_time_rl',
    'tpms_last_seen_pressure_time_rr',
    'tpms_rcp_front_value',
    'tpms_rcp_rear_value',
    'tpms_soft_warning_fl',
    'tpms_soft_warning_fr',
    'tpms_soft_warning_rl',
    'tpms_soft_warning_rr',
    'tpms_hard_warning_fl',
    'tpms_hard_warning_fr',
    'tpms_hard_warning_rl',
    'tpms_hard_warning_rr'
];

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
// Initialize the map roughly centered on Essen with a high zoom until
// coordinates from the API are received.
var map = L.map('map', { attributionControl: false }).setView(DEFAULT_POS, DEFAULT_ZOOM);
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
// Adjust map when the viewport size changes (e.g., on mobile rotation)
$(window).on('resize', function() {
    map.invalidateSize();
});
// Keep marker centered if the map container size changes (e.g., side panels)
var mapEl = document.getElementById('map');
if (window.ResizeObserver && mapEl) {
    var mapResizeObserver = new ResizeObserver(function() {
        map.invalidateSize();
        if (typeof marker !== 'undefined' && marker.getLatLng) {
            zoomSetByApp = true;
            map.setView(marker.getLatLng(), map.getZoom(), {animate: false});
        }
    });
    mapResizeObserver.observe(mapEl);
}
// Track when the user last changed the zoom level
var lastUserZoom = 0;
var USER_ZOOM_PRIORITY_MS = 30 * 1000;
var zoomSetByApp = false;
var $zoomLevel = $('#zoom-level');
var $privacyMapNotice = $('#privacy-map-notice');
function updateZoomDisplay() {
    if ($zoomLevel.length) {
        $zoomLevel.text('Zoom: ' + map.getZoom());
    }
}
updateZoomDisplay();

function formatierePrivatsphaereRadius(radius) {
    radius = Number(radius);
    if (!isFinite(radius) || radius <= 0) {
        return '';
    }
    if (radius >= 10000) {
        return Math.round(radius / 1000) + ' km';
    }
    if (radius >= 1000) {
        return (Math.round(radius / 100) / 10).toFixed(1) + ' km';
    }
    return Math.round(radius) + ' m';
}

function kartenPrivatmodusAktiv() {
    return !!(CONFIG && CONFIG['privacy-mode']);
}

function kartenPrivatmodusGenauigkeit() {
    var precision = CONFIG ? Number(CONFIG.privacy_precision) : 2;
    if (!isFinite(precision)) {
        precision = 2;
    }
    return Math.min(4, Math.max(0, Math.round(precision)));
}

function rundeKartenKoordinate(value) {
    var numeric = Number(value);
    if (!isFinite(numeric)) {
        return numeric;
    }
    var precision = kartenPrivatmodusGenauigkeit();
    var factor = Math.pow(10, precision);
    return Math.round(numeric * factor) / factor;
}

function berechnePrivatsphaereRadius(latitude) {
    var precision = kartenPrivatmodusGenauigkeit();
    var halfDegree = 0.5 * Math.pow(10, -precision);
    var lat = Number(latitude);
    var latRad = isFinite(lat) ? lat * Math.PI / 180 : 0;
    var latMeter = 111320 * halfDegree;
    var lonMeter = 111320 * Math.abs(Math.cos(latRad)) * halfDegree;
    return Math.max(1, Math.ceil(Math.sqrt(latMeter * latMeter + lonMeter * lonMeter)));
}

function privatisiereKartenPunkt(lat, lng) {
    if (!kartenPrivatmodusAktiv()) {
        return {lat: Number(lat), lng: Number(lng), radius: 0, active: false};
    }
    var privatLat = rundeKartenKoordinate(lat);
    var privatLng = rundeKartenKoordinate(lng);
    return {
        lat: privatLat,
        lng: privatLng,
        radius: isFinite(privatLat) && isFinite(privatLng) ? berechnePrivatsphaereRadius(privatLat) : 0,
        active: true
    };
}

function privatisiereKartenPunkte(points) {
    if (!kartenPrivatmodusAktiv() || !Array.isArray(points)) {
        return points;
    }
    return points.map(function(point) {
        if (!Array.isArray(point) || point.length < 2) {
            return point;
        }
        var kopie = point.slice();
        kopie[0] = rundeKartenKoordinate(kopie[0]);
        kopie[1] = rundeKartenKoordinate(kopie[1]);
        return kopie;
    });
}

function entfernePrivatsphaereKreis() {
    if (!privacyCircle) {
        return;
    }
    try {
        map.removeLayer(privacyCircle);
    } catch (err) {}
    privacyCircle = null;
}

function updatePrivatsphaereOverlay(active, lat, lng, radius) {
    var hatPosition = isFinite(lat) && isFinite(lng);
    radius = Number(radius);
    if (!isFinite(radius) || radius <= 0) {
        radius = 0;
    }

    if (!active) {
        entfernePrivatsphaereKreis();
        if ($privacyMapNotice.length) {
            $privacyMapNotice.prop('hidden', true).text('');
        }
        return;
    }

    if ($privacyMapNotice.length) {
        var text = 'Privatsphäre-Modus aktiv';
        var radiusText = formatierePrivatsphaereRadius(radius);
        if (radiusText) {
            text += ' · Bereich ca. ' + radiusText;
        }
        $privacyMapNotice.text(text).prop('hidden', false);
    }

    if (!hatPosition || radius <= 0) {
        entfernePrivatsphaereKreis();
        return;
    }

    if (!privacyCircle) {
        privacyCircle = L.circle([lat, lng], {
            radius: radius,
            color: '#ff9800',
            weight: 2,
            opacity: 0.95,
            fillColor: '#ff9800',
            fillOpacity: 0.14,
            dashArray: '6 6',
            interactive: false
        }).addTo(map);
        return;
    }
    privacyCircle.setLatLng([lat, lng]);
    privacyCircle.setRadius(radius);
}

function zoomFuerPrivatsphaereRadius(radius, fallbackZoom) {
    radius = Number(radius);
    if (!isFinite(radius) || radius <= 0) {
        return fallbackZoom;
    }
    if (radius >= 30000) return Math.min(fallbackZoom, 8);
    if (radius >= 10000) return Math.min(fallbackZoom, 10);
    if (radius >= 5000) return Math.min(fallbackZoom, 11);
    if (radius >= 2000) return Math.min(fallbackZoom, 12);
    if (radius >= 1000) return Math.min(fallbackZoom, 13);
    if (radius >= 500) return Math.min(fallbackZoom, 14);
    if (radius >= 250) return Math.min(fallbackZoom, 15);
    if (radius >= 100) return Math.min(fallbackZoom, 16);
    if (radius >= 30) return Math.min(fallbackZoom, 17);
    return fallbackZoom;
}

function istGueltigeKartenKoordinate(lat, lng) {
    if (lat === null || lat === undefined || lng === null || lng === undefined) {
        return false;
    }
    if (lat === '' || lng === '') {
        return false;
    }
    lat = Number(lat);
    lng = Number(lng);
    return isFinite(lat) &&
        isFinite(lng) &&
        lat >= -90 &&
        lat <= 90 &&
        lng >= -180 &&
        lng <= 180;
}

function istPlausibleNavigationsZielKoordinate(lat, lng) {
    return istGueltigeKartenKoordinate(lat, lng) &&
        Math.abs(Number(lat)) >= NAVIGATIONS_ZIEL_NULL_EPSILON &&
        Math.abs(Number(lng)) >= NAVIGATIONS_ZIEL_NULL_EPSILON;
}

function dekodierePolyline(polyline, praezision) {
    if (typeof polyline !== 'string' || !polyline) {
        return [];
    }
    var faktor = Math.pow(10, praezision || 5);
    var index = 0;
    var lat = 0;
    var lng = 0;
    var punkte = [];

    function dekodiereWert() {
        var ergebnis = 0;
        var verschiebung = 0;
        var byteWert = 0;
        do {
            if (index >= polyline.length) {
                return null;
            }
            byteWert = polyline.charCodeAt(index++) - 63;
            ergebnis |= (byteWert & 0x1f) << verschiebung;
            verschiebung += 5;
        } while (byteWert >= 0x20);
        return ergebnis & 1 ? ~(ergebnis >> 1) : ergebnis >> 1;
    }

    while (index < polyline.length) {
        var deltaLat = dekodiereWert();
        var deltaLng = dekodiereWert();
        if (deltaLat == null || deltaLng == null) {
            return [];
        }
        lat += deltaLat;
        lng += deltaLng;
        punkte.push([lat / faktor, lng / faktor]);
    }

    return punkte;
}

function routeLineZuKartenPunkte(routeLine) {
    if (typeof routeLine !== 'string' || !routeLine.trim()) {
        return [];
    }
    var kodiertePolyline = routeLine.trim();
    if (typeof atob === 'function') {
        try {
            kodiertePolyline = atob(kodiertePolyline);
        } catch (err) {}
    }
    return dekodierePolyline(kodiertePolyline, 6).filter(function(point) {
        return Array.isArray(point) &&
            point.length >= 2 &&
            istGueltigeKartenKoordinate(point[0], point[1]);
    });
}

map.on('zoomend', function() {
    if (zoomSetByApp) {
        zoomSetByApp = false;
    } else {
        lastUserZoom = Date.now();
    }
    updateZoomDisplay();
});
var polyline = null;
var pendingPath = null;
var lastDataTimestamp = null;
var lastStreamTimestamp = null;
var lastStateTimestamp = null;
var lastStateSinceTimestamp = null;
var lastVehicleState = null;
var lastTelemetryProfile = null;
var lastTelemetryTarget = null;
var lastTelemetryTargetSince = null;
var telemetryParkDelaySeconds = null;
var lastTelemetryConfigSynced = null;
var lastTelemetryConfigKeyPaired = null;
var lastTelemetryConfigSyncState = null;
var lastTelemetryConfigSyncError = null;
var lastTelemetryConfigSyncProfile = null;
var installedVersion = null;
var CONFIG = {};
var HIGHLIGHT_BLUE = false;
var currentPath = [];
var lastPathDelta = [];
var OFFLINE_TEXT = 'Das Fahrzeug ist offline und schläft - Bitte nicht wecken! - Die Daten sind die zuletzt bekannten und somit nicht aktuell!';
var SERVICE_MODE_TEXT = 'Fahrzeug befindet sich im Service Mode.';
var SERVICE_MODE_PLUS_TEXT = 'Fahrzeug befindet sich im Service Mode Plus.';
var smsForm = $('#sms-form');
var smsNameInput = $('#sms-name');
var smsInput = $('#sms-text');
var smsButton = $('#sms-send');
var smsStatus = $('#sms-status');
var TOGGLE_DEFAULTS = {
    'map': true,
    'lock-status': true,
    'user-presence': true,
    'gear-shift': true,
    'battery-indicator': true,
    'speedometer': true,
    'thermometer-inside': true,
    'thermometer-outside': true,
    'thermometer-battery': true,
    'climate-indicator': true,
    'tpms-indicator': true,
    'openings-indicator': true,
    'blue-openings': false,
    'heater-indicator': true,
    'charging-info': true,
    'ladeplanung-info': true,
    'preconditioning-info': true,
    'reifendruck-details': true,
    'v2l-infos': true,
    'announcement-box': true,
    'page-menu': true,
    'menu-dashboard': true,
    'menu-statistik': true,
    'menu-history': true,
    'nav-bar': true,
    'technical-info': true,
    'media-player': true,
    'ptt-controls': true,
    'software-update': true,
    'offline-msg': true,
    'loading-msg': true,
    'park-since': true,
    'sms-form': true,
    'supercharger-list': true
};

function applyThermometerCompatibility(cfg) {
    if (!cfg || typeof cfg.thermometers === 'undefined') return;
    THERMOMETER_IDS.forEach(function(id) {
        if (typeof cfg[id] === 'undefined') {
            cfg[id] = !!cfg.thermometers;
        }
    });
}

function parseVersion(str) {
    return str ? str.split(' ')[0] : null;
}

function isNewerVersion(installed, available) {
    var instParts = installed.split('.').map(Number);
    var availParts = available.split('.').map(Number);
    for (var i = 0; i < Math.max(instParts.length, availParts.length); i++) {
        var a = availParts[i] || 0;
        var b = instParts[i] || 0;
        if (a > b) return true;
        if (a < b) return false;
    }
    return false;
}

function parseAnnouncements(text) {
    var arr = [];
    if (text) {
        text.split(/\n/).forEach(function(line) {
            line = line.trim();
            if (line) arr.push(line);
        });
    }
    return arr.slice(0, 3);
}

function normalisiereDashboardState(status) {
    if (typeof status !== 'string') {
        return status;
    }
    var st = status.trim().toLowerCase();
    if (!st) {
        return '';
    }
    if (st === 'connected') {
        return 'online';
    }
    if (st === 'disconnected') {
        return 'offline';
    }
    return st;
}

function istOfflineOderSchlaeft(status) {
    var st = normalisiereDashboardState(status);
    return st === 'offline' || st === 'asleep';
}

function entfernungMeter(lat1, lng1, lat2, lng2) {
    if (!isFinite(lat1) || !isFinite(lng1) || !isFinite(lat2) || !isFinite(lng2)) {
        return null;
    }
    var radius = 6371000;
    var toRad = Math.PI / 180;
    var dLat = (Number(lat2) - Number(lat1)) * toRad;
    var dLng = (Number(lng2) - Number(lng1)) * toRad;
    var rLat1 = Number(lat1) * toRad;
    var rLat2 = Number(lat2) * toRad;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(rLat1) * Math.cos(rLat2) *
            Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return radius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function routenPunkteSindPlausibel(points, startLat, startLng, zielLat, zielLng) {
    if (!Array.isArray(points) || points.length < 2) {
        return false;
    }
    var vorherigerPunkt = null;
    for (var i = 0; i < points.length; i++) {
        var point = points[i];
        if (!Array.isArray(point) || point.length < 2) {
            return false;
        }
        var lat = Number(point[0]);
        var lng = Number(point[1]);
        if (!istGueltigeKartenKoordinate(lat, lng)) {
            return false;
        }
        if (vorherigerPunkt) {
            var entfernung = entfernungMeter(
                vorherigerPunkt[0],
                vorherigerPunkt[1],
                lat,
                lng
            );
            if (entfernung != null && entfernung > ROUTENPUNKT_MAX_SPRUNG_METER) {
                return false;
            }
        }
        vorherigerPunkt = [lat, lng];
    }

    var ersterPunkt = points[0];
    var letzterPunkt = points[points.length - 1];
    if (istGueltigeKartenKoordinate(startLat, startLng)) {
        var startEntfernung = Math.min(
            entfernungMeter(startLat, startLng, ersterPunkt[0], ersterPunkt[1]),
            entfernungMeter(startLat, startLng, letzterPunkt[0], letzterPunkt[1])
        );
        if (startEntfernung > ROUTENPUNKT_MAX_SPRUNG_METER) {
            return false;
        }
    }
    if (istGueltigeKartenKoordinate(zielLat, zielLng)) {
        var zielEntfernung = Math.min(
            entfernungMeter(zielLat, zielLng, ersterPunkt[0], ersterPunkt[1]),
            entfernungMeter(zielLat, zielLng, letzterPunkt[0], letzterPunkt[1])
        );
        if (zielEntfernung > ROUTENPUNKT_MAX_SPRUNG_METER) {
            return false;
        }
    }
    return true;
}

function routenPunkteAusreisserAmRandEntfernen(points) {
    if (!Array.isArray(points)) {
        return [];
    }
    var bereinigt = points.slice();

    function punktAbstand(indexA, indexB) {
        return entfernungMeter(
            bereinigt[indexA][0],
            bereinigt[indexA][1],
            bereinigt[indexB][0],
            bereinigt[indexB][1]
        );
    }

    while (bereinigt.length > 2) {
        var ersteLuecke = punktAbstand(0, 1);
        if (ersteLuecke == null || ersteLuecke <= ROUTENPUNKT_MAX_SPRUNG_METER) {
            break;
        }
        bereinigt.shift();
    }
    while (bereinigt.length > 2) {
        var letzteLuecke = punktAbstand(bereinigt.length - 2, bereinigt.length - 1);
        if (letzteLuecke == null || letzteLuecke <= ROUTENPUNKT_MAX_SPRUNG_METER) {
            break;
        }
        bereinigt.pop();
    }
    return bereinigt;
}

function fahrzeugIstGeparktFuerKarte(data, drive, speedKmh) {
    drive = drive || {};
    var gang = normalizeShiftState(drive.shift_state);
    if (gang && gang !== 'P') {
        return false;
    }
    if (speedKmh != null && isFinite(speedKmh) && Math.abs(Number(speedKmh)) > 1) {
        return false;
    }
    var status = getStatus(data || {});
    return status === 'Geparkt' || status === 'Ladevorgang' || gang === 'P';
}

function navigationFuerKarteAktiv(data, drive) {
    drive = drive || {};
    if (drive.active_route_active === false) {
        return false;
    }
    if (drive.active_route_active === true) {
        return true;
    }
    return Boolean(
        drive.active_route_destination ||
        drive.active_route_miles_to_arrival != null ||
        drive.active_route_minutes_to_arrival != null
    );
}

function positionIstNeu(lat, lng, geparkt) {
    if (!isFinite(lat) || !isFinite(lng)) {
        return false;
    }
    if (!letzteKartenPosition) {
        return true;
    }
    if (geparkt) {
        var entfernung = entfernungMeter(
            letzteKartenPosition[0],
            letzteKartenPosition[1],
            lat,
            lng
        );
        if (entfernung != null && entfernung < PARKED_MAP_JITTER_METERS) {
            return false;
        }
    }
    var diffLat = Math.abs(lat - letzteKartenPosition[0]);
    var diffLng = Math.abs(lng - letzteKartenPosition[1]);
    return diffLat > 1e-6 || diffLng > 1e-6;
}

function kartenPunkteSignatur(points) {
    if (!Array.isArray(points) || !points.length) {
        return 'leer';
    }
    var erstes = points[0] || [];
    var letztes = points[points.length - 1] || [];
    return [
        points.length,
        erstes[0],
        erstes[1],
        letztes[0],
        letztes[1]
    ].join('|');
}

function planeNaechsteStatusabfrage() {
    if (statusAbfrageTimer) {
        clearTimeout(statusAbfrageTimer);
    }
    var idleSekunden = Number(lastApiIntervalIdle);
    if (!isFinite(idleSekunden) || idleSekunden <= 0) {
        idleSekunden = 30;
    }
    var intervallMs = Math.max(1, idleSekunden) * 1000;
    statusAbfrageTimer = setTimeout(function() {
        startStreamIfOnline();
    }, intervallMs);
}

function startAnnouncementCycle() {
    if (announcementTimer) {
        clearInterval(announcementTimer);
        announcementTimer = null;
    }
    // Always reset the index when the announcement list changes to avoid
    // referencing an out-of-range entry when the number of lines decreases.
    announcementIndex = 0;
    if (announcementList.length > 1) {
        announcementTimer = setInterval(function() {
            announcementIndex = (announcementIndex + 1) % announcementList.length;
            updateAnnouncement();
        }, 5000);
    }
}

function configEnabled(id) {
    var defaultVal = TOGGLE_DEFAULTS.hasOwnProperty(id) ? TOGGLE_DEFAULTS[id] : true;
    if (!CONFIG || typeof CONFIG[id] === 'undefined') {
        return defaultVal;
    }
    return !!CONFIG[id];
}

function applyConfig(cfg) {
    CONFIG = cfg || {};
    applyThermometerCompatibility(CONFIG);
    HIGHLIGHT_BLUE = configEnabled('blue-openings');
    if (CONFIG.announcement) {
        announcementRaw = CONFIG.announcement;
    } else {
        announcementRaw = '';
    }
    announcementList = parseAnnouncements(announcementRaw);
    startAnnouncementCycle();
    updateAnnouncement();
    showConfigured();
}

function showConfigured() {
    Object.keys(TOGGLE_DEFAULTS).forEach(function(id) {
        if (id === 'blue-openings') return;
        if (id === 'tpms-indicator') {
            var $tpms = $('#' + id);
            if (configEnabled(id)) {
                $tpms.css('display', '');
            } else {
                $tpms.css('display', 'none');
            }
            return;
        }
        if (
            id === 'ladeplanung-info' ||
            id === 'preconditioning-info' ||
            id === 'technical-info' ||
            id === 'reifendruck-details'
        ) return;
        $('#' + id).toggle(configEnabled(id));
    });
    var visibleThermometers = THERMOMETER_IDS.some(function(id) {
        return configEnabled(id);
    });
    $('#thermometers').toggle(visibleThermometers);
    $('#dashboard-content').show();
    // Recalculate map dimensions when the content becomes visible.
    map.invalidateSize();
    updateSmsForm();
    if (!configEnabled('supercharger-list')) {
        $('#supercharger-items').empty();
        clearSuperchargerMarkers();
    } else {
        updateSuperchargerList();
    }
    if (!configEnabled('ladeplanung-info')) {
        $('#ladeplanung-info').empty().hide();
    }
    if (!configEnabled('preconditioning-info')) {
        $('#preconditioning-info').empty().hide();
    }
    if (!configEnabled('technical-info')) {
        $('#technical-info').empty().hide();
    }
    if (!configEnabled('reifendruck-details')) {
        $('#reifendruck-details').empty().hide();
    }
}

function updateSmsForm() {
    if (!smsForm.length) return;
    var cfg = CONFIG || {};
    if (!configEnabled('sms-form')) {
        smsForm.hide();
        smsNameInput.prop('disabled', true);
        smsInput.prop('disabled', true);
        smsButton.prop('disabled', true);
        smsStatus.text('');
        return;
    }
    var hasNumber = cfg.phone_number && cfg.infobip_api_key && cfg.sms_enabled !== false;
    smsForm.toggle(!!hasNumber);
    var driveOnly = cfg.sms_drive_only !== false;
    var parkedSince = parkStartTime ? Date.now() - parkStartTime : 0;
    var allowWhileParked = parkedSince > 0 && parkedSince <= PARK_GRACE_MS;
    var enabled = hasNumber && (!driveOnly || (currentGear && currentGear !== 'P') || allowWhileParked);
    smsNameInput.prop('disabled', !enabled);
    smsInput.prop('disabled', !enabled);
    smsButton.prop('disabled', !enabled);
    if (!enabled) {
        if (hasNumber && driveOnly && currentGear === 'P') {
            if (parkedSince > PARK_GRACE_MS) {
                smsStatus.text('Nachrichten nur bis 5 Minuten nach dem Parken m\u00F6glich');
            } else {
                smsStatus.text('Nachricht nur w\u00E4hrend der Fahrt erlaubt');
            }
        } else if (hasNumber && driveOnly && !currentGear) {
            smsStatus.text('Nachricht nur w\u00E4hrend der Fahrt erlaubt');
        } else {
            smsStatus.text('');
        }
        smsNameInput.val('');
        smsInput.val('');
    } else {
        smsStatus.text('');
    }
}

function showLoading() {
    if (!configEnabled('loading-msg')) {
        $('#loading-msg').hide();
        return;
    }
    $('#loading-msg').show();
}

function hideLoading() {
    $('#loading-msg').hide();
}

// Marker and polyline for active navigation destination
var flagIcon = L.divIcon({
    html: [
        '<svg width="40" height="48" viewBox="0 0 20 30">',
        '<defs>',
        '<pattern id="checker" width="4" height="4" patternUnits="userSpaceOnUse">',
        '<rect width="2" height="2" fill="#000"/>',
        '<rect x="2" y="2" width="2" height="2" fill="#000"/>',
        '</pattern>',
        '</defs>',
        '<path d="M5 2v26" stroke="black" stroke-width="2" fill="none"/>',
        '<path d="M7 4l10 5-10 5z" fill="url(#checker)" stroke="black" stroke-width="1"/>',
        '</svg>'
    ].join(''),
    className: 'flag-icon',
    iconSize: [40, 48],
    iconAnchor: [8, 45]
});
var destMarker = null;
var destLine = null;

var arrowIcon = L.divIcon({
    html: '<svg width="30" height="30" viewBox="0 0 30 30"><polygon points="15,0 30,30 15,22 0,30" /></svg>',
    className: 'arrow-icon',
    iconSize: [30, 30],
    iconAnchor: [15, 15]
});
var scMarkerIcon = L.divIcon({
    html: '⚡',
    className: 'sc-icon',
    iconSize: [20, 20],
    iconAnchor: [10, 10]
});

var marker = L.marker(DEFAULT_POS, {
    icon: arrowIcon,
    rotationAngle: 0,
    rotationOrigin: 'center center'
}).addTo(map);
marker.on('moveend', function() {
    if (Array.isArray(pendingPath)) {
        if (polyline) {
            polyline.setLatLngs(pendingPath);
        } else {
            polyline = L.polyline(pendingPath, { color: 'blue' }).addTo(map);
        }
        pendingPath = null;
    }
});
var eventSource = null;

function updatePathPoints(data) {
    lastPathDelta = [];
    if (data && data.path_reset) {
        if (Array.isArray(data.path)) {
            currentPath = data.path.slice();
        } else {
            currentPath = [];
        }
    } else if (data && Array.isArray(data.path)) {
        currentPath = data.path.slice();
    }
    if (data && Array.isArray(data.path_delta) && data.path_delta.length) {
        if (!Array.isArray(currentPath)) {
            currentPath = [];
        }
        data.path_delta.forEach(function(pt) {
            if (!Array.isArray(pt) || pt.length < 2) {
                return;
            }
            var last = currentPath[currentPath.length - 1];
            if (!last || last[0] !== pt[0] || last[1] !== pt[1]) {
                currentPath.push(pt);
                lastPathDelta.push(pt);
            }
        });
    }
    return Array.isArray(currentPath) ? currentPath : [];
}

function neuerPfadNurAngehängt(data) {
    return Boolean(
        data &&
        !data.path_reset &&
        !Array.isArray(data.path) &&
        Array.isArray(lastPathDelta) &&
        lastPathDelta.length &&
        polyline
    );
}

function clearSuperchargerMarkers() {
    superchargerMarkers.forEach(function(m) {
        try {
            map.removeLayer(m);
        } catch (err) {}
    });
    superchargerMarkers = [];
}

function updateSuperchargerList(data) {
    if (typeof data !== 'undefined') {
        lastSuperchargerData = data;
    } else {
        data = lastSuperchargerData;
    }
    var $container = $('#supercharger-list');
    var $list = $('#supercharger-items');
    if (!$container.length || !$list.length) {
        return;
    }
    if (!configEnabled('supercharger-list')) {
        $list.empty();
        clearSuperchargerMarkers();
        return;
    }
    var online = data && data.state === 'online';
    var entries = [];
    if (online && data && Array.isArray(data.nearby_superchargers)) {
        entries = data.nearby_superchargers.slice(0, 5);
    }
    clearSuperchargerMarkers();
    $list.empty();
    if (!online) {
        $list.append('<li class="empty">Keine Live-Daten verfügbar.</li>');
        return;
    }
    if (!entries.length) {
        $list.append('<li class="empty">Keine Supercharger gefunden.</li>');
        return;
    }
    entries.forEach(function(site) {
        if (!site) return;
        var name = site.name || 'Supercharger';
        var distanceText = '';
        if (typeof site.distance_km === 'number' && isFinite(site.distance_km)) {
            distanceText = site.distance_km.toFixed(1) + ' km';
        }
        var availability = '';
        var available = site.available_stalls;
        var total = site.total_stalls;
        if (available != null && total != null) {
            availability = available + ' / ' + total + ' frei';
        } else if (available != null) {
            availability = available + ' frei';
        } else if (total != null) {
            availability = total + ' Plätze';
        }
        var metaParts = [];
        if (distanceText) metaParts.push(distanceText);
        if (availability) metaParts.push(availability);
        var metaText = metaParts.join(' · ');
        var $li = $('<li>');
        var $row = $('<div class="row">');
        $row.append($('<span class="name">').text(name));
        if (metaText) {
            $row.append($('<span class="meta">').text(metaText));
        }
        $li.append($row);
        $list.append($li);
        if (site.location && site.location.latitude != null && site.location.longitude != null) {
            var lat = Number(site.location.latitude);
            var lng = Number(site.location.longitude);
            if (isFinite(lat) && isFinite(lng)) {
                var marker = L.marker([lat, lng], { icon: scMarkerIcon });
                marker.bindTooltip(name + (distanceText ? ' – ' + distanceText : ''), {permanent: false});
                marker.addTo(map);
                superchargerMarkers.push(marker);
            }
        }
    });
}

function updateHeader(data) {
    var info = '';
    if (data) {
        var name = data.vehicle_state && data.vehicle_state.vehicle_name;
        if (!name && data.display_name) {
            name = data.display_name;
        }
        name = bereinigeDoppeltenModellnamen(name);
        if (name) {
            info = 'für ' + name;
        }
        var version = data.vehicle_state && data.vehicle_state.car_version;
        if (version) {
            version = parseVersion(version);
            installedVersion = version;
            info += ' (V ' + version + ')';
        }
    }
    $('#vehicle-info').text(info);
}

function bereinigeDoppeltenModellnamen(name) {
    if (typeof name !== 'string') {
        return name;
    }
    var bereinigt = name.replace(/\s+/g, ' ').trim();
    if (!bereinigt) {
        return bereinigt;
    }
    var doppelSuffixMuster = /\(([^()]+)\)\s*\(\1\)\s*$/i;
    while (doppelSuffixMuster.test(bereinigt)) {
        bereinigt = bereinigt.replace(doppelSuffixMuster, '($1)').trim();
    }
    return bereinigt;
}

function fetchVehicles() {
    $.getJSON('/api/vehicles', function(resp) {
        var vehicles = Array.isArray(resp) ? resp : [];
        var $select = $('#vehicle-select');
        var $label = $('label[for="vehicle-select"]');
        $select.empty();
        if (!vehicles.length) {
            return;
        }
        vehicles.forEach(function(v) {
            $select.append($('<option>').val(v.id).text(v.display_name));
        });
        if (vehicles.length <= 1) {
            $label.hide();
            $select.hide();
        } else {
            $label.show();
            $select.show();
        }
        if (!currentVehicle && vehicles.length > 0) {
            currentVehicle = vehicles[0].id;
        }
        if (currentVehicle) {
            $select.val(currentVehicle);
            startStreamIfOnline();
        }
    });
}

function handleData(data) {
    hideLoading();
    updateHeader(data);
    updateUI(data);
    updateVehicleState(data.state, data.state_checked_at, data);
    updateTelemetryProfile(
        data.telemetry_profile,
        data.telemetry_profile_target,
        data.telemetry_profile_target_since,
        data.telemetry_profile_park_delay_seconds,
        data.telemetry_config_sync_state,
        data.telemetry_config_synced,
        data.telemetry_config_key_paired,
        data.telemetry_config_sync_error,
        data.telemetry_config_sync_profile
    );
    var vehicle = data.vehicle_state || {};
    updateOfflineInfo(data.state, vehicle.service_mode, vehicle.service_mode_plus);
    updateSoftwareUpdate(vehicle.software_update);
    var drive = data.drive_state || {};
    var charge = data.charge_state || {};
    var climate = data.climate_state || {};
    updateDataAge(neuesterDatenZeitstempel(data, vehicle, drive, charge, climate));
    updateLockStatus(vehicle.locked);
    updateUserPresence(vehicle.is_user_present);
    updateTurnSignalIndicator(vehicle.lights_turn_signal, vehicle.lights_hazards_active);
    updateHighBeamIndicator(vehicle.lights_high_beams);
    updateVehicleSymbols(vehicle, data.gui_settings || {});
    updateGearShift(drive.shift_state);
    updateParkTime(data.park_start);
    updateNavBar(drive);
    var displayPower = drive.power;
    if (charge.charging_state === 'Charging' && charge.charger_power != null) {
        displayPower = charge.charger_power;
    }
    updateSpeedometer(drive.speed, displayPower, charge.charging_state);
    updatePedalPosition(vehicle.pedal_position);
    updateOdometer(vehicle.odometer);
    var rangeMiles = charge.ideal_battery_range;
    if (rangeMiles == null) {
        rangeMiles = charge.est_battery_range;
    }
    updateBatteryIndicator(charge.battery_level, rangeMiles, charge.charging_state, charge.battery_heater_on);
    updateV2LInfos(charge, drive);
    updateChargingInfo(charge, data);
    updateLadeplanungInfo(charge, drive, data);
    updateTechnischeDetails(charge);
    updateThermometers(
        climate.inside_temp,
        climate.outside_temp,
        charge.battery_temp,
        charge.module_temp_min,
        charge.module_temp_max
    );
    updateClimateStatus(climate.is_climate_on);
    updateClimateMode(climate.climate_keeper_mode);
    updateCabinProtection(climate.cabin_overheat_protection);
    updateFanStatus(climate.fan_status);
    updateDesiredTemp(climate.driver_temp_setting);
    updatePreconditioningInfo(
        climate,
        charge,
        drive,
        darfVorklimatisierungAnzeigen(data, drive)
    );
    updateHeaterIndicator(
        climate.is_front_defroster_on,
        climate.is_rear_defroster_on,
        climate.steering_wheel_heater,
        climate.steering_wheel_heat_level,
        climate.auto_steering_wheel_heat,
        climate.wiper_blade_heater,
        climate.side_mirror_heaters,
        charge.battery_heater_on,
        climate.seat_heater_left,
        climate.seat_heater_right,
        climate.seat_heater_rear_left,
        climate.seat_heater_rear_center,
        climate.seat_heater_rear_right
    );
    updateTPMS(vehicle);
    updateReifendruckDetails(vehicle);
    updateOpenings(vehicle, charge);
    updateMediaPlayer(vehicle.media_info);
    var alarm = data.alarm_state;
    if (alarm == null && vehicle.alarm_state != null) {
        alarm = vehicle.alarm_state;
    }
    updateAlarmPopup(alarm);
    var lat = Number(drive.latitude);
    var lng = Number(drive.longitude);
    var privacyModeAktiv = kartenPrivatmodusAktiv();
    var kartenPosition = privatisiereKartenPunkt(lat, lng);
    var mapLat = privacyModeAktiv ? kartenPosition.lat : lat;
    var mapLng = privacyModeAktiv ? kartenPosition.lng : lng;
    var privacyRadius = kartenPosition.radius;
    var slide = false;
    var offline = istOfflineOderSchlaeft(data.state);
    if (isFinite(mapLat) && isFinite(mapLng)) {
        var speedVal = parseFloat(drive.speed);
        var speedKmh = isNaN(speedVal) ? 0 : speedVal * MILES_TO_KM;
        var karteGeparkt = fahrzeugIstGeparktFuerKarte(data, drive, speedKmh);
        var coordsNeu = positionIstNeu(mapLat, mapLng, karteGeparkt);
        if (coordsNeu) {
            marker.setLatLng([mapLat, mapLng]);
        }
        var zoom = computeZoomForSpeed(speedKmh);
        if (privacyModeAktiv) {
            zoom = zoomFuerPrivatsphaereRadius(privacyRadius, zoom);
        }
        if (Date.now() - lastUserZoom < USER_ZOOM_PRIORITY_MS) {
            zoom = map.getZoom();
        }
        if (coordsNeu || !letzteKartenPosition) {
            zoomSetByApp = true;
            map.setView([mapLat, mapLng], zoom, {animate: false});
            updateZoomDisplay();
        }
        if (typeof drive.heading === 'number' && (!karteGeparkt || letzteKartenRichtung == null)) {
            var displayHeading = adjustHeadingForReverse(drive.heading, drive.shift_state);
            if (
                letzteKartenRichtung == null ||
                Math.abs(Number(displayHeading) - Number(letzteKartenRichtung)) > 0.1
            ) {
                marker.setRotationAngle(displayHeading);
                letzteKartenRichtung = displayHeading;
            }
        }
        if (coordsNeu || !letzteKartenPosition) {
            letzteKartenPosition = [mapLat, mapLng];
        }
    } else if (!letzteKartenPosition && !offline) {
        // Auf Standardposition zurücksetzen, wenn keine Koordinaten vorliegen
        var zoom = DEFAULT_ZOOM;
        if (Date.now() - lastUserZoom < USER_ZOOM_PRIORITY_MS) {
            zoom = map.getZoom();
        }
        zoomSetByApp = true;
        map.setView(DEFAULT_POS, zoom);
        updateZoomDisplay();
    }
    updatePrivatsphaereOverlay(privacyModeAktiv, mapLat, mapLng, privacyRadius);

    var addr = data.location_address;
    if (privacyModeAktiv) {
        $('#address-text').text('');
        $('#address-error').hide();
    } else if (addr) {
        $('#address-text').text(addr);
        $('#address-error').hide();
    } else {
        $('#address-text').text('');
        $('#address-error').hide();
    }
    updateSuperchargerList(data);

    // Navigationsziel und empfangene RouteLine in der Karte anzeigen
    var dLat = null;
    var dLng = null;
    var zielKoordinatePlausibel = false;
    if (
        drive.active_route_latitude != null &&
        drive.active_route_longitude != null
    ) {
        dLat = Number(drive.active_route_latitude);
        dLng = Number(drive.active_route_longitude);
        zielKoordinatePlausibel = istPlausibleNavigationsZielKoordinate(dLat, dLng);
        if (zielKoordinatePlausibel && privacyModeAktiv) {
            var privatZiel = privatisiereKartenPunkt(dLat, dLng);
            dLat = privatZiel.lat;
            dLng = privatZiel.lng;
        }
    }
    var aktuellePositionPlausibel = isFinite(mapLat) && isFinite(mapLng);
    var routenPunkte = privacyModeAktiv ? [] : routeLineZuKartenPunkte(drive.active_route_line);
    if (routenPunkte.length > 1) {
        routenPunkte = routenPunkteAusreisserAmRandEntfernen(routenPunkte);
        if (!routenPunkteSindPlausibel(
            routenPunkte,
            aktuellePositionPlausibel ? mapLat : null,
            aktuellePositionPlausibel ? mapLng : null,
            zielKoordinatePlausibel ? dLat : null,
            zielKoordinatePlausibel ? dLng : null
        )) {
            routenPunkte = [];
        }
    }
    var nutztRouteLine = routenPunkte.length > 1;
    var zeigtNavigationsLinie = nutztRouteLine || (
        zielKoordinatePlausibel &&
        aktuellePositionPlausibel
    );
    var navigationInKarteAktiv = navigationFuerKarteAktiv(data, drive);
    if (navigationInKarteAktiv && (zeigtNavigationsLinie || zielKoordinatePlausibel)) {
        var linienPunkte = nutztRouteLine ? routenPunkte : [];
        if (!nutztRouteLine && zielKoordinatePlausibel && aktuellePositionPlausibel) {
            linienPunkte = [[mapLat, mapLng], [dLat, dLng]];
        }
        var linienOptionen = nutztRouteLine ? {
            color: '#00e5ff',
            lineCap: 'round',
            lineJoin: 'round',
            opacity: 0.9,
            smoothFactor: 0,
            weight: 4
        } : {
            color: 'red',
            dashArray: '5, 5',
            weight: 2
        };
        var zielSignatur = [
            drive.active_route_destination || '',
            mapLat,
            mapLng,
            dLat,
            dLng,
            nutztRouteLine ? kartenPunkteSignatur(routenPunkte) : 'luftlinie'
        ].join('|');
        if (zielSignatur !== letzteZielSignatur) {
            if (zielKoordinatePlausibel) {
                if (!destMarker) {
                    destMarker = L.marker([dLat, dLng], { icon: flagIcon }).addTo(map);
                } else {
                    destMarker.setLatLng([dLat, dLng]);
                }
            } else if (destMarker) {
                map.removeLayer(destMarker);
                destMarker = null;
            }
            if (linienPunkte.length > 1) {
                if (!destLine) {
                    destLine = L.polyline(linienPunkte, linienOptionen).addTo(map);
                } else {
                    destLine.setLatLngs(linienPunkte);
                    destLine.setStyle(linienOptionen);
                }
            } else {
                if (destLine) {
                    map.removeLayer(destLine);
                    destLine = null;
                }
            }
            letzteZielSignatur = zielSignatur;
        }
    } else {
        if (destMarker) {
            map.removeLayer(destMarker);
            destMarker = null;
        }
        if (destLine) {
            map.removeLayer(destLine);
            destLine = null;
        }
        letzteZielSignatur = null;
    }
    var pathPoints = updatePathPoints(data);
    var sichtbarePathPoints = privatisiereKartenPunkte(pathPoints);
    var pfadSignatur = kartenPunkteSignatur(sichtbarePathPoints);
    if (sichtbarePathPoints.length > 1) {
        if (pfadSignatur !== letztePfadSignatur) {
            if (!polyline) {
                polyline = L.polyline(sichtbarePathPoints, { color: 'blue' }).addTo(map);
            } else if (neuerPfadNurAngehängt(data)) {
                privatisiereKartenPunkte(lastPathDelta).forEach(function(pt) {
                    polyline.addLatLng(pt);
                });
            } else if (slide) {
                pendingPath = sichtbarePathPoints.slice();
            } else {
                polyline.setLatLngs(sichtbarePathPoints);
            }
            letztePfadSignatur = pfadSignatur;
        }
    } else if (polyline) {
        map.removeLayer(polyline);
        polyline = null;
        letztePfadSignatur = pfadSignatur;
    } else {
        letztePfadSignatur = pfadSignatur;
    }
}


function updateGearShift(state) {
    var gear = state || 'P';
    currentGear = gear;
    $('#gear-shift div').removeClass('active');
    $('#gear-shift div[data-gear="' + gear + '"]').addClass('active');
    displayParkTime();
    updateSmsForm();
}

function updateLockStatus(locked) {
    if (locked == null) {
        $('#lock-status').text('');
        return;
    }
    var isLocked = false;
    if (typeof locked === 'string') {
        var norm = locked.toLowerCase();
        isLocked = norm === 'true' || norm === '1';
    } else {
        isLocked = !!locked;
    }
    if (isLocked) {
        $('#lock-status')
            .text('\uD83D\uDD12')
            .attr('title', 'Verriegelt')
            .attr('aria-label', 'Verriegelt');
    } else {
        $('#lock-status')
            .text('\uD83D\uDD13')
            .attr('title', 'Offen')
            .attr('aria-label', 'Offen');
    }
}

function updateUserPresence(present) {
    if (present == null) {
        $('#user-presence').empty();
        return;
    }
    var isPresent = false;
    if (typeof present === 'string') {
        var norm = present.toLowerCase();
        isPresent = norm === 'true' || norm === '1';
    } else {
        isPresent = !!present;
    }
    var icon = '<svg width="30" height="30" viewBox="0 0 24 24" ' +
               'fill="currentColor" aria-hidden="true">' +
               '<circle cx="12" cy="7" r="5" />' +
               '<path d="M2 22c0-5.5 4.5-10 10-10s10 4.5 10 10" />' +
               '</svg>';
    $('#user-presence').html(icon);
    if (isPresent) {
        $('#user-presence')
            .css('color', '#4caf50')
            .attr('title', 'Person im Fahrzeug')
            .attr('aria-label', 'Person im Fahrzeug');
    } else {
        $('#user-presence')
            .css('color', '#d00')
            .attr('title', 'Keine Person im Fahrzeug')
            .attr('aria-label', 'Keine Person im Fahrzeug');
    }
}

function updateTurnSignalIndicator(turnSignal, hazardsActive) {
    var $indicator = $('#turn-indicator');
    var $left = $('#turn-left');
    var $right = $('#turn-right');
    var signal = typeof turnSignal === 'string' ? turnSignal.toLowerCase() : '';
    if (signal.indexOf('turnsignalstate') === 0) {
        signal = signal.substring('turnsignalstate'.length).toLowerCase();
    }
    var hazards = false;
    if (typeof hazardsActive === 'string') {
        var hazardsText = hazardsActive.toLowerCase();
        hazards = hazardsText === 'true' || hazardsText === '1' || hazardsText === 'on';
    } else {
        hazards = !!hazardsActive;
    }
    var leftActive = hazards || signal === 'left' || signal === 'both';
    var rightActive = hazards || signal === 'right' || signal === 'both';
    $left
        .toggleClass('is-active', leftActive)
        .attr('title', 'Blinker links')
        .attr('aria-label', 'Blinker links');
    $right
        .toggleClass('is-active', rightActive)
        .attr('title', 'Blinker rechts')
        .attr('aria-label', 'Blinker rechts');
    var title = 'Blinker aus';
    if (hazards || signal === 'both') {
        title = 'Warnblinker an';
    } else if (signal === 'left') {
        title = 'Blinker links';
    } else if (signal === 'right') {
        title = 'Blinker rechts';
    }
    $indicator.attr('title', title).attr('aria-label', title);
}

function updateHighBeamIndicator(highBeamsActive) {
    var $el = $('#high-beam-indicator');
    var active = false;
    if (typeof highBeamsActive === 'string') {
        var text = highBeamsActive.toLowerCase();
        active = text === 'true' || text === '1' || text === 'on';
    } else {
        active = !!highBeamsActive;
    }
    var title = active ? 'Fernlicht an' : 'Fernlicht aus';
    $el.toggleClass('is-active', active)
        .attr('title', title)
        .attr('aria-label', title);
}

function updateClimateStatus(on) {
    if (on == null) {
        $('#climate-status').text('').attr('title', '').attr('aria-label', '');
        return;
    }
    var active = false;
    if (typeof on === 'string') {
        var norm = on.toLowerCase();
        active = norm === 'true' || norm === '1';
    } else {
        active = !!on;
    }
    if (active) {
        $('#climate-status')
            .text('\u2744\uFE0F')
            .attr('title', 'Klimaanlage an')
            .attr('aria-label', 'Klimaanlage an');
    } else {
        $('#climate-status')
            .text('\uD83D\uDEAB')
            .attr('title', 'Klimaanlage aus')
            .attr('aria-label', 'Klimaanlage aus');
    }
}

function updateFanStatus(speed) {
    if (speed == null || isNaN(speed)) {
        $('#fan-status').text('').attr('title', '').attr('aria-label', '');
        return;
    }
    var val = Math.max(0, Math.min(11, Number(speed)));
    $('#fan-status')
        .text('\uD83C\uDF00 ' + val)
        .attr('title', 'L\u00FCfterstufe ' + val)
        .attr('aria-label', 'L\u00FCfterstufe ' + val);
}

function updateClimateMode(mode) {
    var $el = $('#climate-mode');
    if (typeof mode === 'string') {
        mode = mode.toLowerCase();
    }
    if (!mode || mode === 'off') {
        $el.text('').attr('title', '').attr('aria-label', '').hide();
        return;
    }
    var icon = '';
    var title = '';
    if (mode === 'dog') {
        icon = '\uD83D\uDC36';
        title = 'Hundemodus';
    } else if (mode === 'camp' || mode === 'party') {
        icon = '\u26FA';
        title = 'Camp-Modus';
    } else if (mode === 'on') {
        icon = '\u267B';
        title = 'Klimaanlage halten';
    } else {
        $el.text('').attr('title', '').hide();
        return;
    }
    $el.text(icon)
        .attr('title', title)
        .attr('aria-label', title)
        .show();
}

function updateCabinProtection(value) {
    var $el = $('#cabin-protection');
    if (value === 'On') {
        $el.text('\u2600\uFE0F')
            .attr('title', 'Kabinenschutz aktiv')
            .attr('aria-label', 'Kabinenschutz aktiv')
            .show();
    } else {
        $el.text('')
            .attr('title', '')
            .attr('aria-label', '')
            .hide();
    }
}

function updateDesiredTemp(temp) {
    if (temp == null || isNaN(temp)) {
        $('#desired-temp')
            .text('Wunsch: -- \u00B0C')
            .attr('title', 'Wunschtemperatur')
            .attr('aria-label', 'Wunschtemperatur -- \u00B0C');
        return;
    }
    $('#desired-temp')
        .text('Wunsch: ' + temp.toFixed(1) + ' \u00B0C')
        .attr('title', 'Wunschtemperatur')
        .attr('aria-label', 'Wunschtemperatur ' + temp.toFixed(1) + ' \u00B0C');
}

function updateHeaterIndicator(front, rear, steering, steeringLevel, steeringAuto, wiper,
                               mirror, battery,
                               seatL, seatR, seatRL, seatRC, seatRR) {
    function heaterHtml(name, symbol, symbolClass) {
        var klasse = 'heater-symbol';
        if (symbolClass) {
            klasse += ' ' + symbolClass;
        }
        return '<span class="heater-label">' + name + ':</span>' +
               '<span class="' + klasse + '">' + symbol + '</span>';
    }
    function set(id, val, name) {
        if (val == null) {
            $('#' + id)
                .html(heaterHtml(name, '?', 'is-unknown'))
                .attr('title', name + ' unbekannt')
                .attr('aria-label', name + ' unbekannt');
            return;
        }
        var active = istAktiv(val);
        $('#' + id)
            .html(heaterHtml(name, active ? '\uD83D\uDD25' : '\uD83D\uDEAB'))
            .attr('title', name + (active ? ' an' : ' aus'))
            .attr('aria-label', name + (active ? ' an' : ' aus'));
    }
    function heaterLevel(val) {
        if (val == null || val === '') {
            return null;
        }
        var numeric = parseNumber(val);
        if (numeric != null) {
            return Math.max(0, Math.round(numeric));
        }
        if (typeof val !== 'string') {
            return null;
        }
        var norm = val.trim()
            .replace(/^HvacSteeringWheelHeatLevel/, '')
            .replace(/^SteeringWheelHeatLevel/, '')
            .replace(/^SteeringWheelHeat/, '')
            .replace(/^HeatLevel/, '')
            .replace(/^Level/, '')
            .toLowerCase()
            .replace(/[_\-\s]/g, '');
        if (!norm || ['false', 'off', 'none', 'null', 'unknown'].indexOf(norm) !== -1) {
            return 0;
        }
        if (['true', 'on', 'active', 'enabled', 'low'].indexOf(norm) !== -1) {
            return 1;
        }
        if (['medium', 'mid', 'med'].indexOf(norm) !== -1) {
            return 2;
        }
        if (['high', 'max', 'maximum'].indexOf(norm) !== -1) {
            return 3;
        }
        return null;
    }
    function setSteering(id, val, levelVal, autoVal, name) {
        var level = heaterLevel(levelVal);
        var autoActive = istAktiv(autoVal);
        var active = level != null ? level > 0 : istAktiv(val);
        if (!active && autoActive) {
            active = true;
        }
        var suffix = active ? '\uD83D\uDD25' : '\uD83D\uDEAB';
        var title = name + (active ? ' an' : ' aus');
        if (active && level != null && level > 0) {
            suffix += level;
            title = name + ' Stufe ' + level;
        } else if (active && autoActive) {
            suffix += ' A';
            title = name + ' Automatik';
        }
        $('#' + id)
            .html(heaterHtml(name, suffix))
            .attr('title', title)
            .attr('aria-label', title);
    }
    function setLevel(id, val, name) {
        if (val == null || isNaN(val)) {
            $('#' + id)
                .html(heaterHtml(name, '?', 'is-unknown'))
                .attr('title', name + ' unbekannt')
                .attr('aria-label', name + ' unbekannt');
            return;
        }
        var level = Number(val);
        if (level <= 0) {
            $('#' + id)
                .html(heaterHtml(name, '\uD83D\uDEAB'))
                .attr('title', name + ' aus')
                .attr('aria-label', name + ' aus');
        } else {
            $('#' + id)
                .html(heaterHtml(name, '\uD83D\uDD25' + level))
                .attr('title', name + ' Stufe ' + level)
                .attr('aria-label', name + ' Stufe ' + level);
        }
    }

    set('front-defrost', front, 'Frontscheibenheizung');
    set('rear-defrost', rear, 'Heckscheibenheizung');
    setSteering('steering-heater', steering, steeringLevel, steeringAuto, 'Lenkradheizung');
    set('wiper-heater', wiper, 'Scheibenwischerheizung');
    set('mirror-heater', mirror, 'Seitenspiegelheizung');
    set('battery-heater', battery, 'Batterieheizung');
    setLevel('seat-left', seatL, 'Sitzheizung Fahrer');
    setLevel('seat-right', seatR, 'Sitzheizung Beifahrer');
    setLevel('seat-rear-left', seatRL, 'Sitzheizung hinten links');
    setLevel('seat-rear-center', seatRC, 'Sitzheizung hinten mitte');
    setLevel('seat-rear-right', seatRR, 'Sitzheizung hinten rechts');
}

function leseZeitstempelMillis(wert) {
    var num = parseNumber(wert);
    if (num == null) {
        if (typeof wert === 'string') {
            var parsed = Date.parse(wert);
            if (!isNaN(parsed)) {
                return parsed;
            }
        }
        return null;
    }
    if (num < 1e12) {
        return num * 1000;
    }
    return num;
}

function formatiereUhrzeit(datum) {
    if (!(datum instanceof Date) || isNaN(datum.getTime())) {
        return null;
    }
    return datum.toLocaleTimeString('de-DE', {
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'Europe/Berlin'
    });
}

function formatiereZeitpunkt(wert) {
    var millis = leseZeitstempelMillis(wert);
    if (millis == null) {
        return null;
    }
    var datum = new Date(millis);
    if (isNaN(datum.getTime())) {
        return null;
    }
    return datum.toLocaleString('de-DE', {
        weekday: 'short',
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'Europe/Berlin'
    });
}

function formatiereZeitAusMinuten(minuten) {
    var zahl = parseNumber(minuten);
    if (zahl == null) {
        return null;
    }
    var gesamt = Math.max(0, Math.round(zahl)) % (24 * 60);
    var stunden = Math.floor(gesamt / 60);
    var restMinuten = gesamt % 60;
    return String(stunden).padStart(2, '0') + ':' +
           String(restMinuten).padStart(2, '0') + ' Uhr';
}

function formatiereDauerMinuten(minuten) {
    var zahl = parseNumber(minuten);
    if (zahl == null) {
        return null;
    }
    var gerundet = Math.max(0, Math.round(zahl));
    var stunden = Math.floor(gerundet / 60);
    var restMinuten = gerundet % 60;
    var teile = [];
    if (stunden > 0) {
        teile.push(stunden + ' h');
    }
    teile.push(restMinuten + ' min');
    return teile.join(' ');
}

function formatiereAlter(wert) {
    var millis = leseZeitstempelMillis(wert);
    if (millis == null) {
        return '';
    }
    var diffSekunden = Math.max(0, Math.round((Date.now() - millis) / 1000));
    if (diffSekunden < 60) {
        return 'gerade eben';
    }
    if (diffSekunden < 3600) {
        var minuten = Math.floor(diffSekunden / 60);
        return 'vor ' + minuten + ' min';
    }
    if (diffSekunden < 86400) {
        var stunden = Math.floor(diffSekunden / 3600);
        return 'vor ' + stunden + ' h';
    }
    var tage = Math.floor(diffSekunden / 86400);
    return 'vor ' + tage + ' ' + (tage === 1 ? 'Tag' : 'Tagen');
}

function formatiereBar(wert) {
    var zahl = parseNumber(wert);
    if (zahl == null) {
        return '--';
    }
    return zahl.toFixed(2) + ' bar';
}

function reifendruckStatus(ist, soll, weichWarnung, hartWarnung) {
    var istZahl = parseNumber(ist);
    var sollZahl = parseNumber(soll);
    if (istAktiv(hartWarnung)) {
        return {klasse: 'kritisch', text: 'Kritisch'};
    }
    if (istAktiv(weichWarnung)) {
        return {klasse: 'warnung', text: 'Warnung'};
    }
    if (istZahl == null) {
        return {klasse: 'unbekannt', text: 'Unbekannt'};
    }
    if (istZahl < 2.1 || istZahl > 3.7) {
        return {klasse: 'kritisch', text: 'Kritisch'};
    }
    if (sollZahl != null) {
        var abweichung = Math.abs(istZahl - sollZahl);
        if (abweichung >= 0.4) {
            return {klasse: 'kritisch', text: 'Abweichung'};
        }
        if (abweichung >= 0.2) {
            return {klasse: 'warnung', text: 'Prüfen'};
        }
    } else if (istZahl < 2.7 || istZahl > 3.3) {
        return {klasse: 'warnung', text: 'Prüfen'};
    }
    return {klasse: 'ok', text: 'OK'};
}

function reifendruckHinweis(eintrag, status) {
    var hinweise = [];
    if (istAktiv(eintrag.hart)) {
        hinweise.push('harte Warnung');
    }
    if (istAktiv(eintrag.weich)) {
        hinweise.push('weiche Warnung');
    }
    if (status.klasse === 'kritisch' && hinweise.length === 0) {
        hinweise.push('kritische Abweichung');
    } else if (status.klasse === 'warnung' && hinweise.length === 0) {
        hinweise.push('prüfen');
    }
    return hinweise.join(', ') || status.text;
}

function reifendruckMitLetztenWerten(vehicle) {
    var ergebnis = Object.assign({}, vehicle || {});
    REIFENDRUCK_CACHE_FELDER.forEach(function(feld) {
        var wert = ergebnis[feld];
        var istDruckfeld = feld.indexOf('tpms_pressure_') === 0 ||
            feld.indexOf('tpms_rcp_') === 0;
        var hatWert = istDruckfeld ? parseNumber(wert) != null : wert != null;
        if (hatWert) {
            letzterReifendruckStatus[feld] = wert;
            return;
        }
        if (Object.prototype.hasOwnProperty.call(letzterReifendruckStatus, feld)) {
            ergebnis[feld] = letzterReifendruckStatus[feld];
        }
    });
    return ergebnis;
}

function reifendruckReifen(vehicle) {
    vehicle = reifendruckMitLetztenWerten(vehicle);
    var vorneSoll = vehicle.tpms_rcp_front_value;
    var hintenSoll = vehicle.tpms_rcp_rear_value;
    return [
        {
            id: 'VL',
            name: 'Vorne links',
            wert: vehicle.tpms_pressure_fl,
            soll: vorneSoll,
            weich: vehicle.tpms_soft_warning_fl,
            hart: vehicle.tpms_hard_warning_fl,
            zeit: vehicle.tpms_last_seen_pressure_time_fl
        },
        {
            id: 'VR',
            name: 'Vorne rechts',
            wert: vehicle.tpms_pressure_fr,
            soll: vorneSoll,
            weich: vehicle.tpms_soft_warning_fr,
            hart: vehicle.tpms_hard_warning_fr,
            zeit: vehicle.tpms_last_seen_pressure_time_fr
        },
        {
            id: 'HL',
            name: 'Hinten links',
            wert: vehicle.tpms_pressure_rl,
            soll: hintenSoll,
            weich: vehicle.tpms_soft_warning_rl,
            hart: vehicle.tpms_hard_warning_rl,
            zeit: vehicle.tpms_last_seen_pressure_time_rl
        },
        {
            id: 'HR',
            name: 'Hinten rechts',
            wert: vehicle.tpms_pressure_rr,
            soll: hintenSoll,
            weich: vehicle.tpms_soft_warning_rr,
            hart: vehicle.tpms_hard_warning_rr,
            zeit: vehicle.tpms_last_seen_pressure_time_rr
        }
    ];
}

function updateTPMS(vehicle) {
    function set(reifen) {
        var $group = $('#tpms-' + reifen.id);
        var $title = $group.find('title');
        var $text = $group.find('text');
        var $circle = $group.find('circle');
        var val = reifen.wert;
        if (val == null || isNaN(val)) {
            $text.text('--');
            $circle.css('stroke', '#555');
            $group
                .removeClass('tpms-ok tpms-warnung tpms-kritisch')
                .addClass('tpms-unbekannt')
                .attr('aria-label', reifen.name + ': kein Reifendruckwert');
            $title.text(reifen.name + ': kein Reifendruckwert');
            return;
        }
        var num = Number(val);
        $text.text(num.toFixed(1));
        var status = reifendruckStatus(num, reifen.soll, reifen.weich, reifen.hart);
        var color = '#4caf50';
        if (status.klasse === 'warnung') {
            color = '#ff9800';
        }
        if (status.klasse === 'kritisch') {
            color = '#d00';
        }
        $circle.css('stroke', color);
        $group
            .removeClass('tpms-ok tpms-warnung tpms-kritisch tpms-unbekannt')
            .addClass('tpms-' + status.klasse);
        var ziel = parseNumber(reifen.soll);
        var text = reifen.name + ': ' + num.toFixed(2) + ' bar';
        if (ziel != null) {
            text += ', Soll ' + ziel.toFixed(2) + ' bar';
        }
        var alter = formatiereAlter(reifen.zeit);
        if (alter) {
            text += ', Messung ' + alter;
        }
        text += ', Status ' + reifendruckHinweis(reifen, status);
        $group.attr('aria-label', text);
        $title.text(text);
    }
    var reifen = reifendruckReifen(vehicle);
    reifen.forEach(set);
    updateReifendruckKurzstatus(reifen);
}

function updateReifendruckKurzstatus(reifen) {
    var $summary = $('#tpms-summary');
    if (!$summary.length) {
        return;
    }
    var mitDaten = reifen.filter(function(eintrag) {
        return parseNumber(eintrag.wert) != null;
    });
    if (!mitDaten.length) {
        $summary
            .removeClass('tpms-ok tpms-warnung tpms-kritisch')
            .addClass('tpms-unbekannt')
            .text('Reifendruck: --')
            .attr('title', 'Keine Reifendruckwerte')
            .attr('aria-label', 'Keine Reifendruckwerte');
        return;
    }
    var statusKlasse = 'ok';
    var kritische = 0;
    var warnungen = 0;
    var niedrigster = null;
    var juengsteMessung = null;
    mitDaten.forEach(function(eintrag) {
        var status = reifendruckStatus(eintrag.wert, eintrag.soll, eintrag.weich, eintrag.hart);
        if (status.klasse === 'kritisch') {
            kritische += 1;
        } else if (status.klasse === 'warnung') {
            warnungen += 1;
        }
        var wert = parseNumber(eintrag.wert);
        if (wert != null && (niedrigster == null || wert < niedrigster)) {
            niedrigster = wert;
        }
        var zeit = leseZeitstempelMillis(eintrag.zeit);
        if (zeit != null && (juengsteMessung == null || zeit > juengsteMessung)) {
            juengsteMessung = zeit;
        }
    });
    var text = 'Reifendruck OK';
    if (kritische > 0) {
        statusKlasse = 'kritisch';
        text = kritische + ' kritisch';
    } else if (warnungen > 0) {
        statusKlasse = 'warnung';
        text = warnungen === 1 ? '1 Reifen prüfen' : warnungen + ' Reifen prüfen';
    }
    if (niedrigster != null) {
        text += ' · min ' + niedrigster.toFixed(1) + ' bar';
    }
    var alter = formatiereAlter(juengsteMessung);
    if (alter) {
        text += ' · ' + alter;
    }
    $summary
        .removeClass('tpms-ok tpms-warnung tpms-kritisch tpms-unbekannt')
        .addClass('tpms-' + statusKlasse)
        .text(text)
        .attr('title', text)
        .attr('aria-label', text);
}

function updateReifendruckDetails(vehicle) {
    var $details = $('#reifendruck-details');
    if (!$details.length || !configEnabled('reifendruck-details')) {
        $details.empty().hide();
        return;
    }
    var reifen = reifendruckReifen(vehicle);
    var hatDaten = reifen.some(function(eintrag) {
        return parseNumber(eintrag.wert) != null;
    });
    if (!hatDaten) {
        $details.empty().hide();
        return;
    }
    var kritische = 0;
    var warnungen = 0;
    var rows = reifen.map(function(eintrag) {
        var ist = parseNumber(eintrag.wert);
        var soll = parseNumber(eintrag.soll);
        var status = reifendruckStatus(ist, soll, eintrag.weich, eintrag.hart);
        if (status.klasse === 'kritisch') {
            kritische += 1;
        } else if (status.klasse === 'warnung') {
            warnungen += 1;
        }
        var abweichung = '--';
        if (ist != null && soll != null) {
            var diff = ist - soll;
            abweichung = (diff >= 0 ? '+' : '') + diff.toFixed(2) + ' bar';
        }
        var alter = formatiereAlter(eintrag.zeit) || '--';
        return '<tr class="reifendruck-' + status.klasse + '">' +
               '<th>' + escapeHtml(eintrag.name) + '</th>' +
               '<td>' + formatiereBar(ist) + '</td>' +
               '<td>' + formatiereBar(soll) + '</td>' +
               '<td>' + escapeHtml(abweichung) + '</td>' +
               '<td>' + escapeHtml(alter) + '</td>' +
               '<td><span class="tpms-status tpms-status-' + status.klasse + '">' +
               escapeHtml(reifendruckHinweis(eintrag, status)) + '</span></td>' +
               '</tr>';
    });
    var zusammenfassung = 'Reifendruck im Zielbereich';
    if (kritische > 0) {
        zusammenfassung = kritische + ' kritische ' +
            (kritische === 1 ? 'Abweichung' : 'Abweichungen');
    } else if (warnungen > 0) {
        zusammenfassung = warnungen === 1 ? '1 Reifen prüfen' : warnungen + ' Reifen prüfen';
    }
    var html = '<h3>Reifendruckdetails</h3>' +
               '<p class="panel-summary">' + escapeHtml(zusammenfassung) + '</p>' +
               '<table><thead><tr>' +
               '<th>Reifen</th><th>Ist</th><th>Soll</th><th>Abweichung</th><th>Messung</th><th>Status</th>' +
               '</tr></thead><tbody>' + rows.join('') + '</tbody></table>';
    $details.html(html).show();
}

function updateBrakeLights(vehicle) {
    var $lights = $('#brake-lights');
    if (!$lights.length) {
        return;
    }
    vehicle = vehicle || {};
    var pedalAktiv = istAktiv(vehicle.brake_pedal);
    var bremsdruck = parseNumber(vehicle.brake_pedal_pos);
    var aktiv = pedalAktiv || (bremsdruck != null && bremsdruck > 0.1);
    var titel = aktiv ? 'Bremslicht an' : 'Bremslicht aus';
    if (bremsdruck != null) {
        titel += ' · Bremsdruck ' + bremsdruck.toFixed(1);
    }
    $lights
        .toggleClass('is-active', aktiv)
        .attr('aria-label', titel)
        .attr('title', titel);
    $lights.find('title').text(titel);
}

function updateOpenings(vehicle, charge) {
    var parts = [
        {key: 'df', id: 'door-fl'},
        {key: 'dr', id: 'door-rl'},
        {key: 'pf', id: 'door-fr'},
        {key: 'pr', id: 'door-rr'},
        {key: 'fd_window', id: 'window-fl'},
        {key: 'rd_window', id: 'window-rl'},
        {key: 'fp_window', id: 'window-fr'},
        {key: 'rp_window', id: 'window-rr'},
        {key: 'ft', id: 'frunk'},
        {key: 'rt', id: 'trunk'},
        {key: 'charge_port_door_open', id: 'charge-port', src: charge}
    ];

    parts.forEach(function(p) {
        var obj = p.src || vehicle;
        if (!obj || obj[p.key] == null) return;
        // Values are 0 when the part is closed and non-zero when open.
        // Use loose inequality to handle any non-zero value as "open".
        var open = Number(obj[p.key]) !== 0;
        var $el = $('#' + p.id);
        $el.attr('class', open ? 'part-open' : 'part-closed');
        if (p.id.startsWith('window-')) {
            $el.toggleClass('window-open', open);
        }
    });

    var doorParts = ['door-fl', 'door-fr', 'door-rl', 'door-rr'];
    doorParts.forEach(function(id) {
        $('#' + id).toggleClass('blue-highlight', HIGHLIGHT_BLUE);
    });

    var windowParts = ['window-fl', 'window-fr', 'window-rl', 'window-rr'];
    windowParts.forEach(function(id) {
        $('#' + id).toggleClass('window-highlight', HIGHLIGHT_BLUE);
    });

    var srPct = vehicle.sun_roof_percent_open;
    var srState = vehicle.sun_roof_state;
    var sunroofStatusKnown = vehicle.sun_roof_status_available !== false &&
        (srPct != null || srState);
    if (sunroofStatusKnown) {
        var pct = Number(srPct);
        var state = srState == null ? '' : String(srState).toLowerCase();
        var open = state && state !== 'closed' && (isNaN(pct) || pct > 0);
        $('#sunroof').attr('class', open ? 'part-open' : 'part-closed');
        $('#sunroof-percent').text(open && !isNaN(pct) ? Math.round(pct) + '%' : '');
        $('#sunroof title').text(open ? 'Schiebedach offen' : 'Schiebedach geschlossen');
    } else {
        $('#sunroof').attr('class', 'part-unknown');
        $('#sunroof-percent').text('?');
        $('#sunroof title').text('Schiebedachstatus über Fleet Telemetry nicht verfügbar');
    }

    var charging = charge && charge.charging_state === 'Charging';
    $('#charge-cable').toggleClass('charging', charging);
    updateBrakeLights(vehicle);
}

var MAX_SPEED = 250;
var MIN_TEMP = -20;
var MAX_TEMP = 50;

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

function updateSpeedometer(speed, power, chargingState) {
    if (speed == null) speed = 0;
    if (power == null) power = 0;
    var kmh = Math.round(speed * MILES_TO_KM);
    var angle = (Math.min(Math.max(kmh, 0), MAX_SPEED) / MAX_SPEED) * 180 - 90;
    $('#speedometer-needle').attr('transform', 'rotate(' + angle + ' 60 50)');
    $('#speed-value').text(kmh + ' km/h');
    var text = Math.round(power) + ' kW';
    if (chargingState === 'Charging') {
        text += ' (Ladeleistung)';
    } else if (power < 0) {
        text += ' (Rekuperation)';
    }
    $('#power-value').text(text);
}

function updatePedalPosition(value) {
    var $needle = $('#pedal-position-needle');
    var $outline = $('#pedal-position-needle-outline');
    if (!$needle.length && !$outline.length) {
        return;
    }
    var position = parseNumber(value);
    if (position == null) {
        $outline.attr('transform', 'rotate(-90 60 50)').removeClass('is-active');
        $needle
            .attr('transform', 'rotate(-90 60 50)')
            .removeClass('is-active');
        $needle.find('title').text('Pedalposition nicht verfügbar');
        return;
    }
    var prozent = Math.min(Math.max(position, 0), 100);
    var winkel = prozent / 100 * 180 - 90;
    $outline
        .attr('transform', 'rotate(' + winkel + ' 60 50)')
        .addClass('is-active');
    $needle
        .attr('transform', 'rotate(' + winkel + ' 60 50)')
        .addClass('is-active');
    $needle.find('title').text('Pedalposition ' + prozent.toFixed(1) + ' %');
}

function updateOdometer(value) {
    if (value == null || isNaN(value)) {
        $('#odometer-value').text('--');
        return;
    }
    var km = Number(value) * MILES_TO_KM;
    var formatted = km
        .toFixed(0)
        .replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    $('#odometer-value').text(formatted + ' km');
}

function updateThermometers(inside, outside, battery, batteryMin, batteryMax) {
    var range = MAX_TEMP - MIN_TEMP;
    if (battery != null && !isNaN(battery)) {
        letzteBatterieTemperatur = battery;
    } else if (letzteBatterieTemperatur != null) {
        battery = letzteBatterieTemperatur;
    }
    function set(prefix, temp, labelPrefix) {
        var $level = $('#' + prefix + '-level');
        var $bulb = $('#' + prefix + '-bulb');
        var $label = $('#' + prefix + '-temp-value');
        if (!$level.length || !$bulb.length || !$label.length) {
            return;
        }
        var missing = temp == null || isNaN(temp);
        var value = missing ? 0 : temp;
        var clamped = Math.max(MIN_TEMP, Math.min(MAX_TEMP, value));
        var h = (clamped - MIN_TEMP) / range * 40;
        var y = 5 + 40 - h;
        var color = '#d00';
        if (value < 15) {
            color = '#06c';
        } else if (value < 25) {
            color = '#4caf50';
        } else if (value < 30) {
            color = '#ff9800';
        }
        $level.attr('y', y).attr('height', h).css('fill', color);
        $bulb.css('fill', color);
        var label = missing ? '-.- °C' : temp.toFixed(1) + ' °C';
        if (prefix === 'battery') {
            label = 'Ø ' + label;
        }
        $label.text(labelPrefix + ': ' + label);
    }
    set('inside', inside, 'Innen');
    set('outside', outside, 'Außen');
    set('battery', battery, 'Batterie');
    aktualisiereBatterieTemperaturGrenzen(batteryMin, batteryMax);
}

function aktualisiereBatterieTemperaturGrenzen(minimum, maximum) {
    var minWert = parseNumber(minimum);
    var maxWert = parseNumber(maximum);
    if (minWert != null) {
        letzteBatterieTemperaturMinimum = minWert;
    } else {
        minWert = letzteBatterieTemperaturMinimum;
    }
    if (maxWert != null) {
        letzteBatterieTemperaturMaximum = maxWert;
    } else {
        maxWert = letzteBatterieTemperaturMaximum;
    }
    if (minWert != null && maxWert != null && minWert > maxWert) {
        var tausch = minWert;
        minWert = maxWert;
        maxWert = tausch;
    }
    var minText = minWert == null ? '-- °C' : minWert.toFixed(1) + ' °C';
    var maxText = maxWert == null ? '-- °C' : maxWert.toFixed(1) + ' °C';
    $('#battery-temp-min-value').text('Min: ' + minText);
    $('#battery-temp-max-value').text('Max: ' + maxText);
    $('#battery-temp-minmax')
        .attr('title', 'Batterietemperatur Min/Max: ' + minText + ' / ' + maxText)
        .attr('aria-label', 'Batterietemperatur Minimum ' + minText + ', Maximum ' + maxText);
}

function updateBatteryIndicator(level, rangeMiles, chargingState, heaterOn) {
    var pct = level != null && !isNaN(level) ? Math.max(0, Math.min(100, Number(level))) : 0;
    var pctText = Math.round(pct);
    var range = rangeMiles != null ? Math.round(rangeMiles * MILES_TO_KM) : '?';
    var charging = chargingState === 'Charging';
    var heating = !!heaterOn;
    var clip = 'clip-path: inset(' + (100 - pct) + '% 0 0 0)';
    var html = '<div class="battery">';
    html += '<div class="level" style="' + clip + '"></div>';
    if (charging) {
        html += '<div class="bolt">\u26A1</div>';
    }
    if (heating) {
        html += '<div class="heater">\uD83D\uDD25</div>';
    }
    html += '</div>';
    html += '<div class="battery-value">' + pctText + '%</div>';
    html += '<div class="range">' + range + ' km</div>';
    $('#battery-indicator').html(html);
}

function batteryBar(level) {
    var pct = level != null && !isNaN(level) ? Math.max(0, Math.min(100, Number(level))) : 0;
    var pctText = Math.round(pct);
    var clip = 'clip-path: inset(' + (100 - pct) + '% 0 0 0)';
    return '<div class="battery-block"><div class="battery"><div class="level" style="' + clip + '"></div></div><div class="battery-value">' + pctText + '%</div></div>';
}

var lastChargeInfo = null;
var lastChargeStop = null;
var lastEnergyAdded = null;
var letzteLadedauerMs = null;
var letzterLadezuwachsProzent = null;
var lastChargeSessionStartMs = null;
var lastChargingState = null;
var lastChargingInfoHtml = null;
var letzteBatterieTemperatur = null;
var letzteBatterieTemperaturMinimum = null;
var letzteBatterieTemperaturMaximum = null;
var letzteTechnischeDetailsHtml = null;

function parseNumber(value) {
    if (value == null || value === '') {
        return null;
    }
    var num = Number(value);
    if (!isFinite(num)) {
        return null;
    }
    return num;
}

function wertIstOffen(value) {
    if (value == null) {
        return false;
    }
    if (typeof value === 'boolean') {
        return value;
    }
    if (typeof value === 'number') {
        return Math.abs(value) > 0.001;
    }
    if (typeof value === 'string') {
        var norm = value.trim().toLowerCase();
        if (!norm) {
            return false;
        }
        if (['0', 'false', 'no', 'none', 'null', 'n/a', 'unknown'].indexOf(norm) !== -1) {
            return false;
        }
        if (['closed', 'close', 'closing', 'locked'].indexOf(norm) !== -1) {
            return false;
        }
        var zahl = parseNumber(norm);
        if (zahl != null) {
            return Math.abs(zahl) > 0.001;
        }
        return true;
    }
    return !!value;
}

function fahrzeugIstOffen(vehicle) {
    if (!vehicle) {
        return false;
    }
    if (istAktiv(vehicle.is_user_present) ||
        istAktiv(vehicle.user_present) ||
        istAktiv(vehicle.occupant_present) ||
        istAktiv(vehicle.is_driver_present) ||
        istAktiv(vehicle.driver_present)) {
        return true;
    }
    if (vehicle.locked === false) {
        return true;
    }
    var oeffnungsfelder = [
        'df',
        'dr',
        'pf',
        'pr',
        'ft',
        'rt',
        'fd_window',
        'rd_window',
        'fp_window',
        'rp_window'
    ];
    for (var i = 0; i < oeffnungsfelder.length; i++) {
        if (wertIstOffen(vehicle[oeffnungsfelder[i]])) {
            return true;
        }
    }
    if (wertIstOffen(vehicle.sun_roof_percent_open)) {
        return true;
    }
    return wertIstOffen(vehicle.sun_roof_state);
}

function fahrzeugStehtFuerVorklimatisierung(drive) {
    drive = drive || {};
    var gang = normalizeShiftState(drive.shift_state);
    if (gang && gang !== 'P') {
        return false;
    }

    var geschwindigkeit = parseNumber(drive.speed);
    if (geschwindigkeit != null && Math.abs(geschwindigkeit) > 0.05) {
        return false;
    }

    return gang === 'P' || geschwindigkeit != null;
}

function darfVorklimatisierungAnzeigen(data, drive) {
    if (data && fahrzeugIstOffen(data.vehicle_state)) {
        return false;
    }
    if (data && typeof data.preconditioning_display_allowed !== 'undefined') {
        return istAktiv(data.preconditioning_display_allowed);
    }
    return fahrzeugStehtFuerVorklimatisierung(drive);
}

function parseChargeSessionStart(value) {
    var num = parseNumber(value);
    if (num != null) {
        if (num < 1e12) {
            return num * 1000;
        }
        return num;
    }
    if (typeof value === 'string') {
        var parsed = Date.parse(value);
        if (!isNaN(parsed)) {
            return parsed;
        }
    }
    return null;
}

function formatChargeDuration(durationMs) {
    if (durationMs == null || !isFinite(durationMs) || durationMs < 0) {
        return null;
    }
    var totalMinutes = Math.floor(durationMs / 60000);
    var hours = Math.floor(totalMinutes / 60);
    var minutes = totalMinutes % 60;
    var parts = [];
    if (hours > 0) {
        parts.push(hours + ' h');
    }
    parts.push(minutes + ' min');
    return parts.join(' ');
}

function formatPercentDelta(delta) {
    if (delta == null || !isFinite(delta) || delta < 0) {
        return null;
    }
    var rounded = Math.round(delta * 10) / 10;
    if (rounded < 0) {
        return null;
    }
    if (Math.abs(rounded - Math.round(rounded)) < 0.05) {
        return Math.round(rounded).toString();
    }
    return rounded.toFixed(1);
}

function updateV2LInfos(charge, drive) {
    var $info = $('#v2l-infos');
    if (!charge || !CONFIG['v2l-infos']) {
        $info.empty().hide();
        return;
    }
    var cond = charge.charging_state === 'Starting' &&
               String(charge.charger_power) === '4' &&
               charge.charge_port_color === 'FlashingGreen' &&
               charge.conn_charge_cable === 'IEC';
    if (cond) {
        var html = '<p><center><h2><a href="https://bit.ly/49Vp3wN" target="_blank">V2L-Adapter</a> (Vehicle 2 Load) eingesteckt. Nun stehen mir 220V/18A (4kW) zur Verfügung.<br> ' +
                   'Der Kaffeevollautomat wartet auf dich. Komm vorbei.</h2></center></p>';
        var lat = drive && drive.latitude;
        var lng = drive && drive.longitude;
        if (lat != null && lng != null) {
            var url = 'https://www.google.com/maps/search/?api=1&query=' +
                      encodeURIComponent(lat + ',' + lng);
            html += '<p><center><h3><a href="' + url + '" target="_blank">Standort in Google Maps</a></h3></center></p>';
        }
        $info.html(html).show();
    } else {
        $info.empty().hide();
    }
}

function istAktiv(wert) {
    if (typeof wert === 'string') {
        var norm = wert.toLowerCase();
        return norm === 'true' || norm === '1' || norm === 'on' || norm === 'yes';
    }
    return !!wert;
}

function formatiereTemperatur(wert) {
    var zahl = parseNumber(wert);
    if (zahl == null) {
        return '';
    }
    return zahl.toFixed(1) + ' °C';
}

function vorklimatisierungZieltemperatur(climate) {
    var fahrer = formatiereTemperatur(climate && climate.driver_temp_setting);
    var beifahrer = formatiereTemperatur(climate && climate.passenger_temp_setting);
    if (fahrer && beifahrer && fahrer !== beifahrer) {
        return fahrer + ' / ' + beifahrer;
    }
    return fahrer || beifahrer;
}

function updatePreconditioningInfo(climate, charge, drive, anzeigenErlaubt) {
    var $info = $('#preconditioning-info');
    if (!$info.length || !configEnabled('preconditioning-info')) {
        $info.empty().hide();
        return;
    }

    climate = climate || {};
    charge = charge || {};
    if (typeof anzeigenErlaubt === 'undefined') {
        anzeigenErlaubt = fahrzeugStehtFuerVorklimatisierung(drive);
    }
    if (!anzeigenErlaubt) {
        $info.empty().hide();
        return;
    }

    var vorklimatisiert = istAktiv(climate.is_preconditioning);
    var automatischeKlima = istAktiv(climate.is_auto_conditioning_on);
    var planAktiv = istAktiv(charge.preconditioning_enabled);
    var klimaAn = istAktiv(climate.is_climate_on);
    var batterieHeizt = istAktiv(charge.battery_heater_on) ||
                        istAktiv(climate.battery_heater);
    var heizleistungFehlt = istAktiv(charge.not_enough_power_to_heat) ||
                            istAktiv(climate.battery_heater_no_power);
    var relevant = vorklimatisiert || automatischeKlima || planAktiv ||
                   (batterieHeizt && (vorklimatisiert || automatischeKlima || klimaAn)) ||
                   heizleistungFehlt;
    if (!relevant) {
        $info.empty().hide();
        return;
    }

    var titel = 'Vorklimatisierung';
    var zusammenfassung = 'Vorklimatisierung aktiv';
    if (vorklimatisiert) {
        zusammenfassung = 'Vorklimatisierung läuft';
    } else if (automatischeKlima) {
        zusammenfassung = 'Automatische Klimatisierung läuft';
    } else if (planAktiv) {
        zusammenfassung = 'Vorklimatisierung für geplante Abfahrt aktiv';
    } else if (heizleistungFehlt) {
        zusammenfassung = 'Heizleistung begrenzt';
    }

    var rows = [];
    if (vorklimatisiert || automatischeKlima || klimaAn) {
        var status = klimaAn ? 'Klima läuft' : 'Klima bereit';
        if (vorklimatisiert) {
            status = 'Vorklimatisierung läuft';
        } else if (automatischeKlima) {
            status = 'Automatische Klimatisierung läuft';
        }
        rows.push('<tr><th>Status:</th><td>' + escapeHtml(status) + '</td></tr>');
    }

    var innen = formatiereTemperatur(climate.inside_temp);
    if (innen) {
        rows.push('<tr><th>Innenraum:</th><td>' + escapeHtml(innen) + '</td></tr>');
    }
    var ziel = vorklimatisierungZieltemperatur(climate);
    if (ziel) {
        rows.push('<tr><th>Zieltemperatur:</th><td>' + escapeHtml(ziel) + '</td></tr>');
    }
    var luefter = parseNumber(climate.fan_status);
    if (luefter != null && luefter > 0) {
        rows.push('<tr><th>Lüfter:</th><td>Stufe ' + escapeHtml(String(luefter)) + '</td></tr>');
    }

    var abfahrt = planAktiv ? geplanteAbfahrtszeit(charge) : null;
    if (abfahrt) {
        rows.push('<tr><th>Geplante Abfahrt:</th><td>' + escapeHtml(abfahrt) + '</td></tr>');
    }
    if (planAktiv) {
        var planText = 'aktiv';
        var zeitraum = beschreibeVorklimatisierungsZeitraum(
            charge.preconditioning_times
        );
        if (zeitraum) {
            planText += ' (' + zeitraum + ')';
        }
        rows.push('<tr><th>Planung:</th><td>' + escapeHtml(planText) + '</td></tr>');
    }
    if (batterieHeizt || heizleistungFehlt) {
        var batterieText = batterieHeizt ? 'Batterieheizung aktiv' : 'Batterieheizung aus';
        if (heizleistungFehlt) {
            batterieText += ', Heizleistung begrenzt';
        }
        rows.push('<tr><th>Batterie:</th><td>' + escapeHtml(batterieText) + '</td></tr>');
    }

    $info.html(
        '<h3>' + escapeHtml(titel) + '</h3>' +
        '<p class="panel-summary">' + escapeHtml(zusammenfassung) + '</p>' +
        '<table>' + rows.join('') + '</table>'
    ).show();
}

function beschreibeZeitraum(wert) {
    if (!wert) {
        return '';
    }
    var text = String(wert);
    var norm = text.toLowerCase();
    if (norm === 'all_week') {
        return 'täglich';
    }
    if (norm === 'weekdays') {
        return 'werktags';
    }
    if (norm === 'weekends') {
        return 'am Wochenende';
    }
    return text.replace(/_/g, ' ');
}

function beschreibeVorklimatisierungsZeitraum(wert) {
    if (!wert) {
        return '';
    }
    if (String(wert).toLowerCase() === 'all_week') {
        return '';
    }
    return beschreibeZeitraum(wert);
}

function geplanteAbfahrtszeit(charge) {
    var absoluterZeitpunkt = charge.scheduled_departure_time;
    if (absoluterZeitpunkt != null && absoluterZeitpunkt !== '') {
        var millis = leseZeitstempelMillis(absoluterZeitpunkt);
        if (millis != null) {
            if (millis <= Date.now()) {
                return null;
            }
            return formatiereZeitpunkt(absoluterZeitpunkt);
        }
    }
    var zeit = formatiereZeitAusMinuten(charge.scheduled_departure_time_minutes);
    if (zeit) {
        return zeit;
    }
    return null;
}

function formatiereZukünftigenZeitpunkt(wert) {
    var millis = leseZeitstempelMillis(wert);
    if (millis == null || millis <= Date.now()) {
        return null;
    }
    return formatiereZeitpunkt(wert);
}

function ladeRestzeitMinuten(charge) {
    var minuten = parseNumber(charge.minutes_to_full_charge);
    if (minuten != null) {
        return minuten;
    }
    var stunden = parseNumber(charge.time_to_full_charge);
    if (stunden != null) {
        return stunden * 60;
    }
    return null;
}

function ladeendeText(minuten) {
    var dauer = formatiereDauerMinuten(minuten);
    if (!dauer) {
        return null;
    }
    var ende = new Date(Date.now() + Math.max(0, Math.round(minuten)) * 60000);
    var uhrzeit = formatiereUhrzeit(ende);
    if (uhrzeit) {
        return dauer + ' (ca. ' + uhrzeit + ' Uhr)';
    }
    return dauer;
}

function updateLadeplanungInfo(charge, drive, data) {
    var $info = $('#ladeplanung-info');
    if (!$info.length || !configEnabled('ladeplanung-info')) {
        $info.empty().hide();
        return;
    }
    if (!charge) {
        $info.empty().hide();
        return;
    }

    var abfahrt = geplanteAbfahrtszeit(charge);
    var ladezustand = charge.charging_state || '';
    var laedt = ladezustand === 'Charging' || ladezustand === 'Starting';
    var ladezeitMinuten = ladeRestzeitMinuten(charge);
    var hatRestzeit = ladezeitMinuten != null && ladezeitMinuten > 0;
    var vorklimatisierungErlaubt = darfVorklimatisierungAnzeigen(data, drive);
    var vorklimatisierung = vorklimatisierungErlaubt &&
                            istAktiv(charge.preconditioning_enabled);
    var nebenzeit = istAktiv(charge.off_peak_charging_enabled);
    var geplantesLaden = charge.scheduled_charging_mode && charge.scheduled_charging_mode !== 'Off';
    var geplantAusstehend = istAktiv(charge.scheduled_charging_pending);
    var batterieHeizt = istAktiv(charge.battery_heater_on);
    var heizleistungFehlt = istAktiv(charge.not_enough_power_to_heat);
    var relevant = abfahrt || laedt || hatRestzeit || vorklimatisierung ||
                   nebenzeit || geplantesLaden || geplantAusstehend ||
                   batterieHeizt || heizleistungFehlt;
    if (!relevant) {
        $info.empty().hide();
        return;
    }

    var rows = [];
    if (abfahrt) {
        rows.push('<tr><th>Geplante Abfahrt:</th><td>' + escapeHtml(abfahrt) + '</td></tr>');
    }
    if (charge.charge_limit_soc != null) {
        rows.push('<tr><th>Ladegrenze:</th><td>' + escapeHtml(String(charge.charge_limit_soc)) + ' %</td></tr>');
    }
    if (hatRestzeit) {
        rows.push('<tr><th>Bis Ladegrenze:</th><td>' + escapeHtml(ladeendeText(ladezeitMinuten)) + '</td></tr>');
    } else if (laedt) {
        rows.push('<tr><th>Bis Ladegrenze:</th><td>keine Restzeit gemeldet</td></tr>');
    }
    if (geplantesLaden || geplantAusstehend) {
        var ladeModus = charge.scheduled_charging_mode || 'aktiv';
        if (geplantAusstehend) {
            ladeModus += ' (wartet auf Start)';
        }
        rows.push('<tr><th>Geplantes Laden:</th><td>' + escapeHtml(ladeModus) + '</td></tr>');
    }
    var startZeit = formatiereZukünftigenZeitpunkt(charge.scheduled_charging_start_time);
    if (startZeit) {
        rows.push('<tr><th>Geplanter Ladestart:</th><td>' + escapeHtml(startZeit) + '</td></tr>');
    }
    if (vorklimatisierungErlaubt && (abfahrt || vorklimatisierung)) {
        var vorklimaText = vorklimatisierung ? 'aktiv' : 'aus';
        var vorklimaZeitraum = beschreibeVorklimatisierungsZeitraum(
            charge.preconditioning_times
        );
        if (vorklimaZeitraum) {
            vorklimaText += ' (' + vorklimaZeitraum + ')';
        }
        rows.push('<tr><th>Vorklimatisierung:</th><td>' + escapeHtml(vorklimaText) + '</td></tr>');
    }
    if (abfahrt || nebenzeit) {
        var nebenzeitText = nebenzeit ? 'aktiv' : 'aus';
        var nebenzeitZeitraum = beschreibeZeitraum(charge.off_peak_charging_times);
        if (nebenzeitZeitraum) {
            nebenzeitText += ' (' + nebenzeitZeitraum + ')';
        }
        rows.push('<tr><th>Nebenzeit-Laden:</th><td>' + escapeHtml(nebenzeitText) + '</td></tr>');
    }
    if (batterieHeizt || heizleistungFehlt) {
        var heizungText = batterieHeizt ? 'Batterieheizung aktiv' : 'Batterieheizung aus';
        if (heizleistungFehlt) {
            heizungText += ', Heizleistung begrenzt';
        }
        rows.push('<tr><th>Batterieheizung:</th><td>' + escapeHtml(heizungText) + '</td></tr>');
    }

    var zusammenfassung = 'Ladeplanung aktiv';
    if (hatRestzeit) {
        var ende = new Date(Date.now() + Math.max(0, Math.round(ladezeitMinuten)) * 60000);
        var endeUhrzeit = formatiereUhrzeit(ende);
        if (endeUhrzeit) {
            zusammenfassung = 'Ladeziel gegen ' + endeUhrzeit + ' Uhr';
        }
    } else if (abfahrt) {
        zusammenfassung = 'Abfahrt um ' + abfahrt;
    }
    $info.html(
        '<h3>Ladeplanung</h3>' +
        '<p class="panel-summary">' + escapeHtml(zusammenfassung) + '</p>' +
        '<table>' + rows.join('') + '</table>'
    ).show();
}

function updateChargingInfo(charge, wurzelDaten) {
    var $info = $('#charging-info');
    if (!charge) {
        if (lastChargingInfoHtml !== '') {
            $info.empty().hide();
            lastChargingInfoHtml = '';
        } else {
            $info.hide();
        }
        return;
    }

    if (charge.last_charge_energy_added != null && !isNaN(charge.last_charge_energy_added)) {
        lastEnergyAdded = Number(charge.last_charge_energy_added);
    }

    var state = charge.charging_state;
    var now = Date.now();
    var sessionStartMsAktuell = parseChargeSessionStart(charge.charge_session_start);
    var hatLadeStart = state === 'Charging' || state === 'Starting';
    var neuerLadeStart = false;
    if (sessionStartMsAktuell != null && lastChargeSessionStartMs != null && sessionStartMsAktuell !== lastChargeSessionStartMs) {
        neuerLadeStart = true;
    }
    if (hatLadeStart && lastChargingState && lastChargingState !== 'Charging' && lastChargingState !== 'Starting') {
        neuerLadeStart = true;
    }
    if (hatLadeStart && lastChargeStop != null) {
        neuerLadeStart = true;
    }
    if (neuerLadeStart) {
        letzterLadezuwachsProzent = null;
        letzteLadedauerMs = null;
    }

    if (state === 'Charging') {
        lastChargeInfo = JSON.parse(JSON.stringify(charge));
        lastChargeStop = null;
        if (charge.charge_energy_added != null && !isNaN(charge.charge_energy_added)) {
            lastEnergyAdded = Number(charge.charge_energy_added);
        }
    } else {
        if (lastChargeInfo && !lastChargeStop) {
            lastChargeStop = now;
        }
        if (charge.charge_energy_added != null && !isNaN(charge.charge_energy_added)) {
            lastEnergyAdded = Number(charge.charge_energy_added);
        } else if (lastEnergyAdded == null && charge.last_charge_energy_added != null && !isNaN(charge.last_charge_energy_added)) {
            lastEnergyAdded = Number(charge.last_charge_energy_added);
        }
    }

    var showFull = false;
    var startSoc = null;
    var currentSoc = null;
    var berechneterZuwachsProzent = null;
    if (state === 'Charging') {
        showFull = true;
    } else if (lastChargeStop && now - lastChargeStop <= 600000) {
        charge = lastChargeInfo || charge;
        showFull = true;
    }

    var durationText = null;
    var addedPercentText = null;
    var lastChargeDurationText = null;
    var lastChargeAddedPercentText = null;
    var lastChargeStartSoc = null;
    var lastChargeEndSoc = null;
    if (showFull) {
        var sessionStartRaw = charge ? charge.charge_session_start : null;
        if (sessionStartRaw == null && lastChargeInfo) {
            sessionStartRaw = lastChargeInfo.charge_session_start;
        }
        var sessionStartMs = parseChargeSessionStart(sessionStartRaw);
        durationText = formatChargeDuration(sessionStartMs != null ? now - sessionStartMs : null);

        startSoc = parseNumber(charge ? charge.charge_session_start_soc : null);
        if (startSoc == null && lastChargeInfo) {
            startSoc = parseNumber(lastChargeInfo.charge_session_start_soc);
        }
        currentSoc = parseNumber(charge ? charge.battery_level : null);
        if (currentSoc == null && charge) {
            currentSoc = parseNumber(charge.usable_battery_level);
        }
        if (currentSoc == null && lastChargeInfo) {
            currentSoc = parseNumber(lastChargeInfo.battery_level);
            if (currentSoc == null) {
                currentSoc = parseNumber(lastChargeInfo.usable_battery_level);
            }
        }
        if (startSoc != null && currentSoc != null) {
            berechneterZuwachsProzent = currentSoc - startSoc;
            addedPercentText = formatPercentDelta(berechneterZuwachsProzent);
        }
    }

    var letzteLadedauerQuelle = charge ? charge.last_charge_duration_s : null;
    if (letzteLadedauerQuelle == null && wurzelDaten) {
        letzteLadedauerQuelle = wurzelDaten.last_charge_duration_s;
    }
    if (letzteLadedauerQuelle != null && !isNaN(letzteLadedauerQuelle)) {
        letzteLadedauerMs = Number(letzteLadedauerQuelle) * 1000;
    }
    var letzterLadezuwachsQuelle = charge ? charge.last_charge_added_percent : null;
    if (letzterLadezuwachsQuelle == null && wurzelDaten) {
        letzterLadezuwachsQuelle = wurzelDaten.last_charge_added_percent;
    }
    var letzteLadezuwachsQuelleTyp = null;
    var neuerLadeStartOhneStartSoc = neuerLadeStart && startSoc == null;
    if (
        letzterLadezuwachsQuelle != null
        && !isNaN(letzterLadezuwachsQuelle)
        && !neuerLadeStartOhneStartSoc
    ) {
        letzterLadezuwachsProzent = Number(letzterLadezuwachsQuelle);
        letzteLadezuwachsQuelleTyp = 'letzte_session';
    } else if (berechneterZuwachsProzent != null) {
        letzterLadezuwachsProzent = berechneterZuwachsProzent;
        letzteLadezuwachsQuelleTyp = 'aktuelle_session';
    }
    if (neuerLadeStart && berechneterZuwachsProzent != null) {
        letzterLadezuwachsProzent = berechneterZuwachsProzent;
        letzteLadezuwachsQuelleTyp = 'aktuelle_session';
    }
    if (letzteLadedauerMs != null) {
        lastChargeDurationText = formatChargeDuration(letzteLadedauerMs);
    }
    if (letzterLadezuwachsProzent != null) {
        var lastChargePercentText = formatPercentDelta(letzterLadezuwachsProzent);
        if (!lastChargePercentText) {
            lastChargePercentText = letzterLadezuwachsProzent.toFixed(1);
        }
        lastChargeAddedPercentText = lastChargePercentText;
    }
    if (lastChargeAddedPercentText) {
        lastChargeAddedPercentText = String(lastChargeAddedPercentText).trim();
        lastChargeAddedPercentText = lastChargeAddedPercentText.replace(/\s*%+\s*$/, '');
        if (lastChargeAddedPercentText) {
            lastChargeAddedPercentText = lastChargeAddedPercentText + '%';
        }
    }
    if (letzteLadezuwachsQuelleTyp === 'letzte_session') {
        var letzterEndSocQuelle = charge ? charge.last_charge_end_soc : null;
        if (letzterEndSocQuelle == null && wurzelDaten) {
            letzterEndSocQuelle = wurzelDaten.last_charge_end_soc;
        }
        lastChargeEndSoc = parseNumber(letzterEndSocQuelle);
        if (lastChargeEndSoc != null && letzterLadezuwachsProzent != null) {
            lastChargeStartSoc = Number(lastChargeEndSoc) - Number(letzterLadezuwachsProzent);
        }
    } else if (letzteLadezuwachsQuelleTyp === 'aktuelle_session') {
        lastChargeStartSoc = parseNumber(startSoc);
        lastChargeEndSoc = parseNumber(currentSoc);
    }
    var lastChargeSocText = null;
    if (lastChargeEndSoc != null && letzterLadezuwachsProzent != null) {
        if (letzteLadezuwachsQuelleTyp !== 'aktuelle_session') {
            lastChargeStartSoc = Number(lastChargeEndSoc) - Number(letzterLadezuwachsProzent);
        }
    }
    if (lastChargeStartSoc != null && lastChargeEndSoc != null) {
        var startSocText = Math.round(lastChargeStartSoc).toFixed(0);
        var endSocText = Math.round(lastChargeEndSoc).toFixed(0);
        lastChargeSocText = '(' + startSocText + '%-' + endSocText + '%)';
    }
    if (lastChargeSocText) {
        if (lastChargeAddedPercentText) {
            lastChargeAddedPercentText = lastChargeAddedPercentText + ' ' + lastChargeSocText;
        } else {
            lastChargeAddedPercentText = '– ' + lastChargeSocText;
        }
    }

    var rows = [];
    if (showFull) {
        if (charge.charging_state) {
            rows.push('<tr><th>Status:</th><td>' + charge.charging_state + '</td></tr>');
        }
        if (charge.charge_energy_added != null) {
            rows.push('<tr><th>Geladene Energie:</th><td>' + Number(charge.charge_energy_added).toFixed(2) + ' kWh</td></tr>');
            if (durationText) {
                rows.push('<tr><th>Ladedauer:</th><td>' + durationText + '</td></tr>');
            }
            if (addedPercentText) {
                rows.push('<tr><th>% hinzugefügt:</th><td>' + addedPercentText + ' %</td></tr>');
            }
        } else {
            if (durationText) {
                rows.push('<tr><th>Ladedauer:</th><td>' + durationText + '</td></tr>');
            }
            if (addedPercentText) {
                rows.push('<tr><th>% hinzugefügt:</th><td>' + addedPercentText + ' %</td></tr>');
            }
        }
        if (charge.charger_voltage != null) {
            rows.push('<tr><th>Spannung:</th><td>' + Number(charge.charger_voltage).toFixed(0) + ' V</td></tr>');
        }
        if (charge.charge_rate != null) {
            rows.push('<tr><th>Ladestrom:</th><td>' + Number(charge.charge_rate).toFixed(0) + ' A</td></tr>');
        }
        if (charge.charger_power != null) {
            rows.push('<tr><th>Ladeleistung:</th><td>' + Number(charge.charger_power).toFixed(0) + ' kW</td></tr>');
        }
        if (charge.conn_charge_cable) {
            rows.push('<tr><th>Kabel:</th><td>' + charge.conn_charge_cable + '</td></tr>');
        }
        if (charge.fast_charger_brand) {
            rows.push('<tr><th>Schnelllader Marke:</th><td>' + charge.fast_charger_brand + '</td></tr>');
        }
        if (charge.fast_charger_type) {
            rows.push('<tr><th>Schnelllader Typ:</th><td>' + charge.fast_charger_type + '</td></tr>');
        }
        if (charge.minutes_to_full_charge != null) {
            rows.push('<tr><th>Minuten bis Ladegrenze (' + charge.charge_limit_soc + ' %):</th><td>' + Math.round(charge.minutes_to_full_charge) + ' min</td></tr>');
        }
        if (state !== 'Charging' && lastEnergyAdded != null) {
            rows.push('<tr><th>Zuletzt hinzugefügte Energie:</th><td>' + lastEnergyAdded.toFixed(2) + ' kWh</td></tr>');
        }
    } else if (state !== 'Charging' && lastEnergyAdded != null) {
        rows.push('<tr><th>Zuletzt hinzugefügte Energie:</th><td>' + lastEnergyAdded.toFixed(2) + ' kWh</td></tr>');
    }
    if (lastChargeDurationText) {
        rows.push('<tr><th>Letzte Ladedauer:</th><td>' + lastChargeDurationText + '</td></tr>');
    }
    if (lastChargeAddedPercentText) {
        rows.push('<tr><th>Zuletzt hinzugefügte %:</th><td>' + lastChargeAddedPercentText + '</td></tr>');
    }

    var chargingInfoHtml = rows.length ? '<table>' + rows.join('') + '</table>' : '';
    if (chargingInfoHtml === lastChargingInfoHtml) {
        if (rows.length) {
            $info.show();
        } else {
            $info.hide();
        }
    } else if (rows.length) {
        $info.html(chargingInfoHtml).show();
        lastChargingInfoHtml = chargingInfoHtml;
    } else {
        $info.empty().hide();
        lastChargingInfoHtml = chargingInfoHtml;
    }

    if (sessionStartMsAktuell != null) {
        lastChargeSessionStartMs = sessionStartMsAktuell;
    }
    lastChargingState = state;
}

function formatiereTechnischenWert(wert, nachkommastellen, einheit) {
    var zahl = parseNumber(wert);
    if (zahl == null) {
        return null;
    }
    return zahl.toFixed(nachkommastellen) + ' ' + einheit;
}

function updateTechnischeDetails(charge) {
    var $info = $('#technical-info');
    if (!$info.length) {
        return;
    }
    if (!configEnabled('technical-info') || !charge) {
        $info.empty().hide();
        letzteTechnischeDetailsHtml = '';
        return;
    }

    var packSpannung = parseNumber(charge.pack_voltage);
    var packStrom = parseNumber(charge.pack_current);
    var packLeistung = parseNumber(charge.pack_power);
    if (packLeistung == null && packSpannung != null && packStrom != null) {
        packLeistung = packSpannung * packStrom / 1000;
    }

    var rows = [];
    var spannungText = formatiereTechnischenWert(packSpannung, 1, 'V');
    var stromText = formatiereTechnischenWert(packStrom, 2, 'A');
    var leistungText = formatiereTechnischenWert(packLeistung, 2, 'kW');
    if (spannungText) {
        rows.push('<tr><th>Packspannung:</th><td>' + escapeHtml(spannungText) + '</td></tr>');
    }
    if (stromText) {
        rows.push('<tr><th>Packstrom:</th><td>' + escapeHtml(stromText) + '</td></tr>');
    }
    if (leistungText) {
        rows.push('<tr><th>Packleistung:</th><td>' + escapeHtml(leistungText) + '</td></tr>');
    }
    if (packLeistung != null) {
        var richtung = 'neutral';
        if (packLeistung > 0.05) {
            richtung = 'Batterie nimmt Energie auf';
        } else if (packLeistung < -0.05) {
            richtung = 'Batterie gibt Energie ab';
        }
        rows.push('<tr><th>Richtung:</th><td>' + escapeHtml(richtung) + '</td></tr>');
    }

    if (!rows.length) {
        $info.empty().hide();
        letzteTechnischeDetailsHtml = '';
        return;
    }

    var html = '<h3>Technische Details</h3>' +
        '<table>' + rows.join('') + '</table>';
    if (html === letzteTechnischeDetailsHtml) {
        $info.show();
        return;
    }
    $info.html(html).show();
    letzteTechnischeDetailsHtml = html;
}

function updateNavBar(drive) {
    var $nav = $('#nav-bar');
    if (!drive || !('active_route_destination' in drive) || !drive.active_route_destination) {
        $nav.html('<table><tr><td colspan="2"><span class="icon">🧭</span>Keine Navigation aktiv</td></tr></table>');
        return;
    }

    var rows = [];
    rows.push('<tr><th><span class="icon">🧭</span>Ich düse gerade nach:</th><td>' + drive.active_route_destination + '</td></tr>');
    if (drive.active_route_energy_at_arrival != null) {
        rows.push('<tr><th><span class="icon">🔋</span>Batteriestand bei Ankunft:</th><td>' + Math.round(drive.active_route_energy_at_arrival) + ' %</td></tr>');
    }
    if (drive.active_route_miles_to_arrival != null) {
        var km = drive.active_route_miles_to_arrival * MILES_TO_KM;
        km = Math.floor(km * 100) / 100;
        rows.push('<tr><th><span class="icon">📏</span>Entfernung bis zum Ziel:</th><td>' + km.toFixed(2) + ' km</td></tr>');
    }
    if (drive.active_route_minutes_to_arrival != null) {
        var mins = Math.round(drive.active_route_minutes_to_arrival);
        var h = Math.floor(mins / 60);
        var m = mins % 60;
        var timeStr = (h > 0 ? h + 'h ' : '') + m + 'min';
        var arrival = new Date(Date.now() + mins * 60000);
        var arrivalStr = arrival.toLocaleTimeString('de-DE', {
            hour: '2-digit',
            minute: '2-digit',
            timeZone: 'Europe/Berlin'
        });
        rows.push('<tr><th><span class="icon">⏱️</span>Restzeit (Ankunftszeit):</th><td>' + timeStr + ' (' + arrivalStr + ')</td></tr>');
    }
    if (drive.active_route_traffic_minutes_delay != null) {
        rows.push('<tr><th><span class="icon">🚦</span>Stau-Verzögerung:</th><td>+' + Math.round(drive.active_route_traffic_minutes_delay) + ' min</td></tr>');
    }
    $nav.html('<table>' + rows.join('') + '</table>');
}

function updateMediaPlayer(media) {
    var $player = $('#media-player');
    if (!media || (!media.now_playing_title && !media.now_playing_artist && !media.now_playing_album)) {
        $player.html('<table><tr><td colspan="2"><span class="icon">🎵</span>Keine Wiedergabe</td></tr></table>');
        return;
    }

    var rows = [];
    var title = media.now_playing_title || '';
    var artist = media.now_playing_artist || '';
    var album = media.now_playing_album || '';
    var source = media.now_playing_source || '';
    var station = media.now_playing_station || '';
    var status = media.media_playback_status || '';
    var vol = media.audio_volume;
    var elapsed = media.now_playing_elapsed;
    var duration = media.now_playing_duration;

    if (title || artist || album) {
        var info = title;
        if (artist) {
            info += (info ? ' - ' : '') + artist;
        }
        if (album) {
            info += (info ? ' (' + album + ')' : album);
        }
        rows.push('<tr><th colspan="2">' + info + '</th></tr>');
    }
    if (source) {
        rows.push('<tr><th>Quelle:</th><td>' + source + '</td></tr>');
    }
    if (station) {
        rows.push('<tr><th>Sender:</th><td>' + station + '</td></tr>');
    }
    if (status) {
        rows.push('<tr><th>Status:</th><td>' + status + '</td></tr>');
    }
    if (vol != null && !isNaN(vol)) {
        rows.push('<tr><th>Lautstärke:</th><td>' + Number(vol).toFixed(1) + '</td></tr>');
    }
    if (duration != null && elapsed != null && duration > 0) {
        var pct = Math.min(Math.max(elapsed / duration * 100, 0), 100);
        var pos = Math.round(elapsed / 1000);
        var dur = Math.round(duration / 1000);
        var bar = '<div id="media-progress"><div id="media-progress-bar" style="width:' + pct.toFixed(1) + '%"></div></div>';
        rows.push('<tr><th>Position:</th><td>' + bar + ' ' + pos + 's / ' + dur + 's</td></tr>');
    }
    $player.html('<table>' + rows.join('') + '</table>');
}

function updateAlarmPopup(state) {
    var active = false;
    if (state != null) {
        if (typeof state === 'string') {
            var norm = state.toLowerCase();
            active = norm !== 'off' && norm !== 'inactive' && norm !== '0';
        } else {
            active = !!state;
        }
    }
    if (active) {
        $('#alarm-popup').addClass('show');
    } else {
        $('#alarm-popup').removeClass('show');
    }
}

function getStatus(data) {
    var drive = data.drive_state || {};
    var charge = data.charge_state || {};
    if (charge.charging_state === 'Charging') {
        return 'Ladevorgang';
    }
    if (drive.shift_state && drive.shift_state !== 'P') {
        return 'Fahrt';
    }
    return 'Geparkt';
}

function describe(key) {
    var words = key.split("_");
    var result = words.map(function(w) {
        return w.charAt(0).toUpperCase() + w.slice(1);
    }).join(" ");
    return result;
}

function neuesterDatenZeitstempel(data, vehicle, drive, charge, climate) {
    var kandidaten = [
        data && data.fleet_telemetry_received_at,
        data && data.fleet_telemetry_updated_at,
        data && data.timestamp,
        vehicle && vehicle.timestamp,
        drive && drive.timestamp,
        charge && charge.timestamp,
        climate && climate.timestamp
    ];
    var neuester = null;
    kandidaten.forEach(function(wert) {
        var millis = leseZeitstempelMillis(wert);
        if (millis != null && (neuester == null || millis > neuester)) {
            neuester = millis;
        }
    });
    return neuester;
}

function updateDataAge(ts) {
    if (typeof ts !== 'undefined') {
        if (ts && ts < 1e12) {
            ts *= 1000;
        }
        lastDataTimestamp = ts || null;
    }
    var $el = $('#data-age');
    var anzeigeZeitstempel = lastDataTimestamp;
    if (lastStreamTimestamp && (
            !anzeigeZeitstempel || lastStreamTimestamp > anzeigeZeitstempel)) {
        anzeigeZeitstempel = lastStreamTimestamp;
    }
    if (!anzeigeZeitstempel) {
        $el.text('');
        return;
    }
    var diff = Math.round((Date.now() - anzeigeZeitstempel) / 1000);
    if (diff < 0) diff = 0;
    var text;
    if (diff < 60) {
        text = diff + ' s';
    } else if (diff < 3600) {
        var m = Math.floor(diff / 60);
        var s = diff % 60;
        text = m + ' min ' + s + ' s';
    } else {
        var h = Math.floor(diff / 3600);
        var m = Math.floor((diff % 3600) / 60);
        var s = diff % 60;
        text = h + ' h ' + m + ' min ' + s + ' s';
    }
    var timeStr = new Date(anzeigeZeitstempel).toLocaleTimeString('de-DE', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        timeZone: 'Europe/Berlin'
    });
    $el.text('Letztes Signal vor ' + text + ' (' + timeStr + ')');
}

function aktualisiereStreamSignal(ts) {
    var millis = leseZeitstempelMillis(ts);
    if (millis == null) {
        millis = Date.now();
    }
    if (!lastStreamTimestamp || millis >= lastStreamTimestamp) {
        lastStreamTimestamp = millis;
    }
    updateDataAge();
}

function formatiereKurzesAlter(millis) {
    if (!millis) {
        return null;
    }
    var diff = Math.round((Date.now() - millis) / 1000);
    if (diff < 0) diff = 0;
    if (diff < 60) {
        return diff + ' s';
    }
    if (diff < 3600) {
        var minuten = Math.floor(diff / 60);
        var sekunden = diff % 60;
        return minuten + ' min ' + sekunden + ' s';
    }
    var stunden = Math.floor(diff / 3600);
    var restMinuten = Math.floor((diff % 3600) / 60);
    return stunden + ' h ' + restMinuten + ' min';
}

function stateSeitZeitstempelAusDaten(data) {
    if (!data || typeof data !== 'object') {
        return null;
    }
    var kandidaten = [
        data.state_since_ms,
        data.state_since_at,
        data.state_since
    ];
    var verbindung = data.fleet_telemetry_connectivity || {};
    if (verbindung && typeof verbindung === 'object') {
        kandidaten.push(
            verbindung.CreatedAt,
            verbindung.created_at,
            verbindung.Timestamp,
            verbindung.timestamp
        );
    }
    for (var i = 0; i < kandidaten.length; i++) {
        var millis = leseZeitstempelMillis(kandidaten[i]);
        if (millis != null) {
            return millis;
        }
    }
    return null;
}

function zweistellig(wert) {
    wert = Math.floor(Math.max(0, wert));
    return wert < 10 ? '0' + wert : String(wert);
}

function formatiereHochzaehlendeDauer(seitMillis) {
    var sekunden = Math.floor(Math.max(0, Date.now() - seitMillis) / 1000);
    var stunden = Math.floor(sekunden / 3600);
    var minuten = Math.floor((sekunden % 3600) / 60);
    var restSekunden = sekunden % 60;
    return zweistellig(stunden) + ':' +
        zweistellig(minuten) + ':' +
        zweistellig(restSekunden);
}

function zeichneVehicleState() {
    var $state = $('#vehicle-state');
    if (typeof lastVehicleState !== 'string' || lastVehicleState.length === 0) {
        $state.text('');
        return;
    }
    var text = 'State: ' + lastVehicleState;
    var zustandMitDauer = lastVehicleState === 'offline' ||
        lastVehicleState === 'online';
    if (zustandMitDauer && lastStateSinceTimestamp) {
        text += ' (seit ' + formatiereHochzaehlendeDauer(lastStateSinceTimestamp) + ')';
    }
    $state.text(text);
}

function telemetryProfileParkCountdownSekunden() {
    if (lastTelemetryProfile !== 'live' || lastTelemetryTarget !== 'parked') {
        return null;
    }
    if (lastTelemetryTargetSince == null || telemetryParkDelaySeconds == null) {
        return null;
    }
    var zielMillis = lastTelemetryTargetSince + telemetryParkDelaySeconds * 1000;
    return Math.max(0, Math.ceil((zielMillis - Date.now()) / 1000));
}

function zeichneTelemetryProfile() {
    var $profil = $('#telemetry-profile');
    if (!lastTelemetryProfile) {
        $profil.text('');
        return;
    }
    var text = 'Telemetry: ' + lastTelemetryProfile;
    if (lastTelemetryTarget && lastTelemetryTarget !== lastTelemetryProfile) {
        text += ' -> ' + lastTelemetryTarget;
        var rest = telemetryProfileParkCountdownSekunden();
        if (rest != null) {
            text += ' (in ' + rest + ' ' +
                (rest === 1 ? 'Sekunde' : 'Sekunden') + ')';
        }
    }
    $profil.html(escapeHtml(text) + telemetryConfigSyncHtml());
}

function telemetryConfigSyncHtml() {
    var state = String(lastTelemetryConfigSyncState || 'unknown').toLowerCase();
    var synced = lastTelemetryConfigSynced === true;
    var klasse = 'telemetry-sync-unknown';
    var statusMarke = 'unknown';
    var titel = 'Fleet-Telemetry-Konfiguration: Status unbekannt';
    if (synced || state === 'synced') {
        klasse = 'telemetry-sync-synced';
        statusMarke = 'synced';
        titel = 'Fleet-Telemetry-Konfiguration ist am Fahrzeug angekommen';
    } else if (state === 'active') {
        klasse = 'telemetry-sync-active';
        statusMarke = 'active';
        titel = 'Fleet-Telemetry-Datenstrom nach Konfigurationswechsel aktiv; Tesla meldet noch keine Sync-Bestätigung';
    } else if (state === 'pending') {
        klasse = 'telemetry-sync-pending';
        statusMarke = 'pending';
        titel = 'Fleet-Telemetry-Konfiguration gesendet, wartet auf Fahrzeugbestätigung';
    } else if (state === 'error') {
        klasse = 'telemetry-sync-error';
        statusMarke = 'error';
        titel = 'Fleet-Telemetry-Konfiguration konnte nicht geprüft werden';
        if (lastTelemetryConfigSyncError) {
            titel += ': ' + lastTelemetryConfigSyncError;
        }
    }
    if (lastTelemetryConfigSyncProfile) {
        titel += ' (' + lastTelemetryConfigSyncProfile + ')';
    }
    return ' <span class="telemetry-sync-icon ' + klasse + '" role="img" ' +
        'aria-label="' + escapeHtml(titel) + '" title="' + escapeHtml(titel) + '">' +
        telemetryConfigSyncSvgHtml(statusMarke) + '</span>';
}

function telemetryConfigSyncSvgHtml(statusMarke) {
    var markierung;
    if (statusMarke === 'synced' || statusMarke === 'active') {
        markierung = '<path class="telemetry-sync-status-mark" d="M16.8 5.3l1.3 1.3 2.6-3.1" />';
    } else if (statusMarke === 'pending') {
        markierung = '<circle class="telemetry-sync-status-outline" cx="18.6" cy="5.2" r="2.6" />' +
            '<path class="telemetry-sync-status-mark" d="M18.6 3.6v1.8l1.2.8" />';
    } else if (statusMarke === 'error') {
        markierung = '<path class="telemetry-sync-status-mark" d="M18.6 3.2v2.8" />' +
            '<circle class="telemetry-sync-status-dot" cx="18.6" cy="7.4" r="0.45" />';
    } else if (statusMarke === 'unpaired') {
        markierung = '<path class="telemetry-sync-status-mark" d="M17.2 3.8l2.8 2.8M20 3.8l-2.8 2.8" />';
    } else {
        markierung = '<circle class="telemetry-sync-status-dot" cx="18.6" cy="5.2" r="0.8" />';
    }
    return '<svg class="telemetry-sync-svg" viewBox="0 0 22 16" aria-hidden="true" focusable="false">' +
        '<path class="telemetry-sync-car" d="M2.6 9.2l1.9-4.5h10.1l2.6 4.5M3.6 9.2h14.2v4.1H3.6z" />' +
        '<circle class="telemetry-sync-wheel" cx="6.1" cy="13.3" r="1.4" />' +
        '<circle class="telemetry-sync-wheel" cx="15.3" cy="13.3" r="1.4" />' +
        '<path class="telemetry-sync-window" d="M6.1 5.1h7.3l1.6 3H4.9z" />' +
        markierung +
        '</svg>';
}

function updateTelemetryProfile(
    profile,
    target,
    targetSince,
    parkDelaySeconds,
    configSyncState,
    configSynced,
    configKeyPaired,
    configSyncError,
    configSyncProfile
) {
    if (!profile) {
        lastTelemetryProfile = null;
        lastTelemetryTarget = null;
        lastTelemetryTargetSince = null;
        telemetryParkDelaySeconds = null;
        lastTelemetryConfigSynced = null;
        lastTelemetryConfigKeyPaired = null;
        lastTelemetryConfigSyncState = null;
        lastTelemetryConfigSyncError = null;
        lastTelemetryConfigSyncProfile = null;
        zeichneTelemetryProfile();
        return;
    }
    lastTelemetryProfile = profile;
    lastTelemetryTarget = target || profile;
    lastTelemetryTargetSince = leseZeitstempelMillis(targetSince);
    telemetryParkDelaySeconds = parseNumber(parkDelaySeconds);
    lastTelemetryConfigSyncState = configSyncState || 'unknown';
    lastTelemetryConfigSynced = configSynced === true;
    lastTelemetryConfigKeyPaired = configKeyPaired === true ? true : null;
    lastTelemetryConfigSyncError = configSyncError || null;
    lastTelemetryConfigSyncProfile = configSyncProfile || null;
    zeichneTelemetryProfile();
}

function updateParkTime(ts) {
    if (typeof ts !== 'undefined') {
        if (ts && ts < 1e12) {
            ts *= 1000;
        }
        parkStartTime = ts || null;
    }
    displayParkTime();
}

function displayParkTime() {
    var $el = $('#park-since');
    if (!configEnabled('park-since')) {
        $el.hide();
        updateSmsForm();
        return;
    }
    if (currentGear && currentGear !== 'P') {
        $el.hide();
        updateSmsForm();
        return;
    }
    if (!parkStartTime) {
        $el.hide();
        updateSmsForm();
        return;
    }
    var diff = Math.max(0, Date.now() - parkStartTime);
    var minutes = Math.floor(diff / 60000);
    var hours = Math.floor(minutes / 60);
    var days = Math.floor(hours / 24);
    hours %= 24;
    minutes = minutes % 60;
    var parts = [];
    if (days > 0) {
        parts.push(days + ' ' + (days === 1 ? 'Tag' : 'Tage'));
    }
    if (hours > 0) {
        parts.push(hours + ' ' + (hours === 1 ? 'Stunde' : 'Stunden'));
    }
    parts.push(minutes + ' ' + (minutes === 1 ? 'Minute' : 'Minuten'));
    $el.text('Geparkt seit ' + parts.join(' ')).show();
    updateSmsForm();
}

function updateVehicleState(state, stateCheckedAt, stateData) {
    var vorherigerState = lastVehicleState;
    if (typeof state === 'string' && state.length > 0) {
        lastVehicleState = normalisiereDashboardState(state);
    } else if (arguments.length > 0) {
        lastVehicleState = null;
        lastStateSinceTimestamp = null;
    }
    if (typeof stateCheckedAt !== 'undefined' && stateCheckedAt !== null) {
        var millis = leseZeitstempelMillis(stateCheckedAt);
        if (millis && (!lastStateTimestamp || millis >= lastStateTimestamp)) {
            lastStateTimestamp = millis;
        }
    }
    if (lastVehicleState) {
        var seitMillis = stateSeitZeitstempelAusDaten(stateData);
        if (seitMillis != null) {
            lastStateSinceTimestamp = seitMillis;
        } else if (vorherigerState !== lastVehicleState || !lastStateSinceTimestamp) {
            lastStateSinceTimestamp = leseZeitstempelMillis(stateCheckedAt) || Date.now();
        }
    }
    zeichneVehicleState();
}

function softwareUpdateAusblenden($msg) {
    $msg.prop('hidden', true).hide().empty();
}

function softwareStatusText(status) {
    if (!status) {
        return '';
    }
    var text = String(status).trim();
    var norm = text.toLowerCase();
    var texte = {
        available: 'Update verfügbar',
        downloading: 'Download läuft',
        downloaded: 'Download abgeschlossen',
        installing: 'Installation läuft',
        install: 'Installation läuft',
        scheduled: 'Installation geplant',
        pending: 'Wartet',
        ready: 'Bereit zur Installation',
        failed: 'Fehler',
        error: 'Fehler',
        none: ''
    };
    if (texte.hasOwnProperty(norm)) {
        return texte[norm];
    }
    return text.replace(/_/g, ' ');
}

function softwareStatusAktiv(status) {
    var text = String(status || '').trim().toLowerCase();
    return !!text && text !== 'none' && text !== 'null';
}

function softwareProzent(wert) {
    var zahl = parseNumber(wert);
    if (zahl == null) {
        return null;
    }
    return Math.max(0, Math.min(100, Math.round(zahl)));
}

function softwareDauer(sekunden) {
    var wert = parseNumber(sekunden);
    if (wert == null || wert <= 0) {
        return null;
    }
    if (wert < 60) {
        return Math.round(wert) + ' s';
    }
    return formatiereDauerMinuten(wert / 60);
}

function softwareFortschritt(label, prozent) {
    if (prozent == null) {
        return '';
    }
    return '<div class="software-progress-row">' +
           '<span>' + escapeHtml(label) + '</span>' +
           '<span>' + prozent + '%</span>' +
           '<div class="software-progress" aria-label="' + escapeHtml(label) + ' ' + prozent + '%">' +
           '<div class="software-progress-bar" style="width:' + prozent + '%"></div>' +
           '</div></div>';
}

function speedLimitMphZuAnzeige(limitMph, gui) {
    var limit = parseNumber(limitMph);
    if (limit == null) {
        return null;
    }
    var einheiten = gui && gui.gui_distance_units;
    var nutztKm = !einheiten || String(einheiten).toLowerCase().indexOf('km') !== -1;
    return {
        wert: Math.round(nutztKm ? limit * MILES_TO_KM : limit),
        einheit: nutztKm ? 'km/h' : 'mph'
    };
}

function updateSpeedLimitSymbol(speedLimitMode, gui) {
    var $symbol = $('#speed-limit-symbol');
    var $value = $('#speed-limit-value');
    if (!$symbol.length) {
        return;
    }
    speedLimitMode = speedLimitMode || {};
    var aktiv = istAktiv(speedLimitMode.active);
    var limit = speedLimitMphZuAnzeige(speedLimitMode.current_limit_mph, gui);
    var text = aktiv ? 'Tempolimit-Modus an' : 'Tempolimit-Modus aus';
    if (aktiv && limit != null) {
        text += ': ' + limit.wert + ' ' + limit.einheit;
    }
    $symbol
        .toggleClass('is-active', aktiv)
        .attr('title', text)
        .attr('aria-label', text);
    $value.text(aktiv && limit != null ? String(limit.wert) : '--');
}

function updateCenterDisplaySymbol(status) {
    var $symbol = $('#center-display-symbol');
    if (!$symbol.length) {
        return;
    }
    var text = typeof status === 'string' ? status.trim() : '';
    var norm = text.toLowerCase();
    var aktiv = !!text && ['off', 'false', 'none', 'unknown', 'invalid'].indexOf(norm) === -1;
    var standby = norm.indexOf('standby') !== -1 || norm.indexOf('sleep') !== -1;
    var beschreibung = text ? 'Center Display: ' + text : 'Center Display unbekannt';
    $symbol
        .toggleClass('is-active', aktiv && !standby)
        .toggleClass('is-standby', standby)
        .attr('title', beschreibung)
        .attr('aria-label', beschreibung);
}

function softwareUpdateAktiv(info) {
    if (!info) {
        return false;
    }
    var version = info && typeof info.version === 'string' ? info.version.trim() : '';
    var available = version ? parseVersion(version) : '';
    var status = info && info.status ? String(info.status).trim() : '';
    var downloadProzent = softwareProzent(info && info.download_perc);
    var installationProzent = softwareProzent(info && info.install_perc);
    var fortschrittAktiv = version && (
        (downloadProzent != null && downloadProzent > 0 && downloadProzent < 100) ||
        (installationProzent != null && installationProzent > 0 && installationProzent < 100)
    );
    var neuereVersion = version && installedVersion && isNewerVersion(installedVersion, available);
    return !!(
        softwareStatusAktiv(status) ||
        fortschrittAktiv ||
        (version && (!installedVersion || neuereVersion))
    );
}

function updateSoftwareUpdateSymbol(info) {
    var $symbol = $('#software-update-symbol');
    var $progress = $('#software-update-compact-progress');
    if (!$symbol.length) {
        return;
    }
    var aktiv = softwareUpdateAktiv(info);
    var downloadProzent = softwareProzent(info && info.download_perc);
    var installationProzent = softwareProzent(info && info.install_perc);
    var prozent = installationProzent != null ? installationProzent : downloadProzent;
    var statusText = softwareStatusText(info && info.status);
    var version = info && typeof info.version === 'string' ? parseVersion(info.version) : '';
    var titel = aktiv ? (statusText || 'Software-Update verfügbar') : 'Kein Software-Update';
    if (version) {
        titel += ': Version ' + version;
    }
    if (prozent != null) {
        titel += ' (' + prozent + '%)';
    }
    $symbol
        .toggleClass('is-active', aktiv)
        .toggleClass('is-progress', aktiv && prozent != null && prozent > 0 && prozent < 100)
        .attr('title', titel)
        .attr('aria-label', titel);
    $progress.text(aktiv && prozent != null ? prozent + '%' : '');
}

function updateVehicleSymbols(vehicle, gui) {
    vehicle = vehicle || {};
    updateSpeedLimitSymbol(vehicle.speed_limit_mode, gui || {});
    updateCenterDisplaySymbol(vehicle.center_display_state);
    updateSoftwareUpdateSymbol(vehicle.software_update);
}

function updateSoftwareUpdate(info) {
    var $msg = $('#software-update');
    if (!configEnabled('software-update')) {
        softwareUpdateAusblenden($msg);
        return;
    }
    var version = info && typeof info.version === 'string' ? info.version.trim() : '';
    var available = version ? parseVersion(version) : '';
    var status = info && info.status ? String(info.status).trim() : '';
    var statusAktiv = softwareStatusAktiv(status);
    var downloadProzent = softwareProzent(info && info.download_perc);
    var installationProzent = softwareProzent(info && info.install_perc);
    var fortschrittAktiv = version && (
        (downloadProzent != null && downloadProzent > 0 && downloadProzent < 100) ||
        (installationProzent != null && installationProzent > 0 && installationProzent < 100)
    );
    var neuereVersion = version && installedVersion && isNewerVersion(installedVersion, available);
    var relevanteVersion = version && (!installedVersion || neuereVersion || fortschrittAktiv || statusAktiv);
    if (!relevanteVersion && !statusAktiv) {
        softwareUpdateAusblenden($msg);
        return;
    }

    var statusText = softwareStatusText(status);
    var summary = statusText || 'Software-Update verfügbar';
    if (available) {
        summary += ': Version ' + available;
    }
    var rows = [];
    if (available) {
        rows.push('<tr><th>Version:</th><td>' + escapeHtml(available) + '</td></tr>');
    }
    if (statusText) {
        rows.push('<tr><th>Status:</th><td>' + escapeHtml(statusText) + '</td></tr>');
    }
    var geplanteZeit = formatiereZeitpunkt(info && info.scheduled_time_ms);
    if (geplanteZeit) {
        rows.push('<tr><th>Geplant:</th><td>' + escapeHtml(geplanteZeit) + '</td></tr>');
    }
    var dauer = softwareDauer(info && info.expected_duration_sec);
    if (dauer) {
        rows.push('<tr><th>Erwartete Dauer:</th><td>' + escapeHtml(dauer) + '</td></tr>');
    }
    var warnungSekunden = parseNumber(info && info.warning_time_remaining_ms);
    if (warnungSekunden != null) {
        warnungSekunden = warnungSekunden / 1000;
        var warnung = softwareDauer(warnungSekunden);
        if (warnung) {
            rows.push('<tr><th>Warnzeit:</th><td>' + escapeHtml(warnung) + '</td></tr>');
        }
    }
    var progress = softwareFortschritt('Download', downloadProzent) +
                   softwareFortschritt('Installation', installationProzent);
    $msg.html(
        '<h3>Software-Update</h3>' +
        '<p class="panel-summary">' + escapeHtml(summary) + '</p>' +
        progress +
        '<table>' + rows.join('') + '</table>'
    ).prop('hidden', false).show();
}

function updateOfflineInfo(state, serviceMode, serviceModePlus) {
    var $msg = $('#offline-msg');
    if (!configEnabled('offline-msg')) {
        hideLoading();
        $msg.hide().text('');
        return;
    }
    if (serviceModePlus) {
        hideLoading();
        $msg.text(SERVICE_MODE_PLUS_TEXT).show();
        return;
    }
    if (serviceMode) {
        hideLoading();
        $msg.text(SERVICE_MODE_TEXT).show();
        return;
    }
    if (typeof state === 'string') {
        var st = normalisiereDashboardState(state);
        if (st === 'offline' || st === 'asleep') {
            hideLoading();
            $msg.text(OFFLINE_TEXT).show();
            return;
        }
    }
    hideLoading();
    $msg.hide().text('');
}

function updateClientCount() {
    $.getJSON('/api/clients', function(resp) {
        if (typeof resp.clients === 'number') {
            $('#client-count').text('Clients: ' + resp.clients);
        }
    });
}

function escapeHtml(text) {
    return $('<div>').text(text).html();
}

function formatAnnouncement(text) {
    var html = text;
    if (!/<[a-z][\s\S]*>/i.test(text)) {
        html = escapeHtml(text);
    }
    html = html.replace(/\n/g, '<br>');
    return html.replace(/(https?:\/\/[^\s]+)/g, function(url) {
        return '<a href="' + url + '" target="_blank">' + url + '</a>';
    });
}

function updateAnnouncement() {
    var $box = $('#announcement-box');
    var text = '';
    if (announcementList.length) {
        text = announcementList[announcementIndex] || '';
    } else if (announcementRaw) {
        text = announcementRaw;
    }
    if (text) {
        $box.html(formatAnnouncement(text));
    } else {
        $box.empty();
    }
}

function fetchAnnouncement() {
    $.getJSON('/api/announcement', function(resp) {
        if (typeof resp.announcement !== 'undefined') {
            if (resp.announcement !== announcementRaw) {
                announcementRaw = resp.announcement;
                announcementList = parseAnnouncements(announcementRaw);
                startAnnouncementCycle();
                updateAnnouncement();
            }
        }
    });
}





function updateUI(data) {
    var status = getStatus(data);
    $('#vehicle-status').text('Status: ' + status);
}


$('#vehicle-select').on('change', function() {
    currentVehicle = $(this).val();
    startStreamIfOnline();
});


function startStream() {
    if (!currentVehicle) {
        return;
    }
    if (streamWiederverbindungsTimer) {
        clearTimeout(streamWiederverbindungsTimer);
        streamWiederverbindungsTimer = null;
    }
    if (eventSource) {
        eventSource.close();
    }
    showLoading();
    eventSource = new EventSource('/stream/' + currentVehicle);
    eventSource.onmessage = function(e) {
        var data = JSON.parse(e.data);
        if (!data.error) {
            aktualisiereStreamSignal(Date.now());
            handleData(data);
        }
    };
    eventSource.addEventListener('stream', function(e) {
        try {
            var data = JSON.parse(e.data);
            aktualisiereStreamSignal(data.stream_heartbeat_at);
        } catch (err) {
            aktualisiereStreamSignal(Date.now());
        }
    });
    eventSource.onerror = function() {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        if (!currentVehicle) return;
        $.getJSON('/api/state/' + currentVehicle, function(resp) {
            var st = resp.state;
            updateVehicleState(st, resp.state_checked_at, resp);
            updateOfflineInfo(st, resp.service_mode, resp.service_mode_plus);
            updateSoftwareUpdate(resp.software_update);
            if (istOfflineOderSchlaeft(st)) {
                planeNaechsteStatusabfrage();
                $.getJSON('/api/data/' + currentVehicle, function(data) {
                    if (data && !data.error) {
                        handleData(data);
                    }
                });
                return;
            }
            $.getJSON('/api/data/' + currentVehicle, function(data) {
                if (data && !data.error) {
                    handleData(data);
                }
            });
        });
        // Nach kurzer Trennung den SSE-Kanal direkt wieder öffnen.
        if (!streamWiederverbindungsTimer) {
            streamWiederverbindungsTimer = setTimeout(function() {
                streamWiederverbindungsTimer = null;
                if (currentVehicle && !eventSource && !statusAbfrageTimer) {
                    startStream();
                }
            }, STREAM_WIEDERVERBINDUNG_MS);
        }
    };
}

function startStreamIfOnline() {
    if (!currentVehicle) {
        return;
    }
    if (streamWiederverbindungsTimer) {
        clearTimeout(streamWiederverbindungsTimer);
        streamWiederverbindungsTimer = null;
    }
    if (statusAbfrageTimer) {
        clearTimeout(statusAbfrageTimer);
        statusAbfrageTimer = null;
    }
    $.getJSON('/api/state/' + currentVehicle, function(resp) {
        var st = resp.state;
        updateVehicleState(st, resp.state_checked_at, resp);
        updateOfflineInfo(st, resp.service_mode, resp.service_mode_plus);
        updateSoftwareUpdate(resp.software_update);
        if (istOfflineOderSchlaeft(st)) {
            hideLoading();
            planeNaechsteStatusabfrage();
            $.getJSON('/api/data/' + currentVehicle, function(data) {
                if (data && !data.error) {
                    handleData(data);
                }
            });
            return;
        }
        startStream();
        $.getJSON('/api/data/' + currentVehicle, function(data) {
            if (data && !data.error) {
                handleData(data);
            }
        });
    });
}

$.getJSON('/api/config', function(cfg) {
    applyConfig(cfg);
    lastConfigJSON = JSON.stringify(cfg || {});
    if (cfg) {
        lastApiInterval = cfg.api_interval;
        lastApiIntervalIdle = Number(cfg.api_interval_idle);
        if (cfg.vehicle_id) {
            currentVehicle = cfg.vehicle_id;
        }
    }
    fetchVehicles();
});

function fetchConfig() {
    $.getJSON('/api/config', function(cfg) {
        var naechstesApiIntervalIdle = cfg ? Number(cfg.api_interval_idle) : null;
        var json = JSON.stringify(cfg || {});
        if (json !== lastConfigJSON) {
            if (cfg && (cfg.api_interval !== lastApiInterval ||
                        naechstesApiIntervalIdle !== lastApiIntervalIdle ||
                        cfg.vehicle_id !== currentVehicle)) {
                location.reload(true);
                return;
            }
            lastConfigJSON = json;
            if (cfg) {
                lastApiInterval = cfg.api_interval;
                lastApiIntervalIdle = naechstesApiIntervalIdle;
            }
            applyConfig(cfg);
        }
    });
}

function checkAppVersion() {
    $.getJSON('/api/version', function(resp) {
        if (resp.version && APP_VERSION && resp.version !== APP_VERSION) {
            location.reload(true);
        }
    });
}

setInterval(checkAppVersion, 60000);
setInterval(function() {
    updateDataAge();
    zeichneVehicleState();
    zeichneTelemetryProfile();
}, 1000);
setInterval(updateClientCount, 5000);
setInterval(fetchAnnouncement, 15000);
setInterval(fetchConfig, 15000);
setInterval(displayParkTime, 60000);
updateClientCount();
fetchAnnouncement();
updateSmsForm();


$('#sms-send').on('click', function() {
    var name = $('#sms-name').val().trim();
    var msg = $('#sms-text').val().trim();
    if (!msg) return;
    var fullMsg = name ? name + ': ' + msg : msg;
    if (fullMsg.length > 160) {
        $('#sms-status').text('Nachricht zu lang');
        return;
    }
    $('#sms-status').text('Senden...');
    $.ajax({
        url: '/api/sms',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({message: msg, name: name}),
        success: function(resp) {
            if (resp && resp.success) {
                $('#sms-status').text('Gesendet');
                $('#sms-name').val('');
                $('#sms-text').val('');
            } else {
                $('#sms-status').text('Fehler: ' + (resp.error || 'unbekannt'));
            }
        },
        error: function(xhr) {
            var msg = 'unbekannt';
            try {
                var resp = JSON.parse(xhr.responseText);
                if (resp && resp.error) {
                    msg = resp.error;
                }
            } catch (e) {}
            $('#sms-status').text('Fehler: ' + msg);
        }
    });
});

$('#alarm-close').on('click', function() {
    $('#alarm-popup').removeClass('show');
});

// © 2026 Erik Schauer, do1ffe@darc.de
