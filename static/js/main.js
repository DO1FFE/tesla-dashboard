var currentVehicle = null;
var MILES_TO_KM = 1.60934;
var parkStart = null;
var parkTimer = null;
var map = L.map('map').setView([0, 0], 13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
}).addTo(map);
var polyline = null;

var carIcon = L.icon({
    iconUrl: 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNiIgaGVpZ2h0PSIxNiIgZmlsbD0iY3VycmVudENvbG9yIiBjbGFzcz0iYmkgYmktY2FyLWZyb250LWZpbGwiIHZpZXdCb3g9IjAgMCAxNiAxNiI+CiAgPHBhdGggZD0iTTIuNTIgMy41MTVBMi41IDIuNSAwIDAgMSA0LjgyIDJoNi4zNjJjMSAwIDEuOTA0LjU5NiAyLjI5OCAxLjUxNWwuNzkyIDEuODQ4Yy4wNzUuMTc1LjIxLjMxOS4zOC40MDQuNS4yNS44NTUuNzE1Ljk2NSAxLjI2MmwuMzM1IDEuNjc5Yy4wMzMuMTYxLjA0OS4zMjUuMDQ5LjQ5di40MTNjMCAuODE0LS4zOSAxLjU0My0xIDEuOTk3VjEzLjVhLjUuNSAwIDAgMS0uNS41aC0yYS41LjUgMCAwIDEtLjUtLjV2LTEuMzM4Yy0xLjI5Mi4wNDgtMi43NDUuMDg4LTQgLjA4OHMtMi43MDgtLjA0LTQtLjA4OFYxMy41YS41LjUgMCAwIDEtLjUuNWgtMmEuNS41IDAgMCAxLS41LS41di0xLjg5MmMtLjYxLS40NTQtMS0xLjE4My0xLTEuOTk3di0uNDEzYTIuNSAyLjUgMCAwIDEgLjA0OS0uNDlsLjMzNS0xLjY4Yy4xMS0uNTQ2LjQ2NS0xLjAxMi45NjQtMS4yNjFhLjgwNy44MDcgMCAwIDAgLjM4MS0uNDA0bC43OTItMS44NDhaTTMgMTBhMSAxIDAgMSAwIDAtMiAxIDEgMCAwIDAgMCAyWm0xMCAwYTEgMSAwIDEgMCAwLTIgMSAxIDAgMCAwIDAgMlpNNiA4YTEgMSAwIDAgMCAwIDJoNGExIDEgMCAxIDAgMC0ySDZaTTIuOTA2IDUuMTg5YS41MS41MSAwIDAgMCAuNDk3LjczMWMuOTEtLjA3MyAzLjM1LS4xNyA0LjU5Ny0uMTcgMS4yNDcgMCAzLjY4OC4wOTcgNC41OTcuMTdhLjUxLjUxIDAgMCAwIC40OTctLjczMWwtLjk1Ni0xLjkxM0EuNS41IDAgMCAwIDExLjY5MSAzSDQuMzA5YS41LjUgMCAwIDAtLjQ0Ny4yNzZMMi45MDYgNS4xOVoiLz4KPC9zdmc+',
    iconSize: [50, 50],
    iconAnchor: [25, 25]
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
    $.getJSON('/api/vehicles', function(vehicles) {
        var $select = $('#vehicle-select');
        var $label = $('label[for="vehicle-select"]');
        $select.empty();
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
    html += generateTable(simpleData(data, status));
    html += generateCategoryTables(categorizedData(data, status), status);
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
    if (!currentVehicle) return;
    if (eventSource) {
        eventSource.close();
    }
    eventSource = new EventSource('/stream/' + currentVehicle);
    eventSource.onmessage = function(e) {
        var data = JSON.parse(e.data);
        handleData(data);
    };
}

fetchVehicles();
