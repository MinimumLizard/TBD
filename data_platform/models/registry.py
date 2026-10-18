"""Find every model, check every manifest, order the models by dependency, and publish them.

    python -m data_platform.models.registry check              # CI: exit 1 on any problem
    python -m data_platform.models.registry order              # the order models run in
    python -m data_platform.models.registry publish            # write manifests to models.registry (DATABASE_URL)
    python -m data_platform.models.registry export-web         # regenerate web/lib/generated/registry.json

What "check" enforces, so a broken plug-in fails CI rather than the site:
  * the folder name matches the manifest; compute.py defines compute(); METHOD.md exists;
  * the title and summary keys exist in web/messages/en.json (text never lives in a manifest);
  * the disclaimer key exists in compliance/disclaimers.yaml;
  * every dataset read and every table written exists in db/migrations; every output has exactly one owner;
  * every pinned dependency names a model and version that exist, and there are no cycles;
  * config/entitlements.yaml gives every model a tier that exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

from ..core.settings import REPO_ROOT
from .framework import MODELS_DIR, Manifest, load_manifest, model_names

MIGRATIONS = REPO_ROOT / "db" / "migrations"
MESSAGES_EN = REPO_ROOT / "web" / "messages" / "en.json"
DISCLAIMERS = REPO_ROOT / "compliance" / "disclaimers.yaml"
ENTITLEMENTS = REPO_ROOT / "config" / "entitlements.yaml"
WEB_EXPORT = REPO_ROOT / "web" / "lib" / "generated" / "registry.json"

RELATION = re.compile(r"create\s+(?:or\s+replace\s+)?(?:table|view)\s+(?:if\s+not\s+exists\s+)?([a-z_]+\.[a-z_]+)",
                      re.IGNORECASE)


def relations_in_migrations(directory: Path = MIGRATIONS) -> set[str]:
    out = set()
    for path in directory.glob("*.sql"):
        text = "\n".join(line.split("--", 1)[0] for line in path.read_text().splitlines())
        out.update(m.lower() for m in RELATION.findall(text))
    return out


def _has_key(messages: dict, dotted: str) -> bool:
    node = messages
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return isinstance(node, str) and bool(node.strip())


def load_entitlements(path: Path = ENTITLEMENTS) -> dict:
    return yaml.safe_load(path.read_text())


def load_all(root: Path = MODELS_DIR) -> dict[str, Manifest]:
    return {name: load_manifest(name, root) for name in model_names(root)}


def check(root: Path = MODELS_DIR) -> list[str]:
    """Every problem found, as one line each. Empty means valid."""
    problems: list[str] = []
    manifests: dict[str, Manifest] = {}
    for name in model_names(root):
        try:
            manifests[name] = load_manifest(name, root)
        except Exception as exc:  # noqa: BLE001 - reported, not raised: show every broken manifest at once
            problems.append(f"{name}: invalid manifest: {exc}")
    relations = relations_in_migrations()
    messages = json.loads(MESSAGES_EN.read_text()) if MESSAGES_EN.exists() else {}
    disclaimers = yaml.safe_load(DISCLAIMERS.read_text())
    ent = load_entitlements()
    tiers = ent.get("tiers", [])
    owners: dict[str, str] = {}

    for name, m in manifests.items():
        folder = root / name
        compute_py = folder / "compute.py"
        if not compute_py.exists() or not re.search(r"^def compute\(inputs, as_of", compute_py.read_text(), re.M):
            problems.append(f"{name}: compute.py must define compute(inputs, as_of)")
        if not (folder / "METHOD.md").exists():
            problems.append(f"{name}: METHOD.md is missing")
        for key in (m.title_key, m.summary_key):
            if not _has_key(messages, key):
                problems.append(f"{name}: message key {key} is not in web/messages/en.json")
        if m.disclaimer_key not in disclaimers:
            problems.append(f"{name}: disclaimer {m.disclaimer_key} is not in compliance/disclaimers.yaml")
        for ds in m.requires_datasets:
            if ds.lower() not in relations:
                problems.append(f"{name}: requires {ds}, which no migration creates")
        for out in m.outputs:
            if out.lower() not in relations:
                problems.append(f"{name}: outputs {out}, which no migration creates")
            if out != "models.model_stats":
                if out in owners:
                    problems.append(f"{name}: {out} is already written by {owners[out]}")
                owners[out] = name
        entry = (ent.get("models") or {}).get(name)
        if not entry or entry.get("minimum_tier") not in tiers:
            problems.append(f"{name}: config/entitlements.yaml gives it no valid minimum_tier")
        elif entry.get("free_preview") and int(entry["free_preview"].get("delay_days", 0)) <= 0:
            problems.append(f"{name}: free_preview.delay_days must be a positive number of days")
        elif entry.get("recent_window"):
            rw = entry["recent_window"]
            if int(rw.get("days", 0)) <= 0:
                problems.append(f"{name}: recent_window.days must be a positive number of days")
            if rw.get("full_history_tier") not in tiers or \
                    tiers.index(rw.get("full_history_tier")) <= tiers.index(entry["minimum_tier"]):
                problems.append(f"{name}: recent_window.full_history_tier must be a tier above the minimum tier")

    for name, m in manifests.items():
        for v in m.versions:
            for dep, dep_version in v.requires_models.items():
                if dep not in manifests:
                    problems.append(f"{name} {v.method_version}: requires unknown model {dep}")
                    continue
                try:
                    dv = manifests[dep].version(dep_version)
                except KeyError:
                    problems.append(f"{name} {v.method_version}: requires {dep} {dep_version}, which does not exist")
                    continue
                if dv.status == "retired" and v.status != "retired":
                    problems.append(f"{name} {v.method_version}: requires retired {dep} {dep_version}")
    for extra in set((ent.get("models") or {})) - set(manifests):
        problems.append(f"config/entitlements.yaml: {extra} is not a model")
    try:
        order(manifests)
    except ValueError as exc:
        problems.append(str(exc))
    return problems


def order(manifests: dict[str, Manifest]) -> list[str]:
    """Models in an order where every dependency runs first (alphabetical among equals, so it is stable)."""
    deps = {n: {d for v in m.active_versions for d in v.requires_models} for n, m in manifests.items()}
    done: list[str] = []
    while len(done) < len(deps):
        ready = sorted(n for n, d in deps.items() if n not in done and d <= set(done))
        if not ready:
            raise ValueError(f"dependency cycle among {sorted(set(deps) - set(done))}")
        done += ready
    return done


def web_export(manifests: dict[str, Manifest], root: Path = MODELS_DIR) -> dict:
    """Everything the web app needs, in one generated file, so it never reads outside web/: tiers and each model's
    minimum tier, labels, current version and method page; the disclaimer texts; the trading calendars (for the
    freshness check). No parameters, nothing secret."""
    ent = load_entitlements()
    calendars = {}
    for path in sorted((REPO_ROOT / "config" / "calendars").glob("*.yaml")):
        cal = yaml.safe_load(path.read_text())
        calendars[path.stem] = {"name": cal.get("name"), "every_day": bool(cal.get("every_day", False)),
                                "closures": sorted(str(d) for d in (cal.get("closures") or {}))}
    return {
        "tiers": ent["tiers"],
        "unpublished_outputs": ent.get("unpublished_outputs", []),
        "disclaimers": {key: {"en": " ".join(value["en"].split())} for key, value in
                        yaml.safe_load(DISCLAIMERS.read_text()).items()},
        "calendars": calendars,
        "models": {
            name: {
                "market": m.market,
                "title_key": m.title_key,
                "summary_key": m.summary_key,
                "disclaimer_key": m.disclaimer_key,
                "outputs": m.outputs,
                "current_version": m.current.method_version,
                "versions": [{"method_version": v.method_version, "status": v.status, "changes": v.changes}
                             for v in m.versions],
                "minimum_tier": ent["models"][name]["minimum_tier"],
                "free_preview": ent["models"][name].get("free_preview"),
                "recent_window": ent["models"][name].get("recent_window"),
                "method_md": (root / name / "METHOD.md").read_text(),
            } for name, m in sorted(manifests.items())
        },
    }


def web_export_text(manifests: dict[str, Manifest]) -> str:
    return json.dumps(web_export(manifests), indent=2, sort_keys=True) + "\n"


def publish(conn, manifests: dict[str, Manifest]) -> int:
    n = 0
    for name, m in manifests.items():
        for v in m.versions:
            body = m.model_dump(mode="json")
            text = json.dumps(body, sort_keys=True)
            conn.execute(
                """insert into models.registry (model, method_version, status, manifest, manifest_sha256)
                   values (%s, %s, %s, %s::jsonb, %s)
                   on conflict (model, method_version) do update set status = excluded.status,
                     manifest = excluded.manifest, manifest_sha256 = excluded.manifest_sha256, published_at = now()
                   where models.registry.manifest_sha256 <> excluded.manifest_sha256
                      or models.registry.status <> excluded.status""",
                (name, v.method_version, v.status, text, hashlib.sha256(text.encode()).hexdigest()))
            n += 1
    conn.commit()
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["check", "order", "publish", "export-web"])
    parser.add_argument("--check-only", action="store_true", help="export-web: fail if the file is out of date")
    args = parser.parse_args(argv)

    if args.command == "check":
        problems = check()
        for p in problems:
            print(p)
        print(f"model registry: {len(model_names())} model(s), {len(problems)} problem(s)")
        return 1 if problems else 0
    manifests = load_all()
    if args.command == "order":
        print("\n".join(order(manifests)))
        return 0
    if args.command == "export-web":
        text = web_export_text(manifests)
        if args.check_only:
            if not WEB_EXPORT.exists() or WEB_EXPORT.read_text() != text:
                print(f"{WEB_EXPORT.relative_to(REPO_ROOT)} is out of date: run "
                      "python -m data_platform.models.registry export-web")
                return 1
            return 0
        WEB_EXPORT.parent.mkdir(parents=True, exist_ok=True)
        WEB_EXPORT.write_text(text)
        print(f"wrote {WEB_EXPORT.relative_to(REPO_ROOT)}")
        return 0
    from ..core import db, settings as settings_mod
    conn = db.connect(settings_mod.load().database_url)
    print(f"published {publish(conn, manifests)} model version(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
