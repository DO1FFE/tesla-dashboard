# Tessie API Endpoints

Diese Übersicht basiert auf der offiziellen Tessie-OpenAPI-Spezifikation und listet alle bekannten Endpoints mit Beschreibung und Beispieldaten.

## Basis-URL
- `https://api.tessie.com`

## Authentifizierung
- **bearerAuth**: http (Schema: bearer)

## Endpoints
### Driver Management

#### `POST /{vin}/command/disable_guest`

**Beschreibung**

- Deaktivieren Sie den Gastmodus
- Deaktiviert den Gastmodus.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/enable_guest`

**Beschreibung**

- Aktivieren Sie den Gastmodus
- Aktiviert den Gastmodus.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `GET /{vin}/drivers`

**Beschreibung**

- Holen Sie sich Treiber
- Gibt eine Liste zusätzlicher Treiber zurück.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "results": [
    {
      "my_tesla_unique_id": 88888888,
      "user_id": 1234567,
      "user_id_s": "1234567",
      "driver_first_name": "Jane",
      "driver_last_name": "Doe",
      "granular_access": {
        "hide_private": false
      },
      "active_pubkeys": [
        "043da2708632f7d7c01f6casdf824007465408d475c37a6adfaa19aed565f3e254790c1baaac94ee2c68349642d21e16bf89c70a13019516ed475104c945cb3d53"
      ],
      "public_key": ""
    },
    {
      "my_tesla_unique_id": 99999999,
      "user_id": 123456,
      "user_id_s": "123456",
      "driver_first_name": "John",
      "driver_last_name": "Doe",
      "granular_access": {
        "hide_private": false
      },
      "active_pubkeys": [
        "04b7f61ba31002e4646f64795asdf2813e72e73159947e2bfa0badad9d42c0e3762e581c5ae58010146ccd9288333ceff26b84e57ae624fc4f7428ee20e719f00d"
      ],
      "public_key": "04b7f61ba31002e4646f64795asdf2813e72e73159947e2bfa0badad9d42c0e3762e581c5ae58010146ccd9288333ceff26b84e57ae624fc4f7428ee20e719f00d"
    }
  ]
}
```

_Antwortbeschreibung: Okay_

#### `POST /{vin}/drivers/{id}/delete`

**Beschreibung**

- Treiber löschen
- Löscht einen Fahrer aus dem Fahrzeug.

**Parameter**

- `id` (in: path, erforderlich: ja): Fahrer-ID.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "result": true
}
```

_Antwortbeschreibung: Okay_

#### `GET /{vin}/invitations`

**Beschreibung**

- Holen Sie sich Einladungen
- Gibt eine Liste von Fahrereinladungen zurück.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "results": [
    {
      "id": 2252266471835261,
      "owner_id": 1311857,
      "share_user_id": null,
      "product_id": "7SAXCBE6XPF123456",
      "state": "pending",
      "code": "d9SZ0FG_CuVqQ7OoVx1_e5-UOGLt83MqxT7BY8DsaeCs",
      "expires_at": "2023-11-29T00:55:31.000Z",
      "revoked_at": null,
      "borrowing_device_id": null,
      "key_id": null,
      "product_type": "vehicle",
      "share_type": "customer",
      "active_pubkeys": [
        null
      ],
      "id_s": "2252266471835261",
      "owner_id_s": "1311857",
      "share_user_id_s": "",
      "borrowing_key_hash": null,
      "vin": "7SAXCBE6XPF123456",
      "share_link": "https://www.tesla.com/_rs/1/d9SZ0FG_CuVqQ7OoVx1_e5-UOGLt83MqxT7BY8DsaeCs"
    },
    {
      "id": 2252267587512399,
      "owner_id": 1311857,
      "share_user_id": null,
      "product_id": "7SAXCBE6XPF123456",
      "state": "pending",
      "code": "deu-VGwpumXGXSLHCpWN2DVedKIs7fBpdiqO76Qv7KW4",
      "expires_at": "2023-11-29T00:59:06.000Z",
      "revoked_at": null,
      "borrowing_device_id": null,
      "key_id": null,
      "product_type": "vehicle",
      "share_type": "customer",
      "active_pubkeys": [
        null
      ],
      "id_s": "2252267587512399",
      "owner_id_s": "1311857",
      "share_user_id_s": "",
      "borrowing_key_hash": null,
      "vin": "7SAXCBE6XPF123456",
      "share_link": "https://www.tesla.com/_rs/1/deu-VGwpumXGXSLHCpWN2DVedKIs7fBpdiqO76Qv7KW4"
    },
    {
      "id": 2252270843114074,
      "owner_id": 1311857,
      "share_user_id": null,
      "product_id": "7SAXCBE6XPF123456",
      "state": "pending",
      "code": "div7Qqpxlq6-kKZ2AxkvLw3oCp_JsxdYJnQsYYB2jL3w",
      "expires_at": "2023-11-29T00:55:18.000Z",
      "revoked_at": null,
      "borrowing_device_id": null,
      "key_id": null,
      "product_type": "vehicle",
      "share_type": "customer",
      "active_pubkeys": [
        null
      ],
      "id_s": "7SAXCBE6XPF123456",
      "owner_id_s": "1311857",
      "share_user_id_s": "",
      "borrowing_key_hash": null,
      "vin": "7SAXCBE6XPF123456",
      "share_link": "https://www.tesla.com/_rs/1/div7Qqpxlq6-kKZ2AxkvLw3oCp_JsxdYJnQsYYB2jL3w"
    }
  ]
}
```

_Antwortbeschreibung: Okay_

#### `POST /{vin}/invitations`

**Beschreibung**

- Erstellen Sie eine Einladung
- Erstellt eine Fahrereinladung.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "result": {
    "id": 2252275396890299,
    "owner_id": 1311857,
    "share_user_id": null,
    "product_id": "7SAXCBE6XPF123456",
    "state": "pending",
    "code": "dgIPJtGS_CnIprYz0yy1dDvduRl0mQBYEwA-u_Fsc_5w",
    "expires_at": "2023-11-29T01:53:09.000Z",
    "revoked_at": null,
    "borrowing_device_id": null,
    "key_id": null,
    "product_type": "vehicle",
    "share_type": "customer",
    "active_pubkeys": [
      null
    ],
    "id_s": "2252275396890299",
    "owner_id_s": "1311857",
    "share_user_id_s": "",
    "borrowing_key_hash": null,
    "vin": "7SAXCBE6XPF123456",
    "share_link": "https://www.tesla.com/_rs/1/dgIPJtGS_CnIprYz0yy1dDvduRl0mQBYEwA-u_Fsc_5w"
  }
}
```

_Antwortbeschreibung: Okay_

#### `POST /{vin}/invitations/{id}/revoke`

**Beschreibung**

- Eine Einladung widerrufen
- Widerruft eine Fahrereinladung.

**Parameter**

- `id` (in: path, erforderlich: ja): Einladungs-ID.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "result": true
}
```

_Antwortbeschreibung: Okay_

### Telemetry Configuration

#### `DELETE /{vin}/fleet_telemetry_config`

**Beschreibung**

- Telemetriekonfiguration löschen
- Löschen Sie die Flottentelemetriekonfiguration des Fahrzeugs.

