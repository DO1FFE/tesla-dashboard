var currentVehicle = null;
var MILES_TO_KM = 1.60934;
var parkStart = null;
var parkTimer = null;
// Initialize the map roughly centered on Essen with a high zoom until
// coordinates from the API are received.
var map = L.map('map').setView([51.4556, 7.0116], 19);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
}).addTo(map);
var polyline = null;

var carIcon = L.icon({
    iconUrl: "data:image/png;base64,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",
    iconSize: [30, 30],
    iconAnchor: [15, 15]
});

var marker = L.marker([0, 0], {
    icon: carIcon,
    rotationAngle: 0,
    rotationOrigin: 'center center'
}).addTo(map);
var eventSource = null;

function updateHeader(data) {
    var info = '';
    if (data && data.display_name) {
        info = 'für ' + data.display_name;
        var version = data.vehicle_state && data.vehicle_state.car_version;
        if (version) {
            info += ' (' + version + ')';
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
            $('#errors').text(resp.error || 'Keine Fahrzeuge gefunden. Bitte Tesla-Zugangsdaten pr\xC3\xBCfen.');
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
    updateModules(data);
    var drive = data.drive_state || {};
    var lat = drive.latitude;
    var lng = drive.longitude;
    if (lat && lng) {
        marker.setLatLng([lat, lng]);
        map.setView([lat, lng], map.getZoom());
        if (typeof drive.heading === 'number') {
            marker.setRotationAngle(drive.heading);
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
}

function updateParkTime() {
    if (!parkStart) {
        $('#park-time').text('?');
        return;
    }
    var diff = Date.now() - parkStart;
    var hours = Math.floor(diff / 3600000);
    var minutes = Math.floor((diff % 3600000) / 60000);
    var parts = [];
    if (hours > 0) {
        parts.push(hours + ' ' + (hours === 1 ? 'Stunde' : 'Stunden'));
    }
    parts.push(minutes + ' ' + (minutes === 1 ? 'Minute' : 'Minuten'));
    $('#park-time').text(parts.join(' '));
}

function batteryBar(level) {
    var pct = level != null ? level : 0;
    var color = '#4caf50';
    if (pct < 20) {
        color = '#f44336';
    } else if (pct < 50) {
        color = '#ffc107';
    }
    return '<div class="battery"><div class="level" style="width:' + pct + '%; background:' + color + '"></div></div> ' + pct + '%';
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

var DESCRIPTIONS = {
    // Wichtige Felder mit fest hinterlegter Übersetzung
    'battery_level': 'Akkustand (%)',
    'battery_range': 'Reichweite (km)',
    'est_battery_range': 'Restreichweite (km)',
    'odometer': 'Kilometerstand (km)',
    'outside_temp': 'Außen­temperatur (°C)',
    'inside_temp': 'Innenraum­temperatur (°C)',
    'speed': 'Geschwindigkeit (km/h)',
    'heading': 'Richtung (°)',
    'charge_rate': 'Laderate (km/h)',
    'charger_power': 'Ladeleistung (kW)',
    'time_to_full_charge': 'Zeit bis voll (h)',
    'tpms_pressure_fl': 'Reifen vorne links (bar)',
    'tpms_pressure_fr': 'Reifen vorne rechts (bar)',
    'tpms_pressure_rl': 'Reifen hinten links (bar)',
    'tpms_pressure_rr': 'Reifen hinten rechts (bar)',
    'power': 'Verbrauch (kW)',
    'aux_battery_power': '12V-Verbrauch (W)',
    'charge_state': 'Ladezustand',
    'climate_state': 'Klimazustand',
    'drive_state': 'Fahrstatus',
    'gui_settings': 'GUI‑Einstellungen',
    'vehicle_config': 'Fahrzeugkonfiguration',
    'vehicle_state': 'Fahrzeugstatus',
    'media_info': 'Medieninfos',
    'media_state': 'Medienstatus',
    'distance_to_arrival': 'Entfernung zum Ziel (km)'
};

var WORD_MAP = {
    'battery': 'Batterie',
    'heater': 'Heizung',
    'on': 'an',
    'off': 'aus',
    'range': 'Reichweite',
    'level': 'Stand',
    'charge': 'Laden',
    'power': 'Leistung',
    'voltage': 'Spannung',
    'current': 'Strom',
    'temperature': 'Temperatur',
    'speed': 'Geschwindigkeit',
    'odometer': 'Kilometerzähler',
    'pressure': 'Druck',
    'front': 'vorn',
    'rear': 'hinten',
    'left': 'links',
    'right': 'rechts',
    'fl': 'vorne links',
    'fr': 'vorne rechts',
    'rl': 'hinten links',
    'rr': 'hinten rechts',
    'vehicle': 'Fahrzeug',
    'state': 'Status',
    'mode': 'Modus',
    'sun': 'Sonnen',
    'roof': 'Dach',
    'update': 'Update',
    'webcam': 'Webcam'
};

function describe(key) {
    if (DESCRIPTIONS[key]) {
        return DESCRIPTIONS[key];
    }
    var words = key.split('_');
    var result = words.map(function(w) {
        return WORD_MAP[w] || w;
    }).join(' ');
    return result.charAt(0).toUpperCase() + result.slice(1);
}


function generateTable(obj) {
    var html = '<table class="info-table">';
    Object.keys(obj).sort().forEach(function(key) {
        var value = obj[key];
        if (value === null || value === undefined) {
            return;
        }
        if (typeof value === 'object') {
            html += '<tr><th colspan="2">' + describe(key) + '</th></tr>';
            html += '<tr><td colspan="2">' + generateTable(value) + '</td></tr>';
        } else {
            if (key === 'battery_level') {
                value = batteryBar(value);
            }
            html += '<tr><th>' + describe(key) + '</th><td>' + value + '</td></tr>';
        }
    });
    html += '</table>';
    return html;
}

function categorizedData(data, status) {
    var charge = data.charge_state || {};
    var climate = data.climate_state || {};
    var drive = data.drive_state || {};
    var vehicle = data.vehicle_state || {};
    var categories = {
        'Batterie und Laden': {},
        'Klimaanlage': {},
        'Fahrstatus': {},
        'Fahrzeugstatus': {},
        'Medieninfos': {}
    };

    function add(cat, key, val) {
        if (val !== null && val !== undefined) {
            categories[cat][key] = val;
        }
    }

    if (status === 'Ladevorgang') {
        add('Batterie und Laden', 'battery_level', charge.battery_level);
        add('Batterie und Laden', 'battery_range', charge.battery_range != null ? (charge.battery_range * MILES_TO_KM).toFixed(1) : null);
        add('Batterie und Laden', 'charge_rate', charge.charge_rate != null ? (charge.charge_rate * MILES_TO_KM).toFixed(1) : null);
        add('Batterie und Laden', 'charger_power', charge.charger_power);
        add('Batterie und Laden', 'time_to_full_charge', charge.time_to_full_charge);

        add('Klimaanlage', 'inside_temp', climate.inside_temp);
        add('Klimaanlage', 'outside_temp', climate.outside_temp);
        add('Klimaanlage', 'is_climate_on', climate.is_climate_on);

        add('Fahrzeugstatus', 'locked', vehicle.locked);
        add('Fahrzeugstatus', 'odometer', vehicle.odometer != null ? Math.round(vehicle.odometer * MILES_TO_KM) : null);
        add('Fahrzeugstatus', 'remote_start_enabled', vehicle.remote_start_enabled);
        add('Fahrzeugstatus', 'tpms_pressure_fl', vehicle.tpms_pressure_fl);
        add('Fahrzeugstatus', 'tpms_pressure_fr', vehicle.tpms_pressure_fr);
        add('Fahrzeugstatus', 'tpms_pressure_rl', vehicle.tpms_pressure_rl);
        add('Fahrzeugstatus', 'tpms_pressure_rr', vehicle.tpms_pressure_rr);
        if (vehicle.software_update && vehicle.software_update.version) add('Fahrzeugstatus', 'software_update', { version: vehicle.software_update.version });
        if (vehicle.speed_limit_mode && vehicle.speed_limit_mode.active != null) add('Fahrzeugstatus', 'speed_limit_mode', { active: vehicle.speed_limit_mode.active });
    } else if (status === 'Fahrt') {
        add('Batterie und Laden', 'battery_level', charge.battery_level);
        add('Batterie und Laden', 'battery_range', charge.battery_range != null ? (charge.battery_range * MILES_TO_KM).toFixed(1) : null);

        add('Fahrstatus', 'shift_state', drive.shift_state);
        add('Fahrstatus', 'speed', drive.speed != null ? Math.round(drive.speed * MILES_TO_KM) : null);
        add('Fahrstatus', 'heading', drive.heading);
        add('Fahrstatus', 'latitude', drive.latitude);
        add('Fahrstatus', 'longitude', drive.longitude);
        add('Fahrstatus', 'power', drive.power);
        if (drive.active_route_miles_to_arrival != null) add('Fahrstatus', 'distance_to_arrival', (drive.active_route_miles_to_arrival * MILES_TO_KM).toFixed(1));

        add('Fahrzeugstatus', 'locked', vehicle.locked);
        add('Fahrzeugstatus', 'odometer', vehicle.odometer != null ? Math.round(vehicle.odometer * MILES_TO_KM) : null);
        add('Fahrzeugstatus', 'remote_start_enabled', vehicle.remote_start_enabled);
    } else { // Geparkt
        add('Batterie und Laden', 'battery_level', charge.battery_level);
        add('Batterie und Laden', 'battery_range', charge.battery_range != null ? (charge.battery_range * MILES_TO_KM).toFixed(1) : null);

        add('Klimaanlage', 'inside_temp', climate.inside_temp);
        add('Klimaanlage', 'outside_temp', climate.outside_temp);
        add('Klimaanlage', 'is_climate_on', climate.is_climate_on);
        add('Klimaanlage', 'seat_heater_left', climate.seat_heater_left);
        add('Klimaanlage', 'seat_heater_right', climate.seat_heater_right);

        add('Fahrzeugstatus', 'locked', vehicle.locked);
        add('Fahrzeugstatus', 'odometer', vehicle.odometer != null ? Math.round(vehicle.odometer * MILES_TO_KM) : null);
        add('Fahrzeugstatus', 'tpms_pressure_fl', vehicle.tpms_pressure_fl);
        add('Fahrzeugstatus', 'tpms_pressure_fr', vehicle.tpms_pressure_fr);
        add('Fahrzeugstatus', 'tpms_pressure_rl', vehicle.tpms_pressure_rl);
        add('Fahrzeugstatus', 'tpms_pressure_rr', vehicle.tpms_pressure_rr);
        add('Fahrzeugstatus', 'power', drive.power);
        var auxPower = null;
        if (vehicle.aux_battery_power != null) {
            auxPower = vehicle.aux_battery_power;
        } else if (vehicle.aux_battery_voltage != null && vehicle.aux_battery_current != null) {
            auxPower = Math.round(vehicle.aux_battery_voltage * vehicle.aux_battery_current);
        }
        add('Fahrzeugstatus', 'aux_battery_power', auxPower);
    }

    if (vehicle.media_info) {
        add('Medieninfos', 'media_playback_status', vehicle.media_info.media_playback_status);
        add('Medieninfos', 'now_playing_source', vehicle.media_info.now_playing_source);
        add('Medieninfos', 'audio_volume', vehicle.media_info.audio_volume);
    }

    return categories;
}

function generateCategoryTables(cats, status) {
    var html = '';
    var allowed = [];
    if (status === 'Ladevorgang') {
        allowed = ['Batterie und Laden', 'Klimaanlage', 'Fahrzeugstatus', 'Medieninfos'];
    } else if (status === 'Fahrt') {
        allowed = ['Batterie und Laden', 'Fahrstatus', 'Fahrzeugstatus', 'Medieninfos'];
    } else {
        allowed = ['Batterie und Laden', 'Fahrzeugstatus', 'Klimaanlage', 'Medieninfos'];
    }
    Object.keys(cats).forEach(function(name) {
        if (allowed.indexOf(name) === -1) return;
        var obj = cats[name];
        if (Object.keys(obj).length === 0) return;
        html += '<h3>' + name + '</h3>' + generateTable(obj);
    });
    return html;
}

function simpleData(data, status) {
    var drive = data.drive_state || {};
    var charge = data.charge_state || {};
    var climate = data.climate_state || {};
    var vehicle = data.vehicle_state || {};
    var result = {};

    if (status === 'Ladevorgang') {
        if (charge.battery_level != null) result.battery_level = charge.battery_level;
        if (charge.battery_range != null) result.battery_range = (charge.battery_range * MILES_TO_KM).toFixed(1);
        if (charge.charge_rate != null) result.charge_rate = (charge.charge_rate * MILES_TO_KM).toFixed(1);
        if (charge.charger_power != null) result.charger_power = charge.charger_power;
        if (charge.time_to_full_charge != null) result.time_to_full_charge = charge.time_to_full_charge;
    } else if (status === 'Fahrt') {
        if (drive.speed != null) result.speed = Math.round(drive.speed * MILES_TO_KM);
        if (drive.heading != null) result.heading = drive.heading;
        if (drive.active_route_miles_to_arrival != null) result.distance_to_arrival = (drive.active_route_miles_to_arrival * MILES_TO_KM).toFixed(1);
        if (charge.battery_level != null) result.battery_level = charge.battery_level;
        if (charge.battery_range != null) result.battery_range = (charge.battery_range * MILES_TO_KM).toFixed(1);
        if (climate.outside_temp != null) result.outside_temp = climate.outside_temp;
    } else {
        if (charge.battery_level != null) result.battery_level = charge.battery_level;
        if (charge.battery_range != null) result.battery_range = (charge.battery_range * MILES_TO_KM).toFixed(1);
        if (vehicle.odometer != null) result.odometer = Math.round(vehicle.odometer * MILES_TO_KM);
        if (vehicle.tpms_pressure_fl != null) result.tpms_pressure_fl = vehicle.tpms_pressure_fl;
        if (vehicle.tpms_pressure_fr != null) result.tpms_pressure_fr = vehicle.tpms_pressure_fr;
        if (vehicle.tpms_pressure_rl != null) result.tpms_pressure_rl = vehicle.tpms_pressure_rl;
        if (vehicle.tpms_pressure_rr != null) result.tpms_pressure_rr = vehicle.tpms_pressure_rr;
        if (drive.power != null) result.power = drive.power;
        var auxPower = null;
        if (vehicle.aux_battery_power != null) {
            auxPower = vehicle.aux_battery_power;
        } else if (vehicle.aux_battery_voltage != null && vehicle.aux_battery_current != null) {
            auxPower = Math.round(vehicle.aux_battery_voltage * vehicle.aux_battery_current);
        }
        if (auxPower != null) result.aux_battery_power = auxPower;
    }

    return result;
}

function updateUI(data) {
    var html = '';
    var status = getStatus(data);
    parkStart = data.park_start || null;
    html += '<h2>' + status + '</h2>';
    if (status === 'Geparkt') {
        html += '<p id="park-since">Geparkt seit <span id="park-time"></span></p>';
    }
    // Only show status and parking duration, omit detailed tables
    $('#info').html(html);
    if (status === 'Geparkt' && parkStart) {
        updateParkTime();
        if (!parkTimer) {
            parkTimer = setInterval(updateParkTime, 60000);
        }
    } else {
        if (parkTimer) {
            clearInterval(parkTimer);
            parkTimer = null;
        }
        if (status === 'Geparkt') {
            $('#park-time').text('?');
        }
    }
}

function updateModules(data) {
    var drive = data.drive_state || {};
    $('#module-drive').html('<h3>Fahrstatus</h3>' + generateTable(drive));

    var climate = data.climate_state || {};
    $('#module-climate').html('<h3>Klima</h3>' + generateTable(climate));

    var charge = data.charge_state || {};
    var battery = {
        battery_level: charge.battery_level,
        est_battery_range: charge.est_battery_range != null ? (charge.est_battery_range * MILES_TO_KM).toFixed(1) : null
    };
    $('#module-battery').html('<h3>Batterie</h3>' + generateTable(battery));

    var vehicle = data.vehicle_state || {};
    var tires = {
        tpms_pressure_fl: vehicle.tpms_pressure_fl,
        tpms_pressure_fr: vehicle.tpms_pressure_fr,
        tpms_pressure_rl: vehicle.tpms_pressure_rl,
        tpms_pressure_rr: vehicle.tpms_pressure_rr
    };
    $('#module-tires').html('<h3>Reifen</h3>' + generateTable(tires));

    if (vehicle.media_info) {
        $('#module-media').html('<h3>Media</h3>' + generateTable(vehicle.media_info));
    } else {
        $('#module-media').html('<h3>Media</h3><p>Keine Daten</p>');
    }
}

$('#vehicle-select').on('change', function() {
    currentVehicle = $(this).val();
    startStream();
});


function startStream() {
    if (!currentVehicle) {
        $('#errors').text('Kein Fahrzeug ausgew\xC3\xA4hlt.');
        return;
    }
    if (eventSource) {
        eventSource.close();
    }
    eventSource = new EventSource('/stream/' + currentVehicle);
    eventSource.onmessage = function(e) {
        var data = JSON.parse(e.data);
        if (data.error) {
            $('#errors').text(data.error);
        } else {
            handleData(data);
        }
    };
    eventSource.onerror = function() {
        $('#errors').text('Live-Daten konnten nicht geladen werden. Lade Cache.');
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
    };
}

function fetchErrors() {
    $.getJSON('/error', function(errs) {
        if (!errs.length) {
            $('#errors').text('');
            return;
        }
        var html = '<h3>Fehler</h3><ul>';
        errs.forEach(function(e) {
            var d = new Date(e.timestamp * 1000);
            html += '<li>' + d.toLocaleString() + ': ' + e.message + '</li>';
        });
        html += '</ul>';
        $('#errors').html(html);
    });
}

fetchVehicles();
fetchErrors();
setInterval(fetchErrors, 10000);
