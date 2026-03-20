import yaml
from agent.utils import load_graph, dump_graph, extract_relevant_subgraph

SYSTEM_PROMPT = """당신은 숙련된 서사 작가이자 스토리 구조 전문가입니다.
주어진 세계관 규칙, 캐릭터 정보, 이전 사건들을 바탕으로 새로운 시퀀스의 서사를 생성합니다.

출력은 반드시 다음 두 XML 블록으로만 구성해야 합니다:

<narrative>
  (마크다운 형식의 서사 텍스트. 생동감 있고 구체적으로 작성.)
</narrative>
<updates>
  (YAML 형식의 구조화된 업데이트. 아래 스키마를 엄격히 따를 것.)
</updates>

<updates> 블록의 YAML 스키마:
```
events_log_entry:
  sequence_id: <int>
  title: "<string>"
  summary: "<string>  # 다음 시퀀스에서 압축 기억으로 사용될 1-2문장 요약"
  key_events:
    - "<string>"
  impacts:
    - "<string>"

payoff_updates:
  resolve:            # 이번 시퀀스에서 해결된 payoff_id 목록 (없으면 빈 리스트)
    - "<payoff_id>"
  new_payoffs:        # 새로 생긴 떡밥 (없으면 빈 리스트)
    - payoff_id: "<string>"
      description: "<string>"
      origin_sequence: <int>
      weight: <float 0.1~1.0>
      condition_to_resolve: "<string>"

world_rules_changes:  # 세계관 규칙 변경이 있을 때만 포함 (없으면 이 키 자체를 생략)
  - rule_id: "<string>"
    name: "<string>"
    description: "<string>"

character_updates:
  - char_id: "<string>"
    current_status: "<string>"

relationship_updates:  # 이번 시퀀스로 변화한 관계 (변화 없으면 빈 리스트)
  - from: "<node_id>"   # CHAR_*, ITEM_*, FAC_* 모두 가능
    to: "<node_id>"
    relation: "<relation_type>"   # trust / fear_hostility / past_connection 등
    strength: <float 0.0~1.0>    # (선택) 새 강도
    since_sequence: <int>        # (선택) 관계 시작 시퀀스
    note: "<string>"             # (선택) 변화 이유

feedforward:
  next_main_goal: "<string>"
  next_key_conflict:
    - type: "<External/Internal>"
      description: "<string>"
  new_elements:
    characters:   # 새 인물 (없으면 빈 리스트)
      - id: "<string>"
        name: "<string>"
        affiliation: "<string>"
        current_status: "<string>"
        traits: []
    locations:    # 새 장소 (없으면 빈 리스트)
      - loc_id: "<string>"
        name: "<string>"
        status: "<string>"
  new_payoffs_to_queue:  # feedforward 단계에서 큐에 올릴 새 떡밥 (없으면 빈 리스트)
    - description: "<string>"
      weight: <float>
```

XML 블록 외부에 다른 텍스트를 절대 출력하지 마세요."""


def build_user_prompt(state: dict) -> str:
    seq_id = state["current_sequence_id"]
    world_rules = state["world_rules"]
    payoff_queue = state["payoff_queue"]
    events_log = state["events_log"]
    main_logline = state["main_logline"]
    narrative_rules = state["narrative_rules"]
    trigger = state["current_trigger"]
    characters = state["current_characters"]
    G = load_graph(characters)
    subgraph = extract_relevant_subgraph(G, radius=2)
    characters_context = dump_graph(subgraph)

    # 페이오프 큐 중 pending 목록 (weight 내림차순으로 정렬하여 우선순위 명시)
    pending = payoff_queue.get("pending_payoffs", [])
    pending_sorted = sorted(pending, key=lambda x: x.get("weight", 0), reverse=True)

    # 이번 시퀀스에서 트리거가 지정한 payoff (새 단순 구조)
    payoff_to_trigger = trigger.get("ingredients_to_use", {}).get("payoff_id_to_trigger", "")

    # 이전 events_log: 직전 시퀀스는 narrative.md 전문 포함 (context_loader에서 주입됨)
    history = events_log.get("history", [])
    history_lines = []
    for entry in history:
        history_lines.append(
            f"[Sequence {entry['sequence_id']}] {entry['title']}\n"
            f"  요약: {entry['summary']}\n"
            f"  주요 사건: {', '.join(entry.get('key_events', []))}"
        )
    history_text = "\n".join(history_lines) if history_lines else "없음"

    # 직전 시퀀스 narrative 전문 (context_loader가 state에 주입)
    prev_narrative = state.get("prev_narrative_full", "")
    prev_narrative_block = (
        f"\n---\n## 직전 시퀀스 {seq_id - 1} 서사 전문\n{prev_narrative}\n---"
        if prev_narrative
        else ""
    )

    prompt = f"""## 현재 생성 대상: Sequence {seq_id}

---
## 서사 규칙 (모든 시퀀스에 공통 적용)
{yaml.dump(narrative_rules, allow_unicode=True, default_flow_style=False)}

---
## 세계관 규칙
{yaml.dump(world_rules, allow_unicode=True, default_flow_style=False)}

---
## 메인 로그라인 & 현재 상태
{yaml.dump(main_logline, allow_unicode=True, default_flow_style=False)}

---
## 이전 사건 기록 (압축)
{history_text}
{prev_narrative_block}

---
## 현재 캐릭터 & 진영 (트리거 관련 노드, radius=2)
{yaml.dump(characters_context, allow_unicode=True, default_flow_style=False)}

---
## 미결 페이오프 큐 (weight 높을수록 우선 해결)
{yaml.dump({"pending_payoffs": pending_sorted}, allow_unicode=True, default_flow_style=False)}

이번 시퀀스에서 반드시 트리거할 페이오프: {payoff_to_trigger}

---
## 이번 시퀀스 트리거
{yaml.dump(trigger, allow_unicode=True, default_flow_style=False)}

---
위 정보를 바탕으로 Sequence {seq_id}의 서사를 생성하고, <updates> 블록을 정확히 채워주세요."""

    return prompt
