# Identification

The **Identification** tab is where you match a query observation against the rest of the catalog.
It has two modes, switched with the buttons at the top left:

## Identify mode

1. Select a **query observation** and an **algorithm** (e.g. ORB).
2. Click **Identify**. HerpetoID preprocesses the images, extracts features, and ranks the other
   observations of the same species by similarity.
3. The ranked candidates appear as **Top matches** cards — each with its **similarity score**
   (1.0 = most similar) and the ROI crop. Select a card to see the **match evidence**: the two
   normalized patterns side by side with the matched spots joined by colored lines, plus inlier
   counts. Each pattern sits in its own panel, named underneath — *Query* on the left, the
   *Candidate* on the right — so there is never any doubt which is which. Use the overlay controls
   to hide lines/points, limit how many are drawn, or fade them.
4. Click **Show more candidates** to extend the ranking further down the catalog.

Captures are shown the way up you left them on the Observations tab (see *Adding Observations* →
*Turning a capture the right way up*), regions included — so an animal you turned upright is upright
here too, and in the match evidence.

You can also turn a capture **from here**: the **⟲ ⟳** buttons in the corner of the *Query
observation* image do exactly what the editor's do — the turn is stored with the capture, the marked
region follows it, and every other view shows the new orientation. If candidates are already on
screen, the ranking is re-run so the match evidence matches the pictures beside it.

### Seeing the whole photograph

Both the match evidence and the ROI crops show *fragments* — the marked region, normalized. When the
pose or the framing is what settles a doubtful match, **right-click** either the match evidence or a
ROI crop and choose **Show full image**. A window opens with the whole photograph, the marked region
outlined, and the usual zoom (mouse wheel) and pan (click-drag). It is not modal, so you can leave it
open beside the comparison while you decide. On the match evidence the menu offers both sides.

## Compare A/B mode

Answers the focused one-vs-one question: "are these two captures the same individual?" Pick two
observations and press **Compare** to see the same match-evidence view for that single pair.

## Making a decision

The software only *proposes* candidates — you decide. **Individuals are only created here**: a code
typed in the Observations editor stays *pending* (shown as "CA-001 ?") until you confirm it.

- **Confirm SAME individual as match** — links the query and the selected candidate to the same
  individual (creating a new individual record if needed).
- **Mark query as NEW individual** — creates a fresh individual for the query when it matches
  nothing, reusing the pending code you typed in the editor (or auto-generating one).

The second button changes to say what it will actually do. If the query is **already** a cataloged
individual — you are re-assessing it, say after changing the species — it reads **Not a recapture —
keep CA-001**: there is no new individual to create, and the verdict keeps the identity and code it
already has. To give it a *different* identity instead, edit the individual code on the Observations
tab.

After every decision the query moves on to the **next capture that has not been assessed yet**, so a
season is worked through in one pass rather than starting from the top each time. It wraps around,
and tells you when every marked capture has been through identification.

Confirmed individuals appear on the **Individuals** tab, and recaptures feed the **Statistics**.

## About the ORB algorithm

ORB detects distinctive keypoints and matches them between two images (with a ratio test). It then
checks which matches agree on one way the animal could have moved between the photographs: shifted,
turned, and closer or further away (a RANSAC similarity transform). The score **counts the matches
that agree**. A handful agree by chance even between different animals, so those earn nothing, and
each further agreeing match adds evidence.

The colours on the score were calibrated on real fire-salamander photographs verified by eye: 82
recaptures, and 78 pairs of *different* animals that had looked alike to a matcher.

- **Green** (0.5 and above, about eight agreeing matches): reached by two thirds of the recaptures and
  by 1% of the different animals.
- **Amber** (0.25 and above, about six): reached by 87% of the recaptures and 9% of the different
  animals.

Treat green as a strong lead and amber as worth a look, never as proof. The calibration comes from
the fire salamander, so for other species the colours are only a starting point.

The algorithm never sees your photograph directly: the **species module** turns the region you marked
into a normalized pattern image first, and that is what gets matched. Both modules that ship with
HerpetoID throw the lighting away at this step — uneven torchlight and shadows vary slowly across a
photograph, a spot does not — and each reads its pattern from the property that carries it: brightness
for the brook newt's dark belly spots, colour for the fire salamander's yellow. Scores from different
species are therefore not comparable with each other; what matters is the ranking within one query.
