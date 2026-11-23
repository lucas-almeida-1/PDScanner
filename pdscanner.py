#!/usr/bin/env python3
"""PDScanner - Project Dependency Scanner.

Checks the tools a project needs (Node.js, uv, Poetry, ...), then the project
dependencies, and installs whatever is missing with a detailed real-time log.
"""
import fnmatch
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time

IGNORED_DIRS = {
    'node_modules', 'dist', 'build', '.git', '.vite', '.validators',
    '__pycache__', '.venv', 'venv', '.mypy_cache', '.pytest_cache', '.ruff_cache',
}
CODE_EXTS = ('.ts', '.tsx', '.js', '.jsx', '.py')
MANIFESTS = ('package.json', 'poetry.lock', 'pyproject.toml', 'requirements.txt')
# Conventional monorepo containers scanned automatically (besides the current dir).
MONOREPO_DIRS = ('apps', 'services')

IS_WINDOWS = os.name == 'nt'
ALLOW_SUDO = False
SYSTEM_PACKAGES = {  # tool -> {package manager: package}
    'git': {'default': 'git'},
    'curl': {'default': 'curl'},
    'make': {'default': 'make'},
    'docker': {'apt-get': 'docker.io', 'brew': '--cask docker', 'default': 'docker'},
}
SYSTEM_TOOLS = tuple(SYSTEM_PACKAGES)
NVM_URL = 'https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh'
UV_URL = 'https://astral.sh/uv/install.sh'
BUN_URL = 'https://bun.sh/install'


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #

def print_banner():
    print("=" * 60)
    print(" PDScanner - Project Dependency Scanner")
    print("=" * 60)


def read_text(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ''


def read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def label(path):
    rel = os.path.relpath(path, os.getcwd())
    return '.' if rel == '.' else rel.replace(os.sep, '/')


def countdown(seconds=5):
    print("(To interrupt execution, press Ctrl + C)\n")
    try:
        for i in range(seconds, 0, -1):
            print(f"({i})")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)


def run(cmd, cwd=None, shell=False):
    """Runs a command streaming its output. Returns the exit code (-1 on launch error)."""
    try:
        return subprocess.run(cmd, cwd=cwd, shell=shell, check=False).returncode
    except Exception as err:
        shown = cmd if isinstance(cmd, str) else ' '.join(cmd)
        print(f"Error executing '{shown}': {err}")
        return -1


def capture(cmd, cwd=None):
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
        return res.returncode, (res.stdout or '') + (res.stderr or '')
    except Exception:
        return -1, ''


def add_to_path(*dirs):
    """Makes freshly installed tools visible to this process (and its children)."""
    current = os.environ.get('PATH', '').split(os.pathsep)
    for d in dirs:
        if d and os.path.isdir(d) and d not in current:
            os.environ['PATH'] = d + os.pathsep + os.environ.get('PATH', '')
            current.insert(0, d)


def refresh_known_paths():
    home = os.path.expanduser('~')
    extra = [
        os.path.join(home, '.local', 'bin'),
        os.path.join(home, '.cargo', 'bin'),
        os.path.join(home, '.bun', 'bin'),
    ]
    nvm_root = os.path.join(os.environ.get('NVM_DIR', os.path.join(home, '.nvm')), 'versions', 'node')
    if os.path.isdir(nvm_root):
        versions = sorted(os.listdir(nvm_root), key=version_key, reverse=True)
        extra += [os.path.join(nvm_root, v, 'bin') for v in versions]
    if IS_WINDOWS:
        for var in ('ProgramFiles', 'LOCALAPPDATA', 'APPDATA'):
            base = os.environ.get(var)
            if base:
                extra += [os.path.join(base, 'nodejs'), os.path.join(base, 'Programs', 'uv'),
                          os.path.join(base, 'Python', 'Scripts')]
        extra.append(os.path.join(home, '.local', 'bin'))
    add_to_path(*extra)


