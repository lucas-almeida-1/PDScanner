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
- Required Tools Check: Detects Node.js (with the minimum version from `engines.node` / `.nvmrc`), npm/yarn/pnpm/bun, uv and Poetry before scanning dependencies, and offers to install the missing or outdated ones.
- Automatic Tool Installation: Linux/macOS/WSL use nvm (Node), the official uv/bun installers and pipx/pip (Poetry); Windows uses winget. Installs run in real time after a 5-second countdown and are verified afterwards.
- System Tools (WSL/Linux): git, curl, make and docker can be required with `--with` and installed through the system package manager when you pass `--sudo`; curl is installed automatically when neither curl nor wget exists and a download is needed.
- Monorepo Support: Scans the current directory plus `apps/*` and `services/*` (or every subfolder with `--recursive`). npm workspaces are installed once from the root.
- Python Virtual Environments: Projects with `[project]` in `pyproject.toml` are checked against their own `.venv` and installed with uv (when the project uses it) or `venv` + pip, including the `dev` extra.
- Global Availability: Install once via pipx or pip and run pdscanner anywhere across your system.

---

## Prerequisites

Only Python is needed to run PDScanner itself; Node.js, uv and Poetry are detected and installed by it when a project requires them (needs `curl` or `wget` on Linux/macOS, `winget` on Windows).

- Python 3.8 or higher installed on your system.
- Node.js / npm / yarn / pnpm / bun installed (required if scanning JavaScript/TypeScript projects).
- Poetry installed (if scanning Poetry-managed Python projects).
- Git installed (required for remote installation from GitHub).

---

## Installation

### Option 0: One-line bootstrap (Linux / macOS / WSL)

Installs git, python3 and pipx when missing (asks for sudo if needed) and then PDScanner itself:

```bash
curl -fsSL https://raw.githubusercontent.com/lucas-almeida-1/PDScanner/main/install.sh | bash
```

After that, just run `pdscanner` inside any project: it finds the projects, checks/installs the tools and dependencies and reports required files.

### Option 1: Install with pipx

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

### Options

| Option | Description |
|---|---|
| `-c`, `--check` | Only report missing tools and dependencies; installs nothing |
| `-r`, `--recursive` | Look for projects in all subfolders |
| `--sudo` | Allow installing system tools (git, curl, make, docker) through apt/dnf/pacman/zypper/apk with `sudo`. Without it, PDScanner only prints the exact command |
| `--with LIST` | Also require extra tools, comma-separated: `git`, `curl`, `make`, `docker` (e.g. `pdscanner --with docker,make --sudo`) |
| `--no-tools` | Skip the required tools check/installation |
| `-h`, `--help` | Show help |

On Windows, a freshly installed tool may not be visible until you open a new terminal; PDScanner tells you when that happens and you just run it again.

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

--- Checking Required Tools ---

Found the following required tools:
  [OUTDATED]  node 18.19.0 - Version 22+ required by package.json
  [INSTALLED] npm 10.2.3 - Already installed on machine
  [MISSING]   uv - Not found on machine (required by apps/backend (uv project))

Starting installation of node via nvm (Node Version Manager) -> Node 22
...

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

## Project configuration (`pdscanner.json`)

Optional file in the project root to declare what PDScanner cannot infer:

```json
{
  "tools": ["make"],
  "files": [
    { "path": "apps/backend/notebooks/*.ipynb", "message": "Copy the notebook here (not versioned)." }
  ]
}
```

- `tools`: extra system tools to require (`git`, `curl`, `make`, `docker`).
- `files`: files/globs that must exist; missing ones are reported with your message.

When a tool needs administrator rights and `--sudo` was not given, PDScanner asks `[y/N]` in interactive terminals before running `sudo`.

## License

Distributed under the MIT License.
