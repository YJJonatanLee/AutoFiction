import os
from pathlib import Path

import anthropic

from .state import NarrativeState
from .utils import (
    get_sequence_path,
    get_settings_path,
    parse_updates_yaml,
    parse_xml_sections,
    read_yaml,
    write_text,
    write_yaml,
    load_graph,
    dump_graph,
)
from .prompts import SYSTEM_PROMPT, build_user_prompt


# ---------------------------------------------------------------------------
# 1. context_loader
# ---------------------------------------------------------------------------

def context_loader(state: NarrativeState) -> NarrativeState:
    """Settings/ 및 현재 Sequence N/ 의 YAML을 읽어 state에 로드."""
    base = state["base_path"]
    seq_id = state["current_sequence_id"]
    settings = get_settings_path(base)
    seq_path = get_sequence_path(base, seq_id)

    try:
        world_rules = read_yaml(settings / "worlds_rules.yaml")
        main_logline = read_yaml(settings / "main_logline.yaml")
        events_log = read_yaml(settings / "events_log.yaml")
        payoff_queue = read_yaml(settings / "payoff_queue.yaml")
        narrative_rules = read_yaml(settings / "narrative_rules.yaml")

        trigger = read_yaml(seq_path / "sequence_trigger.yaml")
        characters = read_yaml(seq_path / "characters_and_factions.yaml")

        # 컨텍스트 압축: 직전 시퀀스 narrative.md 전문 포함
        prev_narrative_full = ""
        if seq_id > 1:
            prev_narrative_path = get_sequence_path(base, seq_id - 1) / "narrative.md"
            if prev_narrative_path.exists():
                prev_narrative_full = prev_narrative_path.read_text(encoding="utf-8")

        return {
            **state,
            "world_rules": world_rules,
            "main_logline": main_logline,
            "events_log": events_log,
            "payoff_queue": payoff_queue,
            "narrative_rules": narrative_rules,
            "current_trigger": trigger,
            "current_characters": characters,
            "prev_narrative_full": prev_narrative_full,
            "error": None,
        }
    except Exception as e:
        return {**state, "error": f"context_loader 오류: {e}"}


# ---------------------------------------------------------------------------
# 2. sequence_generator
# ---------------------------------------------------------------------------

def sequence_generator(state: NarrativeState) -> NarrativeState:
    """LLM을 호출하여 서사를 생성."""
    if state.get("error"):
        return state

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    user_prompt = build_user_prompt(state)

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_output = message.content[0].text
        return {**state, "raw_llm_output": raw_output, "error": None}
    except Exception as e:
        return {**state, "error": f"sequence_generator 오류: {e}"}


# ---------------------------------------------------------------------------
# 3. output_parser
# ---------------------------------------------------------------------------

def output_parser(state: NarrativeState) -> NarrativeState:
    """LLM 출력을 파싱하여 narrative와 structured_updates로 분리."""
    if state.get("error"):
        return state

    raw = state.get("raw_llm_output", "")
    try:
        narrative, updates_raw = parse_xml_sections(raw)

        if not narrative:
            return {**state, "error": "output_parser: <narrative> 블록이 비어 있음"}
        if not updates_raw:
            return {**state, "error": "output_parser: <updates> 블록이 비어 있음"}

        structured_updates = parse_updates_yaml(updates_raw)

        # 필수 필드 검사
        required = ["events_log_entry", "payoff_updates", "character_updates", "feedforward"]
        missing = [k for k in required if k not in structured_updates]
        if missing:
            return {
                **state,
                "error": f"output_parser: 필수 필드 누락: {missing}",
            }

        return {
            **state,
            "generated_narrative": narrative,
            "structured_updates": structured_updates,
            "error": None,
        }
    except Exception as e:
        return {**state, "error": f"output_parser 오류: {e}"}


# ---------------------------------------------------------------------------
# 4. state_updater
# ---------------------------------------------------------------------------

