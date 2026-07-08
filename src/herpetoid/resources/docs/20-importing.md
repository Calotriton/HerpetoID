# Importing Images

On the **Import** tab (with a project open):

1. Choose the **species** from the drop-down (species come from the installed species modules).
2. Optionally enter an **observer** name.
3. Click **Add Images…** and select one or more image files.

Each image becomes a new **observation**. Images are copied into the project's `images/` folder (named
by content hash, so the same file is never stored twice), and a thumbnail is generated. Imported images
appear in the gallery below the controls.

## Tips

- Supported formats: PNG, JPEG, TIFF, BMP.
- Image orientation is corrected automatically from EXIF metadata.
- Review imported observations on the **Observations** tab, where you can click a row to view the full
  image with zoom (mouse wheel) and pan (click-drag).
