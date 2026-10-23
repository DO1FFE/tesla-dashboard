#!/usr/bin/env python3
"""Installiere den geschützten Transport vor dem Laden des Dashboard-Codes."""

import asyncio
import json
import os
from pathlib import Path
import runpy
import sys

import eventlet
import eventlet.hubs

if not eventlet.patcher.is_monkey_patched("socket"):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        eventlet.hubs.use_hub("eventlet.hubs.asyncio")
    eventlet.monkey_patch()

# Bei Installation liegen Starter und Schutzmodul schreibgeschützt nebeneinander.
import fahrzeugzugriffsschutz


def main(projekt=Path("/home/do1ffe/tesla-dashboard")):
    if not os.environ.get("TESLA_DASHBOARD_ABFRAGESPERRE_BIS"):
        raise RuntimeError("Neustart ohne konfigurierte Abfragesperre verweigert")
    from dotenv import load_dotenv
    load_dotenv(projekt / ".env")
    fahrzeugzugriffsschutz.aus_umgebung_starten()
    status = projekt / "data/neustartschutz.json"
    zwischen = status.with_suffix(".tmp")
    zwischen.write_text(json.dumps({
        "pid": os.getpid(), "transport_geschützt": True,
        "ende": os.environ["TESLA_DASHBOARD_ABFRAGESPERRE_BIS"],
    }), encoding="utf-8")
    zwischen.replace(status)
    sys.path.insert(1, str(projekt))
    os.chdir(projekt)
    runpy.run_path(str(projekt / "app.py"), run_name="__main__")


if __name__ == "__main__":
    main()

# © 2026 Erik Schauer, do1ffe@darc.de