**Wichtig:** Durch das Löschen dieser Konfiguration wird die Funktionalität der Tessie-Plattform deaktiviert.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "updated_vehicles": 1
}
```

_Antwortbeschreibung: Okay_

#### `GET /{vin}/fleet_telemetry_config`

**Beschreibung**

- Rufen Sie die Telemetriekonfiguration ab
- Gibt die Flottentelemetriekonfiguration des Fahrzeugs zurück.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "synced": true,
  "config": {
    "hostname": "telemetry.tessie.com",
    "ca": "...",
    "exp": 1753759258,
    "port": 443,
    "fields": {
      "ACChargingPower": {
        "interval_seconds": 60
      },
      "BatteryLevel": {
        "interval_seconds": 60
      },
      "ChargeState": {
        "interval_seconds": 60
      },
      "DCChargingPower": {
        "interval_seconds": 60
      },
      "EnergyRemaining": {
        "interval_seconds": 60
      },
      "Gear": {
        "interval_seconds": 60
      },
      "IdealBatteryRange": {
        "interval_seconds": 60
      },
      "Location": {
        "interval_seconds": 60
      },
      "Odometer": {
        "interval_seconds": 60
      },
      "RatedRange": {
        "interval_seconds": 60
      }
    },
    "alert_types": [
      "service"
    ]
  },
  "update_available": false
}
```

_Antwortbeschreibung: Okay_

#### `POST /{vin}/fleet_telemetry_config`

**Beschreibung**

- Telemetriekonfiguration festlegen
- Legt die Flottentelemetriekonfiguration des Fahrzeugs fest.

Legt standardmäßig unsere empfohlene Konfiguration fest. Geben Sie eine Konfiguration an, um sie zu überschreiben. Benutzerdefinierte Konfigurationen sind auf eine maximale Rate von 1 Signal pro Sekunde beschränkt.

