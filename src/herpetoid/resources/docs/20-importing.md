# Adding Observations

Open **Add Observations** (the button next to the tabs, or File → Add Observations…, Ctrl+I) with a
project open:

1. Choose the **species** from the drop-down (species come from the installed species modules).
   Nothing is chosen for you: the list opens on *— Select a species —* and Import stays disabled
   until you pick one. Once a project holds exactly one species, later imports open on it.
2. Enter the **observer** name (required before importing).
3. Add the photographs. Either:
   - **Select images…** — pick one or more individual image files; or
   - **Select folder…** — pick one folder and stage *every* image inside it **and all of its
     subfolders**. A card dump organised as `2023-07-15 Riu Aigues/CAM1/…`, one folder per site,
     day or camera, goes in as a single selection.

   Either way the files are only *staged* — shown in the "Selected for import" strip — and nothing is
   added to the project yet. Selecting the same file twice never stages it twice.
4. Click **Import N image(s)** to confirm. Closing the window without pressing Import imports nothing.

Each imported image becomes a new **observation**. Images are copied into the project's `images/`
folder (named by content hash, so the same file is never stored twice), and a thumbnail is generated.
Imported images appear in the gallery below the controls.

## The date is filled in for you

At import, each observation's **Date** field is filled in from two sources, in this order:

1. **The path** — the file's own name first, then the folders above it, nearest first (up to three
   levels). Recognised spellings: `2023-07-15`, `15-07-2023`, `20230715`, `15072023`, `15-jul-2023`,
   `15 julio 2023`, and the same with `_` or `.` instead of `-`.
2. **The camera's EXIF metadata** — the moment the shutter fired (`DateTimeOriginal`). This is what
   covers an untouched card dump, where `DCIM/100CANON/DSC_0031.JPG` says nothing at all.

The path is used first because it is the one *you* chose: a folder you named `2023-07-15 Riu Aigues`
is a deliberate statement about that session, whereas a camera whose clock was never set after a
battery change reports its dates with complete confidence and complete inaccuracy.

Hover a staged thumbnail before importing to see the date that was found and where it came from.

A purely numeric date such as `05-07-2023` is read **day-first** (5 July), matching the DD/MM/YYYY
format HerpetoID shows throughout. Anything that isn't a real calendar date is ignored rather than
guessed at — a sequence number like `IMG_1234` or `DSC01234567`, or an EXIF stamp of `0000:00:00`,
leaves the Date field empty. You can always change the date on the **Observations** tab.

## The species matters — and can be changed later

The species you choose is not a label. It selects the **species module**, which decides three things:

- **Which fields you can record.** *Salamandra salamandra* adds total length and dorsal pattern type;
  *Calotriton asper* does not have them. A value recorded under one species that the other does not
  declare is kept in the project but stops being shown.
- **How the pattern is read.** The fire salamander module reads the *yellowness* of the dorsum; the
  brook newt module reads the *lightness* of the belly. Feeding photographs to the wrong one gives a
  matcher that works from the wrong signal.
- **What each capture is compared against.** Identification only ranks a query against captures of
  the *same* species, and an individual belongs to one species.

So it is worth getting right — and worth correcting rather than living with. **Project → Change
Species…**, or the **Change…** button beside *Species* on the Observations tab, moves observations
from one species to another. Photographs, marked regions and recorded values all carry across; only
the module interpreting them changes. You can move the whole project or a single capture.

An individual is the one thing that cannot simply follow, because it belongs to a species and its
code is unique within one. An individual whose captures *all* move comes across with them, code and
identity intact. If a capture would leave an individual behind — some of its captures move, some stay
— that capture is unlinked instead and keeps its code as a *pending* one, to re-confirm on the
Identification tab. A species left holding nothing is removed from the project.

Any identification you have already run should be run again afterwards: the ranking was produced by
the other module.

## Marking the pattern region

On the **Observations** tab, select a capture and mark the region that carries the pattern — this is
what the matcher actually compares. The tool follows the species: some species are marked with a box,
others (both species that ship with HerpetoID) with a polygon, where you click each point,
right-click to undo the last one and double-click to close the shape. The line under the image tells
you what that species expects.

Mark the pattern itself, not the whole animal: a polygon that follows the belly or the back, without
much of the hand or the substrate inside it, gives the matcher less to be distracted by.

### Turning a capture the right way up

The **⟲** and **⟳** buttons in the image's top-right corner turn the capture a quarter turn. The turn
is **kept with the capture**: it is stored in the project and every other screen — the Identification
tab, the match evidence, the catalog browser — shows the photograph the same way up, so two animals
photographed head-to-tail can be compared side by side. The marked region turns with the picture, and
so does a region you have drawn but not yet saved.

Turning changes nothing about the animal: an already-identified capture keeps its individual. The
photograph on disk is never rewritten either — the turn is recorded and applied when the image is
loaded, so the original file stays exactly as your camera wrote it. **⤢** just refits the view to the
window; to undo a turn, turn it back the other way.

## Tips

- Supported formats: PNG, JPEG, TIFF, BMP.
- Image orientation is corrected automatically from EXIF metadata.
- **Photograph in colour** where the pattern *is* a colour: the fire salamander module reads the
  yellow directly, and a greyscale photograph still works but less reliably.
- **Even light beats bright light.** Both modules discard slow changes in illumination, so a shadow
  across the animal is survivable — but a blown-out highlight on wet skin destroys the pattern
  underneath it, and nothing downstream can recover what the sensor never recorded. Wiping the animal
  or diffusing the flash does more for your match rates than any setting in this application.
- Review imported observations on the **Observations** tab, where you can click a row to view the full
  image with zoom (mouse wheel) and pan (click-drag).