def state_updater(state: NarrativeState) -> NarrativeState:
    """Settings YAML 파일 업데이트."""
    if state.get("error"):
        return state

    base = state["base_path"]
    settings = get_settings_path(base)
    updates = state["structured_updates"]
    seq_id = state["current_sequence_id"]

    try:
        # --- events_log.yaml: 새 entry append ---
        events_log = state["events_log"]
        entry = updates.get("events_log_entry", {})
        if entry:
            history = events_log.get("history", [])
            history.append(entry)
            events_log["history"] = history
            write_yaml(settings / "events_log.yaml", events_log)

        # --- payoff_queue.yaml: resolve 처리 + new_payoffs 추가 ---
        payoff_queue = state["payoff_queue"]
        payoff_updates = updates.get("payoff_updates", {})

        resolve_ids = payoff_updates.get("resolve", []) or []
        new_payoffs = payoff_updates.get("new_payoffs", []) or []

        pending = payoff_queue.get("pending_payoffs", [])
        resolved = payoff_queue.get("resolved_payoffs", [])

        newly_resolved = [p for p in pending if p.get("payoff_id") in resolve_ids]
        still_pending = [p for p in pending if p.get("payoff_id") not in resolve_ids]

        for p in newly_resolved:
            p["resolved_at_sequence"] = seq_id
        resolved.extend(newly_resolved)
        still_pending.extend(new_payoffs)

        # feedforward new_payoffs_to_queue도 추가
        feedforward = updates.get("feedforward", {})
        ff_payoffs = feedforward.get("new_payoffs_to_queue", []) or []
        for i, fp in enumerate(ff_payoffs):
            still_pending.append(
                {
                    "payoff_id": f"PAYOFF_{seq_id:02d}_{i+1:02d}",
                    "description": fp.get("description", ""),
                    "origin_sequence": seq_id,
                    "weight": fp.get("weight", 0.3),
                    "condition_to_resolve": fp.get("condition_to_resolve", "미정"),
                }
            )

        payoff_queue["pending_payoffs"] = still_pending
        payoff_queue["resolved_payoffs"] = resolved
        write_yaml(settings / "payoff_queue.yaml", payoff_queue)

        # --- world_rules.yaml: 변경 있을 때만 ---
        world_rules_changes = updates.get("world_rules_changes", None)
        if world_rules_changes:
            world_rules = state["world_rules"]
            existing_rules = world_rules.get("world_settings", {}).get("core_mechanics", [])
            existing_ids = {r["rule_id"] for r in existing_rules}
            for change in world_rules_changes:
                rid = change.get("rule_id")
                if rid in existing_ids:
                    for r in existing_rules:
                        if r["rule_id"] == rid:
                            r.update(change)
                else:
                    existing_rules.append(change)
            world_rules.setdefault("world_settings", {})["core_mechanics"] = existing_rules
            write_yaml(settings / "worlds_rules.yaml", world_rules)

        # --- main_logline.yaml: sequence_id +1, logline 업데이트 ---
        main_logline = state["main_logline"]
        main_logline.setdefault("metadata", {})["current_sequence_id"] = seq_id + 1
        ff = updates.get("feedforward", {})
        if ff.get("next_main_goal"):
            main_logline.setdefault("current_state", {})["logline"] = ff["next_main_goal"]
            conflicts = ff.get("next_key_conflict", [])
            if conflicts:
                main_logline["current_state"]["immediate_objective"] = (
                    conflicts[0].get("description", "") if isinstance(conflicts[0], dict)
                    else str(conflicts[0])
                )
        write_yaml(settings / "main_logline.yaml", main_logline)

        return {
            **state,
            "events_log": events_log,
            "payoff_queue": payoff_queue,
            "main_logline": main_logline,
            "error": None,
        }
    except Exception as e:
        return {**state, "error": f"state_updater 오류: {e}"}


# ---------------------------------------------------------------------------
# 5. novel_writer
# ---------------------------------------------------------------------------

NOVEL_SYSTEM_PROMPT = """당신은 한국 문학상을 받은 소설가입니다.
주어진 서사 플롯 개요를 바탕으로, 독자가 몰입할 수 있는 완성된 소설 한 챕터를 작성합니다.

작성 원칙:
- 플롯의 모든 사건과 감정선을 유지하되, 장면·대화·내면 묘사를 풍부하게 확장하세요.
- 직접적 설명(telling) 대신 감각적 묘사(showing)를 우선합니다.
- 캐릭터의 내면 독백, 신체 반응, 주변 환경 묘사를 적극 활용하세요.
- 문장 리듬에 변화를 주어 긴장과 이완을 교차시키세요.
- 마크다운 제목(#) 없이 순수 산문으로만 작성합니다.
- 플롯 단계 이름(행동, 충돌 등)을 본문에 노출하지 마세요.
- 분량: 최소 1500자 이상."""


def novel_writer(state: NarrativeState) -> NarrativeState:
    """generated_narrative 플롯을 완성도 높은 소설 산문으로 재작성."""
    if state.get("error"):
        return state

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    seq_id = state["current_sequence_id"]

    user_prompt = f"""아래는 Sequence {seq_id}의 서사 플롯 개요입니다.
이것을 완성된 소설 챕터로 재작성해주세요. 플롯의 모든 사건·감정·반전을 유지하면서
독자가 현장에 있는 것처럼 느낄 수 있도록 장면과 대화를 충분히 확장하세요.

---
{state["generated_narrative"]}
---"""

    try:
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=8192,
            system=NOVEL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        novel = message.content[0].text
        return {**state, "novel_narrative": novel, "error": None}
    except Exception as e:
        return {**state, "error": f"novel_writer 오류: {e}"}


