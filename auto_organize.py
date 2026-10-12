"""Classify desktop entries without changing their filesystem location."""

from pathlib import Path


TYPES = (
    ("文件夹", "cat-all-gen-64.png", set()),
    ("文档", "cat-intel-gen-64.png", {".txt", ".md", ".pdf", ".doc", ".docx", ".rtf", ".odt", ".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".epub"}),
    ("图片", "cat-media-gen-64.png", {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic"}),
    ("音乐", "cat-media-gen-64.png", {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".wma"}),
    ("视频", "cat-media-gen-64.png", {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".m4v"}),
    ("压缩包", "cat-logistics-gen-64.png", {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"}),
    ("快捷方式", "cat-network-gen-64.png", {".lnk", ".url", ".exe", ".msi", ".bat", ".cmd", ".ps1"}),
    ("其他", "cat-all-gen-64.png", set()),
)


def classify(path: Path) -> str:
    if path.is_dir():
        return "文件夹"
    suffix = path.suffix.casefold()
    for name, _, extensions in TYPES[1:-1]:
        if suffix in extensions:
            return name
    return "其他"


def icon_for_type(name: str) -> str:
    return next(icon for kind, icon, _ in TYPES if kind == name)
