import os
import re
from dataclasses import dataclass
from datetime import datetime

import requests


@dataclass
class RepoActivity:
    name: str
    url: str
    pushed_at: str
    primary_language: str


@dataclass
class LanguageUsage:
    language: str
    bytes: int


@dataclass
class ActivityResponse:
    repos: list[RepoActivity]
    languages: list[LanguageUsage]


TOKEN = os.environ["GH_TOKEN"]
USERNAME = os.environ["GH_USERNAME"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def get_ignored_repos(extra_repos: list[str] | None = None) -> set[str]:
    """Devuelve un conjunto en minúsculas con los repositorios a ignorar."""
    ignored = {USERNAME.lower()}  # Siempre ignora el repositorio de perfil

    # Añade los repositorios definidos por código
    if extra_repos:
        ignored.update(repo.strip().lower() for repo in extra_repos if repo.strip())

    # Opcional: también permite leer una lista separada por comas desde .env (ej: IGNORED_REPOS=repo1,repo2)
    env_ignored = os.getenv("IGNORED_REPOS", "")
    if env_ignored:
        ignored.update(
            repo.strip().lower() for repo in env_ignored.split(",") if repo.strip()
        )

    return ignored


def get_latest_activity(
    limit: int = 10, ignored_repos: set[str] | None = None
) -> ActivityResponse:
    if ignored_repos is None:
        ignored_repos = get_ignored_repos()
    url = "https://api.github.com/user/repos"
    params = {
        "sort": "pushed",
        "direction": "desc",
        "per_page": limit,
        "affiliation": "owner",
    }

    response = requests.get(url, headers=HEADERS, params=params, timeout=10)
    response.raise_for_status()
    repos = response.json()

    latest_repos: list[RepoActivity] = []
    language_bytes: dict[str, int] = {}

    for repo in repos:
        # Ignore the special profile repository (username/username)
        if repo["name"].lower() in ignored_repos:
            continue
        pushed_dt = datetime.strptime(repo["pushed_at"], "%Y-%m-%dT%H:%M:%SZ")
        latest_repos.append(
            RepoActivity(
                name=repo["name"],
                url=repo["html_url"],
                pushed_at=pushed_dt.strftime("%Y-%m-%d %H:%M UTC"),
                primary_language=repo["language"] or "None",
            )
        )

        lang_response = requests.get(repo["languages_url"], headers=HEADERS, timeout=10)
        if lang_response.status_code == 200:
            for lang, byte_count in lang_response.json().items():
                language_bytes[lang] = language_bytes.get(lang, 0) + byte_count

    sorted_languages = [
        LanguageUsage(language=lang, bytes=count)
        for lang, count in sorted(
            language_bytes.items(), key=lambda x: x[1], reverse=True
        )
    ]

    return ActivityResponse(repos=latest_repos, languages=sorted_languages)


def generate_markdown_sections(
    activity: ActivityResponse, max_repos: int = 5, max_langs: int = 5
) -> str:
    """Generates formatted Markdown sections from an ActivityResponse object."""
    lines = []

    # 1. Projects Section
    lines.append("### 🚀 Latest Committed Projects\n")
    if not activity.repos:
        lines.append("*No recent repository activity found.*\n")
    else:
        for repo in activity.repos[:max_repos]:
            lines.append(
                f"- **[{repo.name}]({repo.url})** (`{repo.primary_language}`) — Last pushed: *{repo.pushed_at}*"
            )
        lines.append("")

    # 2. Languages Section
    lines.append("### 💻 Recently Used Languages\n")
    if not activity.languages:
        lines.append("*No language data available.*\n")
    else:
        total_bytes = sum(item.bytes for item in activity.languages)
        for item in activity.languages[:max_langs]:
            percentage = (item.bytes / total_bytes) * 100 if total_bytes > 0 else 0
            filled_blocks = round(percentage / 10)
            bar = "█" * filled_blocks + "░" * (10 - filled_blocks)
            lines.append(f"- **{item.language}**: `{bar}` {percentage:.1f}%")

    return "\n".join(lines)


def update_readme(
    markdown_content: str,
    readme_path: str = "README.md",
    start_marker: str = "<!-- START_ACTIVITY -->",
    end_marker: str = "<!-- END_ACTIVITY -->",
) -> None:
    """Replaces content between start and end markers in the specified README file."""
    with open(readme_path, "r", encoding="utf-8") as file:
        readme_text = file.read()

    pattern = re.compile(
        rf"({re.escape(start_marker)}).*?({re.escape(end_marker)})",
        flags=re.DOTALL,
    )

    if not pattern.search(readme_text):
        raise ValueError(
            f"Could not find {start_marker} and {end_marker} in {readme_path}"
        )

    replacement = f"{start_marker}\n{markdown_content}\n{end_marker}"
    updated_readme = pattern.sub(replacement, readme_text)

    if updated_readme != readme_text:
        with open(readme_path, "w", encoding="utf-8") as file:
            file.write(updated_readme)
        print(f"Successfully updated {readme_path}.")
    else:
        print(f"No changes detected in {readme_path}.")


if __name__ == "__main__":
    ignored = get_ignored_repos(["navi-cheats", "scripts"])
    activity_response = get_latest_activity(limit=10, ignored_repos=ignored)
    markdown = generate_markdown_sections(activity_response, max_repos=5, max_langs=5)
    update_readme(markdown, readme_path="README.md")
