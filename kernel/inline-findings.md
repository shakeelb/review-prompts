# Writing review findings

Use this instead of `inline-template.md` when `scripts/kreview.py prepare`
built the review pack.  You write the questions.  `scripts/kreview.py finish`
quotes the diff around them, wraps your text at 78 columns, checks it against
the mailing list rules, and writes `./review-inline.txt` and
`./review-metadata.json`.  Do not write either file yourself, and do not
fetch the diff again to quote it.

## The findings file

Write `./review-context/findings.txt` in this form:

```
severity: <low | medium | high | critical>
explanation: <one sentence on what the most severe issue causes>
summary: <what the commit does, in at most three sentences>

=== finding
file: <path of the file, as the diff names it>
after: <the diff line your comment goes under, copied exactly>

<your comment>

=== finding
file: COMMIT_MESSAGE

<your comment about the commit message>
```

- Write one `=== finding` block for every issue that survived verification,
  including issues that a later commit in the series fixes.  Never include
  one you ruled out as a false positive.
- One block per issue, not per place the issue shows.  When the commit
  message makes a claim that an issue in the code disproves, that is the
  same issue: quote the claim in the comment on the code.  Use
  `file: COMMIT_MESSAGE` for an issue that is only in the commit message.
- `after:` is the line of the diff that sits closest to the code you are
  asking about; your comment is placed directly under it.  Copy it from
  part 2 of the pack with its leading `+` or `-`.  If that line occurs more
  than once in the file, add a second `after:` line holding the line that
  follows it.
- A regression in code the patch does not touch goes under the changed line
  that causes it.  An unchanged line that part 2 of the pack shows around
  the change may be used as well: the diff sent to the list does not
  contain it, so the comment is placed under the nearest changed line.
- For `file: COMMIT_MESSAGE` leave `after:` out.  The whole commit message is
  quoted above your comment, so quote the exact words you are questioning.
  A missing or wrong Fixes: tag is a commit message finding; give the tag
  you suggest on a line of its own.
- `severity` rises with user-visible harm: crashes, instability, security
  problems, incorrect behaviour.  With several issues, score the most
  severe, or their combined effect.

## How to write a comment

The comments are sent as a reply to the patch on a kernel mailing list.

- Plain text only: no markdown, no headings, no labels such as a word in
  capitals followed by a colon.  Upper case is only for code you quote.
- Ask, don't accuse, and never mention the author.  Not "Did you corrupt
  memory here?" but "Can this corrupt memory?".  Vary how the questions
  start.
- Stay factual and undramatic.  Call an issue a regression; never call it
  critical.
- Name the thing.  Not "does this leak a resource?" but "does this leak the
  folio?".  Not "is there a bounds issue?" but "can this overflow xyz[]?".
- Never give a line number.  Name the function, and show a call chain
  `funcA()->funcB()` or a few lines of the code instead.
- Keep paragraphs short.  Put a blank line between groups of facts and
  before the question.  Show a sequence of events as code and call chains
  rather than describing it in one dense paragraph:

```
Can this sequence occur?  If CPU1 already called bt_accept_unlink() and
cleared the parent pointer:

CPU1
bt_accept_unlink()
   bt_sk(sk)->parent = NULL;

CPU2 would see this in bt_accept_dequeue():
    if (!bt_sk(sk)->parent) {
        ...
        goto restart;
    }

and take the restart path instead of unlinking a second time?
```

- Say only what is needed.  An obvious slip needs one sentence.  Do not
  explain why the issue matters or why a typo is a problem.
- If the issue is fixed by a later commit, or was raised in a lore thread,
  say so in the comment and give the commit subject or the lore link.
- A subjective or style observation starts with something like "this isn't
  a bug, but ..." and is still a question about the specific code.  Never
  say or imply that code was written by a tool.
- Never quote, cite or build on automated review output (Sashiko, BPF CI,
  review bots, AI reviews).  Drop a finding that depends on it.  An
  `Assisted-by:` trailer in the commit message is ordinary metadata and is
  not an issue.

## Then

Run `scripts/kreview.py finish` from the directory `prepare` was run in.  If
it lists problems, fix `findings.txt` and run it again; it writes nothing
until the file is clean.  Its output says where each comment was placed.
Check that against what you intended, and you are done with the report.
