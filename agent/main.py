import argparse
import os
from pathlib import Path

from .graph import build_graph


def main():
    parser = argparse.ArgumentParser(description="LangGraph Narrative Agent")
    parser.add_argument(
        "--max-sequences",
        type=int,
        default=3,
        help="생성할 최대 시퀀스 수 (기본값: 3)",
    )
    parser.add_argument(
        "--base-path",
        type=str,
        default=None,
        help="프로젝트 루트 경로 (기본값: 이 스크립트 기준 상위 디렉토리)",
    )
    parser.add_argument(
        "--start-sequence",
        type=int,
        default=1,
        help="시작 시퀀스 ID (기본값: 1)",
    )
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise EnvironmentError("ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다.")

    base_path = args.base_path or str(Path(__file__).parent.parent)

    graph = build_graph()

    initial_state = {
        "current_sequence_id": args.start_sequence,
        "max_sequences": args.max_sequences,
        "base_path": base_path,
        "world_rules": {},
        "main_logline": {},
        "events_log": {},
        "payoff_queue": {},
        "narrative_rules": {},
        "current_trigger": {},
        "current_characters": {},
        "generated_narrative": "",
        "raw_llm_output": "",
        "structured_updates": {},
        "novel_narrative": "",
        "error": None,
    }

    print(f"[시작] Sequence {args.start_sequence} → {args.max_sequences} 생성 시작")
    print(f"[경로] {base_path}\n")

    final_state = graph.invoke(initial_state)

    if final_state.get("error"):
        print(f"\n[오류] {final_state['error']}")
        return 1

    completed = final_state["current_sequence_id"] - 1
    print(f"\n[완료] Sequence {args.start_sequence} ~ {completed} 생성 완료")
    return 0


if __name__ == "__main__":
    exit(main())
