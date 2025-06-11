var currentVehicle = null;
var MILES_TO_KM = 1.60934;
var parkStart = null;
var parkTimer = null;
var map = L.map('map').setView([0, 0], 13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
}).addTo(map);

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
            fetchData();
        }
    });
}

function fetchData() {
    if (!currentVehicle) return;
    $.getJSON('/api/data/' + currentVehicle, function(data) {
        updateUI(data);
        var drive = data.drive_state || {};
        var lat = drive.latitude;
        var lng = drive.longitude;
        if (lat && lng) {
            marker.setLatLng([lat, lng]);
            // Preserve the current zoom level when updating the map position
            map.setView([lat, lng], map.getZoom());
            if (typeof drive.heading === 'number') {
                marker.setRotationAngle(drive.heading);
            }
        }
    });
}

function updateParkTime() {
    if (!parkStart) {
        $('#park-time').text('?');
        return;
    }
    var diff = Date.now() - parkStart;
    var hours = Math.floor(diff / 3600000);
    var minutes = Math.floor((diff % 3600000) / 60000);
    $('#park-time').text(hours + ' h ' + minutes + ' min');
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

function categorizedData(data) {
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

    // Batterie und Laden
    if (charge.battery_level != null) categories['Batterie und Laden'].battery_level = charge.battery_level;
    if (charge.battery_range != null) categories['Batterie und Laden'].battery_range = (charge.battery_range * MILES_TO_KM).toFixed(1);
    if (charge.charge_rate != null) categories['Batterie und Laden'].charge_rate = (charge.charge_rate * MILES_TO_KM).toFixed(1);
    if (charge.charger_power != null) categories['Batterie und Laden'].charger_power = charge.charger_power;
    if (charge.time_to_full_charge != null) categories['Batterie und Laden'].time_to_full_charge = charge.time_to_full_charge;

    // Klimaanlage
    if (climate.inside_temp != null) categories['Klimaanlage'].inside_temp = climate.inside_temp;
    if (climate.outside_temp != null) categories['Klimaanlage'].outside_temp = climate.outside_temp;
    if (climate.hvac_auto_request != null) categories['Klimaanlage'].hvac_auto_request = climate.hvac_auto_request;
    if (climate.is_climate_on != null) categories['Klimaanlage'].is_climate_on = climate.is_climate_on;
    if (climate.seat_heater_left != null) categories['Klimaanlage'].seat_heater_left = climate.seat_heater_left;
    if (climate.seat_heater_right != null) categories['Klimaanlage'].seat_heater_right = climate.seat_heater_right;

    // Fahrstatus
    if (drive.shift_state != null) categories['Fahrstatus'].shift_state = drive.shift_state;
    if (drive.speed != null) categories['Fahrstatus'].speed = Math.round(drive.speed * MILES_TO_KM);
    if (drive.heading != null) categories['Fahrstatus'].heading = drive.heading;
    if (drive.latitude != null) categories['Fahrstatus'].latitude = drive.latitude;
    if (drive.longitude != null) categories['Fahrstatus'].longitude = drive.longitude;
    if (drive.power != null) categories['Fahrstatus'].power = drive.power;

    // Fahrzeugstatus
    if (vehicle.locked != null) categories['Fahrzeugstatus'].locked = vehicle.locked;
    if (vehicle.odometer != null) categories['Fahrzeugstatus'].odometer = Math.round(vehicle.odometer * MILES_TO_KM);
    if (vehicle.autopark_state_v2 != null) categories['Fahrzeugstatus'].autopark_state_v2 = vehicle.autopark_state_v2;
    if (vehicle.autopark_style != null) categories['Fahrzeugstatus'].autopark_style = vehicle.autopark_style;
    if (vehicle.last_autopark_error != null) categories['Fahrzeugstatus'].last_autopark_error = vehicle.last_autopark_error;
    if (vehicle.software_update && vehicle.software_update.version) categories['Fahrzeugstatus'].software_update = { version: vehicle.software_update.version };
    if (vehicle.speed_limit_mode && vehicle.speed_limit_mode.active != null) categories['Fahrzeugstatus'].speed_limit_mode = { active: vehicle.speed_limit_mode.active };
    if (vehicle.remote_start_enabled != null) categories['Fahrzeugstatus'].remote_start_enabled = vehicle.remote_start_enabled;
    if (vehicle.tpms_pressure_fl != null) categories['Fahrzeugstatus'].tpms_pressure_fl = vehicle.tpms_pressure_fl;
    if (vehicle.tpms_pressure_fr != null) categories['Fahrzeugstatus'].tpms_pressure_fr = vehicle.tpms_pressure_fr;
    if (vehicle.tpms_pressure_rl != null) categories['Fahrzeugstatus'].tpms_pressure_rl = vehicle.tpms_pressure_rl;
    if (vehicle.tpms_pressure_rr != null) categories['Fahrzeugstatus'].tpms_pressure_rr = vehicle.tpms_pressure_rr;

    // Medieninfos
    if (vehicle.media_info) {
        if (vehicle.media_info.media_playback_status != null) categories['Medieninfos'].media_playback_status = vehicle.media_info.media_playback_status;
        if (vehicle.media_info.now_playing_source != null) categories['Medieninfos'].now_playing_source = vehicle.media_info.now_playing_source;
        if (vehicle.media_info.audio_volume != null) categories['Medieninfos'].audio_volume = vehicle.media_info.audio_volume;
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

function simpleData(data) {
    var drive = data.drive_state || {};
    var charge = data.charge_state || {};
    var climate = data.climate_state || {};
    var vehicle = data.vehicle_state || {};
    var result = {};

    if (charge.charging_state === 'Charging') {
        if (charge.battery_level != null) result.battery_level = charge.battery_level;
        if (charge.battery_range != null) result.battery_range = (charge.battery_range * MILES_TO_KM).toFixed(1);
        if (charge.charge_rate != null) result.charge_rate = (charge.charge_rate * MILES_TO_KM).toFixed(1);
        if (charge.charger_power != null) result.charger_power = charge.charger_power;
        if (charge.time_to_full_charge != null) result.time_to_full_charge = charge.time_to_full_charge;
    } else if (drive.shift_state && drive.shift_state !== 'P') {
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
    var drive = data.drive_state || {};
    var charge = data.charge_state || {};
    var html = '';
    var status = '';
    parkStart = data.park_start || null;
    if (charge.charging_state === 'Charging') {
        status = 'Ladevorgang';
    } else if (drive.shift_state === 'P' || !drive.shift_state) {
        status = 'Geparkt';
    } else {
        status = 'Fahrt';
    }
    html += '<h2>' + status + '</h2>';
    if (status === 'Geparkt') {
        html += '<p>Geparkt seit <span id="park-time"></span></p>';
    }
    html += generateTable(simpleData(data));
    html += generateCategoryTables(categorizedData(data), status);
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

$('#vehicle-select').on('change', function() {
    currentVehicle = $(this).val();
    fetchData();
});

fetchVehicles();
setInterval(fetchData, 5000);
