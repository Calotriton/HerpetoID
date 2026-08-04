---
layout: page
title: How it works
subtitle: Photo-identification, from a folder of field images to a catalogue of known individuals.
permalink: /how-it-works/
description: >-
  The HerpetoID workflow — import, mark the pattern, search the catalogue, confirm the match — and
  the plugin architecture that lets it grow to new species and new algorithms.
---

## The idea

Many animals carry a pattern that is as individual as a fingerprint and stable over years: the
ventral spots of a Pyrenean brook newt (*Calotriton asper*), the belly markings of a toad, the flank
blotches of a salamander. If you can photograph it, you can recognise the animal again — without
tags, clipping, or handling beyond the photograph itself.

Doing that by eye works until the catalogue reaches a few dozen individuals. Past that, every new
photograph means comparing against everything you have already recorded. HerpetoID does the
comparing, and leaves the deciding to you.

## The workflow

### 1. Create a project

A project is a single self-contained folder holding the database, the images, the computed
descriptors and the metadata. It is portable: copy it to an external drive, back it up, or hand the
whole thing to a colleague and they have everything.

### 2. Import a survey

Add the photographs from a session. Capture dates, and any location data the camera recorded, are
read from the image metadata so you are not retyping what the file already knows.

### 3. Mark the pattern

Outline the region of interest — the part of the animal that carries the markings. Which region
that is, and how it should be normalised and cleaned up before matching, is defined by the species
module, not hard-coded into the application.

### 4. Search the catalogue

The matching algorithm compares the pattern against every individual already in the project and
returns a **ranked shortlist** of candidates, each with a similarity score.

### 5. Confirm or reject

This is the part deliberately left to a human. Candidates are shown side by side with the query
image so you can judge the evidence yourself. Confirm a recapture and the observation is filed under
that individual; reject them all and you register a new one.

### 6. Export

Observations, individuals, capture histories and measurements export for analysis in the tools you
already use for mark–recapture.

> **Human-in-the-loop by design.** HerpetoID proposes; the scientist decides. A false match that
> nobody checked is worse than no match at all, so the software never confirms an identification on
> its own.

## What makes it extensible

HerpetoID is built as three layers, with all dependencies pointing inward to the core:

| Layer | What it does |
|---|---|
| **Core** | Projects, database, images, search, exports, statistics, the plugin registry and the identification pipeline. Contains no species-specific and no algorithm-specific logic. |
| **Species modules** | One plugin per taxon: which region to use, how to preprocess it, what fields to record, how to validate them, which algorithms it works with. |
| **Identification algorithms** | Reusable, species-agnostic matchers. Drop-in installable, and shared across every species. |

The consequence that matters in practice: **the application hard-codes no observation fields.** A
species module declares what it measures, and the core builds the data-entry forms, the comparison
panels, the statistics dashboards and the exports from that declaration. Adding a new animal does
not mean modifying — or re-testing — the core.

### Adding a species

A species module declares its species profile, its observation fields, its region of interest, its
preprocessing and the algorithms it is compatible with. It emits plain declarative data, never
interface code, which is why a module written today keeps working as the application's own
interface evolves.

### Adding an algorithm

Matchers are species-agnostic: implement feature extraction and comparison, register the plugin, and
every species module that declares it compatible can use it. Classic keypoint matchers (ORB, SIFT)
come first; learned approaches such as SuperPoint and DINOv2 embeddings are on the roadmap.

Both kinds of plugin can be installed as a Python package or simply dropped into the `plugins/`
folder next to the application. Developer documentation lives in the
[repository]({{ site.github_repo_url }}#authoring-plugins).

## Your data stays yours

HerpetoID runs entirely offline. There is no account, no cloud service, and no telemetry — your
photographs and locality data never leave your machine. Sensitive site coordinates for protected
species are a real concern in herpetology, and the safest design is the one where the data never
travels.

## Current status

HerpetoID is in **early development** and under active work. The architecture and the core workflow
are in place; packaged releases and additional species modules are being prepared. Progress is
announced on the [news page]({{ '/news/' | relative_url }}), and the full source is
[on GitHub]({{ site.github_repo_url }}).