Die vollständige Liste der Felder finden Sie [hier](https://github.com/teslamotors/fleet-telemetry/blob/main/protos/vehicle_data.proto).

**Wichtig:** Das Ändern dieser Konfiguration kann negative Auswirkungen auf die Funktionalität der Tessie-Plattform haben.


**Beispielanfrage**

```json
{
  "fields": {
    "ACChargingPower": {
      "interval_seconds": 60
    },
    "BatteryLevel": {
      "interval_seconds": 60
    },
    "ChargeState": {
      "interval_seconds": 60
    },
    "DCChargingPower": {
      "interval_seconds": 60
    },
    "EnergyRemaining": {
      "interval_seconds": 60
    },
    "Gear": {
      "interval_seconds": 60
    },
    "IdealBatteryRange": {
      "interval_seconds": 60
    },
    "Location": {
      "interval_seconds": 60
    },
    "Odometer": {
      "interval_seconds": 60
    },
    "RatedRange": {
      "interval_seconds": 60
    }
  }
}
```

**Beispielantwort**

```json
{
  "result": true
}
```

_Antwortbeschreibung: Okay_

### Vehicle Commands

#### `POST /{vin}/command/activate_front_trunk`

**Beschreibung**

- Vorderer Kofferraum
- Öffnet den vorderen Kofferraum.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/activate_rear_trunk`

**Beschreibung**

- Hinterer Kofferraum
- Öffnet den hinteren Kofferraum oder schließt ihn, wenn der Kofferraum offen ist und das Fahrzeug über einen elektrisch betriebenen Kofferraum verfügt.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/add_charge_schedule`

**Beschreibung**

- Ladeplan hinzufügen
- Fügen Sie einen Ladeplan hinzu oder aktualisieren Sie ihn.

**Parameter**

- `vin` (in: path, erforderlich: ja): Die zugehörige VIN.
- `start_enabled` (in: query, erforderlich: ja): Ob das Fahrzeug zur angegebenen start_time mit dem Laden beginnen soll.
- `end_enabled` (in: query, erforderlich: ja): Ob das Fahrzeug nach der angegebenen end_time mit dem Laden aufhören soll.
- `start_time` (in: query, erforderlich: nein): Die Anzahl der Minuten des Tages, nach dem dieser Zeitplan beginnt. 1:05 Uhr wird als 65 dargestellt. Lassen Sie es weg, wenn start_enabled auf „false“ gesetzt ist.
- `end_time` (in: query, erforderlich: nein): Die Anzahl der Minuten des Tages, an dem dieser Zeitplan endet. 1:05 Uhr wird als 65 dargestellt. Lassen Sie es weg, wenn end_enabled auf „false“ gesetzt ist.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/add_precondition_schedule`

**Beschreibung**

- Vorbedingungszeitplan hinzufügen
- Fügen Sie einen Vorkonditionierungsplan hinzu oder aktualisieren Sie ihn.

**Parameter**

- `vin` (in: path, erforderlich: ja): Die zugehörige VIN.
- `precondition_time` (in: query, erforderlich: ja): Die Anzahl der Minuten des Tages, nach denen das Fahrzeug die Vorkonditionierung abschließen sollte. 1:05 Uhr wird als 65 dargestellt.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/cancel_software_update`

**Beschreibung**

- Software-Update abbrechen
- Bricht alle geplanten Software-Updates ab.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/clear_speed_limit_pin`

**Beschreibung**

- Geschwindigkeitsbegrenzungs-PIN löschen
- Entfernt die Geschwindigkeitsbegrenzungs-PIN.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/close_charge_port`

**Beschreibung**

- Schließen Sie den Ladeanschluss
- Schließt den Ladeanschluss.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/close_sunroof`

**Beschreibung**

- Schiebedach schließen
- Schließt das Schiebedach.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/close_tonneau`

**Beschreibung**

- Tonneau schließen
- Schließt das Tonneau.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/close_windows`

**Beschreibung**

- Schließen Sie Windows
- Schließt alle Fenster, wenn das Fahrzeug dies unterstützt.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/disable_keep_accessory_power_mode`

**Beschreibung**

- Deaktivieren Sie den Power-Modus für Zubehör beibehalten
- Deaktiviert den Keep-Accessory-Power-Modus.

**Parameter**

- `vin` (in: path, erforderlich: ja): Die zugehörige VIN.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/disable_low_power_mode`

**Beschreibung**

- Deaktivieren Sie den Energiesparmodus
- Deaktiviert den Energiesparmodus.

**Parameter**

- `vin` (in: path, erforderlich: ja): Die zugehörige VIN.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/disable_sentry`

**Beschreibung**

- Deaktivieren Sie den Sentry-Modus
- Deaktiviert den Sentry-Modus.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/disable_speed_limit`

**Beschreibung**

- Geschwindigkeitsbegrenzung deaktivieren
- Deaktiviert die Geschwindigkeitsbegrenzung.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/disable_valet`

**Beschreibung**

- Deaktivieren Sie den Valet-Modus
- Deaktiviert den Valet-Modus.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/enable_keep_accessory_power_mode`

**Beschreibung**

- Aktivieren Sie „Zubehör-Strommodus beibehalten“.
- Aktiviert den Beibehaltungsmodus für die Stromversorgung des Zubehörs.

**Parameter**

- `vin` (in: path, erforderlich: ja): Die zugehörige VIN.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/enable_low_power_mode`

**Beschreibung**

- Aktivieren Sie den Energiesparmodus
- Aktiviert den Energiesparmodus.

**Parameter**

- `vin` (in: path, erforderlich: ja): Die zugehörige VIN.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/enable_sentry`

**Beschreibung**

- Aktivieren Sie den Sentry-Modus
- Aktiviert den Sentry-Modus.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/enable_speed_limit`

**Beschreibung**

- Geschwindigkeitsbegrenzung aktivieren
- Aktiviert die Geschwindigkeitsbegrenzung.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/enable_valet`

**Beschreibung**

- Aktivieren Sie den Valet-Modus
- Aktiviert den Valet-Modus.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/flash`

**Beschreibung**

- Blitzlichter
- Die Lichter blinken.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/honk`

**Beschreibung**

- Hupe
- Hupt die Hupe.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/lock`

**Beschreibung**

- Sperren
- Verriegelt das Fahrzeug.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/open_charge_port`

**Beschreibung**

- Öffnen Sie den Ladeanschluss
- Öffnet den Ladeanschluss, wenn er geschlossen ist, oder entsperrt ihn, wenn er offen ist.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/open_tonneau`

**Beschreibung**

- Offenes Tonneau
- Öffnet das Tonneau.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/remote_boombox`

**Beschreibung**

- Boombox
- Erzeugt ein Furzgeräusch.

Erfordert 2022.40.25+.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/remote_start`

**Beschreibung**

- Aktivieren Sie schlüsselloses Fahren
- Ermöglicht schlüsselloses Fahren.

Die Fahrt muss innerhalb von 2 Minuten beginnen.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/remove_charge_schedule`

**Beschreibung**

- Ladeplan entfernen
- Entfernen Sie einen Ladeplan.

**Parameter**

- `vin` (in: path, erforderlich: ja): Die zugehörige VIN.
- `id` (in: query, erforderlich: ja): Die ID des zu löschenden Zeitplans.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/remove_precondition_schedule`

**Beschreibung**

- Vorbedingungszeitplan entfernen
- Entfernen Sie einen Vorkonditionierungsplan.

**Parameter**

- `vin` (in: path, erforderlich: ja): Die zugehörige VIN.
- `id` (in: query, erforderlich: ja): Die ID des zu löschenden Zeitplans.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/schedule_software_update`

**Beschreibung**

- Planen Sie ein Software-Update
- Plant ein Software-Update.

**Parameter**

- `in_seconds` (in: query, erforderlich: ja): Die Anzahl der Sekunden in der Zukunft, für die das Update geplant werden soll. Auf 0 setzen, um das Update sofort zu planen.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/set_bioweapon_mode`

**Beschreibung**

- Stellen Sie den Bio-Verteidigungsmodus ein
- Legt den Biowaffen-Verteidigungsmodus fest.

**Parameter**

- `on` (in: query, erforderlich: ja): Ob der Biowaffen-Verteidigungsmodus aktiviert werden soll.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/set_cabin_overheat_protection`

**Beschreibung**

- Stellen Sie den Kabinenüberhitzungsschutz ein
- Legt den Kabinenüberhitzungsschutzmodus fest.

**Parameter**

- `vin` (in: path, erforderlich: ja): Die zugehörige VIN.
- `on` (in: query, erforderlich: nein): Ob die Funktion ein- oder ausgeschaltet sein soll.
- `fan_only` (in: query, erforderlich: nein): Ob nur der Lüfter zum Kühlen verwendet werden soll.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/set_charge_limit`

**Beschreibung**

- Gebührenlimit festlegen
- Legt das Gebührenlimit fest.

**Parameter**

- `percent` (in: query, erforderlich: ja): Der Batterieprozentsatz, bis zu dem geladen werden soll.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/set_charging_amps`

**Beschreibung**

- Ladestärke einstellen
- Legt den Ladestrom fest.

**Parameter**

- `amps` (in: query, erforderlich: ja): Die Anzahl der Ampere.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/set_climate_keeper_mode`

**Beschreibung**

- Stellen Sie den Climate Keeper-Modus ein
- Legt den Climate Keeper-Modus fest.

**Parameter**

- `mode` (in: query, erforderlich: ja): Der Climate Keeper-Modus. Verwenden Sie 1 für den Keep-Modus, 2 für den Dog-Modus, 3 für den Camp-Modus und 0 zum Deaktivieren.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/set_cop_temp`

**Beschreibung**

- Stellen Sie die Kabinenüberhitzungsschutztemperatur ein
- Legt die Aktivierungstemperatur des Kabinenüberhitzungsschutzes fest.

**Parameter**

- `vin` (in: path, erforderlich: ja): Die zugehörige VIN.
- `cop_temp` (in: query, erforderlich: nein): Die Aktivierungstemperatur (1 = niedrig, 2 = mittel, 3 = hoch).

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/set_scheduled_charging`

**Beschreibung**

- Legen Sie das geplante Laden fest
- Legt die geplante Ladekonfiguration fest.

Für Fahrzeuge ab 2024.26 verwenden Sie stattdessen [add_charge_schedule](https://developer.tessie.com/reference/add-charge-schedule) und [add_precondition_schedule](https://developer.tessie.com/reference/remove-charge-schedule).

**Parameter**

- `enable` (in: query, erforderlich: ja): Ob das geplante Laden aktiviert werden soll.
- `time` (in: query, erforderlich: ja): Die Minuten nach Mitternacht Ortszeit, um mit dem Ladevorgang zu beginnen.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/set_scheduled_departure`

**Beschreibung**

- Legen Sie die geplante Abfahrt fest
- Legt die geplante Abfahrtskonfiguration fest.

Für Fahrzeuge ab 2024.26 verwenden Sie stattdessen [add_charge_schedule](https://developer.tessie.com/reference/add-charge-schedule) und [add_precondition_schedule](https://developer.tessie.com/reference/remove-charge-schedule).

**Parameter**

- `enable` (in: query, erforderlich: ja): Ob geplante Abfahrt aktiviert werden soll.
- `departure_time` (in: query, erforderlich: ja): Die Abfahrtszeit in Minuten nach Mitternacht Ortszeit.
- `preconditioning_enabled` (in: query, erforderlich: nein): Ob die Kabine vorkonditioniert werden soll.
- `preconditioning_weekdays_only` (in: query, erforderlich: nein): Ob die Kabine nur an Wochentagen vorkonditioniert werden soll.
- `off_peak_charging_enabled` (in: query, erforderlich: nein): Ob das Laden außerhalb der Spitzenzeiten durchgeführt werden soll.
- `off_peak_charging_weekdays_only` (in: query, erforderlich: nein): Legt fest, ob das Laden außerhalb der Spitzenzeiten nur an Wochentagen durchgeführt werden soll.
- `end_off_peak_time` (in: query, erforderlich: nein): Das Ende der Ladezeit außerhalb der Spitzenzeiten in Minuten nach Mitternacht Ortszeit.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/set_seat_cool`

**Beschreibung**

- Sitzkühlung einstellen
- Stellt die Sitzkühlungsstufe ein.

**Parameter**

- `level` (in: query, erforderlich: nein): Die Kühlstufe. Zum Ausschalten auf 0 einstellen.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/set_seat_heat`

**Beschreibung**

- Sitzheizung einstellen
- Stellt die Sitzheizungsstufe ein.

**Parameter**

- `level` (in: query, erforderlich: nein): Die Heizstufe. Zum Ausschalten auf 0 einstellen.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/set_speed_limit`

**Beschreibung**

- Geschwindigkeitsbegrenzung festlegen
- Legt die Geschwindigkeitsbegrenzung fest.

**Parameter**

- `mph` (in: query, erforderlich: nein): Das Tempolimit.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/set_temperatures`

**Beschreibung**

- Temperatur einstellen
- Stellt die Kabinentemperatur ein.

**Parameter**

- `temperature` (in: query, erforderlich: ja): Die Temperatur in Celsius.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/share`

**Beschreibung**

- Teilen
- Gibt eine Adresse, einen Breiten-/Längengrad oder eine Video-URL an das Fahrzeug weiter.

**Parameter**

- `value` (in: query, erforderlich: ja): Eine Straßenadresse, Breiten-/Längenkoordinaten oder eine Video-URL.
- `locale` (in: query, erforderlich: nein): Die Sprache und der Ländercode der Adresse. Nützlich für die genaue Übersetzung von Adressen in das Navigationssystem.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/start_charging`

**Beschreibung**

- Starten Sie den Ladevorgang
- Beginnt mit dem Laden.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/start_climate`

**Beschreibung**

- Klima starten
- Startet das Klimasystem und bereitet die Batterie vor.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/start_max_defrost`

**Beschreibung**

- Abtauen starten
- Beginnt mit dem Auftauen.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/start_steering_wheel_heater`

**Beschreibung**

- Starten Sie die Lenkradheizung
- Startet die Lenkradheizung.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/stop_charging`

**Beschreibung**

- Stoppen Sie den Ladevorgang
- Stoppt den Ladevorgang.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/stop_climate`

**Beschreibung**

- Stoppt das Klima
- Stoppt das Klimasystem.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/stop_max_defrost`

**Beschreibung**

- Abtauen stoppen
- Stoppt das Auftauen.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/stop_steering_wheel_heater`

**Beschreibung**

- Stoppen Sie die Lenkradheizung
- Stoppt die Lenkradheizung.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/trigger_homelink`

**Beschreibung**

- HomeLink auslösen
- Löst das primäre HomeLink-Gerät aus.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/unlock`

**Beschreibung**

- Entsperren
- Entriegelt das Fahrzeug.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/vent_sunroof`

**Beschreibung**

- Entlüftungsschiebedach
- Entlüftet das Schiebedach.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/command/vent_windows`

**Beschreibung**

- Lüftungsfenster
- Entlüftet alle Fenster.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

#### `POST /{vin}/wake`

**Beschreibung**

- Wach auf
- Weckt das Fahrzeug aus dem Ruhezustand.

Gibt „true“ zurück, nachdem das Fahrzeug wach ist, oder „false“ nach einem Timeout von 90 Sekunden.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "result": true
}
```

_Antwortbeschreibung: Erfolg_

### Vehicle Data

#### `GET /battery_health`

**Beschreibung**

- Erhalten Sie den Batteriezustand
- Gibt den Batteriezustand aller Fahrzeuge zurück.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "results": [
    {
      "vin": "5YJXCAE43LF123456",
      "plate": "VT782CE",
      "odometer": 16380.9,
      "max_range": 303.48,
      "max_ideal_range": 1196,
      "capacity": 96.7,
      "original_capacity": 97.15,
      "degradation_percent": 0.5,
      "health_percent": 99.5
    }
  ]
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /charging_invoices`

**Beschreibung**

- Erhalten Sie alle Abrechnungsrechnungen
- Sendet Laderechnungen für alle Fahrzeuge zurück.

Nur für Flottenkonten.

**Parameter**

- `vin` (in: query, erforderlich: nein): Die zugehörige VIN.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "results": [
    {
      "id": 242345313,
      "started_at": 1699829921,
      "ended_at": 1699833374,
      "invoice_number": "3000P0085545388",
      "vin": "7SA3CBE6XPF123456",
      "location": "Yuma, AZ - South Fortuna Road",
      "energy_used": 70,
      "idle_minutes": 0,
      "charging_fees": 24.5,
      "idle_fees": 0,
      "total_cost": 24.5,
      "cost_per_kwh": 0.35,
      "currency": "USD",
      "invoice_url": "https://tesla.com/teslaaccount/charging/invoice/f4d990ab-f32f-4965-8f61-6e7603714a41"
    },
    {
      "id": 242281757,
      "started_at": 1699818910,
      "ended_at": 1699821672,
      "invoice_number": "3000P0085503265",
      "vin": "7SA3CBE6XPF123456",
      "location": "Tempe, AZ",
      "energy_used": 72,
      "idle_minutes": 0,
      "charging_fees": 18.72,
      "idle_fees": 0,
      "total_cost": 18.72,
      "cost_per_kwh": 0.26,
      "currency": "USD",
      "invoice_url": "https://tesla.com/teslaaccount/charging/invoice/ae422c93-7e86-43d3-a24f-58f0604a1b06"
    }
  ]
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /vehicles`

**Beschreibung**

- Holen Sie sich Fahrzeuge
- Gibt den aktuellen Zustand aller Fahrzeuge zurück.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "results": [
    {
      "vin": "5YJXCAE43LF123456",
      "is_active": true,
      "last_state": {
        "id": 1492931520123456,
        "vin": "5YJXCAE43LF123456",
        "id_s": "1492931520123456",
        "color": "string",
        "state": "online",
        "user_id": 1311857,
        "in_service": true,
        "vehicle_id": 1349238573,
        "access_type": "OWNER",
        "api_version": 34,
        "drive_state": {
          "power": 0,
          "speed": "string",
          "heading": 194,
          "latitude": 40.7484,
          "gps_as_of": 1643590638,
          "longitude": 73.9857,
          "timestamp": 1643590652755,
          "native_type": "wgs",
          "shift_state": "P",
          "native_latitude": 40.7484,
          "native_longitude": 73.9857,
          "native_location_supported": 1
        },
        "charge_state": {
          "timestamp": 1643590652755,
          "charge_amps": 12,
          "charge_rate": 0,
          "battery_level": 89,
          "battery_range": 269.01,
          "charger_power": 0,
          "trip_charging": true,
          "charger_phases": "string",
          "charging_state": "Complete",
          "charger_voltage": 0,
          "charge_limit_soc": 90,
          "battery_heater_on": true,
          "charge_port_color": "Off",
          "charge_port_latch": "Engaged",
          "conn_charge_cable": "SAE",
          "est_battery_range": 223.25,
          "fast_charger_type": "MCSingleWireCAN",
          "fast_charger_brand": "<invalid>",
          "charge_energy_added": 4.64,
          "charge_to_max_range": true,
          "ideal_battery_range": 999,
          "time_to_full_charge": 0,
          "charge_limit_soc_max": 100,
          "charge_limit_soc_min": 50,
          "charge_limit_soc_std": 90,
          "fast_charger_present": true,
          "usable_battery_level": 89,
          "charge_enable_request": true,
          "charge_port_door_open": true,
          "charger_pilot_current": 12,
          "preconditioning_times": "weekdays",
          "charge_current_request": 12,
          "charger_actual_current": 0,
          "minutes_to_full_charge": 0,
          "managed_charging_active": true,
          "off_peak_charging_times": "all_week",
          "off_peak_hours_end_time": 375,
          "preconditioning_enabled": true,
          "scheduled_charging_mode": "Off",
          "charge_miles_added_ideal": 4641,
          "charge_miles_added_rated": 14.5,
          "max_range_charge_counter": 0,
          "not_enough_power_to_heat": true,
          "scheduled_departure_time": 1643578200,
          "off_peak_charging_enabled": true,
          "charge_current_request_max": 12,
          "scheduled_charging_pending": true,
          "user_charge_enable_request": "string",
          "managed_charging_start_time": "string",
          "charge_port_cold_weather_mode": "string",
          "scheduled_charging_start_time": "string",
          "managed_charging_user_canceled": true,
          "scheduled_departure_time_minutes": 810,
          "scheduled_charging_start_time_app": 817,
          "supercharger_session_trip_planner": true
        },
        "display_name": "Seneca",
        "gui_settings": {
          "timestamp": 1643590652755,
          "gui_24_hour_time": true,
          "show_range_units": true,
          "gui_range_display": "Rated",
          "gui_distance_units": "mi/hr",
          "gui_charge_rate_units": "kW",
          "gui_temperature_units": "F"
        },
        "option_codes": "AD15MDL3PBSBRENABT37ID3WRF3GS3PBDRLHDV2WW39BAPF0COUSBC3BCH07PC30FC3PFG31GLFRHL31HM31IL31LTPBMR31FM3BRS3HSA3PSTCPSC04SU3CT3CATW00TM00UT3PWR00AU3PAPH3AF00ZCSTMI00CDM0",
        "climate_state": {
          "timestamp": 1643590652755,
          "fan_status": 0,
          "inside_temp": 24.3,
          "defrost_mode": 0,
          "outside_temp": 17.5,
          "is_climate_on": true,
          "battery_heater": true,
          "bioweapon_mode": true,
          "max_avail_temp": 28,
          "min_avail_temp": 15,
          "seat_heater_left": 0,
          "hvac_auto_request": "On",
          "seat_heater_right": 0,
          "is_preconditioning": true,
          "wiper_blade_heater": true,
          "climate_keeper_mode": "off",
          "driver_temp_setting": 22.8,
          "left_temp_direction": 0,
          "side_mirror_heaters": true,
          "is_rear_defroster_on": true,
          "right_temp_direction": 0,
          "is_front_defroster_on": true,
          "seat_heater_rear_left": 0,
          "steering_wheel_heater": true,
          "passenger_temp_setting": 22.8,
          "seat_heater_rear_right": 0,
          "battery_heater_no_power": true,
          "is_auto_conditioning_on": true,
          "seat_heater_rear_center": 0,
          "cabin_overheat_protection": "On",
          "seat_heater_third_row_left": 0,
          "seat_heater_third_row_right": 0,
          "remote_heater_control_enabled": true,
          "allow_cabin_overheat_protection": true,
          "supports_fan_only_cabin_overheat_protection": true
        },
        "vehicle_state": {
          "df": 0,
          "dr": 0,
          "ft": 0,
          "pf": 0,
          "pr": 0,
          "rt": 0,
          "locked": true,
          "odometer": 14096.485641,
          "fd_window": 0,
          "fp_window": 0,
          "rd_window": 0,
          "rp_window": 0,
          "timestamp": 1643590652755,
          "santa_mode": 0,
          "valet_mode": true,
          "api_version": 34,
          "car_version": "2022.4 fae2af490933",
          "media_state": {
            "remote_control_enabled": true
          },
          "sentry_mode": true,
          "remote_start": true,
          "vehicle_name": "Seneca",
          "dashcam_state": "Unavailable",
          "autopark_style": "standard",
          "homelink_nearby": true,
          "is_user_present": true,
          "software_update": {
            "status": "available",
            "version": "2022.4",
            "install_perc": 1,
            "download_perc": 0,
            "expected_duration_sec": 2700
          },
          "speed_limit_mode": {
            "active": true,
            "pin_code_set": true,
            "max_limit_mph": 90,
            "min_limit_mph": 50,
            "current_limit_mph": 84
          },
          "tpms_pressure_fl": "string",
          "tpms_pressure_fr": "string",
          "tpms_pressure_rl": "string",
          "tpms_pressure_rr": "string",
          "autopark_state_v2": "standby",
          "calendar_supported": true,
          "last_autopark_error": "no_error",
          "center_display_state": 0,
          "remote_start_enabled": true,
          "homelink_device_count": 0,
          "sentry_mode_available": true,
          "remote_start_supported": true,
          "smart_summon_available": true,
          "notifications_supported": true,
          "parsed_calendar_supported": true,
          "dashcam_clip_save_available": true,
          "summon_standby_mode_enabled": true
        },
        "backseat_token": "string",
        "vehicle_config": {
          "plg": true,
          "pws": true,
          "rhd": true,
          "car_type": "modelx",
          "seat_type": 0,
          "timestamp": 1643590652755,
          "eu_vehicle": true,
          "roof_color": "None",
          "utc_offset": -28800,
          "wheel_type": "Turbine22Dark",
          "spoiler_type": "Passive",
          "trim_badging": "p100d",
          "driver_assist": "TeslaAP3",
          "headlamp_type": "Led",
          "exterior_color": "Pearl",
          "rear_seat_type": 7,
          "rear_drive_unit": "Large",
          "third_row_seats": "FuturisFoldFlat",
          "car_special_type": "base",
          "charge_port_type": "US",
          "ece_restrictions": true,
          "front_drive_unit": "PermanentMagnet",
          "has_seat_cooling": true,
          "rear_seat_heaters": 3,
          "use_range_badging": true,
          "can_actuate_trunks": true,
          "efficiency_package": "Default",
          "has_air_suspension": true,
          "has_ludicrous_mode": true,
          "interior_trim_type": "AllBlack",
          "sun_roof_installed": 0,
          "default_charge_to_max": true,
          "motorized_charge_port": true,
          "dashcam_clip_save_supported": true,
          "can_accept_navigation_requests": true
        },
        "calendar_enabled": true,
        "backseat_token_updated_at": "string"
      }
    }
  ]
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/battery`

**Beschreibung**

- Holen Sie sich die Batterie
- Gibt den Zustand der Batterie eines Fahrzeugs zurück.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "timestamp": 1710785350,
  "battery_level": 89.828,
  "battery_range": 273.47,
  "ideal_battery_range": 273.47,
  "phantom_drain_percent": 1,
  "energy_remaining": 85.5,
  "lifetime_energy_used": 3266.888,
  "pack_current": -0.6,
  "pack_voltage": 451.61,
  "module_temp_min": 20.5,
  "module_temp_max": 21
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/battery_health`

**Beschreibung**

- Erhalten Sie Messungen zum Batteriezustand
- Gibt die Batteriezustandsmessungen für ein Fahrzeug im Zeitverlauf zurück.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "result": {
    "max_range": 303.35,
    "max_ideal_range": 255.12,
    "capacity": 96.79
  }
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/charges`

**Beschreibung**

- Gebühren erhalten
- Gibt die Gebühren für ein Fahrzeug zurück.

**Parameter**

- `superchargers_only` (in: query, erforderlich: nein): Legt fest, ob nur Gebühren von Superchargern berücksichtigt werden sollen.
- `origin_latitude` (in: query, erforderlich: nein): Der Breitengrad der Ladestation.
- `origin_longitude` (in: query, erforderlich: nein): Der Längengrad der Ladestation.
- `origin_radius` (in: query, erforderlich: nein): Der Radius von der Ladestation in Metern.
- `exclude_origin` (in: query, erforderlich: nein): Ob die Ladestation ausgeschlossen werden soll.
- `minimum_energy_added` (in: query, erforderlich: nein): Die der Batterie mindestens zugeführte Energie in kWh.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "results": [
    {
      "id": 434159,
      "started_at": 1628906796,
      "ended_at": 1628911246,
      "location": "South Las Vegas Boulevard, Las Vegas, Nevada 89119, United States",
      "latitude": 36.070656,
      "longitude": -115.172968,
      "is_supercharger": true,
      "odometer": 12345.67,
      "energy_added": 81.41,
      "energy_used": 81.5,
      "miles_added": 256,
      "miles_added_ideal": 512,
      "starting_battery": 11,
      "ending_battery": 96,
      "cost": 0
    }
  ]
}
```

_Antwortbeschreibung: Erfolg_

#### `POST /{vin}/charges/{id}/set_cost`

**Beschreibung**

- Ladekosten festlegen
- Legt die Kosten einer Gebühr fest.

**Parameter**

- `id` (in: path, erforderlich: ja): Die ID der Gebühr.
- `cost` (in: query, erforderlich: nein): Die Kosten der Gebühr. Lassen Sie das Feld leer, um die Kosten zu entfernen.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "result": true
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/consumption_since_charge`

