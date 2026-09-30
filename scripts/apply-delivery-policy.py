#!/usr/bin/env python3
"""Plan and apply the Hraness main-delivery policy with the existing gh session.

First run: REPO --mode checked-pr --dry-run
Apply the reviewed result: REPO --mode checked-pr --expect-plan PLAN_HASH
Repeat all policy options in both commands. checked-pr always requires
Required from GitHub Actions (integration 15368); --context adds other checks.
For a publisher that requires an up-to-date base, --require-up-to-date explicitly
enables strict checks in the managed ruleset. It is valid only with checked-pr;
without it, existing strictness is preserved. It never weakens strict checks.

Only repository merge settings, main_policy, and the repository-owned ruleset
named Protect main delivery are managed. Existing check providers, strictness,
bypass actors, and other rules/parameters are retained. Managed human approval
flags are disabled and merge methods are limited to squash. Other rulesets,
classic protection, and environments are untouched. direct refuses existing PR
or check requirements; it never removes them. No GitHub App setup is required.

Dry-run emits exact mutation payloads and a hash bound to the observed policy.
Apply requires that hash, re-reads policy before and after each write, and stops
on drift or an API error. GitHub provides no transaction across these endpoints:
a concurrent change between a read and a write remains possible, and a failure
may leave earlier writes applied. Inspect a fresh dry-run before retrying.
"""

import argparse
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import re
import subprocess
import sys
from urllib.parse import quote


GH = "/opt/homebrew/bin/gh"
ORG = "hraness"
MANAGED_NAME = "Protect main delivery"
REQUIRED_APP = 15368
PAGE_SIZE = 100
MAX_PAGES = 100
SETTINGS = {
    "allow_auto_merge": True,
    "allow_merge_commit": False,
    "allow_rebase_merge": False,
    "allow_squash_merge": True,
    "delete_branch_on_merge": True,
    "allow_update_branch": True,
    "squash_merge_commit_title": "PR_TITLE",
    "squash_merge_commit_message": "PR_BODY",
}
PR_POLICY = {
    "required_approving_review_count": 0,
    "dismiss_stale_reviews_on_push": False,
    "require_code_owner_review": False,
    "require_last_push_approval": False,
    "required_review_thread_resolution": False,
    "require_extra_approval_for_unattributed_changes": False,
    "allowed_merge_methods": ["squash"],
}
WRITABLE_RULESET = {
    "name", "target", "enforcement", "bypass_actors", "conditions", "rules",
}
READ_ONLY_RULESET = {
    "id", "node_id", "source", "source_type", "created_at", "updated_at",
    "current_user_can_bypass", "_links",
}


class PolicyError(Exception):
    """An input, state, or transport failure safe to print without API bodies."""


def require(condition, message):
    if not condition:
        raise PolicyError(message)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise PolicyError("Policy data is not valid JSON.") from error


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "API JSON contains duplicate keys.")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise PolicyError("API JSON contains a non-finite number.")

    def finite_float(value):
        number = float(value)
        require(math.isfinite(number), "API JSON contains a non-finite number.")
        return number

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant, parse_float=finite_float)
    except (ValueError, TypeError) as error:
        raise PolicyError("API returned invalid JSON.") from error


def clean_string(value):
    return isinstance(value, str) and bool(value.strip()) and not any(
        ord(char) < 32 or ord(char) == 127 for char in value
    )


def repository_name(value):
    parts = value.split("/")
    require(len(parts) in (1, 2), "Use a repository name or hraness/REPO.")
    if len(parts) == 2:
        require(parts[0].lower() == ORG, "Only repositories in hraness are supported.")
    name = parts[-1]
    require(
        re.fullmatch(r"[A-Za-z0-9._-]{1,100}", name) is not None and name not in (".", ".."),
        "Invalid repository name.",
    )
    return f"{ORG}/{name}"


def valid_branch(value):
    return clean_string(value) and not (
        value.startswith(("/", "-")) or value.endswith(("/", ".")) or value == "@" or
        any(part in value for part in ("..", "//", "@{")) or
        re.search(r"[\s~^:?*\[\\]", value) or
        any(part.startswith(".") or part.endswith(".lock") for part in value.split("/"))
    )