def version_key(text):
    return tuple(int(n) for n in re.findall(r'\d+', text)[:3]) or (0,)


# --------------------------------------------------------------------------- #
# Project discovery
# --------------------------------------------------------------------------- #

def has_manifest(d):
    return any(os.path.exists(os.path.join(d, m)) for m in MANIFESTS)


def discover_projects(recursive=False):
    """Current directory first, then conventional monorepo children (or everything when recursive)."""
    root = os.getcwd()
    found = []
    if has_manifest(root):
        found.append(root)

    if recursive:
        for current, dirs, _ in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS and not d.startswith('.'))
            if current != root and has_manifest(current):
                found.append(current)
        return found

    for container in MONOREPO_DIRS:
        base = os.path.join(root, container)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            child = os.path.join(base, name)
            if os.path.isdir(child) and name not in IGNORED_DIRS and has_manifest(child):
                found.append(child)
    return found


def npm_workspaces(root):
    ws = read_json(os.path.join(root, 'package.json')).get('workspaces', [])
    if isinstance(ws, dict):
        ws = ws.get('packages', [])
    return [w.rstrip('/') for w in ws] if isinstance(ws, list) else []


def covered_by_workspace(project, root):
    rel = os.path.relpath(project, root).replace(os.sep, '/')
    return rel != '.' and any(fnmatch.fnmatch(rel, pattern) for pattern in npm_workspaces(root))


def node_install_cmd(d):
    if os.path.exists(os.path.join(d, 'pnpm-lock.yaml')):
        return ["pnpm", "install"]
    if os.path.exists(os.path.join(d, 'yarn.lock')):
        return ["yarn", "install"]
    if os.path.exists(os.path.join(d, 'bun.lockb')) or os.path.exists(os.path.join(d, 'bun.lock')):
        return ["bun", "install"]
    return ["npm", "install"]


def is_poetry(d):
    return os.path.exists(os.path.join(d, 'poetry.lock')) or '[tool.poetry]' in read_text(os.path.join(d, 'pyproject.toml'))


def uses_uv(d):
    """A project is uv-based when it says so, or when its launcher script calls uv."""
    root = os.getcwd()
    if os.path.exists(os.path.join(d, 'uv.lock')) or '[tool.uv]' in read_text(os.path.join(d, 'pyproject.toml')):
        return True
    for base in {d, root}:
        for script in ('run-local.sh', 'Makefile'):
            if re.search(r'\buv (venv|pip|sync|run)\b', read_text(os.path.join(base, script))):
                return True
    return False


def python_kind(d):
    if is_poetry(d):
        return 'poetry'
    if os.path.exists(os.path.join(d, 'requirements.txt')):
        return 'requirements'
    if '[project]' in read_text(os.path.join(d, 'pyproject.toml')):
        return 'pyproject'
    return None


# --------------------------------------------------------------------------- #
# Prerequisite tools (Node.js, uv, Poetry, ...)
# --------------------------------------------------------------------------- #

def tool_version(name):
    """Returns (found, version_text)."""
    exe = shutil.which(name)
    if not exe:
        return False, ''
    code, out = capture([exe, '--version'])
    if code != 0:
        return False, ''
    m = re.search(r'\d+(?:\.\d+)*', out)
    return True, m.group(0) if m else out.strip()


def required_node_major(projects):
    best = 0
    for d in projects:
        spec = read_json(os.path.join(d, 'package.json')).get('engines', {}).get('node', '')
        m = re.search(r'\d+', spec or '')
        if not m:
            m = re.search(r'\d+', read_text(os.path.join(d, '.nvmrc')))
        if m:
            best = max(best, int(m.group(0)))
    return best


def project_config():
    cfg = read_json(os.path.join(os.getcwd(), 'pdscanner.json'))
    return cfg if isinstance(cfg, dict) else {}


