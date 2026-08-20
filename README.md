# HerpetoID

**A modular platform for non-invasive individual identification of wildlife from natural body
patterns.**

HerpetoID is a production-quality desktop application that helps ecologists identify and re-identify
individual animals from photographs of their unique natural markings (e.g. the ventral spot pattern of
the Pyrenean brook newt, *Calotriton asper*). It is designed as a **long-term scientific platform**,
not a single-purpose tool: new species and new matching algorithms are added as **plugins**, without
modifying the core.

**Website: <https://calotriton.github.io/HerpetoID/>** — what it does, how it works, and downloads.

> Status: early development. The desktop application, the plugin SDK and two species modules
> (*Calotriton asper*, *Salamandra salamandra*) work end to end; the layer boundaries below are
> enforced by the test suite.

## Species modules included

| Module | Pattern | Channel | Normalization |
|---|---|---|---|
| *Calotriton asper* (Pyrenean brook newt) | Ventral spots, polygon ROI | Lightness — the pattern *is* a lightness pattern | Band-pass |
| *Salamandra salamandra* (fire salamander) | Dorsal yellow on black, polygon ROI | CIE Lab **b\*** yellowness | Band-pass |

Both modules face the same problem — animals photographed wet, at night, under a torch — and both
solve it the same way: the illumination varies slowly across a frame while the pattern does not, so a
**band-pass** separates them, with widths expressed as fractions of the marked region so the filter
follows the animal's size rather than the photographer's distance. Replacing global histogram
equalization with this took first-place matches from 26/40 to 40/40 for the newt and from 22/40 to
40/40 for the salamander under simulated field lighting.

What is genuinely species-specific is the **channel**: a fire salamander's yellow-on-black is a
higher-contrast signal in `b*` than in grey, which yields more repeatable keypoints, while a brook
newt's dark-on-pale belly has no chromatic axis to move to. That choice is worth a modest extra
margin, not the bulk of the improvement. All of these figures come from **synthetic** captures under
a modelled set of nuisances (the generators are in `tests/test_plugins.py`) — they compare recipes
against each other and are not validation against a real catalogue.

---

## Key ideas

Three independent layers, with dependencies pointing **inward** to the Core:

| Layer | Responsibility | Depends on |
|---|---|---|
| **Core** | GUI, projects, database, metadata, images, search, exports, settings, help, plugin registry, identification pipeline. Contains **no** species- or algorithm-specific logic. | — |
| **Species Modules** | Per-taxon plugins: ROI, preprocessing, observation fields, species profile, validation, compatible algorithms, visualization. **Never implement a generic algorithm.** | Core abstractions (`herpetoid.api`) |
| **Identification Algorithms** | Reusable, species-agnostic matchers (ORB, SIFT, and later SuperPoint / DINOv2 / CNN embeddings). Drop-in installable. | Core abstractions (`herpetoid.api`) |

The plugin SDK (`herpetoid.api`) is **Qt-free** — species modules and algorithms emit declarative data
(field schemas, ROI specs, visualization overlays), never GUI widgets. Core renders everything
generically, so it **hard-codes no observation fields** and auto-builds forms, comparison panels,
statistics dashboards and exports from what a species declares.

## Highlights

- **Offline-first**, portable **project bundles** (a self-contained folder: SQLite DB + images +
  descriptors + metadata).
- **Human-in-the-loop**: the software proposes ranked candidate matches; the scientist decides.
- **Generic, field-driven metadata & statistics** — future species get their own measurements, means,
  ratios and growth curves with no core changes.
- **Extensible** via Python entry points *and* a drop-in `plugins/` folder.

## Installation (development)

Requires **Python 3.12+** and **git**.

```powershell
git clone https://github.com/Calotriton/HerpetoID.git
cd HerpetoID
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Quick start

```powershell
# launch the desktop application
herpetoid

# run the checks CI runs
pytest
ruff check .
mypy
```

## Authoring plugins

- **A new algorithm**: subclass `herpetoid.api.IdentificationAlgorithm`, implement `descriptor`,
  `extract_features`, `compare` (the rest have sensible defaults), and register it under the
  `herpetoid.algorithms` entry-point group — or drop it into the user `plugins/` folder.
- **A new species**: subclass `herpetoid.api.SpeciesModule`, implement `descriptor`,
  `define_species_profile`, `define_observation_fields`, `preprocess`, `compatible_algorithms`, and
  register it under `herpetoid.species_modules`.

Validate any plugin against the reusable **conformance suites** shipped in `herpetoid.testing` (see
`tests/test_conformance_selftest.py` for how to call them).

> Plugins are ordinary Python and run with your privileges — install them only from sources you
> trust. See [`SECURITY.md`](SECURITY.md) for the full trust model.

## Security

HerpetoID is offline and makes no network calls, but it opens files that may come from other people:
project bundles are designed to be shared. [`SECURITY.md`](SECURITY.md) documents what is trusted,
what is not, and how to report a vulnerability.

## License

MIT — see [`LICENSE`](LICENSE).
