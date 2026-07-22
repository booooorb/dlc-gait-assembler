# Architecture

The application is organized around one dependency direction:

```text
GUI features  →  services and pipelines  →  dependency-free domain values
```

Code in `services` must never import `gui`. Code in `services/domain` must also
remain independent of Qt, subprocesses, the filesystem, and pipeline adapters.
The architecture test enforces these boundaries.

## Public boundaries

- Import shared Qt widgets, media helpers, and formatting from `gui/shared`.
- Import theme tokens, palette/font helpers, QSS, and custom drawing from the
  `gui/theme` package.
- Import manifest serializers from `services/manifests` or the relevant
  workflow module (`video`, `gait`, or `knee`).
- Import automated-profile models, validation, and persistence from
  `services/profiles`.
- Import environment and temporary-directory discovery from
  `services/pipeline/runtime`.
- Import ALMA, automated-pipeline, and RustLab1 APIs from their package
  `__init__.py` files. Callers must not import another module's private names.

`services/analysis_manifests.py`, `services/automated_profiles.py`, and
`gui/automated_pipeline/profiles.py` are documented compatibility facades.
They contain re-exports only and can be removed in a future breaking release.

## Feature placement

GUI packages are feature-oriented. A feature's public window or workspace is a
thin coordinator; form settings, pairing logic, dialogs, previews, and workers
live beside it. Logic that does not require Qt should be represented by plain
functions or dataclasses so it can be tested without constructing widgets.

Service packages are responsibility-oriented:

- `domain`: dependency-free values and invariants
- `manifests`: versioned serialization by workflow
- `profiles`: profile models, pure validation, and transactional storage
- `pipeline`: runtime discovery and external workflow adapters

Keep a cohesive small adapter such as `deeplabcut.py` as a module. Promote it to
a package only when it has multiple independent responsibilities.

## Naming and tests

Public functions, models, and constants use names without a leading underscore
and are exported explicitly from package `__init__.py` files. Private helpers
may be used only inside their defining module.

New unit tests mirror the source feature under `tests/unit/gui` or
`tests/unit/services`. Compatibility tests protect legacy imports until a
dedicated breaking-release cleanup removes the facades.

Run the guardrails with:

```bash
pytest
ruff check .
```
