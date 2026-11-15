#!/usr/bin/env python3
"""
Mechanical helpers for kernel patch review.

Some of the work the review prompts ask for needs no judgement, and a model
that does it by hand pays for it in context and in turns.  This script does
that work instead:

  kreview.py guides [REF|PATCH]        print the subsystem rules that apply
                                        to a commit or a patch file
  kreview.py guides --for ITEM...      name the guides for paths or symbols
  kreview.py section GUIDE TITLE       print one section of a guide

Guide selection applies the trigger table in subsystem/subsystem.md, so the
same change always gets the same guides.  scripts.md describes how each kind
of trigger is matched and what is printed for a matching guide.
"""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
PROMPT_DIR = SCRIPT_DIR.parent
GUIDE_DIR = PROMPT_DIR / "subsystem"
GUIDE_INDEX = GUIDE_DIR / "subsystem.md"

# A guide this small is printed whole whenever it matches.
SMALL_GUIDE_BYTES = 2000

# A guide matched by one of its path triggers is printed whole up to this size.
# The change is inside that subsystem, so rules that name none of the changed
# identifiers can still apply to it.
HOME_GUIDE_BYTES = 8000

# Past HOME_GUIDE_BYTES, sections that only mention the surrounding code are
# added until the guide's share reaches this size.
HOME_GUIDE_CONTEXT_BYTES = 8000

# Ceiling for all the rules printed for one change.
RULES_BUDGET_BYTES = 24000

FILE_TRIGGERS = ("Kconfig", "Kbuild", "Makefile")
FILE_EXT_RE = re.compile(r"\.(c|h|S|rs|py|sh|pl|yaml|json|dts|dtsi|rst|txt|lds)$")
FILE_NAME_RE = re.compile(r"[\w.*+-]+")

# Names that appear in almost every change and so say nothing about which
# rule applies to it.
STOP_WORDS = frozenset("""
    auto bool break case char const continue default define defined do double
    else endif enum extern false float for goto if ifdef ifndef include inline
    int long noinline register return short signed sizeof static struct switch
    true typedef typeof union unsigned void volatile while
    NULL size_t ssize_t loff_t gfp_t uintptr_t
    __u8 __u16 __u32 __u64 __s8 __s16 __s32 __s64 __le16 __le32 __le64
    __be16 __be32 __be64 __init __exit __user __iomem
    PAGE_SIZE PAGE_SHIFT PAGE_MASK ARRAY_SIZE IS_ENABLED IS_ERR IS_ERR_OR_NULL
    PTR_ERR ERR_PTR ERR_CAST BUG_ON WARN_ON WARN_ON_ONCE BUILD_BUG_ON
    EXPORT_SYMBOL EXPORT_SYMBOL_GPL MODULE_LICENSE container_of likely unlikely
    pr_err pr_warn pr_info pr_debug dev_err dev_warn dev_info dev_dbg
    CORRECT WRONG TODO NOTE
    """.split())

ERRNO_RE = re.compile(r"E[A-Z0-9]{3,}")


