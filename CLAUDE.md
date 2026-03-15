# CLAUDE.md — LangGraph Narrative Agent 인수인계 문서

## 프로젝트 한 줄 요약
YAML 기반 서사 상태 머신을 LangGraph agent로 구동하는 시스템.
Sequence N의 결과물이 Sequence N+1의 입력이 되는 autoregressive loop.

---

## 현재 구현 상태 (완료)

모든 코드 파일이 작성된 상태이며, **아직 실제 실행은 해보지 않았다.**

### 파일 구조
```
ai_playground/
├── CLAUDE.md               ← 이 파일
├── README.md
├── requirements.txt        # langgraph, anthropic, pyyaml
├── quick_start.sh          # 가상환경 생성 + 실행까지 원스텝
├── Settings/
│   ├── events_log.yaml
│   ├── main_logline.yaml
│   ├── narrative_rules.yaml   ← 이번 세션에서 분리함 (불변 서사 규칙)
│   ├── payoff_queue.yaml
│   └── worlds_rules.yaml
├── Sequence 1/             # 수동 작성된 초기 시퀀스
│   ├── characters_and_factions.yaml
│   └── sequence_trigger.yaml  ← 이번 세션에서 단순화함
└── agent/
    ├── state.py            # NarrativeState TypedDict
    ├── nodes.py            # 5개 노드
    ├── graph.py            # StateGraph 조립
    ├── utils.py            # YAML read/write, XML 파서
    ├── prompts.py          # 시스템/유저 프롬프트
    └── main.py             # CLI 진입점 (argparse)
```

---

## 이번 세션에서 결정한 설계 사항

### 1. narrative_rules.yaml 분리
`sequence_trigger.yaml`에 있던 불변 정보를 `Settings/narrative_rules.yaml`로 분리함.

**narrative_rules.yaml이 담는 것 (불변, 사람이 편집):**
- `event_structure`: 4단계 서사 구조 (action → complication → climax → resolution)
- `output_requirements`: LLM 출력 요구사항
- `feedforward_schema`: feedforward 출력 형식 지시

**sequence_trigger.yaml이 담는 것 (가변, 시퀀스마다 작성):**
- `sequence_id`: 몇 번째 시퀀스인지
- `current_drive`: 이번 시퀀스의 목표와 갈등
- `ingredients_to_use`: 트리거할 payoff_id, 장소 제약

**중요:** `narrative_rules`는 코드가 직접 파싱해서 쓰는 게 아니라,
유저 프롬프트에 텍스트로 덤프해서 LLM이 참고하도록 넘기는 역할만 함.
→ 프롬프트 엔지니어링을 YAML로 외부화한 것.

### 2. feedforward 설계 원칙
- `feedforward_generation`은 LLM의 **출력**이지 입력이 아님
- trigger 파일에서 제거하고 `narrative_rules.yaml`의 `feedforward_schema`로 대체
- LLM이 `<updates>` 블록의 `feedforward` 섹션을 채우면,
  `sequence_creator`가 그걸 읽어 다음 `sequence_trigger.yaml`을 자동 생성

### 3. sequence_trigger.yaml 생성 로직 (sequence_creator)
다음 시퀀스의 trigger를 자동 생성할 때:
- `feedforward.next_main_goal` → `current_drive.main_goal`
- `feedforward.next_key_conflict` → `current_drive.key_conflict`
- `feedforward.new_elements.locations[0]` → `ingredients_to_use.location_constraint`
- 다음 payoff 선택 우선순위: feedforward new_payoffs → pending 중 weight 최고값

---

## 그래프 흐름
```
context_loader
    → sequence_generator   (Claude API 호출)
    → output_parser        (XML 파싱 + 유효성 검사)
    → state_updater        (Settings YAML 업데이트)
    → sequence_creator     (Sequence N+1/ 생성, narrative.md 저장)
    → [current_sequence_id <= max_sequences] → context_loader (루프)
    → END
```

### 컨텍스트 압축 전략
- 직전 시퀀스 (N-1): `narrative.md` 전문 포함
- N-2 이전: `events_log.yaml`의 `summary` 필드만 (압축 기억)
- Settings 전체: 항상 포함

---

## 다음 세션에서 할 일 (미완료)

### 우선순위 높음
- [ ] **실제 실행 테스트** — `./quick_start.sh` 로 단일 시퀀스 생성 확인
  - `Sequence 2/` 세 파일 생성 확인
  - `Settings/events_log.yaml`에 entry 추가 확인
  - `Settings/payoff_queue.yaml`에서 PAYOFF_002 resolved 이동 확인

### 논의 중이거나 잠재적 개선 사항
- [ ] `narrative_rules`를 LLM에 텍스트로만 전달하는 현재 방식 vs.
      코드가 직접 `event_structure`를 강제하는 방식 — 어느 쪽이 나을지 미결
- [ ] `prev_narrative_full`이 state TypedDict에 선언되지 않음
      (`context_loader`가 state에 임시로 추가하는 방식 — 정리 필요할 수 있음)
- [ ] 오류 발생 시 재시도 로직 없음 (현재는 error 세팅 후 END로 빠짐)

---

## 실행 방법 (빠른 참고)
```bash
cd /Users/youngjunlee/Project/Poetic_Machine_Lab/ai_playground

# 원스텝
./quick_start.sh

# 수동
export ANTHROPIC_API_KEY="..."
python -m agent.main --max-sequences 1
```

---

## 주의사항
- `worlds_rules.yaml` (s 붙음) — 파일명 오타이지만 코드와 일치시켜 그대로 유지 중
- `sequence_id` in trigger: Sequence N 폴더의 trigger는 N+1 생성용 지침을 담음
  (e.g. `Sequence 1/sequence_trigger.yaml`의 `sequence_id: 2`)
- 실행은 반드시 `ai_playground/` 루트에서 `python -m agent.main` 형태로 해야 함
  (상대 경로 기준점 때문)
