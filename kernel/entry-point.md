# New entry point analysis

Mandatory when the patch adds a new entry point (ioctl, syscall, sysfs
write, hook, exported API) into existing internal machinery.

- Precondition inventory: list every assumption the reused machinery
  makes (locks held, SRCU, vcpu/task loaded or initialized, first-run
  or first-use side effects, feature-mode state). For each, show
  where the new caller establishes it, or prove it cannot matter.
  "The existing callers do it" is not evidence the new caller does.
- Input-space sweep: enumerate the flag/mode dimensions of every
  object the entry point consumes (for KVM: memslot flags, VM type,
  protected/nested/mode variants) and trace one path per value
  class. The bug lives in the class nobody named in the commit
  message.
- Emulation parity: if the entry point claims to mirror an existing
  path ("as if X happened"), build a two-column table of helper
  calls (reference path vs new path). Every asymmetry must be
  justified or reported. Pay attention to helper variants whose
  names differ by a suffix (_prot, _atomic, __locked): they usually
  differ in exactly one semantic the new path forgot about.
- Output: `ENTRY-POINT: none` or the precondition inventory,
  input-space classes traced, and the parity table (or `parity: not
  an emulation path`)
