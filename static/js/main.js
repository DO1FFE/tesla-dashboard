var currentVehicle = null;
var APP_VERSION = window.APP_VERSION || null;
var MILES_TO_KM = 1.60934;
var lastSuperchargerFetch = 0;
var superchargerData = [];
// Default view if no coordinates are available
var DEFAULT_POS = [51.4556, 7.0116];
var DEFAULT_ZOOM = 19;
// Initialize the map roughly centered on Essen with a high zoom until
// coordinates from the API are received.
var map = L.map('map').setView(DEFAULT_POS, DEFAULT_ZOOM);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
}).addTo(map);
var polyline = null;
var lastDataTimestamp = null;
var CONFIG = {};
var HIGHLIGHT_BLUE = false;
var ASLEEP = false;

function applyConfig(cfg) {
    if (!cfg) return;
    CONFIG = cfg;
    HIGHLIGHT_BLUE = !!CONFIG['blue-openings'];
    showConfigured();
}

function showConfigured() {
    Object.keys(CONFIG).forEach(function(id) {
        if (id === 'blue-openings') return;
        $('#' + id).toggle(!!CONFIG[id]);
    });
    $('#dashboard-content').show();
    $('#sleep-msg').hide();
    ASLEEP = false;
}

function hideForSleep() {
    $('#dashboard-content').hide();
    $('#sleep-msg').show();
    ASLEEP = true;
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

var marker = L.marker([0, 0], {
    icon: arrowIcon,
    rotationAngle: 0,
    rotationOrigin: 'center center'
}).addTo(map);
var eventSource = null;

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
            version = version.split(' ')[0];
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
            $select.val(currentVehicle);
            startStream();
        }
    });
}

function handleData(data) {
    updateHeader(data);
    updateUI(data);
    updateVehicleState(data.state);
    if (data.state && data.state.toLowerCase() === 'asleep') {
        hideForSleep();
    } else if (ASLEEP && data.state && data.state.toLowerCase() === 'online') {
        showConfigured();
    }
    var drive = data.drive_state || {};
    var vehicle = data.vehicle_state || {};
    updateDataAge(vehicle.timestamp);
    updateLockStatus(vehicle.locked);
    updateUserPresence(vehicle.is_user_present);
    updateGearShift(drive.shift_state);
    updateNavBar(drive);
    updateSpeedometer(drive.speed, drive.power);
    updateOdometer(vehicle.odometer);
    var charge = data.charge_state || {};
    var rangeMiles = charge.ideal_battery_range;
    if (rangeMiles == null) {
        rangeMiles = charge.est_battery_range;
    }
    updateBatteryIndicator(charge.battery_level, rangeMiles, charge.charging_state);
    updateV2LInfos(charge, drive);
    updateChargingInfo(charge);
    var climate = data.climate_state || {};
    updateThermometers(climate.inside_temp, climate.outside_temp);
    updateClimateStatus(climate.is_climate_on);
    updateClimateMode(climate.climate_keeper_mode);
    updateCabinProtection(climate.cabin_overheat_protection);
    updateFanStatus(climate.fan_status);
    updateDesiredTemp(climate.driver_temp_setting);
    updateTPMS(vehicle.tpms_pressure_fl,
               vehicle.tpms_pressure_fr,
               vehicle.tpms_pressure_rl,
               vehicle.tpms_pressure_rr);
    updateOpenings(vehicle, charge);
    updateMediaPlayer(vehicle.media_info);
    var lat = drive.latitude;
    var lng = drive.longitude;
    if (lat && lng) {
        marker.setLatLng([lat, lng]);
        map.setView([lat, lng], map.getZoom());
        if (typeof drive.heading === 'number') {
            marker.setRotationAngle(drive.heading);
        }
    } else {
        // Fall back to Essen if no coordinates are available
        map.setView(DEFAULT_POS, DEFAULT_ZOOM);
    }

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
    if (data.path && data.path.length > 1) {
        if (polyline) {
            polyline.setLatLngs(data.path);
        } else {
            polyline = L.polyline(data.path, { color: 'blue' }).addTo(map);
        }
    } else if (polyline) {
        map.removeLayer(polyline);
        polyline = null;
    }
    updateSuperchargerList();
    fetchSuperchargers();
}


