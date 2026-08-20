# 확장 팩 (L2)

> ⚠️ **이 리포에는 `personas.jsonl`(12.9MB)이 포함되어 있지 않습니다.**
> 아래 "직접 만들기"를 따라 하시면 동일한 확장 팩을 생성할 수 있습니다.

확장 팩이 설치되면 **3,000명**이 검색 대상이 됩니다. 네트워크는 필요 없습니다.

| 항목 | 값 |
|---|---|
| 인원 | **3,000명** (세그먼트 600명씩) |
| 원본 대비 | 0.30% |
| 고유 직업 | **671종** |
| 표집 | `even` (세그먼트 균등) · 씨앗 817 |
| 출처 | nvidia/Nemotron-Personas-Korea (CC BY 4.0) · shard 0 · 111,112명에서 추출 |

자세한 통계는 `MANIFEST.md`, 한계는 `../SPEC.md`.

---

## 확장 팩 없이도 스킬은 돌아갑니다

`SKILL.md`의 Step 0가 환경을 확인해 자동으로 단계를 낮춥니다.

| 레벨 | 인원 | 조건 |
|---|---|---|
| **L2 확장 팩** | 3,000명 | `personas.jsonl` 존재 |
| **L1.5** | 300명 | `quickref-300.md` 존재 |
| **L1 코어 팩** | 35명 | **항상 동작하는 기본값** |

**"사용 불가"가 아니라 "검색 범위가 좁아지는 것"입니다.**
인터뷰·QA 전 모드는 L1에서도 정상 동작합니다.

---

## 파일

| 파일 | 용도 | 이 리포에 |
|---|---|---|
| `personas.jsonl` | 검색 원본 (전체 서술 포함) | ❌ 직접 생성 |
| `_index.tsv` | 한 줄 인덱스 — grep용 | ❌ 직접 생성 |
| `_index_A.tsv` ~ `_index_E.tsv` | 세그먼트별 인덱스 | ❌ 직접 생성 |
| `quickref-300.md` | 300명 한 줄 요약 | ⭕ |
| `MANIFEST.md` | 생성 조건·세그먼트·태그 분포 | ⭕ |

---

## 직접 만들기

원본 데이터를 받아서 스크립트를 돌리면 됩니다. **원본을 받는 것만으로는 확장 팩이 되지 않습니다.** 추출·가공이 필요합니다.

```bash
# 1) 원본 데이터 받기 (조각당 약 11만 명)
#    https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea/tree/main/data
#    parquet 파일을 ./data 폴더에 두세요

# 2) 의존성
pip install pyarrow

# 3) 생성 — 기본 3,000명
python scripts/build_extended_pack.py --local ./data

# 더 크게
python scripts/build_extended_pack.py --local ./data --total 8000

# 특정 집단을 두껍게 (1인 사업자 중심)
python scripts/build_extended_pack.py --local ./data \\
       --balance custom --weights A=0.1,B=0.1,C=0.5,D=0.15,E=0.15
```

생성이 끝나면 이 폴더에 `personas.jsonl`과 `_index*.tsv`가 만들어지고, 스킬이 자동으로 L2로 올라갑니다.

---

## 쓰는 법

```bash
# 5인 패널 자동 구성
python scripts/find_personas.py --panel --tag '#1인사업자' --age 30-50 --province 서울

# 조건 검색
python scripts/find_personas.py --tag '#저디지털' --age 65-90 -n 3
python scripts/find_personas.py --occupation 소규모 --keyword 배달 -n 5

# 표만 보기
python scripts/find_personas.py --tag '#육아' --format index -n 20
```

스크립트를 못 쓰는 환경이면 `quickref-300.md`를 직접 읽어 고르면 됩니다.

---

## 라이선스

원본: [nvidia/Nemotron-Personas-Korea](https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea) · **CC BY 4.0**
재배포할 때 출처 표기를 유지하세요.
