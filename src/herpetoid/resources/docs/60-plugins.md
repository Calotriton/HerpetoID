# Plugins

HerpetoID is a platform. Two kinds of plugin extend it:

- **Species Modules** — one per taxon. A module declares the region of interest, the preprocessing, the
  observation fields, the species profile, the compatible algorithms, and its statistics.
- **Identification Algorithms** — reusable and species-agnostic (ORB today; SuperPoint, DINOv2 and CNN
  embeddings can be added later). Any algorithm can be used by any compatible species.

The **Plugins** tab lists everything currently installed, with its version and where it was loaded from.

## Installing plugins

Plugins are discovered two ways:

1. **Pip-installed packages** that register a HerpetoID entry point.
2. **Drop-in folder** — Python plugin files placed in your user `plugins/` directory are loaded at
   startup. A plugin that fails to load is skipped (and logged), never preventing the app from starting.

> **Install plugins only from sources you trust.** A plugin is a Python program: HerpetoID runs it at
> startup with your user privileges, so it can do anything you can do on your computer. Project
> bundles are different — they hold data only, and opening a bundle a colleague sent you never
> installs or runs a plugin.

Developers: validate a new plugin against the reusable conformance suites shipped in
`herpetoid.testing` before distributing it.
