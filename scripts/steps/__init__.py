"""
Step functions for the routing engine.

Steps are the pipeline units executed by the engine after a matcher fires.
Each step is referenced by dotted name in config/mappings.json (e.g. steps.soft_deny_redirect).

Phase 1 will implement the individual step functions in this package.
"""
