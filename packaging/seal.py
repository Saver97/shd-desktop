"""Seal the tested 1.0.2 single-EXE candidate without touching prior releases."""

import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.2"
CANDIDATE = ROOT / "release-candidate" / VERSION / "SHDDesktop.exe"
SEALED = ROOT / "release" / "sealed" / VERSION
RUNTIME = {
    "SHDDesktop.exe": CANDIDATE,
    "恢复桌面图标.cmd": ROOT / "恢复桌面图标.cmd",
    "README.md": ROOT / "README.md",
    "RELEASE_NOTES.md": ROOT / "RELEASE_NOTES.md",
    "THIRD_PARTY_NOTICES.md": ROOT / "THIRD_PARTY_NOTICES.md",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detail(path: Path) -> dict:
    return {"sha256": sha256(path.read_bytes()), "bytes": path.stat().st_size}


def source_files() -> list[Path]:
    allowed = {".py", ".md", ".txt", ".ps1", ".cmd", ".spec", ".cs"}
    files = [path for path in ROOT.iterdir() if path.is_file()
             and (path.suffix in allowed or path.name == ".gitignore")]
    for directory in ("assets", "docs", "packaging", "shd_desktop", "tests", "tools"):
        files.extend(path for path in (ROOT / directory).rglob("*") if path.is_file()
                     and (directory == "assets" or path.suffix in allowed))
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def write_zip(path: Path, files: dict[str, Path], prefix: str) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as archive:
        for name, source in files.items():
            archive.write(source, f"{prefix}/{name}")
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {f"{prefix}/{name}" for name in files}
        for name, source in files.items():
            assert sha256(archive.read(f"{prefix}/{name}")) == sha256(source.read_bytes())


def main() -> None:
    if SEALED.exists():
        raise SystemExit(f"Refusing to overwrite sealed version: {SEALED}")
    for path in RUNTIME.values():
        if not path.is_file():
            raise SystemExit(f"Missing runtime file: {path}")
    results = json.loads((ROOT / "build-single" / VERSION / "test-results.json")
                         .read_text(encoding="utf-8-sig"))
    assert len(results) == 30 and all(item["Code"] == 0 for item in results)
    probe_ms = json.loads((ROOT / "build-single" / VERSION / "probe-results.json")
                          .read_text(encoding="utf-8-sig"))
    assert len(probe_ms) == 3 and all(isinstance(value, int) for value in probe_ms)
    sources = source_files()
    assert len(sources) == len({path.relative_to(ROOT).as_posix() for path in sources})
    assert not any("references" in path.parts for path in sources)
    SEALED.mkdir(parents=True)
    single = SEALED / f"SHDDesktop-{VERSION}.exe"
    shutil.copy2(CANDIDATE, single)
    runtime_name = f"SHDDesktop-{VERSION}-win64.zip"
    source_name = f"SHDDesktop-{VERSION}-source.zip"
    write_zip(SEALED / runtime_name, RUNTIME, f"SHDDesktop-{VERSION}")
    source_map = {path.relative_to(ROOT).as_posix(): path for path in sources}
    write_zip(SEALED / source_name, source_map, f"SHDDesktop-{VERSION}-source")
    packages = sorted({(dist.metadata["Name"], dist.version)
                       for dist in metadata.distributions()}, key=lambda item: item[0].casefold())
    lock_name = f"requirements-lock-{VERSION}.txt"
    (SEALED / lock_name).write_text(
        "".join(f"{name}=={version}\n" for name, version in packages), encoding="utf-8")
    note_name = "封版说明.md"
    (SEALED / note_name).write_text(f"""# SHD Desktop {VERSION} 单文件封版

日期：2026-10-12。旧版封版文件未覆盖。

## 交付内容

- `SHDDesktop-{VERSION}.exe`：可直接下载的单个 Windows 10/11 x64 可执行文件。首次启动会在当前用户的 `%LOCALAPPDATA%\\SHDDesktop\\Runtime` 缓存内层运行组件。
- `{runtime_name}`：只有一个程序 EXE，另含图标恢复脚本和说明文件。
- `{source_name}`：源码、测试、构建脚本和自有资源快照，不包含 `docs/design/references`。
- `{lock_name}`、`manifest.json`、`SHA256SUMS.txt`：构建依赖和校验信息。

单文件 EXE SHA256：`{detail(single)['sha256']}`。

## 验证范围

- 30 项回归脚本通过；发布 EXE 的 `--help`、`--smoke` 退出码为 0。
- 发布 EXE 对当前运行的 1.0.1 单实例 `--probe` 连续三次成功，耗时约 {', '.join(map(str, probe_ms))} 毫秒。
- 运行 ZIP 与源码 ZIP 已逐条校验文件 SHA256；缓存的内层程序 SHA256 与构建产物一致。
- 当前构建机为 Windows 11；Windows 10、双显示器热插拔、外部 LLM 和 QQ 音乐服务需要在试用设备上实测。
- 用户数据、密钥和登录凭据未纳入任何封版包。EXE 未签名。

升级时先从托盘正常退出旧版，再运行新 EXE，以便恢复桌面图标。QQMusicApi 的许可与上游用途限制需公司核查，参见 `THIRD_PARTY_NOTICES.md`。项目源码按用户要求暂不设置项目许可证。
""", encoding="utf-8")
    artifacts = [single.name, runtime_name, source_name, lock_name, note_name]
    manifest = {
        "version": VERSION,
        "status": "sealed-single-exe",
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "exe_sha256": detail(single)["sha256"],
        "artifacts": {name: detail(SEALED / name) for name in artifacts},
        "runtime_files": [{"path": name, **detail(path)} for name, path in RUNTIME.items()],
        "source_files": [{"path": name, **detail(path)} for name, path in source_map.items()],
        "validation": {
            "regression_scripts": len(results),
            "regression_failures": 0,
            "packaged_help_exit_code": 0,
            "packaged_smoke_exit_code": 0,
            "running_v1_0_1_probe_exit_code": 0,
            "running_v1_0_1_probe_ms": probe_ms,
        },
    }
    (SEALED / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (SEALED / "SHA256SUMS.txt").write_text(
        "".join(f"{detail(SEALED / name)['sha256']}  {name}\n"
                for name in sorted(artifacts + ["manifest.json"])), encoding="utf-8")
    for path in SEALED.iterdir():
        path.chmod(0o444)
    print(SEALED)
    print(f"source files: {len(sources)}; artifacts: {len(list(SEALED.iterdir()))}")


if __name__ == "__main__":
    main()
