# AutoFiction
A LangGraph-powered narrative engine where each chapter seeds the next

YAML 기반 서사 상태 머신을 LangGraph agent로 구동하는 시스템.
Sequence N의 결과물이 Sequence N+1의 입력이 되는 autoregressive loop으로 서사를 자동 생성합니다.

---

## 프로젝트 구조

```
ai_playground/
├── README.md
├── requirements.txt
├── quick_start.sh                     # 가상환경 생성 + 실행 원스텝
├── Settings/                          # 전역 상태 (agent가 업데이트)
│   ├── events_log.yaml                # 시퀀스별 사건 기록 (압축 기억)
│   ├── main_logline.yaml              # 메인 로그라인 & 현재 목표
│   ├── narrative_rules.yaml           # 불변 서사 규칙 (수동 작성, agent는 읽기만)
│   ├── payoff_queue.yaml              # 미결/해결 페이오프 목록
│   └── worlds_rules.yaml             # 세계관 규칙 & 장소
├── Sequence 1/                        # 초기 설정 (수동 작성)
│   ├── characters_and_factions.yaml
│   └── sequence_trigger.yaml          # current_drive + ingredients_to_use만 포함
├── Sequence 2/                        # agent가 생성
│   ├── characters_and_factions.yaml
│   ├── sequence_trigger.yaml
│   └── narrative.md                   # novel_writer가 생성한 완성 소설 산문
└── agent/
    ├── __init__.py
    ├── state.py      # NarrativeState TypedDict
    ├── nodes.py      # 6개 노드 함수
    ├── graph.py      # StateGraph 조립 & 엣지 정의
    ├── utils.py      # YAML read/write, XML 파서
    ├── prompts.py    # 시스템/유저 프롬프트 템플릿
    └── main.py       # CLI 진입점
```

---

## 동작 원리

```
[Sequence N 폴더] ──── context_loader ────► sequence_generator
      ↑                                            │
      │                                     output_parser
      │                                            │
      │                                     state_updater
      │                                            │
      │                                      novel_writer   ← 소설 산문 재작성
      │                                            │
      └──────────────── sequence_creator ◄─────────┘
         (N < max)              │
                               END
                         (N >= max or error)
```

### Graph 노드

| 노드 | 역할 |
|------|------|
| `context_loader` | Settings/ + Sequence N/ YAML을 읽어 state에 로드 |
| `sequence_generator` | Claude Sonnet으로 서사 플롯 개요 및 구조화 업데이트 생성 |
| `output_parser` | LLM 출력의 `<narrative>` / `<updates>` XML 블록 파싱 |
| `state_updater` | Settings YAML 파일 업데이트 (events_log, payoff_queue, main_logline 등) |
| `novel_writer` | Claude Opus로 플롯 개요를 완성도 높은 소설 산문으로 재작성 |
| `sequence_creator` | Sequence N+1/ 폴더 및 파일 생성, novel_writer 출력을 narrative.md로 저장 |

### 컨텍스트 압축 전략

- **직전 시퀀스**: `narrative.md` 전문 포함 (최신 맥락)
- **N-2 이전**: `events_log.yaml`의 `summary` 필드만 참조 (압축 기억)
- **Settings 전체**: `world_rules` + `narrative_rules` + `payoff_queue` 항상 포함

---

## 설치 및 실행

### 빠른 시작 (권장)

```bash
./quick_start.sh
```

가상환경 생성 → 의존성 설치 → API 키 확인 → 시퀀스 수 입력 → 실행까지 한 번에 처리합니다.

### 수동 실행

#### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

#### 2. API 키 설정

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

#### 3. 실행

```bash
# 프로젝트 루트(ai_playground/)에서 실행
cd ai_playground

# 단일 시퀀스 생성 (Sequence 1 → Sequence 2 생성)
python -m agent.main --max-sequences 1

# 연속 3개 시퀀스 생성 (Sequence 1 → Sequence 4까지)
python -m agent.main --max-sequences 3

# 특정 시퀀스부터 시작
python -m agent.main --max-sequences 3 --start-sequence 2

# 프로젝트 경로 직접 지정
python -m agent.main --max-sequences 3 --base-path /path/to/ai_playground
```

---

## LLM 출력 포맷

LLM은 두 XML 블록만 출력합니다:

```xml
<narrative>
  ...서사 텍스트 (마크다운)...
</narrative>
<updates>
  events_log_entry:
    sequence_id: 2
    title: "..."
    summary: "..."
    key_events: [...]
    impacts: [...]

  payoff_updates:
    resolve: ["PAYOFF_002"]
    new_payoffs:
      - payoff_id: "PAYOFF_003"
        ...

  world_rules_changes:   # 변경 있을 때만
    - rule_id: "RULE_03"
      ...

  character_updates:
    - char_id: "CHAR_01"
      current_status: "..."

  feedforward:
    next_main_goal: "..."
    next_key_conflict: [...]
    new_elements:
      characters: [...]
      locations: [...]
    new_payoffs_to_queue: [...]
</updates>
```

---

## YAML 파일 역할

### Settings/

| 파일 | 수정 주체 | 역할 |
|------|----------|------|
| `events_log.yaml` | agent | 시퀀스별 사건 기록. `summary` 필드가 압축 기억으로 사용됨 |
| `main_logline.yaml` | agent | 현재 내러티브 목표 및 로그라인. 매 시퀀스마다 업데이트됨 |
| `narrative_rules.yaml` | 사람 | 불변 서사 규칙 — event_structure, output_requirements, feedforward_schema |
| `payoff_queue.yaml` | agent | 미결(`pending`) / 해결(`resolved`) 페이오프 목록 |
| `worlds_rules.yaml` | agent | 세계관 규칙, 핵심 메카닉, 장소 정보 |

### Sequence N/

| 파일 | 수정 주체 | 역할 |
|------|----------|------|
| `characters_and_factions.yaml` | agent | 현재 등장인물 상태 및 진영 (매 시퀀스 갱신) |
| `sequence_trigger.yaml` | 사람 / agent | `current_drive` + `ingredients_to_use`만 포함 (가변 정보) |
| `narrative.md` | agent | `novel_writer`가 생성한 완성 소설 산문 |

---

## 검증 체크리스트

```bash
# 1. 단일 시퀀스 생성
python -m agent.main --max-sequences 1

# 2. Sequence 2/ 폴더에 세 파일 존재 확인
ls Sequence\ 2/
# → characters_and_factions.yaml  narrative.md  sequence_trigger.yaml

# 3. events_log에 Sequence 1 entry 추가 확인
cat Settings/events_log.yaml

# 4. payoff_queue에서 PAYOFF_002 resolved 이동 확인
cat Settings/payoff_queue.yaml

# 5. 연속 생성 (Sequence 4까지)
python -m agent.main --max-sequences 3
```

---

## 모델 분리 전략

두 단계에 서로 다른 모델을 사용합니다:

| 노드 | 모델 | 이유 |
|------|------|------|
| `sequence_generator` | `claude-sonnet-4-6` | 구조화된 XML+YAML 출력 생성 — 정확성 우선 |
| `novel_writer` | `claude-opus-4-6` | 자유로운 소설 산문 — 문학적 품질 우선 |

---

## 의존성

| 패키지 | 용도 |
|--------|------|
| `langgraph` | StateGraph 기반 에이전트 오케스트레이션 |
| `anthropic` | Claude API 클라이언트 |
| `pyyaml` | YAML 파일 read/write |
