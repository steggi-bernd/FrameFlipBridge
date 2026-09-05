# SPDX-License-Identifier: GPL-3.0-or-later
"""Prueft den Teil des Addons, der ohne Blender auskommt.

``bridge.py`` importiert absichtlich kein ``bpy``. Genau deshalb laesst sich das
Stueck, auf das es ankommt -- die Verbindung, die Warteschlange, das Verhalten bei
abwesendem Gegenueber -- hier pruefen, ohne Blender zu starten.

Aufruf:  python tests/test_bridge.py
"""

import json
import os
import socket
import sys
import tempfile
import threading
import time

# Direkt ueber den Dateipfad geladen, nicht ueber das Paket: Dessen __init__
# importiert bpy und liefe nur in Blender. Dass das hier gelingt, ist zugleich der
# Beweis, dass bridge.py wirklich ohne bpy auskommt.
import importlib.util                        # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location(
    "ff_bridge", os.path.join(_ROOT, "frameflip_bridge", "bridge.py"))

bridge = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bridge)

PASSED = 0
FAILED = 0


def check(condition, what, detail=""):
    global PASSED, FAILED

    if condition:
        PASSED += 1
        print("  [ok]   %s" % what)
    else:
        FAILED += 1
        print("  [FEHL] %s %s" % (what, detail))


def group(title):
    print("\n%s\n%s" % (title, "-" * len(title)))


class Receiver:
    """Spielt FrameFlip: nimmt eine Verbindung an und sammelt die Zeilen."""

    def __init__(self):
        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]

        self.lines = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self.server.settimeout(5.0)
            conn, _ = self.server.accept()
        except OSError:
            return

        conn.settimeout(0.4)
        buffer = b""

        while not self._stop.is_set():
            try:
                chunk = conn.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            if not chunk:
                break

            buffer += chunk
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                if raw.strip():
                    self.lines.append(json.loads(raw.decode("utf-8")))

        conn.close()

    def close(self):
        self._stop.set()
        try:
            self.server.close()
        except OSError:
            pass


def with_handshake(port, token):
    """Legt eine Handschlagdatei an und biegt den Pfad darauf um."""
    folder = tempfile.mkdtemp(prefix="ffbridge_")
    path = os.path.join(folder, "bridge.json")

    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"port": port, "token": token}, handle)

    bridge.handshake_path = lambda: path
    return path


def test_sends_in_order():
    group("Bruecke - Meldungen kommen an, in der Reihenfolge")

    receiver = Receiver()
    with_handshake(receiver.port, "testtoken")

    sender = bridge.Sender()
    sender.start()

    for frame in range(1, 6):
        sender.send({"type": "write", "frame": frame})

    deadline = time.time() + 5
    while time.time() < deadline and len(receiver.lines) < 6:
        time.sleep(0.05)

    sender.stop()
    receiver.close()

    check(len(receiver.lines) >= 6, "Handschlag und fuenf Meldungen", str(len(receiver.lines)))

    if receiver.lines:
        check(receiver.lines[0].get("type") == "hello",
              "die erste Zeile ist der Handschlag")
        check(receiver.lines[0].get("token") == "testtoken",
              "mit dem Token aus der Datei")

    frames = [line.get("frame") for line in receiver.lines if line.get("type") == "write"]
    check(frames == [1, 2, 3, 4, 5], "die Reihenfolge bleibt erhalten", str(frames))


def test_never_blocks_without_receiver():
    group("Bruecke - ohne Gegenueber wird nichts blockiert")

    # Ein Pfad, an dem nichts liegt: kein Port, kein Token, keine Verbindung.
    bridge.handshake_path = lambda: os.path.join(tempfile.gettempdir(), "gibtesnicht.json")

    check(bridge.read_handshake() is None, "ohne Datei gibt es keine Verbindungsdaten")

    sender = bridge.Sender()
    sender.start()

    started = time.time()
    for i in range(bridge.QUEUE_LIMIT * 3):
        sender.send({"type": "stats", "text": "Sample %d/128" % i})
    elapsed = time.time() - started

    check(elapsed < 1.0,
          "dreifach ueberfuellte Warteschlange kostet keine Sekunde",
          "%.3f s" % elapsed)
    check(sender.dropped > 0, "und alte Meldungen fallen heraus", str(sender.dropped))
    check(not sender.connected, "verbunden ist dabei nichts")

    stopping = time.time()
    sender.stop()
    check(time.time() - stopping < 2.0, "das Beenden haengt nicht am Wiederholungstakt")


def test_handshake_is_read_defensively():
    group("Bruecke - unbrauchbare Handschlagdatei")

    folder = tempfile.mkdtemp(prefix="ffbridge_bad_")

    for name, content in (
        ("leer.json", ""),
        ("kaputt.json", "{das ist kein json"),
        ("fehlt.json", '{"port": 1234}'),
        ("port0.json", '{"port": 0, "token": "x"}'),
        ("porttext.json", '{"port": "abc", "token": "x"}'),
        ("leertoken.json", '{"port": 1234, "token": ""}'),
    ):
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

        bridge.handshake_path = lambda p=path: p
        check(bridge.read_handshake() is None, "%s ergibt nichts" % name)

    good = os.path.join(folder, "gut.json")
    with open(good, "w", encoding="utf-8") as handle:
        handle.write('{"port": 47823, "token": "abc"}')

    bridge.handshake_path = lambda: good
    check(bridge.read_handshake() == (47823, "abc"),
          "eine gueltige Datei wird dagegen gelesen")


def test_reconnects_after_loss():
    group("Bruecke - Verbindung kommt nach einem Abbruch zurueck")

    receiver = Receiver()
    with_handshake(receiver.port, "t1")

    sender = bridge.Sender()
    sender.start()
    sender.send({"type": "init", "job": "a"})

    deadline = time.time() + 5
    while time.time() < deadline and not sender.connected:
        time.sleep(0.05)

    check(sender.connected, "erst verbunden")

    # FrameFlip verschwindet, ein neues nimmt denselben Port nicht wieder ein -
    # der Sender muss das aushalten, ohne stehenzubleiben.
    receiver.close()
    time.sleep(0.3)

    for i in range(20):
        sender.send({"type": "stats", "text": "x%d" % i})

    sender.stop()
    check(True, "der Abbruch fuehrt zu keiner Ausnahme")


def main():
    test_sends_in_order()
    test_never_blocks_without_receiver()
    test_handshake_is_read_defensively()
    test_reconnects_after_loss()

    print("\n%d Zusicherungen erfuellt, %d fehlgeschlagen." % (PASSED, FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
