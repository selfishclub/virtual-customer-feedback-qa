#!/usr/bin/env python3
"""
확장 팩(L2) 생성기 — 딱 한 번만 실행하면 된다.

nvidia/Nemotron-Personas-Korea(100만 명)에서 세그먼트 균형을 맞춰
수천 명을 뽑고, 네트워크 없이 검색할 수 있는 로컬 팩으로 저장한다.

두 가지 방법 중 하나로 원본을 읽는다.

  A. 허깅페이스 스트리밍 (네트워크 필요)
       pip install datasets
       python build_extended_pack.py

  B. 로컬 parquet 읽기 (네트워크 불필요)  ← 방화벽 환경에서 이 방법
       # https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea/tree/main/data
       # 에서 train-0000X-of-00009.parquet 을 1개 이상 내려받은 뒤
       pip install pyarrow
       python build_extended_pack.py --local ./data/train-00000-of-00009.parquet
       python build_extended_pack.py --local ./data          # 폴더 전체
       python build_extended_pack.py --local './data/*.parquet'

  샤드 1개(약 220MB)에 11만 명이 들어 있어 3,000명을 뽑기에 충분하다.

기타 옵션
  --total 5000                총 인원
  --balance business          표집 방식 (even/business/natural/custom)
  --scan-limit 400000         빨리 끝내고 싶을 때

산출물 (references/extended-pack/)
  personas.jsonl     전체 레코드 (검색 원본)
  _index.tsv         한 줄 요약 인덱스 (grep용)
  _index_<SEG>.tsv   세그먼트별 인덱스
  quickref-300.md    300명 한 줄 요약 — 스크립트를 못 쓰는 환경(Chat)용
  MANIFEST.md        생성 조건·통계
"""

import argparse
import glob
import json
import os
import random
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "references", "extended-pack"))

SEGMENTS = ["A", "B", "C", "D", "E"]
SEG_LABEL = {
    "A": "2030 싱글·직장인·취준",
    "B": "3040 부모·가족 중심",
    "C": "1인 사업자·자영업·전문직",
    "D": "4050 직장인·전문직",
    "E": "5060+ 시니어·저디지털",
}

# 표집 방식. 자세한 설명은 references/SPEC.md 5장.
#   even    — 세그먼트 균등. 소수 집단을 만날 확률이 올라가 blind spot 발굴에 유리
#   natural — 정원 없이 원본 순서대로. 원 데이터 분포에 가깝다
#   custom  — --weights 로 직접 지정
BALANCE_PRESETS = {
    "even": {"A": 0.20, "B": 0.20, "C": 0.20, "D": 0.20, "E": 0.20},
    "business": {"A": 0.20, "B": 0.18, "C": 0.32, "D": 0.15, "E": 0.15},
}
DEFAULT_WEIGHTS = BALANCE_PRESETS["even"]

# 1인 사업자·자영업·프리랜서·개업 전문직.
# 이 데이터의 직업 분류는 KSCO(한국표준직업분류) 계열이라 표현이 정형화되어 있다.
# 고용된 판매직(그 외 일반 영업원, 상점 판매원, 매장 계산원 등)은 일부러 제외한다.
RE_SELF_EMPLOYED = re.compile(
    r"자영|사업|대표이사|사장|원장|점주|점장|프리랜|개인\s*사업|창업|"
    r"소규모\s*상점|노점|온라인\s*쇼핑\s*판매|스마트스토어|온라인\s*판매|"
    r"부동산|공인중개|중개사|중개인|감정\s*전문가|경매사|"
    r"컨설턴트|미용사|미용실|카페\s*운영|"
    r"시간강사|방문강사|강사\s*및\s*트레이너|"
    r"디자이너|작가"
)
RE_INACTIVE = re.compile(r"무직|주부|학생|구직|취업\s*준비|퇴직|은퇴|실업")
RE_CHILDREN = re.compile(r"아이|자녀|육아|아들|딸|초등|유치원|어린이집")
RE_HIGH_DIGITAL = re.compile(
    r"엑셀|스프레드시트|앱\s*개발|프로그래|코딩|디자인\s*툴|프리미어|포토샵|"
    r"블로그\s*운영|스마트스토어|SNS\s*마케팅|데이터|IT|소프트웨어|네트워크|보안"
)
RE_LOW_DIGITAL = re.compile(r"종이|손편지|돋보기|라디오|TV|텔레비전|신문")
# 넓게 잡으면 절반이 걸려 필터로 못 쓴다. 문서를 실제로 "읽는" 신호만 남긴다.
RE_METICULOUS = re.compile(r"약관|계약서|보증서|법령|법규|조항|세칙|약정서")
RE_SECURITY = re.compile(r"보안|개인정보|해킹|암호")
RE_THRIFTY = re.compile(r"가계부|알뜰|절약|십\s*원|중고|가성비")
RE_SKEPTIC = re.compile(r"검증|신중|의심|따져|회의")


