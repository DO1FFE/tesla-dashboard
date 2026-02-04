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
    var weekEl = document.getElementById('heatmap-week');
    var dayEl = document.getElementById('heatmap-day');
    var yearLabelEl = document.getElementById('heatmap-year-label');
    var monthLabelEl = document.getElementById('heatmap-month-label');
    var weekLabelEl = document.getElementById('heatmap-week-label');
    var dayLabelEl = document.getElementById('heatmap-day-label');

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
    var osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
    }).addTo(map);
    var esriLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles © Esri — Quelle: Esri, i-cubed, USDA, USGS, AEX, GeoEye, ' +
            'Getmapping, Aerogrid, IGN, IGP, UPR-EGP ' +
            'und die GIS-User-Community'
    });
    var esriLabelLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Beschriftungen © Esri'
    });
    var hybridLayer = L.layerGroup([esriLayer, esriLabelLayer]);
    L.control.layers({'Standard': osmLayer, 'Hybrid': hybridLayer, 'Satellit': esriLayer}, null, {position: 'topright'}).addTo(map);
    var heatLayer = null;
    var controlsEl = document.getElementById('heatmap-controls');
    if (controlsEl) {
        L.DomEvent.disableClickPropagation(controlsEl);
        L.DomEvent.disableScrollPropagation(controlsEl);

        var selects = controlsEl.querySelectorAll('select');
        var stopPropagation = function(event) {
            event.stopPropagation();
        };
        var disableDragging = function() {
            if (map.dragging) {
                map.dragging.disable();
            }
        };
        var enableDragging = function() {
            if (map.dragging) {
                map.dragging.enable();
            }
        };

        for (var i = 0; i < selects.length; i++) {
            selects[i].addEventListener('pointerdown', stopPropagation);
            selects[i].addEventListener('touchstart', stopPropagation);
            selects[i].addEventListener('focus', disableDragging);
            selects[i].addEventListener('pointerdown', disableDragging);
            selects[i].addEventListener('blur', enableDragging);
        }
    }

    function setFilterVisibility(scope) {
        var showYear = scope === 'year';
        var showMonth = scope === 'month';
        var showWeek = scope === 'week';
        var showDay = scope === 'day';
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
        if (weekLabelEl) {
            weekLabelEl.style.display = showWeek ? '' : 'none';
        }
        if (weekEl) {
            weekEl.style.display = showWeek ? '' : 'none';
        }
        if (dayLabelEl) {
            dayLabelEl.style.display = showDay ? '' : 'none';
        }
        if (dayEl) {
            dayEl.style.display = showDay ? '' : 'none';
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

    function selectionDescription(scope, year, month, week, day) {
        if (scope === 'year') {
            return year ? 'Jahr ' + year : 'Jahr';
        }
        if (scope === 'month') {
            return month ? 'Monat ' + month : 'Monat';
        }
        if (scope === 'week') {
            return week ? 'Woche ' + week : 'Woche';
        }
        if (scope === 'day') {
            return day ? 'Tag ' + day : 'Tag';
        }
        return 'Alle Fahrten';
    }

    function buildHeatmapUrl(scope, year, month, week, day) {
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
        if (scope === 'week' && week) {
            url += '&week=' + encodeURIComponent(week);
        }
        if (scope === 'day' && day) {
            url += '&day=' + encodeURIComponent(day);
        }
        return url;
    }

    function fetchHeatmap() {
        var scope = scopeEl ? scopeEl.value : 'all';
        var year = yearEl ? yearEl.value : '';
        var month = monthEl ? monthEl.value : '';
        var week = weekEl ? weekEl.value : '';
        var day = dayEl ? dayEl.value : '';
        var description = selectionDescription(scope, year, month, week, day);

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
        if (scope === 'week' && !week) {
            if (heatLayer) {
                map.removeLayer(heatLayer);
                heatLayer = null;
            }
            setLoading('Keine Fahrtdaten für ' + description + '.');
            return;
        }
        if (scope === 'day' && !day) {
            if (heatLayer) {
                map.removeLayer(heatLayer);
                heatLayer = null;
            }
            setLoading('Keine Fahrtdaten für ' + description + '.');
            return;
        }

        setLoading('Lade Heatmap-Daten…');
        setError('');
        fetch(buildHeatmapUrl(scope, year, month, week, day))
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

    if (weekEl) {
        weekEl.addEventListener('change', function() {
            if (!scopeEl || scopeEl.value === 'week') {
                fetchHeatmap();
            }
        });
    }

    if (dayEl) {
        dayEl.addEventListener('change', function() {
            if (!scopeEl || scopeEl.value === 'day') {
                fetchHeatmap();
            }
        });
    }

    fetchHeatmap();
})();
