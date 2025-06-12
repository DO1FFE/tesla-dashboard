var currentVehicle = null;
var MILES_TO_KM = 1.60934;
// Default view if no coordinates are available
var DEFAULT_POS = [51.4556, 7.0116];
var DEFAULT_ZOOM = 19;
var parkStart = null;
var parkTimer = null;
// Initialize the map roughly centered on Essen with a high zoom until
// coordinates from the API are received.
var map = L.map('map').setView(DEFAULT_POS, DEFAULT_ZOOM);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
}).addTo(map);
var polyline = null;

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
    var vehicle = data.vehicle_state || {};
    updateLockStatus(vehicle.locked);
    updateUserPresence(vehicle.is_user_present);
    updateGearShift(drive.shift_state);
    updateSpeedometer(drive.speed, drive.power);
    var charge = data.charge_state || {};
    updateBatteryIndicator(charge.battery_level, charge.battery_range);
    var climate = data.climate_state || {};
    updateThermometers(climate.inside_temp, climate.outside_temp);
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

function formatParkDuration(start) {
    if (!start) {
        return '?';
    }
    var diff = Date.now() - start;
    var hours = Math.floor(diff / 3600000);
    var minutes = Math.floor((diff % 3600000) / 60000);
    var parts = [];
    if (hours > 0) {
        parts.push(hours + ' ' + (hours === 1 ? 'Stunde' : 'Stunden'));
    }
    parts.push(minutes + ' ' + (minutes === 1 ? 'Minute' : 'Minuten'));
    return parts.join(' ');
}

function updateParkTime() {
    $('#park-time').text(formatParkDuration(parkStart));
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
        $('#user-presence').text('');
        return;
    }
    var isPresent = false;
    if (typeof present === 'string') {
        var norm = present.toLowerCase();
        isPresent = norm === 'true' || norm === '1';
    } else {
        isPresent = !!present;
    }
    // use text variant of the bust in silhouette emoji so color can be applied
    $('#user-presence').text('\uD83D\uDC64\uFE0E');
    if (isPresent) {
        $('#user-presence').css('color', '#4caf50').attr('title', 'Person im Fahrzeug');
    } else {
        $('#user-presence').css('color', '#d00').attr('title', 'Keine Person im Fahrzeug');
    }
}

var MAX_SPEED = 240;
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

function updateThermometers(inside, outside) {
    if (inside == null) inside = 0;
    if (outside == null) outside = 0;
    var range = MAX_TEMP - MIN_TEMP;
    function set(prefix, temp) {
        var clamped = Math.max(MIN_TEMP, Math.min(MAX_TEMP, temp));
        var h = (clamped - MIN_TEMP) / range * 40;
        var y = 5 + 40 - h;
        var color = '#d00';
        if (temp < 15) {
            color = '#06c';
        } else if (temp < 25) {
            color = '#4caf50';
        } else if (temp < 30) {
            color = '#ff9800';
        }
        $('#' + prefix + '-level').attr('y', y).attr('height', h).css('fill', color);
        $('#' + prefix + '-bulb').css('fill', color);
        var label = isNaN(temp) ? '? °C' : temp.toFixed(1) + ' °C';
        $('#' + prefix + '-temp-value').text((prefix === 'inside' ? 'Innen: ' : 'Außen: ') + label);
    }
    set('inside', inside);
    set('outside', outside);
}

function updateBatteryIndicator(level, rangeMiles) {
    var pct = level != null ? level : 0;
    var range = rangeMiles != null ? Math.round(rangeMiles * MILES_TO_KM) : '?';
    var html = '<div class="battery"><div class="level" style="height:' + pct + '%;"></div></div>';
    html += '<div class="battery-value">' + pct + '%</div>';
    html += '<div class="range">' + range + ' km</div>';
    $('#battery-indicator').html(html);
}

function batteryBar(level) {
    var pct = level != null ? level : 0;
    return '<div class="battery-block"><div class="battery"><div class="level" style="height:' + pct + '%;"></div></div><div class="battery-value">' + pct + '%</div></div>';
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
    var parkSinceText = parkStart ? formatParkDuration(parkStart) : '';
    html += '<h2>' + status + '</h2>';
    if (status === 'Geparkt') {
        html += '<p id="park-since">Geparkt seit <span id="park-time">' + parkSinceText + '</span></p>';
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

    $('#module-charge').html('<h3>Laden</h3>' + generateTable(charge));

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

    var update = vehicle.software_update || {};
    if (Object.keys(update).length > 0) {
        $('#module-updates').html('<h3>Updates</h3>' + generateTable(update));
    } else {
        $('#module-updates').html('<h3>Updates</h3><p>Keine Daten</p>');
    }
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

fetchVehicles();
