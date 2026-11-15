---
name: kernel
description: Load anytime the working directory is a linux kernel tree, and always load it when you answer questions inside the kernel tree.  Linux Kernel knowledge, subsystem specific details, analysis, review, debugging protocols.  Read this anytime you're in the linux kernel tree
invocation_policy: automatic
---

The kernel prompts are in `{{KERNEL_REVIEW_PROMPTS_DIR}}`, the prompt
directory.  Nothing in it is needed until a task calls for it, so pick the
row that matches the task and load only what that row names.  Where a row
names a file, reading it is mandatory: read it before doing anything else.

| Task | Load |
|------|------|
| Review a patch, a commit or a series | `{{KERNEL_REVIEW_PROMPTS_DIR}}/review-core.md`, then follow it.  It gathers its own context and tells you what else to load, and when |
| Debug a crash, oops, warning or stack trace | `{{KERNEL_REVIEW_PROMPTS_DIR}}/agent/debug.md`, then follow it.  Use the crash information as the entry points into the code |
| Make the same change in many places: a rename, an API change, an added parameter, removed boilerplate | `{{KERNEL_REVIEW_PROMPTS_DIR}}/coccinelle.md`.  Write a `.cocci` semantic patch and give the `make coccicheck` command, rather than editing the files one by one |
| Read, explain, write or change kernel code | The subsystem guides for that code, as described below |
| Anything else in the tree, such as building, git or tooling | Nothing |

## Subsystem guides

Each guide holds the invariants, API contracts and known bug patterns of one
subsystem.  To find the ones for the code at hand, name the files and the
APIs you are working with:

```
{{KERNEL_REVIEW_PROMPTS_DIR}}/scripts/kreview.py guides --for mm/slub.c kmalloc_node call_rcu
```

It prints the sections of the matching guides that are about those files
and APIs, and the titles of the sections it left out along with the command
that prints one.  Read what it prints, and fetch a left-out section when the
task reaches what it covers.  Before analysing code for bugs, also read
`{{KERNEL_REVIEW_PROMPTS_DIR}}/technical-patterns.md`.

If the script cannot be run, `{{KERNEL_REVIEW_PROMPTS_DIR}}/subsystem/subsystem.md`
is the table it applies: match its triggers by hand and read the guides it
names.

## Semcode Integration

When available, use semcode MCP tools for efficient code navigation:
- `find_function` / `find_type`: Get definitions
- `find_callchain`: Trace call relationships
- `find_callers` / `find_calls`: Explore call graphs
- `grep_functions`: Search function bodies
- `diff_functions`: Identify changed functions in patches

## Output

- Patch reviews produce `review-metadata.json`, and `review-inline.txt` when regressions are found
- Debug sessions produce `debug-report.txt` with analysis results
- Both reports are formatted for the Linux kernel mailing list (plain text, 78 char wrap)
