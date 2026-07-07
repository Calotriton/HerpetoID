# HerpetoID

**A modular platform for non-invasive individual identification of wildlife from natural body
patterns.**

HerpetoID is a production-quality desktop application that helps ecologists identify and re-identify
individual animals from photographs of their unique natural markings (e.g. the ventral spot pattern of
the Pyrenean brook newt, *Calotriton asper*). It is designed as a **long-term scientific platform**,
not a single-purpose tool: new species and new matching algorithms are added as **plugins**, without
modifying the core.

> Status: early development. See [`docs/architecture.md`](docs/architecture.md) for the design and the
> implementation plan for the roadmap.

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
# run the test suite
pytest

# launch the application (desktop GUI arrives in the GUI phase)
herpetoid
```

## Authoring plugins

- **A new algorithm**: subclass `herpetoid.api.IdentificationAlgorithm`, implement `descriptor`,
  `extract_features`, `compare` (the rest have sensible defaults), and register it under the
  `herpetoid.algorithms` entry-point group — or drop it into the user `plugins/` folder.
- **A new species**: subclass `herpetoid.api.SpeciesModule`, implement `descriptor`,
  `define_species_profile`, `define_observation_fields`, `preprocess`, `compatible_algorithms`, and
  register it under `herpetoid.species_modules`.

Validate any plugin against the reusable **conformance test suites** in `tests/conformance/`. See
[`docs/plugin-authoring.md`](docs/plugin-authoring.md).

## License

MIT — see [`LICENSE`](LICENSE).