# ---------------------------------------------------------------------------
# 6. sequence_creator
# ---------------------------------------------------------------------------

def sequence_creator(state: NarrativeState) -> NarrativeState:
    """Sequence N+1/ 폴더 및 파일 생성."""
    if state.get("error"):
        return state

    base = state["base_path"]
    seq_id = state["current_sequence_id"]
    next_seq_id = seq_id + 1
    next_seq_path = get_sequence_path(base, next_seq_id)
    updates = state["structured_updates"]

    try:
        next_seq_path.mkdir(parents=True, exist_ok=True)

        # --- narrative.md: 소설 산문 저장 (novel_writer 출력 우선, 없으면 generated_narrative) ---
        current_seq_path = get_sequence_path(base, seq_id)
        narrative_to_save = state.get("novel_narrative") or state["generated_narrative"]
        write_text(current_seq_path / "narrative.md", narrative_to_save)

        # --- characters_and_factions.yaml: character_updates 반영 ---
        characters = state["current_characters"]
        char_updates = updates.get("character_updates", []) or []

        # --- NetworkX로 characters 그래프 로드 ---
        G = load_graph(characters)  # nx.MultiDiGraph

        # 1. character_updates: current_status만 업데이트
        for cu in char_updates:
            cid = cu.get("char_id")
            if cid and cid in G and "current_status" in cu:
                G.nodes[cid]["current_status"] = cu["current_status"]

        # 2. feedforward.new_elements.characters: 새 캐릭터 노드 추가
        new_chars = updates.get("feedforward", {}).get("new_elements", {}).get("characters", []) or []
        for nc in new_chars:
            nid = nc.get("id")
            if nid and nid not in G:
                G.add_node(nid, node_type="characters", **{k: v for k, v in nc.items() if k != "id"})

        # 3. relationship_updates: (from, to, relation) 트리플로 엣지 upsert
        # MultiDiGraph에서 key=relation으로 엣지를 구분
        relationship_updates = updates.get("relationship_updates", []) or []
        for ru in relationship_updates:
            src, dst, rel = ru.get("from"), ru.get("to"), ru.get("relation")
            if not (src and dst and rel):
                continue
            if G.has_edge(src, dst, key=rel):
                for opt in ("strength", "note", "since_sequence"):
                    if opt in ru:
                        G[src][dst][rel][opt] = ru[opt]
            else:
                edge_attrs = {"relation": rel}
                for opt in ("strength", "since_sequence", "note"):
                    if opt in ru:
                        edge_attrs[opt] = ru[opt]
                G.add_edge(src, dst, key=rel, **edge_attrs)

        characters = dump_graph(G)

        write_yaml(next_seq_path / "characters_and_factions.yaml", characters)

        # --- sequence_trigger.yaml: feedforward 데이터로 생성 ---
        feedforward = updates.get("feedforward", {})
        new_locations = feedforward.get("new_elements", {}).get("locations", []) or []
        next_loc = new_locations[0].get("name", "다음 목적지") if new_locations else "다음 목적지"

        # 새 payoffs 중 첫 번째를 트리거로 사용 (없으면 기존 pending 중 최고 weight)
        ff_payoffs = feedforward.get("new_payoffs_to_queue", []) or []
        pending_payoffs = state["payoff_queue"].get("pending_payoffs", [])
        if ff_payoffs:
            next_payoff_id = f"PAYOFF_{seq_id:02d}_01"
        elif pending_payoffs:
            top = sorted(pending_payoffs, key=lambda x: x.get("weight", 0), reverse=True)
            next_payoff_id = top[0].get("payoff_id", "")
        else:
            next_payoff_id = ""

        next_conflicts = feedforward.get("next_key_conflict", [])

        def _conflict_desc(c):
            return c.get("description", str(c)) if isinstance(c, dict) else str(c)

        trigger_yaml = {
            "sequence_id": next_seq_id + 1,
            "current_drive": {
                "main_goal": feedforward.get("next_main_goal", ""),
                "key_conflict": [
                    {
                        "type": c.get("type", "External") if isinstance(c, dict) else "External",
                        "description": _conflict_desc(c),
                    }
                    for c in next_conflicts
                ],
            },
            "ingredients_to_use": {
                "payoff_id_to_trigger": next_payoff_id,
                "location_constraint": next_loc,
            },
        }
        write_yaml(next_seq_path / "sequence_trigger.yaml", trigger_yaml)

        return {
            **state,
            "current_sequence_id": next_seq_id,
            "error": None,
        }
    except Exception as e:
        return {**state, "error": f"sequence_creator 오류: {e}"}
