"""Live smoke test against the real Claude API. Requires ANTHROPIC_API_KEY (or `ant auth
login`) to be configured — this was not available in the environment this scaffold was
built in, so it hasn't been run yet. From backend/, with the venv active:

    python scripts/try_extraction.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.extraction.engine import run_extraction
from app.tasks.registry import get_task

SYNTHETIC_TRANSCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "train.jsonl"
)


def load_sample_transcript() -> str:
    with SYNTHETIC_TRANSCRIPT_PATH.open() as f:
        record = json.loads(f.readline())
    lines = [f"{turn['speaker']}: {turn['utterance']}" for turn in record["conversation"]]
    return "\n".join(lines)


def main() -> None:
    transcript = load_sample_transcript()
    print("--- transcript ---")
    print(transcript)
    print("--- extraction result ---")

    task = get_task("billing_codes")
    result = run_extraction(task, transcript)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
