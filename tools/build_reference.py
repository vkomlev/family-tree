"""Собирает справочник docs/reference.md из site/people.json.

Запуск: python tools/build_reference.py
"""
from __future__ import annotations

import json
import logging
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
log = logging.getLogger(__name__)


def fmt(date: str | None) -> str:
    """Переводит ГГГГ-ММ-ДД в ДД.ММ.ГГГГ, остальное оставляет как есть."""
    if not date:
        return ""
    m = re.fullmatch(r"(\d{4})-(\d\d)-(\d\d)", date)
    if m:
        return f"{m[3]}.{m[2]}.{m[1]}"
    m = re.fullmatch(r"(\d{4})-(\d\d)", date)
    return f"{m[2]}.{m[1]}" if m else date


def full(p: dict) -> str:
    """Полное имя с девичьей фамилией."""
    name = " ".join(x for x in (p.get("surname"), p.get("name"), p.get("patronymic")) if x)
    return f"{name} ({p['maiden']})" if p.get("maiden") else name


def event(e: dict | None) -> str:
    """Дата, место и причина события одной строкой."""
    if not e:
        return ""
    return ", ".join(x for x in (fmt(e.get("date")), e.get("place"), e.get("cause")) if x)


def main() -> None:
    """Читает JSON и пишет markdown-справочник, сгруппированный по фамилиям."""
    src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "site" / "people.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    out = src.parent / "docs" / "reference.md"
    people = {p["id"]: p for p in data["people"]}
    lines = [f"# Справочник: {data['meta']['title']}", "",
             f"Обновлено: {data['meta']['updated']}. Источник истины — `people.json`; файл собран скриптом.", ""]
    by_family: dict[str, list[dict]] = {}
    for p in people.values():
        by_family.setdefault(p.get("maiden") or p["surname"], []).append(p)
    for fam in sorted(by_family):
        lines += [f"## {fam}", ""]
        for p in sorted(by_family[fam], key=lambda x: x.get("birth", {}).get("date", "~").lstrip("~")):
            lines.append(f"### {full(p)}")
            for label, key in (("Рождение", "birth"), ("Смерть", "death")):
                if event(p.get(key)):
                    lines.append(f"- {label}: {event(p.get(key))}")
            for label, key in (("Отец", "father"), ("Мать", "mother")):
                if p.get(key) in people:
                    lines.append(f"- {label}: {full(people[p[key]])}")
            for s in p.get("spouses", []):
                extra = ", ".join(x for x in (fmt(s.get("date")), s.get("place")) if x)
                lines.append(f"- Супруг(а): {full(people[s['id']])}" + (f" — брак {extra}" if extra else ""))
            if p.get("notes"):
                lines.append(f"- Заметки: {p['notes']}")
            for src in p.get("sources", []):
                lines.append(f"- Источник: {src}")
            lines.append("")
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    log.info("Записано %s человек в %s", len(people), out)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
