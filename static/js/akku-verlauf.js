(function() {
    'use strict';
    var punkte = [];
    var canvas = document.getElementById('akku-diagramm');
    var status = document.getElementById('akku-status');
    var tabelle = document.getElementById('akku-tabelle');

    function zahlText(wert) {
        return wert.toLocaleString('de-DE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }

    function zeichnen() {
        if (!punkte.length) return;
        var breite = canvas.getBoundingClientRect().width;
        var höhe = 240;
        var faktor = window.devicePixelRatio || 1;
        canvas.width = Math.round(breite * faktor);
        canvas.height = Math.round(höhe * faktor);
        var ctx = canvas.getContext('2d');
        ctx.scale(faktor, faktor);
        var maximum = Math.ceil(Math.max.apply(null, punkte.map(function(p) { return p.value; })) / 10) * 10;
        maximum = Math.max(10, maximum);
        var start = punkte[0].received_at;
        var ende = punkte[punkte.length - 1].received_at;
        var links = 48, rechts = breite - 16, oben = 16, unten = höhe - 35;
        ctx.font = '12px sans-serif';
        for (var i = 0; i <= 4; i++) {
            var y = unten - (unten - oben) * i / 4;
            ctx.strokeStyle = '#454545';
            ctx.beginPath(); ctx.moveTo(links, y); ctx.lineTo(rechts, y); ctx.stroke();
            ctx.fillStyle = '#dddddd';
            ctx.fillText((maximum * i / 4).toFixed(0), 4, y + 4);
        }
        ctx.fillText('kWh', 4, 12);
        var vorher = null;
        punkte.forEach(function(punkt) {
            var x = ende === start ? (links + rechts) / 2 : links + (rechts - links) * (punkt.received_at - start) / (ende - start);
            var y = unten - (unten - oben) * punkt.value / maximum;
            ctx.strokeStyle = '#4dc7a2'; ctx.lineWidth = 2;
            // Fehlende Tage nicht durch eine scheinbar gemessene Linie überbrücken.
            if (vorher && Math.floor(punkt.received_at / 86400000) -
                    Math.floor(vorher.zeit / 86400000) === 1) {
                ctx.beginPath(); ctx.moveTo(vorher.x, vorher.y); ctx.lineTo(x, y); ctx.stroke();
            }
            ctx.fillStyle = '#f2f2f2'; ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill();
            vorher = {x: x, y: y, zeit: punkt.received_at};
        });
        ctx.fillStyle = '#dddddd';
        ctx.fillText(new Date(start).toLocaleDateString('de-DE'), links, höhe - 8);
        if (ende !== start) {
            ctx.textAlign = 'right';
            ctx.fillText(new Date(ende).toLocaleDateString('de-DE'), rechts, höhe - 8);
        }
    }

    async function laden() {
        try {
            var parameter = new URLSearchParams(window.location.search);
            var fahrzeug = parameter.get('vehicle_id');
            var antwort = await fetch('/api/akku-verlauf' + (fahrzeug ? '?vehicle_id=' + encodeURIComponent(fahrzeug) : ''));
            if (!antwort.ok) throw new Error('HTTP ' + antwort.status);
            var daten = await antwort.json();
            if (!Array.isArray(daten.points)) throw new Error('Ungültige Messdaten');
            punkte = daten.points.filter(function(p) {
                return Number.isFinite(p.received_at) && p.received_at > 0 && Number.isFinite(p.value) && p.value > 0;
            });
            punkte.sort(function(a, b) { return a.received_at - b.received_at; });
            canvas.hidden = !punkte.length;
            tabelle.hidden = !punkte.length;
            var tbody = document.getElementById('akku-messwerte');
            tbody.textContent = '';
            if (!punkte.length) {
                status.textContent = 'Noch keine gültige Vollenergie-Messung empfangen.';
                return;
            }
            var letzter = punkte[punkte.length - 1];
            status.textContent = 'Zuletzt gemeldet: ' + zahlText(letzter.value) + ' kWh · ' +
                new Date(letzter.received_at).toLocaleString('de-DE', {timeZone: 'Europe/Berlin'});
            punkte.slice().reverse().forEach(function(punkt) {
                var zeile = document.createElement('tr');
                [new Date(punkt.received_at).toLocaleString('de-DE', {timeZone: 'Europe/Berlin'}), zahlText(punkt.value) + ' kWh'].forEach(function(text) {
                    var zelle = document.createElement('td');
                    zelle.textContent = text;
                    zeile.appendChild(zelle);
                });
                tbody.appendChild(zeile);
            });
            zeichnen();
        } catch (fehler) {
            status.textContent = 'Akku-Verlauf derzeit nicht abrufbar. Vorhandene Messwerte bleiben unverändert.';
        }
    }

    window.addEventListener('resize', zeichnen);
    setInterval(laden, 60000);
    laden();
}());
// © 2026 Erik Schauer, do1ffe@darc.de
