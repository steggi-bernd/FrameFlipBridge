"""
Das Ergebnis eines Einzelbild-Renders auf die Platte bekommen.

Bei einer Animation schreibt Blender jeden Frame selbst, und das Addon meldet nur
den Pfad. Bei einem Einzelbild (F12) schreibt Blender gar nichts: Das Bild liegt
als ``Render Result`` im Speicher und ist nirgends zwischengespeichert. Wer es
sehen will, muss es speichern - sonst gibt es nichts anzuzeigen.

Zwei Entscheidungen, die hier wichtiger sind als der Code selbst:

**Nur nach dem Render, nie waehrend.** Aufgerufen wird das aus ``render_complete``,
also wenn Blender fertig ist. Der Grund ist, dass das Speichern die
Ausgabeeinstellungen der Szene kurz umstellen muss - anders kommt man an ein JPEG
nicht heran, ``save_render`` benutzt immer die Einstellungen einer Szene. Das
mitten in einem laufenden Render zu tun waere leichtfertig: Die naechsten Frames
schrieben womoeglich im falschen Format.

**Nur, wenn nichts geschrieben wurde.** Hat Blender schon Dateien abgelegt, gibt es
nichts zu retten - dann kennt FrameFlip die Pfade ohnehin.
"""

import os
import tempfile

import bpy

from . import debug


#: Das Bild, in dem Blender das Ergebnis haelt. Der Name ist fest.
RESULT = "Render Result"

#: Klein genug fuers Handy, gross genug zum Hineinzoomen.
QUALITY = 85


def _target():
    """Ein fester Pfad je Blender-Sitzung, damit sich nichts ansammelt."""
    return os.path.join(tempfile.gettempdir(), "frameflip-still-%d.jpg" % os.getpid())


def save():
    """
    Speichert das Renderergebnis als JPEG und gibt den Pfad zurueck - oder None.

    None ist der Normalfall und kein Fehler: kein Ergebnis im Speicher, keine
    Schreibrechte, ein Format, das nicht geht. Ein Vorschaubild ist nichts, wofuer
    irgendetwas anderes schiefgehen darf.
    """
    image = bpy.data.images.get(RESULT)

    if image is None:
        debug.log("still: kein Render Result im Speicher")
        return None

    scene = bpy.context.scene

    if scene is None:
        return None

    settings = scene.render.image_settings

    # Der Bestand wird gemerkt und in jedem Fall zurueckgesetzt. Bliebe hier JPEG
    # stehen, schriebe der naechste Render des Benutzers im falschen Format - ein
    # Schaden, der die Vorschau bei weitem nicht wert waere.
    before = (
        settings.file_format,
        settings.color_mode,
        settings.quality,
    )

    path = _target()

    try:
        settings.file_format = "JPEG"

        # JPEG kann kein Alpha. Ohne diese Zeile scheitert das Speichern bei jeder
        # Szene, die auf RGBA steht - und das ist die Voreinstellung fuer Film.
        settings.color_mode = "RGB"
        settings.quality = QUALITY

        image.save_render(filepath=path, scene=scene)

        debug.log("still: gespeichert nach %s" % path)
        return path

    except (RuntimeError, OSError, ValueError, AttributeError) as problem:
        debug.log("still: ging nicht (%s)" % problem)
        return None

    finally:
        try:
            settings.file_format, settings.color_mode, settings.quality = before
        except (AttributeError, TypeError) as problem:
            # Sollte nie passieren. Wenn doch, muss es im Protokoll stehen - die
            # Ausgabeeinstellungen des Benutzers sind dann veraendert.
            debug.log("still: Einstellungen NICHT zurueckgesetzt (%s)" % problem)
