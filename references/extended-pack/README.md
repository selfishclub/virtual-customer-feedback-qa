# 확장 팩 (L2) — 설치됨 ✅

**3,000명이 들어 있습니다.** 별도 설정 없이 바로 검색됩니다. 네트워크도 필요 없습니다.

| 항목 | 값 |
|---|---|
| 인원 | **3,000명** (세그먼트 600명씩) |
| 원본 대비 | 0.30% |
| 고유 직업 | **671종** |
| 표집 | `even` (세그먼트 균등) · 씨앗 817 |
| 출처 | nvidia/Nemotron-Personas-Korea (CC BY 4.0) · shard 0 · 111,112명에서 추출 |

자세한 통계는 `MANIFEST.md`, 한계는 `../SPEC.md`.

## 파일

| 파일 | 용도 |
|---|---|
| `personas.jsonl` | 검색 원본 (전체 서술 포함) |
| `_index.tsv` | 한 줄 인덱스 — grep용 |
| `_index_A.tsv` ~ `_index_E.tsv` | 세그먼트별 인덱스 — 스크립트 없는 환경에서 직접 읽기 |
| `quickref-300.md` | 300명 한 줄 요약 — 통째로 읽어도 되는 크기 |
| `MANIFEST.md` | 생성 조건·세그먼트·태그 분포 |

## 쓰는 법

```bash
# 5인 패널 자동 구성 (핵심2 + 경계2 + 비사용자1)
python scripts/find_personas.py --panel --tag '#1인사업자' --age 30-50 --province 서울

# 조건 검색
python scripts/find_personas.py --tag '#저디지털' --age 65-90 -n 3
python scripts/find_personas.py --occupation 소규모 --keyword 배달 -n 5

# 표만 보기
python scripts/find_personas.py --tag '#육아' --format index -n 20
```

스크립트를 못 쓰는 환경이면 `_index_<세그먼트>.tsv`나 `quickref-300.md`를 직접 읽어 고르면 됩니다.

## 더 키우고 싶다면

샤드를 더 받아서 다시 만들면 됩니다. 조각당 약 11만 명이에요.

```bash
# https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea/tree/main/data
pip install pyarrow
python scripts/build_extended_pack.py --local ./data --total 8000

# 특정 집단을 두껍게
python scripts/build_extended_pack.py --local ./data --balance business
python scripts/build_extended_pack.py --local ./data \
       --balance custom --weights A=0.1,B=0.1,C=0.5,D=0.15,E=0.15
```

## 라이선스

원본: [nvidia/Nemotron-Personas-Korea](https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea) · **CC BY 4.0**
재배포할 때 출처 표기를 유지하세요.
