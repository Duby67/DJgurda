# Quality Score

## Purpose

This file defines the quality bar for changes.

## Baseline

- the change is understandable from narrow context;
- behavior changes are reflected in docs when needed;
- riskier paths have targeted checks or tests;
- source status and runtime boundaries remain explicit;
- no hidden broadening of scope happened during implementation.

## Review Questions

- Was the context pack small and justified?
- Did the change stay inside the intended subsystem?
- Are stable and experimental paths still clearly separated?
- Did docs move closer to the code instead of drifting away from it?
- Were risky checks left unrun, and if so, was that stated explicitly?
