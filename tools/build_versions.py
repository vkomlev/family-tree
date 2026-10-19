"""Собирает версии древа из истории git репозитория с данными.

Каждый коммит, менявший people.json, — отдельная версия:
  <out>/versions/<id>/people.json (+ people.<язык>.json, если есть в коммите)
  <out>/versions/index.json — список версий, новые сверху.
Удалённые версии перечислены в <репозиторий>/versions-hidden.json (короткие хеши коммитов) и пропускаются.

Запуск: python tools/build_versions.py <репозиторий-с-данными> <каталог-выкладки>
"""
from __future__ import annotations

import json
import logging
import pathlib
import subprocess
import sys

log = logging.getLogger(__name__)


def git(repo: pathlib.Path, *args: str) -> str:
    """Выполняет git в репозитории и возвращает stdout (UTF-8)."""
    res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
    return res.stdout.decode("utf-8")


def main() -> None:
    """Выгружает people*.json каждого коммита и пишет index.json."""
    repo, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    log_lines = git(repo, "log", "--format=%H%x09%cI%x09%s", "--", "people.json").splitlines()
    hidden_file = repo / "versions-hidden.json"
    hidden = set(json.loads(hidden_file.read_text(encoding="utf-8"))) if hidden_file.exists() else set()
    versions = []
    for line in log_lines:
        sha, date, subject = line.split("\t", 2)
        if sha[:7] in hidden:
            continue
        subject = subject.split(": ", 1)[-1]
        vid = date[:19].replace(":", "").replace("T", "-") + "-" + sha[:7]
        vdir = out / "versions" / vid
        vdir.mkdir(parents=True, exist_ok=True)
        files = [f for f in git(repo, "ls-tree", "--name-only", sha).split() if f.startswith("people") and f.endswith(".json")]
        count = 0
        for f in files:
            body = git(repo, "show", f"{sha}:{f}")
            (vdir / f).write_text(body, encoding="utf-8")
            if f == "people.json":
                count = len(json.loads(body)["people"])
        versions.append({"id": vid, "date": date, "message": subject, "people": count})
    (out / "versions").mkdir(parents=True, exist_ok=True)
    (out / "versions" / "index.json").write_text(json.dumps(versions, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("Версий: %s", len(versions))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
