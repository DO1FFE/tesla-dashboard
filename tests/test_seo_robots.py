import pathlib
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


def test_unterseiten_bekommen_noindex_header():
    assert _robots_header_fuer_pfad("/statistik") == "noindex, nofollow"
    assert _robots_header_fuer_pfad("/history") == "noindex, nofollow"
    assert _robots_header_fuer_pfad("/api/data") == "noindex, nofollow"


def test_robots_txt_erlaubt_keine_unterseiten():
    robots_txt = pathlib.Path("static/robots.txt").read_text(encoding="utf-8")

    assert "Disallow: /" in robots_txt
    assert "Allow: /$" in robots_txt
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
    assert '<link rel="canonical" href="https://tesla.example/">' in html
    assert '<meta property="og:title" content="Tesla-Dashboard - Live-Fahrzeugdaten">' in html
    assert "<title>Tesla-Dashboard - Live-Fahrzeugdaten</title>" in html


def test_unterseite_hat_noindex_und_hauptseiten_canonical():
    with app.app.test_request_context("/statistik", base_url="https://tesla.example"):
        html = render_template("seo.html")

    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert '<link rel="canonical" href="https://tesla.example/">' in html
    assert "og:title" not in html


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
