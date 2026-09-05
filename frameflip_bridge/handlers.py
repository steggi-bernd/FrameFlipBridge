# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Anknuepfpunkte an Blenders Renderlauf.

Alle Handler tragen ``@persistent``. Ohne den Dekorator wuerde Blender sie beim
Laden einer anderen Datei entfernen -- und genau das soll nicht passieren: Einmal
installiert, meldet der Addon jeden Render dieser Blender-Instanz, ohne dass
irgendwo etwas eingeschaltet werden muss.

Jeder Handler tut hier nur zweierlei: ein paar Werte einsammeln und sie in die
Warteschlange legen. Er laeuft auf Blenders Hauptthread; alles, was dort wartet,
haelt den Render an.
"""

import os
import uuid

import bpy
from bpy.app.handlers import persistent

from . import bridge, debug

#: Wie oft der Fortschrittstext hoechstens weitergereicht wird, in Sekunden.
#: Blender ruft render_stats deutlich oefter; die Anzeige braucht das nicht.
STATS_INTERVAL = 0.5

#: Zustand des laufenden Auftrags. Nur aus dem Hauptthread angefasst.
_job = {"id": None, "last_stats": 0.0}


def _new_job_id():
    return uuid.uuid4().hex[:8]


def _output_directory(scene):
    """Der Ordner, in den geschrieben wird - FrameFlip findet die Frames selbst."""
    try:
        return os.path.dirname(bpy.path.abspath(scene.render.filepath))
    except (AttributeError, ValueError):
        return ""


def _frame_path(scene, frame):
    """
    Die Datei, die Blender fuer diesen Frame geschrieben hat.

    ``frame_path`` rechnet Praefix, Stellenzahl und Endung aus den
    Ausgabeeinstellungen aus. Das selbst zusammenzusetzen ginge daneben, sobald
    jemand ein anderes Namensschema oder Format benutzt.
    """
    try:
        return bpy.path.abspath(scene.render.frame_path(frame=frame))
    except (AttributeError, ValueError, TypeError):
        return ""


def _engine(scene):
    try:
        return scene.render.engine or ""
    except AttributeError:
        return ""


# ---------------------------------------------------------------------- Handler


@persistent
def on_render_init(scene, *_args):
    _job["id"] = _new_job_id()
    debug.log("render_init")
    _job["last_stats"] = 0.0

    try:
        render = scene.render
        percent = max(1, render.resolution_percentage) / 100.0

        bridge.sender.send({
            "type": "init",
            "job": _job["id"],
            "file": bpy.data.filepath or "",
            "scene": scene.name,
            "engine": _engine(scene),
            "first": int(scene.frame_start),
            "last": int(scene.frame_end),
            "width": int(render.resolution_x * percent),
            "height": int(render.resolution_y * percent),
            "output": _output_directory(scene),
        })
    except (AttributeError, ValueError):
        # Eine unvollstaendige Meldung ist besser als eine Ausnahme im Handler:
        # Blender gibt Fehler aus Handlern nur auf der Konsole aus, und der Nutzer
        # saehe bloss einen Render, der nichts meldet.
        bridge.sender.send({"type": "init", "job": _job["id"]})


@persistent
def on_render_pre(scene, *_args):
    debug.log("render_pre  Frame %d" % scene.frame_current)

    if _job["id"] is None:
        on_render_init(scene)

    bridge.sender.send({
        "type": "pre",
        "job": _job["id"],
        "frame": int(scene.frame_current),
    })


@persistent
def on_render_write(scene, *_args):
    frame = int(scene.frame_current)

    debug.log("render_write Frame %d" % frame)

    bridge.sender.send({
        "type": "write",
        "job": _job["id"],
        "frame": frame,
        "path": _frame_path(scene, frame),
    })


@persistent
def on_render_stats(text, *_args):
    """
    Bekommt als einziger Handler keinen Scene, sondern den Fortschrittstext.

    Der Text ist keine Schnittstelle: Cycles und EEVEE bauen ihn verschieden, und
    zwischen Versionen aendert er sich. Ausgewertet wird er drueben in FrameFlip,
    und zwar defensiv - hier wird er nur durchgereicht.
    """
    if _job["id"] is None or not isinstance(text, str):
        return

    moment = bridge.now()
    if moment - _job["last_stats"] < STATS_INTERVAL:
        return

    _job["last_stats"] = moment

    debug.log("render_stats %r" % text)

    bridge.sender.send({"type": "stats", "job": _job["id"], "text": text})


@persistent
def on_render_complete(scene, *_args):
    debug.log("render_complete")
    bridge.sender.send({"type": "done", "job": _job["id"]})
    _job["id"] = None


@persistent
def on_render_cancel(scene, *_args):
    debug.log("render_cancel")
    bridge.sender.send({"type": "cancel", "job": _job["id"]})
    _job["id"] = None


# ---------------------------------------------------------------------- An/Ab

#: Handler und ihre Liste. Als Paare, damit Ab- und Anmelden symmetrisch bleiben.
_BINDINGS = (
    ("render_init", on_render_init),
    ("render_pre", on_render_pre),
    ("render_write", on_render_write),
    ("render_stats", on_render_stats),
    ("render_complete", on_render_complete),
    ("render_cancel", on_render_cancel),
)


def register():
    unregister()        # doppelte Registrierung nach einem Reload vermeiden

    debug.log("Handler angemeldet")

    for name, function in _BINDINGS:
        getattr(bpy.app.handlers, name).append(function)


def unregister():
    for name, function in _BINDINGS:
        handlers = getattr(bpy.app.handlers, name, None)
        if handlers is None:
            continue

        # Nach einem Reload des Addons ist die alte Funktion eine ANDERE mit
        # gleichem Namen. Deshalb ueber den Namen vergleichen, nicht ueber Identitaet.
        for existing in list(handlers):
            if getattr(existing, "__name__", None) == function.__name__:
                handlers.remove(existing)

    _job["id"] = None