class GitHub:
    def request(self, method, path, body=None, missing=False):
        command = [
            GH, "api", "--hostname", "github.com", "--include", "--method", method,
            path, "-H", "Accept: application/vnd.github+json",
            "-H", "X-GitHub-Api-Version: 2022-11-28",
        ]
        if body is not None:
            command += ["--input", "-"]
        try:
            result = subprocess.run(
                command, input=canonical(body) if body is not None else None,
                capture_output=True, text=True, timeout=60, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PolicyError("gh could not complete the API request; no automatic retry.") from error
        headers, separator, response = result.stdout.replace("\r\n", "\n").partition("\n\n")
        status_line = headers.split("\n", 1)[0]
        match = re.fullmatch(r"HTTP/[0-9.]+ ([0-9]{3})(?: .*)?", status_line)
        require(bool(match) and bool(separator), "gh returned no recognizable HTTP response.")
        status = int(match.group(1))
        if missing and status == 404:
            return None
        require(
            result.returncode == 0 and 200 <= status < 300,
            f"GitHub {method} failed (HTTP {status}); no automatic retry.",
        )
        return strict_json(response) if response.strip() else None


def pages(api, path):
    result, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        separator = "&" if "?" in path else "?"
        items = api.request("GET", f"{path}{separator}per_page={PAGE_SIZE}&page={page}")
        require(isinstance(items, list) and len(items) <= PAGE_SIZE, "Invalid API list page.")
        fingerprint = digest(items)
        require(not items or fingerprint not in seen, "API pagination repeated a page.")
        seen.add(fingerprint)
        result.extend(items)
        if len(items) < PAGE_SIZE:
            return result
    raise PolicyError("API pagination exceeded the supported limit.")


def validate_checks(parameters, classic=False):
    require(isinstance(parameters, dict), "Invalid required-check parameters.")
    strict = "strict" if classic else "strict_required_status_checks_policy"
    require(type(parameters.get(strict)) is bool, "Required-check strictness must be a boolean.")
    if not classic and "do_not_enforce_on_create" in parameters:
        require(type(parameters["do_not_enforce_on_create"]) is bool, "Invalid check creation policy.")
    key, app_key = ("checks", "app_id") if classic else ("required_status_checks", "integration_id")
    checks = parameters.get(key, []) if classic else parameters.get(key)
    require(isinstance(checks, list), "Invalid required-check list.")
    identities = set()
    for check in checks:
        require(isinstance(check, dict) and clean_string(check.get("context")), "Invalid check context.")
        app = check.get(app_key)
        require(app is None or type(app) is int and (app > 0 or classic and app == -1), "Invalid check integration.")
        identity = (check["context"], app)
        require(identity not in identities, "Duplicate required check.")
        identities.add(identity)
    if classic:
        contexts = parameters.get("contexts", [])
        require(isinstance(contexts, list) and all(clean_string(c) for c in contexts), "Invalid classic check contexts.")
    return checks


def normalized_rule(rule):
    require(isinstance(rule, dict) and clean_string(rule.get("type")), "Invalid ruleset rule.")
    result = deepcopy(rule)
    if "parameters" in result:
        require(isinstance(result["parameters"], dict), "Invalid rule parameters.")
    if rule["type"] == "required_status_checks":
        checks = validate_checks(result.get("parameters"))
        result["parameters"]["required_status_checks"] = sorted(checks, key=canonical)
    if rule["type"] == "pull_request":
        parameters = result.get("parameters")
        require(isinstance(parameters, dict), "Invalid pull-request parameters.")
        for key, desired in PR_POLICY.items():
            if key not in parameters:
                continue
            value = parameters[key]
            if type(desired) is bool:
                require(type(value) is bool, "Invalid pull-request approval flag.")
            elif type(desired) is int:
                require(type(value) is int and value >= 0, "Invalid pull-request approval count.")
            else:
                require(
                    isinstance(value, list) and bool(value) and
                    all(v in ("merge", "squash", "rebase") for v in value) and len(set(value)) == len(value),
                    "Invalid pull-request merge methods.",
                )
    return result


def normalized_ruleset(value):
    require(isinstance(value, dict), "Invalid ruleset object.")
    require(type(value.get("id")) is int and value["id"] > 0, "Invalid ruleset ID.")
    for key in ("name", "source_type", "source", "target", "enforcement"):
        require(clean_string(value.get(key)), "Missing ruleset identity or policy fields.")
    require(isinstance(value.get("rules"), list), "Missing full ruleset rules.")
    result = {key: deepcopy(item) for key, item in value.items() if key not in READ_ONLY_RULESET}
    result.update({key: value[key] for key in ("id", "source", "source_type")})
    result["rules"] = sorted([normalized_rule(rule) for rule in value["rules"]], key=lambda rule: rule["type"])
    types = [rule["type"] for rule in result["rules"]]
    require(len(types) == len(set(types)), "Duplicate rule type in a ruleset.")
    if "bypass_actors" in value:
        actors = value["bypass_actors"]
        require(isinstance(actors, list), "Invalid bypass actors.")
        for actor in actors:
            require(
                isinstance(actor, dict) and clean_string(actor.get("actor_type")) and
                clean_string(actor.get("bypass_mode")) and
                (actor.get("actor_id") is None or type(actor["actor_id"]) is int and actor["actor_id"] > 0),
                "Invalid bypass actor.",
            )
        result["bypass_actors"] = sorted(deepcopy(actors), key=canonical)
    return result


def read_state(api, repo):
    root = f"repos/{repo}"
    metadata = api.request("GET", root)
    require(isinstance(metadata, dict), "Invalid repository metadata.")
    require(str(metadata.get("full_name", "")).lower() == repo.lower(), "Repository identity changed.")
    require(isinstance(metadata.get("permissions"), dict) and metadata["permissions"].get("admin") is True,
            "The gh session must have repository administration access to inspect all protection.")
    branch = metadata.get("default_branch")
    require(valid_branch(branch), "Invalid default branch.")
    settings = {}
    for key, desired in SETTINGS.items():
        require(type(metadata.get(key)) is type(desired), "Missing or invalid repository merge settings.")
        settings[key] = metadata[key]
    properties = api.request("GET", f"{root}/properties/values")
    require(isinstance(properties, list), "Invalid repository properties.")
    property_values = {}
    for item in properties:
        require(isinstance(item, dict) and clean_string(item.get("property_name")) and "value" in item,
                "Invalid repository property.")
        name = item["property_name"]
        require(name not in property_values, "Duplicate repository property.")
        property_values[name] = item["value"]
    main_policy = property_values.get("main_policy")
    require(main_policy is None or isinstance(main_policy, str), "Invalid main_policy property.")
    rulesets, ids = [], set()
    for summary in pages(api, f"{root}/rulesets?includes_parents=true"):
        require(isinstance(summary, dict) and type(summary.get("id")) is int and summary["id"] > 0,
                "Invalid ruleset summary.")
        ruleset_id = summary["id"]
        require(ruleset_id not in ids, "Duplicate ruleset ID.")
        ids.add(ruleset_id)
        full = normalized_ruleset(api.request("GET", f"{root}/rulesets/{ruleset_id}?includes_parents=true"))
        for key in ("id", "name", "source", "source_type", "enforcement"):
            require(key in summary and summary[key] == full[key], "Ruleset changed during discovery.")
        rulesets.append(full)
    effective, effective_ids = [], set()
    for rule in pages(api, f"{root}/rules/branches/{quote(branch, safe='')}"):
        rule = normalized_rule(rule)
        require(type(rule.get("ruleset_id")) is int and rule["ruleset_id"] in ids,
                "Effective branch rules reference an undiscovered ruleset.")
        source = next(item for item in rulesets if item["id"] == rule["ruleset_id"])
        require(rule.get("ruleset_source") == source["source"] and
                rule.get("ruleset_source_type") == source["source_type"], "Effective rule source changed.")
        identity = (rule["ruleset_id"], rule["type"])
        require(identity not in effective_ids, "Duplicate effective branch rule.")
        effective_ids.add(identity)
        effective.append(rule)
    classic = api.request("GET", f"{root}/branches/{quote(branch, safe='')}/protection", missing=True)
    require(classic is None or isinstance(classic, dict), "Invalid classic branch protection.")
    if classic:
        reviews = classic.get("required_pull_request_reviews")
        require(reviews is None or isinstance(reviews, dict), "Invalid classic review protection.")
        if classic.get("required_status_checks") is not None:
            validate_checks(classic["required_status_checks"], classic=True)
    return {
        "repo": metadata["full_name"], "default_branch": branch, "settings": settings,
        "main_policy": {"present": "main_policy" in property_values, "value": main_policy},
        "rulesets": sorted(rulesets, key=lambda item: item["id"]),
        "effective_rules": sorted(effective, key=canonical), "classic_protection": classic,
    }


def managed_ruleset(state):
    matches = [item for item in state["rulesets"] if item["name"] == MANAGED_NAME]
    require(len(matches) <= 1, "Multiple rulesets have the managed name.")
    if not matches:
        return None
    managed = matches[0]
    require(managed["source_type"] == "Repository" and managed["source"].lower() == state["repo"].lower(),
            "The named ruleset is inherited or belongs to another repository.")
    require(managed["target"] == "branch", "The named ruleset must target branches.")
    require(set(managed) <= WRITABLE_RULESET | {"id", "source", "source_type"},
            "The named ruleset has unsupported policy fields; review it separately.")
    require(WRITABLE_RULESET <= set(managed), "The named ruleset is missing policy fields.")
    conditions = managed["conditions"]
    require(isinstance(conditions, dict) and set(conditions) == {"ref_name"}, "Unsupported managed conditions.")
    refs = conditions["ref_name"]
    require(isinstance(refs, dict) and set(refs) == {"include", "exclude"}, "Unsupported managed ref conditions.")
    includes = refs["include"]
    allowed = {"~DEFAULT_BRANCH", f"refs/heads/{state['default_branch']}"}
    require(isinstance(includes, list) and bool(includes) and
            all(isinstance(ref, str) and ref in allowed for ref in includes) and
            len(set(includes)) == len(includes) and refs["exclude"] == [],
            "The named ruleset must target only the default branch, without exclusions.")
    return managed


def check_required_pin(checks, app_key):
    required = [check for check in checks if check["context"] == "Required"]
    require(len(required) <= 1, "Multiple Required checks in one protection rule.")
    for check in required:
        require(check.get(app_key) in (None, REQUIRED_APP) or app_key == "app_id" and check.get(app_key) == -1,
                "Required is pinned to a conflicting integration.")


@dataclass
class Plan:
    state: dict
    mode: str
    contexts: list
    actions: list
    require_up_to_date: bool = False

    def document(self):
        result = {
            "schema": 1, "repo": self.state["repo"], "mode": self.mode,
            "contexts": self.contexts, "state_hash": digest(self.state), "actions": self.actions,
            "require_up_to_date": self.require_up_to_date,
        }
        return {**result, "plan_hash": digest(result)}


def plan_policy(state, mode, contexts=(), require_up_to_date=False):
    require(mode in ("checked-pr", "direct"), "Unsupported delivery mode.")
    require(type(require_up_to_date) is bool, "Invalid up-to-date policy option.")
    require(not require_up_to_date or mode == "checked-pr", "--require-up-to-date requires checked-pr mode.")
    require(all(clean_string(context) and context == context.strip() for context in contexts), "Invalid requested check context.")
    require(len(contexts) == len(set(contexts)), "Duplicate requested check context.")
    require(mode != "direct" or not contexts, "direct does not accept required check contexts.")
    contexts = sorted(set(contexts) | ({"Required"} if mode == "checked-pr" else set()))
    managed = managed_ruleset(state)
    protected_rules = state["effective_rules"] + (managed["rules"] if managed else [])
    for rule in protected_rules:
        if rule["type"] == "required_status_checks":
            check_required_pin(validate_checks(rule["parameters"]), "integration_id")
    classic = state["classic_protection"] or {}
    if classic.get("required_status_checks") is not None:
        check_required_pin(validate_checks(classic["required_status_checks"], classic=True), "app_id")
    if mode == "direct":
        require(not any(rule["type"] in ("pull_request", "required_status_checks") for rule in protected_rules)
                and classic.get("required_pull_request_reviews") is None
                and classic.get("required_status_checks") is None,
                "direct cannot replace existing PR or check protection; review that policy separately.")
    if managed:
        payload = {key: deepcopy(managed[key]) for key in WRITABLE_RULESET}
    else:
        payload = {
            "name": MANAGED_NAME, "target": "branch", "enforcement": "active", "bypass_actors": [],
            "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}}, "rules": [],
        }
    payload["enforcement"] = "active"
    rules = {rule["type"]: rule for rule in payload["rules"]}
    for kind in ("deletion", "non_fast_forward"):
        rules.setdefault(kind, {"type": kind})
    if mode == "checked-pr":
        reviews = rules.setdefault("pull_request", {"type": "pull_request", "parameters": {}})
        reviews["parameters"].update(deepcopy(PR_POLICY))
        check_parameters = rules.setdefault("required_status_checks", {
            "type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": False, "do_not_enforce_on_create": False,
                "required_status_checks": [],
            },
        })["parameters"]
        if require_up_to_date:
            check_parameters["strict_required_status_checks_policy"] = True
        checks = check_parameters["required_status_checks"]
        for check in checks:
            if check["context"] == "Required":
                check["integration_id"] = REQUIRED_APP
        present = {check["context"] for check in checks}
        for context in contexts:
            if context not in present:
                checks.append({"context": context, **({"integration_id": REQUIRED_APP} if context == "Required" else {})})
    payload["rules"] = sorted([normalized_rule(rule) for rule in rules.values()], key=lambda rule: rule["type"])
    root = f"repos/{state['repo']}"
    actions = []
    if not managed:
        actions.append({"method": "POST", "path": f"{root}/rulesets", "body": payload})
    elif payload != {key: managed[key] for key in WRITABLE_RULESET}:
        actions.append({"method": "PUT", "path": f"{root}/rulesets/{managed['id']}", "body": payload})
    delta = {key: value for key, value in SETTINGS.items() if state["settings"][key] != value}
    if delta:
        actions.append({"method": "PATCH", "path": root, "body": delta})
    if state["main_policy"]["value"] != mode:
        actions.append({"method": "PATCH", "path": f"{root}/properties/values", "body": {
            "properties": [{"property_name": "main_policy", "value": mode}],
        }})
    return Plan(deepcopy(state), mode, contexts, actions, require_up_to_date)


