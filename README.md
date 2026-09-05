# FrameFlip Bridge

**Blender add-on that reports running renders to
[FrameFlip](https://github.com/steggi-bernd/FrameFlip).**

Installed once, it reports every render of that Blender instance — nothing needs to
be switched on anywhere. FrameFlip then shows progress, the sample counter, time per
frame and the machine's load, and loads every finished frame into the preview as
soon as it is written.

## What it does — and deliberately does not

The add-on is thin on purpose. It passes on **what only Blender knows**:

* which job starts — scene, engine, frame range, resolution, output path
* which frame is running and which file was written
* Blender's own progress text, unparsed

Everything about the machine — CPU, memory, GPU — FrameFlip measures itself. It runs
in the tray anyway and is in a better position to do it.

That split is not convenience. It keeps the add-on free of **third-party packages**,
of **network code** and of **secrets**:

* Python's standard library only. Nothing to install, nothing to update.
* It talks to `127.0.0.1` exclusively — the local machine.
* The pairing key for the phone stays with FrameFlip. Blender stores add-on
  preference passwords in plain text; it has no business being there.

**No image data** crosses the bridge. The add-on reports a path, FrameFlip reads the
file itself — that costs Blender nothing.

## Installation

Blender 4.2 and newer:

1. Pack `frameflip_bridge` as a ZIP
2. *Edit → Preferences → Get Extensions → Install from Disk*

Older versions (3.6 to 4.1): the same ZIP via *Add-ons → Install*.

Whether it works is shown in *Properties → Output → FrameFlip*: "Connected",
"Connecting …" or "FrameFlip is not running".

## The principle the whole design follows

> **Handlers must do nothing except put an entry on a queue.**

Blender's render handlers run on the main thread. Anything that waits there stalls
the render — a socket write on a bad connection costs seconds **per frame**. So the
handler only enqueues, and a thread of its own carries it away.

The queue never blocks either. If FrameFlip is not running, the oldest messages fall
out. A lost intermediate reading is meaningless; a stalled render is not.

## What Blender does not offer

Two limits, verified against the source and documented with references in
[FrameFlip's technical note](https://github.com/steggi-bernd/FrameFlip/blob/main/docs/Blender-Bridge.md):

**A running render cannot be cancelled.** There is only `RENDER_OT_render`; the
animation loop breaks solely on the global `G.is_break` flag, which has no Python
binding. Lowering `frame_end` afterwards does not help either — the end value is
captured when the loop starts.

**The progress text is engine- and version-specific.** Cycles and EEVEE write it
differently, and it changes between versions. So it is parsed defensively — over in
FrameFlip, not here — and no display depends on whether it can be read at all.

Both point towards running renders as a separate process. That is FrameFlip's job,
not this add-on's: it keeps running in the tray long after Blender is closed.

## Diagnostics

*Properties → Output → FrameFlip → Diagnostics* shows what the add-on is doing and
writes the same lines to a file.

Started from Steam or a shortcut, Blender has no console window — `print` would go
nowhere, and an add-on that silently reports nothing is indistinguishable from a
broken one.

It is built to be removed later: one module with a single function facing outward,
one separate panel section, one-line calls at the events. Delete `debug.py`, remove
the calls, done.

## Tests

```bash
python tests/test_bridge.py
```

Runs **without Blender**. `bridge.py` imports no `bpy` — which is exactly why the
part that matters can be tested: the connection, the queue, and the behaviour when
nothing is listening. That the test starts at all is the proof of that separation.

## Language

Interface texts are English. The comments in the source are German — that is where
the reasoning behind each decision lives, and translating it would risk losing
exactly the part worth keeping.

## Licence

GPL-3.0-or-later. A Blender add-on links `bpy` and therefore has to be GPL.
FrameFlip itself is MIT and stays that way — the two talk to each other over a
socket, not inside a shared process.