def pick_segment(age: int, occupation: str, family_blob: str) -> str:
    """세그먼트 판정. 우선순위: C(직업) > E(연령) > B(자녀) > A/D(연령)."""
    if RE_SELF_EMPLOYED.search(occupation):
        return "C"
    if age >= 60:
        return "E"
    if 25 <= age <= 49 and RE_CHILDREN.search(family_blob):
        return "B"
    if age <= 39:
        return "A"
    return "D"


def build_tags(r: dict, blob: str, family_blob: str = "") -> list:
    """검색용 태그. 데이터에 없는 속성(소득 등)은 만들지 않는다."""
    occ = r.get("occupation") or ""
    age = r.get("age") or 0
    tags = []

    if RE_SELF_EMPLOYED.search(occ):
        tags.append("#1인사업자")
    elif RE_INACTIVE.search(occ):
        tags.append("#비경제활동")
    else:
        tags.append("#직장인")

    if "창업" in blob:
        tags.append("#창업준비")
    # 육아는 가족 서술 + 양육 가능 연령대일 때만. 전체 서술로 잡으면
    # 본인의 어린 시절·형제 이야기까지 걸린다.
    if 25 <= age <= 55 and RE_CHILDREN.search(family_blob or blob):
        tags.append("#육아")

    if RE_HIGH_DIGITAL.search(blob):
        tags.append("#고디지털")
    elif RE_LOW_DIGITAL.search(blob) or age >= 65:
        tags.append("#저디지털")

    if age >= 70:
        tags.append("#접근성")
    if RE_METICULOUS.search(blob):
        tags.append("#약관정독")
    if RE_SECURITY.search(blob):
        tags.append("#보안민감")
    if RE_THRIFTY.search(blob):
        tags.append("#가격깐깐")
    if RE_SKEPTIC.search(blob):
        tags.append("#테크회의론")

    # 소득(#고소득/#저소득)은 공개판에 해당 필드가 없어 생성하지 않는다.
    # 추정으로 붙이면 모드 I4(가격)에서 잘못된 근거가 된다.
    return sorted(set(tags))


def open_stream(args):
    """레코드 이터레이터를 연다. 두 경로 중 하나.

    --local 이 있으면 로컬 parquet을 읽는다 (네트워크 불필요).
    없으면 허깅페이스에서 스트리밍한다 (네트워크 필요).
    """
    if args.local:
        try:
            import pyarrow.parquet as pq
        except ImportError:
            sys.exit("pyarrow가 필요합니다:  pip install pyarrow")

        paths = []
        if os.path.isdir(args.local):
            paths = sorted(os.path.join(args.local, f)
                           for f in os.listdir(args.local) if f.endswith(".parquet"))
        else:
            paths = sorted(glob.glob(args.local))
        if not paths:
            sys.exit(f"parquet 파일을 찾지 못했습니다: {args.local}")
        print(f"로컬 parquet {len(paths)}개를 읽습니다:")
        for p in paths:
            print(f"  - {os.path.basename(p)} ({os.path.getsize(p)/1024/1024:.0f} MB)")

        def gen():
            for p in paths:
                pf = pq.ParquetFile(p)
                for batch in pf.iter_batches(batch_size=2048):
                    for row in batch.to_pylist():
                        yield row
        return gen()

    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit("datasets 라이브러리가 필요합니다:  pip install datasets\n"
                 "(네트워크가 막힌 환경이라면 parquet을 내려받아 --local 로 지정하세요)")
    print("허깅페이스 데이터셋 연결 중… (첫 실행은 시간이 걸립니다)")
    return load_dataset("nvidia/Nemotron-Personas-Korea", split="train", streaming=True)


