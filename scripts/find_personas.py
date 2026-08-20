#!/usr/bin/env python3
"""
페르소나 검색기 — 네트워크가 필요 없다. 표준 라이브러리만 쓴다.

확장 팩(L2, references/extended-pack/personas.jsonl)에서 조건에 맞는 사람을 찾아
페르소나 카드로 출력한다. 확장 팩이 없으면 그 사실을 알리고 코어 팩(L1)을 안내한다.

사용법
  # 조건 검색
  python find_personas.py --tag '#1인사업자' --age 30-50 -n 5
  python find_personas.py --occupation 부동산 --province 부산 -n 3
  python find_personas.py --keyword 배달 --exclude-tag '#비경제활동' -n 5

  # 패널 자동 구성 (핵심2 + 경계2 + 비사용자1)
  python find_personas.py --panel --age 30-50 --tag '#1인사업자' --province 서울

  # 인덱스만 (표 형태)
  python find_personas.py --tag '#저디지털' --format index -n 20
"""

import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.normpath(os.path.join(HERE, "..", "references", "extended-pack", "personas.jsonl"))
CORE = os.path.normpath(os.path.join(HERE, "..", "references", "core-pack.md"))

NARRATIVE_KEYS = (
    "persona", "professional_persona", "family_persona", "culinary_persona",
    "travel_persona", "arts_persona", "sports_persona", "cultural_background",
    "hobbies_and_interests", "skills_and_expertise", "career_goals_and_ambitions",
)


def load(path):
    if not os.path.exists(path):
        print("확장 팩(L2)이 아직 없습니다.\n", file=sys.stderr)
        print(f"  없는 파일: {path}\n", file=sys.stderr)
        print("두 가지 중 하나를 하세요:", file=sys.stderr)
        print("  1) 코어 팩(L1) 35명으로 진행  →  " + CORE, file=sys.stderr)
        print("  2) 확장 팩을 한 번 만들기 (Claude Code, 네트워크 필요):", file=sys.stderr)
        print("       pip install datasets", file=sys.stderr)
        print("       python scripts/build_extended_pack.py", file=sys.stderr)
        sys.exit(2)
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def parse_age(s):
    if not s:
        return None
    if "-" in s:
        a, b = s.split("-", 1)
        return int(a), int(b)
    v = int(s)
    return v, v


def blob(r):
    return " ".join(str(r.get(k) or "") for k in NARRATIVE_KEYS)


def conditions_from(args):
    """조건을 개별 함수로 분해한다. 패널 구성에서 '몇 개가 어긋났는지' 세기 위해."""
    conds = []
    rng = parse_age(args.age)
    if rng:
        conds.append(("age", lambda r: rng[0] <= (r.get("age") or -1) <= rng[1]))
    if args.sex:
        conds.append(("sex", lambda r: (r.get("sex") or "") == args.sex))
    if args.province:
        conds.append(("province", lambda r: args.province in str(r.get("province") or "")))
    if args.district:
        conds.append(("district", lambda r: args.district in str(r.get("district") or "")))
    if args.occupation:
        conds.append(("occupation", lambda r: args.occupation in str(r.get("occupation") or "")))
    if args.seg:
        conds.append(("seg", lambda r: (r.get("segment") or "") == args.seg.upper()))
    for t in (args.tag or []):
        conds.append((f"tag{t}", lambda r, t=t: t in (r.get("tags") or [])))
    if args.keyword:
        conds.append(("keyword", lambda r: args.keyword in blob(r)))
    return conds


def hard_filters(rows, args):
    """제외 조건은 어떤 자리에서도 무시하지 않는다."""
    out = rows
    for t in (args.exclude_tag or []):
        out = [r for r in out if t not in (r.get("tags") or [])]
    return out


def match_count(r, conds):
    return sum(1 for _, fn in conds if fn(r))


def card(r):
    lines = [
        f"### {r['id']}. {r['age']}세 {r.get('sex','')} · {r.get('occupation','')} · "
        f"{r.get('province','')} {r.get('district','')}",
        f"- 태그: {' '.join(r.get('tags') or [])}",
        f"- 종합: {r.get('persona','')}",
    ]
    for key, label in (
        ("professional_persona", "일"),
        ("family_persona", "가족·주거"),
        ("culinary_persona", "소비·식습관"),
        ("hobbies_and_interests", "취미·일상"),
        ("cultural_background", "성향·배경"),
        ("career_goals_and_ambitions", "목표"),
    ):
        v = r.get(key)
        if v:  # 값이 없으면 줄 자체를 뺀다. 빈칸으로 두고 지어내지 않기 위해.
            lines.append(f"- {label}: {v}")
    lines.append("")
    return "\n".join(lines)


