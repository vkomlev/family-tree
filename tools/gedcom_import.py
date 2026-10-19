"""Импорт GEDCOM (5.5 / 5.5.1) в people.json.

  python tools/gedcom_import.py <файл.ged> <people.json>            — только отчёт, ничего не меняет
  python tools/gedcom_import.py <файл.ged> <people.json> --apply    — записать изменения

Что делает:
- сопоставляет людей из файла с уже записанными (фамилия или девичья + имя + отчество, при наличии — год рождения);
- новых людей добавляет, у найденных дописывает только ПУСТЫЕ поля (даты, места, родители, супруги);
- расхождения (в файле одно, у нас другое) не перезаписывает, а показывает в отчёте.
"""
from __future__ import annotations

import json
import logging
import pathlib
import re
import sys
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
TR = dict(zip("абвгдезийклмнопрстуфыэ", "abvgdeziyklmnoprstufye"))
TR.update({"ё": "e", "ж": "zh", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ю": "yu", "я": "ya", "ь": "", "ъ": ""})


@dataclass
class Indi:
    """Человек из GEDCOM."""
    xref: str
    given: str = ""
    surname: str = ""
    sex: str = ""
    birth: dict = field(default_factory=dict)
    death: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class Fam:
    """Семья из GEDCOM."""
    husb: str = ""
    wife: str = ""
    children: list[str] = field(default_factory=list)
    marr: dict = field(default_factory=dict)


def parse_date(s: str) -> str:
    """'12 JAN 1948' → 1948-01-12, 'JAN 1982' → 1982-01, 'ABT 1850' → ~1850."""
    s = s.strip().upper()
    approx = bool(re.match(r"^(ABT|EST|CAL|BEF|AFT)\b", s))
    s = re.sub(r"^(ABT|EST|CAL|BEF|AFT|FROM|TO)\s+", "", s)
    m = re.match(r"^(?:(\d{1,2})\s+)?(?:([A-Z]{3})\s+)?(\d{4})", s)
    if not m:
        return ""
    day, mon, year = m.groups()
    out = year
    if mon in MONTHS:
        out += f"-{MONTHS[mon]:02d}"
        if day:
            out += f"-{int(day):02d}"
    return ("~" if approx else "") + out


def read_gedcom(path: pathlib.Path) -> tuple[dict[str, Indi], list[Fam]]:
    """Разбирает файл на людей и семьи (CONC/CONT в заметках склеиваются)."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1251"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    indis: dict[str, Indi] = {}
    fams: list[Fam] = []
    cur: Indi | Fam | None = None
    ev: dict | None = None
    note: list[str] | None = None
    for line in text.splitlines():
        m = re.match(r"^\s*(\d+)\s+(@[^@]+@\s+)?(\w+)\s?(.*)$", line)
        if not m:
            continue
        lvl, xref, tag, val = int(m[1]), (m[2] or "").strip(), m[3], m[4].strip()
        if lvl == 0:
            ev = note = None
            cur = Indi(xref) if tag == "INDI" else Fam() if tag == "FAM" else None
            if isinstance(cur, Indi):
                indis[xref] = cur
            elif isinstance(cur, Fam):
                fams.append(cur)
            continue
        if cur is None:
            continue
        if lvl == 1:
            ev = note = None
            if isinstance(cur, Indi):
                if tag == "NAME":
                    nm = re.match(r"^(.*?)/(.*?)/", val + "//")
                    cur.given, cur.surname = nm[1].strip(), nm[2].strip()
                elif tag == "SEX":
                    cur.sex = {"M": "m", "F": "f"}.get(val[:1].upper(), "")
                elif tag in ("BIRT", "DEAT"):
                    ev = cur.birth if tag == "BIRT" else cur.death
                elif tag == "NOTE" and not val.startswith("@"):
                    cur.notes.append(val)
                    note = cur.notes
            else:
                if tag == "HUSB":
                    cur.husb = val
                elif tag == "WIFE":
                    cur.wife = val
                elif tag == "CHIL":
                    cur.children.append(val)
                elif tag == "MARR":
                    ev = cur.marr
        elif lvl == 2:
            if isinstance(cur, Indi) and tag in ("GIVN", "SURN") and val:
                setattr(cur, "given" if tag == "GIVN" else "surname", val)
            elif ev is not None and tag == "DATE":
                ev["date"] = parse_date(val)
            elif ev is not None and tag == "PLAC":
                ev["place"] = val
            elif note is not None and tag in ("CONC", "CONT"):
                note[-1] += ("\n" if tag == "CONT" else "") + val
    return indis, fams


def split_given(given: str) -> tuple[str, str]:
    """'Иван Петрович' → ('Иван', 'Петрович'), если второе слово похоже на отчество."""
    parts = given.split()
    if len(parts) >= 2 and re.search(r"(вич|вна|ична|чна|ич|кызы|оглы)$", parts[-1], re.I):
        return " ".join(parts[:-1]), parts[-1]
    return given, ""


def key(name: str, patr: str, surname: str) -> str:
    """Ключ сравнения: без регистра, ё=е."""
    return " ".join(x.lower().replace("ё", "е") for x in (surname, name, patr) if x)


def slug(s: str) -> str:
    """Идентификатор латиницей из фамилии и имени."""
    out = "".join(TR.get(c, c) for c in s.lower())
    return re.sub(r"[^a-z0-9]+", "-", out).strip("-") or "person"


def year(d: dict | None) -> str:
    """Год из события."""
    m = re.search(r"\d{4}", (d or {}).get("date", ""))
    return m[0] if m else ""


def main() -> None:
    """Сопоставляет, добавляет, дописывает, печатает отчёт."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    ged, target, apply = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), "--apply" in sys.argv
    data = json.loads(target.read_text(encoding="utf-8"))
    people = {p["id"]: p for p in data["people"]}
    index: dict[str, list[str]] = {}
    for p in people.values():
        for sur in {p.get("surname", ""), p.get("maiden", "")} - {""}:
            index.setdefault(key(p.get("name", ""), p.get("patronymic", ""), sur), []).append(p["id"])
    indis, fams = read_gedcom(ged)
    mapping: dict[str, str] = {}
    added, filled, conflicts = [], [], []

    def fill(p: dict, k: str, v, label: str) -> None:
        """Дописывает поле, если оно пустое; иначе фиксирует расхождение."""
        if not v:
            return
        if not p.get(k):
            p[k] = v
            filled.append(f"{label}: {k}")
        elif p[k] != v and not (isinstance(v, dict) and all(p[k].get(a) == b for a, b in v.items())):
            if isinstance(v, dict):
                for a, b in v.items():
                    if not p[k].get(a):
                        p[k][a] = b
                        filled.append(f"{label}: {k}.{a}")
                    elif p[k][a] != b:
                        conflicts.append(f"{label}: {k}.{a} — у нас «{p[k][a]}», в файле «{b}»")
            else:
                conflicts.append(f"{label}: {k} — у нас «{p[k]}», в файле «{v}»")

    for x, i in indis.items():
        name, patr = split_given(i.given)
        cands = index.get(key(name, patr, i.surname), [])
        if not cands:
            # мягкое сравнение: фамилия + имя совпали, а отчество есть только с одной стороны
            loose = key(name, "", i.surname)
            cands = [pid for k, ids in index.items() if k == loose or (not patr and k.startswith(loose + " "))
                     for pid in ids if not patr or not people[pid].get("patronymic")]
            cands = list(dict.fromkeys(cands))
        y = year(i.birth)
        cands = [c for c in cands if not y or not year(people[c].get("birth")) or year(people[c].get("birth")) == y]
        label = f"{i.surname} {i.given}".strip()
        if len(cands) == 1:
            pid = cands[0]
            p = people[pid]
            fill(p, "sex", i.sex, label)
            fill(p, "patronymic", patr, label)
            fill(p, "birth", i.birth, label)
            fill(p, "death", i.death, label)
        else:
            if len(cands) > 1:
                conflicts.append(f"{label}: несколько похожих ({', '.join(cands)}) — добавлен как новый, проверить вручную")
            pid = base = slug(f"{i.surname} {name}")
            n = 2
            while pid in people:
                pid, n = f"{base}-{n}", n + 1
            p = {"id": pid, "surname": i.surname, "name": name, "sex": i.sex}
            if patr:
                p["patronymic"] = patr
            for k in ("birth", "death"):
                if getattr(i, k):
                    p[k] = getattr(i, k)
            if i.notes:
                p["notes"] = " ".join(i.notes)
            p["sources"] = [f"GEDCOM: {ged.name}"]
            by = year(i.birth)
            if not i.death and (not by or int(by) > 1915):
                p["living"] = True  # даты живых на сайте скрыты
            people[pid] = p
            data["people"].append(p)
            added.append(f"{label} → {pid}")
        mapping[x] = pid

    for f in fams:
        h, w = mapping.get(f.husb), mapping.get(f.wife)
        for c in f.children:
            cp = people.get(mapping.get(c, ""))
            if not cp:
                continue
            for k, v in (("father", h), ("mother", w)):
                fill(cp, k, v, f"{cp.get('surname', '')} {cp.get('name', '')}")
        if h and w:
            hp = people[h]
            sp = hp.get("spouses", [])
            wsp = [s["id"] for s in people[w].get("spouses", [])]
            if not any(s["id"] == w for s in sp) and h not in wsp:
                hp.setdefault("spouses", []).append({"id": w, **f.marr})
                filled.append(f"{hp['surname']} {hp['name']}: супруг(а) {people[w]['name']}")

    print(f"Файл: {ged.name}. Людей в файле: {len(indis)}, семей: {len(fams)}.")
    print(f"\nНовые ({len(added)}):", *added, sep="\n  ")
    print(f"\nДописано ({len(filled)}):", *filled, sep="\n  ")
    print(f"\nРасхождения — не тронуты ({len(conflicts)}):", *conflicts, sep="\n  ")
    if apply:
        target.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nЗаписано в {target}.")
    else:
        print("\nЭто проверка. Чтобы записать — добавьте --apply.")


if __name__ == "__main__":
    main()
