# Packaging (Windows)

HerpetoID is packaged into a standalone Windows application with **PyInstaller**.

## Build

From the project root, in the activated virtual environment:

```powershell
pip install -e ".[dev]"          # includes pyinstaller
pyinstaller packaging/herpetoid.spec
```

The result is a one-folder application at `dist/HerpetoID/`, launched via
`dist/HerpetoID/HerpetoID.exe`. Zip that folder to distribute it — no Python install is required on the
target machine.

## What the spec does

- Bundles the offline Markdown manual (`herpetoid/resources/docs`).
- Copies the package metadata (`copy_metadata("herpetoid")`) so **entry-point plugin discovery** still
  works inside the frozen app.
- Collects the first-party plugin submodules (`herpetoid.plugins`), which are imported dynamically.
- Builds a windowed (no console) application.

## Notes

- Drop-in plugins from the user `plugins/` folder are still discovered at runtime by the packaged app.
- To reduce size, the build excludes `tkinter`. PySide6/Qt make up most of the bundle size.
