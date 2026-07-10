# Adding Observations

Open **Add Observations** (toolbar, or File → Add Observations…, Ctrl+I) with a project open:

1. Choose the **species** from the drop-down (species come from the installed species modules).
2. Enter the **observer** name (required before importing).
3. Click **Select images…** and pick one or more image files. They are only *staged* — shown in the
   "Selected for import" strip — and nothing is added to the project yet.
4. Click **Import N image(s)** to confirm. Closing the window without pressing Import imports nothing.

Each imported image becomes a new **observation**. Images are copied into the project's `images/`
folder (named by content hash, so the same file is never stored twice), and a thumbnail is generated.
Imported images appear in the gallery below the controls.

## Tips

- Supported formats: PNG, JPEG, TIFF, BMP.
- Image orientation is corrected automatically from EXIF metadata.
- Review imported observations on the **Observations** tab, where you can click a row to view the full
  image with zoom (mouse wheel) and pan (click-drag).
