var currentVehicle = null;
var map = L.map('map').setView([0, 0], 13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Map data © OpenStreetMap contributors'
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
        $('#data').text(JSON.stringify(data, null, 2));
        var lat = data.drive_state && data.drive_state.latitude;
        var lng = data.drive_state && data.drive_state.longitude;
        if (lat && lng) {
            marker.setLatLng([lat, lng]);
            map.setView([lat, lng], 13);
        }
    });
}

$('#vehicle-select').on('change', function() {
    currentVehicle = $(this).val();
    fetchData();
});

fetchVehicles();
setInterval(fetchData, 5000);
