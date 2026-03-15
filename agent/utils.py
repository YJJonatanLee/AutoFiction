import re
import yaml
from pathlib import Path


def read_yaml(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(path: str | Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def write_text(path: str | Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def parse_xml_sections(text: str) -> tuple[str, str]:
    """LLM 출력에서 <narrative>와 <updates> 블록을 분리."""
    narrative_match = re.search(r"<narrative>(.*?)</narrative>", text, re.DOTALL)
    updates_match = re.search(r"<updates>(.*?)</updates>", text, re.DOTALL)

    narrative = narrative_match.group(1).strip() if narrative_match else ""
    updates_raw = updates_match.group(1).strip() if updates_match else ""

    return narrative, updates_raw


def parse_updates_yaml(updates_raw: str) -> dict:
    """<updates> 블록 내부의 YAML 텍스트를 파싱."""
    try:
        return yaml.safe_load(updates_raw) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"updates 블록 YAML 파싱 실패: {e}\n원문:\n{updates_raw}")


def get_sequence_path(base_path: str, sequence_id: int) -> Path:
    return Path(base_path) / f"Sequence {sequence_id}"


def get_settings_path(base_path: str) -> Path:
    return Path(base_path) / "Settings"