def plan_tools(projects, extras=()):
    """Ordered list of (tool, reason, min_major) required by the detected projects."""
    tools = {}

    def need(tool, reason, major=0):
        if tool not in tools:
            tools[tool] = [reason, major]
        else:
            tools[tool][1] = max(tools[tool][1], major)

    node_projects = [d for d in projects if os.path.exists(os.path.join(d, 'package.json'))]
    if node_projects:
        major = required_node_major(node_projects)
        need('node', 'package.json', major)
        for d in node_projects:
            manager = node_install_cmd(d)[0]
            need(manager, f'{label(d)}/package.json')
    for d in projects:
        kind = python_kind(d)
        if kind == 'poetry':
            need('poetry', f'{label(d)} (Poetry project)')
        elif kind == 'pyproject' and uses_uv(d):
            need('uv', f'{label(d)} (uv project)')
    for tool in list(project_config().get('tools', [])):
        if tool in SYSTEM_TOOLS:
            need(tool, 'pdscanner.json')
    for tool in extras:
        need(tool, 'requested with --with')
    return [(t, r, m) for t, (r, m) in tools.items()]


def check_tool(tool, reason, major):
    found, version = tool_version(tool)
    if found and major and version_key(version)[0] < major:
        print(f"  [OUTDATED]  {tool} {version} - Version {major}+ required by {reason}")
        return 'outdated', version
    if found:
        print(f"  [INSTALLED] {tool} {version} - Already installed on machine")
        return 'ok', version
    print(f"  [MISSING]   {tool} - Not found on machine (required by {reason})")
    return 'missing', ''


def ensure_downloader(url):
    """Neither curl nor wget: try to install curl (needs --sudo on most systems). Returns a download prefix."""
    option = system_install('curl')
    if option is None:
        return None
    description, runner = option
    print(f"Neither curl nor wget found. Installing curl via {description}")
    if runner is None:
        return None
    countdown()
    runner()
    return sh_download(url)


def sh_download(url):
    if shutil.which('curl'):
        return f'curl -fsSL {url}'
    if shutil.which('wget'):
        return f'wget -qO- {url}'
    return None


