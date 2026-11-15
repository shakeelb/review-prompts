# Writing the review output by hand

Use this for Task 4 of `review-core.md` only when the review ran without
`scripts/kreview.py`, so there is no `./review-context/prepare.json` for
`scripts/kreview.py finish` to work from.

## Reporting

**If no regressions found**:
- check: were subjective issues found? [ Y/N]
  - If yes, these are regresssions, go to "If regressions found" section
- Mark complete and provide summary
- Note any context limitations

This step must not be skipped if there are regressions found.  You're creating
a text file to be sent to the linux kernel mailing list.  It is absolutely
CRITICAL this text file meets the standards of linux kernel communications
as defined in inline-template.md.  If you fail to follow those instructions,
the review is completely useless.

**If regressions found**:
0. Clear any context not related to the regressions themselves
1. Load `inline-template.md`
  - you must use inline-template.md for all analysis feedback
2. Create `review-inline.txt` in current directory, never use the prompt directory
3. Follow the instructions in the template carefully
  - NEVER WRITE `REGRESSION:` INTO ./review-inline.txt THIS
    AND ANY OTHER ALL CAPS ANALYSIS IS INCOMPATIBLE WITH LINUX KERNEL STANDARDS
4. Never include bugs that you identified as false positives in the report
5. Never include issues that quote, cite, summarize, or repeat automated review
   feedback. Search case-insensitively for forbidden bot evidence (`sashiko`, `bot+bpf-ci`,
   `kernel-patches-review-bot`, `Claude`, `AI review found`,
   `AI reviewed your patch`, `CI run summary`, `sashiko.dev`) and remove the
   entire affected issue.
6. Verify the ./review-inline.txt file exists if regressions are found
7. Verify the ./review-inline.txt file follows inline-template.md's guidelines

### MANDATORY COMPLETION VERIFICATION

Check ./review-inline.txt and confirm it looks like the inline-template.md

Your default commentary output is unfit for kernel reviews and analysis.
Confirm review-inline.txt follows inline-template.md, regenerate it if you've
snuck in markdown, ALL CAPS, or somehow broken with inline-template.md's
guidelines.

### Task 5 Review metadata output

Create a json file in the current directory named ./review-metadata.json

Identify an issue severity score "low", "medium", "high", "critical" for anything
reported in ./review-inline.txt. Scores would increase in severity based on
user-visible errors such as system crashes, instability, security problems, or
incorrect system behavior.

Create a one sentence explanation for your issue severity score.  If there are no
issues, just use "none"

If there are multiple issues, just pick the most severe, or consider the combination
of their overall implications.

The file should be created for every analysis, even if bugs were not found.
If the file already exists, it should be completely replaced.

./review-metadata.json will be parsed by other programs.

CRITICAL: DO NOT INVENT OTHER FIELDS FOR ./review-metadata.json.  IT MUST HAVE
THESE EXACT FIELDS IN THIS EXACT FORMAT.  DEVIATION IS NOT ALLOWED.

```json
{
  "author": "<string commit author>",
  "sha": "<string sha of the commit>",
  "subject": "<string commit subject>",
  "issues-found": <number>,
  "issue-severity-score": "<none/low/medium/high/critical>",
  "issue-severity-explanation": "<string, result of Task 5 analysis>"
}
```

- Ensure ./review-metadata.json exists and has the correct format
