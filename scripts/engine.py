"""
Categorization and routing engine.

Reads config/mappings.json and, for a given tool call, walks the matchers list
for that tool in order. The first matcher whose `method` returns True has its
`steps` pipeline executed. Each step is a Python callable with the interface:

    step(context: dict) -> dict

Steps chain context forward. The engine emits the final context as the hook
decision. If no matcher fires, the _fallback decision (pass) applies.

Phase 1 will implement this module.
"""
