# SPDX-License-Identifier: GPL-3.0-or-later
"""Die sichtbare Seite: ein kleines Feld in den Ausgabe-Einstellungen.

Bewusst knapp. Der Addon hat nichts einzustellen -- Port und Token stehen in der
Handschlagdatei, die FrameFlip schreibt. Zu sehen sein muss nur eines: ob die
Verbindung steht. Ohne diese Auskunft sucht man bei einer stummen Anzeige an der
falschen Stelle.
"""

import bpy

from . import bridge


class FRAMEFLIP_PT_bridge(bpy.types.Panel):
    bl_label = "FrameFlip"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "output"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = False

        if bridge.sender.connected:
            row = layout.row()
            row.label(text="Verbunden", icon="LINKED")
            return

        if bridge.read_handshake() is None:
            column = layout.column(align=True)
            column.label(text="FrameFlip laeuft nicht", icon="UNLINKED")
            column.label(text="Im Tray starten, dann verbindet es sich von selbst.")
            return

        layout.label(text="Verbinde …", icon="SORTTIME")


class FRAMEFLIP_OT_reconnect(bpy.types.Operator):
    """Verbindung zu FrameFlip neu aufbauen"""

    bl_idname = "frameflip.reconnect"
    bl_label = "FrameFlip neu verbinden"
    bl_options = {"REGISTER"}

    def execute(self, context):
        bridge.sender.stop()
        bridge.sender.start()

        self.report({"INFO"}, "FrameFlip: Verbindung wird neu aufgebaut")
        return {"FINISHED"}


_CLASSES = (FRAMEFLIP_PT_bridge, FRAMEFLIP_OT_reconnect)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            # Beim Neuladen kann eine Klasse bereits weg sein.
            pass
