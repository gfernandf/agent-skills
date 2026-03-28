#!/usr/bin/env python3
"""Generate a static HTML catalog / marketplace site from catalog JSON files.

Reads ``catalog/capabilities.json`` and ``catalog/skills.json`` produced by
``tools/generate_catalog.py`` and emits a self-contained ``index.html`` inside
``catalog/site/`` that can be served by any static host (GitHub Pages, S3, etc.).

Usage::

    python tooling/generate_marketplace_site.py          # from agent-skills root
    python tooling/generate_marketplace_site.py --registry ../agent-skill-registry
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

_CSS = """\
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#c9d1d9;
--accent:#58a6ff;--green:#3fb950;--tag:#1f6feb33;font-family:system-ui,sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);padding:2rem}
h1{color:var(--accent);margin-bottom:.5rem}
.subtitle{color:#8b949e;margin-bottom:1.5rem}
.search{width:100%;padding:.6rem 1rem;border-radius:6px;border:1px solid var(--border);
background:var(--card);color:var(--text);font-size:1rem;margin-bottom:1.5rem}
.tabs{display:flex;gap:.5rem;margin-bottom:1rem}
.tab{padding:.4rem 1rem;border-radius:20px;border:1px solid var(--border);
cursor:pointer;background:transparent;color:var(--text);font-size:.85rem}
.tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:1rem}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;
padding:1rem;transition:border-color .2s}
.card:hover{border-color:var(--accent)}
.card h3{color:var(--accent);font-size:.95rem;margin-bottom:.4rem}
.card p{font-size:.82rem;color:#8b949e;line-height:1.4;margin-bottom:.6rem}
.tags{display:flex;flex-wrap:wrap;gap:.3rem}
.tag{font-size:.7rem;padding:.15rem .5rem;border-radius:12px;
background:var(--tag);color:var(--accent)}
.count{color:var(--green);font-weight:600}
"""

_JS = """\
document.addEventListener('DOMContentLoaded',()=>{
  const search=document.querySelector('.search');
  const cards=document.querySelectorAll('.card');
  const tabs=document.querySelectorAll('.tab');
  let activeType='all';
  search.addEventListener('input',filter);
  tabs.forEach(t=>t.addEventListener('click',()=>{
    tabs.forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    activeType=t.dataset.type;
    filter();
  }));
  function filter(){
    const q=search.value.toLowerCase();
    cards.forEach(c=>{
      const text=c.textContent.toLowerCase();
      const type=c.dataset.type;
      const matchType=activeType==='all'||type===activeType;
      c.style.display=(matchType&&text.includes(q))?'':'none';
    });
  }
});
"""


def _esc(text: str) -> str:
    return html.escape(str(text)) if text else ""


def _render_card(item: dict, card_type: str) -> str:
    name = _esc(item.get("id") or item.get("name") or item.get("slug", "unknown"))
    desc = _esc((item.get("description") or item.get("purpose") or "")[:200])
    channel = _esc(item.get("channel", ""))
    domain = _esc(item.get("domain", ""))
    tags_html = ""
    if channel:
        tags_html += f'<span class="tag">{channel}</span>'
    if domain:
        tags_html += f'<span class="tag">{domain}</span>'
    return (
        f'<div class="card" data-type="{card_type}">'
        f"<h3>{name}</h3>"
        f"<p>{desc}</p>"
        f'<div class="tags">{tags_html}</div>'
        f"</div>"
    )


def generate_site(registry_root: Path, output_dir: Path) -> Path:
    catalog_dir = registry_root / "catalog"
    caps_path = catalog_dir / "capabilities.json"
    skills_path = catalog_dir / "skills.json"

    capabilities: list[dict] = []
    skills: list[dict] = []

    if caps_path.exists():
        capabilities = json.loads(caps_path.read_text(encoding="utf-8"))
    if skills_path.exists():
        skills = json.loads(skills_path.read_text(encoding="utf-8"))

    cards_html = ""
    for cap in capabilities:
        cards_html += _render_card(cap, "capability")
    for skill in skills:
        cards_html += _render_card(skill, "skill")

    n_caps = len(capabilities)
    n_skills = len(skills)

    page = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>agent-skills Marketplace</title>
<style>{_CSS}</style>
</head>
<body>
<h1>agent-skills Marketplace</h1>
<p class="subtitle">
  <span class="count">{n_caps}</span> capabilities &middot;
  <span class="count">{n_skills}</span> skills
</p>
<input class="search" type="text" placeholder="Search capabilities and skills…"/>
<div class="tabs">
  <button class="tab active" data-type="all">All</button>
  <button class="tab" data-type="capability">Capabilities</button>
  <button class="tab" data-type="skill">Skills</button>
</div>
<div class="grid">{cards_html}</div>
<script>{_JS}</script>
</body>
</html>
"""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "index.html"
    out_path.write_text(page, encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate marketplace catalog site")
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Path to agent-skill-registry root (default: auto-detect sibling)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: <registry>/catalog/site)",
    )
    args = parser.parse_args()

    if args.registry:
        registry_root = args.registry.resolve()
    else:
        # Auto-detect: assume agent-skill-registry is sibling
        here = Path(__file__).resolve().parent.parent
        candidate = here.parent / "agent-skill-registry"
        if candidate.exists():
            registry_root = candidate
        else:
            registry_root = here

    output_dir = args.output or (registry_root / "catalog" / "site")
    out = generate_site(registry_root, output_dir)
    print(f"Marketplace site generated → {out}")


if __name__ == "__main__":
    main()