def system_install(tool):
    """Installs a tool through the OS package manager (sudo only when --sudo was given)."""
    if IS_WINDOWS:
        ids = {'git': 'Git.Git', 'curl': 'cURL.cURL', 'make': 'GnuWin32.Make', 'docker': 'Docker.DockerDesktop'}
        if not shutil.which('winget'):
            return None
        return f'winget install {ids[tool]}', lambda: run(['winget', 'install', '-e', '--id', ids[tool],
                                                           '--accept-package-agreements', '--accept-source-agreements'])
    manager = next((m for m in ('apt-get', 'dnf', 'yum', 'pacman', 'zypper', 'apk', 'brew') if shutil.which(m)), None)
    if not manager:
        return None
    pkgs = SYSTEM_PACKAGES[tool]
    pkg = pkgs.get(manager, pkgs['default'])
    verbs = {'apt-get': 'install -y', 'dnf': 'install -y', 'yum': 'install -y', 'pacman': '-S --noconfirm',
             'zypper': '--non-interactive install', 'apk': 'add', 'brew': 'install'}
    steps = []
    if manager == 'apt-get':
        steps.append('apt-get update')
    steps.append(f'{manager} {verbs[manager]} {pkg}')
    needs_root = manager != 'brew' and hasattr(os, 'geteuid') and os.geteuid() != 0
    if needs_root:
        if not shutil.which('sudo'):
            return None
        steps = ['sudo ' + st for st in steps]
    command = ' && '.join(steps)
    if needs_root and not ALLOW_SUDO:
        if not sys.stdin.isatty():
            return f'{command}  (needs sudo: run it yourself or use --sudo)', None

        def ask_and_run():
            print(f"\n'{tool}' needs administrator rights: {command}")
            try:
                answer = input("Allow PDScanner to run this with sudo? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = ''
            if answer not in ('y', 'yes', 's', 'sim'):
                print("Skipped by user.")
                return -1
            return run(command, shell=True)
        return command, ask_and_run
    return command, lambda: run(command, shell=True)


def installer_for(tool, major):
    """Returns (description, runner) or None when no automatic installation is possible."""
    py = sys.executable

    def posix_script(description, script):
        return description, lambda: run(['bash', '-c', script])

    def winget(pkg_id, description):
        if not shutil.which('winget'):
            return None
        return description, lambda: run(['winget', 'install', '-e', '--id', pkg_id,
                                         '--accept-package-agreements', '--accept-source-agreements'])

    def python_cli(package):
        if shutil.which('pipx'):
            return f'pipx install {package}', lambda: run(['pipx', 'install', package])
        return f'{py} -m pip install --user {package}', lambda: run([py, '-m', 'pip', 'install', '--user', package])

    if tool in SYSTEM_PACKAGES:
        return system_install(tool)

    if tool == 'poetry':
        return python_cli('poetry')

    if tool == 'uv':
        if IS_WINDOWS:
            return winget('astral-sh.uv', 'winget install astral-sh.uv')
        dl = sh_download(UV_URL) or ensure_downloader(UV_URL)
        return posix_script('official uv installer (astral.sh)', f'{dl} | sh') if dl else None

    if tool in ('node', 'npm'):
        if IS_WINDOWS:
            return winget('OpenJS.NodeJS.LTS', 'winget install OpenJS.NodeJS.LTS')
        dl = sh_download(NVM_URL) or ensure_downloader(NVM_URL)
        if not dl:
            return None
        target = str(major) if major else '--lts'
        script = (f'{dl} | bash && export NVM_DIR="${{NVM_DIR:-$HOME/.nvm}}" && '
                  f'. "$NVM_DIR/nvm.sh" && nvm install {target} && nvm alias default {target}')
        return posix_script(f'nvm (Node Version Manager) -> Node {target}', script)

    if tool in ('pnpm', 'yarn'):
        if not shutil.which('npm'):
            return None
        return f'npm install -g {tool}', lambda: run(['npm', 'install', '-g', tool])

    if tool == 'bun':
        if IS_WINDOWS:
            return winget('Oven-sh.Bun', 'winget install Oven-sh.Bun')
        dl = sh_download(BUN_URL) or ensure_downloader(BUN_URL)
        return posix_script('official bun installer', f'{dl} | bash') if dl else None

    return None


def ensure_prerequisites(projects, install=True, extras=()):
    """Checks required tools and installs the missing ones. Returns the set of unavailable tools."""
    plan = plan_tools(projects, extras)
    if not plan:
        return set()

    print("\n--- Checking Required Tools ---\n")
    print("Found the following required tools:")
    pending = []
    for tool, reason, major in plan:
        state, _ = check_tool(tool, reason, major)
        if state != 'ok':
            pending.append((tool, reason, major))

    print("\nTools scan summary:")
    print(f"  Total required tools: {len(plan)}")
    print(f"  Installed: {len(plan) - len(pending)}")
    print(f"  Missing or outdated: {len(pending)}\n")

    if not pending:
        print("All required tools are already installed on your machine!")
        return set()
    if not install:
        return {t for t, _, _ in pending}

    unavailable = set()
    for tool, reason, major in pending:
        # Installing one tool can provide another (npm ships with node).
        found, version = tool_version(tool)
        if found and not (major and version_key(version)[0] < major):
            print(f"{tool} {version} is now available (installed together with another tool).")
            continue
        option = installer_for(tool, major)
        if option is None:
            print(f"No automatic installation available for '{tool}' on this system. "
                  f"Install it manually and run pdscanner again.")
            unavailable.add(tool)
            continue

        description, runner = option
        if runner is None:
            print(f"Cannot install '{tool}' automatically: {description}")
            unavailable.add(tool)
            continue
        print(f"Starting installation of {tool} via {description}")
        countdown()
        print(f"\nInstalling {tool} in real-time...")
        code = runner()
        refresh_known_paths()

        found, version = tool_version(tool)
        if found and not (major and version_key(version)[0] < major):
            print(f"\n{tool} {version} installed successfully!")
            if tool == 'docker' and 'microsoft' in platform.release().lower():
                print("Note (WSL): enable Docker Desktop's WSL integration or start the docker daemon manually.")
        elif code == 0 and IS_WINDOWS:
            print(f"\n{tool} was installed, but this terminal cannot see it yet. "
                  f"Open a new terminal and run pdscanner again.")
            unavailable.add(tool)
        else:
            print(f"\nFailed to install {tool}. Exit code: {code}")
            unavailable.add(tool)

    if unavailable:
        print(f"\nStill unavailable: {', '.join(sorted(unavailable))}. "
              f"Dependencies that need them will be skipped.")
    return unavailable


# --------------------------------------------------------------------------- #
# Node.js dependencies
# --------------------------------------------------------------------------- #

def get_installed_npm_packages(d):
    """Returns a set of npm packages currently present in node_modules."""
    installed = set()
    node_modules = os.path.join(d, 'node_modules')
    if os.path.exists(node_modules):
        for item in os.listdir(node_modules):
            if item.startswith('@'):
                subfolder = os.path.join(node_modules, item)
                if os.path.isdir(subfolder):
                    for sub in os.listdir(subfolder):
                        installed.add(f"{item}/{sub}")
            elif not item.startswith('.'):
                installed.add(item)
    return installed


def scan_npm_dependencies(d, unavailable, install=True):
    package_json_path = os.path.join(d, 'package.json')
    if not os.path.exists(package_json_path):
        return False

    cmd = node_install_cmd(d)
    pkg_manager = cmd[0]
    print(f"\n--- Scanning Node.js / {pkg_manager.upper()} Dependencies ({label(d)}/package.json) ---\n")
    pj = read_json(package_json_path)
    if not isinstance(pj, dict) or (not pj and read_text(package_json_path).strip() not in ('{}', '')):
        print("Error reading package.json: invalid JSON")
        return False
    npm_deps = set(pj.get('dependencies', {}).keys()) | set(pj.get('devDependencies', {}).keys())

    installed_npm = get_installed_npm_packages(d)
    missing_deps = []

    print("Found the following required Node.js dependencies:")
    for dep in sorted(npm_deps):
        if dep in installed_npm:
            print(f"  [INSTALLED] {dep} - Already installed on machine")
        else:
            print(f"  [MISSING]   {dep} - Not found on machine")
            missing_deps.append(dep)

    print("\nNode.js scan summary:")
    print(f"  Total required dependencies: {len(npm_deps)}")
    print(f"  Installed: {len(npm_deps) - len(missing_deps)}")
    print(f"  Missing: {len(missing_deps)}\n")

    if not missing_deps:
        print("All required Node.js dependencies are already installed on your machine!")
        return True
    if not install:
        return True
    if pkg_manager in unavailable or 'node' in unavailable or not shutil.which(pkg_manager):
        print(f"Skipping installation: {pkg_manager} is not available.")
        return True

    print(f"Starting installation of missing Node.js dependencies via {pkg_manager}")
    countdown()
    print(f"\nInstalling dependencies in real-time via {pkg_manager}...")
    code = run(cmd, cwd=d)
    if code == 0:
        print("\nNode.js prerequisites installed successfully!")
    else:
        print(f"\nFailed to install Node.js dependencies. Exit code: {code}")
    return True


# --------------------------------------------------------------------------- #
# Python dependencies
# --------------------------------------------------------------------------- #

def norm(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def get_installed_python_packages(python=None):
    """Names of the packages installed in the given interpreter (default: current one)."""
    installed = set()
    if python:
        code, out = capture([python, '-c',
                             "import importlib.metadata as m;"
                             "print('\\n'.join(d.metadata['Name'] for d in m.distributions()))"])
        if code == 0:
            installed.update(norm(line) for line in out.splitlines() if line.strip())
        return installed
    try:
        import importlib.metadata
        for dist in importlib.metadata.distributions():
            installed.add(norm(dist.metadata['Name']))
    except Exception:
        code, out = capture([sys.executable, "-m", "pip", "list", "--format=json"])
        if code == 0:
            try:
                installed.update(norm(i.get('name', '')) for i in json.loads(out))
            except Exception:
                pass
    return installed


def parse_poetry_dependencies(d):
    deps = set()
    poetry_lock_path = os.path.join(d, 'poetry.lock')
    pyproject_path = os.path.join(d, 'pyproject.toml')

    if os.path.exists(poetry_lock_path):
        for line in read_text(poetry_lock_path).splitlines():
            line = line.strip()
            if line.startswith('name = '):
                pkg_name = line.split('=')[1].strip().strip('"').strip("'")
                if pkg_name:
                    deps.add(pkg_name)
        if deps:
            return sorted(deps)

    in_deps = False
    for line in read_text(pyproject_path).splitlines():
        line = line.strip()
        if '[tool.poetry.dependencies]' in line or '[project.dependencies]' in line:
            in_deps = True
            continue
        if line.startswith('['):
            in_deps = False
        if in_deps and '=' in line and not line.startswith('#'):
            pkg_name = line.split('=')[0].strip()
            if pkg_name and pkg_name.lower() != 'python':
                deps.add(pkg_name)
    return sorted(deps)


def requirement_name(spec):
    m = re.match(r'\s*([A-Za-z0-9][A-Za-z0-9._-]*)', spec)
    return m.group(1) if m else ''


def parse_pyproject_dependencies(d):
    """Returns (dependencies, optional_groups) from [project] in pyproject.toml."""
    path = os.path.join(d, 'pyproject.toml')
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore
        with open(path, 'rb') as f:
            project = tomllib.load(f).get('project', {})
        deps = [requirement_name(s) for s in project.get('dependencies', [])]
        groups = {k: [requirement_name(s) for s in v]
                  for k, v in project.get('optional-dependencies', {}).items()}
        return [x for x in deps if x], groups
    except Exception:
        pass

    # Fallback for interpreters without a TOML parser: read the plain `dependencies = [...]` block.
    text = read_text(path)
    m = re.search(r'^dependencies\s*=\s*\[(.*?)\]', text, re.S | re.M)
    deps = [requirement_name(s) for s in re.findall(r'["\']([^"\']+)["\']', m.group(1))] if m else []
    groups = {}
    sec = re.search(r'\[project\.optional-dependencies\](.*?)(?=^\[|\Z)', text, re.S | re.M)
    if sec:
        for g in re.finditer(r'^([A-Za-z0-9_-]+)\s*=\s*\[(.*?)\]', sec.group(1), re.S | re.M):
            groups[g.group(1)] = [requirement_name(s) for s in re.findall(r'["\']([^"\']+)["\']', g.group(2))]
    return [x for x in deps if x], groups


def report_python(title, deps, installed):
    missing = []
    print(f"Found the following required {title} dependencies:")
    for dep in deps:
        if norm(dep) in installed:
            print(f"  [INSTALLED] {dep} - Already installed on machine")
        else:
            print(f"  [MISSING]   {dep} - Not found on machine")
            missing.append(dep)
    print(f"\n{title} scan summary:")
    print(f"  Total required dependencies: {len(deps)}")
    print(f"  Installed: {len(deps) - len(missing)}")
    print(f"  Missing: {len(missing)}\n")
    return missing


def finish_install(code, what):
    if code == 0:
        print(f"\n{what} prerequisites installed successfully!")
    else:
        print(f"\nFailed to install {what} dependencies. Exit code: {code}")


def venv_python(d):
    for rel in (('.venv', 'bin', 'python'), ('.venv', 'Scripts', 'python.exe')):
        path = os.path.join(d, *rel)
        if os.path.exists(path):
            return path
    return None


def scan_python_dependencies(d, unavailable, install=True):
    kind = python_kind(d)
    if kind is None:
        return False
    where = label(d)

    if kind == 'poetry':
        print(f"\n--- Scanning Python Dependencies (Poetry, {where}) ---\n")
        deps = parse_poetry_dependencies(d)
        if deps:
            missing = report_python('Poetry', deps, get_installed_python_packages())
            if not missing:
                print("All required Poetry dependencies are already installed on your machine!")
                return True
        else:
            print("Poetry project detected. Starting dependency check via Poetry...")
        if not install:
            return True
        if 'poetry' in unavailable or not shutil.which('poetry'):
            print("Skipping installation: poetry is not available.")
            return True
        print("Starting installation of missing Poetry dependencies via Poetry")
        countdown()
        print("\nInstalling Poetry dependencies in real-time...")
        finish_install(run(["poetry", "install"], cwd=d), 'Poetry')
        return True

    if kind == 'requirements':
        print(f"\n--- Scanning Python Dependencies ({where}/requirements.txt) ---\n")
        deps = []
        for line in read_text(os.path.join(d, 'requirements.txt')).splitlines():
            line = line.strip()
            if line and not line.startswith(('#', '-')):
                name = requirement_name(line)
                if name:
                    deps.append(name)
        missing = report_python('Python', deps, get_installed_python_packages())
        if not missing:
            print("All required Python dependencies are already installed on your machine!")
            return True
        if not install:
            return True
        print("Starting installation of missing Python dependencies on machine")
        countdown()
        print("\nInstalling Python dependencies in real-time...")
        finish_install(run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=d), 'Python')
        return True

    # pyproject.toml with [project]: dependencies live in the project's own .venv
    use_uv = uses_uv(d)
    print(f"\n--- Scanning Python Dependencies ({where}/pyproject.toml, .venv) ---\n")
    deps, groups = parse_pyproject_dependencies(d)
    extras = ['dev'] if 'dev' in groups else []
    all_deps = list(dict.fromkeys(list(deps) + [x for e in extras for x in groups[e]]))
    vpy = venv_python(d)
    if vpy:
        print(f"Using virtual environment: {label(os.path.dirname(os.path.dirname(vpy)))}")
        installed = get_installed_python_packages(vpy)
    else:
        print("Virtual environment (.venv) not found: every dependency is considered missing.")
        installed = set()

    if not all_deps:
        print("No dependencies declared in [project].")
        return True
    missing = report_python('Python', all_deps, installed)
    if not missing:
        print("All required Python dependencies are already installed in the project's .venv!")
        return True
    if not install:
        return True
    if use_uv and ('uv' in unavailable or not shutil.which('uv')):
        print("Skipping installation: uv is not available.")
        return True

    spec = f".[{','.join(extras)}]" if extras else "."
    manager = 'uv' if use_uv else 'venv + pip'
    print(f"Starting installation of missing Python dependencies via {manager}")
    countdown()
    print(f"\nInstalling Python dependencies in real-time via {manager}...")
    code = 0
    if not vpy:
        print("Creating virtual environment (.venv)...")
        pin = re.search(r'requires-python\s*=\s*["\']\s*>=\s*(\d+\.\d+)', read_text(os.path.join(d, 'pyproject.toml')))
        uv_cmd = ['uv', 'venv'] + (['--python', pin.group(1)] if pin else [])
        code = run(uv_cmd if use_uv else [sys.executable, '-m', 'venv', '.venv'], cwd=d)
    if code == 0:
        if use_uv:
            code = run(['uv', 'pip', 'install', '-e', spec], cwd=d)
        else:
            code = run([venv_python(d) or sys.executable, '-m', 'pip', 'install', '-e', spec], cwd=d)
    finish_install(code, 'Python')
    return True


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def check_required_files():
    """Files the project declares in pdscanner.json that PDScanner cannot create (e.g. a private notebook)."""
    entries = project_config().get('files', [])
    if not entries:
        return
    import glob
    print("\n--- Checking Required Project Files (pdscanner.json) ---\n")
    missing = 0
    for entry in entries:
        pattern = entry.get('path', '')
        if glob.glob(os.path.join(os.getcwd(), pattern)):
            print(f"  [FOUND]     {pattern}")
        else:
            missing += 1
            print(f"  [MISSING]   {pattern} - {entry.get('message', 'Required file not found')}")
    print("\nRequired files summary:")
    print(f"  Total: {len(entries)}")
    print(f"  Found: {len(entries) - missing}")
    print(f"  Missing: {missing}\n")
    if missing:
        print("Add the missing file(s) above before starting the app.")
    else:
        print("All required project files are in place!")


def list_code_files(projects):
    print("\nStarting scan of required dependencies for the project...\n")
    root = os.getcwd()
    for current, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in IGNORED_DIRS]
        for file in sorted(files):
            if file.endswith(CODE_EXTS):
                print(f"Reading {os.path.relpath(os.path.join(current, file), root)}...")


