# 마른길

2022년 8월 8일 강남 집중호우를 재생해, 사용자가 침수 상황에서
**지금 위험한가**와 **지금 무엇을 해야 하는가**를 한 화면에서 확인하는 모바일 웹 MVP.

> **교육·시연용이며 공식 재난안전 판단 도구가 아니다.**

이 저장소에는 두 갈래가 들어 있다.

| 갈래 | 무엇 | 시작점 |
|---|---|---|
| **앱** | 계약·API·모바일 화면 | 아래 [앱 개발 Quick Start](#앱-개발-quick-start) |
| **모델** | 하수관로 고수위 위험 예측 파이프라인 | 아래 [모델 재현](#모델-재현) |

---

## 앱 개발 Quick Start

**깨끗한 clone 에서 시작하는 기준이다.** 원본 데이터가 없어도 여기까지 전부 된다.

### 필요한 것

| | 버전 | 왜 |
|---|---|---|
| Python | **3.11 이상** | `pyproject.toml` `requires-python` |
| Node.js | **팀 표준 v24.19.0** (하한 22.12) | 표준은 [`.nvmrc`](.nvmrc), 하한은 `web/package.json` `engines`. 22.12 미만은 Vite 7 이 안 돈다 |
| 셸 | Windows PowerShell **또는** macOS·Linux bash | 두 플랫폼 모두 지원한다 |

**Node 버전은 `nvm` 으로 맞추는 것이 가장 빠르다.** 저장소 루트에서:

```bash
nvm install && nvm use          # macOS · Linux — .nvmrc 를 자동으로 읽는다
```

```powershell
nvm install 24.19.0 ; nvm use 24.19.0   # Windows (nvm-windows 는 .nvmrc 를 안 읽는다)
```

버전이 표준과 다르면 `setup` 이 경고만 하고 진행한다. **하한 미만이면 멈춘다** —
그 상태로는 프론트 빌드가 어차피 실패하기 때문이다.

### 1. 설치 (최초 1회) — 이 한 줄이면 끝난다

```powershell
# Windows
git clone <저장소 주소>
cd mareungil
.\make.ps1 setup
```

```bash
# macOS · Linux
git clone <저장소 주소>
cd mareungil
./make.sh setup
```

**두 스크립트는 태스크 이름과 검증 단계가 같다.** 한쪽에만 명령이 생기면
`tests/test_portability.py` 가 실패하므로 플랫폼별로 안내가 갈리지 않는다.

`setup` 이 세 가지를 이어서 한다.

1. **사전 확인** — Python 3.11 이상과 Node/npm 이 실제로 실행되는지 본다. 없으면 무엇을 설치해야 하는지 알려주고 멈춘다
2. **설치** — Python 가상환경(`.venv`)과 프론트 의존성. 어느 한 단계라도 실패하면 즉시 멈춘다
3. **검증** — 계약 검증 · Python 테스트 · TypeScript 검사 · 프론트 테스트 · production build

**"환경 준비 완료" 가 나와야 개발을 시작한다.** 여기서 막히면 그대로 팀 시간이 빠진다.

> `.\make.ps1` 이 실행되지 않고 *"이 시스템에서 스크립트를 실행할 수 없으므로"* 가 뜨면
> PowerShell 실행 정책 문제다. 창을 하나 열고 아래를 한 번만 실행한다.
>
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

### 2. 실행

창 두 개를 띄운다.

```powershell
.\make.ps1 api      # 백엔드   http://127.0.0.1:8000/docs
.\make.ps1 web      # 프론트   http://127.0.0.1:5173
```

```bash
./make.sh api       # 백엔드   http://127.0.0.1:8000/docs
./make.sh web       # 프론트   http://127.0.0.1:5173
```

화면에 **위험 등급 · 현재 위치 · 권고 행동 · 재생 시각 · 119 버튼 · 면책 문구**가 보이면 성공이다.

> 지금 응답은 전부 **픽스처 기반**이다. 예측·판단·경로 엔진이 아직 붙지 않았고,
> 화면과 API 응답(`source_kind`)이 그 사실을 표시한다.

### 3. 배포 (Deployment)

이 프로젝트는 백엔드와 프론트엔드가 분리되어 있으므로 투트랙(Two-track) 배포를 권장한다.

- **백엔드 (Render)**
  - Render 대시보드에서 **New > Blueprint** 로 저장소를 연결하면 루트의 `render.yaml`을 읽어 자동 배포된다.
  - 수동 설정 시: Build Command `pip install -r requirements-dev.txt`, Start Command `uvicorn api.main:app --host 0.0.0.0 --port 10000`
- **프론트엔드 (Vercel)**
  - Vercel 대시보드에서 **Add New > Project** 로 저장소를 연결한다.
  - ⚠️ **Root Directory**를 반드시 `web`으로 설정한다.
  - **Environment Variables**에 `VITE_API_BASE` 키로 백엔드의 URL(`https://*.onrender.com`)을 추가하고 배포한다.

### 명령 전체

```powershell
.\make.ps1 setup           # clone 직후 이것 하나 (사전 확인 + 설치 + 검증)
.\make.ps1 install         # 설치만 (검증은 따로 check)
.\make.ps1 install-model   # 모델 파이프라인 의존성 (AI·데이터 담당만)

.\make.ps1 api             # 백엔드 개발 서버
.\make.ps1 web             # 프론트 개발 서버

.\make.ps1 contracts       # 모든 계약 픽스처 검증
.\make.ps1 fixtures        # DS 픽스처 재생성
.\make.ps1 test            # Python 테스트
.\make.ps1 webtest         # 프론트 smoke test
.\make.ps1 typecheck       # TypeScript 검사
.\make.ps1 build           # 프론트 production build

.\make.ps1 check           # 위 검증 전부
```

macOS·Linux 는 같은 이름으로 `./make.sh <task>` 를 쓴다.

### 플랫폼 차이로 깨지지 않게 해 둔 것

Windows·macOS 를 섞어 쓰므로, **한쪽에서만 터지는** 문제를 미리 막아 두었다.
전부 `tests/test_portability.py` 가 지키며 어기면 `check` 에서 빨개진다.

| 문제 | 어떻게 막았나 |
|---|---|
| 줄바꿈(CRLF/LF) 차이로 diff·실행이 깨짐 | [`.gitattributes`](.gitattributes) 가 저장소 전체에 규칙을 건다. **개인 `core.autocrlf` 설정에 맡기지 않는다.** `*.sh` 는 LF, `*.ps1`·`*.bat` 는 CRLF 로 못박는다 |
| Node 버전이 달라 빌드가 다르게 동작 | [`.nvmrc`](.nvmrc) 가 팀 표준, `web/package.json` `engines` 가 하한. 두 값이 어긋나면 테스트가 실패한다 |
| 절대경로(`C:\...`)를 코드에 박아 남이 못 돌림 | 검사가 소스 전체를 훑는다. 경로는 `Path(__file__)` 기준 상대경로로만 만든다 |
| 한쪽 실행 스크립트에만 명령이 생김 | `make.ps1` 과 `make.sh` 의 태스크 목록·검증 단계를 대조한다 |

> 이 검사를 처음 넣었을 때 **실제로 절대경로 네 곳이 걸렸다.**
> `scripts/mareungil/config.py` 의 `ROOT = Path(r"C:\2026_Mareungil")` 이 대표적이며,
> 그 상태로는 다른 팀원이 데이터 파이프라인을 아예 돌릴 수 없었다.

### 다음에 읽을 것

| 문서 | 내용 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | **저장소 작업 규칙.** enum, 금칙어, 모듈 의존 방향, 계약 변경 절차 |
| [docs/HACKATHON_11H_RUNBOOK.md](docs/HACKATHON_11H_RUNBOOK.md) | 11시간 실행계획과 담당 배치 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 기술 선택과 **미확정(OPEN) 목록** |
| [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md) | 저장소 생성과 5인 공유 |
| [docs/REPOSITORY_AUDIT.md](docs/REPOSITORY_AUDIT.md) | 구현됨 / STUB / 없음 구분 |
| [docs/HACKATHON_CHECKLIST.md](docs/HACKATHON_CHECKLIST.md) | 게이트별·데모 직전 체크리스트 |
| [docs/README.md](docs/README.md) | 설계·요구사항 문서 세트 |

---

## 모델 재현

강남·서초 하수관로 센서의 **10·30·60분 후 고수위 위험**을 예측한다.
주 예측시간은 30분. 2022년 서울시 공개데이터 기반.

### 먼저 읽을 것

| 문서 | 내용 |
|---|---|
| [reports/안윤지_위험예측_데이터조사.md](reports/안윤지_위험예측_데이터조사.md) | **메인 설계안.** 데이터 검증부터 모델 결과까지 전부 |
| [reports/안윤지_데이터_현황_및_자료요청_가이드.md](reports/안윤지_데이터_현황_및_자료요청_가이드.md) | 서울시 자료요청 문안과 절차 |
| [data_unified/processed/v2/README.md](data_unified/processed/v2/README.md) | 데이터셋 계약과 재현 방법 |

### 반드시 알고 시작할 것

**전체 정확도·F1로 성과를 판단하면 안 된다.**

아무것도 학습하지 않은 기준선("지금 물이 높으면 30분 뒤에도 높다")이 F1 **0.894** 를 낸다.
대부분의 행에서 수위가 거의 안 변하기 때문이다. 그런데 이 기준선은 **물이 차오르기
시작하는 순간을 단 한 건도 못 잡는다(0.000).**

그래서 대표지표는 **상승전이 재현율**이다.

| test (8/8 극한호우), t+30 | 차오르는 순간 잡은 비율 | 오경보율 | 미리 경고한 비율 | 전체 F1 |
|---|---:|---:|---:|---:|
| 로지스틱 | **0.731** | 0.051 | 87.7% | 0.829 |
| HistGB | 0.648 | 0.029 | 85.3% | 0.839 |
| 규칙 기준선 | 0.108 | 0.006 | 43.1% | 0.892 |
| 지속성 기준선 | 0.000 | 0.000 | 23.0% | 0.894 |

전체 F1만 보면 기준선이 더 높다. 상승전이로 보면 정반대다.
고수위 시작 374건 중 **328건(87.7%)을 미리 경고**한다 — 이것이 모델이 만든 가치다.

### 데이터는 이 저장소에 없다

원본 약 7.5GB 는 용량 때문에 제외했다. 공식 포털에서 각자 내려받는다.

- 서울시 강우량 [OA-1168](https://data.seoul.go.kr/dataList/OA-1168/F/1/datasetView.do)
- 서울시 하수관로 수위 [OA-2527](https://data.seoul.go.kr/dataList/OA-2527/S/1/datasetView.do?tab=A)
- 경로와 배치는 `data_unified/metadata/source_manifest.csv` 참고

**모델링용 데이터셋(`processed/v2/*.parquet`)은 포함돼 있으므로**, 원본 없이도
평가·모델 스크립트는 바로 돌릴 수 있다.

### 재현

모델 파이프라인은 앱과 의존성이 다르다. 먼저 설치한다.

```powershell
.\make.ps1 install-model    # pandas · numpy · scikit-learn · pyarrow
```

```powershell
# 1) 데이터셋 (원본 7.28GB 필요. 이미 만들어진 parquet 이 있으면 건너뛴다)
python scripts\build_dataset.py events
python scripts\build_dataset.py sewer
python scripts\build_dataset.py rain
python scripts\build_dataset.py features

# 2) 기준선과 모델
python scripts\run_baselines.py 30
python scripts\run_models.py 30

# 3) 경보 정책
python scripts\run_alarm_policy.py 30
python scripts\run_severity_threshold.py 30
```

### 지금 못 하는 것

- **물리적 만관율** — 관 높이와 센서 영점이 없어 "몇 % 찼다"를 말할 수 없다.
  수위 단위(m/cm)도 미확인이라 출력에 `UNCONFIRMED` 로 표시한다.
- **정확한 도로 위치** — 센서 35개 중 공식 좌표는 0개. 주소 지오코딩 추정값이며
  정확 번지 수준은 10개뿐이다. `geocode_quality` 를 반드시 함께 보고 판단할 것.
- **경보 해제** — 켜는 건 되는데 끄는 게 아직 부정확하다(오해제율 0.117). 운영 투입 금지.
- **예보 활용** — 현재는 관측된 비만 쓴다. KMA 초단기예보는 미수집.

---

## 저장소 구조

```text
contracts/            계약 — 아무것도 import 하지 않는다
├─ schema/            JSON Schema Draft 2020-12 (4대 계약 + 공식정보)
├─ fixtures/
│  ├─ risk_*.json     RF-*  모델 위험 스냅샷 (실제 모델 출력)
│  ├─ demo/           DS-*  통합 데모 AssessResponse
│  ├─ official/       공식 경보·통제 픽스처
│  └─ invalid/        반드시 거부되어야 하는 조합
├─ destinations.json  지정 지점 목록 (초안)
└─ validate.py        픽스처 일괄 검증

services/
├─ decision/          판단 엔진 ② — 순수 함수만. I/O 없음
│  ├─ enums.py        공용 enum Python 사본
│  └─ postprocess.py  확정된 경로 후처리 1건
└─ route/             경로 엔진 ③ — 인터페이스 + STUB

api/                  통합 API. 세 계약을 묶어 AssessResponse 하나를 제공
web/                  모바일 단일 화면 (Vite + React + TS + Leaflet)
└─ src/contracts/     enum·타입 TypeScript 사본

tests/                계약·정책·API·enum 동기화·금칙어
scripts/              데이터·모델 파이프라인 (기존 자산)
└─ mareungil/
   ├─ config.py       데이터 계약·사건분할·예산. 바꾸면 전부 재실행해야 한다
   ├─ rainfall.py     강우 로딩, 강우사건 정의
   ├─ sewer.py        수위 추출, 완전격자 되채움
   ├─ features.py     피처·타깃·고수위 임계
   ├─ evaluate.py     국면 분해 평가 (상승전이 중심)
   └─ policy.py       경보 임계정책, 경보해제
docs/                 설계·요구사항·실행계획·결정 기록
```

의존은 한 방향으로만 흐른다. 자세한 규칙은 [CLAUDE.md](CLAUDE.md) 9절.

## 보안과 대용량 데이터

- `secrets/` 는 커밋하지 않는다. 서울시 OpenAPI 키는 로컬
  `secrets/seoul_openapi_key.txt` 에서 읽으며 로그·산출물에 남기지 않는다.
- `.env` 는 커밋하지 않는다. 새 환경변수는 **`.env.example` 에 이름과 설명만** 추가한다.
- 원본 데이터(약 7.5GB)와 `data/` 침수흔적도는 커밋하지 않는다.
- 산출물은 `data_unified/processed/v2/` 에만 쓴다. **원본(raw)은 절대 수정하지 않는다.**
- 새 데이터 파일을 추가하기 전에 `git check-ignore -v <path>` 로 제외되는지 확인한다.
- **런타임에 예측·판정을 위한 외부 API 를 호출하지 않는다.** 유일한 런타임 외부
  의존은 지도 타일이며, 타일이 실패해도 위험·행동·시각·119 는 보여야 한다.
