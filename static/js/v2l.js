(function () {
    'use strict';

    var body = document.body;
    var vehicleId = body.getAttribute('data-vehicle-id') || 'default';
    var csrfMeta = document.querySelector('meta[name="csrf-token"]');
    var csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
    var aktuellerPayload = null;
    var abfrageTimer = null;
    var aktionLaeuft = false;

    function element(id) {
        return document.getElementById(id);
    }

    function zahl(wert, stellen) {
        if (wert == null || wert === '') {
            return '–';
        }
        var nummer = Number(wert);
        if (!isFinite(nummer)) {
            return '–';
        }
        try {
            return nummer.toLocaleString('de-DE', {
                minimumFractionDigits: stellen,
                maximumFractionDigits: stellen
            });
        } catch (_fehler) {
            return nummer.toFixed(stellen).replace('.', ',');
        }
    }

    function dauerText(sekunden) {
        var gesamt = Math.max(0, Math.round(Number(sekunden) || 0));
        var stunden = Math.floor(gesamt / 3600);
        var minuten = Math.floor((gesamt % 3600) / 60);
        var rest = gesamt % 60;
        if (stunden > 0) {
            return stunden + ' h ' + minuten + ' min';
        }
        if (minuten > 0) {
            return minuten + ' min ' + rest + ' s';
        }
        return rest + ' s';
    }

    function htmlSicher(wert) {
        return String(wert == null ? '' : wert)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function statusSetzen(text, fehler) {
        var status = element('v2l-action-status');
        status.textContent = text || '';
        status.classList.toggle('is-error', !!fehler);
    }

    function knoepfeSperren(gesperrt) {
        aktionLaeuft = gesperrt;
        element('v2l-start-button').disabled = gesperrt;
        element('v2l-stop-button').disabled = gesperrt;
    }

    function apiAbrufen(url, optionen) {
        optionen = optionen || {};
        optionen.credentials = 'same-origin';
        optionen.headers = optionen.headers || {};
        optionen.headers.Accept = 'application/json';
        if (optionen.method && optionen.method !== 'GET') {
            optionen.headers['Content-Type'] = 'application/json';
            if (csrfToken) {
                optionen.headers['X-CSRFToken'] = csrfToken;
            }
        }
        return fetch(url, optionen).then(function (antwort) {
            return antwort.json().catch(function () {
                return {};
            }).then(function (daten) {
                if (!antwort.ok) {
                    throw new Error(daten.error || ('HTTP ' + antwort.status));
                }
                return daten;
            });
        });
    }

    function liveZuruecksetzen() {
        element('v2l-live-duration').textContent = '–';
        element('v2l-live-soc').textContent = '–';
        element('v2l-live-energy').textContent = '–';
        element('v2l-live-power').textContent = '–';
        element('v2l-live-average').textContent = '–';
        element('v2l-live-coverage').textContent = '–';
        element('v2l-measurement-method').textContent = 'SOC';
    }

    function liveRendern(aktiv) {
        var marke = element('v2l-status-mark');
        var start = element('v2l-start-button');
        var stopp = element('v2l-stop-button');
        var titel = element('v2l-title-input');
        var kapazitaet = element('v2l-capacity-input');
        var laeuft = !!aktiv;

        marke.classList.toggle('is-active', laeuft);
        start.hidden = laeuft;
        stopp.hidden = !laeuft;
        titel.disabled = laeuft;
        kapazitaet.disabled = laeuft;
        element('v2l-status-heading').textContent = laeuft ? 'Aufzeichnung aktiv' : 'Bereit';
        element('v2l-status-text').textContent = laeuft
            ? ((aktiv.titel || 'V2L') + ' · ' + aktiv.zeitraum)
            : 'Keine Aufzeichnung aktiv';

        if (!laeuft) {
            liveZuruecksetzen();
            return;
        }
        var socText = zahl(aktiv.start_soc, 2) + ' → ' + zahl(aktiv.ende_soc, 2) + ' %';
        element('v2l-live-duration').textContent = dauerText(aktiv.dauer_s);
        element('v2l-live-soc').textContent = socText;
        element('v2l-live-energy').textContent = zahl(aktiv.verbrauch_kwh, 3) + ' kWh';
        element('v2l-live-power').textContent = aktiv.aktuelle_leistung_kw == null
            ? '–'
            : zahl(aktiv.aktuelle_leistung_kw, 2) + ' kW';
        element('v2l-live-average').textContent = zahl(aktiv.durchschnitt_kw, 2) + ' kW';
        element('v2l-live-coverage').textContent = zahl(aktiv.messabdeckung_prozent, 1) + ' %';
        element('v2l-measurement-method').textContent = aktiv.methode;
    }

    function zusammenfassungRendern(zusammenfassung) {
        zusammenfassung = zusammenfassung || {};
        element('v2l-total-sessions').textContent = String(zusammenfassung.anzahl || 0);
        element('v2l-total-energy').textContent = zahl(zusammenfassung.verbrauch_kwh || 0, 2) + ' kWh';
        element('v2l-total-duration').textContent = dauerText(zusammenfassung.dauer_s || 0);
        element('v2l-total-average').textContent = zahl(zusammenfassung.durchschnitt_kw || 0, 2) + ' kW';
    }

    function sitzungenRendern(sitzungen) {
        var tbody = element('v2l-history-rows');
        if (!Array.isArray(sitzungen) || sitzungen.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="v2l-empty">Keine Sitzungen vorhanden</td></tr>';
            return;
        }
        tbody.innerHTML = sitzungen.map(function (sitzung) {
            var klasse = sitzung.status === 'active' ? ' class="is-active"' : '';
            var soc = zahl(sitzung.start_soc, 2) + ' → ' + zahl(sitzung.ende_soc, 2) + ' %';
            var quellen = {
                automatic: 'Automatisch',
                manual: 'Manuell',
                reconstructed: 'Rekonstruiert'
            };
            var quelle = quellen[sitzung.quelle] || htmlSicher(sitzung.quelle);
            var verbrauch = zahl(sitzung.verbrauch_kwh, 3) + ' kWh';
            var prozent = sitzung.soc_verlust == null
                ? ''
                : '<small>' + zahl(sitzung.soc_verlust, 2) + ' Prozentpunkte</small>';
            var methode = htmlSicher(sitzung.methode) + '<small>' + quelle + '</small>';
            var ort = sitzung.adresse ? htmlSicher(sitzung.adresse) : '–';
            return '<tr' + klasse + '>' +
                '<td>' + htmlSicher(sitzung.datum) + '<small>' + htmlSicher(sitzung.titel) + '</small></td>' +
                '<td>' + htmlSicher(sitzung.zeitraum) + '</td>' +
                '<td>' + dauerText(sitzung.dauer_s) + '</td>' +
                '<td>' + soc + '</td>' +
                '<td>' + verbrauch + prozent + '</td>' +
                '<td>' + zahl(sitzung.durchschnitt_kw, 2) + ' / ' + zahl(sitzung.spitze_kw, 2) + ' kW</td>' +
                '<td>' + zahl(sitzung.messabdeckung_prozent, 1) + ' %<small>' + sitzung.messpunkte + ' Messpunkte</small></td>' +
                '<td>' + methode + '</td>' +
                '<td>' + ort + '</td>' +
                '</tr>';
        }).join('');
    }

    function linieZeichnen(ctx, punkte, xWert, yWert, farbe) {
        var begonnen = false;
        ctx.beginPath();
        ctx.strokeStyle = farbe;
        ctx.lineWidth = 2;
        punkte.forEach(function (punkt) {
            var x = xWert(punkt);
            var y = yWert(punkt);
            if (x == null || y == null || !isFinite(x) || !isFinite(y)) {
                begonnen = false;
                return;
            }
            if (!begonnen) {
                ctx.moveTo(x, y);
                begonnen = true;
            } else {
                ctx.lineTo(x, y);
            }
        });
        ctx.stroke();
    }

    function chartZeichnen(messpunkte) {
        var canvas = element('v2l-chart');
        var box = canvas.getBoundingClientRect();
        var faktor = Math.max(1, window.devicePixelRatio || 1);
        var breite = Math.max(320, Math.round(box.width));
        var hoehe = Math.max(180, Math.round(box.height));
        canvas.width = Math.round(breite * faktor);
        canvas.height = Math.round(hoehe * faktor);
        var ctx = canvas.getContext('2d');
        ctx.scale(faktor, faktor);
        ctx.clearRect(0, 0, breite, hoehe);
        ctx.font = '12px Roboto, Arial, sans-serif';
        ctx.fillStyle = '#8f8f8f';

        if (!Array.isArray(messpunkte) || messpunkte.length < 2) {
            ctx.textAlign = 'center';
            ctx.fillText('Keine Live-Messpunkte', breite / 2, hoehe / 2);
            return;
        }

        var rand = {links: 48, rechts: 48, oben: 30, unten: 28};
        var innenBreite = breite - rand.links - rand.rechts;
        var innenHoehe = hoehe - rand.oben - rand.unten;
        var start = messpunkte[0].zeit_ms;
        var ende = messpunkte[messpunkte.length - 1].zeit_ms;
        if (ende <= start) {
            ende = start + 1;
        }
        var socWerte = messpunkte.map(function (punkt) {
            return punkt.soc == null ? NaN : Number(punkt.soc);
        })
            .filter(function (wert) { return isFinite(wert); });
        var leistungsWerte = messpunkte.map(function (punkt) {
            return punkt.leistung_kw == null ? NaN : Number(punkt.leistung_kw);
        })
            .filter(function (wert) { return isFinite(wert); });
        var socMin = socWerte.length ? Math.min.apply(null, socWerte) : 0;
        var socMax = socWerte.length ? Math.max.apply(null, socWerte) : 100;
        var socRand = Math.max(0.5, (socMax - socMin) * 0.15);
        socMin = Math.max(0, socMin - socRand);
        socMax = Math.min(100, socMax + socRand);
        if (socMax <= socMin) {
            socMax = socMin + 1;
        }
        var leistungMax = leistungsWerte.length
            ? Math.max(1, Math.max.apply(null, leistungsWerte) * 1.15)
            : 1;

        ctx.strokeStyle = '#2e2e2e';
        ctx.lineWidth = 1;
        ctx.textAlign = 'right';
        for (var i = 0; i <= 4; i += 1) {
            var y = rand.oben + innenHoehe * i / 4;
            ctx.beginPath();
            ctx.moveTo(rand.links, y);
            ctx.lineTo(rand.links + innenBreite, y);
            ctx.stroke();
            var socLabel = socMax - (socMax - socMin) * i / 4;
            ctx.fillStyle = '#51c878';
            ctx.fillText(zahl(socLabel, 1), rand.links - 7, y + 4);
            ctx.textAlign = 'left';
            ctx.fillStyle = '#f0a34a';
            ctx.fillText(zahl(leistungMax * (1 - i / 4), 1), rand.links + innenBreite + 7, y + 4);
            ctx.textAlign = 'right';
        }

        function xPosition(punkt) {
            return rand.links + (punkt.zeit_ms - start) / (ende - start) * innenBreite;
        }
        function socPosition(punkt) {
            if (punkt.soc == null) {
                return null;
            }
            var wert = Number(punkt.soc);
            if (!isFinite(wert)) {
                return null;
            }
            return rand.oben + (socMax - wert) / (socMax - socMin) * innenHoehe;
        }
        function leistungsPosition(punkt) {
            if (punkt.leistung_kw == null) {
                return null;
            }
            var wert = Number(punkt.leistung_kw);
            if (!isFinite(wert)) {
                return null;
            }
            return rand.oben + (leistungMax - wert) / leistungMax * innenHoehe;
        }

        linieZeichnen(ctx, messpunkte, xPosition, socPosition, '#51c878');
        linieZeichnen(ctx, messpunkte, xPosition, leistungsPosition, '#f0a34a');
        ctx.fillStyle = '#8f8f8f';
        ctx.textAlign = 'left';
        ctx.fillText(new Date(start).toLocaleTimeString('de-DE'), rand.links, hoehe - 8);
        ctx.textAlign = 'right';
        ctx.fillText(new Date(ende).toLocaleTimeString('de-DE'), breite - rand.rechts, hoehe - 8);
    }

    function payloadRendern(payload) {
        aktuellerPayload = payload;
        liveRendern(payload.aktiv);
        zusammenfassungRendern(payload.zusammenfassung);
        sitzungenRendern(payload.sitzungen);
        chartZeichnen(payload.messpunkte);
        var kapazitaet = element('v2l-capacity-input');
        if (document.activeElement !== kapazitaet && !payload.aktiv) {
            var kapazitaetswert = payload.kapazität_kwh == null
                ? NaN
                : Number(payload.kapazität_kwh);
            if (isFinite(kapazitaetswert)) {
                kapazitaet.value = kapazitaetswert.toFixed(1);
            }
        }
    }

    function datenAktualisieren() {
        window.clearTimeout(abfrageTimer);
        return apiAbrufen('/api/v2l?vehicle_id=' + encodeURIComponent(vehicleId))
            .then(function (payload) {
                payloadRendern(payload);
                if (!aktionLaeuft) {
                    statusSetzen('', false);
                }
            })
            .catch(function (fehler) {
                statusSetzen(fehler.message, true);
            })
            .then(function () {
                abfrageTimer = window.setTimeout(datenAktualisieren, 2000);
            });
    }

    element('v2l-control-form').addEventListener('submit', function (ereignis) {
        ereignis.preventDefault();
        knoepfeSperren(true);
        statusSetzen('Aufzeichnung wird gestartet …', false);
        var kapazitaet = parseFloat(element('v2l-capacity-input').value.replace(',', '.'));
        apiAbrufen('/api/v2l/start', {
            method: 'POST',
            body: JSON.stringify({
                vehicle_id: vehicleId,
                titel: element('v2l-title-input').value,
                kapazitaet_kwh: kapazitaet
            })
        }).then(function () {
            statusSetzen('Aufzeichnung gestartet', false);
            return datenAktualisieren();
        }).catch(function (fehler) {
            statusSetzen(fehler.message, true);
        }).then(function () {
            knoepfeSperren(false);
        });
    });

    element('v2l-stop-button').addEventListener('click', function () {
        knoepfeSperren(true);
        statusSetzen('Aufzeichnung wird beendet …', false);
        apiAbrufen('/api/v2l/stop', {
            method: 'POST',
            body: JSON.stringify({vehicle_id: vehicleId})
        }).then(function () {
            statusSetzen('Aufzeichnung beendet', false);
            return datenAktualisieren();
        }).catch(function (fehler) {
            statusSetzen(fehler.message, true);
        }).then(function () {
            knoepfeSperren(false);
        });
    });

    window.addEventListener('resize', function () {
        if (aktuellerPayload) {
            chartZeichnen(aktuellerPayload.messpunkte);
        }
    });

    datenAktualisieren();
}());