function updateGearShift(state) {
    var gear = state || 'P';
    $('#gear-shift div').removeClass('active');
    $('#gear-shift div[data-gear="' + gear + '"]').addClass('active');
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
        $('#lock-status').text('\uD83D\uDD12').attr('title', 'Verriegelt');
    } else {
        $('#lock-status').text('\uD83D\uDD13').attr('title', 'Offen');
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
        $('#user-presence').css('color', '#4caf50').attr('title', 'Person im Fahrzeug');
    } else {
        $('#user-presence').css('color', '#d00').attr('title', 'Keine Person im Fahrzeug');
    }
}

function updateClimateStatus(on) {
    if (on == null) {
        $('#climate-status').text('').attr('title', '');
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
        $('#climate-status').text('\u2744\uFE0F').attr('title', 'Klimaanlage an');
    } else {
        $('#climate-status').text('\uD83D\uDEAB').attr('title', 'Klimaanlage aus');
    }
}

function updateFanStatus(speed) {
    if (speed == null || isNaN(speed)) {
        $('#fan-status').text('').attr('title', '');
        return;
    }
    var val = Math.max(0, Math.min(11, Number(speed)));
    $('#fan-status').text('\uD83C\uDF00 ' + val).attr('title', 'L\u00FCfterstufe ' + val);
}

