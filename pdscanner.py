#!/usr/bin/env python3
import os
import sys
import time
import subprocess
import json

def print_banner():
    print("=" * 60)
    print(" PDScanner - Project Dependency Scanner")
    print("=" * 60)

def get_installed_npm_packages():
    """Returns a set of npm packages currently present in node_modules."""
    installed = set()
    node_modules = os.path.join(os.getcwd(), 'node_modules')
    if os.path.exists(node_modules):
        for item in os.listdir(node_modules):
            if item.startswith('@'):
                subfolder = os.path.join(node_modules, item)
                if os.path.isdir(subfolder):
                    for subitem in os.listdir(subfolder):
                        installed.add(f"{item}/{subitem}")
            else:
                installed.add(item)
    return installed

def get_node_install_cmd():
    if os.path.exists(os.path.join(os.getcwd(), 'pnpm-lock.yaml')):
        return ["pnpm", "install"]
    elif os.path.exists(os.path.join(os.getcwd(), 'yarn.lock')):
        return ["yarn", "install"]
    elif os.path.exists(os.path.join(os.getcwd(), 'bun.lockb')):
        return ["bun", "install"]
    return ["npm", "install"]

def scan_npm_dependencies():
    package_json_path = os.path.join(os.getcwd(), 'package.json')
    if not os.path.exists(package_json_path):
        return False

    cmd = get_node_install_cmd()
    pkg_manager = cmd[0]
    print(f"\n--- Scanning Node.js / {pkg_manager.upper()} Dependencies (package.json) ---\n")
    npm_deps = set()
    try:
        with open(package_json_path, 'r', encoding='utf-8') as f:
            pj = json.load(f)
            npm_deps.update(pj.get('dependencies', {}).keys())
            npm_deps.update(pj.get('devDependencies', {}).keys())
    except Exception as e:
        print(f"Error reading package.json: {e}")
        return False

    installed_npm = get_installed_npm_packages()
    installed_deps = []
    missing_deps = []

    print("Found the following required Node.js dependencies:")
    for dep in sorted(npm_deps):
        if dep in installed_npm:
            print(f"  [INSTALLED] {dep} - Already installed on machine")
            installed_deps.append(dep)
        else:
            print(f"  [MISSING]   {dep} - Not found on machine")
            missing_deps.append(dep)

    total = len(npm_deps)
    num_installed = len(installed_deps)
    num_missing = len(missing_deps)

    print("\nNode.js scan summary:")
    print(f"  Total required dependencies: {total}")
    print(f"  Installed: {num_installed}")
    print(f"  Missing: {num_missing}\n")

    if num_missing == 0:
        print("All required Node.js dependencies are already installed on your machine!")
        return True

    print(f"Starting installation of missing Node.js dependencies via {pkg_manager}")
    print("(To interrupt execution, press Ctrl + C)\n")

    try:
        for i in range(5, 0, -1):
            print(f"({i})")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)

    print(f"\nInstalling dependencies in real-time via {pkg_manager}...")
    try:
        res = subprocess.run(cmd, check=False)
        if res.returncode == 0:
            print("\nNode.js prerequisites installed successfully!")
        else:
            print(f"\nFailed to install Node.js dependencies. Exit code: {res.returncode}")
    except Exception as err:
        print(f"\nError executing package manager ({pkg_manager}): {err}")

    return True

def get_installed_python_packages():
    """Returns a set of installed Python package names."""
    installed = set()
    try:
        import importlib.metadata
        for dist in importlib.metadata.distributions():
            installed.add(dist.metadata['Name'].lower())
    except Exception:
        try:
            res = subprocess.run([sys.executable, "-m", "pip", "list", "--format=json"], capture_output=True, text=True)
            if res.returncode == 0:
                pkgs = json.loads(res.stdout)
                for item in pkgs:
                    installed.add(item.get('name', '').lower())
        except Exception:
            pass
    return installed

