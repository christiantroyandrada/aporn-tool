"""Run manifest + resume logic: which stages are done, and what re-running should recompute."""
import hashlib
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class StageRecord:
    id: str
    status: str = StageStatus.PENDING.value
    params_key: str = ""          # hash of the params this stage depends on (FR-24e)
    outputs: list = field(default_factory=list)
    error: str = ""


@dataclass
class Manifest:
    mode: str
    target: str
    input_fingerprint: str = ""   # detects repointed/grown inputs (FR-24f)
    order: list = field(default_factory=list)   # active stage sequence for THIS run (FR-24d)
    stages: dict = field(default_factory=dict)

    def stage(self, sid: str) -> StageRecord:
        # Auto-create a pending record the first time we touch a stage.
        return self.stages.setdefault(sid, StageRecord(sid))

    def mark(self, sid: str, status, **kw) -> StageRecord:
        rec = self.stage(sid)
        rec.status = status.value if isinstance(status, StageStatus) else status
        for key, value in kw.items():
            setattr(rec, key, value)
        return rec

    def next_pending(self):
        # Resume point: the first stage in order that isn't DONE (failed/pending both qualify).
        for sid in self.order:
            if self.stage(sid).status != StageStatus.DONE.value:
                return sid
        return None

    def invalidate_from(self, sid: str) -> None:
        # A change at `sid` forces it + everything downstream to re-run; upstream stays DONE.
        start = self.order.index(sid)
        for s in self.order[start:]:
            self.stage(s).status = StageStatus.PENDING.value


def input_fingerprint(files) -> str:
    # A stable signature of the input set — name + size + mtime of each sub.
    digest = hashlib.sha256()
    for f in sorted(Path(x) for x in files):
        st = f.stat()
        digest.update(f"{f.name}|{st.st_size}|{int(st.st_mtime)}\n".encode())
    return digest.hexdigest()[:16]


def save_manifest(m: Manifest, path) -> None:
    data = {
        "mode": m.mode, "target": m.target,
        "input_fingerprint": m.input_fingerprint, "order": m.order,
        "stages": {sid: asdict(rec) for sid, rec in m.stages.items()},
    }
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_manifest(path) -> Manifest:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    m = Manifest(mode=data["mode"], target=data["target"],
                 input_fingerprint=data.get("input_fingerprint", ""),
                 order=data.get("order", []))
    for sid, rec in data.get("stages", {}).items():
        m.stages[sid] = StageRecord(**rec)
    return m
