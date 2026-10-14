#!/usr/bin/env python3
"""Generate correlated mock data across all MAHALO3 systems using 1min.ai.

The LLM (1min.ai) is used ONLY to produce short, realistic text content
(titles, descriptions, commit messages, incident summaries). All IDs and
cross-system links are wired in code, in dependency order, so the resulting
dataset is always referentially consistent:

    developers/projects (existing seed)
      -> jira stories
        -> github PRs (+ commits)
        -> confluence pages
        -> servicenow deployments
          -> servicenow incidents

Data is written directly into each mock service's persistent JSON store
(mock-services/<svc>/data.json), so it survives restarts and requires no
running services. Every generated text field is capped at 250 characters.

Usage (all count flags are REQUIRED):

    python generate_mock_data.py \\
        --jira-stories 20 --github-prs 8 --confluence-pages 6 \\
        --servicenow-deployments 5 --servicenow-incidents 4 \\
        [--append | --reset] [--seed 42] [--dry-run]

Default mode is --append (add on top of existing data). Use --reset to rebuild
from the clean seed first.
"""

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
MOCKS = ROOT / "mock-services"

MAX_CHARS = 250
BATCH_SIZE = 8  # records of content requested per LLM call (5-10 range)

# Services align to repos/projects.
SERVICES = [
    {"id": "payment-service", "repo_id": "repo-1", "project_id": "PAY"},
    {"id": "cart-service", "repo_id": "repo-2", "project_id": "CART"},
    {"id": "auth-service", "repo_id": "repo-3", "project_id": "AUTH"},
    {"id": "product-service", "repo_id": "repo-4", "project_id": "PROD"},
    {"id": "order-service", "repo_id": "repo-5", "project_id": "ORD"},
]
PROJECT_IDS = [s["project_id"] for s in SERVICES]
ENVIRONMENTS = ["staging", "production"]
DEPLOY_STATUSES = ["success", "success", "success", "failed", "rolled_back", "in_progress"]
SEVERITIES = ["P1", "P2", "P3", "P4"]
STORY_STATUSES = ["todo", "in_progress", "in_review", "done"]
PRIORITIES = ["critical", "high", "medium", "low"]


# ── 1min.ai content generation ────────────────────────────

def _load_env():
    """Read ONEMIN_* credentials from the root .env (simple parser)."""
    env = {}
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


class ContentGenerator:
    """Requests short text lines from 1min.ai, with a safe offline fallback."""

    def __init__(self, dry_run: bool = False):
        env = _load_env()
        self.api_key = env.get("ONEMIN_API_KEY", "")
        self.base_url = env.get("ONEMIN_BASE_URL", "https://api.1min.ai").rstrip("/v1").rstrip("/")
        self.model = env.get("SYNTHESIS_MODEL", "gpt-4o")
        self.dry_run = dry_run
        self.enabled = bool(self.api_key) and not self.api_key.startswith("your-") and not dry_run

    def _call(self, prompt: str) -> str:
        payload = {
            "type": "UNIFY_CHAT_WITH_AI",
            "model": self.model,
            "promptObject": {"prompt": prompt},
        }
        headers = {"Content-Type": "application/json", "API-KEY": self.api_key}
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{self.base_url}/api/chat-with-ai", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("aiRecord", {}).get("aiRecordDetail", {}).get("resultObject", [])
        return "\n".join(result) if isinstance(result, list) else str(result)

    def lines(self, description: str, n: int, examples: str = "") -> list[str]:
        """Return n short text lines for the given kind of content.

        Falls back to synthetic placeholders if the LLM is unavailable or
        returns too few usable lines, so generation never dead-ends.
        """
        out: list[str] = []
        if self.enabled:
            remaining = n
            while remaining > 0:
                take = min(BATCH_SIZE, remaining)
                prompt = (
                    f"Generate {take} realistic, concise {description} for an e-commerce "
                    f"engineering team. Return each on its own line, no numbering, no quotes. "
                    f"Each line must be under {MAX_CHARS} characters. {examples}"
                )
                try:
                    raw = self._call(prompt)
                    batch = [self._clean(l) for l in raw.splitlines() if l.strip()]
                    out.extend([b for b in batch if b][:take])
                except Exception as e:  # noqa: BLE001
                    print(f"  ! LLM call failed ({e}); using fallback for this batch", file=sys.stderr)
                    break
                remaining = n - len(out)
                time.sleep(0.3)  # be gentle on rate limits
        # Fallback / top-up
        while len(out) < n:
            out.append(self._fallback(description, len(out) + 1))
        return out[:n]

    @staticmethod
    def _clean(line: str) -> str:
        line = re.sub(r"^\s*[-*\d.)\]]+\s*", "", line).strip().strip('"').strip()
        return line[:MAX_CHARS]

    @staticmethod
    def _fallback(description: str, i: int) -> str:
        base = re.sub(r"[^a-zA-Z ]", "", description).strip().title()
        return f"{base} {i}"[:MAX_CHARS]


