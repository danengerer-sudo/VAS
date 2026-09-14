#!/usr/bin/env python3
"""Read and write the shared state directory.

`/state` is the interface between a long-running agent working in this repo
and the human answering its questions. Both sides only ever exchange files --
no conversation history is synced, and neither side needs to know what the
other is thinking, only what it wrote down.

    state/status.md            what the agent is doing right now
    state/questions/NNNN.md    one file per OPEN question
    state/questions/answered/  questions that have been closed out
    state/decisions.md         append-only log of question + answer

Use this tool rather than editing those files by hand: it allocates question
ids without collisions, keeps `decisions.md` append-only, and logs the question
alongside the answer so a decision still makes sense six weeks later.

    state.py ask --topic rotor-finish --question "..." \
        --tried "..." --option "..." --option "..." --recommend 1 [--blocking]
    state.py list [--blocking-only]
    state.py show 43
    state.py answer 43 "the second one, match the main rotor"
    state.py status "Rebuilding the tail boom loft; 2 questions open"

Stdlib only, no dependencies.
"""

import argparse
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
QUESTIONS = STATE / "questions"
ANSWERED = QUESTIONS / "answered"
DECISIONS = STATE / "decisions.md"
STATUS = STATE / "status.md"

ID_RE = re.compile(r"^(\d{4})\.md$")


def now():
    """UTC timestamp, seconds resolution, e.g. 2026-09-14T16:40:00Z."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# front matter


def split_front_matter(text):
    """Return (dict, body). Front matter is `key: value` lines between ---."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 3)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, text[end + 5 :].lstrip("\n")


def join_front_matter(meta, body):
    lines = "\n".join(f"{k}: {v}" for k, v in meta.items())
    return f"---\n{lines}\n---\n\n{body.rstrip()}\n"


def is_blocking(meta):
    return meta.get("blocking", "false").strip().lower() == "true"


# --------------------------------------------------------------------------
# question files


def question_paths(include_answered=False):
    dirs = [QUESTIONS] + ([ANSWERED] if include_answered else [])
    found = []
    for d in dirs:
        if d.is_dir():
            found += [p for p in d.iterdir() if ID_RE.match(p.name)]
    return sorted(found, key=lambda p: p.name)


def next_id():
    """One past the highest id ever used, open or answered."""
    used = [int(ID_RE.match(p.name).group(1)) for p in question_paths(True)]
    return (max(used) + 1) if used else 1


def find_question(qid, where=None):
    name = f"{qid:04d}.md"
    for d in where or (QUESTIONS, ANSWERED):
        path = d / name
        if path.is_file():
            return path
    return None


def first_sentence(body):
    """The question itself -- first non-heading, non-empty line of the body."""
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return ""


def section(body, heading):
    """Return the text under `## heading`, or '' if absent."""
    out, collecting = [], False
    for line in body.splitlines():
        if line.startswith("## "):
            collecting = line[3:].strip().lower() == heading.lower()
            continue
        if collecting:
            out.append(line)
    return "\n".join(out).strip()


# --------------------------------------------------------------------------
# commands


def cmd_ask(args):
    if len(args.option) < 2:
        sys.exit(
            "error: give at least two concrete options (--option) so the answer\n"
            "can be 'the second one' rather than an essay. If there is only one\n"
            "way forward, this is not a question -- take it and note it in status."
        )
    if len(args.option) > 3:
        print(
            f"warning: {len(args.option)} options. Two or three is the readable "
            "limit on a phone.",
            file=sys.stderr,
        )
    if not 1 <= args.recommend <= len(args.option):
        sys.exit(f"error: --recommend must be between 1 and {len(args.option)}")

    QUESTIONS.mkdir(parents=True, exist_ok=True)
    qid = next_id()
    meta = {
        "id": f"{qid:04d}",
        "created": now(),
        "blocking": "true" if args.blocking else "false",
        "topic": args.topic,
    }

    options = "\n".join(
        f"{i}. {opt}" + ("  **(recommended)**" if i == args.recommend else "")
        for i, opt in enumerate(args.option, 1)
    )
    body = f"{args.question.strip()}\n\n## Tried\n\n{args.tried.strip()}\n\n## Options\n\n{options}\n"

    path = QUESTIONS / f"{qid:04d}.md"
    path.write_text(join_front_matter(meta, body))
    print(f"{path.relative_to(ROOT)}  ({'blocking' if args.blocking else 'can keep working'})")