def parse_poetry_dependencies():
    deps = set()
    poetry_lock_path = os.path.join(os.getcwd(), 'poetry.lock')
    pyproject_path = os.path.join(os.getcwd(), 'pyproject.toml')

    if os.path.exists(poetry_lock_path):
        try:
            with open(poetry_lock_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('name = '):
                        pkg_name = line.split('=')[1].strip().strip('"').strip("'")
                        if pkg_name:
                            deps.add(pkg_name)
            if deps:
                return sorted(deps)
        except Exception:
            pass

    if os.path.exists(pyproject_path):
        try:
            with open(pyproject_path, 'r', encoding='utf-8') as f:
                in_deps = False
                for line in f:
                    line = line.strip()
                    if '[tool.poetry.dependencies]' in line or '[project.dependencies]' in line:
                        in_deps = True
                        continue
                    elif line.startswith('['):
                        in_deps = False

                    if in_deps and '=' in line and not line.startswith('#'):
                        pkg_name = line.split('=')[0].strip()
                        if pkg_name and pkg_name.lower() != 'python':
                            deps.add(pkg_name)
        except Exception:
            pass

    return sorted(deps)

def scan_python_dependencies():
    poetry_lock = os.path.join(os.getcwd(), 'poetry.lock')
    pyproject = os.path.join(os.getcwd(), 'pyproject.toml')
    requirements_path = os.path.join(os.getcwd(), 'requirements.txt')

    is_poetry = os.path.exists(poetry_lock)
    if not is_poetry and os.path.exists(pyproject):
        try:
            with open(pyproject, 'r', encoding='utf-8') as f:
                content = f.read()
                if '[tool.poetry]' in content:
                    is_poetry = True
        except Exception:
            pass

    if is_poetry:
        print("\n--- Scanning Python Dependencies (Poetry) ---\n")
        poetry_deps = parse_poetry_dependencies()
        installed_py = get_installed_python_packages()

        installed_deps = []
        missing_deps = []

        if poetry_deps:
            print("Found the following required Poetry dependencies:")
            for dep in poetry_deps:
                if dep.lower() in installed_py:
                    print(f"  [INSTALLED] {dep} - Already installed on machine")
                    installed_deps.append(dep)
                else:
                    print(f"  [MISSING]   {dep} - Not found on machine")
                    missing_deps.append(dep)

            total = len(poetry_deps)
            num_installed = len(installed_deps)
            num_missing = len(missing_deps)

            print("\nPoetry scan summary:")
            print(f"  Total required dependencies: {total}")
            print(f"  Installed: {num_installed}")
            print(f"  Missing: {num_missing}\n")

            if num_missing == 0:
                print("All required Poetry dependencies are already installed on your machine!")
                return True
        else:
            print("Poetry project detected. Starting dependency check via Poetry...")

        print("Starting installation of missing Poetry dependencies via Poetry")
        print("(To interrupt execution, press Ctrl + C)\n")

        try:
            for i in range(5, 0, -1):
                print(f"({i})")
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            sys.exit(0)

        print("\nInstalling Poetry dependencies in real-time...")
        try:
            res = subprocess.run(["poetry", "install"], check=False)
            if res.returncode == 0:
                print("\nPoetry prerequisites installed successfully!")
            else:
                print(f"\nFailed to install Poetry dependencies. Exit code: {res.returncode}")
        except Exception as err:
            print(f"\nError executing poetry: {err}")
        return True


    if not os.path.exists(requirements_path):
        return False

    print("\n--- Scanning Python Dependencies (requirements.txt) ---\n")
    req_deps = []
    try:
        with open(requirements_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    pkg_name = line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0].strip()
                    if pkg_name:
                        req_deps.append(pkg_name)
    except Exception as e:
        print(f"Error reading requirements.txt: {e}")
        return False

    installed_py = get_installed_python_packages()
    installed_deps = []
    missing_deps = []

    print("Found the following required Python dependencies:")
    for dep in req_deps:
        if dep.lower() in installed_py:
            print(f"  [INSTALLED] {dep} - Already installed on machine")
            installed_deps.append(dep)
        else:
            print(f"  [MISSING]   {dep} - Not found on machine")
            missing_deps.append(dep)

    total = len(req_deps)
    num_installed = len(installed_deps)
    num_missing = len(missing_deps)

    print("\nPython scan summary:")
    print(f"  Total required dependencies: {total}")
    print(f"  Installed: {num_installed}")
    print(f"  Missing: {num_missing}\n")

    if num_missing == 0:
        print("All required Python dependencies are already installed on your machine!")
        return True

    print("Starting installation of missing Python dependencies on machine")
    print("(To interrupt execution, press Ctrl + C)\n")

    try:
        for i in range(5, 0, -1):
            print(f"({i})")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)

    print("\nInstalling Python dependencies in real-time...")
    try:
        res = subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=False)
        if res.returncode == 0:
            print("\nPython prerequisites installed successfully!")
        else:
            print(f"\nFailed to install Python dependencies. Exit code: {res.returncode}")
    except Exception as err:
        print(f"\nError executing package manager: {err}")

    return True

def scan_project_dependencies():
    print("\nStarting scan of required dependencies for the project...\n")

    # Scan code files in project
    scanned_files = 0
    for root, dirs, files in os.walk(os.getcwd()):
        dirs[:] = [d for d in dirs if d not in ['node_modules', 'dist', '.git', '.vite', '.validators', '__pycache__', '.venv', 'venv']]
        for file in sorted(files):
            if file.endswith(('.ts', '.tsx', '.js', '.jsx', '.py')):
                rel_path = os.path.relpath(os.path.join(root, file), os.getcwd())
                scanned_files += 1
                print(f"Reading {rel_path}...")

    found_npm = scan_npm_dependencies()
    found_py = scan_python_dependencies()

    if not found_npm and not found_py:
        print("\nNo supported dependency manifest found (package.json, poetry.lock, or requirements.txt).")

def main():
    print_banner()
    scan_project_dependencies()

if __name__ == '__main__':
    main()


