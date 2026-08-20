# Adding Observations

Open **Add Observations** (the button next to the tabs, or File → Add Observations…, Ctrl+I) with a
project open:

1. Choose the **species** from the drop-down (species come from the installed species modules).
2. Enter the **observer** name (required before importing).
3. Click **Select images…** and pick one or more image files. They are only *staged* — shown in the
   "Selected for import" strip — and nothing is added to the project yet.
4. Click **Import N image(s)** to confirm. Closing the window without pressing Import imports nothing.

Each imported image becomes a new **observation**. Images are copied into the project's `images/`
folder (named by content hash, so the same file is never stored twice), and a thumbnail is generated.
Imported images appear in the gallery below the controls.

## Marking the pattern region

On the **Observations** tab, select a capture and mark the region that carries the pattern — this is
what the matcher actually compares. The tool follows the species: some species are marked with a box,
others (both species that ship with HerpetoID) with a polygon, where you click each point,
right-click to undo the last one and double-click to close the shape. The line under the image tells
you what that species expects.

Mark the pattern itself, not the whole animal: a polygon that follows the belly or the back, without
much of the hand or the substrate inside it, gives the matcher less to be distracted by.

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