def scan_project_dependencies(recursive=False, install=True, check_tools=True, extras=()):
    projects = discover_projects(recursive)
    list_code_files(projects)

    if not projects:
        print("\nNo supported dependency manifest found "
              "(package.json, poetry.lock, pyproject.toml or requirements.txt).")
        return

    if len(projects) > 1:
        print("\nProjects detected:")
        for d in projects:
            print(f"  - {label(d)}")

    unavailable = ensure_prerequisites(projects, install, extras) if check_tools else set()

    root = os.getcwd()
    for d in projects:
        if not covered_by_workspace(d, root):
            scan_npm_dependencies(d, unavailable, install)
        scan_python_dependencies(d, unavailable, install)
    check_required_files()


def print_help():
    print("Usage: pdscanner [options]\n")
    print("  -c, --check         only report missing tools and dependencies (no installation)")
    print("  -r, --recursive     look for projects in all subfolders (default: current dir, apps/*, services/*)")
    print("      --sudo          install system tools (git, curl, make, docker) with sudo without asking")
    print("                      (without it, you are asked interactively; non-interactive runs only print the command)")
    print("      --with LIST     also require extra tools, comma-separated: git, curl, make, docker")
    print("      --no-tools      skip the check/installation of Node.js, uv, Poetry, ...")
    print("  -h, --help          show this help")


