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
// Default view if no coordinates are available
var DEFAULT_POS = [51.4556, 7.0116];
var DEFAULT_ZOOM = 18;
var superchargerMarkers = [];
var lastSuperchargerData = null;
var letzteKartenPosition = null;

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
var map = L.map('map').setView(DEFAULT_POS, DEFAULT_ZOOM);
var osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
}).addTo(map);
var esriLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles © Esri — Quelle: Esri, i-cubed, USDA, USGS, AEX, GeoEye, ' +
        'Getmapping, Aerogrid, IGN, IGP, UPR-EGP ' +
        'und die GIS-User-Community'
});
var esriLabelLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Beschriftungen © Esri'
});
var hybridLayer = L.layerGroup([esriLayer, esriLabelLayer]);
L.control.layers({'Standard': osmLayer, 'Hybrid': hybridLayer, 'Satellit': esriLayer}, null, {position: 'topright'}).addTo(map);
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
function updateZoomDisplay() {
    if ($zoomLevel.length) {
        $zoomLevel.text('Zoom: ' + map.getZoom());
    }
}
updateZoomDisplay();
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
var installedVersion = null;
var CONFIG = {};
var HIGHLIGHT_BLUE = false;
var currentPath = [];
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
    'v2l-infos': true,
    'announcement-box': true,
    'page-menu': true,
    'menu-dashboard': true,
    'menu-statistik': true,
    'menu-history': true,
    'nav-bar': true,
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

function istOfflineOderSchlaeft(status) {
    if (typeof status !== 'string') {
        return false;
    }
    var st = status.toLowerCase();
    return st === 'offline' || st === 'asleep';
}

function positionIstNeu(lat, lng) {
    if (!isFinite(lat) || !isFinite(lng)) {
        return false;
    }
    if (!letzteKartenPosition) {
        return true;
    }
    var diffLat = Math.abs(lat - letzteKartenPosition[0]);
    var diffLng = Math.abs(lng - letzteKartenPosition[1]);
    return diffLat > 1e-6 || diffLng > 1e-6;
}

