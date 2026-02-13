#!/usr/bin/env python3
"""
Anatomy Icon Gallery Generator

Scans all frontend app repos for icon usage, extracts SVGs from
@anatomy-financial/anatomy-ui-core, and generates a static HTML gallery.

Usage:
    python update-gallery.py                  # Generate gallery only
    python update-gallery.py --push           # Generate + commit + push to GitHub
    python update-gallery.py --open           # Generate + open in browser
    python update-gallery.py --push --open    # All of the above
"""

import argparse
import os
import re
import subprocess
import webbrowser
from datetime import date
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────────────────

ANATOMY_ROOT = Path(__file__).resolve().parent.parent  # /Users/.../anatomy
REPO_DIR = Path(__file__).resolve().parent              # anatomy-icon-gallery/
OUTPUT_FILE = REPO_DIR / "index.html"

# Where to find the compiled icon components
ICON_PACKAGE_LOCATIONS = [
    ANATOMY_ROOT / "review-eob-mf" / "node_modules" / "@anatomy-financial" / "anatomy-ui-core" / "dist" / "icons",
    ANATOMY_ROOT / "empire" / "node_modules" / "@anatomy-financial" / "anatomy-ui-core" / "dist" / "icons",
    ANATOMY_ROOT / "hil-ui" / "node_modules" / "@anatomy-financial" / "anatomy-ui-core" / "dist" / "icons",
    ANATOMY_ROOT / "document-center-mf" / "node_modules" / "@anatomy-financial" / "anatomy-ui-core" / "dist" / "icons",
    ANATOMY_ROOT / "anatomy-financials-ui" / "node_modules" / "@anatomy-financial" / "anatomy-ui-core" / "dist" / "icons",
]

# Frontend app source directories to scan for icon usage
APP_SOURCE_DIRS = {
    "hil-ui": ANATOMY_ROOT / "hil-ui" / "src",
    "empire": ANATOMY_ROOT / "empire" / "src",
    "anatomy-financials-ui": ANATOMY_ROOT / "anatomy-financials-ui" / "src",
    "document-center-mf": ANATOMY_ROOT / "document-center-mf" / "src",
    "review-eob-mf": ANATOMY_ROOT / "review-eob-mf" / "src",
}

APP_COLORS = {
    "hil-ui": "#4A90D9",
    "empire": "#D94A4A",
    "anatomy-financials-ui": "#4AD97A",
    "document-center-mf": "#D9A04A",
    "review-eob-mf": "#9B4AD9",
}


# ─── SVG Extraction ─────────────────────────────────────────────────────────

def find_icons_dir():
    """Find the first available icons directory from node_modules."""
    for loc in ICON_PACKAGE_LOCATIONS:
        if loc.is_dir():
            return loc
    raise FileNotFoundError(
        "Could not find @anatomy-financial/anatomy-ui-core icons in any repo's node_modules. "
        "Run `npm install` in at least one frontend repo first."
    )


def extract_svg_from_js(js_content):
    """Parse a compiled React icon component .js file and extract standalone SVG markup."""
    # Extract SVG attributes
    width_m = re.search(r'width:\s*["\'](\d+)["\']', js_content)
    height_m = re.search(r'height:\s*["\'](\d+)["\']', js_content)
    viewbox_m = re.search(r'viewBox:\s*["\']([^"\']+)["\']', js_content)

    if not viewbox_m:
        return None

    width = width_m.group(1) if width_m else "24"
    height = height_m.group(1) if height_m else "24"
    viewbox = viewbox_m.group(1)

    elements = []

    # Extract <path> elements
    for m in re.finditer(r'd:\s*["\']([^"\']+)["\'][^}]*?(?:fill:\s*([^,}]+?)\s*[,}])?', js_content):
        d = m.group(1)
        fill = m.group(2).strip().strip("\"'") if m.group(2) else "#333"
        if "var(" in fill or fill in ("void 0", "fill", "undefined"):
            fill = "#333"

        # Check for fillRule nearby
        context = js_content[max(0, m.start() - 200):m.end()]
        fill_rule = ' fill-rule="evenodd" clip-rule="evenodd"' if "fillRule" in context else ""

        elements.append(f'<path d="{d}" fill="{fill}"{fill_rule}/>')

    # Extract <circle> elements
    for m in re.finditer(
        r'jsx\("circle",\s*\{[^}]*cx:\s*["\']([^"\']+)["\'][^}]*cy:\s*["\']([^"\']+)["\']'
        r'[^}]*r:\s*["\']([^"\']+)["\'][^}]*(?:fill:\s*["\']([^"\']+)["\'])?',
        js_content
    ):
        fill = m.group(4) or "#333"
        if "var(" in fill:
            fill = "#333"
        elements.append(f'<circle cx="{m.group(1)}" cy="{m.group(2)}" r="{m.group(3)}" fill="{fill}"/>')

    if not elements:
        return None

    return (
        f'<svg width="{width}" height="{height}" viewBox="{viewbox}" '
        f'fill="none" xmlns="http://www.w3.org/2000/svg">{"".join(elements)}</svg>'
    )