**Beschreibung**

- Holen Sie sich Verbrauch
- Gibt Verbrauchsdaten seit dem letzten Aufladen eines Fahrzeugs zurück.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "last_charge_at": 1675940795,
  "distance_driven": 10.4,
  "battery_percent_used": 10,
  "battery_percent_used_by_driving": 4,
  "rated_range_used": 34.57,
  "rated_range_used_by_driving": 16.75,
  "ideal_range_used": 34.57,
  "ideal_range_used_by_driving": 16.75,
  "energy_used": 7.56,
  "energy_used_by_driving": 3.66
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/drives`

**Beschreibung**

- Holen Sie sich Laufwerke
- Gibt die Laufwerke für ein Fahrzeug zurück.

**Parameter**

- `origin_latitude` (in: query, erforderlich: nein): Der Breitengrad des Startpunkts.
- `origin_longitude` (in: query, erforderlich: nein): Der Längengrad des Startpunkts.
- `origin_radius` (in: query, erforderlich: nein): Der Radius vom Startpunkt in Metern.
- `exclude_origin` (in: query, erforderlich: nein): Ob der Startpunkt ausgeschlossen werden soll.
- `destination_latitude` (in: query, erforderlich: nein): Der Breitengrad des Endpunkts.
- `destination_longitude` (in: query, erforderlich: nein): Der Längengrad des Endpunkts.
- `destination_radius` (in: query, erforderlich: nein): Der eingeschlossene Radius vom Endpunkt in Metern.
- `exclude_destination` (in: query, erforderlich: nein): Ob der Endpunkt ausgeschlossen werden soll.
- `tag` (in: query, erforderlich: nein): Das mit dem Laufwerk verknüpfte Tag.
- `exclude_tag` (in: query, erforderlich: nein): Ob das Tag ausgeschlossen werden soll.
- `driver_profile` (in: query, erforderlich: nein): Das mit dem Laufwerk verknüpfte Fahrerprofil.
- `exclude_driver_profile` (in: query, erforderlich: nein): Ob das Fahrerprofil ausgeschlossen werden soll.
- `minimum_distance` (in: query, erforderlich: nein): Die gefahrene Mindeststrecke in Meilen.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "results": [
    {
      "id": 1363162,
      "started_at": 1628960959,
      "ended_at": 1628970656,
      "starting_location": "8055 Dean Martin Drive, Las Vegas, Nevada 89139, United States",
      "starting_latitude": 36.042928,
      "starting_longitude": -115.187801,
      "ending_location": "Cataba Road, Hesperia, California 92344, United States",
      "ending_latitude": 34.42468,
      "ending_longitude": -117.385746,
      "starting_battery": 97,
      "ending_battery": 21,
      "average_inside_temperature": 20.23,
      "average_outside_temperature": 34.94,
      "average_speed": 73,
      "max_speed": 90,
      "rated_range_used": 230.45,
      "odometer_distance": 185.9,
      "autopilot_distance": 174.6,
      "energy_used": 73.28,
      "tag": "Personal"
    }
  ]
}
```