function planeNaechsteStatusabfrage() {
    if (statusAbfrageTimer) {
        clearTimeout(statusAbfrageTimer);
    }
    var intervall = lastApiIntervalIdle || 30000;
    statusAbfrageTimer = setTimeout(function() {
        startStreamIfOnline();
    }, intervall);
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
            }
        });
    }
    return Array.isArray(currentPath) ? currentPath : [];
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
    updateVehicleState(data.state);
    var vehicle = data.vehicle_state || {};
    updateOfflineInfo(data.state, vehicle.service_mode, vehicle.service_mode_plus);
    updateSoftwareUpdate(vehicle.software_update);
    var drive = data.drive_state || {};
    updateDataAge(vehicle.timestamp);
    updateLockStatus(vehicle.locked);
    updateUserPresence(vehicle.is_user_present);
    updateGearShift(drive.shift_state);
    updateParkTime(data.park_start);
    updateNavBar(drive);
    var charge = data.charge_state || {};
    updateSpeedometer(drive.speed, drive.power, charge.charging_state);
    updateOdometer(vehicle.odometer);
    var rangeMiles = charge.ideal_battery_range;
    if (rangeMiles == null) {
        rangeMiles = charge.est_battery_range;
    }
    updateBatteryIndicator(charge.battery_level, rangeMiles, charge.charging_state, charge.battery_heater_on);
    updateV2LInfos(charge, drive);
    updateChargingInfo(charge, data);
    var climate = data.climate_state || {};
    updateThermometers(climate.inside_temp, climate.outside_temp, charge.battery_temp);
    updateClimateStatus(climate.is_climate_on);
    updateClimateMode(climate.climate_keeper_mode);
    updateCabinProtection(climate.cabin_overheat_protection);
    updateFanStatus(climate.fan_status);
    updateDesiredTemp(climate.driver_temp_setting);
    updateHeaterIndicator(
        climate.is_front_defroster_on,
        climate.is_rear_defroster_on,
        climate.steering_wheel_heater,
        climate.wiper_blade_heater,
        climate.side_mirror_heaters,
        charge.battery_heater_on,
        climate.seat_heater_left,
        climate.seat_heater_right,
        climate.seat_heater_rear_left,
        climate.seat_heater_rear_center,
        climate.seat_heater_rear_right
    );
    updateTPMS(vehicle.tpms_pressure_fl,
               vehicle.tpms_pressure_fr,
               vehicle.tpms_pressure_rl,
               vehicle.tpms_pressure_rr);
    updateOpenings(vehicle, charge);
    updateMediaPlayer(vehicle.media_info);
    var alarm = data.alarm_state;
    if (alarm == null && vehicle.alarm_state != null) {
        alarm = vehicle.alarm_state;
    }
    updateAlarmPopup(alarm);
    var lat = Number(drive.latitude);
    var lng = Number(drive.longitude);
    var slide = false;
    var offline = istOfflineOderSchlaeft(data.state);
    if (isFinite(lat) && isFinite(lng)) {
        var coordsNeu = positionIstNeu(lat, lng);
        if (offline) {
            marker.setLatLng([lat, lng]);
        } else if (typeof marker.slideTo === 'function') {
            marker.slideTo([lat, lng], {duration: 1000});
            slide = true;
        } else {
            marker.setLatLng([lat, lng]);
        }
        var speedVal = parseFloat(drive.speed);
        var units = data.gui_settings && data.gui_settings.gui_distance_units;
        var mph = !units || units.indexOf('km') === -1;
        var speedKmh = isNaN(speedVal) ? 0 : (mph ? speedVal * MILES_TO_KM : speedVal);
        var zoom = computeZoomForSpeed(speedKmh);
        if (Date.now() - lastUserZoom < USER_ZOOM_PRIORITY_MS) {
            zoom = map.getZoom();
        }
        if (!offline || coordsNeu || !letzteKartenPosition) {
            zoomSetByApp = true;
            if (offline) {
                map.setView([lat, lng], zoom, {animate: false});
            } else {
                map.flyTo([lat, lng], zoom);
            }
            updateZoomDisplay();
        }
        if (typeof drive.heading === 'number') {
            var displayHeading = adjustHeadingForReverse(drive.heading, drive.shift_state);
            marker.setRotationAngle(displayHeading);
        }
        letzteKartenPosition = [lat, lng];
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

    var addr = data.location_address;
    if (addr) {
        $('#address-text').text(addr);
        $('#address-error').hide();
    } else {
        $('#address-text').text('');
        $('#address-error').hide();
    }
    updateSuperchargerList(data);

    // Show destination flag and route line if navigation is active
    if (drive.active_route_destination && drive.active_route_latitude && drive.active_route_longitude) {
        var dLat = drive.active_route_latitude;
        var dLng = drive.active_route_longitude;
        if (!destMarker) {
            destMarker = L.marker([dLat, dLng], { icon: flagIcon }).addTo(map);
        } else {
            destMarker.setLatLng([dLat, dLng]);
        }
        if (lat && lng) {
            if (!destLine) {
                destLine = L.polyline([[lat, lng], [dLat, dLng]], { color: 'red', dashArray: '5, 5', weight: 2 }).addTo(map);
            } else {
                destLine.setLatLngs([[lat, lng], [dLat, dLng]]);
            }
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
    }
    var pathPoints = updatePathPoints(data);
    if (pathPoints.length > 1) {
        if (!polyline) {
            polyline = L.polyline(pathPoints, { color: 'blue' }).addTo(map);
        } else if (slide) {
            pendingPath = pathPoints.slice();
        } else {
            polyline.setLatLngs(pathPoints);
        }
    } else if (polyline) {
        map.removeLayer(polyline);
        polyline = null;
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
    if (!mode || mode === 'off') {
        $el.text('').attr('title', '').attr('aria-label', '').hide();
        return;
    }
    var icon = '';
    var title = '';
    if (mode === 'dog') {
        icon = '\uD83D\uDC36';
        title = 'Hundemodus';
    } else if (mode === 'camp') {
        icon = '\u26FA';
        title = 'Camp-Modus';
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

function updateHeaterIndicator(front, rear, steering, wiper,
                               mirror, battery,
                               seatL, seatR, seatRL, seatRC, seatRR) {
    function set(id, val, name) {
        if (val == null) {
            $('#' + id)
                .html(name + ': \uD83D\uDEAB')
                .attr('title', name + ' unbekannt')
                .attr('aria-label', name + ' unbekannt');
            return;
        }
        var active = false;
        if (typeof val === 'string') {
            var norm = val.toLowerCase();
            active = norm === 'true' || norm === '1';
        } else {
            active = !!val;
        }
        $('#' + id)
            .html(name + ': ' + (active ? '\uD83D\uDD25' : '\uD83D\uDEAB'))
            .attr('title', name + (active ? ' an' : ' aus'))
            .attr('aria-label', name + (active ? ' an' : ' aus'));
    }
    function setLevel(id, val, name) {
        if (val == null || isNaN(val)) {
            $('#' + id)
                .html(name + ': \uD83D\uDEAB')
                .attr('title', name + ' unbekannt')
                .attr('aria-label', name + ' unbekannt');
            return;
        }
        var level = Number(val);
        if (level <= 0) {
            $('#' + id)
                .html(name + ': \uD83D\uDEAB')
                .attr('title', name + ' aus')
                .attr('aria-label', name + ' aus');
        } else {
            $('#' + id)
                .html(name + ': \uD83D\uDD25' + level)
                .attr('title', name + ' Stufe ' + level)
                .attr('aria-label', name + ' Stufe ' + level);
        }
    }

    set('front-defrost', front, 'Frontscheibenheizung');
    set('rear-defrost', rear, 'Heckscheibenheizung');
    set('steering-heater', steering, 'Lenkradheizung');
    set('wiper-heater', wiper, 'Scheibenwischerheizung');
    set('mirror-heater', mirror, 'Seitenspiegelheizung');
    set('battery-heater', battery, 'Batterieheizung');
    setLevel('seat-left', seatL, 'Sitzheizung Fahrer');
    setLevel('seat-right', seatR, 'Sitzheizung Beifahrer');
    setLevel('seat-rear-left', seatRL, 'Sitzheizung hinten links');
    setLevel('seat-rear-center', seatRC, 'Sitzheizung hinten mitte');
    setLevel('seat-rear-right', seatRR, 'Sitzheizung hinten rechts');
}

function updateTPMS(fl, fr, rl, rr) {
    function set(id, val) {
        var $group = $('#tpms-' + id);
        var $text = $group.find('text');
        var $circle = $group.find('circle');
        if (val == null || isNaN(val)) {
            $text.text('--');
            $circle.css('stroke', '#555');
            return;
        }
        var num = Number(val);
        $text.text(num.toFixed(1));
        var color = '#4caf50';
        if (num < 2.7 || num > 3.3) {
            color = '#ff9800';
        }
        if (num < 2.1 || num > 3.7) {
            color = '#d00';
        }
        $circle.css('stroke', color);
    }
    set('VL', fl);
    set('VR', fr);
    set('HL', rl);
    set('HR', rr);
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
    if (srPct != null || srState) {
        var pct = Number(srPct);
        var open = srState && srState.toLowerCase() !== 'closed' && pct > 0;
        $('#sunroof').attr('class', open ? 'part-open' : 'part-closed');
        $('#sunroof-percent').text(open && !isNaN(pct) ? Math.round(pct) + '%' : '');
    }

    var charging = charge && charge.charging_state === 'Charging';
    $('#charge-cable').toggleClass('charging', charging);
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

function updateThermometers(inside, outside, battery) {
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
        $label.text(labelPrefix + ': ' + label);
    }
    set('inside', inside, 'Innen');
    set('outside', outside, 'Außen');
    set('battery', battery, 'Batterie');
}

function updateBatteryIndicator(level, rangeMiles, chargingState, heaterOn) {
    var pct = level != null ? level : 0;
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
    html += '<div class="battery-value">' + pct + '%</div>';
    html += '<div class="range">' + range + ' km</div>';
    $('#battery-indicator').html(html);
}

function batteryBar(level) {
    var pct = level != null ? level : 0;
    var clip = 'clip-path: inset(' + (100 - pct) + '% 0 0 0)';
    return '<div class="battery-block"><div class="battery"><div class="level" style="' + clip + '"></div></div><div class="battery-value">' + pct + '%</div></div>';
}

var lastChargeInfo = null;
var lastChargeStop = null;
var lastEnergyAdded = null;
var letzteLadedauerMs = null;
var letzterLadezuwachsProzent = null;
var lastChargeSessionStartMs = null;
var lastChargingState = null;
var letzteBatterieTemperatur = null;

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

function updateChargingInfo(charge, wurzelDaten) {
    var $info = $('#charging-info');
    if (!charge) {
        $info.empty().hide();
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
        var letzterStartSocQuelle = charge ? charge.last_charge_start_soc : null;
        if (letzterStartSocQuelle == null && wurzelDaten) {
            letzterStartSocQuelle = wurzelDaten.last_charge_start_soc;
        }
        lastChargeStartSoc = parseNumber(letzterStartSocQuelle);
        var letzterEndSocQuelle = charge ? charge.last_charge_end_soc : null;
        if (letzterEndSocQuelle == null && wurzelDaten) {
            letzterEndSocQuelle = wurzelDaten.last_charge_end_soc;
        }
        lastChargeEndSoc = parseNumber(letzterEndSocQuelle);
    } else if (letzteLadezuwachsQuelleTyp === 'aktuelle_session') {
        lastChargeStartSoc = parseNumber(startSoc);
        lastChargeEndSoc = parseNumber(currentSoc);
    }
    var lastChargeSocText = null;
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

    if (rows.length) {
        $info.html('<table>' + rows.join('') + '</table>').show();
    } else {
        $info.empty().hide();
    }

    if (sessionStartMsAktuell != null) {
        lastChargeSessionStartMs = sessionStartMsAktuell;
    }
    lastChargingState = state;
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

function updateDataAge(ts) {
    if (typeof ts !== 'undefined') {
        if (ts && ts < 1e12) {
            ts *= 1000;
        }
        lastDataTimestamp = ts || null;
    }
    var $el = $('#data-age');
    if (!lastDataTimestamp) {
        $el.text('');
        return;
    }
    var diff = Math.round((Date.now() - lastDataTimestamp) / 1000);
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
    var timeStr = new Date(lastDataTimestamp).toLocaleTimeString('de-DE', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        timeZone: 'Europe/Berlin'
    });
    $el.text('Letztes Update vor ' + text + ' (' + timeStr + ')');
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

function updateVehicleState(state) {
    if (typeof state === 'string' && state.length > 0) {
        $('#vehicle-state').text('State: ' + state);
    } else {
        $('#vehicle-state').text('');
    }
}

function updateSoftwareUpdate(info) {
    var $msg = $('#software-update');
    if (!configEnabled('software-update')) {
        $msg.hide().text('');
        return;
    }
    var version = info && typeof info.version === 'string' ? info.version.trim() : '';
    if (!version) {
        $msg.hide().text('');
        return;
    }
    var available = parseVersion(version);
    if (!installedVersion || !isNewerVersion(installedVersion, available)) {
        $msg.hide().text('');
        return;
    }
    var parts = ['Version: ' + available];
    if (info.status) parts.push('Status: ' + info.status);
    if (typeof info.download_perc === 'number') {
        parts.push('Download: ' + info.download_perc + '%');
    }
    if (typeof info.install_perc === 'number') {
        parts.push('Installation: ' + info.install_perc + '%');
    }
    if (typeof info.expected_duration_sec === 'number') {
        parts.push('Dauer: ' + info.expected_duration_sec + 's');
    }
    $msg.text('Software-Update – ' + parts.join(', ')).show();
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
        var st = state.toLowerCase();
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
    if (eventSource) {
        eventSource.close();
    }
    showLoading();
    eventSource = new EventSource('/stream/' + currentVehicle);
    eventSource.onmessage = function(e) {
        var data = JSON.parse(e.data);
        if (!data.error) {
            handleData(data);
        }
    };
    eventSource.onerror = function() {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        if (!currentVehicle) return;
        $.getJSON('/api/state/' + currentVehicle, function(resp) {
            var st = resp.state;
            updateVehicleState(st);
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
        // Ensure the map shows Essen if no cached data was found
        var zoom = DEFAULT_ZOOM;
        if (Date.now() - lastUserZoom < USER_ZOOM_PRIORITY_MS) {
            zoom = map.getZoom();
        }
        zoomSetByApp = true;
        map.setView(DEFAULT_POS, zoom);
        updateZoomDisplay();
        // Attempt to reconnect after a short delay in case the browser has
        // suspended the connection while running in the background.
        if (!statusAbfrageTimer) {
            setTimeout(startStreamIfOnline, 5000);
        }
    };
}

function startStreamIfOnline() {
    if (!currentVehicle) {
        return;
    }
    if (statusAbfrageTimer) {
        clearTimeout(statusAbfrageTimer);
        statusAbfrageTimer = null;
    }
    $.getJSON('/api/state/' + currentVehicle, function(resp) {
        var st = resp.state;
        updateVehicleState(st);
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
        lastApiIntervalIdle = cfg.api_interval_idle;
        if (cfg.vehicle_id) {
            currentVehicle = cfg.vehicle_id;
        }
    }
    fetchVehicles();
});

function fetchConfig() {
    $.getJSON('/api/config', function(cfg) {
        var json = JSON.stringify(cfg || {});
        if (json !== lastConfigJSON) {
            if (cfg && (cfg.api_interval !== lastApiInterval ||
                        cfg.api_interval_idle !== lastApiIntervalIdle ||
                        cfg.vehicle_id !== currentVehicle)) {
                location.reload(true);
                return;
            }
            lastConfigJSON = json;
            if (cfg) {
                lastApiInterval = cfg.api_interval;
                lastApiIntervalIdle = cfg.api_interval_idle;
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
setInterval(function() { updateDataAge(); }, 1000);
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