function updateClimateMode(mode) {
    var $el = $('#climate-mode');
    if (!mode || mode === 'off') {
        $el.text('').attr('title', '').hide();
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
    $el.text(icon).attr('title', title).show();
}

function updateCabinProtection(value) {
    var $el = $('#cabin-protection');
    if (value === 'On') {
        $el.text('\u2600\uFE0F').attr('title', 'Kabinenschutz aktiv').show();
    } else {
        $el.text('').attr('title', '').hide();
    }
}

function updateDesiredTemp(temp) {
    if (temp == null || isNaN(temp)) {
        $('#desired-temp').text('🌡️ -- °C').attr('title', 'Wunschtemperatur');
        return;
    }
    $('#desired-temp').text('\uD83C\uDF21\uFE0F ' + temp.toFixed(1) + ' \u00B0C')
        .attr('title', 'Wunschtemperatur');
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
        if (num < 2.8 || num > 3.3) {
            color = '#ff9800';
        }
        if (num < 2.5 || num > 3.6) {
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
}

var MAX_SPEED = 250;
var MIN_TEMP = -20;
var MAX_TEMP = 50;

function updateSpeedometer(speed, power) {
    if (speed == null) speed = 0;
    if (power == null) power = 0;
    var kmh = Math.round(speed * MILES_TO_KM);
    var angle = (Math.min(Math.max(kmh, 0), MAX_SPEED) / MAX_SPEED) * 180 - 90;
    $('#speedometer-needle').attr('transform', 'rotate(' + angle + ' 60 50)');
    $('#speed-value').text(kmh + ' km/h');
    var text = Math.round(power) + ' kW';
    if (power < 0) {
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

function updateThermometers(inside, outside) {
    var range = MAX_TEMP - MIN_TEMP;
    function set(prefix, temp) {
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
        $('#' + prefix + '-level').attr('y', y).attr('height', h).css('fill', color);
        $('#' + prefix + '-bulb').css('fill', color);
        var label = missing ? '-.- °C' : temp.toFixed(1) + ' °C';
        $('#' + prefix + '-temp-value').text((prefix === 'inside' ? 'Innen: ' : 'Außen: ') + label);
    }
    set('inside', inside);
    set('outside', outside);
}

function updateBatteryIndicator(level, rangeMiles, chargingState) {
    var pct = level != null ? level : 0;
    var range = rangeMiles != null ? Math.round(rangeMiles * MILES_TO_KM) : '?';
    var charging = chargingState === 'Charging';
    var html = '<div class="battery">';
    html += '<div class="level" style="height:' + pct + '%;"></div>';
    if (charging) {
        html += '<div class="bolt">\u26A1</div>';
    }
    html += '</div>';
    html += '<div class="battery-value">' + pct + '%</div>';
    html += '<div class="range">' + range + ' km</div>';
    $('#battery-indicator').html(html);
}

function batteryBar(level) {
    var pct = level != null ? level : 0;
    return '<div class="battery-block"><div class="battery"><div class="level" style="height:' + pct + '%;"></div></div><div class="battery-value">' + pct + '%</div></div>';
}

var lastChargeInfo = null;
var lastChargeStop = null;

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

function updateChargingInfo(charge) {
    var $info = $('#charging-info');
    if (!charge) {
        $info.empty().hide();
        return;
    }

    var state = charge.charging_state;
    var now = Date.now();

    if (state === 'Charging') {
        lastChargeInfo = JSON.parse(JSON.stringify(charge));
        lastChargeStop = null;
    } else {
        if (lastChargeInfo && !lastChargeStop) {
            lastChargeStop = now;
        }
    }

    var showFull = false;
    if (state === 'Charging') {
        showFull = true;
    } else if (lastChargeStop && now - lastChargeStop <= 600000) {
        charge = lastChargeInfo || charge;
        showFull = true;
    }

    var rows = [];
    if (showFull) {
        if (charge.charging_state) {
            rows.push('<tr><th>Status:</th><td>' + charge.charging_state + '</td></tr>');
        }
        if (charge.charge_energy_added != null) {
            rows.push('<tr><th>Geladene Energie:</th><td>' + Number(charge.charge_energy_added).toFixed(2) + ' kWh</td></tr>');
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
            rows.push('<tr><th>Minuten bis voll:</th><td>' + Math.round(charge.minutes_to_full_charge) + ' min</td></tr>');
        }
    } else if (lastChargeInfo && lastChargeInfo.charge_energy_added != null) {
        rows.push('<tr><th>Beim letzten Stopp hinzugefügte Energie:</th><td>' + Number(lastChargeInfo.charge_energy_added).toFixed(2) + ' kWh</td></tr>');
    }

    if (rows.length) {
        $info.html('<table>' + rows.join('') + '</table>').show();
    } else {
        $info.empty().hide();
    }
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
        var arrivalStr = arrival.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
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
        rows.push('<tr><th>Position:</th><td>' + pos + 's / ' + dur + 's (' + Math.round(pct) + '%)</td></tr>');
    }
    $player.html('<table>' + rows.join('') + '</table>');
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
    var timeStr = new Date(lastDataTimestamp).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'});
    $el.text('Letztes Update vor ' + text + ' (' + timeStr + ')');
}

function updateVehicleState(state) {
    if (typeof state === 'string' && state.length > 0) {
        $('#vehicle-state').text('State: ' + state);
    } else {
        $('#vehicle-state').text('');
    }
}

function updateClientCount() {
    $.getJSON('/api/clients', function(resp) {
        if (typeof resp.clients === 'number') {
            $('#client-count').text('Clients: ' + resp.clients);
        }
    });
}

function updateSuperchargerList() {
    var $list = $('#supercharger-list');
    if (!superchargerData.length) {
        $list.empty();
        return;
    }
    var rows = superchargerData.slice(0, 10).map(function(sc) {
        var dist = sc.distance_km != null ? sc.distance_km.toFixed(1) : '?';
        return '<tr><td>' + sc.name + '</td><td class="sc-distance">' + dist + ' km</td></tr>';
    });
    $list.html('<h3>Nächstgelegene Supercharger:</h3><table><tbody>' + rows.join('') + '</tbody></table>');
}

function fetchSuperchargers() {
    if (!currentVehicle) return;
    var now = Date.now();
    if (now - lastSuperchargerFetch < 60000) return;
    lastSuperchargerFetch = now;
    $.getJSON('/api/superchargers/' + currentVehicle, function(resp) {
        if (Array.isArray(resp)) {
            superchargerData = resp;
            updateSuperchargerList();
        }
    });
}




function updateUI(data) {
    var status = getStatus(data);
    $('#vehicle-status').text('Status: ' + status);
}


$('#vehicle-select').on('change', function() {
    currentVehicle = $(this).val();
    startStream();
});


function startStream() {
    if (!currentVehicle) {
        return;
    }
    if (eventSource) {
        eventSource.close();
    }
    superchargerData = [];
    updateSuperchargerList();
    lastSuperchargerFetch = 0;
    eventSource = new EventSource('/stream/' + currentVehicle);
    fetchSuperchargers();
    eventSource.onmessage = function(e) {
        var data = JSON.parse(e.data);
        if (!data.error) {
            handleData(data);
        }
    };
    eventSource.onerror = function() {
        if (eventSource) {
            eventSource.close();
        }
        var url = '/api/data';
        if (currentVehicle) {
            url += '/' + currentVehicle;
        }
        $.getJSON(url, function(data) {
            if (data && !data.error) {
                handleData(data);
            }
        });
        // Ensure the map shows Essen if no cached data was found
        map.setView(DEFAULT_POS, DEFAULT_ZOOM);
    };
}

$.getJSON('/api/config', function(cfg) {
    applyConfig(cfg);
    fetchVehicles();
});

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
updateClientCount();