_Antwortbeschreibung: Erfolg_

#### `POST /{vin}/drives/set_tag`

**Beschreibung**

- Legen Sie das Laufwerks-Tag fest
- Legt das Tag für eine Liste von Laufwerken fest.

**Beispielanfrage**

```json
{
  "drives": "10000,10001,10002",
  "tag": "Business"
}
```

**Beispielantwort**

```json
{
  "result": true
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/firmware_alerts`

**Beschreibung**

- Erhalten Sie Firmware-Benachrichtigungen
- Gibt die Liste der von einem Fahrzeug generierten Firmware-Warnungen zurück.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "results": [
    {
      "timestamp": 1726683716,
      "name": "VCFRONT_a361_washerFluidLowMomentary",
      "description": null,
      "recent_fleet_count": 123456
    }
  ]
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/idles`

**Beschreibung**

- Holen Sie sich Leerlauf
- Gibt den Leerlauf eines Fahrzeugs zurück.

Ein Fahrzeug gilt als im Leerlauf, wenn es nicht fährt oder lädt.

**Parameter**

- `origin_latitude` (in: query, erforderlich: nein): Der Breitengrad des Parkplatzes.
- `origin_longitude` (in: query, erforderlich: nein): Der Längengrad des Parkplatzes.
- `origin_radius` (in: query, erforderlich: nein): Der Radius vom Parkplatz in Metern.
- `exclude_origin` (in: query, erforderlich: nein): Ob der Parkplatz einbezogen werden soll.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "results": [
    {
      "id": 1393231,
      "started_at": 1626454383,
      "ended_at": 1626461947,
      "location": "8055 Dean Martin Drive, Las Vegas, Nevada 89139, United States",
      "latitude": 36.042928,
      "longitude": -115.187801,
      "starting_battery": 66,
      "ending_battery": 63,
      "rated_range_used": 8.29,
      "climate_fraction": 1,
      "sentry_fraction": 0,
      "energy_used": 2.64
    }
  ]
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/last_idle_state`

