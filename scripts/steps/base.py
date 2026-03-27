"""
Base step interface and step type semantics.

A step is a callable:

    step(context: dict) -> dict

Steps receive the context from the previous step (or the engine's initial context)
and return a modified copy. The engine chains them in order.

Step types (from config/mappings.json `type` field):

  check     — Verify a precondition. If it fails and on_failure="abort", the
               engine halts the pipeline and falls through to _fallback.
               If on_failure="continue", a flag is set in context and the
               pipeline proceeds.

  transform — Enrich or modify context data (e.g. add file_size, file_ext).
               Always passes through — cannot abort.

  decide    — Set the routing decision in context: pass | soft_deny | hard_deny.
               The engine reads context["decision"] after all steps complete.

  resolve   — Produce the final hook output (deny message, redirect suggestion).
               Terminal — generates context["output"] for the hook response.

Phase 1 will implement: check_code_index_fresh, check_doc_index_fresh,
enrich_file_metadata, soft_deny_redirect, hard_deny, redirect_to_context_mode,
format_deny_message, format_redirect_message, format_exa_redirect,
format_context_mode_web_redirect, pass_through.
"""