def one_line(txt: str, limit: int = 90) -> str:
    txt = re.sub(r"\s+", " ", (txt or "")).strip()
    return txt[:limit] + ("…" if len(txt) > limit else "")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--total", type=int, default=3000, help="총 인원 (기본 3000)")
    p.add_argument("--scan-limit", type=int, default=0,
                   help="최대 스캔 건수. 0이면 채워질 때까지 (기본 0)")
    p.add_argument("--seed", type=int, default=817, help="난수 씨앗 — 재현성 보장")
    p.add_argument("--balance", choices=["even", "business", "natural", "custom"],
                   default="even",
                   help="표집 방식. even=세그먼트 균등(기본) / business=1인사업자 중심 / "
                        "natural=원본 분포 그대로 / custom=--weights 사용")
    p.add_argument("--weights", help="custom일 때. 예: A=0.15,B=0.15,C=0.4,D=0.15,E=0.15")
    p.add_argument("--local", help="로컬 parquet 경로 (파일·글롭·디렉터리). 지정하면 네트워크를 쓰지 않는다")
    p.add_argument("--out", default=OUT_DIR)
    args = p.parse_args()

    random.seed(args.seed)

    if args.balance == "custom":
        if not args.weights:
            sys.exit("--balance custom 을 쓰려면 --weights 가 필요합니다.")
        w = {}
        for part in args.weights.split(","):
            k, v = part.split("=")
            w[k.strip().upper()] = float(v)
        missing = [s for s in SEGMENTS if s not in w]
        if missing:
            sys.exit(f"--weights 에 빠진 세그먼트: {missing}")
        total_w = sum(w.values())
        weights = {s: w[s] / total_w for s in SEGMENTS}
    elif args.balance == "natural":
        weights = None  # 정원 없음. 원본 순서대로 담는다
    else:
        weights = BALANCE_PRESETS[args.balance]

    ds = open_stream(args)

    if weights is None:
        # 원본 분포를 따르므로 세그먼트별 상한을 총원으로 열어둔다
        quota = {s: args.total for s in SEGMENTS}
        print(f"표집: natural (원본 분포 그대로) · 총 {args.total}명")
    else:
        quota = {s: max(1, round(args.total * weights[s])) for s in SEGMENTS}
        print(f"표집: {args.balance} · 세그먼트 목표치: {quota}")
    picked = {s: [] for s in SEGMENTS}
    seen_occ = Counter()
    scanned = 0

    for r in ds:
        scanned += 1
        if sum(len(v) for v in picked.values()) >= args.total:
            break
        if args.scan_limit and scanned > args.scan_limit:
            print(f"\n스캔 상한({args.scan_limit:,})에 도달했습니다.")
            break

        try:
            age = int(r.get("age") or 0)
        except (TypeError, ValueError):
            continue
        occ = (r.get("occupation") or "").strip()
        if not occ or age <= 0:
            continue

        family_blob = " ".join(str(r.get(k) or "") for k in ("family_persona", "family_type"))
        seg = pick_segment(age, occ, family_blob)
        if len(picked[seg]) >= quota[seg]:
            if all(len(picked[s]) >= quota[s] for s in SEGMENTS):
                break
            continue

        # 같은 직업이 팩을 잠식하지 않게 (세그먼트 정원의 5% 상한, 최소 3명)
        if seen_occ[occ] >= max(3, quota[seg] // 20):
            continue

        blob = " ".join(str(r.get(k) or "") for k in (
            "persona", "professional_persona", "family_persona", "culinary_persona",
            "hobbies_and_interests", "skills_and_expertise", "cultural_background",
            "career_goals_and_ambitions",
        ))
        tags = build_tags(r, blob, family_blob)
        pid = f"{seg}{len(picked[seg]) + 1:04d}"

        picked[seg].append({
            "id": pid,
            "segment": seg,
            "age": age,
            "sex": r.get("sex"),
            "occupation": occ,
            "province": r.get("province"),
            "district": r.get("district"),
            "education_level": r.get("education_level"),
            "marital_status": r.get("marital_status"),
            "family_type": r.get("family_type"),
            "housing_type": r.get("housing_type"),
            "tags": tags,
            "persona": r.get("persona"),
            "professional_persona": r.get("professional_persona"),
            "family_persona": r.get("family_persona"),
            "culinary_persona": r.get("culinary_persona"),
            "travel_persona": r.get("travel_persona"),
            "arts_persona": r.get("arts_persona"),
            "sports_persona": r.get("sports_persona"),
            "cultural_background": r.get("cultural_background"),
            "hobbies_and_interests": r.get("hobbies_and_interests"),
            "skills_and_expertise": r.get("skills_and_expertise"),
            "career_goals_and_ambitions": r.get("career_goals_and_ambitions"),
        })
        seen_occ[occ] += 1

        done = sum(len(v) for v in picked.values())
        if done % 100 == 0:
            print(f"  수집 {done}/{args.total}  (스캔 {scanned:,}건)  "
                  + " ".join(f"{s}:{len(picked[s])}" for s in SEGMENTS))

    rows = [x for s in SEGMENTS for x in picked[s]]
    if not rows:
        sys.exit("수집된 레코드가 없습니다. 네트워크와 데이터셋 접근을 확인하세요.")

    os.makedirs(args.out, exist_ok=True)

    # 1) 전체 레코드
    with open(os.path.join(args.out, "personas.jsonl"), "w", encoding="utf-8") as f:
        for x in rows:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

    # 2) 인덱스 (전체 + 세그먼트별)
    header = "id\tseg\tage\tsex\toccupation\tprovince\tdistrict\ttags\tsummary\n"

    def idx_line(x):
        return "\t".join([
            x["id"], x["segment"], str(x["age"]), str(x["sex"] or ""),
            str(x["occupation"] or ""), str(x["province"] or ""), str(x["district"] or ""),
            " ".join(x["tags"]), one_line(x["persona"], 70),
        ]) + "\n"

    with open(os.path.join(args.out, "_index.tsv"), "w", encoding="utf-8") as f:
        f.write(header)
        for x in rows:
            f.write(idx_line(x))

    for s in SEGMENTS:
        with open(os.path.join(args.out, f"_index_{s}.tsv"), "w", encoding="utf-8") as f:
            f.write(header)
            for x in picked[s]:
                f.write(idx_line(x))

    # 3) 퀵레퍼런스 300명 — 스크립트를 못 쓰는 환경에서 통째로 읽는 용도
    quick = []
    for s in SEGMENTS:
        if not picked[s]:
            continue
        n = max(1, round(300 * len(picked[s]) / len(rows)))  # 실제 수집 비율대로
        quick += random.sample(picked[s], min(n, len(picked[s])))
    with open(os.path.join(args.out, "quickref-300.md"), "w", encoding="utf-8") as f:
        f.write("# 퀵레퍼런스 (L1.5 · %d명)\n\n" % len(quick))
        f.write("스크립트를 실행할 수 없는 환경에서 이 파일을 통째로 읽어 쓴다.\n")
        f.write("상세가 필요하면 `personas.jsonl`에서 같은 ID를 찾는다.\n\n")
        for s in SEGMENTS:
            part = [x for x in quick if x["segment"] == s]
            if not part:
                continue
            f.write(f"\n## {s} — {SEG_LABEL[s]} ({len(part)}명)\n\n")
            for x in part:
                f.write(f"- **{x['id']}** {x['age']}세 {x['sex']} · {x['occupation']} · "
                        f"{x['province']} {x['district']} · {' '.join(x['tags'])}\n")

    # 4) 매니페스트
    tag_count = Counter(t for x in rows for t in x["tags"])
    with open(os.path.join(args.out, "MANIFEST.md"), "w", encoding="utf-8") as f:
        f.write("# 확장 팩 매니페스트\n\n")
        f.write("출처: nvidia/Nemotron-Personas-Korea (CC BY 4.0)\n\n")
        f.write(f"- 총원: **{len(rows)}명** / 원본 100만 명 "
                f"(커버리지 {len(rows)/1_000_000*100:.2f}%)\n")
        f.write(f"- 표집 방식: **{args.balance}**"
                + (f" (`{args.weights}`)" if args.balance == "custom" else "") + "\n")
        f.write(f"- 스캔: {scanned:,}건\n- 씨앗: {args.seed}\n")
        f.write(f"- 고유 직업: {len(seen_occ)}종\n\n")
        f.write("> ⚠️ 확률 표본이 아니다. 비율·빈도로 해석하지 않는다. "
                "자세한 한계는 `references/SPEC.md` 참조.\n\n")
        f.write("## 세그먼트\n\n| 코드 | 이름 | 인원 |\n|---|---|---|\n")
        for s in SEGMENTS:
            f.write(f"| {s} | {SEG_LABEL[s]} | {len(picked[s])} |\n")
        f.write("\n## 태그 분포\n\n| 태그 | 인원 |\n|---|---|\n")
        for t, c in tag_count.most_common():
            f.write(f"| `{t}` | {c} |\n")
        f.write("\n> 소득 관련 태그는 공개판에 해당 필드가 없어 생성하지 않았다.\n")

    if len(rows) < args.total:
        print(f"\n⚠️  요청 {args.total}명 중 {len(rows)}명만 모았습니다.")
        print("    원인은 보통 둘 중 하나입니다 —")
        print("    · 직업 중복 상한에 걸림 (parquet 샤드가 적어 직업 다양성이 부족)")
        print("    · 스캔 상한/데이터 소진")
        print("    parquet을 더 넣거나 --total 을 낮추세요.")

    print(f"\n완료: {len(rows)}명 → {args.out}")
    for s in SEGMENTS:
        print(f"  {s} {SEG_LABEL[s]}: {len(picked[s])}명")
    print("\n이제 네트워크 없이 검색할 수 있습니다:")
    print("  python scripts/find_personas.py --tag '#1인사업자' --age 30-50 -n 5")


if __name__ == "__main__":
    main()
