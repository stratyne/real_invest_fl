# UI Framework Decision

**Status:** Deferred — pending pipeline design completion.

**Options under consideration:**
- Streamlit (rapid Python-only, good for single-operator dashboard)
- FastAPI + Jinja2 + HTMX (more control, no JS framework required)
- FastAPI + React (maximum flexibility, higher build cost)

**Decision criteria:** Number of interactive screens, real-time log streaming
requirement, map view complexity, and available build time.

**Decision owner:** Project lead
**Decision deadline:** Before Phase 3 (API layer) is complete.
