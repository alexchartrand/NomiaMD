"""Live smoke test against the Mistral API. Requires MISTRAL_API_KEY to be configured
(point MISTRAL_ENDPOINT at scripts/fake_llm_server.py instead to avoid a real API call).
From backend/, with the venv active:

    python scripts/try_extraction.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Must run before app.extraction.engine is imported below — app.extraction.engine.get_client()
# reads MISTRAL_API_KEY. Explicit path for the same reason as app/main.py: under a debugger,
# load_dotenv() searches os.getcwd() instead of walking up from this file.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.bootstrap import application_services  # noqa: E402
from app.extraction.pipeline import run_billing_codes_pipeline  # noqa: E402
from app.sample_patients import get_sample_patients  # noqa: E402


def load_sample_transcript() -> str:
    return get_sample_patients()[3].transcript


async def main() -> None:
    transcript = load_sample_transcript()
    print("--- transcript ---")
    print(transcript)

    async with application_services():
        summary_result, billing_result = await run_billing_codes_pipeline(transcript)

    print("--- consultation summary ---")
    print(summary_result.model_dump_json(indent=2))
    print("--- billing codes result ---")
    print(billing_result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
