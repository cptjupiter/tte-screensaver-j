# Themen für den Spielplatz

Jede `.json`-Datei in diesem Ordner ist ein Thema. Der Spielplatz lädt beim
Speichern automatisch neu – Datei im Editor ändern, speichern, zuschauen.

Dateien, deren Name mit `_` beginnt, werden ignoriert (gut für Entwürfe).
Die Reihenfolge ergibt sich aus dem Dateinamen (`01-…`, `02-…`).

## Neues Thema anlegen

1. Eine bestehende Datei kopieren, z. B. `02-jupiter.json` → `05-mein-thema.json`
2. Werte anpassen und speichern
3. Im Spielplatz mit ↑ / ↓ zum Thema wechseln

## Felder

| Feld | Bedeutung | Beispiel |
|---|---|---|
| `name` | Anzeigename | `"Jupiter"` |
| `text` | Text, der automatisch als ASCII-Art gesetzt wird (braucht `pyfiglet`) | `"JUPITER"` |
| `font` | Schriftart für `text` ([Liste](http://www.figlet.org/examples.html)) | `"ansi_shadow"`, `"slant"`, `"big"` |
| `ascii_file` | Stattdessen fertige ASCII-Art aus einer Textdatei in diesem Ordner | `"logo.txt"` |
| `ascii_art` | Oder direkt im JSON, als Liste von Zeilen | `["###", "# #"]` |
| `background` | Hintergrundfarbe | `"#0b0d17"` |
| `font_size` | Schriftgrösse in Pixel | `18` |
| `colors` | Farbverlauf für das fertige Bild (alle Effekte mit `final_gradient_stops`) | `["#ff2a6d", "#05d9e8"]` |
| `direction` | Richtung des Verlaufs | `"vertical"`, `"horizontal"`, `"diagonal"`, `"radial"` |
| `effects` | Nur diese Effekte zeigen (leer oder weglassen = alle) | `["Matrix", "Decrypt"]` |
| `effect_settings` | Feineinstellungen pro Effekt, siehe unten | |

Ohne `text`, `ascii_file` und `ascii_art` wird die Standard-ASCII-Art verwendet.

## Feineinstellungen pro Effekt

Jeder Effekt hat eigene Einstellungen (Farben, Tempo, Symbole). Im Spielplatz
**Taste I** drücken – dann erscheinen alle Einstellungen des laufenden Effekts
mit ihren Standardwerten in der Konsole. Diese lassen sich im Thema überschreiben:

```json
"effect_settings": {
  "Matrix": {
    "rain_color_gradient": ["#e3a857", "#6b3a14"],
    "rain_time": 8
  }
}
```

Farben als `"#rrggbb"`, Bereiche als `[von, bis]`, Richtungen als Text.
Einige Effekte (z. B. SynthGrid) haben kein `final_gradient_stops` – dort
wirkt `colors` nicht, und die Farben werden nur über `effect_settings` gesetzt.
