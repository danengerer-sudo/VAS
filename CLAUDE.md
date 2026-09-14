# VAS

A CAD asset repo (see `assets/models/README.md`) with an asynchronous
human-in-the-loop layer bolted on. If you are an agent working here, the
second part applies to you on every run.

## Asking instead of stopping or guessing

When you hit a decision that depends on something you **cannot determine** —
client intent, budget, an unstated constraint, a judgement call about
acceptable risk — do not stop, and do not guess. Write a question file and
carry on with any other work you can do:

    python3 tools/state.py ask --topic <kebab-case> \
        --question "<one plain sentence, no jargon>" \
        --tried "<why you are blocked and what you already tried>" \
        --option "<concrete option>" --option "<concrete option>" \
        --recommend <1-based index of your pick> \
        [--blocking]

Then keep working on everything that does not depend on the answer. Poll
`state/decisions.md` for the entry matching your question id, and resume when
it appears.

**The bar is high.** A hard problem is not a question — hard is the job. Ask
only when no amount of work on your side could produce the answer. The most
likely way this whole system fails is by asking too much: a tool that pings
six times an hour gets muted and then abandoned. Be ruthless about this, and
prefer making the call and noting it in `status.md` over asking.

`--blocking` means there is genuinely nothing else you can do. It is a real
alert on someone's phone. If you can keep working, leave it off.

Keep `status.md` current with `tools/state.py status "<what you are doing>"`
at the start of a run, on any meaningful change of task, and at the end.

Never write `state/decisions.md` yourself — that file is the human's side of
the conversation, and it is append-only. Full protocol in `state/README.md`.

## Assets

`tools/make_helicopter.py` generates both detail levels of the helicopter GLB
and asserts its own invariants (watertight meshes, nothing poking through the
hull, clear forward view). Regenerate rather than editing a `.glb`:

    python3 tools/make_helicopter.py assets/models/helicopter_lowpoly.glb