def index_table(rows):
    out = ["| ID | 나이 | 성별 | 직업 | 지역 | 태그 |", "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['id']} | {r['age']} | {r.get('sex','')} | {r.get('occupation','')} | "
                   f"{r.get('province','')} {r.get('district','')} | {' '.join(r.get('tags') or [])} |")
    return "\n".join(out)


def run_panel(rows, conds, rnd):
    """핵심 2 + 경계 2 + 비사용자 1."""
    n = len(conds)
    if n == 0:
        sys.exit("패널 구성에는 조건이 최소 1개 필요합니다 (--age / --tag / --occupation 등).")

    scored = [(match_count(r, conds), r) for r in rows]
    core = [r for c, r in scored if c == n]
    edge = [r for c, r in scored if c == n - 1]
    out = [r for c, r in scored if c <= max(0, n - 2)]

    def take(pool, k, used):
        pool = [r for r in pool if r["id"] not in used]
        rnd.shuffle(pool)
        # 직업·지역이 겹치지 않게 우선 선택
        chosen, seen = [], set()
        for r in pool:
            key = (r.get("occupation"), r.get("province"))
            if key in seen:
                continue
            seen.add(key)
            chosen.append(r)
            if len(chosen) == k:
                break
        while len(chosen) < k and pool:  # 다양성 확보가 안 되면 그냥 채운다
            r = pool.pop(0)
            if r not in chosen:
                chosen.append(r)
        return chosen

    used, panel = set(), []
    for label, pool, k in (("핵심", core, 2), ("경계", edge, 2), ("비사용자", out, 1)):
        got = take(pool, k, used)
        for r in got:
            used.add(r["id"])
            panel.append((label, r))
        if len(got) < k:
            print(f"⚠️  '{label}' 자리 {k}명 중 {len(got)}명만 찾았습니다 "
                  f"(후보 {len(pool)}명). 조건을 완화하거나 확장 팩을 키우세요.", file=sys.stderr)

    print(f"## 패널 스냅샷 (조건 {n}개)\n")
    print("| 자리 | ID | 나이·성별 | 직업 | 지역 | 태그 |")
    print("|---|---|---|---|---|---|")
    for label, r in panel:
        print(f"| {label} | {r['id']} | {r['age']} {r.get('sex','')} | {r.get('occupation','')} | "
              f"{r.get('province','')} {r.get('district','')} | {' '.join(r.get('tags') or [])} |")
    print("\n---\n")
    for label, r in panel:
        print(f"**[{label}]**")
        print(card(r))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--age", help="나이 또는 범위 (예: 35 또는 30-50)")
    p.add_argument("--sex", choices=["남자", "여자", "남", "여"])
    p.add_argument("--province", help="시도 (예: 서울, 부산)")
    p.add_argument("--district", help="시군구")
    p.add_argument("--occupation", help="직업 키워드")
    p.add_argument("--seg", help="세그먼트 A~E")
    p.add_argument("--tag", action="append", help="태그 (여러 번 사용 가능)")
    p.add_argument("--exclude-tag", action="append", help="제외할 태그")
    p.add_argument("--keyword", help="페르소나 서술 전체에서 찾을 키워드")
    p.add_argument("--panel", action="store_true", help="5인 패널 자동 구성")
    p.add_argument("-n", "--n", type=int, default=5, help="출력 인원 (기본 5)")
    p.add_argument("--format", choices=["card", "index"], default="card")
    p.add_argument("--seed", type=int, default=817, help="난수 씨앗 — 같은 씨앗이면 같은 결과")
    p.add_argument("--pack", default=PACK)
    args = p.parse_args()

    rows = hard_filters(load(args.pack), args)
    conds = conditions_from(args)
    rnd = random.Random(args.seed)

    if args.panel:
        run_panel(rows, conds, rnd)
        return

    hits = [r for r in rows if match_count(r, conds) == len(conds)]
    if not hits:
        # 완전 일치가 없으면 가장 가까운 순으로 보여주되, 격차를 명시한다.
        scored = sorted(((match_count(r, conds), r) for r in rows),
                        key=lambda x: -x[0])[:args.n]
        if not scored or scored[0][0] == 0:
            sys.exit("조건에 맞는 페르소나가 없습니다. 조건을 완화해 보세요.")
        print(f"⚠️  조건 {len(conds)}개를 모두 만족하는 사람이 없습니다. "
              f"가장 가까운 {len(scored)}명을 보여줍니다.\n"
              f"   → 사용할 때 어떤 조건이 어긋나는지 반드시 명시하세요.\n")
        hits = [r for _, r in scored]
    else:
        rnd.shuffle(hits)
        hits = hits[:args.n]

    if args.format == "index":
        print(index_table(hits))
    else:
        for r in hits:
            print(card(r))


if __name__ == "__main__":
    main()
