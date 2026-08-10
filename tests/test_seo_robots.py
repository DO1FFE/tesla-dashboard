import json
import pathlib
import re
import sys

from flask import Response, render_template

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app


def _robots_header_fuer_pfad(pfad):
    with app.app.test_request_context(pfad):
        antwort = Response()
        app._set_robots_header(antwort)
        return antwort.headers.get("X-Robots-Tag")


def test_nur_hauptseite_bleibt_indexierbar():
    assert _robots_header_fuer_pfad("/") is None
    assert _robots_header_fuer_pfad("/robots.txt") is None
    assert _robots_header_fuer_pfad("/sitemap.xml") is None


def test_unterseiten_bekommen_noindex_header():
    assert _robots_header_fuer_pfad("/statistik") == "noindex, follow"
    assert _robots_header_fuer_pfad("/history") == "noindex, follow"
    assert _robots_header_fuer_pfad("/api/data") == "noindex, follow"


def test_robots_txt_erlaubt_keine_unterseiten():
    robots_txt = pathlib.Path("static/robots.txt").read_text(encoding="utf-8")

    assert "Disallow: /" in robots_txt
    assert "Allow: /$" in robots_txt
    assert "Allow: /static/css/" in robots_txt
    assert "Allow: /static/js/" in robots_txt
    assert "Allow: /static/images/tesla-dashboard-logo.webp" in robots_txt
    assert "Allow: /static/\n" not in robots_txt
    assert "Allow: /sitemap.xml" in robots_txt
    assert "Sitemap: https://tesla.do1ffe.de/sitemap.xml" in robots_txt
    assert "Allow: /statistik" not in robots_txt


def test_hauptseite_hat_indexierbare_seo_angaben(monkeypatch):
    monkeypatch.setattr(app, "socketio_client_script", lambda: "/static/js/socket.io-test.js")

    with app.app.test_request_context("/", base_url="https://tesla.example"):
        html = render_template(
            "index.html",
            version="1.0.0",
            config={},
            splashscreen_anzeigen=False,
        )

    assert '<meta name="robots" content="index, follow">' in html
    assert '<link rel="canonical" href="https://tesla.do1ffe.de/">' in html
    assert (
        '<meta property="og:title" content="Tesla-Dashboard: Live-Fahrzeugdaten, '
        'Karte &amp; Ladezustand">'
    ) in html
    assert (
        "<title>Tesla-Dashboard: Live-Fahrzeugdaten, Karte &amp; "
        "Ladezustand</title>"
    ) in html
    assert '<h1 class="dashboard-heading">' in html
    assert "dashboard-intro" not in html
    assert 'href="https://do1ffe.de/tesla-dashboard">Projektseite</a>' in html
    assert 'href="https://do1ffe.de/">DO1FFE</a>' in html
    assert 'href="https://github.com/DO1FFE/tesla-dashboard">GitHub</a>' in html
    assert (
        '<meta property="og:image" '
        'content="https://tesla.do1ffe.de/static/images/tesla-dashboard-logo.webp">'
    ) in html
    treffer = re.search(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        html,
        re.DOTALL,
    )
    assert treffer is not None
    schema = json.loads(treffer.group(1))
    assert schema["@type"] == "WebApplication"
    assert schema["url"] == "https://tesla.do1ffe.de/"
    assert schema["sameAs"] == "https://github.com/DO1FFE/tesla-dashboard"
    assert "geo" not in schema
    assert "location" not in schema


def test_unterseite_hat_noindex_ohne_widerspruechliches_canonical():
    with app.app.test_request_context("/statistik", base_url="https://tesla.example"):
        html = render_template("seo.html")

    assert '<meta name="robots" content="noindex, follow">' in html
    assert '<link rel="canonical"' not in html
    assert "og:title" not in html


def test_sitemap_enthaelt_nur_die_oeffentliche_startseite():
    with app.app.test_request_context("/sitemap.xml"):
        antwort = app.sitemap_xml()

    xml = antwort.get_data(as_text=True)
    assert antwort.mimetype == "application/xml"
    assert xml.count("<url>") == 1
    assert "<loc>https://tesla.do1ffe.de/</loc>" in xml
    assert "/statistik" not in xml
    assert "/api/" not in xml


def test_404_seite_hat_status_h1_noindex_und_keinen_canonical():
    antwort = app.app.test_client().get("/nicht-vorhandene-seite")
    html = antwort.get_data(as_text=True)

    assert antwort.status_code == 404
    assert antwort.headers["X-Robots-Tag"] == "noindex, follow"
    assert '<meta name="robots" content="noindex, follow">' in html
    assert '<link rel="canonical"' not in html
    assert html.count("<h1>") == 1
    assert "Seite nicht gefunden" in html
    assert "pagead2.googlesyndication.com" not in html
    assert "© 2025-2026 Erik Schauer, do1ffe@darc.de" in html


def test_alle_templates_mit_keywords_nutzen_seo_include():
    template_ordner = pathlib.Path("templates")
    ausnahmen = {"analytics.html", "seo.html"}

    for template in template_ordner.glob("*.html"):
        if template.name in ausnahmen:
            continue
        inhalt = template.read_text(encoding="utf-8")
        if '<meta name="keywords"' in inhalt:
            assert "{% include 'seo.html' %}" in inhalt, template.name
        assert '<meta name="robots"' not in inhalt, template.name
