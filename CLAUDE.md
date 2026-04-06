# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 요약

YAML 기반 서사 상태 머신을 LangGraph agent로 구동하는 시스템.
Sequence N의 결과물이 Sequence N+1의 입력이 되는 autoregressive loop.
각 시퀀스는 플롯 개요(sequence_generator)와 소설 산문(novel_writer) 두 단계의 LLM 호출로 생성된다.

---

## 실행 방법

```bash
# 반드시 Autofiction/ 프로젝트 루트에서 실행 (상대 경로 기준점)
cd /path/to/Autofiction

# 의존성 설치
pip install -r requirements.txt

# .env 파일에 ANTHROPIC_API_KEY 저장하거나 export로 설정
export ANTHROPIC_API_KEY="..."

# 원스텝 (가상환경 생성 + 실행, .env 자동 로드, max-sequences·start-sequence 대화형 입력)
./quick_start.sh

# 수동 실행
python -m agent.main --max-sequences 1
python -m agent.main --max-sequences 3 --start-sequence 2
```

CLI 인수:
- `--max-sequences` (기본값 3): 생성할 시퀀스 수
- `--start-sequence` (기본값 1): 시작 시퀀스 ID
- `--base-path`: 프로젝트 루트 경로 (기본값: `agent/` 상위 디렉토리)

---

## 아키텍처

### LangGraph 그래프 흐름

```
context_loader
    → sequence_generator   (claude-sonnet-4-6: 플롯 개요 + <updates> YAML 생성)
    → output_parser        (XML 파싱 + 필수 필드 유효성 검사)
    → state_updater        (Settings/ + History/ YAML 뮤테이션: events_log, payoff_queue, main_logline, worlds_rules)
    → novel_writer         (claude-opus-4-6: 플롯 → 소설 산문 재작성, 최소 1500자)
    → sequence_creator     (Sequence N+1/ 폴더·파일 생성, narrative.md 저장)
    → [should_continue] → context_loader (루프) 또는 END
```

`should_continue`: `current_sequence_id <= max_sequences` 이고 에러 없으면 루프 계속.

### LLM 출력 형식

`sequence_generator`는 두 XML 블록만 출력해야 한다:
- `<narrative>`: 마크다운 플롯 개요
- `<updates>`: YAML 구조체 (스키마는 `agent/prompts.py` `SYSTEM_PROMPT` 참조)

`<updates>` 필수 키: `events_log_entry`, `payoff_updates`, `character_updates`, `feedforward`
`<updates>` 선택 키: `world_rules_changes` (변경 없으면 생략), `relationship_updates` (변화 없으면 빈 리스트)

### 컨텍스트 압축 전략

- 직전 시퀀스(N-1): `narrative.md` 전문을 프롬프트에 포함 (`prev_narrative_full`로 state에 주입)
- N-2 이전: `events_log.yaml`의 `summary` 필드만 포함 (압축 기억)
- `Settings/` 전체: 항상 포함
- 캐릭터 그래프: `CHAR_01` 기준 radius=2 홉 이내 노드만 `extract_relevant_subgraph`로 필터링

---

## 데이터 흐름

### Settings/ (고정 세계관 상태)

| 파일 | 역할 | 변경 노드 |
|------|------|-----------|
| `worlds_rules.yaml` | 세계관 규칙 | `state_updater` (변경 있을 때만) |
| `main_logline.yaml` | 메인 로그라인 + 현재 상태 | `state_updater` |
| `narrative_rules.yaml` | 불변 서사 규칙 (LLM에 텍스트로 덤프) | 사람이 직접 편집 |

### History/ (매 시퀀스 갱신되는 이력 데이터)

| 파일 | 역할 | 변경 노드 |
|------|------|-----------|
| `events_log.yaml` | 시퀀스 히스토리 | `state_updater` (entry append) |
| `payoff_queue.yaml` | 미결/해결 페이오프 큐 | `state_updater` |

### Sequences/Sequence N/ (시퀀스별 데이터)

| 파일 | 역할 | 생성 시점 |
|------|------|-----------|
| `sequence_trigger.yaml` | 이번 시퀀스의 목표·갈등·재료 | `sequence_creator`가 N+1용 자동 생성 |
| `characters_and_factions.yaml` | 캐릭터 상태 (그래프 직렬화 포맷) | `sequence_creator`가 N+1용 업데이트 후 복사 |
| `narrative.md` | 완성된 소설 산문 | `sequence_creator`가 현재 시퀀스(N)에 저장 |

`sequence_creator`는 한 번 실행으로 두 가지 작업을 수행한다:
1. 현재 시퀀스 N: `narrative.md` 저장
2. 다음 시퀀스 N+1: 폴더 생성 + `sequence_trigger.yaml` + `characters_and_factions.yaml` 작성

