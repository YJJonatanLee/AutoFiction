from typing import Optional, TypedDict


class NarrativeState(TypedDict):
    # 제어
    current_sequence_id: int
    max_sequences: int
    base_path: str

    # Settings (항상 최신)
    world_rules: dict
    main_logline: dict
    events_log: dict
    payoff_queue: dict
    narrative_rules: dict

    # 현재 시퀀스 입력
    current_trigger: dict
    current_characters: dict

    # LLM 출력
    generated_narrative: str
    raw_llm_output: str
    structured_updates: dict
    novel_narrative: str

    # 에러
    error: Optional[str]
