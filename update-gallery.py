#!/usr/bin/env python3
"""
Anatomy Icon Gallery Generator

Scans ALL frontend app repos for icon usage, extracts SVGs from:
  1. @anatomy-financial/anatomy-ui-core (from every repo's node_modules)
  2. Custom SVG components (e.g. anatomy-financials-ui/src/components/svgs/)
  3. Local designSystem icon re-exports (empire, hil-ui)
  4. PrimeIcons CSS class usage

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

# All frontend repos
REPOS = ["review-eob-mf", "empire", "hil-ui", "document-center-mf", "anatomy-financials-ui"]

# Frontend app source directories to scan for icon usage
APP_SOURCE_DIRS = {repo: ANATOMY_ROOT / repo / "src" for repo in REPOS}

# Directories containing custom SVG icon components (not from the shared package)
CUSTOM_SVG_DIRS = {
    "anatomy-financials-ui": [
        ANATOMY_ROOT / "anatomy-financials-ui" / "src" / "components" / "svgs",
    ],
}

APP_COLORS = {
    "hil-ui": "#4A90D9",
    "empire": "#D94A4A",
    "anatomy-financials-ui": "#4AD97A",
    "document-center-mf": "#D9A04A",
    "review-eob-mf": "#9B4AD9",
}

# Known PrimeIcon CSS classes used across apps
PRIMEICON_PATTERN = re.compile(r"""pi[- ]pi-([a-z0-9-]+)|iconClass\s*=\s*['"]pi-([a-z0-9-]+)['"]""")


# ─── SVG Extraction from compiled React components ───────────────────────────