### characters_and_factions.yaml 포맷

NetworkX `MultiDiGraph` 직렬화 포맷. `load_graph()` / `dump_graph()` 로 변환:

```yaml
nodes:
  characters:
    - id: "CHAR_01"    # 주인공 (extract_relevant_subgraph의 중심)
      name: "..."
      current_status: "..."
  factions:
    - id: "FAC_01"
      ...
edges:
  - from: "CHAR_01"
    to: "FAC_01"
    relation: "trust"   # key로 사용 — 같은 두 노드 간 relation 타입별 다중 엣지 허용
    strength: 0.8
```

노드 ID 컨벤션: `CHAR_*` (캐릭터), `FAC_*` (진영), `ITEM_*` (아이템).

### feedforward → 다음 trigger 매핑

`feedforward` 출력 → `Sequence N+1/sequence_trigger.yaml`:
- `next_main_goal` → `current_drive.main_goal`
- `next_key_conflict` → `current_drive.key_conflict`
- `new_elements.locations[0]` → `ingredients_to_use.location_constraint`
- `new_payoffs_to_queue[0]` (없으면 pending 중 최고 weight) → `payoff_id_to_trigger`

`feedforward.new_payoffs_to_queue` 항목은 `state_updater`가 `payoff_queue.yaml`에 추가할 때 ID를 자동 생성한다: `PAYOFF_{seq_id:02d}_{i+1:02d}` (예: 시퀀스 3의 첫 번째 신규 payoff → `PAYOFF_03_01`)

---

## 코드 모듈 구조

| 파일 | 역할 |
|------|------|
| `agent/graph.py` | LangGraph 그래프 빌드·컴파일, `should_continue` 조건 분기 |
| `agent/nodes.py` | 6개 노드 구현 + `NOVEL_SYSTEM_PROMPT` (novel_writer 전용) |
| `agent/prompts.py` | `SYSTEM_PROMPT` (sequence_generator 전용) + `build_user_prompt()` |
| `agent/state.py` | `NarrativeState` TypedDict 선언 |
| `agent/utils.py` | YAML I/O, XML 파싱, NetworkX 그래프 유틸리티 |
| `agent/main.py` | argparse 엔트리포인트, 초기 state 구성 |

---

## 주의사항

- **`worlds_rules.yaml`** — 파일명에 `s`가 붙은 오타. 코드와 일치시켜 그대로 유지.
- **`sequence_trigger.yaml`의 `sequence_id`** — Sequence N 폴더의 trigger는 `sequence_id: N+1`을 담는다. `sequence_creator`는 `Sequence N+1/`에 파일을 쓸 때 `next_seq_id + 1` 값을 기록한다 (즉 폴더 번호보다 1 큰 값).
- **`prev_narrative_full`** — `NarrativeState` TypedDict에 선언되지 않음. `context_loader`가 `{**state, "prev_narrative_full": ...}` 로 동적 추가. `build_user_prompt()`가 `state.get("prev_narrative_full", "")`로 안전하게 읽음.
- **에러 처리** — 각 노드에서 에러 발생 시 `state["error"]`를 세팅하고 즉시 END로 빠짐. 재시도 로직 없음.
- **`narrative_rules.yaml`** — 코드가 직접 파싱하지 않음. `build_user_prompt()`가 YAML 텍스트 그대로 덤프해서 LLM에 전달. (프롬프트 엔지니어링 외부화)
- **`utils.py` 경로 헬퍼** — `get_sequence_path(base_path, n)` → `Path / "Sequences" / "Sequence {n}"`, `get_settings_path(base_path)` → `Path / "Settings"`, `get_history_path(base_path)` → `Path / "History"`. 경로 구성 시 이 함수를 사용할 것.
- **YAML 쓰기** — `write_yaml()`은 `allow_unicode=True`로 저장하므로 한글 등 유니코드가 그대로 유지됨.
- **`NOVEL_SYSTEM_PROMPT`** — `agent/prompts.py`가 아니라 `agent/nodes.py`에 정의됨. `SYSTEM_PROMPT`(sequence_generator용)만 `prompts.py`에 있다.

---

## 미완료 항목

- [ ] `prev_narrative_full` — `NarrativeState` TypedDict(`agent/state.py`)에 미선언. `context_loader`가 동적으로 주입하고 `build_user_prompt()`가 `state.get()`으로 안전하게 읽어 현재는 동작하나, TypedDict에 공식 추가하면 타입 체크가 온전해짐.
- [ ] 에러 시 재시도 로직 없음 — 각 노드 에러 즉시 END. 필요 시 LangGraph retry 정책 추가 고려.
