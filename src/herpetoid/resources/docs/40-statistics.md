# Statistics

The **Statistics** tab summarizes the project. It is **field-driven**: each species declares which
measurements it records and which statistics to derive, so the dashboard adapts automatically to any
species.

## Always available

- Number of **individuals** and **observations**.
- **Recaptures** — observations of already-cataloged individuals.
- The **date range** of observations.

## Field-driven

Computed from the species' declared statistics, for example:

- **Means** of numeric measurements (e.g. mean SVL, mean weight).
- **Distributions / ratios** of categorical fields (e.g. sex ratio, computed per individual; the fire
  salamander module also breaks its captures down by dorsal pattern type).
- **Growth** — a per-individual time series of a measurement (e.g. SVL over time).
- **Derived metrics** a module computes from several fields at once — the fire salamander module
  reports body condition (Fulton's K) from weight and SVL.

Press **Refresh** after adding or identifying observations to recompute.
