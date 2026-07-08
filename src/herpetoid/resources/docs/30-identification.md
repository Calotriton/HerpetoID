# Identification

The **Candidates** tab is where you match a query observation against the rest of the catalog.

1. Select a **query observation** and an **algorithm** (e.g. ORB).
2. Click **Identify**. HerpetoID preprocesses the images, extracts features, and ranks the other
   observations of the same species by similarity.
3. The ranked candidates appear in the table with a **similarity score** (1.0 = most similar). Select a
   candidate to compare it with the query **side by side**.

## Making a decision

The software only *proposes* candidates — you decide:

- **Confirm same individual** — links the query and the selected candidate to the same individual
  (creating a new individual record if needed).
- **Mark query as new individual** — creates a fresh individual for the query when it matches nothing.

Confirmed individuals appear on the **Individuals** tab, and recaptures feed the **Statistics**.

## About the ORB algorithm

ORB detects distinctive keypoints, matches them between two images (with a ratio test), and verifies the
match geometrically (RANSAC homography). The score combines the number of verified inliers, the inlier
ratio, and the geometric plausibility of the match.
