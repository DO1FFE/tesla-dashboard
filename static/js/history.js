var map = L.map('map').setView([51.4556, 7.0116], 13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
}).addTo(map);

function bearing(p1, p2) {
    var lat1 = p1[0] * Math.PI / 180;
    var lon1 = p1[1] * Math.PI / 180;
    var lat2 = p2[0] * Math.PI / 180;
    var lon2 = p2[1] * Math.PI / 180;
    var y = Math.sin(lon2 - lon1) * Math.cos(lat2);
    var x = Math.cos(lat1) * Math.sin(lat2) -
            Math.sin(lat1) * Math.cos(lat2) * Math.cos(lon2 - lon1);
    var brng = Math.atan2(y, x) * 180 / Math.PI;
    return (brng + 360) % 360;
}

if (Array.isArray(tripPath) && tripPath.length) {
    var coords = tripPath.map(function(p) { return [p[0], p[1]]; });
    var poly = L.polyline(coords, {color: 'blue'}).addTo(map);
    map.fitBounds(poly.getBounds());

    var arrowIcon = L.divIcon({
        html: '<svg width="30" height="30" viewBox="0 0 30 30"><polygon points="15,0 30,30 15,22 0,30" /></svg>',
        className: 'arrow-icon',
        iconSize: [30, 30],
        iconAnchor: [15, 15]
    });

    var marker = L.marker(coords[coords.length - 1], {
        icon: arrowIcon,
        rotationAngle: tripHeading,
        rotationOrigin: 'center center'
    }).addTo(map);

    function updateInfo(idx) {
        var point = tripPath[idx];
        var text = [];
        if (point[4]) {
            var date = new Date(point[4]);
            text.push(date.toLocaleString());
        }
        if (point[2] !== null && point[2] !== undefined && point[2] !== '') {
            text.push('Geschwindigkeit: ' + point[2] + ' km/h');
        }
        if (point[3] !== null && point[3] !== undefined && point[3] !== '') {
            text.push('Power: ' + point[3] + ' kW');
        }
        document.getElementById('point-info').textContent = text.join(' | ');
    }

    function updateMarker(idx) {
        var point = tripPath[idx];
        marker.setLatLng([point[0], point[1]]);
        var angle = 0;
        if (idx > 0) {
            angle = bearing(tripPath[idx - 1], point);
        }
        marker.setRotationAngle(angle);
        updateInfo(idx);
    }

    var slider = document.getElementById('point-slider');
    slider.max = tripPath.length - 1;
    slider.value = tripPath.length - 1;

    var originalZoom = null;
    var zoomTimeout = null;

    slider.addEventListener('input', function() {
        var idx = parseInt(this.value, 10);
        updateMarker(idx);
        var latlng = marker.getLatLng();

        if (originalZoom === null) {
            originalZoom = map.getZoom();
        }
        var maxZoom = typeof map.getMaxZoom === 'function' ? map.getMaxZoom() : 18;
        map.setView(latlng, maxZoom);

        if (zoomTimeout) {
            clearTimeout(zoomTimeout);
        }
        zoomTimeout = setTimeout(function() {
            if (originalZoom !== null) {
                map.setZoom(originalZoom);
                originalZoom = null;
            }
        }, 3000);
    });

    updateMarker(tripPath.length - 1);
    map.setView(marker.getLatLng(), map.getZoom());
}
