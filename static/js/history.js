var map = L.map('map').setView([51.4556, 7.0116], 13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
}).addTo(map);

if (Array.isArray(tripPath) && tripPath.length) {
    var poly = L.polyline(tripPath, {color: 'blue'}).addTo(map);
    map.fitBounds(poly.getBounds());
    var arrowIcon = L.divIcon({
        html: '<svg width="30" height="30" viewBox="0 0 30 30"><polygon points="15,0 30,30 15,22 0,30" /></svg>',
        className: 'arrow-icon',
        iconSize: [30, 30],
        iconAnchor: [15, 15]
    });
    L.marker(tripPath[tripPath.length - 1], {
        icon: arrowIcon,
        rotationAngle: tripHeading,
        rotationOrigin: 'center center'
    }).addTo(map);
}