def contains(actual, wanted):
    if isinstance(wanted, dict):
        return isinstance(actual, dict) and all(key in actual and contains(actual[key], value) for key, value in wanted.items())
    if isinstance(wanted, list):
        return isinstance(actual, list) and len(actual) == len(wanted) and all(contains(a, w) for a, w in zip(actual, wanted))
    return type(actual) is type(wanted) and actual == wanted


def advance_state(state, action, response):
    state = deepcopy(state)
    root = f"repos/{state['repo']}"
    if action["path"] == root:
        state["settings"].update(action["body"])
    elif action["path"] == f"{root}/properties/values":
        state["main_policy"] = {"present": True, "value": action["body"]["properties"][0]["value"]}
    else:
        updated = normalized_ruleset(response)
        original = managed_ruleset(state)
        require(updated["source_type"] == "Repository" and updated["source"] == state["repo"], "Unexpected written ruleset source.")
        require(contains(updated, action["body"]), "Written ruleset differs from the planned payload.")
        require(updated["id"] == original["id"] if original else
                all(updated["id"] != item["id"] for item in state["rulesets"]), "Unexpected written ruleset ID.")
        state["rulesets"] = sorted(
            [item for item in state["rulesets"] if item["id"] != updated["id"]] + [updated], key=lambda item: item["id"],
        )
        managed_ruleset(state)
        state["effective_rules"] = sorted(
            [rule for rule in state["effective_rules"] if rule["ruleset_id"] != updated["id"]] + [
                {**rule, "ruleset_id": updated["id"], "ruleset_source": updated["source"], "ruleset_source_type": "Repository"}
                for rule in updated["rules"]
            ], key=canonical,
        )
    return state


