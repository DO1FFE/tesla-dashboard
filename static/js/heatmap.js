/* global L */
(function() {
    'use strict';

    var DEFAULT_POS = [51.4556, 7.0116]; // Essen
    var DEFAULT_ZOOM = 12;

    var mapEl = document.getElementById('map');
    var loadingEl = document.getElementById('loading-status');
    var errorEl = document.getElementById('error-status');

    function setLoading(text) {
        if (loadingEl) {
            loadingEl.textContent = text;
        }
    }

    function setError(text) {
        if (errorEl) {
            errorEl.textContent = text || '';
        }
    }

    if (!mapEl) {
        setError('Kartencontainer fehlt.');
        return;
    }

    var map = L.map(mapEl).setView(DEFAULT_POS, DEFAULT_ZOOM);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
    }).addTo(map);

    function normalizePoints(points) {
        var maxWeight = 0;
        for (var i = 0; i < points.length; i++) {
            var weight = Number(points[i][2]) || 0;
            if (weight > maxWeight) {
                maxWeight = weight;
            }
        }
        if (maxWeight <= 0) {
            maxWeight = 1;
        }
        return points.map(function(p) {
            return [p[0], p[1], (Number(p[2]) || 0) / maxWeight || 0.1];
        });
    }

    function fitBoundsForPoints(points) {
        if (!points.length) {
            return;
        }
        var bounds = L.latLngBounds(points.map(function(p) { return [p[0], p[1]]; }));
        map.fitBounds(bounds, { maxZoom: 14 });
    }

    function buildHeatLayer(points) {
        var normalized = normalizePoints(points);
        L.heatLayer(normalized, {
            radius: 25,
            blur: 15,
            maxZoom: 17
        }).addTo(map);
        fitBoundsForPoints(points);
    }

    function parseHeatmapResponse(data) {
        if (data.points && Array.isArray(data.points)) {
            return data.points;
        }
        if (data.features && Array.isArray(data.features)) {
            var pts = [];
            data.features.forEach(function(feature) {
                var coords = feature.geometry && feature.geometry.coordinates;
                var weight = feature.properties && feature.properties.weight;
                if (!coords || coords.length < 2) {
                    return;
                }
                pts.push([coords[1], coords[0], weight != null ? weight : 1]);
            });
            return pts;
        }
        return [];
    }

    function fetchHeatmap() {
        setLoading('Lade Heatmap-Daten…');
        setError('');
        fetch('/api/heatmap')
            .then(function(resp) {
                if (!resp.ok) {
                    throw new Error('HTTP ' + resp.status);
                }
                return resp.json();
            })
            .then(function(data) {
                var points = parseHeatmapResponse(data);
                if (!points.length) {
                    setLoading('Keine Fahrtdaten vorhanden.');
                    return;
                }
                buildHeatLayer(points);
                setLoading('Heatmap geladen (' + points.length + ' Punkte).');
            })
            .catch(function(err) {
                setLoading('');
                setError('Fehler beim Laden der Heatmap: ' + err.message);
            });
    }

    fetchHeatmap();
})();
