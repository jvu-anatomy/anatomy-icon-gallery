# Anatomy Frontend Icon Gallery

A visual gallery of every icon used across the Anatomy frontend applications, hosted on GitHub Pages.

**Live site:** [jvu-anatomy.github.io/anatomy-icon-gallery](https://jvu-anatomy.github.io/anatomy-icon-gallery/)

## What It Gathers

The gallery scans five frontend repositories and collects icons from three sources:

### 1. anatomy-ui-core (shared design system)

Icons distributed through the `@anatomy-financial/anatomy-ui-core` npm package. These are compiled React components with inline SVG, located in each repo's `node_modules/@anatomy-financial/anatomy-ui-core/dist/icons/`. The script scans all five repos' `node_modules` and merges the results to account for version differences.

### 2. Custom SVG Components

App-specific SVG icon components that live outside the shared package. Currently this includes icons in `anatomy-financials-ui/src/components/svgs/` (and its `transactionIcons/` subdirectory). These are `.tsx` files containing inline SVG markup.

### 3. PrimeIcons (CSS)

CSS-based icons from the [PrimeIcons](https://primeng.org/icons) library, detected by scanning for `pi-*` class patterns in `.tsx`, `.scss`, and `.css` files. These are rendered in the gallery using the PrimeIcons CDN.

### Repos Scanned

| Repository | Description |
|---|---|
| `review-eob-mf` | EOB review micro-frontend |
| `empire` | Empire application |
| `hil-ui` | HIL user interface |
| `document-center-mf` | Document center micro-frontend |
| `anatomy-financials-ui` | Main financials UI application |

### Gallery Features

- Search icons by name
- Filter by application
- Source badges showing where each icon comes from (core / custom / prime)
- Colored dots indicating which apps use each icon
- Click any icon card to copy its SVG to clipboard

## Updating the Gallery

### Prerequisites

- **Python 3.6+** (uses `pathlib`, `argparse`, f-strings)
- **Git** (for committing and pushing)
- **GitHub CLI (`gh`)** is not required for updates, only standard `git`
- All five frontend repos cloned as siblings under the same parent directory:
  ```
  anatomy/
  ├── anatomy-icon-gallery/    # this repo
  ├── review-eob-mf/
  ├── empire/
  ├── hil-ui/
  ├── document-center-mf/
  └── anatomy-financials-ui/
  ```
- Each frontend repo should have its `node_modules` installed (`npm install`) so the script can read icons from `node_modules/@anatomy-financial/anatomy-ui-core/dist/icons/`

### Usage

From the `anatomy-icon-gallery/` directory:

```bash
# Generate the gallery (index.html) without pushing
python3 update-gallery.py

# Generate and open in your browser
python3 update-gallery.py --open

# Generate, commit, and push to GitHub (updates the live site)
python3 update-gallery.py --push

# Generate, push, and open
python3 update-gallery.py --push --open
```

### What the Script Does

1. Walks each repo's `node_modules/@anatomy-financial/anatomy-ui-core/dist/icons/` to extract SVGs from compiled React component files
2. Reads custom `.tsx` SVG components from `anatomy-financials-ui/src/components/svgs/`
3. Scans each repo's `src/` directory to determine which apps import which icons
4. Scans for PrimeIcons CSS class usage (`pi-*` patterns) across all apps
5. Generates `index.html` with all icons, search, filters, and per-app usage data
6. Optionally commits and pushes to trigger a GitHub Pages rebuild

### Adding a New Repo or Custom SVG Directory

Edit the constants at the top of `update-gallery.py`:

```python
# Add a new repo to scan
REPOS = ["review-eob-mf", "empire", "hil-ui", "document-center-mf", "anatomy-financials-ui"]

# Add custom SVG directories for any app
CUSTOM_SVG_DIRS = {
    "anatomy-financials-ui": [
        ANATOMY_ROOT / "anatomy-financials-ui" / "src" / "components" / "svgs",
    ],
    # "new-app": [
    #     ANATOMY_ROOT / "new-app" / "src" / "icons",
    # ],
}
```