def get_exported_name(js_content):
    """Get the exported function/component name from a compiled JS file."""
    m = re.search(r'export\s*\{\s*(\w+)', js_content)
    return m.group(1) if m else None


def load_all_icons(icons_dir):
    """Load all icons from the package dist/icons directory."""
    icons = {}
    for entry in sorted(icons_dir.iterdir()):
        if not entry.is_dir():
            continue
        js_files = [f for f in entry.iterdir() if f.suffix == ".js" and ".map" not in f.name]
        if not js_files:
            continue

        content = js_files[0].read_text(encoding="utf-8")
        name = get_exported_name(content) or entry.name
        svg = extract_svg_from_js(content)
        if svg:
            icons[name] = {"svg": svg, "folder": entry.name, "used_by": []}

    return icons


# ─── App Usage Scanning ──────────────────────────────────────────────────────

def scan_app_for_icons(src_dir, known_icon_names):
    """Scan a frontend app's source for imported icon names."""
    found = set()
    if not src_dir.is_dir():
        return found

    for root, _, files in os.walk(src_dir):
        for fname in files:
            if not fname.endswith((".ts", ".tsx", ".js", ".jsx")):
                continue
            fpath = Path(root) / fname
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # Match icon names from import statements
            for icon_name in known_icon_names:
                if icon_name in content:
                    found.add(icon_name)

    return found


# ─── HTML Generation ─────────────────────────────────────────────────────────

