# /state

The interface between a long-running agent working in this repo and the human
answering its questions. Both sides read and write plain markdown here and
nothing else — no conversation history is synced, no agent holds its own
memory of the project. Files or nothing.

    status.md              what the agent is doing right now
    questions/NNNN.md      one file per OPEN question
    questions/answered/    questions that have been closed out
    decisions.md           append-only log of question + answer

Use `tools/state.py` rather than editing these by hand. It allocates ids
without collisions, keeps `decisions.md` append-only, and logs the question
alongside the answer — six weeks from now you will want to know *why* you said
no to something, and an answer on its own will not tell you.

## One writer per file

Two agents writing the same file is boring and real, and it fails at the worst
moment. So:

| File | Written by | Read by |
|---|---|---|
| `status.md` | the agent | you |
| `questions/NNNN.md` | the agent (created), the tool (closed out) | both |
| `decisions.md` | the answering side, append-only | the agent, polling |

The agent never writes `decisions.md`. You never hand-edit a question file.

## Asking

A question file is written **only when the answer depends on something the
agent cannot know** — client intent, budget, an unstated constraint, a
judgement call about acceptable risk. Not because a problem is hard. Hard is
the job.

    python3 tools/state.py ask \
        --topic rotor-finish \
        --question "Should the tail rotor match the main rotor's metal finish, or be painted?" \
        --tried "Both read fine in isolation; the reference photos show either, so this is a look call, not a modelling one." \
        --option "Match the main rotor — one Metal material, simplest" \
        --option "Paint the tail rotor in the body colour" \
        --recommend 1

Every question carries, in this order:

1. **The question**, one plain sentence, no jargon.
2. **What was tried** and why it is blocked.
3. **Two or three concrete options with a recommendation**, so the answer can
   be "the second one" rather than an essay.

`--blocking` is the only priority signal, and there are exactly two tiers.
Set it only when there is genuinely no other work to do. Unset, the question
waits; set, it is a real alert. A tool that pings you six times an hour gets
muted and then abandoned, so the bar for asking at all is high and the bar for
`--blocking` is higher.

## Answering

    python3 tools/state.py list
    python3 tools/state.py show 43
    python3 tools/state.py answer 43 "the second one — paint it"

That appends the question and answer to `decisions.md` and moves the question
out of the open queue. The agent polls `decisions.md`, finds the entry for the
id it is waiting on, and resumes.

## Scope

This is Phase 1 of the voice layer: question files and a status line, read by
hand. No server, no notifications, no voice. The point is to find out whether
the questions the agent writes are worth asking — if they are not, nothing
downstream can save it, and that is worth discovering for free.

Later phases (a relay server watching `questions/` for new files, push to a
phone, a `digest.md` regenerated on change, then voice) read and write these
same files. Nothing here should need to change to support them.
