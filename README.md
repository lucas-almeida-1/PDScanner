# PDScanner (Project Dependency Scanner)

Automated project dependency scanner and installer CLI for developer workspaces.

PDScanner is a lightweight CLI tool designed to scan project root directories, check installed packages against requirements, identify missing dependencies, and automatically install them using the appropriate package manager.

---

## Features

- Multi-Ecosystem Support: Automatically detects and scans Node.js (package.json) and Python (requirements.txt, poetry.lock, pyproject.toml) projects.
- Smart Package Manager Auto-Detection:
  - Node.js: Automatically selects npm, yarn, pnpm, or bun based on lockfiles.
  - Python: Automatically selects pip or poetry based on project configuration.
- Automated Folder Traversal: Recursively scans source files (.ts, .tsx, .js, .jsx, .py) while ignoring build artifacts (node_modules, dist, .git, .vite, .venv, __pycache__).
- Missing Dependency Check: Detects installed vs missing dependencies in your local environment.
- Interactive Auto-Installer: Gives a 5-second countdown before launching real-time installation.
- Global Availability: Install once via pipx or pip and run pdscanner anywhere across your system.

---

## Prerequisites

- Python 3.8 or higher installed on your system.
- Node.js / npm / yarn / pnpm / bun installed (required if scanning JavaScript/TypeScript projects).
- Poetry installed (if scanning Poetry-managed Python projects).
- Git installed (required for remote installation from GitHub).

---

## Installation

### Option 1: Install with pipx (Recommended)

```bash
pipx install git+https://github.com/lucas-almeida-1/PDScanner.git
```

### Option 2: Install with pip

```bash
pip install git+https://github.com/lucas-almeida-1/PDScanner.git
```

---

## Usage

Navigate to the root directory of any project and run:

```bash
pdscanner
# or short alias
pdscan
```

### Example Output

```text
============================================================
 PDScanner - Project Dependency Scanner
============================================================

Starting scan of required dependencies for the project...

Reading src/index.ts...
Reading src/App.tsx...

--- Scanning Node.js / NPM Dependencies (package.json) ---

Found the following required Node.js dependencies:
  [INSTALLED] react - Already installed on machine
  [MISSING]   lucide-react - Not found on machine

Node.js scan summary:
  Total required dependencies: 2
  Installed: 1
  Missing: 1

Starting installation of missing Node.js dependencies via npm
(To interrupt execution, press Ctrl + C)

(5)
(4)
(3)
...
Installing dependencies in real-time via npm...

Node.js prerequisites installed successfully!
```

---

## License

Distributed under the MIT License.
