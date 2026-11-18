# bronkhorst-mfc

Group-wide Bronkhorst MFC driver (GHE, ETH Zurich), used by students and by the ecoTrace bench
(`ecotrace-dmrv/measurements` pins a tag). Not part of the ecoTrace shared-MAJOR scheme.

- Branches `main` and `dev`; work on `dev`, PR `dev` -> `main`, the human merges. Tag `vX.Y.Z` on `main`
  after the merge; bump `version` in `pyproject.toml` and `__init__.py` together.
- Commits: Conventional Commits, subject <= 50 chars, at most 3 bullets, prompts archived in
  `prompts/`, `Assisted-by:` and `Claude-session:` trailers; never `Co-Authored-By`.
- Never command flow on real hardware without the human confirming the physical state
  (valves, outlet open) in their own words. See `docs/OPERATING.md`.
- Instruments are identified by serial number, fluids by name. Never hardcode a COM port, an
  address or a fluidset index in library code.
- Tests run without hardware: `python -m unittest discover tests`. Keep them passing.
