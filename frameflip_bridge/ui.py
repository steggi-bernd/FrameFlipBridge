# SPDX-License-Identifier: GPL-3.0-or-later
"""Die sichtbare Seite: ein Feld in den Ausgabe-Einstellungen.

Zwei Teile. Der obere ist der Dauerzustand und knapp gehalten -- einzustellen gibt
es nichts, Port und Token stehen in der Handschlagdatei, die FrameFlip schreibt.
Zu sehen sein muss nur, ob die Verbindung steht.

Der untere Teil ist die **Diagnose** und ausdruecklich zum spaeteren Entfernen
gedacht: Er zeigt den Mitschnitt aus ``debug.py``. Ueber Steam gestartet hat
Blender kein Konsolenfenster, ``print`` liefe also ins Leere -- und ein Addon, das
stillschweigend nichts meldet, ist von einem kaputten nicht zu unterscheiden.

Zum Entfernen: diesen unteren Abschnitt loeschen, ``debug.py`` mitsamt seinen
Aufrufen entfernen. Sonst haengt nichts daran.
"""

import os
import subprocess
import sys

import bpy

from . import bridge, debug


class FRAMEFLIP_PT_bridge(bpy.types.Panel):
    bl_label = "FrameFlip"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "output"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout

        if bridge.sender.connected:
            layout.label(text="Verbunden", icon="LINKED")
        elif bridge.read_handshake() is None:
            column = layout.column(align=True)
            column.label(text="FrameFlip läuft nicht", icon="UNLINKED")
            column.label(text="Im Tray starten – die Verbindung kommt von selbst.")
        else:
            layout.label(text="Verbinde …", icon="SORTTIME")

        if bridge.sender.dropped:
            layout.label(text="%d Meldungen verworfen" % bridge.sender.dropped,
                         icon="ERROR")

        layout.operator("frameflip.reconnect", icon="FILE_REFRESH")


# ---------------------------------------------------------------------- Diagnose


class FRAMEFLIP_PT_debug(bpy.types.Panel):
    """Zum spaeteren Entfernen gedacht - siehe Modulkopf."""

    bl_label = "Diagnose"
    bl_parent_id = "FRAMEFLIP_PT_bridge"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "output"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.prop(context.scene, "frameflip_debug", toggle=True,
                 text="Mitschnitt an" if debug.enabled else "Mitschnitt aus")
        row.operator("frameflip.open_log", text="", icon="TEXT")
        row.operator("frameflip.clear_log", text="", icon="TRASH")

        lines = debug.lines()

        if not lines:
            layout.label(text="Noch nichts aufgezeichnet.")
            return

        # Die letzten Zeilen, juengste unten - so liest man ein Protokoll.
        box = layout.box()
        column = box.column(align=True)

        for line in lines[-14:]:
            column.label(text=line)


class FRAMEFLIP_OT_reconnect(bpy.types.Operator):
    """Verbindung zu FrameFlip neu aufbauen"""

    bl_idname = "frameflip.reconnect"
    bl_label = "Neu verbinden"
    bl_options = {"REGISTER"}

    def execute(self, context):
        bridge.sender.stop()
        bridge.sender.start()

        debug.log("Verbindung von Hand neu aufgebaut")
        self.report({"INFO"}, "FrameFlip: Verbindung wird neu aufgebaut")
        return {"FINISHED"}


class FRAMEFLIP_OT_open_log(bpy.types.Operator):
    """Die Mitschnittdatei im Dateimanager zeigen"""

    bl_idname = "frameflip.open_log"
    bl_label = "Mitschnitt öffnen"
    bl_options = {"REGISTER"}

    def execute(self, context):
        path = debug.path()

        if not os.path.exists(path):
            self.report({"WARNING"}, "Noch kein Mitschnitt vorhanden")
            return {"CANCELLED"}

        try:
            if sys.platform == "win32":
                os.startfile(path)                                  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except OSError as error:
            self.report({"ERROR"}, "Konnte nicht geöffnet werden: %s" % error)
            return {"CANCELLED"}

        return {"FINISHED"}


class FRAMEFLIP_OT_clear_log(bpy.types.Operator):
    """Mitschnitt leeren"""

    bl_idname = "frameflip.clear_log"
    bl_label = "Mitschnitt leeren"
    bl_options = {"REGISTER"}

    def execute(self, context):
        debug.clear()
        return {"FINISHED"}


def _toggle_debug(self, context):
    debug.enabled = self.frameflip_debug


_CLASSES = (
    FRAMEFLIP_PT_bridge,
    FRAMEFLIP_PT_debug,
    FRAMEFLIP_OT_reconnect,
    FRAMEFLIP_OT_open_log,
    FRAMEFLIP_OT_clear_log,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Scene.frameflip_debug = bpy.props.BoolProperty(
        name="Mitschnitt",
        description="Ereignisse in eine Datei schreiben und hier anzeigen",
        default=debug.enabled,
        update=_toggle_debug,
    )


def unregister():
    if hasattr(bpy.types.Scene, "frameflip_debug"):
        del bpy.types.Scene.frameflip_debug

    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            # Beim Neuladen kann eine Klasse bereits weg sein.
            pass
