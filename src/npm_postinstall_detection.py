import io, json, tarfile, urllib.parse, requests

def fetch_npm_tarball_bytes(name: str, version: str, timeout=(15, 30)) -> bytes:
    safe = urllib.parse.quote(name, safe="")
    meta_url = f"https://registry.npmjs.org/{safe}/{version}"
    m = requests.get(meta_url, timeout=timeout[0])
    m.raise_for_status()
    tarball_url = m.json()["dist"]["tarball"]
    r = requests.get(tarball_url, timeout=timeout[1])
    r.raise_for_status()
    return r.content

def extract_package_json_from_tarball(tar_bytes: bytes) -> dict | None:
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tf:
        candidates = ["package/package.json", "package.json"]
        members = {m.name: m for m in tf.getmembers()}
        for cand in candidates:
            if cand in members:
                f = tf.extractfile(members[cand])
                if not f:
                    continue
                try:
                    return json.load(io.TextIOWrapper(f, encoding="utf-8"))
                except Exception:
                    return None
    return None

def detect_postinstall_scripts(pkg_json: dict) -> dict:
    """
    Return lifecycle info:
      { "has_postinstall": bool, "lifecycle": ["postinstall", "install", ...], "postinstall_cmd": "..." }
    """
    scripts = (pkg_json or {}).get("scripts") or {}
    lifecycle_keys = {"postinstall", "install", "prepare"}
    lifecycle_present = sorted([k for k in scripts.keys() if k in lifecycle_keys])
    return {
        "has_postinstall": "postinstall" in scripts,
        "lifecycle": lifecycle_present,
        "postinstall_cmd": scripts.get("postinstall", ""),
    }

def check_npm_postinstall(name: str, version: str) -> dict:
    """
    High-level check used by Heisenberg:
      {
        "has_postinstall": bool,
        "lifecycle": [...],
        "postinstall_cmd": "..."
      }
    """
    blob = fetch_npm_tarball_bytes(name, version)
    pkg_json = extract_package_json_from_tarball(blob)
    if not pkg_json:
        return {"has_postinstall": False, "lifecycle": [], "postinstall_cmd": ""}
    return detect_postinstall_scripts(pkg_json)