**Beschreibung**

- Letzten Ruhezustand abrufen
- Gibt Daten zurück, die sich darauf beziehen, wann ein Fahrzeug zuletzt aufgehört hat zu fahren oder zu laden.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "result": {
    "timestamp": 1675173627,
    "battery_level": 68,
    "usable_battery_level": 68,
    "battery_range": 204.96,
    "est_battery_range": 165.47,
    "ideal_battery_range": 999
  }
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/location`

**Beschreibung**

- Standort abrufen
- Gibt die Koordinaten, die Straßenadresse und den zugehörigen gespeicherten Standort eines Fahrzeugs zurück.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "latitude": 37.4929681,
  "longitude": -121.9453489,
  "address": "45500 Fremont Blvd, Fremont, California 94538, United States",
  "saved_location": "Work"
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/map`

**Beschreibung**

- Karte abrufen
- Gibt ein Kartenbild des Standorts eines Fahrzeugs zurück.

**Parameter**

- `width` (in: query, erforderlich: nein): Die Breite der Karte.
- `height` (in: query, erforderlich: nein): Die Höhe der Karte.
- `zoom` (in: query, erforderlich: nein): Die Zoomstufe der Karte.
- `marker_size` (in: query, erforderlich: nein): Die Größe der Fahrzeugmarkierung. Auf 0 setzen, um die Markierung auszublenden.
- `style` (in: query, erforderlich: nein): Der Stil der Karte.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

- Kein Antwortbeispiel in der Spezifikation vorhanden.

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/path`

**Beschreibung**

- Holen Sie sich den Fahrweg
- Gibt den Fahrweg eines Fahrzeugs während eines bestimmten Zeitraums zurück.

Wenn kein Zeitrahmen angegeben ist, wird der Fahrweg für die letzten 30 Tage zurückgegeben.

**Parameter**

- `separate` (in: query, erforderlich: nein): Ob der Pfad durch einzelne Laufwerke getrennt werden soll.
- `simplify` (in: query, erforderlich: nein): Ob der Pfad vereinfacht werden soll, um die Anzahl der Punkte zu reduzieren.
- `details` (in: query, erforderlich: nein): Ob der Pfad Details wie Zeitstempel, Geschwindigkeiten und Überschriften enthalten soll.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "results": [
    {
      "timestamp": 1728191237,
      "latitude": 40.73061,
      "longitude": -73.935242,
      "heading": 116,
      "battery_level": 79,
      "speed": 18,
      "odometer": 1234.56,
      "autopilot": "Standby"
    },
    {
      "timestamp": 1728191268,
      "latitude": 40.73061,
      "longitude": -73.935242,
      "heading": 109,
      "battery_level": 79,
      "speed": 10,
      "odometer": 1235.67,
      "autopilot": "Standby"
    },
    {
      "timestamp": 1728191299,
      "latitude": 40.73061,
      "longitude": -73.935242,
      "heading": 118,
      "battery_level": 78,
      "speed": 5,
      "odometer": 1236.78,
      "autopilot": "Off"
    }
  ]
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/plate`

**Beschreibung**

- Holen Sie sich ein Nummernschild
- Gibt das Kennzeichen des Fahrzeugs zurück.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "result": "GOFAST"
}
```

_Antwortbeschreibung: Okay_

#### `POST /{vin}/plate`

**Beschreibung**

- Nummernschild festlegen
- Legt das Nummernschild für das Fahrzeug fest.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "result": true
}
```

