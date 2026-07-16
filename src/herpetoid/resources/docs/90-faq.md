# Troubleshooting & FAQ

**I imported images but can't see them.**
Open the **Observations** tab and click a row — the image appears on the right with zoom/pan. The
**Import** tab also shows a thumbnail gallery of everything you've imported.

**Identification returns no candidates.**
There must be at least one *other* observation of the same species to compare against. Import a few
observations first.

**A candidate is wrong.**
That's expected sometimes — HerpetoID ranks possibilities, and you decide. Pick the correct candidate
(or **Mark query as new individual**). Different sides of an animal (e.g. left vs right flank) generally
cannot be matched to each other.

**Where is my data?**
Inside the project folder: `project.db` plus the `images/` folder. The whole folder is portable.

**Can I change the look of the app?**
Yes — open **Settings** (Tools menu): *Mode* switches System / Light / Dark, and *Style*
picks a color preset (Brook Teal, Forest Moss, River Slate, Sunset Clay). Both apply immediately and
are remembered. The same options live under **View → Theme / Style**.

**How do I add another species or algorithm?**
Install a plugin (see the *Plugins* chapter). No changes to HerpetoID itself are required.

**Nothing happens / an error appears.**
Check the log file in your user application-data folder (`HerpetoID/logs/`). It records warnings and
errors, including plugins that failed to load.
