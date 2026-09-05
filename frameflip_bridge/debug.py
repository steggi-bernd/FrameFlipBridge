# SPDX-License-Identifier: GPL-3.0-or-later
"""Mitschnitt fuer die Fehlersuche.

Absichtlich ein eigenes Modul mit einer einzigen Funktion nach aussen: ``log``.
Wer es spaeter nicht mehr braucht, loescht diese Datei, entfernt die ``debug.log``-
Aufrufe -- es sind wenige und alle einzeilig -- und den Abschnitt im Panel. Nichts
anderes haengt daran.

Warum ueberhaupt: Wird Blender ueber Steam oder eine Verknuepfung gestartet, gibt
es kein Konsolenfenster. ``print`` liefe damit ins Leere, und ein Addon, das
stillschweigend nichts meldet, ist von einem kaputten nicht zu unterscheiden.
Deshalb eine Datei -- und dieselben Zeilen zusaetzlich im Panel, damit man ohne
Dateimanager sieht, was los ist.
"""

import os
import tempfile
import threading
import time

#: Wie viele Zeilen fuer die Anzeige im Panel vorgehalten werden.
MEMORY_LINES = 40

#: Ab dieser Groesse wird die Datei einmal zurueckgesetzt, damit sie nicht waechst.
MAX_BYTES = 512 * 1024

#: Aus heisst: keine Datei, keine Zeilen, kein Aufwand.
enabled = True

_lines = []
_gate = threading.Lock()
_started = time.time()


def path():
    """Wo der Mitschnitt liegt. Im Temp-Ordner - er ist Diagnose, kein Dokument."""
    return os.path.join(tempfile.gettempdir(), "frameflip_bridge.log")


def log(text):
    """Eine Zeile festhalten. Darf aus jedem Thread gerufen werden und wirft nie."""
    if not enabled:
        return

    line = "%7.2f  %s" % (time.time() - _started, text)

    with _gate:
        _lines.append(line)
        if len(_lines) > MEMORY_LINES:
            del _lines[:-MEMORY_LINES]

    try:
        file = path()

        # Zuruecksetzen statt rotieren: Fuer eine Fehlersuche zaehlt das Neueste,
        # und ein zweiter Dateiname waere nur eine weitere Stelle zum Aufraeumen.
        if os.path.exists(file) and os.path.getsize(file) > MAX_BYTES:
            os.remove(file)

        with open(file, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        # Ein Mitschnitt, der sich nicht schreiben laesst, ist ein Schoenheitsfehler.
        pass


def lines():
    """Die letzten Zeilen, juengste zuletzt."""
    with _gate:
        return list(_lines)


def clear():
    with _gate:
        del _lines[:]

    try:
        if os.path.exists(path()):
            os.remove(path())
    except OSError:
        pass