def generate_html(icons, today):
    """Generate the full HTML gallery page."""
    total = len(icons)
    sorted_icons = sorted(icons.items(), key=lambda x: x[0].lower())

    # Stats per app
    app_stats = {}
    for app in APP_COLORS:
        app_stats[app] = sum(1 for _, v in sorted_icons if app in v["used_by"])

    stat_blocks = "\n  ".join(
        f'<div class="stat"><div class="stat-num">{count}</div><div class="stat-label">{app}</div></div>'
        for app, count in app_stats.items()
    )
    legend_items = "\n  ".join(
        f'<div class="legend-item"><div class="legend-dot" style="background:{color}"></div>{app}</div>'
        for app, color in APP_COLORS.items()
    )
    filter_buttons = "\n  ".join(
        f'<button class="filter-btn" data-app="{app}" onclick="setFilter(\'{app}\', this)">{app}</button>'
        for app in APP_COLORS
    )

    icon_cards = []
    for name, data in sorted_icons:
        apps_str = ",".join(data["used_by"])
        tags = "".join(
            f'<div class="app-tag" style="background:{APP_COLORS[app]}" title="{app}"></div>'
            for app in data["used_by"]
        )
        used_label = "Used by: " + ", ".join(data["used_by"]) if data["used_by"] else "Not directly imported"
        icon_cards.append(
            f'<div class="icon-card" data-name="{name.lower()}" data-apps="{apps_str}" '
            f'title="{name}&#10;{used_label}">\n'
            f'    <div class="icon-preview">{data["svg"]}</div>\n'
            f'    <div class="icon-name">{name}</div>\n'
            f'    <div class="app-tags">{tags}</div>\n'
            f'  </div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Anatomy Frontend Icon Gallery</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; padding: 24px; }}
  h1 {{ font-size: 28px; margin-bottom: 8px; }}
  .subtitle {{ color: #666; margin-bottom: 24px; font-size: 14px; }}
  .stats {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
  .stat {{ background: white; border-radius: 8px; padding: 12px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .stat-num {{ font-size: 24px; font-weight: 700; }}
  .stat-label {{ font-size: 12px; color: #666; }}
  .legend {{ display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 12px; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  .filters {{ margin-bottom: 24px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
  .search {{ padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; width: 300px; }}
  .filter-btn {{ padding: 6px 12px; border: 1px solid #ddd; border-radius: 16px; font-size: 12px; cursor: pointer; background: white; transition: all 0.2s; }}
  .filter-btn:hover, .filter-btn.active {{ background: #333; color: white; border-color: #333; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }}
  .icon-card {{ background: white; border-radius: 8px; padding: 16px; display: flex; flex-direction: column; align-items: center; gap: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); transition: all 0.2s; cursor: pointer; }}
  .icon-card:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.15); transform: translateY(-2px); }}
  .icon-preview {{ width: 48px; height: 48px; display: flex; align-items: center; justify-content: center; }}
  .icon-preview svg {{ max-width: 100%; max-height: 100%; }}
  .icon-name {{ font-size: 11px; text-align: center; word-break: break-all; color: #555; font-weight: 500; }}
  .app-tags {{ display: flex; gap: 3px; flex-wrap: wrap; justify-content: center; }}
  .app-tag {{ width: 8px; height: 8px; border-radius: 50%; }}
  .hidden {{ display: none; }}
  .count {{ font-size: 14px; color: #999; margin-left: 8px; }}
</style>
</head>
<body>

<h1>Anatomy Frontend Icon Gallery</h1>
<p class="subtitle">All {total} icons from @anatomy-financial/anatomy-ui-core &mdash; Updated {today}</p>

<div class="stats">
  <div class="stat"><div class="stat-num">{total}</div><div class="stat-label">Total Icons</div></div>
  {stat_blocks}
</div>

<div class="legend">
  {legend_items}
</div>

<div class="filters">
  <input class="search" type="text" placeholder="Search icons..." oninput="filterIcons()">
  <button class="filter-btn active" data-app="all" onclick="setFilter('all', this)">All</button>
  {filter_buttons}
  <span class="count" id="visibleCount">{total} icons</span>
</div>

<div class="grid" id="iconGrid">
  {"".join(icon_cards)}
</div>

<script>
let currentFilter = 'all';

function setFilter(app, btn) {{
  currentFilter = app;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  filterIcons();
}}

function filterIcons() {{
  const search = document.querySelector('.search').value.toLowerCase();
  let visible = 0;
  document.querySelectorAll('.icon-card').forEach(card => {{
    const name = card.dataset.name;
    const apps = card.dataset.apps;
    const matchSearch = !search || name.includes(search);
    const matchApp = currentFilter === 'all' || apps.includes(currentFilter);
    const show = matchSearch && matchApp;
    card.classList.toggle('hidden', !show);
    if (show) visible++;
  }});
  document.getElementById('visibleCount').textContent = visible + ' icons';
}}

document.querySelectorAll('.icon-card').forEach(card => {{
  card.addEventListener('click', () => {{
    const svg = card.querySelector('.icon-preview').innerHTML;
    navigator.clipboard.writeText(svg).then(() => {{
      const name = card.querySelector('.icon-name');
      const orig = name.textContent;
      name.textContent = 'Copied!';
      name.style.color = '#4AD97A';
      setTimeout(() => {{ name.textContent = orig; name.style.color = '#555'; }}, 1000);
    }});
  }});
}});
</script>
</body>
</html>"""


# ─── Git Operations ──────────────────────────────────────────────────────────

def git_push():
    """Commit and push changes to GitHub."""
    os.chdir(REPO_DIR)

    # Check for changes
    result = subprocess.run(["git", "diff", "--stat", "index.html"], capture_output=True, text=True)
    if not result.stdout.strip():
        print("No changes to commit.")
        return False

    subprocess.run(["git", "add", "index.html"], check=True)
    subprocess.run(
        ["git", "commit", "-m", f"Update icon gallery ({date.today().isoformat()})"],
        check=True,
    )
    subprocess.run(["git", "push"], check=True)
    print("Pushed to GitHub. Site will update in ~1 minute.")
    print("  https://jvu-anatomy.github.io/anatomy-icon-gallery/")
    return True


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate the Anatomy icon gallery")
    parser.add_argument("--push", action="store_true", help="Commit and push to GitHub after generating")
    parser.add_argument("--open", action="store_true", help="Open the gallery in the browser after generating")
    args = parser.parse_args()

    print("Finding icon package...")
    icons_dir = find_icons_dir()
    print(f"  Using: {icons_dir}")

    print("Extracting SVGs from compiled React components...")
    icons = load_all_icons(icons_dir)
    print(f"  Found {len(icons)} icons")

    print("Scanning app source directories for icon usage...")
    for app_name, src_dir in APP_SOURCE_DIRS.items():
        if not src_dir.is_dir():
            print(f"  {app_name}: skipped (directory not found)")
            continue
        used = scan_app_for_icons(src_dir, set(icons.keys()))
        for icon_name in used:
            if icon_name in icons:
                icons[icon_name]["used_by"].append(app_name)
        print(f"  {app_name}: {len(used)} icons")

    print("Generating HTML...")
    html = generate_html(icons, date.today().isoformat())
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"  Written to: {OUTPUT_FILE}")

    if args.push:
        print("Pushing to GitHub...")
        git_push()

    if args.open:
        webbrowser.open(f"file://{OUTPUT_FILE}")

    print("Done!")


if __name__ == "__main__":
    main()
