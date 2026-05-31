#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml

EGG_FILE_PATTERN = re.compile(r"egg-.*\.(json|yaml|yml)$", re.IGNORECASE)


def humanize_nest_type(name: str) -> str:
    name = name.replace("_", " ").replace("-", " ")
    return " ".join(word.capitalize() for word in name.split())


def load_egg_file(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".json":
        return json.loads(text)

    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(text)

    raise RuntimeError(f"Unsupported egg file type: {path}")


def parse_egg_metadata(path: Path) -> Dict[str, Any]:
    data = load_egg_file(path)
    metadata = {
        "name": None,
        "description": None,
        "version": None,
        "readme": "",
    }

    if not isinstance(data, dict):
        return metadata

    metadata["name"] = data.get("name")
    metadata["description"] = data.get("description")

    if isinstance(data.get("meta"), dict):
        metadata["version"] = data["meta"].get("version")
    elif isinstance(data.get("egg"), dict):
        egg_data = data["egg"]
        if isinstance(egg_data.get("meta"), dict):
            metadata["version"] = egg_data["meta"].get("version")

    return metadata


def build_download_url(base_owner: str, repo: str, branch: str, relative_path: str) -> str:
    relative_path = Path(relative_path).as_posix()
    return f"https://raw.githubusercontent.com/{base_owner}/{repo}/refs/heads/{branch}/{relative_path}"


def collect_eggs(repos_dir: Path, base_owner: str, branch: str) -> Tuple[defaultdict[str, list[Dict[str, Any]]], defaultdict[str, list[Dict[str, Any]]]]:
    pelican_nests: defaultdict[str, list[Dict[str, Any]]] = defaultdict(list)
    pterodactyl_nests: defaultdict[str, list[Dict[str, Any]]] = defaultdict(list)

    for path in sorted(repos_dir.rglob("*egg-*")):
        if not path.is_file() or not EGG_FILE_PATTERN.search(path.name):
            continue

        relative = path.relative_to(repos_dir)
        if len(relative.parts) < 2:
            continue

        if any(part.startswith(".") for part in relative.parts[1:]):
            continue

        repo_name = relative.parts[0]
        nest_type = humanize_nest_type(repo_name)
        repo_relative_path = Path(*relative.parts[1:]).as_posix()

        metadata = parse_egg_metadata(path)
        if not metadata["name"]:
            continue

        download_url = build_download_url(
            base_owner=base_owner,
            repo=repo_name,
            branch=branch,
            relative_path=repo_relative_path,
        )

        egg_entry = {
            "egg": {
                "name": metadata["name"],
                "meta": {"version": metadata["version"]},
                "description": (metadata["description"] or "").replace("\r\n", " ").replace("\n", " "),
            },
            "download_url": download_url,
            "readme": metadata["readme"],
        }

        if "pterodactyl" in path.name.lower():
            pterodactyl_nests[nest_type].append(egg_entry)
        else:
            pelican_nests[nest_type].append(egg_entry)

    return pelican_nests, pterodactyl_nests


def escape_markdown_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\r\n", " ").replace("\n", " ")


def render_markdown(panel_type: str, nests: Dict[str, list[Dict[str, Any]]]) -> str:
    lines: list[str] = [
        "+++",
        f"title = '{panel_type} Eggs'",
        "draft = false",
        "+++",
    ]

    if panel_type == "Pelican":
        lines.append("> # All pelican eggs can be imported directly in the Pelican Panel!")
    else:
        lines.append("")
    lines.append("")

    for nest_type, eggs in sorted(nests.items()):
        lines.append(f"## {nest_type}")
        lines.append("| Egg | Description |")
        lines.append("|-----|----------|")
        for egg in sorted(eggs, key=lambda e: (e["egg"]["name"] or "").lower()):
            name = escape_markdown_cell(egg["egg"]["name"] or "")
            description = escape_markdown_cell(egg["egg"]["description"] or "")
            url = egg["download_url"]
            lines.append(f"| [{name}]({url}) | {description} |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def generate_output(nests: Dict[str, Any], panel_type: str) -> Dict[str, Any]:
    return {
        "panel_type": panel_type,
        "nests": [
            {"nest_type": nest_type, "Eggs": eggs}
            for nest_type, eggs in sorted(nests.items())
        ],
    }


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    repos_path = (root / "repos").resolve()
    branch = "main"
    owner = "pelican-eggs"
    outputs = {
        "pelican.json": "Pelican",
        "pterodactyl.json": "Pterodactyl",
    }

    if not repos_path.is_dir():
        raise SystemExit(f"repos directory not found: {repos_path}")

    pelican_nests, pterodactyl_nests = collect_eggs(repos_path, owner, branch)
    output_dir = (root / "content").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    file_sets = [
        ("pelican.json", pelican_nests, outputs["pelican.json"]),
        ("pterodactyl.json", pterodactyl_nests, outputs["pterodactyl.json"]),
    ]

    for filename, nests, panel_type in file_sets:
        payload = generate_output(nests, panel_type)

        output_path = output_dir / filename
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent="\t") + "\n", encoding="utf-8")
        print(f"Generated {output_path} with {len(payload['nests'])} nests.")

        md_output_path = output_dir / f"{Path(filename).stem}.md"
        md_output_path.write_text(render_markdown(panel_type, nests), encoding="utf-8")
        print(f"Generated {md_output_path} with {len(nests)} sections.")

    total_pelican = sum(len(v) for v in pelican_nests.values())
    total_ptero = sum(len(v) for v in pterodactyl_nests.values())
    print(
        f"Done: {total_pelican} pelican eggs and {total_ptero} pterodactyl eggs across {len(pelican_nests)} pelican nests and {len(pterodactyl_nests)} pterodactyl nests."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
