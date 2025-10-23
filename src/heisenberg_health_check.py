import argparse
import math
import requests
import sys, os
import urllib

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

sys.path.append(os.path.dirname(__file__))
from npm_postinstall_detection import check_npm_postinstall

parser = argparse.ArgumentParser(description="Check package info using deps.dev")
parser.add_argument(
    "mode",
    nargs="?",
    default="main_package",
    choices=["main_package"],
    help="Only 'main_package' is supported.",
)
parser.add_argument(
    "-mgmt", "--mgmt", required=True, help="Package management system (e.g., pypi, npm)"
)
parser.add_argument("-pkg", "--pkg", required=True, help="Package name")
parser.add_argument("-v", "--version", required=True, help="Package version")
args = parser.parse_args()

# TODO: Extend support to other pkg managers: docker, githubactions, gem, etc
SUPPORTED_MANAGERS = {"pypi", "npm", "go"}

PACKAGE_MANAGER = args.mgmt.lower()

if PACKAGE_MANAGER not in SUPPORTED_MANAGERS:
    print(f"Error: Package manager '{args.mgmt}' is not supported yet.")
    sys.exit(1)

PACKAGE_NAME = args.pkg
PACKAGE_VERSION = args.version
BASE_URL = "https://api.deps.dev/v3"

ENCODED_PACKAGE_NAME = urllib.parse.quote(PACKAGE_NAME, safe="")


def fetch_version_data(
    base_url: str, package_manager: str, encoded_name: str, package_version: str
) -> requests.Response:
    return requests.get(
        f"{base_url}/systems/{package_manager}/packages/{encoded_name}/versions/{package_version}"
    )


def fetch_dependents_count(package_manager: str, encoded_name: str, package_version: str) -> str:
    dependents_url = f"https://api.deps.dev/v3alpha/systems/{package_manager}/packages/{encoded_name}/versions/{package_version}:dependents"
    dependents_response = requests.get(dependents_url)
    if dependents_response.status_code == 200:
        return dependents_response.json().get("dependentCount", "N/A")
    return "N/A"


def fetch_npm_deprecated(
    package_manager: str, package_name: str, package_version: str
) -> str | None:
    if package_manager != "npm":
        return None
    npm_url = f"https://registry.npmjs.org/{package_name}/{package_version}"
    npm_resp = requests.get(npm_url)
    if npm_resp.status_code == 200:
        npm_data = npm_resp.json()
        return npm_data.get("deprecated", None)
    else:
        return None


def fetch_pypi_deprecated(
    package_manager: str, package_name: str, package_version: str
) -> str | None:
    if package_manager != "pypi":
        return None
    url = f"https://pypi.org/pypi/{package_name}/{package_version}/json"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        info = data.get("info", {}) or {}
        classifiers = info.get("classifiers", []) or []
        for c in classifiers:
            if c.strip().lower() == "development status :: 7 - inactive".lower():
                return "Inactive/Deprecated (Development Status :: 7 - Inactive)"
        return None
    except Exception:
        return None


def fetch_project_data_with_github_fallback(
    base_url: str, project_id: str
) -> Tuple[Dict[str, Any], int, int]:
    project_data = {}
    stars = 0
    forks = 0
    if not project_id:
        return project_data, stars, forks
    project_url = f"{base_url}/projects/{urllib.parse.quote(project_id, safe='')}"
    project_response = requests.get(project_url)
    if project_response.status_code == 200:
        return project_response.json(), stars, forks
    if project_id.startswith("github.com"):
        try:
            owner_repo = project_id.replace("github.com/", "")
            gh_api_url = f"https://api.github.com/repos/{owner_repo}"
            gh_resp = requests.get(gh_api_url)
            if gh_resp.status_code == 200:
                gh_data = gh_resp.json()
                stars = gh_data.get("stargazers_count", 0)
                forks = gh_data.get("forks_count", 0)
        except Exception:
            pass
    return project_data, stars, forks


# HIGHLY EXPERIMENTAL and still requires further testing: 
# Custom Health Score Calculator - add this to soften deps.dev score that could be too harsh. This score weighs higher into security rather than popularity.
def compute_custom_health_score(parsed: Dict[str, Any]) -> float | str:
    try:
        stars = int(parsed["popularity_info_stars"])
        forks = int(parsed["popularity_info_forks"])
        maintained = (
            float(parsed["maintenance_info"]) if parsed["maintenance_info"] != "N/A" else 0
        )
        vulnerabilities = (
            float(parsed["security_score"]) if parsed["security_score"] != "N/A" else 0
        )
        dependents = int(parsed["dependents"]) if parsed["dependents"] != "N/A" else 0

        # Popularity log scale normalized
        raw_pop = math.log1p(stars + forks)
        popularity_score = min((raw_pop / 2.5) * 10, 10)

        # Dependents log scale normalized
        dependent_score = min((math.log1p(dependents) / 10) * 10, 10)

        # Final custom weighted health score
        health_score = (
            popularity_score * 0.25
            + maintained * 0.2
            + vulnerabilities * 0.3
            + dependent_score * 0.25
        )
        computed = round(health_score, 1)

        # Adjust based on package health score from deps.dev
        if parsed["health_score"] not in {"N/A", "Not Found"}:
            try:
                package_score = float(parsed["health_score"])
                final_score = round((package_score + computed) / 2, 1)
                return final_score
            except ValueError:
                pass

        return computed
    except Exception:
        return "Unknown"


