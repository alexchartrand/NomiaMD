"""Live smoke test against your local model server. Requires NOMIAMD_BASE_URL (and
NOMIAMD_MODEL) to be configured to point at a running LocalAI instance. From backend/,
with the venv active:

    python scripts/try_extraction.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Must run before app.extraction.engine is imported below — it reads NOMIAMD_BASE_URL /
# NOMIAMD_MODEL at import time. Explicit path for the same reason as app/main.py: under
# a debugger, load_dotenv() searches os.getcwd() instead of walking up from this file.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.extraction.engine import run_extraction  # noqa: E402
from app.sample_patients import get_sample_patients  # noqa: E402
from app.tasks.registry import get_task  # noqa: E402


def load_sample_transcript() -> str:
    return get_sample_patients()[3].transcript


def main() -> None:
    transcript = load_sample_transcript()
    print("--- transcript ---")
    print(transcript)
    print("--- extraction result ---")

    task = get_task("consultation_summary")
    result = run_extraction(task, transcript)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
