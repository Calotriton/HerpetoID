---
title: "Fire salamander module"
date: 2026-08-20
tag: Species module
---

HerpetoID now ships a second species module: **_Salamandra salamandra_**, the fire salamander,
identified from the yellow spots, blotches and stripes on its back. The pattern is set at
metamorphosis and stays with the animal for life, which is what makes it usable as a natural tag.

**It throws the lighting away before matching.** A fire salamander is usually photographed at night,
by torch or flash, often on wet skin, so no two captures of the same animal are lit alike. The module
exploits the fact that illumination changes *slowly* across a photograph while a blotch does not: it
keeps the pattern's own scale and subtracts the rest, handing the matcher the geometry of the pattern
rather than the geometry of the torch beam. The measurement that decided this was blunt — the same
synthetic captures, the same masks, the same ORB matcher, only the preprocessing differing: 40 of 40
correct first-place matches, against 22 of 40 for the histogram-equalization recipe HerpetoID used
before.

The same change went into the brook newt module in this release, and it matters just as much there:
that animal is lifted straight out of a stream, and its belly is every bit as wet and reflective.

**Colour is the smaller, species-specific part.** The module reads the pattern from the blue–yellow
axis of CIE Lab rather than from brightness, because yellow against black is a stronger signal than
light against dark and gives the matcher more to hold on to. It is worth a real but modest margin —
and, contrary to what is often assumed, it is *not* because colour is immune to lighting: measured
one nuisance at a time, the colour axis is if anything more sensitive to a warm flash than brightness
is. We would rather publish the smaller true claim than the larger tidy one.

The module also brings its own field sheet — snout–vent length, total length, weight, sex, life stage
and dorsal pattern type — and its own statistics, including body condition (Fulton's K) and a
breakdown of spotted versus striped animals. None of that is coded into the application: the module
declares it, and the forms, dashboards and exports follow. That is the whole point of the plugin
architecture, and this second module is the proof it holds.