_Antwortbeschreibung: Okay_

#### `GET /{vin}/state`

**Beschreibung**

- Fahrzeug besorgen
- Gibt den neuesten Zustand eines Fahrzeugs zurück.

**Parameter**

- `use_cache` (in: query, erforderlich: nein): Auf „false“ setzen, um den Fahrzeugstatus in Echtzeit abzurufen. Nur ältere Modelle S und Modell X.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "id": 1492931520123456,
  "vin": "5YJXCAE43LF123456",
  "id_s": "1492931520123456",
  "color": "string",
  "state": "online",
  "user_id": 1311857,
  "in_service": true,
  "vehicle_id": 1349238573,
  "access_type": "OWNER",
  "api_version": 34,
  "drive_state": {
    "power": 0,
    "speed": "string",
    "heading": 194,
    "latitude": 40.7484,
    "gps_as_of": 1643590638,
    "longitude": 73.9857,
    "timestamp": 1643590652755,
    "native_type": "wgs",
    "shift_state": "P",
    "native_latitude": 40.7484,
    "native_longitude": 73.9857,
    "native_location_supported": 1,
    "active_route_destination": "Empire State Building",
    "active_route_energy_at_arrival": 81,
    "active_route_latitude": -1.123456,
    "active_route_longitude": 1.123456,
    "active_route_miles_to_arrival": 4.12,
    "active_route_minutes_to_arrival": 5.43,
    "active_route_traffic_minutes_delay": 0
  },
  "charge_state": {
    "timestamp": 1643590652755,
    "charge_amps": 12,
    "charge_rate": 0,
    "battery_level": 89,
    "battery_range": 269.01,
    "charger_power": 0,
    "trip_charging": true,
    "charger_phases": "string",
    "charging_state": "Complete",
    "charger_voltage": 0,
    "charge_limit_soc": 90,
    "battery_heater_on": true,
    "charge_port_color": "Off",
    "charge_port_latch": "Engaged",
    "conn_charge_cable": "SAE",
    "est_battery_range": 223.25,
    "fast_charger_type": "MCSingleWireCAN",
    "fast_charger_brand": "<invalid>",
    "charge_energy_added": 4.64,
    "charge_to_max_range": true,
    "ideal_battery_range": 999,
    "time_to_full_charge": 0,
    "charge_limit_soc_max": 100,
    "charge_limit_soc_min": 50,
    "charge_limit_soc_std": 90,
    "fast_charger_present": true,
    "usable_battery_level": 89,
    "charge_enable_request": true,
    "charge_port_door_open": true,
    "charger_pilot_current": 12,
    "preconditioning_times": "weekdays",
    "charge_current_request": 12,
    "charger_actual_current": 0,
    "minutes_to_full_charge": 0,
    "managed_charging_active": true,
    "off_peak_charging_times": "all_week",
    "off_peak_hours_end_time": 375,
    "preconditioning_enabled": true,
    "scheduled_charging_mode": "Off",
    "charge_miles_added_ideal": 4641,
    "charge_miles_added_rated": 14.5,
    "max_range_charge_counter": 0,
    "not_enough_power_to_heat": true,
    "scheduled_departure_time": 1643578200,
    "off_peak_charging_enabled": true,
    "charge_current_request_max": 12,
    "scheduled_charging_pending": true,
    "user_charge_enable_request": "string",
    "managed_charging_start_time": "string",
    "charge_port_cold_weather_mode": "string",
    "scheduled_charging_start_time": "string",
    "managed_charging_user_canceled": true,
    "scheduled_departure_time_minutes": 810,
    "scheduled_charging_start_time_app": 817,
    "supercharger_session_trip_planner": true,
    "pack_current": -0.7,
    "pack_voltage": 419.79,
    "module_temp_min": 25.5,
    "module_temp_max": 26,
    "energy_remaining": 51.26,
    "lifetime_energy_used": 5224.713
  },
  "display_name": "Seneca",
  "gui_settings": {
    "timestamp": 1643590652755,
    "gui_24_hour_time": true,
    "show_range_units": true,
    "gui_range_display": "Rated",
    "gui_distance_units": "mi/hr",
    "gui_charge_rate_units": "kW",
    "gui_temperature_units": "F"
  },
  "option_codes": "AD15MDL3PBSBRENABT37ID3WRF3GS3PBDRLHDV2WW39BAPF0COUSBC3BCH07PC30FC3PFG31GLFRHL31HM31IL31LTPBMR31FM3BRS3HSA3PSTCPSC04SU3CT3CATW00TM00UT3PWR00AU3PAPH3AF00ZCSTMI00CDM0",
  "climate_state": {
    "timestamp": 1643590652755,
    "fan_status": 0,
    "inside_temp": 24.3,
    "defrost_mode": 0,
    "outside_temp": 17.5,
    "is_climate_on": true,
    "battery_heater": true,
    "bioweapon_mode": true,
    "max_avail_temp": 28,
    "min_avail_temp": 15,
    "seat_heater_left": 0,
    "hvac_auto_request": "On",
    "seat_heater_right": 0,
    "is_preconditioning": true,
    "wiper_blade_heater": true,
    "climate_keeper_mode": "off",
    "driver_temp_setting": 22.8,
    "left_temp_direction": 0,
    "side_mirror_heaters": true,
    "is_rear_defroster_on": true,
    "right_temp_direction": 0,
    "is_front_defroster_on": true,
    "seat_heater_rear_left": 0,
    "steering_wheel_heater": true,
    "passenger_temp_setting": 22.8,
    "seat_heater_rear_right": 0,
    "battery_heater_no_power": true,
    "is_auto_conditioning_on": true,
    "seat_heater_rear_center": 0,
    "cabin_overheat_protection": "On",
    "seat_heater_third_row_left": 0,
    "seat_heater_third_row_right": 0,
    "remote_heater_control_enabled": true,
    "allow_cabin_overheat_protection": true,
    "supports_fan_only_cabin_overheat_protection": true
  },
  "vehicle_state": {
    "df": 0,
    "dr": 0,
    "ft": 0,
    "pf": 0,
    "pr": 0,
    "rt": 0,
    "locked": true,
    "odometer": 14096.485641,
    "fd_window": 0,
    "fp_window": 0,
    "rd_window": 0,
    "rp_window": 0,
    "timestamp": 1643590652755,
    "santa_mode": 0,
    "valet_mode": true,
    "api_version": 34,
    "car_version": "2022.4 fae2af490933",
    "media_state": {
      "remote_control_enabled": true
    },
    "sentry_mode": true,
    "remote_start": true,
    "vehicle_name": "Seneca",
    "dashcam_state": "Unavailable",
    "autopark_style": "standard",
    "homelink_nearby": true,
    "is_user_present": true,
    "software_update": {
      "status": "available",
      "version": "2022.4",
      "install_perc": 1,
      "download_perc": 0,
      "expected_duration_sec": 2700
    },
    "speed_limit_mode": {
      "active": true,
      "pin_code_set": true,
      "max_limit_mph": 90,
      "min_limit_mph": 50,
      "current_limit_mph": 84
    },
    "tpms_pressure_fl": "string",
    "tpms_pressure_fr": "string",
    "tpms_pressure_rl": "string",
    "tpms_pressure_rr": "string",
    "autopark_state_v2": "standby",
    "calendar_supported": true,
    "last_autopark_error": "no_error",
    "center_display_state": 0,
    "remote_start_enabled": true,
    "homelink_device_count": 0,
    "sentry_mode_available": true,
    "remote_start_supported": true,
    "smart_summon_available": true,
    "notifications_supported": true,
    "parsed_calendar_supported": true,
    "dashcam_clip_save_available": true,
    "summon_standby_mode_enabled": true
  },
  "backseat_token": "string",
  "vehicle_config": {
    "plg": true,
    "pws": true,
    "rhd": true,
    "car_type": "modelx",
    "seat_type": 0,
    "timestamp": 1643590652755,
    "eu_vehicle": true,
    "roof_color": "None",
    "utc_offset": -28800,
    "wheel_type": "Turbine22Dark",
    "spoiler_type": "Passive",
    "trim_badging": "p100d",
    "driver_assist": "TeslaAP3",
    "headlamp_type": "Led",
    "exterior_color": "Pearl",
    "rear_seat_type": 7,
    "rear_drive_unit": "Large",
    "third_row_seats": "FuturisFoldFlat",
    "car_special_type": "base",
    "charge_port_type": "US",
    "ece_restrictions": true,
    "front_drive_unit": "PermanentMagnet",
    "has_seat_cooling": true,
    "rear_seat_heaters": 3,
    "use_range_badging": true,
    "can_actuate_trunks": true,
    "efficiency_package": "Default",
    "has_air_suspension": true,
    "has_ludicrous_mode": true,
    "interior_trim_type": "AllBlack",
    "sun_roof_installed": 0,
    "default_charge_to_max": true,
    "motorized_charge_port": true,
    "dashcam_clip_save_supported": true,
    "can_accept_navigation_requests": true
  },
  "calendar_enabled": true,
  "backseat_token_updated_at": "string"
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/states`

**Beschreibung**

- Erhalten Sie historische Zustände
- Gibt historische Zustände für ein Fahrzeug während eines Zeitraums zurück.

Wenn kein Intervall angegeben ist, wird ein sinnvolles Intervall basierend auf dem Zeitrahmen verwendet.

**Parameter**

- `interval` (in: query, erforderlich: nein): Die gewünschte Anzahl von Sekunden zwischen Datenpunkten. Auf 1 setzen, um alle Datenpunkte zurückzugeben.
- `condense` (in: query, erforderlich: nein): Ob die Datenausgabe komprimiert werden soll.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "results": [
    {
      "id": 9271662515,
      "timestamp": 1644010150,
      "state": "online",
      "charging_state": "Charging",
      "shift_state": "P",
      "version": "2022.4",
      "battery_level": 88,
      "usable_battery_level": 88,
      "battery_range": 266.69,
      "est_battery_range": 221.31,
      "ideal_battery_range": 999,
      "latitude": 40.7484,
      "longitude": 73.9857,
      "elevation": null,
      "heading": 213,
      "speed": null,
      "power": 0,
      "odometer": 14096.5,
      "charge_rate": 2,
      "charger_actual_current": 12,
      "charger_power": 1,
      "charger_phases": 1,
      "charger_voltage": 118,
      "charge_miles_added_rated": 1.5,
      "charge_miles_added_ideal": 422,
      "is_climate_on": 0,
      "is_preconditioning": 0,
      "battery_heater_on": 0,
      "inside_temp": 37.7,
      "outside_temp": 20.5,
      "left_temp_direction": 0,
      "right_temp_direction": 0,
      "df": 0,
      "dr": 0,
      "ft": 0,
      "pf": 0,
      "pr": 0,
      "rt": 0,
      "locked": 1,
      "fd_window": 0,
      "fp_window": 0,
      "rd_window": 0,
      "rp_window": 0,
      "sentry_mode": 0,
      "valet_mode": 0
    },
    {
      "id": 9271668763,
      "timestamp": 1644010160,
      "state": "online",
      "charging_state": "Charging",
      "shift_state": "P",
      "version": "2022.4",
      "battery_level": 88,
      "usable_battery_level": 88,
      "battery_range": 266.69,
      "est_battery_range": 221.31,
      "ideal_battery_range": 999,
      "latitude": 40.7484,
      "longitude": 73.9857,
      "elevation": null,
      "heading": 213,
      "speed": null,
      "power": 0,
      "odometer": 14096.5,
      "charge_rate": 1,
      "charger_actual_current": 12,
      "charger_power": 1,
      "charger_phases": 1,
      "charger_voltage": 119,
      "charge_miles_added_rated": 1.5,
      "charge_miles_added_ideal": 422,
      "is_climate_on": 0,
      "is_preconditioning": 0,
      "battery_heater_on": 0,
      "inside_temp": 37.8,
      "outside_temp": 20.5,
      "left_temp_direction": 0,
      "right_temp_direction": 0,
      "df": 0,
      "dr": 0,
      "ft": 0,
      "pf": 0,
      "pr": 0,
      "rt": 0,
      "locked": 1,
      "fd_window": 0,
      "fp_window": 0,
      "rd_window": 0,
      "rp_window": 0,
      "sentry_mode": 0,
      "valet_mode": 0
    },
    {
      "id": 9271676809,
      "timestamp": 1644010170,
      "state": "online",
      "charging_state": "Charging",
      "shift_state": "P",
      "version": "2022.4",
      "battery_level": 88,
      "usable_battery_level": 88,
      "battery_range": 266.69,
      "est_battery_range": 221.31,
      "ideal_battery_range": 999,
      "latitude": 40.7484,
      "longitude": 73.9857,
      "elevation": null,
      "heading": 213,
      "speed": null,
      "power": 0,
      "odometer": 14096.5,
      "charge_rate": 1,
      "charger_actual_current": 12,
      "charger_power": 1,
      "charger_phases": 1,
      "charger_voltage": 118,
      "charge_miles_added_rated": 1.5,
      "charge_miles_added_ideal": 422,
      "is_climate_on": 0,
      "is_preconditioning": 0,
      "battery_heater_on": 0,
      "inside_temp": 37.7,
      "outside_temp": 20.5,
      "left_temp_direction": 0,
      "right_temp_direction": 0,
      "df": 0,
      "dr": 0,
      "ft": 0,
      "pf": 0,
      "pr": 0,
      "rt": 0,
      "locked": 1,
      "fd_window": 0,
      "fp_window": 0,
      "rd_window": 0,
      "rp_window": 0,
      "sentry_mode": 0,
      "valet_mode": 0
    }
  ]
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/status`

