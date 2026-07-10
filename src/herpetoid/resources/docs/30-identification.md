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
   counts. Use the overlay controls to hide lines/points, limit how many are drawn, or fade them.
4. Click **Show more candidates** to extend the ranking further down the catalog.

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

Confirmed individuals appear on the **Individuals** tab, and recaptures feed the **Statistics**.

## About the ORB algorithm

ORB detects distinctive keypoints, matches them between two images (with a ratio test), and verifies the
match geometrically (RANSAC homography). The score combines the number of verified inliers, the inlier
ratio, and the geometric plausibility of the match.
