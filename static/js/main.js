var currentVehicle = null;
var map = L.map('map').setView([0, 0], 13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
}).addTo(map);
var marker = L.marker([0, 0]).addTo(map);

function fetchVehicles() {
    $.getJSON('/api/vehicles', function(vehicles) {
        var $select = $('#vehicle-select');
        $select.empty();
        vehicles.forEach(function(v) {
            $select.append($('<option>').val(v.id).text(v.display_name));
        });
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
        var lat = data.drive_state && data.drive_state.latitude;
        var lng = data.drive_state && data.drive_state.longitude;
        if (lat && lng) {
            marker.setLatLng([lat, lng]);
            map.setView([lat, lng], 13);
        }
    });
}

function updateUI(data) {
    var drive = data.drive_state || {};
    var charge = data.charge_state || {};
    var html = '';
    if (charge.charging_state === 'Charging') {
        html += '<h2>Ladevorgang</h2>';
        html += '<p>Akkustand: ' + (charge.battery_level || '?') + '%</p>';
        if (charge.charger_power != null) {
            html += '<p>Ladeleistung: ' + charge.charger_power + ' kW</p>';
        }
        if (charge.charge_rate != null) {
            html += '<p>Laderate: ' + charge.charge_rate + ' km/h</p>';
        }
        if (charge.time_to_full_charge != null) {
            html += '<p>Zeit bis voll: ' + charge.time_to_full_charge + ' h</p>';
        }
        html += '<p>Status: ' + (charge.charging_state || '') + '</p>';
    } else if (drive.shift_state === 'P' || !drive.shift_state) {
        html += '<h2>Geparkt</h2>';
        html += '<p>Akkustand: ' + (charge.battery_level || '?') + '%</p>';
    } else {
        html += '<h2>Fahrt</h2>';
        html += '<p>Akkustand: ' + (charge.battery_level || '?') + '%</p>';
        if (drive.speed != null) {
            html += '<p>Geschwindigkeit: ' + drive.speed + ' km/h</p>';
        }
        if (drive.power != null) {
            html += '<p>Leistung: ' + drive.power + ' kW</p>';
        }
        if (drive.active_route_miles_to_arrival != null) {
            var km = drive.active_route_miles_to_arrival * 1.60934;
            html += '<p>km bis Ziel: ' + km.toFixed(1) + ' km</p>';
        }
    }
    $('#info').html(html);
    $('#data').text(JSON.stringify(data, null, 2));
}

$('#vehicle-select').on('change', function() {
    currentVehicle = $(this).val();
    fetchData();
});

fetchVehicles();
setInterval(fetchData, 5000);