**Beschreibung**

- Status abrufen
- Gibt den Status eines Fahrzeugs zurück.

Der Status kann „schlafend“, „wartet auf Schlaf“ oder „wach“ sein.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "status": "asleep"
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/tire_pressure`

**Beschreibung**

- Reifendruck ermitteln
- Gibt den Reifendruck eines Fahrzeugs zurück, gemessen in Bar.

Erfordert Firmware 2022.4.5+.

**Parameter**

- `pressure_format` (in: query, erforderlich: nein): Die Druckeinheit.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "front_left": 2.275,
  "front_right": 2.325,
  "rear_left": 2.4,
  "rear_right": 2.425,
  "front_left_status": "low",
  "front_right_status": "low",
  "rear_left_status": "low",
  "rear_right_status": "low",
  "timestamp": 1645131216
}
```

_Antwortbeschreibung: Erfolg_

#### `GET /{vin}/weather`

**Beschreibung**

- Holen Sie sich Wetter
- Gibt die Wettervorhersage rund um ein Fahrzeug zurück.

**Beispielanfrage**

- Kein Anfragebeispiel in der Spezifikation vorhanden.

**Beispielantwort**

```json
{
  "location": "Fremont",
  "condition": "Clear",
  "temperature": 22.77,
  "feels_like": 21.26,
  "humidity": 91,
  "visibility": 10000,
  "pressure": 1017,
  "sunrise": 1672757473,
  "sunset": 1672793687,
  "cloudiness": 25,
  "wind_speed": 8.23,
  "wind_direction": 160
}
```

_Antwortbeschreibung: Erfolg_

