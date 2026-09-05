# SPDX-License-Identifier: GPL-3.0-or-later
"""Verbindung zu FrameFlip.

Der wichtigste Satz dieses Moduls: **Hier wird nichts blockiert.** Die Handler
laufen auf Blenders Hauptthread, und alles, was dort wartet, haelt den Render an.
Ein Socket-Schreibvorgang kann warten -- also legt der Handler nur einen Eintrag in
eine Warteschlange, und ein eigener Thread traegt ihn fort.

Auch die Warteschlange selbst blockiert nie: Ist sie voll, weil FrameFlip nicht
laeuft, fallen die aeltesten Meldungen heraus. Ein verlorener Zwischenstand ist
belanglos; ein haengender Render ist es nicht.
"""

import json
import os
import queue
import socket
import threading
import time

try:
    from . import debug
except ImportError:                     # ohne Paketkontext geladen, etwa im Test
    class debug:                        # noqa: N801 - steht fuer ein Modul
        """Platzhalter. Haelt bridge.py fuer sich allein lauffaehig."""

        @staticmethod
        def log(_text):
            pass

#: Wo FrameFlip Port und Token hinterlegt. Gleiches Benutzerkonto, gleiches Profil.
HANDSHAKE_NAME = os.path.join("FrameFlip", "bridge.json")

#: Mehr als das staut sich nur an, wenn niemand zuhoert.
QUEUE_LIMIT = 256

#: Wartezeiten zwischen Verbindungsversuchen, in Sekunden.
RETRY_STEPS = (1, 2, 5, 10, 30)


def handshake_path():
    """Pfad der Handschlagdatei, oder None auf Systemen ohne APPDATA."""
    base = os.environ.get("APPDATA")
    return os.path.join(base, HANDSHAKE_NAME) if base else None


def read_handshake():
    """Port und Token, oder None. Jeder Fehler bedeutet schlicht: keine Bruecke."""
    path = handshake_path()
    if not path or not os.path.isfile(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        port = int(data["port"])
        token = str(data["token"])
    except (OSError, ValueError, KeyError, TypeError):
        return None

    return (port, token) if 0 < port < 65536 and token else None


class Sender:
    """Nimmt Meldungen entgegen und schickt sie, sobald FrameFlip erreichbar ist."""

    def __init__(self):
        self._queue = queue.Queue(maxsize=QUEUE_LIMIT)
        self._thread = None
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._dropped = 0

        # Wird nach JEDEM Verbindungsaufbau als Erstes geschickt.
        #
        # Ohne das verliert eine spaet gestartete Gegenstelle den Anschluss: Sie hat
        # den Beginn des Auftrags nie gesehen und kann mit den folgenden Meldungen
        # nichts anfangen - sie weiss ja nicht, zu welchem Auftrag sie gehoeren.
        self._preamble = None
        self._preamble_gate = threading.Lock()

    # ------------------------------------------------------------------ Zustand

    @property
    def connected(self):
        return self._connected.is_set()

    @property
    def dropped(self):
        """Wie viele Meldungen verworfen wurden. Nur zur Anzeige."""
        return self._dropped

    # ------------------------------------------------------------------ Betrieb

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="FrameFlipBridge", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._connected.clear()

        # Ein leerer Eintrag weckt den Thread aus dem Warten auf die Warteschlange.
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

        thread, self._thread = self._thread, None
        if thread and thread.is_alive():
            thread.join(timeout=1.0)

    def set_preamble(self, message):
        """
        Was jede neue Verbindung zuerst erfahren muss - hier die Beschreibung des
        laufenden Auftrags. ``None`` loescht sie, sobald der Auftrag endet.
        """
        with self._preamble_gate:
            self._preamble = message

    def send(self, message):
        """Aus dem Handler aufzurufen. Kehrt sofort zurueck, immer."""
        if self._stop.is_set():
            return

        try:
            self._queue.put_nowait(message)
        except queue.Full:
            # Aeltestes wegwerfen und das neue nehmen: Der aktuelle Stand ist
            # interessanter als der von vor einer Minute.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(message)
            except (queue.Empty, queue.Full):
                pass

            self._dropped += 1

    # ------------------------------------------------------------------ Thread

    def _run(self):
        attempt = 0
        sock = None

        while not self._stop.is_set():
            if sock is None:
                sock = self._connect()

                if sock is None:
                    # Nicht erreichbar. Warten, aber unterbrechbar - beim Beenden
                    # von Blender soll niemand dreissig Sekunden auf uns warten.
                    delay = RETRY_STEPS[min(attempt, len(RETRY_STEPS) - 1)]
                    attempt += 1
                    self._stop.wait(delay)
                    continue

                attempt = 0
                self._connected.set()
                debug.log("verbunden")

            try:
                message = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if message is None:
                break

            payload = (json.dumps(message) + "\n").encode("utf-8")

            try:
                sock.sendall(payload)
            except OSError:
                # Gegenstelle weg. Verbindung fallen lassen und neu aufbauen; die
                # Meldung ist verloren, was bei einem Zwischenstand nicht schmerzt.
                debug.log("Verbindung verloren")

                self._close(sock)
                sock = None
                self._connected.clear()

        self._close(sock)
        self._connected.clear()

    def _connect(self):
        info = read_handshake()
        if info is None:
            return None

        port, token = info

        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=2.0)
            sock.settimeout(5.0)

            greeting = json.dumps({"type": "hello", "token": token}) + "\n"
            sock.sendall(greeting.encode("utf-8"))

            with self._preamble_gate:
                preamble = self._preamble

            if preamble is not None:
                sock.sendall((json.dumps(preamble) + "\n").encode("utf-8"))
                debug.log("Auftrag nach Verbindungsaufbau erneut gemeldet")

            return sock
        except OSError:
            return None

    @staticmethod
    def _close(sock):
        if sock is None:
            return

        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

        try:
            sock.close()
        except OSError:
            pass


#: Eine Verbindung je Blender-Instanz genuegt.
sender = Sender()


def now():
    return time.monotonic()
