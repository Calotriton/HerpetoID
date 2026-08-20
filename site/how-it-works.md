---
layout: page
title: How it works
subtitle: Photo-identification for herpetofauna, from a folder of field images to a catalogue of known individuals.
permalink: /how-it-works/
description: >-
  The HerpetoID workflow — import, mark the pattern, search the catalogue, confirm the match — and
  the plugin architecture that lets it grow to new amphibian and reptile species and new algorithms.
---

## The idea

Many amphibians and reptiles carry a pattern that is as individual as a fingerprint: the ventral
spots of a Pyrenean brook newt (*Calotriton asper*), the belly pattern of a great crested newt, the
yellow dorsal blotches of a fire salamander, the head shields of an adder, the scute pattern on a
tortoise's plastron. If you can photograph it, you can recognise the animal again.

That matters more for herps than for most groups. They are small, they shed their skin, many are
strictly protected, and the classic marking methods all cost the animal something — toe-clipping is
invasive and ethically contested, branding is crude, PIT tags are expensive and mean handling every
individual. Photo-identification replaces the mark, not the survey: you still capture and record as
your protocol requires, but nothing permanent is done to the animal.

Doing the matching by eye works until the catalogue reaches a few dozen individuals. Past that,
every new photograph means comparing against everything you have already recorded. HerpetoID does
the comparing, and leaves the deciding to you.

## What carries the pattern

| Group | Where to look |
|---|---|
| **Newts & salamanders** | Ventral spot and blotch patterns; dorsal yellow in *Salamandra*. The best-established photo-ID group. |
| **Frogs & toads** | Dorsal markings, flank and thigh patterning; the iris in some species. |
| **Snakes** | Head scale arrangement, dorsal zigzags and blotches, ventral scale markings. |
| **Lizards** | Dorsal and lateral spot rows, ocelli, throat and gular patterning. |
| **Tortoises & terrapins** | Carapace and plastron scute patterns, head and neck markings. |

None of these are built into the application. Each is declared by a species module.

## The workflow

### 1. Create a project

A project is a single self-contained folder holding the database, the images, the computed
descriptors and the metadata. It is portable: copy it to an external drive, back it up, or hand the
whole thing to a colleague and they have everything.

### 2. Import a survey

Add the photographs from a session — a night at the pond, a transect, a round of refugia checks.
Capture dates, and any location data the camera recorded, are read from the image metadata so you
are not retyping what the file already knows.

### 3. Mark the pattern

Outline the region of interest: the belly plate, the head shields, the plastron. Which region that
is, and how it should be normalised and cleaned up before matching, is defined by the species
module, not hard-coded into the application.

How the pattern is read matters as much as where it is. Both modules that ship with HerpetoID discard
the lighting before matching — illumination changes slowly across a photograph while a spot or a
blotch does not — and then read the pattern from whichever property carries it: brightness for the
brook newt's dark belly spots, colour for the fire salamander's yellow on black.

### 4. Search the catalogue

The matching algorithm compares the pattern against every individual already in the project and
returns a **ranked shortlist** of candidates, each with a similarity score.

### 5. Confirm or reject

This is the part deliberately left to a human. Candidates are shown side by side with the query
image so you can judge the evidence yourself. Confirm a recapture and the observation is filed under
that individual; reject them all and you register a new one.

### 6. Export

Observations, individuals, capture histories and measurements export for analysis in the tools you
already use — survival and abundance models, occupancy, growth curves.

> **Human-in-the-loop by design.** HerpetoID proposes; the herpetologist decides. A false match that
> nobody checked quietly corrupts a capture history, so the software never confirms an
> identification on its own.

## Two things worth knowing before you start

**Patterns are stable, but not always.** In many species the pattern settles after metamorphosis and
holds for years — this is what makes the method work. Growth can still change it, and juveniles are
the least reliable case. Whether patterns are stable enough over your study's timespan is a question
about your species, and worth validating rather than assuming.

**Consistent photographs pay for themselves.** The more standardised the view, the distance and the
lighting, the better any matcher performs. A photo tank or a flat plate, a fixed camera position and
a scale in frame will do more for your match rates than any change of algorithm.

## Biosecurity

Chytrid (*Bd*), *Bsal*, ranavirus and snake fungal disease travel between sites on hands, nets, boots
and photo tanks. Photo-identification does not remove the need for disinfection protocols — you are
still capturing animals — but it does remove the handling that marking would have added, and it
removes the repeat handling of recaptures for re-marking. Follow your national protocol; this is one
fewer contact per animal.

## What makes it extensible

HerpetoID is built as three layers, with all dependencies pointing inward to the core:

| Layer | What it does |
|---|---|
| **Core** | Projects, database, images, search, exports, statistics, the plugin registry and the identification pipeline. Contains no species-specific and no algorithm-specific logic. |
| **Species modules** | One plugin per taxon: which region to use, how to preprocess it, what fields to record, how to validate them, which algorithms it works with. |
| **Identification algorithms** | Reusable, species-agnostic matchers. Drop-in installable, and shared across every species. |

The consequence that matters in practice: **the application hard-codes no observation fields.** A
newt module recording snout–vent length and a tortoise module recording carapace length are the same
kind of object to the core. Each declares what it measures, and the core builds the data-entry
forms, the comparison panels, the statistics dashboards and the exports from that declaration.
Adding a new species does not mean modifying — or re-testing — the core.

### Adding a species

A species module declares its species profile, its observation fields, its region of interest, its
preprocessing and the algorithms it is compatible with. It emits plain declarative data, never
interface code, which is why a module written today keeps working as the application's own
interface evolves.

### Adding an algorithm

Matchers are species-agnostic: implement feature extraction and comparison, register the plugin, and
every species module that declares it compatible can use it — a matcher written for newt bellies is
available to tortoise plastrons for free. Classic keypoint matchers (ORB, SIFT) come first; learned
approaches such as SuperPoint and DINOv2 embeddings are on the roadmap.

Both kinds of plugin can be installed as a Python package or simply dropped into the `plugins/`
folder next to the application. Developer documentation lives in the
[repository]({{ site.github_repo_url }}#authoring-plugins).

## Your data stays yours

HerpetoID runs entirely offline. There is no account, no cloud service, and no telemetry — your
photographs and locality data never leave your machine. For herpetofauna this is not a detail:
precise localities for persecuted snakes, collected tortoises and protected amphibians are exactly
the data you do not want on someone else's server.

## Current status

HerpetoID is in **early development** and under active work. The architecture and the core workflow
are in place, and two species modules ship with the application: the Pyrenean brook newt
(*Calotriton asper*), matched on its ventral spots, and the fire salamander (*Salamandra
salamandra*), matched on the yellow pattern on its back. Packaged releases and further modules are
being prepared. Progress is announced on the [news page]({{ '/news/' | relative_url }}), and the full
source is [on GitHub]({{ site.github_repo_url }}).
