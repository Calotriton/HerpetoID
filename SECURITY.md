# Security

HerpetoID is an offline desktop application for field researchers. It has no server, no accounts and
no network calls: everything happens on the machine it runs on, against files the user chooses. The
security questions that matter here are therefore about **what a file you were sent can do to you**.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through
[GitHub Security Advisories](https://github.com/Calotriton/HerpetoID/security/advisories/new)
rather than opening a public issue. A first response should arrive within a few days.

## Trust model

### Project bundles are untrusted input

A project bundle is a portable folder (`project.db` + `images/` + `thumbnails/` + `descriptors/`) and
it is *meant* to be shared — mailed to a colleague, put on a USB stick, archived with a paper. That
makes every bundle you did not create yourself untrusted input, including the paths recorded inside
its database.

HerpetoID resolves **every** bundle-relative path through
`herpetoid.infrastructure.paths.resolve_in_bundle`, which rejects absolute paths, `..` traversal and
symlinks that leave the bundle. Without it, a hand-edited `project.db` could make the application read
files elsewhere on your disk and embed them in an exported PDF dossier. See `tests/test_security.py`.

Opening a bundle never executes code from it: bundles carry data only, and the database is read
through the SQLAlchemy ORM with bound parameters.

### Plugins are code, and run with your privileges

This is the one place where HerpetoID deliberately executes code it did not ship:

- Python packages that register a `herpetoid.species_modules` or `herpetoid.algorithms` entry point.
- Any `.py` file or package dropped into your user `plugins/` folder.

Both are imported at startup and run with your full user privileges. **Install plugins only from
sources you trust**, exactly as you would for any Python package. A plugin that fails to import is
logged and skipped rather than blocking startup, but a plugin that imports successfully is trusted
completely. Plugins are *not* carried inside project bundles — receiving a bundle never installs one.

### Images are untrusted input

Imported images are decoded by Pillow. HerpetoID checks an image's declared dimensions against a pixel
budget (`herpetoid.infrastructure.image_store`) **before** decoding, so an image header claiming
absurd dimensions is refused instead of exhausting memory. Files that fail to decode are skipped with
a message and never abort a batch import.

### Exports are opened in other programs

CSV and Excel exports contain free-text field data, and spreadsheets execute cells that begin with
`=`, `+`, `-` or `@`. Both spreadsheet exporters neutralize such cells (xlsx keeps the exact value and
tags it as text; CSV, which has no type system, gains a leading apostrophe). JSON export is left
byte-for-byte lossless because JSON is never formula-evaluated.

## Out of scope

- An attacker who already has code execution on the machine, or who can write to the HerpetoID
  installation or plugin folders.
- Malicious plugins installed by the user (see above — plugins are trusted by design).
- The project database itself is not encrypted. If your bundles contain sensitive location data for
  protected species, protect them with full-disk or archive encryption.
