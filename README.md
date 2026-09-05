# FrameFlip Bridge

**Blender-Addon, das laufende Renders an [FrameFlip](https://github.com/steggi-bernd/FrameFlip) meldet.**

Einmal installiert, meldet er jeden Render dieser Blender-Instanz — ohne dass
irgendwo etwas eingeschaltet werden muss. FrameFlip zeigt daraufhin Fortschritt,
Sample-Zähler, Zeit je Frame und die Auslastung des Rechners an, und lädt jeden
fertig geschriebenen Frame sofort in die Vorschau.

## Was er tut — und was ausdrücklich nicht

Der Addon ist mit Absicht dünn. Er reicht weiter, **was nur Blender weiß**:

* welcher Auftrag beginnt — Szene, Engine, Frame-Bereich, Auflösung, Ausgabepfad
* welcher Frame gerade läuft und welche Datei geschrieben wurde
* Blenders eigenen Fortschrittstext, unausgewertet

Alles über den Rechner — CPU, Arbeitsspeicher, GPU — misst FrameFlip selbst. Es
läuft ohnehin dauerhaft im Tray und kann es besser.

Diese Aufteilung ist keine Bequemlichkeit, sondern hält den Addon frei von
**Fremdpaketen**, von **Netzwerkcode** und von **Geheimnissen**:

* Nur Pythons Standardbibliothek. Nichts zu installieren, nichts zu aktualisieren.
* Gesprochen wird ausschließlich mit `127.0.0.1` — dem eigenen Rechner.
* Der Kopplungsschlüssel fürs Handy liegt bei FrameFlip. Blender speichert
  Passwörter in Addon-Einstellungen im Klartext; dort hätte er nichts verloren.

**Keine Bilddaten** gehen über die Brücke. Der Addon meldet einen Pfad, FrameFlip
liest die Datei selbst — das kostet Blender nichts.

## Installation

Blender 4.2 und neuer:

1. `frameflip_bridge` als ZIP packen
2. *Edit → Preferences → Get Extensions → Install from Disk*

Ältere Versionen (3.6 bis 4.1): dasselbe ZIP über *Add-ons → Install*.

Ob es funktioniert, steht in *Properties → Output → FrameFlip*: „Verbunden",
„Verbinde …" oder „FrameFlip läuft nicht".

## Der Grundsatz, der den ganzen Aufbau bestimmt

> **Handler dürfen nichts tun außer einen Eintrag in eine Warteschlange legen.**

Blenders Render-Handler laufen auf dem Hauptthread. Alles, was dort wartet, hält
den Render an — ein Socket-Schreibvorgang an einer schlechten Verbindung kostet
Sekunden **je Frame**. Deshalb legt der Handler nur ab, und ein eigener Thread
trägt fort.

Auch die Warteschlange blockiert nie. Läuft FrameFlip nicht, fallen die ältesten
Meldungen heraus. Ein verlorener Zwischenstand ist belanglos; ein hängender Render
ist es nicht.

## Was Blender nicht hergibt

Zwei Grenzen, am Quelltext geprüft und in
[FrameFlips Technikdokument](https://github.com/steggi-bernd/FrameFlip/blob/main/docs/Blender-Bridge.md)
mit Fundstellen belegt:

**Ein laufender Render lässt sich nicht abbrechen.** Es gibt nur
`RENDER_OT_render`; die Animationsschleife bricht allein über das globale Flag
`G.is_break` ab, das keine Python-Anbindung hat. Auch `frame_end` nachträglich zu
senken hilft nicht — der Endwert wird beim Start der Schleife festgehalten.

**Der Fortschrittstext ist in der Oberfläche arm.** Restzeit, Speicher und der
Sample-Zähler stehen nur bei `blender -b` darin. Deshalb wird er defensiv
ausgewertet — drüben in FrameFlip, nicht hier — und keine Anzeige hängt davon ab,
ob er sich lesen lässt.

Beides spricht dafür, Renders als eigenen Hintergrundprozess zu starten. Das
übernimmt FrameFlip, nicht dieser Addon: Es läuft im Tray weiter, wenn Blender
längst geschlossen ist.

## Tests

```bash
python tests/test_bridge.py
```

Läuft **ohne Blender**. `bridge.py` importiert kein `bpy` — genau deshalb lässt
sich der Teil prüfen, auf den es ankommt: Verbindung, Warteschlange und das
Verhalten bei abwesendem Gegenüber. Dass der Test überhaupt startet, ist zugleich
der Beweis für diese Trennung.

## Lizenz

GPL-3.0-or-later. Ein Blender-Addon bindet `bpy` ein und muss deshalb unter der
GPL stehen. FrameFlip selbst steht unter MIT und bleibt es — die beiden reden über
einen Socket miteinander, nicht über einen gemeinsamen Prozess.