# ── store helpers ─────────────────────────────────────────

def _store_path(service: str) -> Path:
    return MOCKS / service / "data.json"


def _seed_module(service: str):
    import importlib.util

    seed_file = MOCKS / service / "seed_data.py"
    spec = importlib.util.spec_from_file_location(f"{service}_seed", seed_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_store(service: str, keys: list[str], reset: bool) -> dict:
    """Load a mock's data.json, or seed from seed_data.py (on reset/first run)."""
    path = _store_path(service)
    if reset or not path.exists():
        seed = _seed_module(service)
        return {k: list(getattr(seed, k, [])) if not isinstance(getattr(seed, k, []), dict)
                else dict(getattr(seed, k, {})) for k in keys}
    return json.loads(path.read_text(encoding="utf-8"))


def save_store(service: str, data: dict, dry_run: bool) -> None:
    path = _store_path(service)
    if dry_run:
        print(f"  [dry-run] would write {path} ({sum(len(v) for v in data.values() if isinstance(v, list))} list records)")
        return
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    print(f"  wrote {path}")


# ── ID helpers ────────────────────────────────────────────

def _next_num(items, id_prefix_split="-", start=100):
    mx = start
    for it in items:
        try:
            mx = max(mx, int(str(it["id"]).split(id_prefix_split)[-1]))
        except (KeyError, ValueError):
            continue
    return mx


# ── generation ────────────────────────────────────────────

def generate(args, gen: ContentGenerator):
    dev_ids = [f"dev-{i}" for i in range(1, 7)]  # dev-1..dev-6 (incl Lava Dev)

    # --- JIRA stories ---
    jira = load_store("jira", ["DEVELOPERS", "PROJECTS", "SPRINTS", "STORIES"], args.reset)
    story_titles = gen.lines("Jira user story titles", args.jira_stories,
                             examples="e.g. 'Add rate limiting to checkout API'.")
    story_descs = gen.lines("one-sentence Jira story descriptions", args.jira_stories)
    new_stories = []
    per_project_num = {p: _next_num([s for s in jira["STORIES"] if s["project_id"] == p]) for p in PROJECT_IDS}
    for i in range(args.jira_stories):
        proj = random.choice(PROJECT_IDS)
        per_project_num[proj] += 1
        sid = f"{proj}-{per_project_num[proj]}"
        story = {
            "id": sid,
            "project_id": proj,
            "sprint_id": None,
            "title": story_titles[i][:MAX_CHARS],
            "description": story_descs[i][:MAX_CHARS],
            "status": random.choice(STORY_STATUSES),
            "priority": random.choice(PRIORITIES),
            "story_points": random.choice([1, 2, 3, 5, 8, 13]),
            "assignee": random.choice(dev_ids + [None]),
            "acceptance_criteria": [],
            "comments": [],
        }
        jira["STORIES"].append(story)
        new_stories.append(story)
    save_store("jira", jira, args.dry_run)
    print(f"JIRA: +{len(new_stories)} stories")

    # Pool of all stories (existing + new) for linking.
    story_pool = jira["STORIES"]

    # --- GitHub PRs (+ commits) ---
    gh = load_store("github", ["REPOS", "BRANCHES", "PULL_REQUESTS", "COMMITS", "CONTRIBUTOR_STATS"], args.reset)
    pr_titles = gen.lines("GitHub pull request titles (feat/fix style)", args.github_prs,
                          examples="e.g. 'feat: add retry to payment webhook'.")
    commit_msgs = gen.lines("git commit messages (conventional commits)", args.github_prs * 3)
    pr_num = _next_num(gh["PULL_REQUESTS"], start=200)
    commit_seq = len(gh["COMMITS"])
    proj_to_repo = {s["project_id"]: s["repo_id"] for s in SERVICES}
    added_prs = 0
    for i in range(args.github_prs):
        story = random.choice(story_pool)
        repo_id = proj_to_repo[story["project_id"]]
        pr_num += 1
        author = story.get("assignee") or random.choice(dev_ids)
        branch = f"feature/{story['id']}-{re.sub(r'[^a-z0-9]+', '-', pr_titles[i].lower())[:24].strip('-')}"
        gh.setdefault("BRANCHES", {}).setdefault(repo_id, []).append(
            {"name": branch, "protected": False, "last_commit": "2026-08-25"}
        )
        gh["PULL_REQUESTS"].append({
            "id": f"pr-{pr_num}",
            "repo_id": repo_id,
            "number": pr_num,
            "title": pr_titles[i][:MAX_CHARS],
            "description": f"Linked to {story['id']}."[:MAX_CHARS],
            "author": author,
            "author_id": author,
            "status": random.choice(["open", "open", "draft", "merged"]),
            "branch": branch,
            "target_branch": "main",
            "created_at": "2026-08-22",
            "updated_at": "2026-08-24",
            "additions": random.randint(20, 500),
            "deletions": random.randint(0, 80),
            "files_changed": random.randint(1, 15),
            "reviews": [],
            "linked_story": story["id"],
        })
        for j in range(3):
            commit_seq += 1
            gh["COMMITS"].append({
                "id": f"c{commit_seq:03d}",
                "repo_id": repo_id,
                "branch": branch,
                "author": author,
                "author_id": author,
                "message": commit_msgs[i * 3 + j][:MAX_CHARS],
                "date": "2026-08-23",
                "additions": random.randint(5, 160),
                "deletions": random.randint(0, 30),
            })
        added_prs += 1
    save_store("github", gh, args.dry_run)
    print(f"GitHub: +{added_prs} PRs (+{added_prs * 3} commits)")

    # --- Confluence pages ---
    conf = load_store("confluence", ["SPACES", "PAGES"], args.reset)
    space_ids = [s["id"] for s in conf["SPACES"]] or ["ENG"]
    page_titles = gen.lines("Confluence documentation page titles", args.confluence_pages,
                            examples="e.g. 'Deployment runbook for payment-service'.")
    page_summaries = gen.lines("one-sentence documentation page summaries", args.confluence_pages)
    page_num = _next_num(conf["PAGES"], start=900)
    for i in range(args.confluence_pages):
        page_num += 1
        space = random.choice(space_ids)
        conf["PAGES"].append({
            "id": f"{space}-{page_num}",
            "space_id": space,
            "title": page_titles[i][:MAX_CHARS],
            "author": random.choice(dev_ids),
            "last_updated": "2026-08-24",
            "content": page_summaries[i][:MAX_CHARS],
        })
    save_store("confluence", conf, args.dry_run)
    print(f"Confluence: +{args.confluence_pages} pages")

    # --- ServiceNow deployments ---
    snow = load_store("servicenow", ["SERVICES", "DEPLOYMENTS", "INCIDENTS"], args.reset)
    if not snow.get("SERVICES"):
        snow["SERVICES"] = [{"id": s["id"], "repo_id": s["repo_id"], "project_id": s["project_id"],
                             "name": s["id"].replace("-", " ").title()} for s in SERVICES]
    dep_notes = gen.lines("one-line deployment notes", args.servicenow_deployments)
    dep_num = _next_num(snow["DEPLOYMENTS"], start=1000)
    new_deployments = []
    prs_by_repo = {}
    for pr in gh["PULL_REQUESTS"]:
        prs_by_repo.setdefault(pr["repo_id"], []).append(pr)
    for i in range(args.servicenow_deployments):
        svc = random.choice(SERVICES)
        dep_num += 1
        # Link to a PR/story on the same service when possible.
        linked_pr = None
        linked_story = None
        candidates = prs_by_repo.get(svc["repo_id"], [])
        if candidates:
            pr = random.choice(candidates)
            linked_pr = pr["number"]
            linked_story = pr.get("linked_story")
        dep = {
            "id": f"DEP-{dep_num}",
            "service": svc["id"],
            "environment": random.choice(ENVIRONMENTS),
            "version": f"v{random.randint(1,5)}.{random.randint(0,9)}.{random.randint(0,9)}",
            "status": random.choice(DEPLOY_STATUSES),
            "deployed_by": random.choice(dev_ids),
            "deployed_at": f"2026-08-{random.randint(10,25):02d}T{random.randint(0,23):02d}:00:00Z",
            "duration_seconds": random.randint(60, 400),
            "linked_story": linked_story,
            "linked_pr": linked_pr,
            "notes": dep_notes[i][:MAX_CHARS],
        }
        snow["DEPLOYMENTS"].append(dep)
        new_deployments.append(dep)

    # --- ServiceNow incidents (link to deployments) ---
    inc_titles = gen.lines("short production incident titles", args.servicenow_incidents,
                           examples="e.g. 'Checkout 500s after deploy'.")
    inc_descs = gen.lines("one-sentence incident descriptions", args.servicenow_incidents)
    inc_num = _next_num(snow["INCIDENTS"], start=2000)
    deployment_pool = snow["DEPLOYMENTS"]
    for i in range(args.servicenow_incidents):
        inc_num += 1
        # Prefer linking an incident to a failed/rolled_back deployment.
        risky = [d for d in deployment_pool if d["status"] in ("failed", "rolled_back")]
        linked_dep = random.choice(risky) if risky and random.random() < 0.6 else (
            random.choice(deployment_pool) if deployment_pool and random.random() < 0.4 else None
        )
        svc_id = linked_dep["service"] if linked_dep else random.choice(SERVICES)["id"]
        status = random.choice(["open", "investigating", "resolved"])
        snow["INCIDENTS"].append({
            "id": f"INC-{inc_num}",
            "title": inc_titles[i][:MAX_CHARS],
            "severity": random.choice(SEVERITIES),
            "status": status,
            "affected_service": svc_id,
            "assignee": random.choice(dev_ids),
            "opened_at": f"2026-08-{random.randint(12,26):02d}T{random.randint(0,23):02d}:00:00Z",
            "resolved_at": "2026-08-27T00:00:00Z" if status == "resolved" else None,
            "linked_deployment": linked_dep["id"] if linked_dep else None,
            "description": inc_descs[i][:MAX_CHARS],
        })
    save_store("servicenow", snow, args.dry_run)
    print(f"ServiceNow: +{args.servicenow_deployments} deployments, +{args.servicenow_incidents} incidents")


def main():
    parser = argparse.ArgumentParser(
        description="Generate correlated mock data across MAHALO3 systems via 1min.ai.",
    )
    parser.add_argument("--jira-stories", type=int, required=True, help="number of Jira stories")
    parser.add_argument("--github-prs", type=int, required=True, help="number of GitHub PRs (each gets 3 commits)")
    parser.add_argument("--confluence-pages", type=int, required=True, help="number of Confluence pages")
    parser.add_argument("--servicenow-deployments", type=int, required=True, help="number of ServiceNow deployments")
    parser.add_argument("--servicenow-incidents", type=int, required=True, help="number of ServiceNow incidents")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--append", action="store_true", help="add on top of existing data (default)")
    mode.add_argument("--reset", action="store_true", help="rebuild from clean seed first")
    parser.add_argument("--seed", type=int, default=None, help="random seed for reproducibility")
    parser.add_argument("--dry-run", action="store_true", help="preview without writing")
    args = parser.parse_args()

    for name, val in [
        ("--jira-stories", args.jira_stories), ("--github-prs", args.github_prs),
        ("--confluence-pages", args.confluence_pages),
        ("--servicenow-deployments", args.servicenow_deployments),
        ("--servicenow-incidents", args.servicenow_incidents),
    ]:
        if val < 0:
            parser.error(f"{name} must be >= 0")

    if args.seed is not None:
        random.seed(args.seed)

    gen = ContentGenerator(dry_run=args.dry_run)
    mode_label = "RESET" if args.reset else "APPEND"
    llm_label = "1min.ai" if gen.enabled else "offline fallback"
    print(f"Mode: {mode_label} | Content: {llm_label} | dry-run: {args.dry_run}\n")
    generate(args, gen)
    print("\nDone. Restart the mock services (or they'll load the new data.json on next start).")


if __name__ == "__main__":
    main()
