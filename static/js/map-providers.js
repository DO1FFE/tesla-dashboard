/* global L */
(function() {
    'use strict';

    function erstelleAttributionsKontrolle(karte) {
        if (!karte || !L || !L.Control || !L.Control.Attribution) {
            return null;
        }
        var BenutzerAttribution = L.Control.Attribution.extend({
            _update: function() {
                if (!this._map) {
                    return;
                }
                var attributionen = [];
                for (var eintrag in this._attributions) {
                    if (this._attributions[eintrag]) {
                        attributionen.push(eintrag);
                    }
                }
                this._container.innerHTML = attributionen.join('<br>');
            }
        });
        var kontrolle = new BenutzerAttribution({ prefix: false });
        kontrolle.addTo(karte);
        return kontrolle;
    }

    function erstelleKartenLayerKonfiguration(karte, optionen) {
        if (!karte || !L) {
            return null;
        }
        var einstellungen = optionen || {};
        var labelsPaneName = einstellungen.labelsPaneName || 'labels';
        var labelsPane = null;

        if (karte.createPane && labelsPaneName) {
            labelsPane = karte.createPane(labelsPaneName);
            if (labelsPane && labelsPane.style) {
                labelsPane.style.zIndex = einstellungen.labelsPaneZIndex || 650;
                labelsPane.style.pointerEvents = einstellungen.labelsPanePointerEvents || 'none';
            }
        }

        var osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
        }).addTo(karte);
        var esriLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles © Esri — Quelle: Esri, i-cubed, USDA, USGS, AEX, GeoEye, ' +
                'Getmapping, Aerogrid, IGN, IGP, UPR-EGP ' +
                'und die GIS-User-Community'
        });
        var esriLabelOptionen = {
            attribution: 'Beschriftungen © Esri'
        };
        if (labelsPane) {
            esriLabelOptionen.pane = labelsPaneName;
            esriLabelOptionen.zIndex = einstellungen.labelsPaneZIndex || 650;
        }
        var esriLabelLayer = L.tileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
            esriLabelOptionen
        );
        var esriHybridLayer = L.layerGroup([esriLayer, esriLabelLayer]);
        var kartenAnsichtLayer = {
            standard: osmLayer,
            hybrid: esriHybridLayer,
            'hybrid-esri': esriHybridLayer,
            satellit: esriLayer
        };

        return {
            labelsPane: labelsPane,
            osmLayer: osmLayer,
            esriLayer: esriLayer,
            esriLabelLayer: esriLabelLayer,
            esriHybridLayer: esriHybridLayer,
            kartenAnsichtLayer: kartenAnsichtLayer,
            aktiveKartenAnsicht: osmLayer
        };
    }

    function setzeKartenAnsicht(karte, kartenAnsichtLayer, aktiveKartenAnsicht, ansicht) {
        if (!karte || !kartenAnsichtLayer) {
            return aktiveKartenAnsicht || null;
        }
        var zielLayer = kartenAnsichtLayer[ansicht] || kartenAnsichtLayer.standard || aktiveKartenAnsicht;
        if (aktiveKartenAnsicht && karte.hasLayer && karte.hasLayer(aktiveKartenAnsicht)) {
            karte.removeLayer(aktiveKartenAnsicht);
        }
        if (zielLayer && karte.addLayer && (!karte.hasLayer || !karte.hasLayer(zielLayer))) {
            karte.addLayer(zielLayer);
        }
        return zielLayer;
    }

    function ermittleAktiveKartenAnsicht(kartenAnsichtOptionen) {
        if (!kartenAnsichtOptionen || !kartenAnsichtOptionen.length) {
            return 'standard';
        }
        for (var i = 0; i < kartenAnsichtOptionen.length; i++) {
            if (kartenAnsichtOptionen[i].checked) {
                return kartenAnsichtOptionen[i].value;
            }
        }
        return 'standard';
    }

    function bindeKartenAnsichtOptionen(karte, kartenAnsichtLayer, kartenAnsichtOptionen, aktiveKartenAnsicht) {
        if (!kartenAnsichtOptionen || !kartenAnsichtOptionen.length) {
            return aktiveKartenAnsicht || null;
        }
        var handleChange = function(event) {
            if (event.target && event.target.checked) {
                aktiveKartenAnsicht = setzeKartenAnsicht(
                    karte,
                    kartenAnsichtLayer,
                    aktiveKartenAnsicht,
                    event.target.value
                );
            }
        };
        for (var i = 0; i < kartenAnsichtOptionen.length; i++) {
            kartenAnsichtOptionen[i].addEventListener('change', handleChange);
        }
        return setzeKartenAnsicht(
            karte,
            kartenAnsichtLayer,
            aktiveKartenAnsicht,
            ermittleAktiveKartenAnsicht(kartenAnsichtOptionen)
        );
    }

    window.erstelleAttributionsKontrolle = erstelleAttributionsKontrolle;
    window.erstelleKartenLayerKonfiguration = erstelleKartenLayerKonfiguration;
    window.setzeKartenAnsicht = setzeKartenAnsicht;
    window.ermittleAktiveKartenAnsicht = ermittleAktiveKartenAnsicht;
    window.bindeKartenAnsichtOptionen = bindeKartenAnsichtOptionen;
})();
