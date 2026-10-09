# API Contract — Draft

The backend owner must confirm the final endpoint names, input
formats, and invocation method.

## Proposed backend endpoints

- GET /health
- POST /analyze

These are proposed endpoints, not confirmed implementations.

## Vision result fields

- drain_id
- blockage_detected
- blockage_percentage
- confidence
- location
- timestamp
- method
- warnings

Severity and confidence must be unavailable when unsupported
by the implemented detection method.
