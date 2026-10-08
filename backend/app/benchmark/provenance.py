"""Which code produced a run: the commit, and whether the working tree had uncommitted
changes on top of it (a dirty run can't be reproduced from its SHA alone)."""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitProvenance:
    sha: str | None
    dirty: bool

    @classmethod
    def read(cls, cwd: Path) -> "GitProvenance":
        try:
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True
            ).stdout.strip()
            status = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"], cwd=cwd, capture_output=True, text=True, check=True
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            return cls(sha=None, dirty=False)
        return cls(sha=sha, dirty=bool(status.strip()))
