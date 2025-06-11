var currentVehicle = null;
var MILES_TO_KM = 1.60934;
var parkStart = null;
var parkTimer = null;
var map = L.map('map').setView([0, 0], 13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
}).addTo(map);

var carIcon = L.icon({
    iconUrl: 'data:image/png;base64,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',
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
    if (!parkStart) return;
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
    var result = {};

    if (charge.charging_state === 'Charging') {
        if (charge.battery_level != null) result.battery_level = charge.battery_level;
        if (charge.charge_rate != null) result.charge_rate = (charge.charge_rate * MILES_TO_KM).toFixed(1);
        if (charge.charger_power != null) result.charger_power = charge.charger_power;
        if (charge.time_to_full_charge != null) result.time_to_full_charge = charge.time_to_full_charge;
    } else if (drive.shift_state && drive.shift_state !== 'P') {
        if (drive.speed != null) result.speed = Math.round(drive.speed * MILES_TO_KM);
        if (drive.active_route_miles_to_arrival != null) result.distance_to_arrival = (drive.active_route_miles_to_arrival * MILES_TO_KM).toFixed(1);
        if (charge.battery_level != null) result.battery_level = charge.battery_level;
        if (charge.battery_range != null) result.battery_range = (charge.battery_range * MILES_TO_KM).toFixed(1);
    } else {
        if (charge.battery_level != null) result.battery_level = charge.battery_level;
        if (charge.battery_range != null) result.battery_range = (charge.battery_range * MILES_TO_KM).toFixed(1);
        if (data.vehicle_state && data.vehicle_state.odometer != null) result.odometer = Math.round(data.vehicle_state.odometer * MILES_TO_KM);
        if (data.vehicle_state && data.vehicle_state.tpms_pressure_fl != null) result.tpms_pressure_fl = data.vehicle_state.tpms_pressure_fl;
        if (data.vehicle_state && data.vehicle_state.tpms_pressure_fr != null) result.tpms_pressure_fr = data.vehicle_state.tpms_pressure_fr;
        if (data.vehicle_state && data.vehicle_state.tpms_pressure_rl != null) result.tpms_pressure_rl = data.vehicle_state.tpms_pressure_rl;
        if (data.vehicle_state && data.vehicle_state.tpms_pressure_rr != null) result.tpms_pressure_rr = data.vehicle_state.tpms_pressure_rr;
        if (drive.power != null) result.power = drive.power;
        if (data.vehicle_state) {
            var auxPower = null;
            if (data.vehicle_state.aux_battery_power != null) {
                auxPower = data.vehicle_state.aux_battery_power;
            } else if (data.vehicle_state.aux_battery_voltage != null && data.vehicle_state.aux_battery_current != null) {
                auxPower = Math.round(data.vehicle_state.aux_battery_voltage * data.vehicle_state.aux_battery_current);
            }
            if (auxPower != null) result.aux_battery_power = auxPower;
        }
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
    if (status === 'Geparkt' && parkStart) {
        html += '<p>Geparkt seit <span id="park-time"></span></p>';
        updateParkTime();
        if (!parkTimer) {
            parkTimer = setInterval(updateParkTime, 60000);
        }
    } else {
        if (parkTimer) {
            clearInterval(parkTimer);
            parkTimer = null;
        }
    }
    html += generateTable(simpleData(data));
    html += generateCategoryTables(categorizedData(data), status);
    $('#info').html(html);
}

$('#vehicle-select').on('change', function() {
    currentVehicle = $(this).val();
    fetchData();
});

fetchVehicles();
setInterval(fetchData, 5000);
