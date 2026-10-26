"""Where benchmark runs live on disk:

    benchmarks/runs/<name>/manifest.json
    benchmarks/runs/<name>/notes/<patient_id>/<stage>.json
    benchmarks/runs/<name>/metrics.json, report.md
    benchmarks/baselines/<name>/        same layout, committed (`promote`)

`runs/` is gitignored: runs are cheap to redo and noisy in diffs. A baseline is a run worth
comparing against later, copied into git on purpose."""

import json
import shutil
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.benchmark.records import RunManifest, StageName, StageRecord

DEFAULT_ROOT = Path(__file__).parent.parent.parent / "benchmarks"

TRecord = TypeVar("TRecord", bound=StageRecord)


class RunNotFoundError(LookupError):
    pass


class Run:
    def __init__(self, path: Path):
        self.path = path

    @property
    def name(self) -> str:
        return self.path.name

    def read_manifest(self) -> RunManifest:
        return RunManifest.model_validate_json((self.path / "manifest.json").read_text())

    def write_manifest(self, manifest: RunManifest) -> None:
        self._write(self.path / "manifest.json", manifest)

    def has(self, stage: StageName, patient_id: str) -> bool:
        return self._record_path(stage, patient_id).exists()

    def read(self, stage: StageName, patient_id: str, record_type: type[TRecord]) -> TRecord | None:
        path = self._record_path(stage, patient_id)
        if not path.exists():
            return None
        return record_type.model_validate_json(path.read_text())

    def write(self, stage: StageName, record: StageRecord) -> None:
        self._write(self._record_path(stage, record.patient_id), record)

    def patient_ids(self, stage: StageName) -> list[str]:
        notes = self.path / "notes"
        if not notes.exists():
            return []
        return sorted(p.parent.name for p in notes.glob(f"*/{stage}.json"))

    def write_json(self, filename: str, data: dict | BaseModel) -> Path:
        path = self.path / filename
        self._write(path, data)
        return path

    def write_text(self, filename: str, text: str) -> Path:
        path = self.path / filename
        path.write_text(text)
        return path

    def _record_path(self, stage: StageName, patient_id: str) -> Path:
        return self.path / "notes" / patient_id / f"{stage}.json"

    @staticmethod
    def _write(path: Path, data: dict | BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = data.model_dump_json(indent=2) if isinstance(data, BaseModel) else json.dumps(data, indent=2, ensure_ascii=False)
        # Write-then-rename, so an interrupted run never leaves a half-written record that
        # a resume would mistake for a finished one.
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text)
        tmp.replace(path)


class RunStore:
    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = root
        self.runs_dir = root / "runs"
        self.baselines_dir = root / "baselines"

    def exists(self, name: str) -> bool:
        return (self.runs_dir / name / "manifest.json").exists()

    def create(self, name: str) -> Run:
        path = self.runs_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return Run(path)

    def open(self, name: str) -> Run:
        """A run by name, from runs/ first, then baselines/."""
        for directory in (self.runs_dir, self.baselines_dir):
            if (directory / name / "manifest.json").exists():
                return Run(directory / name)
        raise RunNotFoundError(f"No benchmark run named {name!r} under {self.runs_dir} or {self.baselines_dir}")

    def promote(self, name: str, as_name: str) -> Run:
        source = self.open(name)
        target = self.baselines_dir / as_name
        if target.exists():
            raise FileExistsError(f"Baseline {as_name!r} already exists: {target}")
        shutil.copytree(source.path, target)
        return Run(target)
