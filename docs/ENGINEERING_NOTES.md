# Engineering Notes

## What did you build first, and why?

`field_decisions.py` — grounding, controlled vocabulary, the four field statuses, and "the model reports, deterministic code decides" — before the UI, the OpenRouter client, or persistence. Building the rules first, against hand-built fixtures before any real model call, meant the data-pack cases and the live model tested the same logic, not two different things.

## What did you deliberately leave out?

Persistence (in-memory only), authentication/authorisation, a real Graph write, and request queuing — none are needed for a single-reviewer demo (see the README for what production adds).

## What is the biggest production risk?

No identity is attached to approval — the app has no login, so `approved_at` records *when* but not *who*. For a governance process like ILRI's CSF reporting, that's the gap that matters most: accountability, not model accuracy. The model side is already guardrailed (grounding, controlled vocabulary, `AMBIGUOUS` blocking auto-approval), so the largest remaining risk is organisational, not technical.

## What would you change to process thousands of submissions?

Move OpenRouter calls off the synchronous request path onto a task queue. Add real persistence behind the existing `Draft`/`ApprovedRecord` shapes (the models don't change, only where they're stored). Add monitoring for error rate, latency, and the `READY_FOR_REVIEW` vs `NEEDS_ATTENTION` split as a live signal of prompt quality at volume. None of this touches `field_decisions.py` — already stateless, moves as-is.

## How did you use AI?

Built with Claude Code, iteratively, in one long session — implementing on Django first, then rebuilding as the plain package once the framework turned out to solve problems this exercise doesn't have. Every claim about live behaviour (the injection example, the data-pack results) was checked by actually running the code against the live model, not assumed.

## What did you reject or materially change?

- **Django, then plain Python.** A working, fully-tested Django build (ORM, class-based views) was rebuilt as the flat `voice_capture` package — no framework or database needed for a single-reviewer tool.
- **A separate edit validator, then Pydantic alone.** A hand-rolled validator re-implemented rules the extraction schema already enforced.
- **An audit log, then values on the record itself.** `ApprovedRecord` keeps `ai_values` alongside final values directly, instead of a separate table.
- **One-method classes, then plain functions.** `ColourVocabulary`, `QuarterFormat`, `InjectionDetector` wrapped single checks in classes for dependency injection nothing used; now plain functions.
