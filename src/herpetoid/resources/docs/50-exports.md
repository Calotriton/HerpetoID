# Exports

HerpetoID exports your catalog in open formats for analysis and sharing:

- **CSV** — one row per observation, with core fields and all species-specific measurements as columns.
- **Excel (.xlsx)** — an *Observations* sheet plus an *Individuals* sheet.
- **JSON** — a structured export of the project, individuals and observations, for interchange or backup.

A complementary **PDF** report (a project summary and per-individual dossiers) can be generated on
demand.

Exports never alter your project — they produce new files you choose the location of. Because the whole
project is a portable folder, you can also simply copy the folder to share the complete study.

**A note on text that looks like a formula.** Spreadsheets treat a cell starting with `=`, `+`, `-` or
`@` as a formula to run rather than as text. If a note or observer name in your data starts with one of
those characters, HerpetoID marks the cell as text so Excel shows it instead of executing it. In the
Excel export the value is unchanged; in CSV — which has no way to label a cell as text — a leading
apostrophe is added. The JSON export is always kept exactly as entered, so use it when you need the
raw values for analysis.
