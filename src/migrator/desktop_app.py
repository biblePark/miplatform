from __future__ import annotations

import sys

from .desktop_filepicker import launch_filepicker_batch_workflow


def main() -> int:
    try:
        return launch_filepicker_batch_workflow()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
