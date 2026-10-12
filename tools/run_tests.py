"""Run each regression script in its own process from the repository root."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NATIVE = {"test_instance", "test_panel_z"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, help="write machine-readable results")
    args = parser.parse_args()
    failures = []
    results = []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        env = os.environ.copy()
        if path.stem in NATIVE:
            env.pop("QT_QPA_PLATFORM", None)
        else:
            env["QT_QPA_PLATFORM"] = "offscreen"
        result = subprocess.run([sys.executable, "-m", f"tests.{path.stem}"],
                                cwd=ROOT, env=env, check=False,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = result.stdout.decode("utf-8", errors="replace")
        tail = output.strip().splitlines()[-1] if output.strip() else ""
        results.append({"Test": path.name, "Code": result.returncode, "Tail": tail})
        print(f"{path.name}: {'PASS' if result.returncode == 0 else 'FAIL'} {tail}",
              flush=True)
        if result.returncode:
            failures.append(path.name)
            print(output, flush=True)
    if args.results:
        args.results.parent.mkdir(parents=True, exist_ok=True)
        args.results.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
    print(f"{len(list((ROOT / 'tests').glob('test_*.py'))) - len(failures)} passed; "
          f"{len(failures)} failed", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