def cmd_list(args):
    rows = []
    for path in question_paths():
        meta, body = split_front_matter(path.read_text())
        blocking = is_blocking(meta)
        if args.blocking_only and not blocking:
            continue
        rows.append((blocking, meta, first_sentence(body)))

    if not rows:
        print("no open questions")
        return
    # Blocking first, then oldest first -- the order they want answering in.
    rows.sort(key=lambda r: (not r[0], r[1].get("created", "")))
    for blocking, meta, question in rows:
        flag = "BLOCKING" if blocking else "waiting  "
        print(f"{meta.get('id', '????')}  {flag}  [{meta.get('topic', '-')}]  {question}")


def cmd_show(args):
    path = find_question(args.id)
    if not path:
        sys.exit(f"error: no question {args.id:04d}")
    print(path.read_text().rstrip())


def cmd_answer(args):
    path = find_question(args.id, where=(QUESTIONS,))
    if not path:
        if find_question(args.id, where=(ANSWERED,)):
            sys.exit(
                f"error: question {args.id:04d} is already answered. Decisions are "
                "append-only -- ask a new question rather than revising one."
            )
        sys.exit(f"error: no open question {args.id:04d}")

    answer = args.answer.strip()
    if not answer:
        sys.exit("error: empty answer")

    meta, body = split_front_matter(path.read_text())
    stamp = now()

    # Append to the log first: if anything fails after this the question stays
    # open, which is recoverable. The reverse would lose the decision.
    options = section(body, "Options")
    entry = [
        f"## {meta.get('id', f'{args.id:04d}')} — {meta.get('topic', 'untitled')}",
        "",
        f"**Asked** {meta.get('created', '?')} · **Answered** {stamp} · "
        f"{'blocking' if is_blocking(meta) else 'non-blocking'}",
        "",
        f"**Q:** {first_sentence(body)}",
    ]
    if options:
        entry += ["", "**Options offered:**", "", options]
    entry += ["", f"**A:** {answer}", ""]

    DECISIONS.parent.mkdir(parents=True, exist_ok=True)
    if not DECISIONS.exists():
        DECISIONS.write_text(
            "# Decisions\n\nAppend-only. Newest at the bottom. Never edit or "
            "delete an entry.\n"
        )
    with DECISIONS.open("a") as f:
        f.write("\n" + "\n".join(entry))

    # Close the question out.
    meta["answered"] = stamp
    ANSWERED.mkdir(parents=True, exist_ok=True)
    body = body.rstrip() + f"\n\n## Answer\n\n{answer}\n"
    (ANSWERED / path.name).write_text(join_front_matter(meta, body))
    path.unlink()

    print(f"{meta.get('id')} answered · logged to {DECISIONS.relative_to(ROOT)}")


def cmd_status(args):
    open_qs = question_paths()
    blocking = sum(is_blocking(split_front_matter(p.read_text())[0]) for p in open_qs)
    STATE.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(
        "# Status\n\n"
        f"_Updated {now()}_\n\n"
        f"{args.text.strip()}\n\n"
        f"Open questions: {len(open_qs)} ({blocking} blocking)\n"
    )
    print(f"{STATUS.relative_to(ROOT)} updated")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ask", help="write a new question file")
    p.add_argument("--topic", required=True, help="a few words, kebab-case")
    p.add_argument("--question", required=True, help="one plain sentence, no jargon")
    p.add_argument("--tried", required=True, help="why it is blocked and what was tried")
    p.add_argument("--option", action="append", default=[], help="repeat, two or three")
    p.add_argument("--recommend", type=int, default=1, help="1-based index of your pick")
    p.add_argument(
        "--blocking",
        action="store_true",
        help="set only if there is no other work you can do while you wait",
    )
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("list", help="open questions, blocking first")
    p.add_argument("--blocking-only", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="print one question in full")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("answer", help="log an answer and close the question")
    p.add_argument("id", type=int)
    p.add_argument("answer")
    p.set_defaults(func=cmd_answer)

    p = sub.add_parser("status", help="rewrite status.md")
    p.add_argument("text")
    p.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