def execute_plan(api, plan, expected_hash):
    require(expected_hash == plan.document()["plan_hash"], "Plan hash changed; inspect a fresh dry-run.")
    expected = plan.state
    completed = 0
    try:
        current = read_state(api, expected["repo"])
        require(current == expected, "Policy changed after planning; inspect a fresh dry-run.")
        for action in plan.actions:
            response = api.request(action["method"], action["path"], action["body"])
            completed += 1
            expected = advance_state(expected, action, response)
            current = read_state(api, expected["repo"])
            require(current == expected, "Policy changed during application; inspect a fresh dry-run.")
        require(not plan_policy(current, plan.mode, plan.contexts, plan.require_up_to_date).actions,
                "Applied policy did not converge.")
    except PolicyError as error:
        raise PolicyError(f"{error} Completed writes: {completed}; an unsuccessful request may still have applied.") from error
    return {**plan.document(), "result": "applied" if completed else "already compliant", "completed_writes": completed}


def main(argv=None, api=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo")
    parser.add_argument("--mode", required=True, choices=["checked-pr", "direct"])
    parser.add_argument("--context", action="append", default=[])
    parser.add_argument("--require-up-to-date", action="store_true",
                        help="explicitly require strict checks in the managed ruleset (checked-pr only)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--expect-plan", help="plan_hash from a reviewed dry-run; required when applying")
    args = parser.parse_args(argv)
    try:
        repo = repository_name(args.repo)
        require(args.dry_run or args.expect_plan is not None, "Apply requires --expect-plan from a dry-run.")
        require(args.expect_plan is None or re.fullmatch(r"[0-9a-f]{64}", args.expect_plan), "Invalid plan hash.")
        api = api or GitHub()
        plan = plan_policy(read_state(api, repo), args.mode, args.context, args.require_up_to_date)
        result = plan.document() if args.dry_run else execute_plan(api, plan, args.expect_plan)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except PolicyError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
