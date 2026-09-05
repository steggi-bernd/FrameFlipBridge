# SPDX-License-Identifier: GPL-3.0-or-later
"""FrameFlip Bridge - meldet laufende Renders an FrameFlip.

Der Addon selbst tut absichtlich wenig: Er haengt sich an Blenders
Render-Handler und reicht weiter, was nur Blender weiss - welcher Frame gerade
laeuft, welche Datei geschrieben wurde, was im Statustext steht. Alles ueber den
Rechner misst FrameFlip, das ohnehin dauerhaft laeuft.

Diese Aufteilung ist kein Zufall. Sie haelt den Addon frei von Fremdpaketen, frei
von Netzwerkcode und frei von Geheimnissen: Gesprochen wird nur mit dem eigenen
Rechner ueber 127.0.0.1. Der Kopplungsschluessel fuers Handy bleibt drueben bei
FrameFlip - Blender speichert Passwoerter in seinen Addon-Einstellungen im
Klartext, dort haette er nichts verloren.
"""

bl_info = {
    "name": "FrameFlip Bridge",
    "author": "Bernd Steckmeister",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "Properties → Output → FrameFlip",
    "description": "Meldet laufende Renders an FrameFlip",
    "category": "Render",
}

import bpy

from . import bridge, handlers, ui


def register():
    ui.register()
    handlers.register()
    bridge.sender.start()


def unregister():
    handlers.unregister()
    bridge.sender.stop()
    ui.unregister()
