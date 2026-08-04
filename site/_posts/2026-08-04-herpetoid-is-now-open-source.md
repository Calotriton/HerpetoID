---
title: "HerpetoID is now open source"
date: 2026-08-04
tag: Project
---

The HerpetoID repository is public, and this site is where the project will be documented from now
on: what the software does, how to get it, and what changes with each release.

**What HerpetoID is.** A desktop application for photo-identification of individual amphibians and
reptiles — the ventral spots of a Pyrenean brook newt, and in time the belly of a crested newt, the
head shields of a viper, the plastron of a tortoise. It proposes ranked candidate matches from your
own catalogue; you confirm them. Nothing permanent is done to the animal.

**Where it stands.** Early development. The three-layer architecture is in place — a core that knows
nothing about any particular species, species modules that declare their own fields and regions of
interest, and reusable matching algorithms — along with the desktop interface and the Windows
packaging setup.

**What is next.** The first packaged Windows build, so the software can be used without installing
Python. When it is ready it will appear on the [download page]({{ '/download/' | relative_url }})
and be announced here.

If you work on herpetofauna photo-ID and something here would be useful in your own study, the
[source is on GitHub]({{ site.github_repo_url }}) under the MIT license, and
[issues]({{ site.github_repo_url }}/issues) are open. If your study species is not covered yet,
that is a species module waiting to be written — and a good reason to get in touch.
