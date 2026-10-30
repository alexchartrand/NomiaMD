"""Run the retention job once (app/retention/), what the worker does nightly — for dev without
Redis/a worker, or by hand. From backend/:

    uv run python scripts/purge.py --dry-run   # counts only, nothing removed
    uv run python scripts/purge.py
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Loads the repo-root .env — must run before the app imports below read their settings.
import app.config  # noqa: E402,F401

from app.bootstrap import postgres_database  # noqa: E402
from app.retention import RetentionJob  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="count what is due without removing it")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    async with postgres_database():
        report = await RetentionJob().run(dry_run=args.dry_run)
    verb = "due" if args.dry_run else "done"
    for step, count in vars(report).items():
        print(f"{step}: {count} {verb}")


if __name__ == "__main__":
    asyncio.run(main())