def run(cmd: list[str], cwd: Optional[str] = None, stdin: Optional[str] = None) -> str:
    """Run a command and return its stdout; raise on a non-zero exit."""
    result = subprocess.run(
        cmd, cwd=cwd, input=stdin, capture_output=True, text=True, errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {result.stderr.strip()}")
    return result.stdout


def die(message: str) -> NoReturn:
    print(f"kreview.py: {message}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# The change under review
# ---------------------------------------------------------------------------

@dataclass
class Change:
    """A commit or a patch file, split into the parts the matchers need."""
    ref: str                      # what the caller asked for
    sha: Optional[str]            # full sha, or None for a patch file
    subject: str
    message: str                  # subject and body
    diff: str                     # unified diff
    paths: list[str] = field(default_factory=list)
    changed: str = ""             # added and removed lines, hunk headers
    context: str = ""             # unchanged lines around them


IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def identifiers(text: str) -> set[str]:
    return set(IDENT_RE.findall(text)) - STOP_WORDS


def split_diff(diff: str) -> tuple[list[str], str, str]:
    """Return (paths, changed text, context text) for a unified diff."""
    paths: list[str] = []
    changed: list[str] = []
    context: list[str] = []
    in_hunk = False
    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            in_hunk = False
            m = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            if m:
                for path in m.groups():
                    if path not in paths:
                        paths.append(path)
        elif line.startswith("@@"):
            in_hunk = True
            # The text after the second @@ names the enclosing function.
            changed.append(line.split("@@", 2)[-1])
        elif not in_hunk:
            continue
        elif line.startswith(("+", "-")):
            changed.append(line[1:])
        elif line.startswith(" "):
            context.append(line[1:])
    return paths, "\n".join(changed), "\n".join(context)


def looks_like_patch(path: str) -> bool:
    try:
        with open(path, errors="replace") as f:
            head = f.read(200000)
    except OSError:
        return False
    return bool(re.search(r"^diff --git ", head, re.M))


def load_change(ref: str, git_dir: Optional[str], function_context: bool = False) -> Change:
    """Load a commit (any git revision) or a patch file."""
    if os.path.isfile(ref) and looks_like_patch(ref):
        with open(ref, errors="replace") as f:
            text = f.read()
        start = re.search(r"^diff --git ", text, re.M)
        message = text[:start.start()] if start else ""
        diff = text[start.start():] if start else text
        m = re.search(r"^Subject: (?:\[[^\]]*\] *)*(.*)$", message, re.M)
        subject = m.group(1).strip() if m else os.path.basename(ref)
        sha = None
        context_diff = diff
    else:
        try:
            sha = run(["git", "rev-parse", "--verify", "--quiet", ref + "^{commit}"],
                      cwd=git_dir).strip()
        except (RuntimeError, OSError):
            die(f"'{ref}' is neither a commit nor a patch file in git format")
        message = run(["git", "show", "-s", "--format=%B", sha], cwd=git_dir).rstrip() + "\n"
        subject = message.split("\n", 1)[0]
        diff = run(["git", "show", "--format=", sha], cwd=git_dir)
        context_diff = diff
        if function_context:
            # -W widens every hunk to the whole enclosing function, which is
            # the code the rules have to be read against.
            context_diff = run(["git", "show", "--format=", "-W", sha], cwd=git_dir)

    paths, changed, _ = split_diff(diff)
    _, _, context = split_diff(context_diff)
    return Change(ref=ref, sha=sha, subject=subject, message=message, diff=diff,
                  paths=paths, changed=changed, context=context)


# ---------------------------------------------------------------------------
# The trigger table
# ---------------------------------------------------------------------------

@dataclass
class Trigger:
    text: str
    # One (kind, regex) pair per part; "a + b" has two parts and needs both.
    # kind is "path" or "text".  A trigger worded for a human has no parts.
    parts: list[tuple[str, "re.Pattern[str]"]] = field(default_factory=list)


@dataclass
class GuideRow:
    name: str
    triggers: list[Trigger]
    file: str


def split_cell(cell: str) -> list[str]:
    """Split a trigger cell on the commas that are outside backticks."""
    items, current, in_code = [], "", False
    for ch in cell:
        if ch == "`":
            in_code = not in_code
        if ch == "," and not in_code:
            items.append(current)
            current = ""
        else:
            current += ch
    items.append(current)
    return [item.strip() for item in items if item.strip()]


def is_path_like(item: str) -> bool:
    """True for a directory, a path, or a bare file name such as decode.c."""
    if "/" in item or item in FILE_TRIGGERS:
        return True
    return bool(FILE_NAME_RE.fullmatch(item) and FILE_EXT_RE.search(item))


def compile_part(part: str) -> Optional[tuple[str, "re.Pattern[str]"]]:
    """Compile one trigger, or return None when it is wording for a human."""
    is_regex = "\\" in part
    plain = part.replace("\\", "")
    if " " in plain:
        return None
    try:
        if is_path_like(plain):
            if is_regex:
                return ("path", re.compile(part))
            body = re.escape(part).replace(r"\*", "[^/]*")
            # mm/memory.c names one file; net/ and Kconfig are prefixes.
            tail = "$" if FILE_EXT_RE.search(plain) else ""
            return ("path", re.compile(r"(?:^|/)" + body + tail))
        if is_regex:
            return ("text", re.compile(part))
        body = re.escape(part).replace(r"\*", r"\w*")
        # An identifier trigger has to start an identifier or one of its
        # underscore-separated words: skb_ matches __skb_put, not xskb_put.
        lead = "" if part.startswith("*") or not re.match(r"\w", part) else r"(?<![A-Za-z0-9])"
        return ("text", re.compile(lead + body))
    except re.error:
        return None


def compile_trigger(raw: str) -> Trigger:
    trigger = Trigger(text=raw.replace("`", ""))
    parts = []
    for piece in re.split(r"\s\+\s", raw):
        compiled = compile_part(piece.strip().strip("`").strip())
        if compiled is None:
            return trigger
        parts.append(compiled)
    trigger.parts = parts
    return trigger


def parse_trigger_table(index_path: Path = GUIDE_INDEX) -> list[GuideRow]:
    rows = []
    in_table = False
    for line in index_path.read_text().split("\n"):
        if not line.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if "Triggers" in cells:
            in_table = True
            continue
        if not in_table or len(cells) < 3 or set(cells[0]) <= set("-: "):
            continue
        # A regex trigger may contain an escaped pipe; the file is the last cell.
        name, cell, guide = cells[0], "|".join(cells[1:-1]), cells[-1]
        rows.append(GuideRow(name, [compile_trigger(t) for t in split_cell(cell)], guide))
    return rows


@dataclass
class GuideMatch:
    file: str
    name: str
    strength: str      # "path", "changed" or "context"
    trigger: str


STRENGTH_ORDER = {"path": 0, "changed": 1, "context": 2}


def trigger_strength(trigger: Trigger, paths: list[str], changed: str, context: str) -> Optional[str]:
    """How strongly a trigger matches: its weakest part decides."""
    if not trigger.parts:
        return None
    worst = "path"
    for kind, regex in trigger.parts:
        if kind == "path":
            strength = "path" if any(regex.search(p) for p in paths) else None
        elif regex.search(changed):
            strength = "changed"
        elif regex.search(context):
            strength = "context"
        else:
            strength = None
        if strength is None:
            return None
        if STRENGTH_ORDER[strength] > STRENGTH_ORDER[worst]:
            worst = strength
    return worst


def match_guides(rows: list[GuideRow], paths: list[str], changed: str, context: str) -> list[GuideMatch]:
    """Return the guides whose triggers match, strongest match first."""
    best: dict[str, GuideMatch] = {}
    for row in rows:
        for trigger in row.triggers:
            strength = trigger_strength(trigger, paths, changed, context)
            if strength is None:
                continue
            current = best.get(row.file)
            if current is None or STRENGTH_ORDER[strength] < STRENGTH_ORDER[current.strength]:
                best[row.file] = GuideMatch(row.file, row.name, strength, trigger.text)
    return sorted(best.values(), key=lambda m: STRENGTH_ORDER[m.strength])


# ---------------------------------------------------------------------------
# Guide sections
# ---------------------------------------------------------------------------

@dataclass
class Unit:
    """A heading with the text under it, or one item of a Quick Checks list."""
    title: str
    level: int                    # heading depth; 0 for text above the first heading
    text: str
    parent: Optional[int] = None  # index of the enclosing heading
    item: bool = False            # an item of a Quick Checks list
    idents: frozenset = frozenset()
    files: frozenset = frozenset()


HEADING_RE = re.compile(r"^(#{1,4})\s+(.*?)\s*$")
CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
CALL_RE = re.compile(r"\b([A-Za-z_]\w{2,})\s*\(")


def api_names(span: str) -> set[str]:
    """Names in a code span that identify a kernel API.

    A lower-case word on its own (`folio`, `flags`, `lock`) is as likely to
    be a local variable as anything else and matches most changes, so it only
    counts when it is written as a call.
    """
    names = set()
    for m in IDENT_RE.finditer(span):
        name = m.group(0)
        if name in STOP_WORDS or ERRNO_RE.fullmatch(name):
            continue
        called = span[m.end():].lstrip().startswith("(")
        if "_" in name.strip("_") or not name.islower() or called:
            names.add(name)
    return names


def unit_signals(text: str) -> tuple[frozenset, frozenset]:
    """API names and file names a unit talks about."""
    idents: set[str] = set()
    files: set[str] = set()
    prose: list[str] = []
    fenced = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            # In an example only the calls are worth matching; the variable
            # names are made up.
            idents.update(n for n in CALL_RE.findall(line) if n not in STOP_WORDS)
        else:
            prose.append(line)
    for span in CODE_SPAN_RE.findall("\n".join(prose)):
        if "/" in span and " " not in span:
            files.add(span.strip("<>"))
        else:
            idents |= api_names(span)
    return frozenset(idents), frozenset(files)


def split_guide(text: str) -> list[Unit]:
    units = [Unit(title="", level=0, text="")]
    heading_stack: list[int] = []     # indexes of the open headings
    lines: list[str] = []
    fenced = False
    quick = False                     # inside a Quick Checks section

    def flush() -> None:
        units[-1].text = "".join(lines)
        lines.clear()

    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        heading = None if fenced else HEADING_RE.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            while heading_stack and units[heading_stack[-1]].level >= level:
                heading_stack.pop()
            parent = heading_stack[-1] if heading_stack else None
            units.append(Unit(title=heading.group(2), level=level, text="", parent=parent))
            heading_stack.append(len(units) - 1)
            quick = "quick check" in heading.group(2).lower()
        elif quick and not fenced and line.startswith("- "):
            flush()
            bold = re.match(r"- \*\*(.+?)\*\*", line)
            title = bold.group(1) if bold else line[2:].strip()[:60]
            units.append(Unit(title=title.rstrip(":"), level=9, text="",
                              parent=heading_stack[-1], item=True))
        lines.append(line)
    flush()

    for unit in units:
        unit.idents, unit.files = unit_signals(unit.text)
    return units


_guide_cache: dict[str, list[Unit]] = {}


def guide_units(guide: str) -> list[Unit]:
    if guide not in _guide_cache:
        _guide_cache[guide] = split_guide((GUIDE_DIR / guide).read_text(errors="replace"))
    return _guide_cache[guide]


def unit_tier(unit: Unit, change_idents: set[str], context_idents: set[str], paths: list[str]) -> Optional[int]:
    """1: names an API the change adds or removes; 2: names an API in the
    surrounding code, or a file the change touches; 0: names nothing in
    particular; None: about something else."""
    if unit.idents & change_idents:
        return 1
    if unit.idents & context_idents:
        return 2
    if any(p.endswith(f) or f.rstrip("/") + "/" in p for f in unit.files for p in paths):
        return 2
    if not unit.idents and not unit.files:
        return 0
    return None


@dataclass
class GuideRules:
    match: GuideMatch
    whole: bool = False
    shown: list[int] = field(default_factory=list)      # unit indexes, in order
    omitted: list[str] = field(default_factory=list)    # titles left out
    size: int = 0


def select_units(match: GuideMatch, change_idents: set[str], context_idents: set[str],
                 paths: list[str]) -> GuideRules:
    """Decide which parts of one matched guide are printed."""
    rules = GuideRules(match=match)
    units = guide_units(match.file)
    total = sum(len(u.text) for u in units)

    if match.strength == "context":
        return rules
    if total <= SMALL_GUIDE_BYTES or (match.strength == "path" and total <= HOME_GUIDE_BYTES):
        rules.whole = True
        rules.size = total
        return rules

    tiers = [unit_tier(u, change_idents, context_idents, paths) for u in units]
    keep = {i for i, tier in enumerate(tiers) if tier == 1}
    if match.strength == "path":
        # The change is in this subsystem: general sections apply, and so do
        # sections about the surrounding code while there is room for them.
        keep |= {i for i, tier in enumerate(tiers) if tier == 0 and not units[i].item}
        size = sum(len(units[i].text) for i in keep)
        for i, tier in enumerate(tiers):
            if tier == 2 and size + len(units[i].text) <= HOME_GUIDE_CONTEXT_BYTES:
                keep.add(i)
                size += len(units[i].text)
    if not keep:
        return rules

    # A kept unit needs its enclosing headings to make sense, and a guide's
    # opening lines say what it is about.
    for i in sorted(keep):
        parent = units[i].parent
        while parent is not None:
            keep.add(parent)
            parent = units[parent].parent
    keep.add(0)
    for i, unit in enumerate(units):
        if unit.level == 1:
            keep.add(i)

    rules.shown = sorted(keep)
    rules.size = sum(len(units[i].text) for i in rules.shown)
    rules.omitted = omitted_titles(units, keep)
    return rules


def omitted_titles(units: list[Unit], keep: set[int]) -> list[str]:
    """Titles of the sections left out; Quick Checks items are counted."""
    titles = []
    skipped_items: dict[int, int] = {}
    for i, unit in enumerate(units):
        if i in keep or not unit.title:
            continue
        if unit.item:
            skipped_items[unit.parent] = skipped_items.get(unit.parent, 0) + 1
        elif unit.text.strip() != unit.text.strip().split("\n")[0]:
            # A heading with nothing under it is only a container.
            titles.append(unit.title)
    for parent, count in skipped_items.items():
        title = units[parent].title
        if title in titles:
            continue
        titles.append(f"{title} ({count} more items)")
    return titles


def render_units(guide: str, shown: list[int]) -> str:
    units = guide_units(guide)
    return "".join(units[i].text for i in shown).rstrip() + "\n"


def select_rules(change: Change, rows: Optional[list[GuideRow]] = None) -> list[GuideRules]:
    """Pick the guide text that applies to a change, within the budget."""
    rows = rows if rows is not None else parse_trigger_table()
    matches = [m for m in match_guides(rows, change.paths, change.changed, change.context)
               if (GUIDE_DIR / m.file).is_file()]
    change_idents = identifiers(change.changed)
    context_idents = identifiers(change.context) - change_idents
    selected = [select_units(m, change_idents, context_idents, change.paths) for m in matches]

    # Over budget: guides matched by a symbol give way before guides the
    # change lives in, the largest first.
    def total() -> int:
        return sum(r.size for r in selected)

    order = sorted((r for r in selected if r.size),
                   key=lambda r: (r.match.strength != "changed", -r.size))
    for rules in order:
        if total() <= RULES_BUDGET_BYTES:
            break
        units = guide_units(rules.match.file)
        rules.omitted = [u.title for u in units if u.title and not u.item and u.level > 1]
        rules.whole = False
        rules.shown = []
        rules.size = 0
    return selected


def guide_path(guide: str) -> str:
    return str(GUIDE_DIR / guide)


def render_rules(selected: list[GuideRules]) -> str:
    """The rules text for a change, as it is shown to the model."""
    script = str(SCRIPT_DIR / "kreview.py")
    out: list[str] = []
    nearby = []
    for rules in selected:
        m = rules.match
        why = {"path": f"path matches {m.trigger}",
               "changed": f"the change uses {m.trigger}",
               "context": f"{m.trigger} in surrounding code"}[m.strength]
        if not rules.whole and not rules.shown:
            nearby.append(f"{m.file} ({why})")
            continue
        scope = "whole guide" if rules.whole else "matching sections"
        out.append(f"==== {m.file}: {m.name} -- {scope}; {why} ====\n")
        if rules.whole:
            out.append((GUIDE_DIR / m.file).read_text(errors="replace").rstrip() + "\n")
        else:
            out.append(render_units(m.file, rules.shown))
        if rules.omitted:
            out.append(f"\nSections of {m.file} not shown:\n")
            out.extend(f"  - {title}\n" for title in rules.omitted)
        out.append("\n")
    if nearby:
        out.append("Guides not loaded, matched less directly:\n")
        out.extend(f"  - {entry}\n" for entry in nearby)
        out.append("\n")
    if any(r.omitted for r in selected) or nearby:
        out.append("Print a section that was left out with:\n"
                   f"  {script} section GUIDE.md \"TITLE\"\n"
                   f"or read the whole guide in {GUIDE_DIR}/\n")
    if not out:
        return "No subsystem guide matches this change.\n"
    return "".join(out)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_guides(args: argparse.Namespace) -> None:
    rows = parse_trigger_table()
    if args.items:
        # Ad hoc: name the guides for some paths and symbols.
        paths = [i for i in args.items if is_path_like(i)]
        symbols = "\n".join(i for i in args.items if i not in paths)
        matches = [m for m in match_guides(rows, paths, symbols, "")
                   if (GUIDE_DIR / m.file).is_file()]
        if not matches:
            print("No subsystem guide matches.")
            return
        for m in matches:
            size = (GUIDE_DIR / m.file).stat().st_size
            print(f"{guide_path(m.file)}  ({m.name}; matched {m.trigger}; {size} bytes)")
        return

    change = load_change(args.change, args.git_dir, function_context=True)
    selected = select_rules(change, rows)
    if args.list:
        for rules in selected:
            m = rules.match
            state = "whole" if rules.whole else "sections" if rules.shown else "not loaded"
            print(f"{m.file}\t{m.strength}\t{m.trigger}\t{state}\t{rules.size}")
        return
    where = change.sha[:12] if change.sha else os.path.basename(change.ref)
    print(f"Subsystem rules for {where} (\"{change.subject}\")\n")
    sys.stdout.write(render_rules(selected))


def cmd_section(args: argparse.Namespace) -> None:
    guide = os.path.basename(args.guide)
    if not (GUIDE_DIR / guide).is_file():
        die(f"no guide named {guide} in {GUIDE_DIR}")
    units = guide_units(guide)
    wanted = re.sub(r"\s*\(\d+ more items\)$", "", args.title).strip().lower()
    hits = [i for i, u in enumerate(units) if u.title.lower() == wanted]
    if not hits:
        hits = [i for i, u in enumerate(units) if wanted and wanted in u.title.lower()]
    if not hits:
        titles = "\n".join(f"  - {u.title}" for u in units if u.title and not u.item)
        die(f"no section titled '{args.title}' in {guide}; it has:\n{titles}")
    for hit in hits:
        # A section is its heading plus everything nested under it.
        end = hit + 1
        while end < len(units) and (units[end].level > units[hit].level):
            end += 1
        sys.stdout.write("".join(u.text for u in units[hit:end]).rstrip() + "\n\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mechanical helpers for kernel patch review",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    guides = sub.add_parser("guides", help="print the subsystem rules that apply to a change")
    guides.add_argument("change", nargs="?", default="HEAD",
                        help="commit reference or patch file (default: HEAD)")
    guides.add_argument("--for", dest="items", nargs="+", metavar="ITEM",
                        help="name the guides for these paths and symbols instead")
    guides.add_argument("--list", action="store_true",
                        help="list the matching guides without their text")
    guides.add_argument("-C", "--git-dir", default=None, help="git repository directory")
    guides.set_defaults(func=cmd_guides)

    section = sub.add_parser("section", help="print one section of a subsystem guide")
    section.add_argument("guide", help="guide file name, e.g. mm-alloc.md")
    section.add_argument("title", help="section title, or part of it")
    section.set_defaults(func=cmd_section)

    args = parser.parse_args()
    try:
        args.func(args)
    except RuntimeError as err:
        die(str(err))


if __name__ == "__main__":
    main()
