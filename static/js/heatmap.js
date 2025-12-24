/* global L */
(function() {
    'use strict';

    var DEFAULT_POS = [51.4556, 7.0116]; // Essen
    var DEFAULT_ZOOM = 12;

    var mapEl = document.getElementById('map');
    var loadingEl = document.getElementById('loading-status');
    var errorEl = document.getElementById('error-status');
    var scopeEl = document.getElementById('heatmap-scope');
    var yearEl = document.getElementById('heatmap-year');
    var monthEl = document.getElementById('heatmap-month');
    var yearLabelEl = document.getElementById('heatmap-year-label');
    var monthLabelEl = document.getElementById('heatmap-month-label');

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
    var heatLayer = null;

    function setFilterVisibility(scope) {
        var showYear = scope === 'year';
        var showMonth = scope === 'month';
        if (yearLabelEl) {
            yearLabelEl.style.display = showYear ? '' : 'none';
        }
        if (yearEl) {
            yearEl.style.display = showYear ? '' : 'none';
        }
        if (monthLabelEl) {
            monthLabelEl.style.display = showMonth ? '' : 'none';
        }
        if (monthEl) {
            monthEl.style.display = showMonth ? '' : 'none';
        }
    }

    function normalizePoints(points) {
        var maxWeight = 0;
        var sanitized = [];
        for (var i = 0; i < points.length; i++) {
            var lat = Number(points[i][0]);
            var lon = Number(points[i][1]);
            if (!isFinite(lat) || !isFinite(lon)) {
                continue;
            }
            var weight = Number(points[i][2]);
            if (!isFinite(weight)) {
                weight = 1;
            }
            if (weight < 0) {
                weight = 0;
            }
            sanitized.push([lat, lon, weight]);
            if (weight > maxWeight) {
                maxWeight = weight;
            }
        }
        if (maxWeight <= 0) {
            maxWeight = 1;
        }
        return { points: sanitized, maxWeight: maxWeight };
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
        if (heatLayer) {
            map.removeLayer(heatLayer);
        }
        heatLayer = L.heatLayer(normalized.points, {
            radius: 25,
            blur: 15,
            maxZoom: 17,
            max: normalized.maxWeight,
            minOpacity: 0.2,
            gradient: {
                0.0: 'blue',
                0.2: 'cyan',
                0.4: 'lime',
                0.7: 'yellow',
                1.0: 'red'
            }
        }).addTo(map);
        fitBoundsForPoints(normalized.points);
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

    function selectionDescription(scope, year, month) {
        if (scope === 'year') {
            return year ? 'Jahr ' + year : 'Jahr';
        }
        if (scope === 'month') {
            return month ? 'Monat ' + month : 'Monat';
        }
        return 'Alle Fahrten';
    }

    function buildHeatmapUrl(scope, year, month) {
        var url = '/api/heatmap?max_points=0';
        if (scope) {
            url += '&scope=' + encodeURIComponent(scope);
        }
        if (scope === 'year' && year) {
            url += '&year=' + encodeURIComponent(year);
        }
        if (scope === 'month' && month) {
            url += '&month=' + encodeURIComponent(month);
        }
        return url;
    }

    function fetchHeatmap() {
        var scope = scopeEl ? scopeEl.value : 'all';
        var year = yearEl ? yearEl.value : '';
        var month = monthEl ? monthEl.value : '';
        var description = selectionDescription(scope, year, month);

        if (scope === 'year' && !year) {
            if (heatLayer) {
                map.removeLayer(heatLayer);
                heatLayer = null;
            }
            setLoading('Keine Fahrtdaten für ' + description + '.');
            return;
        }
        if (scope === 'month' && !month) {
            if (heatLayer) {
                map.removeLayer(heatLayer);
                heatLayer = null;
            }
            setLoading('Keine Fahrtdaten für ' + description + '.');
            return;
        }

        setLoading('Lade Heatmap-Daten…');
        setError('');
        fetch(buildHeatmapUrl(scope, year, month))
            .then(function(resp) {
                if (!resp.ok) {
                    throw new Error('HTTP ' + resp.status);
                }
                return resp.json();
            })
            .then(function(data) {
                var points = parseHeatmapResponse(data);
                if (!points.length) {
                    if (heatLayer) {
                        map.removeLayer(heatLayer);
                        heatLayer = null;
                    }
                    setLoading('Keine Fahrtdaten für ' + description + '.');
                    return;
                }
                buildHeatLayer(points);
                setLoading(
                    'Heatmap geladen (' + description + ', ' + points.length + ' Punkte).'
                );
            })
            .catch(function(err) {
                setLoading('');
                setError('Fehler beim Laden der Heatmap: ' + err.message);
            });
    }

    if (scopeEl) {
        setFilterVisibility(scopeEl.value);
        scopeEl.addEventListener('change', function() {
            setFilterVisibility(scopeEl.value);
            fetchHeatmap();
        });
    }

    if (yearEl) {
        yearEl.addEventListener('change', function() {
            if (!scopeEl || scopeEl.value === 'year') {
                fetchHeatmap();
            }
        });
    }

    if (monthEl) {
        monthEl.addEventListener('change', function() {
            if (!scopeEl || scopeEl.value === 'month') {
                fetchHeatmap();
            }
        });
    }

    fetchHeatmap();
})();
