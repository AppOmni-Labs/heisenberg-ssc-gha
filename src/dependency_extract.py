import toml
import json
import os
import sys
from typing import Set

from yarnlock import yarnlock_parse

# TOML extractor for poetry and uv
def _extract_toml(path: str) -> Set[str]:
    with open(path, "r") as f:
        packages = toml.load(f).get("package", []) or []
    return {
        f"{pkg['name']}=={pkg['version']}" 
        for pkg in packages 
        if pkg.get('name') and pkg.get('version')
    }

# Extract deps from poetry.lock
def extract_poetry(path: str) -> Set[str]:
    return _extract_toml(path)

# Extract deps from uv.lock
def extract_uv(path: str) -> Set[str]:
    return _extract_toml(path)

# Extract deps from package-lock.json
def extract_npm(path: str) -> Set[str]:
    with open(path, "r") as f:
        data = json.load(f)
    packages = data.get("packages", {})
    result = set()
    for pkg_path, details in packages.items():
        if not pkg_path or "version" not in details:
            continue

        package_name = pkg_path
        if package_name.startswith("node_modules/"):
            package_name = package_name.split("/", 1)[1]

        result.add(f"{package_name}=={details['version']}")
    return result


# Extract deps from yarn.lock
def extract_yarn(path: str) -> Set[str]:
    with open(path, "r", encoding="utf-8") as f:
        data = f.read()

    y = yarnlock_parse(data) or {}
    deps: Set[str] = set()

    for key, value in y.items():
        if not value:
            continue
        version = value.get("version")
        if not version:
            continue

        first_selector = str(key).split(",")[0].strip().strip('"').strip('"')
        npm_marker = "@npm:"
        if npm_marker in first_selector:
            name = first_selector.split(npm_marker, 1)[0]
        else:
            at = first_selector.rfind("@")
            if at <= 0:
                continue
            name = first_selector[:at]

        if name:
            deps.add(f"{name}=={version}")

    return deps


# Extract deps from requirements.txt
def extract_requirements(path: str) -> Set[str]:
    with open(path, "r") as f:
        lines = f.readlines()

    deps = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" in line:
            name, version = line.split("==", 1)
            deps.add(f"{name.strip()}=={version.strip()}")
    return deps


# Extract deps from go.mod
def extract_go(path: str) -> Set[str]:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    deps: Set[str] = set()
    in_require_block = False

    for dep in lines:
        line = dep.strip()

        if not line or line.startswith("//"):
            continue

        if line.startswith("replace ") or line.startswith("exclude "):
            continue

        if line == "require (":
            in_require_block = True
            continue
        if in_require_block and line == ")":
            in_require_block = False
            continue

        if in_require_block:
            parts = line.split()
            if len(parts) >= 2:
                module, version = parts[0], parts[1]
                if version[0].lower() == "v":
                    deps.add(f"{module}=={version}")
            continue

        if line.startswith("require "):
            parts = line[len("require "):].split()
            if len(parts) >= 2:
                module, version = parts[0], parts[1]
                if version[0].lower() == "v":
                    deps.add(f"{module}=={version}")

    return deps 


def main() -> None:
    lock_path = sys.argv[1]
    base_path = lock_path + ".base"

    if not os.path.exists(lock_path):
        print(f"ERROR: {lock_path} does not exist.")
        sys.exit(1)

    if not os.path.exists(base_path):
        print(f"WARNING: {base_path} does not exists, creating empty diff.")
        sys.exit(1)

    if lock_path.endswith("poetry.lock"):
        extract_logic = extract_poetry
    elif lock_path.endswith("uv.lock"):
        extract_logic = extract_uv
    elif lock_path.endswith("package-lock.json"):
        extract_logic = extract_npm
    elif lock_path.endswith("yarn.lock"):
        extract_logic = extract_yarn
    elif lock_path.endswith("requirements.txt"):
        extract_logic = extract_requirements
    elif lock_path.endswith("go.mod"):
        extract_logic = extract_go
    else:
        print("Unsupported lock file.")
        sys.exit(1)

    base_set = extract_logic(base_path)
    pr_set = extract_logic(lock_path)
    new_or_changed = pr_set - base_set

    with open("parsed_deps.txt", "w") as f:
        for entry in sorted(new_or_changed):
            name, version = entry.split("==")
            f.write(f"{name} {version}\n")

    if not new_or_changed:
        print("No new or changed dependencies.")
    else:
        print("new or updated dependencies:")
        for entry in sorted(new_or_changed):
            print(f" - {entry}")


if __name__ == "__main__":
    main()