def extract_svg_from_js(js_content):
    """Parse a compiled React icon component .js file and extract standalone SVG markup."""
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
        context = js_content[max(0, m.start() - 200):m.end()]
        fill_rule = ' fill-rule="evenodd" clip-rule="evenodd"' if "fillRule" in context else ""
        elements.append(f'<path d="{d}" fill="{fill}"{fill_rule}/>')

    # Extract <circle> elements
    for m in re.finditer(
        r'jsx\("circle",\s*\{[^}]*cx:\s*["\']([^"\']+)["\'][^}]*cy:\s*["\']([^"\']+)["\']'
        r'[^}]*r:\s*["\']([^"\']+)["\'][^}]*(?:fill:\s*["\']([^"\']+)["\'])?',
        js_content,
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


def extract_svg_from_tsx(tsx_content):
    """Extract SVG from a source .tsx custom icon component."""
    # Find the SVG tag and its content
    svg_match = re.search(r'(<svg[^>]*>)(.*?)(</svg>)', tsx_content, re.DOTALL)
    if not svg_match:
        return None

    svg_open = svg_match.group(1)
    svg_inner = svg_match.group(2)
    svg_close = svg_match.group(3)

    # Clean JSX attributes to HTML: className -> class, remove {...props}, etc.
    svg_open = re.sub(r'\s*\{\.\.\.props\}', '', svg_open)
    svg_open = svg_open.replace('className=', 'class=')
    # Remove JSX expressions like fill={something}
    svg_open = re.sub(r'\w+=\{[^}]+\}', '', svg_open)

    # Clean inner content
    svg_inner = svg_inner.replace('className=', 'class=')
    svg_inner = re.sub(r'\w+=\{[^}]+\}', '', svg_inner)
    # Remove JSX fragments
    svg_inner = svg_inner.replace('<>', '').replace('</>', '')

    # Ensure viewBox exists
    if 'viewBox' not in svg_open:
        width_m = re.search(r'width="(\d+)"', svg_open)
        height_m = re.search(r'height="(\d+)"', svg_open)
        if width_m and height_m:
            svg_open = svg_open.replace('>', f' viewBox="0 0 {width_m.group(1)} {height_m.group(1)}">', 1)

    full_svg = svg_open + svg_inner + svg_close
    # Replace any remaining CSS variable fills with defaults
    full_svg = re.sub(r'fill="var\([^)]+\)"', 'fill="#333"', full_svg)
    # Replace empty fills
    full_svg = re.sub(r'fill=""', 'fill="#333"', full_svg)

    return full_svg


def get_exported_name(js_content):
    """Get the exported function/component name from a compiled JS file."""
    m = re.search(r'export\s*\{\s*(\w+)', js_content)
    return m.group(1) if m else None


def get_exported_name_tsx(tsx_content, filename):
    """Get the exported component name from a source .tsx file."""
    m = re.search(r'export\s+(?:default\s+)?function\s+(\w+)', tsx_content)
    if m:
        return m.group(1)
    m = re.search(r'export\s+const\s+(\w+)', tsx_content)
    if m:
        return m.group(1)
    # Fall back to filename
    return Path(filename).stem


# ─── Icon Loading ────────────────────────────────────────────────────────────

def load_package_icons():
    """Load icons from @anatomy-financial/anatomy-ui-core across all repos' node_modules.

    Merges icons from all available copies so we catch version differences.
    """
    icons = {}
    seen_dirs = set()

    for repo in REPOS:
        icons_dir = ANATOMY_ROOT / repo / "node_modules" / "@anatomy-financial" / "anatomy-ui-core" / "dist" / "icons"
        if not icons_dir.is_dir():
            continue

        for entry in sorted(icons_dir.iterdir()):
            if not entry.is_dir():
                continue
            js_files = [f for f in entry.iterdir() if f.suffix == ".js" and ".map" not in f.name]
            if not js_files:
                continue

            content = js_files[0].read_text(encoding="utf-8")
            name = get_exported_name(content) or entry.name
            if name in icons:
                continue  # already loaded from another repo

            svg = extract_svg_from_js(content)
            if svg:
                icons[name] = {"svg": svg, "source": "anatomy-ui-core", "used_by": []}

    return icons


def load_custom_svg_icons():
    """Load custom SVG icon components from app-specific directories."""
    icons = {}

    for app_name, dirs in CUSTOM_SVG_DIRS.items():
        for svg_dir in dirs:
            if not svg_dir.is_dir():
                continue

            for fpath in sorted(svg_dir.rglob("*.tsx")):
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                name = get_exported_name_tsx(content, fpath.name)
                if name in icons:
                    continue  # prefer the package version if it exists

                svg = extract_svg_from_tsx(content)
                if svg:
                    # Determine relative path for source label
                    rel = fpath.relative_to(ANATOMY_ROOT)
                    icons[name] = {"svg": svg, "source": f"custom ({app_name})", "used_by": []}

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
            for icon_name in known_icon_names:
                if icon_name in content:
                    found.add(icon_name)

    return found


def scan_app_for_primeicons(src_dir):
    """Scan a frontend app for PrimeIcon CSS class usage."""
    found = set()
    if not src_dir.is_dir():
        return found

    for root, _, files in os.walk(src_dir):
        for fname in files:
            if not fname.endswith((".ts", ".tsx", ".js", ".jsx", ".scss", ".css")):
                continue
            fpath = Path(root) / fname
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for m in PRIMEICON_PATTERN.finditer(content):
                name = m.group(1) or m.group(2)
                if name:
                    found.add(f"pi-{name}")

    return found


# ─── HTML Generation ─────────────────────────────────────────────────────────

def generate_html(icons, primeicons_by_app, today):
    """Generate the full HTML gallery page."""
    total = len(icons)
    sorted_icons = sorted(icons.items(), key=lambda x: x[0].lower())

    # Collect all primeicon names across apps
    all_primeicons = set()
    for app_icons in primeicons_by_app.values():
        all_primeicons |= app_icons

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
        source_label = data.get("source", "")
        used_label = "Used by: " + ", ".join(data["used_by"]) if data["used_by"] else "Not directly imported"
        source_badge = (
            '<span class="source-badge source-custom">custom</span>'
            if "custom" in source_label
            else '<span class="source-badge source-core">core</span>'
        )
        icon_cards.append(
            f'<div class="icon-card" data-name="{name.lower()}" data-apps="{apps_str}" '
            f'data-source="{source_label}" '
            f'title="{name}&#10;{used_label}&#10;Source: {source_label}">\n'
            f'    <div class="icon-preview">{data["svg"]}</div>\n'
            f'    <div class="icon-name">{name}</div>\n'
            f'    {source_badge}\n'
            f'    <div class="app-tags">{tags}</div>\n'
            f'  </div>'
        )

    # PrimeIcons section
    primeicon_cards = []
    for pi_name in sorted(all_primeicons):
        apps_using = [app for app, icons_set in primeicons_by_app.items() if pi_name in icons_set]
        apps_str = ",".join(apps_using)
        tags = "".join(
            f'<div class="app-tag" style="background:{APP_COLORS[app]}" title="{app}"></div>'
            for app in apps_using
        )
        primeicon_cards.append(
            f'<div class="icon-card primeicon-card" data-name="{pi_name}" data-apps="{apps_str}" '
            f'title="{pi_name}&#10;Used by: {", ".join(apps_using)}">\n'
            f'    <div class="icon-preview"><i class="pi {pi_name}" style="font-size:24px;color:#333"></i></div>\n'
            f'    <div class="icon-name">{pi_name}</div>\n'
            f'    <span class="source-badge source-prime">prime</span>\n'
            f'    <div class="app-tags">{tags}</div>\n'
            f'  </div>'
        )

    grand_total = total + len(all_primeicons)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Anatomy Frontend Icon Gallery</title>
<link rel="stylesheet" href="https://unpkg.com/primeicons@6.0.1/primeicons.css">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; padding: 24px; }}
  h1 {{ font-size: 28px; margin-bottom: 8px; }}
  h2 {{ font-size: 20px; margin: 32px 0 16px; padding-bottom: 8px; border-bottom: 2px solid #e0e0e0; }}
  .subtitle {{ color: #666; margin-bottom: 24px; font-size: 14px; }}
  .stats {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
  .stat {{ background: white; border-radius: 8px; padding: 12px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .stat-num {{ font-size: 24px; font-weight: 700; }}
  .stat-label {{ font-size: 12px; color: #666; }}
  .legend {{ display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; align-items: center; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 12px; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  .legend-divider {{ width: 1px; height: 16px; background: #ddd; margin: 0 4px; }}
  .source-badge {{ font-size: 9px; padding: 1px 6px; border-radius: 8px; font-weight: 600; text-transform: uppercase; }}
  .source-core {{ background: #e8f4fd; color: #2b6cb0; }}
  .source-custom {{ background: #fef3cd; color: #856404; }}
  .source-prime {{ background: #f0e6ff; color: #6b21a8; }}
  .filters {{ margin-bottom: 24px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; position: sticky; top: 0; background: #f5f5f5; padding: 12px 0; z-index: 10; }}
  .search {{ padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; width: 300px; }}
  .filter-btn {{ padding: 6px 12px; border: 1px solid #ddd; border-radius: 16px; font-size: 12px; cursor: pointer; background: white; transition: all 0.2s; }}
  .filter-btn:hover, .filter-btn.active {{ background: #333; color: white; border-color: #333; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }}
  .icon-card {{ background: white; border-radius: 8px; padding: 16px; display: flex; flex-direction: column; align-items: center; gap: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); transition: all 0.2s; cursor: pointer; }}
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
<p class="subtitle">{grand_total} total icons ({total} SVG components + {len(all_primeicons)} PrimeIcons) &mdash; Updated {today}</p>

<div class="stats">
  <div class="stat"><div class="stat-num">{grand_total}</div><div class="stat-label">Total Icons</div></div>
  {stat_blocks}
</div>

<div class="legend">
  {legend_items}
  <div class="legend-divider"></div>
  <div class="legend-item"><span class="source-badge source-core">core</span> anatomy-ui-core</div>
  <div class="legend-item"><span class="source-badge source-custom">custom</span> app-specific SVG</div>
  <div class="legend-item"><span class="source-badge source-prime">prime</span> PrimeIcons CSS</div>
</div>

<div class="filters">
  <input class="search" type="text" placeholder="Search icons..." oninput="filterIcons()">
  <button class="filter-btn active" data-app="all" onclick="setFilter('all', this)">All</button>
  {filter_buttons}
  <span class="count" id="visibleCount">{grand_total} icons</span>
</div>

<h2>SVG Icon Components ({total})</h2>
<div class="grid" id="iconGrid">
  {"".join(icon_cards)}
</div>

<h2>PrimeIcons CSS ({len(all_primeicons)})</h2>
<div class="grid" id="primeGrid">
  {"".join(primeicon_cards)}
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
    const preview = card.querySelector('.icon-preview');
    const svg = preview.querySelector('svg');
    const text = svg ? svg.outerHTML : card.querySelector('.icon-name').textContent;
    navigator.clipboard.writeText(text).then(() => {{
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

    result = subprocess.run(["git", "diff", "--stat", "index.html"], capture_output=True, text=True)
    if not result.stdout.strip():
        print("  No changes to commit.")
        return False

    subprocess.run(["git", "add", "index.html"], check=True)
    subprocess.run(
        ["git", "commit", "-m", f"Update icon gallery ({date.today().isoformat()})"],
        check=True,
    )
    subprocess.run(["git", "push"], check=True)
    print("  Pushed to GitHub. Site will update in ~1 minute.")
    print("  https://jvu-anatomy.github.io/anatomy-icon-gallery/")
    return True


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate the Anatomy icon gallery")
    parser.add_argument("--push", action="store_true", help="Commit and push to GitHub after generating")
    parser.add_argument("--open", action="store_true", help="Open the gallery in the browser after generating")
    args = parser.parse_args()

    # 1. Load icons from the shared package (merging across all repos)
    print("Loading icons from @anatomy-financial/anatomy-ui-core (all repos)...")
    icons = load_package_icons()
    print(f"  Found {len(icons)} icons from anatomy-ui-core")

    # 2. Load custom SVG icons from app-specific directories
    print("Loading custom SVG icon components...")
    custom_icons = load_custom_svg_icons()
    # Only add custom icons that aren't already in the package
    new_custom = 0
    for name, data in custom_icons.items():
        if name not in icons:
            icons[name] = data
            new_custom += 1
    print(f"  Found {len(custom_icons)} custom icons ({new_custom} unique, not in core)")

    # 3. Scan each app for icon usage
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

    # 4. Scan for PrimeIcons CSS usage
    print("Scanning for PrimeIcons CSS class usage...")
    primeicons_by_app = {}
    for app_name, src_dir in APP_SOURCE_DIRS.items():
        if not src_dir.is_dir():
            continue
        pi = scan_app_for_primeicons(src_dir)
        if pi:
            primeicons_by_app[app_name] = pi
            print(f"  {app_name}: {len(pi)} PrimeIcons")

    # 5. Generate HTML
    print("Generating HTML...")
    html = generate_html(icons, primeicons_by_app, date.today().isoformat())
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"  Written to: {OUTPUT_FILE}")

    all_primeicons = set()
    for pi_set in primeicons_by_app.values():
        all_primeicons |= pi_set
    print(f"\nSummary: {len(icons)} SVG icons + {len(all_primeicons)} PrimeIcons = {len(icons) + len(all_primeicons)} total")

    if args.push:
        print("Pushing to GitHub...")
        git_push()

    if args.open:
        webbrowser.open(f"file://{OUTPUT_FILE}")

    print("Done!")


if __name__ == "__main__":
    main()