def main():
    global ALLOW_SUDO
    argv = sys.argv[1:]
    extras, flags, i = [], set(), 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--with' or arg.startswith('--with='):
            value = arg.split('=', 1)[1] if '=' in arg else (argv[i + 1] if i + 1 < len(argv) else '')
            i += 0 if '=' in arg else 1
            extras += [t.strip() for t in value.split(',') if t.strip()]
        else:
            flags.add(arg)
        i += 1

    if flags & {'-h', '--help'}:
        print_help()
        return
    unknown = flags - {'-c', '--check', '-r', '--recursive', '--no-tools', '--sudo'}
    bad_tools = [t for t in extras if t not in SYSTEM_TOOLS]
    if unknown or bad_tools:
        if unknown:
            print(f"Unknown option(s): {', '.join(sorted(unknown))}")
        if bad_tools:
            print(f"Unsupported tool(s) for --with: {', '.join(bad_tools)} (supported: {', '.join(SYSTEM_TOOLS)})")
        print()
        print_help()
        sys.exit(2)

    ALLOW_SUDO = '--sudo' in flags
    print_banner()
    print(f"System: {platform.system()} {platform.machine()} | Python {platform.python_version()}")
    refresh_known_paths()
    scan_project_dependencies(
        recursive=bool(flags & {'-r', '--recursive'}),
        install=not (flags & {'-c', '--check'}),
        check_tools='--no-tools' not in flags,
        extras=tuple(dict.fromkeys(extras)),
    )


if __name__ == '__main__':
    main()
