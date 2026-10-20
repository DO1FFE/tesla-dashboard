import shutil
import subprocess

import pytest


def test_manuelle_kartenbedienung_hat_volle_15_sekunden_vorrang():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js für den Kartenzoom-Test erforderlich")
    ergebnis = subprocess.run([node, "-e", r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const quelle = fs.readFileSync('static/js/main.js', 'utf8');
const ereignisse = {}, eingaben = {};
let jetzt = 100000, zoom = 18, aufrufe = 0, fehler = false;
const kontext = {
 Date: {now: () => jetzt},
 $: () => ({length: 0}),
 mapEl: {addEventListener: (name, funktion) => {eingaben[name] = funktion;}},
 map: {
  on: (name, funktion) => {ereignisse[name] = funktion;},
  getZoom: () => zoom,
  setView: (position, neu, optionen) => {
   aufrufe++;
   assert.equal(optionen.animate, false);
   if (fehler) throw new Error('Testfehler');
   const zoomNeu = zoom !== neu;
   if (zoomNeu) {
    ereignisse.zoomstart();
   }
   ereignisse.movestart();
   zoom = neu;
   if (zoomNeu) {
    ereignisse.zoomend();
   }
   ereignisse.moveend();
  }
 }
};
vm.createContext(kontext);
vm.runInContext(quelle.slice(quelle.indexOf('var lastUserZoom ='), quelle.indexOf('function formatierePrivatsphaereRadius')), kontext);
vm.runInContext(quelle.slice(quelle.indexOf("map.on('zoomend'"), quelle.indexOf('var polyline =')), kontext);
const automatisch = neu => kontext.setzeAutomatischeKartenansicht([51, 7], neu);
assert.equal(kontext.USER_ZOOM_PRIORITY_MS, 15000);

// Viele Positions- und Größenupdates ohne Zoomänderung dürfen keinen Restzustand hinterlassen.
for (let i = 0; i < 1000; i++) {
 assert.equal(automatisch(18), true);
 assert.equal(kontext.zoomSetByApp, false);
}
assert.equal(kontext.lastUserZoom, 0);
assert.equal(automatisch(17), true);
assert.equal(kontext.lastUserZoom, 0);

// Während der Geste und bis 15 Sekunden nach ihrem Ende keine Nachführung.
ereignisse.zoomstart();
jetzt += 20000;
const vorher = aufrufe;
assert.equal(automatisch(18), false);
assert.equal(aufrufe, vorher);
zoom = 15;
ereignisse.zoomend();
assert.equal(kontext.lastUserZoom, jetzt);
jetzt += 14999;
assert.equal(automatisch(18), false);
assert.equal(zoom, 15);
jetzt++;
assert.equal(automatisch(18), true);
assert.equal(kontext.kartenNachfuehrungAusstehend, false);

// Schon vor Leaflets verzögertem zoomstart muss die Eingabe geschützt sein.
for (const name of ['wheel', 'pointerdown', 'touchstart', 'dblclick']) {
 jetzt += 20000;
 eingaben[name]();
 assert.equal(automatisch(18), false);
 assert.equal(kontext.kartenNachfuehrungAusstehend, true);
 jetzt += 14999;
 assert.equal(automatisch(18), false);
}
jetzt += 20000;
eingaben.keydown({key: '-'});
assert.equal(automatisch(18), false);
jetzt += 10000;
eingaben.wheel();
jetzt += 14999;
assert.equal(automatisch(18), false);
jetzt++;
assert.equal(automatisch(18), true);

// Langes Ziehen bleibt auch bei zwischenzeitlichem Zoom- oder Resize-Ende geschützt.
ereignisse.movestart();
ereignisse.dragstart();
jetzt += 20000;
assert.equal(automatisch(18), false);
ereignisse.zoomstart();
ereignisse.zoomend();
ereignisse.moveend();
jetzt += 20000;
assert.equal(automatisch(18), false);
ereignisse.dragend();
jetzt += 20000;
assert.equal(automatisch(18), false, 'Nachgleiten muss vollständig abgeschlossen sein');
ereignisse.moveend();
const bewegungsende = jetzt;
jetzt += 14999;
assert.equal(automatisch(18), false);
assert.equal(kontext.lastUserZoom, bewegungsende);
jetzt++;
assert.equal(automatisch(18), true);
assert.equal(kontext.lastUserZoom, bewegungsende, 'Automatische Bewegungen verlängern die Pause nicht');

// Auch Pfeiltasten beginnen eine neue Pause, die erst nach der Bewegung abläuft.
for (const key of ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown']) {
 jetzt += 20000;
 eingaben.keydown({key});
 assert.equal(automatisch(18), false);
 ereignisse.movestart();
 jetzt += 500;
 ereignisse.moveend();
 jetzt += 14999;
 assert.equal(automatisch(18), false);
 jetzt++;
 assert.equal(automatisch(18), true);
}

fehler = true;
assert.throws(() => automatisch(17), /Testfehler/);
assert.equal(kontext.zoomSetByApp, false);
"""], capture_output=True, text=True, timeout=10)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr


# © 2026 Erik Schauer, do1ffe@darc.de