version_response = fetch_version_data(
    BASE_URL, PACKAGE_MANAGER, ENCODED_PACKAGE_NAME, PACKAGE_VERSION
)


deprecated = None
if PACKAGE_MANAGER == "npm":
    deprecated = fetch_npm_deprecated(PACKAGE_MANAGER, PACKAGE_NAME, PACKAGE_VERSION)
elif PACKAGE_MANAGER == "pypi":
    deprecated = fetch_pypi_deprecated(PACKAGE_MANAGER, PACKAGE_NAME, PACKAGE_VERSION)

if version_response.status_code != 200:
    print(f"Package: {PACKAGE_NAME}")
    print(f"Version: {PACKAGE_VERSION}")
    print("Package Health Score: Not Found")
    print("Description: N/A")
    print("Popularity (Stars): N/A")
    print("Popularity (Forks): N/A")
    print("Dependents: N/A")
    print("Maintained Score: N/A")
    print("Security Advisory: None")
    print("Security Score (Vulnerabilities): N/A")
    print("Deprecated: N/A")
    print("Published At: N/A")
    print("Fresh Publish (<24h): N/A")
    sys.exit(0)

version_data = version_response.json()
related_projects = version_data.get("relatedProjects", [])
project_id = related_projects[0].get("projectKey", {}).get("id", "") if related_projects else ""

advisory_keys = version_data.get("advisoryKeys", [])
advisory_ids = [adv.get("id") for adv in advisory_keys]

published_at_iso = version_data.get("publishedAt")
fresh_flag = "N/A"
if published_at_iso:
    try:
        dt = datetime.fromisoformat(published_at_iso.replace("Z", "+00:00"))
        hours_old = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
        fresh_flag = "Yes" if hours_old < 24.0 else "No"
    except Exception:
        fresh_flag = "N/A"

npminfo = None
if PACKAGE_MANAGER == "npm":
    try:
        npminfo = check_npm_postinstall(PACKAGE_NAME, PACKAGE_VERSION)
    except Exception as e:
        npminfo = {"has_postinstall": False, "lifecycle": [], "postinstall_cmd": "", "error": str(e)}

dependent_count = fetch_dependents_count(PACKAGE_MANAGER, ENCODED_PACKAGE_NAME, PACKAGE_VERSION)

project_data, gh_stars, gh_forks = fetch_project_data_with_github_fallback(BASE_URL, project_id)

scorecard = {check["name"]: check for check in project_data.get("scorecard", {}).get("checks", [])}

parsed = {
    "health_score": project_data.get("scorecard", {}).get("overallScore", "N/A"),
    "description": project_data.get("description", "N/A"),
    "popularity_info_stars": project_data.get("starsCount", gh_stars if gh_stars else 0),
    "popularity_info_forks": project_data.get("forksCount", gh_forks if gh_forks else 0),
    "dependents": dependent_count,
    "maintenance_info": scorecard.get("Maintained", {}).get("score", "N/A"),
    "security_score": scorecard.get("Vulnerabilities", {}).get("score", "N/A"),
}
custom_score = compute_custom_health_score(parsed)

# TODO: Add custom health care score if no health score available. Still exprimenting with this.
print(f"Package: {PACKAGE_NAME}")
print(f"Version: {PACKAGE_VERSION}")
print(f"Package Health Score: {parsed['health_score']}")
print(f"Description: {parsed['description']}")
print(f"Popularity (Stars): {parsed['popularity_info_stars']}")
print(f"Popularity (Forks): {parsed['popularity_info_forks']}")
print(f"Dependents: {dependent_count}")
print(f"Maintained Score: {parsed['maintenance_info']}")

if advisory_ids:
    print(f"Security Advisory Count: {len(advisory_ids)}")
    print(f"Security Advisory IDs: {', '.join(advisory_ids)}")
else:
    print("Security Advisory: None")

print(f"Deprecated: {deprecated}")

print(f"Custom Health Score: {custom_score}")

print(f"Security Score (Vulnerabilities): {parsed['security_score']}")

print(f"Published At: {published_at_iso or 'N/A'}")
print(f"Fresh Publish (<24h): {fresh_flag}")

if PACKAGE_MANAGER == "npm":
    has_post = "Yes" if (npminfo and npminfo.get("has_postinstall")) else "No"
    lifecycle = ", ".join(npminfo.get("lifecycle", [])) if npminfo else ""
    post_cmd = (npminfo or {}).get("postinstall_cmd") or ""
    short_cmd = (post_cmd[:160] + "…") if len(post_cmd) > 160 else post_cmd

    print(f"Has Postinstall: {has_post}")
    print(f"Lifecycle Scripts: {lifecycle or 'None'}")
    if has_post == "Yes":
        print(f"Postinstall Cmd: {short_cmd or 'N/A'}")
