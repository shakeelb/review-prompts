# Gathering context without a review pack

Use this only when `scripts/kreview.py prepare` could not build
`./review-context/pack.md`.  It covers the two things the pack would have
held: the subsystem guides that apply to the change, and the code around it.

## Subsystem guides

In the tree under review, run the prompt directory's
`scripts/kreview.py guides <commit or patch file>` and read all of its
output.  It applies the trigger table in `subsystem/subsystem.md` to the
change and prints the guide sections that apply to it, followed by the
titles of the sections left out.  Those titles are part of your
instructions: when the analysis reaches code that a left-out section is
about, print that section with the command given next to the titles and
read it before continuing.

Only if the script cannot be run: read `subsystem/subsystem.md`, scan the
diff against all of its triggers, and load all matching subsystem guides and
critical patterns IMMEDIATELY.

## Code

1. **Using semcode MCP (preferred)**:
   - `diff_functions`: identify changed functions and types
   - `find_function/find_type`: get definitions for all identified items
     - both of these accept a regex for the name, use this before grepping through the sources for definitions
   - `find_callchain`: trace call relationships
     - spot check call relationships, especially to understand proper API usage
     - use arguments to limit callchain depth up and/or down.
   - `find_callers` (who calls X) / `find_calls` (what does X call):
     - Check at least one level up and one level down, more if needed.
     - spot check other call relationships as required
     - Always trace cleanup paths and error handling
   - `grep_functions`: search function bodies for regex patterns.
     - returns matching lines by default (verbose=false).  When verbose=true is used, also returns entire function body
     - use verbose=false first to find matching lines, then use semcode find_function to pull in functions you're interested in
     - use verbose=true only with detailed regexes where you want full function bodies for every result
     - can return a huge number of results, use path regex option to limit results to avoid avoid filling context
     - searches inside of function bodies.  Don't try to do multi-line greps,
       don't try to add curly brackets to limit the result inside of functions
   - If the current commit has deleted a function, semcode won't be able to
     find it unless you search the parent commit.

2. **Without semcode (fallback)**:
   - Use `git show <sha>` to identify changes. Do not use `git diff` against HEAD: `review_one.sh` checks out a worktree with the commit applied, so `git diff` will be empty.
   - Manually find function definitions and relationships with grep and other tools
   - Document any missing context that affects research quality
