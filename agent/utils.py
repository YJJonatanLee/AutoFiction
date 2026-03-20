import re
import yaml
import networkx as nx
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


def load_graph(characters: dict) -> nx.MultiDiGraph:
    """characters_and_factions dict → NetworkX MultiDiGraph.
    MultiDiGraph: 같은 두 노드 사이 relation 타입별 여러 엣지 허용."""
    G = nx.MultiDiGraph()
    nodes = characters.get("nodes", {})

    for node_type, items in nodes.items():
        for item in (items or []):
            nid = item.get("id")
            if nid:
                G.add_node(nid, node_type=node_type, **{k: v for k, v in item.items() if k != "id"})

    for edge in (characters.get("edges", []) or []):
        src, dst, rel = edge.get("from"), edge.get("to"), edge.get("relation")
        if src and dst and rel:
            attrs = {k: v for k, v in edge.items() if k not in ("from", "to", "relation")}
            G.add_edge(src, dst, key=rel, relation=rel, **attrs)

    return G


def dump_graph(G: nx.MultiDiGraph) -> dict:
    """NetworkX MultiDiGraph → characters_and_factions dict (YAML 저장용)"""
    nodes_by_type: dict = {}
    for nid, data in G.nodes(data=True):
        node_type = data.get("node_type", "characters")
        entry = {"id": nid, **{k: v for k, v in data.items() if k != "node_type"}}
        nodes_by_type.setdefault(node_type, []).append(entry)

    edges = []
    for src, dst, rel, data in G.edges(keys=True, data=True):
        edges.append({"from": src, "to": dst, "relation": rel, **{k: v for k, v in data.items() if k != "relation"}})

    return {"nodes": nodes_by_type, "edges": edges}


def extract_relevant_subgraph(G: nx.MultiDiGraph, radius: int = 2) -> nx.MultiDiGraph:
    """주인공(CHAR_01) 기준 radius 홉 이내 노드만 추출.
    CHAR_01이 없으면 전체 그래프 반환."""
    protagonist = "CHAR_01"
    if protagonist not in G:
        return G
    # 방향 무시하고 이웃 탐색 (undirected ego_graph)
    undirected = G.to_undirected()
    sub_nodes = set(nx.ego_graph(undirected, protagonist, radius=radius).nodes())
    return G.subgraph(sub_nodes).copy()
