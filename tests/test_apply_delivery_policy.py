"""Synthetic policy and transport tests; these never contact GitHub."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import subprocess
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, quote, urlsplit

from helpers import load_script


policy = load_script("apply-delivery-policy")
REPO = "hraness/policy-example"
ROOT = f"repos/{REPO}"


def ruleset(identifier=101, name=policy.MANAGED_NAME, strict=True):
    return {
        "id": identifier, "name": name, "target": "branch", "enforcement": "active",
        "source_type": "Repository", "source": REPO,
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
        "node_id": "synthetic-node", "current_user_can_bypass": "never", "_links": {},
        "bypass_actors": [
            {"actor_id": None, "actor_type": "OrganizationAdmin", "bypass_mode": "always"},
            {"actor_id": 71, "actor_type": "Team", "bypass_mode": "pull_request"},
        ],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {"type": "deletion"}, {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": {
                **deepcopy(policy.PR_POLICY), "required_approving_review_count": 2,
                "require_extra_approval_for_unattributed_changes": True,
                "allowed_merge_methods": ["merge", "squash", "rebase"],
                "required_reviewers": [],
                "dismissal_restriction": {"enabled": False, "allowed_actors": []},
                "future_review_setting": {"enabled": True},
            }},
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": strict,
                "do_not_enforce_on_create": True,
                "future_check_setting": {"enabled": True},
                "required_status_checks": [
                    {"context": "Required"},
                    {"context": "preview/example", "integration_id": 12345, "future_field": "kept"},
                    {"context": "external/admission"},
                ],
            }},
            {"type": "required_signatures"},
            {"type": "future_policy", "parameters": {"nested": ["preserve", {"value": 3}]}},
        ],
    }


def rule_of(value, kind):
    return next(rule for rule in value["rules"] if rule["type"] == kind)


class FakeGitHub:
    """Small in-memory REST fixture, including independent policy changes."""

    def __init__(self, managed=True):
        self.metadata = {
            "full_name": REPO, "default_branch": "main", "permissions": {"admin": True},
            **deepcopy(policy.SETTINGS), "allow_auto_merge": False,
            "allow_merge_commit": True, "allow_rebase_merge": True,
        }
        self.properties = [{"property_name": "unrelated", "value": "preserved"}]
        self.rulesets = [ruleset()] if managed else []
        self.classic = None
        self.calls = []
        self.before_request = None
        self.after_write = None
        self.response_filter = None

    @property
    def writes(self):
        return [call for call in self.calls if call[0] != "GET"]

    def effective_rules(self):
        result = []
        for item in self.rulesets:
            refs = item.get("conditions", {}).get("ref_name", {}).get("include", [])
            if item["target"] != "branch" or item["enforcement"] != "active":
                continue
            if not any(ref in ("~DEFAULT_BRANCH", "~ALL", f"refs/heads/{self.metadata['default_branch']}") for ref in refs):
                continue
            for rule in item["rules"]:
                result.append({**deepcopy(rule), "ruleset_id": item["id"],
                               "ruleset_source": item["source"], "ruleset_source_type": item["source_type"]})
        return result

    def request(self, method, path, body=None, missing=False):
        self.calls.append((method, path, deepcopy(body)))
        if self.before_request:
            self.before_request(self, method, path)
        url = urlsplit(path)
        endpoint = url.path
        query = parse_qs(url.query)
        page = int(query.get("page", [1])[0])
        size = int(query.get("per_page", [100])[0])
        branch = quote(self.metadata["default_branch"], safe="")
        if method == "GET":
            if endpoint == ROOT:
                value = self.metadata
            elif endpoint == f"{ROOT}/properties/values":
                value = self.properties
            elif endpoint == f"{ROOT}/rulesets":
                value = [{key: item[key] for key in ("id", "name", "source", "source_type", "enforcement")}
                         for item in self.rulesets][(page - 1) * size:page * size]
            elif endpoint.startswith(f"{ROOT}/rulesets/"):
                value = next(item for item in self.rulesets if item["id"] == int(endpoint.rsplit("/", 1)[-1]))
            elif endpoint == f"{ROOT}/rules/branches/{branch}":
                value = self.effective_rules()[(page - 1) * size:page * size]
            elif endpoint == f"{ROOT}/branches/{branch}/protection":
                assert missing
                value = self.classic
            else:
                raise AssertionError(f"Unexpected GET: {path}")
            return deepcopy(value)
        if method == "PATCH" and endpoint == ROOT:
            self.metadata.update(deepcopy(body))
            value = self.metadata
        elif method == "PATCH" and endpoint == f"{ROOT}/properties/values":
            changed = {item["property_name"] for item in body["properties"]}
            self.properties = [item for item in self.properties if item["property_name"] not in changed] + deepcopy(body["properties"])
            value = None
        elif method == "PUT" and endpoint.startswith(f"{ROOT}/rulesets/"):
            identifier = int(endpoint.rsplit("/", 1)[-1])
            value = next(item for item in self.rulesets if item["id"] == identifier)
            value.update(deepcopy(body))
        elif method == "POST" and endpoint == f"{ROOT}/rulesets":
            value = {**deepcopy(body), "id": 999, "source": REPO, "source_type": "Repository"}
            for rule in value["rules"]:
                if rule["type"] == "pull_request":
                    rule["parameters"]["required_reviewers"] = []
            self.rulesets.append(value)
        else:
            raise AssertionError(f"Unexpected mutation: {method} {path}")
        response = deepcopy(value)
        if self.after_write:
            self.after_write(self, method, path)
        return self.response_filter(response) if self.response_filter else response


class PolicyTests(unittest.TestCase):
    def plan(self, api, mode="checked-pr", contexts=(), require_up_to_date=False):
        return policy.plan_policy(policy.read_state(api, REPO), mode, contexts, require_up_to_date)

    def test_up_to_date_opt_in_only_strengthens_managed_strictness(self):
        for existing_strict in (False, True):
            with self.subTest(existing_strict=existing_strict):
                api = FakeGitHub()
                api.rulesets = [ruleset(strict=existing_strict), ruleset(102, "Other policy", strict=False)]
                api.classic = {"required_status_checks": {"strict": False, "contexts": ["external"]}}
                preserved = deepcopy((api.rulesets[1], api.classic, api.rulesets[0]["bypass_actors"]))
                default = self.plan(api)
                opted_in = self.plan(api, require_up_to_date=True)
                expected_actions = deepcopy(default.actions)
                default_checks = rule_of(expected_actions[0]["body"], "required_status_checks")["parameters"]
                self.assertIs(default_checks["strict_required_status_checks_policy"], existing_strict)
                default_checks["strict_required_status_checks_policy"] = True
                self.assertEqual(opted_in.actions, expected_actions)
                policy.execute_plan(api, opted_in, opted_in.document()["plan_hash"])
                self.assertEqual((api.rulesets[1], api.classic), preserved[:2])
                self.assertCountEqual(api.rulesets[0]["bypass_actors"], preserved[2])
                self.assertEqual(self.plan(api).actions, [])
                self.assertEqual(self.plan(api, require_up_to_date=True).actions, [])

    def test_up_to_date_opt_in_creates_strict_check_rule_with_required_pin(self):
        for managed in (False, True):
            with self.subTest(managed=managed):
                api = FakeGitHub(managed)
                if managed:
                    api.rulesets[0]["rules"] = [rule for rule in api.rulesets[0]["rules"] if rule["type"] != "required_status_checks"]
                plan = self.plan(api, require_up_to_date=True)
                checks = rule_of(plan.actions[0]["body"], "required_status_checks")["parameters"]
                self.assertTrue(checks["strict_required_status_checks_policy"])
                self.assertEqual(checks["required_status_checks"], [{"context": "Required", "integration_id": 15368}])
                policy.execute_plan(api, plan, plan.document()["plan_hash"])
                self.assertEqual(self.plan(api, require_up_to_date=True).actions, [])

    def test_up_to_date_option_is_bound_even_when_payload_is_already_strict(self):
        api = FakeGitHub()
        default = self.plan(api)
        opted_in = self.plan(api, require_up_to_date=True)
        self.assertEqual(default.actions, opted_in.actions)
        self.assertFalse(default.document()["require_up_to_date"])
        self.assertTrue(opted_in.document()["require_up_to_date"])
        self.assertNotEqual(default.document()["plan_hash"], opted_in.document()["plan_hash"])
        with self.assertRaisesRegex(policy.PolicyError, "Plan hash changed"):
            policy.execute_plan(api, opted_in, default.document()["plan_hash"])
        self.assertEqual(api.writes, [])

    def test_up_to_date_cli_opt_in_and_direct_rejection(self):
        api = FakeGitHub()
        api.rulesets = [ruleset(strict=False)]
        output = io.StringIO()
        with redirect_stdout(output):
            result = policy.main(["policy-example", "--mode", "checked-pr", "--require-up-to-date", "--dry-run"], api=api)
        self.assertEqual(result, 0)
        document = json.loads(output.getvalue())
        self.assertTrue(document["require_up_to_date"])
        self.assertTrue(rule_of(document["actions"][0]["body"], "required_status_checks")["parameters"]["strict_required_status_checks_policy"])
        for direct_api in (FakeGitHub(False), FakeGitHub(True)):
            with self.assertRaisesRegex(policy.PolicyError, "requires checked-pr"):
                self.plan(direct_api, "direct", require_up_to_date=True)
            with redirect_stderr(io.StringIO()):
                result = policy.main(["policy-example", "--mode", "direct", "--require-up-to-date", "--dry-run"], api=direct_api)
            self.assertEqual(result, 1)
            self.assertEqual(direct_api.writes, [])
        self.assertEqual(api.writes, [])

    def test_preserves_opaque_rules_parameters_actors_checks_and_strictness(self):
        for strict in (False, True):
            with self.subTest(strict=strict):
                api = FakeGitHub()
                original = ruleset(strict=strict)
                api.rulesets = [original]
                plan = self.plan(api, contexts=["additional/check"])
                payload = plan.actions[0]["body"]
                self.assertEqual(api.rulesets, [original])
                self.assertCountEqual(payload["bypass_actors"], original["bypass_actors"])
                self.assertEqual(payload["conditions"], original["conditions"])
                for kind in ("required_signatures", "future_policy"):
                    self.assertEqual(rule_of(payload, kind), rule_of(original, kind))
                reviews = rule_of(payload, "pull_request")["parameters"]
                for key, desired in policy.PR_POLICY.items():
                    self.assertEqual(reviews[key], desired)
                self.assertEqual(reviews["future_review_setting"], {"enabled": True})
                self.assertEqual(reviews["dismissal_restriction"], {"enabled": False, "allowed_actors": []})
                checks = rule_of(payload, "required_status_checks")["parameters"]
                self.assertIs(checks["strict_required_status_checks_policy"], strict)
                self.assertTrue(checks["do_not_enforce_on_create"])
                self.assertEqual(checks["future_check_setting"], {"enabled": True})
                entries = {entry["context"]: entry for entry in checks["required_status_checks"]}
                self.assertEqual(entries["Required"], {"context": "Required", "integration_id": 15368})
                self.assertEqual(entries["preview/example"], {"context": "preview/example", "integration_id": 12345, "future_field": "kept"})
                self.assertEqual(entries["external/admission"], {"context": "external/admission"})
                self.assertEqual(entries["additional/check"], {"context": "additional/check"})
                self.assertEqual(plan.actions[1]["body"], {
                    "allow_auto_merge": True, "allow_merge_commit": False, "allow_rebase_merge": False,
                })
                self.assertEqual(api.writes, [])

    def test_missing_required_is_always_added_with_integration_pin(self):
        for existing_checks in (False, True):
            with self.subTest(existing_checks=existing_checks):
                api = FakeGitHub()
                if existing_checks:
                    rule_of(api.rulesets[0], "required_status_checks")["parameters"]["required_status_checks"].pop(0)
                else:
                    api.rulesets[0]["rules"] = [r for r in api.rulesets[0]["rules"] if r["type"] != "required_status_checks"]
                checks = rule_of(self.plan(api).actions[0]["body"], "required_status_checks")["parameters"]
                self.assertIn({"context": "Required", "integration_id": 15368}, checks["required_status_checks"])
                self.assertIs(checks["strict_required_status_checks_policy"], existing_checks)

    def test_null_or_existing_required_pin_is_narrowed_or_preserved(self):
        for integration in (None, 15368):
            with self.subTest(integration=integration):
                api = FakeGitHub()
                checks = rule_of(api.rulesets[0], "required_status_checks")["parameters"]["required_status_checks"]
                checks[0]["integration_id"] = integration
                output = rule_of(self.plan(api).actions[0]["body"], "required_status_checks")["parameters"]
                self.assertIn({"context": "Required", "integration_id": 15368}, output["required_status_checks"])

    def test_other_rulesets_classic_and_environments_receive_no_writes(self):
        api = FakeGitHub()
        other = ruleset(102, "Other branch policy")
        inherited = ruleset(103, "Organization policy")
        inherited.update(source_type="Organization", source="hraness")
        tag = ruleset(104, "Release tags")
        tag.update(target="tag", conditions={"ref_name": {"include": ["refs/tags/v*"], "exclude": []}})
        api.rulesets.extend([other, inherited, tag])
        api.classic = {"required_pull_request_reviews": {"required_approving_review_count": 3},
                       "required_status_checks": {"strict": True, "contexts": ["Required"],
                                                  "checks": [{"context": "Required", "app_id": 15368}]}}
        unchanged = deepcopy((api.rulesets[1:], api.classic))
        plan = self.plan(api)
        policy.execute_plan(api, plan, plan.document()["plan_hash"])
        self.assertEqual((api.rulesets[1:], api.classic), unchanged)
        self.assertEqual({method for method, _path, _body in api.writes}, {"PUT", "PATCH"})
        self.assertTrue(all("environment" not in path for _method, path, _body in api.calls))
        self.assertEqual(api.properties[0], {"property_name": "unrelated", "value": "preserved"})

    def test_create_and_update_converge_and_apply_again_without_writes(self):
        for managed in (False, True):
            with self.subTest(managed=managed):
                api = FakeGitHub(managed)
                plan = self.plan(api)
                result = policy.execute_plan(api, plan, plan.document()["plan_hash"])
                self.assertEqual(result["completed_writes"], 3)
                again = self.plan(api)
                self.assertEqual(again.actions, [])
                writes = len(api.writes)
                self.assertEqual(policy.execute_plan(api, again, again.document()["plan_hash"])["result"], "already compliant")
                self.assertEqual(len(api.writes), writes)

    def test_direct_refuses_managed_other_inherited_and_classic_pr_or_check_rules(self):
        for protection in ("managed", "other", "inherited", "classic_pr", "classic_checks"):
            with self.subTest(protection=protection):
                api = FakeGitHub(protection == "managed")
                if protection in ("other", "inherited"):
                    item = ruleset(111, "Separate policy")
                    if protection == "inherited":
                        item.update(source_type="Organization", source="hraness")
                    api.rulesets.append(item)
                elif protection == "classic_pr":
                    api.classic = {"required_pull_request_reviews": {"required_approving_review_count": 0}}
                elif protection == "classic_checks":
                    api.classic = {"required_status_checks": {"strict": False, "contexts": ["external"]}}
                with self.assertRaisesRegex(policy.PolicyError, "direct cannot"):
                    self.plan(api, "direct")
                self.assertEqual(api.writes, [])

    def test_direct_on_unprotected_branch_converges_without_pr_or_checks(self):
        api = FakeGitHub(False)
        plan = self.plan(api, "direct")
        self.assertEqual({r["type"] for r in plan.actions[0]["body"]["rules"]}, {"deletion", "non_fast_forward"})
        policy.execute_plan(api, plan, plan.document()["plan_hash"])
        self.assertEqual(self.plan(api, "direct").actions, [])

    def test_named_collision_and_unsupported_scope_fail_before_any_write(self):
        cases = ["duplicate", "inherited", "tag", "wildcard", "all", "mixed", "excluded", "unknown_field"]
        for case in cases:
            with self.subTest(case=case):
                api = FakeGitHub()
                item = api.rulesets[0]
                refs = item["conditions"]["ref_name"]
                if case == "duplicate":
                    api.rulesets.append(ruleset(102))
                elif case == "inherited":
                    item.update(source_type="Organization", source="hraness")
                elif case == "tag":
                    item["target"] = "tag"
                elif case == "wildcard":
                    refs["include"] = ["refs/heads/*"]
                elif case == "all":
                    refs["include"] = ["~ALL"]
                elif case == "mixed":
                    refs["include"].append("refs/heads/release")
                elif case == "excluded":
                    refs["exclude"] = ["refs/heads/main"]
                else:
                    item["future_top_level_policy"] = True
                with self.assertRaises(policy.PolicyError):
                    self.plan(api)
                self.assertEqual(api.writes, [])

    def test_conflicting_required_pins_in_every_effective_protection_fail(self):
        for source in ("managed", "other", "inherited", "classic"):
            with self.subTest(source=source):
                api = FakeGitHub()
                if source == "classic":
                    api.classic = {"required_status_checks": {"strict": True, "checks": [{"context": "Required", "app_id": 99999}]}}
                else:
                    item = api.rulesets[0] if source == "managed" else ruleset(102, "Other protection")
                    if source != "managed":
                        api.rulesets.append(item)
                    if source == "inherited":
                        item.update(source_type="Organization", source="hraness")
                    rule_of(item, "required_status_checks")["parameters"]["required_status_checks"][0]["integration_id"] = 99999
                with self.assertRaisesRegex(policy.PolicyError, "conflicting integration"):
                    self.plan(api)
                self.assertEqual(api.writes, [])

    def test_ambiguous_and_malformed_checks_fail(self):
        for case in ("duplicate_required", "strict_string", "missing_strict", "boolean_pin", "bad_context", "duplicate_rule", "bad_review"):
            with self.subTest(case=case):
                api = FakeGitHub()
                checks = rule_of(api.rulesets[0], "required_status_checks")["parameters"]
                if case == "duplicate_required":
                    checks["required_status_checks"].append({"context": "Required", "integration_id": 15368})
                elif case == "strict_string":
                    checks["strict_required_status_checks_policy"] = "true"
                elif case == "missing_strict":
                    del checks["strict_required_status_checks_policy"]
                elif case == "boolean_pin":
                    checks["required_status_checks"][0]["integration_id"] = True
                elif case == "bad_context":
                    checks["required_status_checks"][0]["context"] = ""
                elif case == "duplicate_rule":
                    api.rulesets[0]["rules"].append({"type": "deletion"})
                else:
                    rule_of(api.rulesets[0], "pull_request")["parameters"]["require_last_push_approval"] = "false"
                with self.assertRaises(policy.PolicyError):
                    self.plan(api)
                self.assertEqual(api.writes, [])

    def test_plan_is_deterministic_and_dry_run_shows_exact_payloads(self):
        api = FakeGitHub()
        first = self.plan(api, contexts=["check/b", "check/a"]).document()
        api.rulesets[0]["rules"].reverse()
        api.rulesets[0]["bypass_actors"].reverse()
        api.rulesets[0]["updated_at"] = "2026-02-02T00:00:00Z"
        self.assertEqual(self.plan(api, contexts=["check/a", "check/b"]).document(), first)
        stream = io.StringIO()
        with redirect_stdout(stream):
            result = policy.main(["policy-example", "--mode", "checked-pr", "--dry-run"], api=api)
        self.assertEqual(result, 0)
        document = json.loads(stream.getvalue())
        self.assertEqual(document["actions"], self.plan(api).actions)
        self.assertEqual(len(document["plan_hash"]), 64)
        self.assertNotIn("classic_protection", document)
        self.assertEqual(api.writes, [])

    def test_stale_hash_or_stale_state_never_writes(self):
        for change in ("hash", "strict", "actor", "classic", "default", "new_policy"):
            with self.subTest(change=change):
                api = FakeGitHub()
                if change == "strict":
                    rule_of(api.rulesets[0], "required_status_checks")["parameters"]["strict_required_status_checks_policy"] = False
                plan = self.plan(api)
                expected = plan.document()["plan_hash"]
                if change == "hash":
                    expected = "0" * 64
                elif change == "strict":
                    rule_of(api.rulesets[0], "required_status_checks")["parameters"]["strict_required_status_checks_policy"] = True
                elif change == "actor":
                    api.rulesets[0]["bypass_actors"] = []
                elif change == "classic":
                    api.classic = {"required_pull_request_reviews": {"required_approving_review_count": 3}}
                elif change == "default":
                    api.metadata["default_branch"] = "release/next"
                else:
                    api.rulesets.append(ruleset(102, "New protection"))
                with self.assertRaisesRegex(policy.PolicyError, "changed"):
                    policy.execute_plan(api, plan, expected)
                self.assertEqual(api.writes, [])

    def test_concurrent_strengthening_after_first_write_stops_remaining_writes(self):
        api = FakeGitHub()
        plan = self.plan(api)

        def strengthen(client, _method, _path):
            rule_of(client.rulesets[0], "pull_request")["parameters"]["required_approving_review_count"] = 5

        api.after_write = strengthen
        with self.assertRaisesRegex(policy.PolicyError, "Completed writes: 1"):
            policy.execute_plan(api, plan, plan.document()["plan_hash"])
        self.assertEqual(len(api.writes), 1)
        self.assertEqual(rule_of(api.rulesets[0], "pull_request")["parameters"]["required_approving_review_count"], 5)
        self.assertFalse(api.metadata["allow_auto_merge"])

    def test_late_discovery_error_prevents_all_writes(self):
        api = FakeGitHub()

        def fail(_client, method, path):
            if method == "GET" and path.endswith("/protection"):
                raise policy.PolicyError("GitHub GET failed (HTTP 403); no automatic retry.")

        api.before_request = fail
        errors = io.StringIO()
        with redirect_stderr(errors):
            result = policy.main(["policy-example", "--mode", "checked-pr", "--expect-plan", "0" * 64], api=api)
        self.assertEqual(result, 1)
        self.assertIn("403", errors.getvalue())
        self.assertEqual(api.writes, [])

    def test_write_error_stops_without_retry_or_rollback(self):
        api = FakeGitHub()
        plan = self.plan(api)

        def fail(_client, method, path):
            if method == "PATCH" and path == ROOT:
                raise policy.PolicyError("GitHub PATCH failed (HTTP 503); no automatic retry.")

        api.before_request = fail
        with self.assertRaisesRegex(policy.PolicyError, "Completed writes: 1"):
            policy.execute_plan(api, plan, plan.document()["plan_hash"])
        self.assertEqual([call[0] for call in api.writes], ["PUT", "PATCH"])

    def test_bad_write_response_stops_further_mutations(self):
        api = FakeGitHub()
        plan = self.plan(api)
        api.response_filter = lambda response: {**response, "rules": []}
        with self.assertRaisesRegex(policy.PolicyError, "differs from the planned payload"):
            policy.execute_plan(api, plan, plan.document()["plan_hash"])
        self.assertEqual(len(api.writes), 1)

    def test_pagination_is_scoped_and_branch_names_are_encoded(self):
        api = FakeGitHub(False)
        api.metadata["default_branch"] = "release/next#1"
        api.rulesets = [ruleset(identifier, f"Example policy {identifier}") for identifier in range(1, 103)]
        state = policy.read_state(api, REPO)
        self.assertEqual(len(state["rulesets"]), 102)
        paths = [path for _method, path, _body in api.calls]
        self.assertIn(f"{ROOT}/rulesets?includes_parents=true&per_page=100&page=2", paths)
        self.assertTrue(any("rules/branches/release%2Fnext%231?per_page=100&page=2" in path for path in paths))
        self.assertIn(f"{ROOT}/branches/release%2Fnext%231/protection", paths)
        self.assertTrue(all(path.startswith(f"{ROOT}/") or path == ROOT for path in paths))

    def test_input_errors_and_missing_apply_hash_do_not_write(self):
        for repo in ("../other", "outside/policy-example", "a/b/c", "bad?name", "bad%2fname", "", ".."):
            with self.subTest(repo=repo), self.assertRaises(policy.PolicyError):
                policy.repository_name(repo)
        self.assertEqual(policy.repository_name("policy-example"), REPO)
        self.assertEqual(policy.repository_name(REPO), REPO)
        self.assertEqual(policy.repository_name(".github"), "hraness/.github")
        for args in (["policy-example", "--mode", "checked-pr"],
                     ["policy-example", "--mode", "checked-pr", "--expect-plan", "bad"]):
            api = FakeGitHub()
            with redirect_stderr(io.StringIO()):
                self.assertEqual(policy.main(args, api=api), 1)
            self.assertEqual(api.calls, [])
        for mode, contexts in (("direct", ["Required"]), ("checked-pr", ["duplicate", "duplicate"]), ("checked-pr", [" bad "])):
            with self.assertRaises(policy.PolicyError):
                self.plan(FakeGitHub(), mode, contexts)

    def test_malformed_identity_properties_or_authority_stop_discovery(self):
        for case in ("branch", "owner", "admin", "duplicate_property", "setting"):
            with self.subTest(case=case):
                api = FakeGitHub()
                if case == "branch":
                    api.metadata["default_branch"] = "../other"
                elif case == "owner":
                    api.metadata["full_name"] = "example/other"
                elif case == "admin":
                    api.metadata["permissions"]["admin"] = False
                elif case == "duplicate_property":
                    api.properties.append(deepcopy(api.properties[0]))
                else:
                    api.metadata["allow_merge_commit"] = "true"
                with self.assertRaises(policy.PolicyError):
                    self.plan(api)
                self.assertEqual(api.writes, [])

    def test_import_has_no_api_or_cli_side_effects(self):
        with patch.object(subprocess, "run") as run, redirect_stdout(io.StringIO()) as output:
            load_script("apply-delivery-policy")
        run.assert_not_called()
        self.assertEqual(output.getvalue(), "")


class TransportTests(unittest.TestCase):
    def response(self, status=200, body="[]", returncode=0, stderr=""):
        return subprocess.CompletedProcess([], returncode, f"HTTP/2.0 {status} Status\r\nContent-Type: application/json\r\n\r\n{body}", stderr)

    def test_only_actual_404_is_optional_and_errors_do_not_disclose_output(self):
        sensitive = "SYNTHETIC_SENSITIVE_VALUE"
        with patch.object(policy.subprocess, "run", return_value=self.response(404, sensitive, 1)):
            self.assertIsNone(policy.GitHub().request("GET", "repos/example/example/protection", missing=True))
        for result in (self.response(403, sensitive, 1, "404 " + sensitive),
                       subprocess.CompletedProcess([], 1, sensitive, "404 " + sensitive)):
            with patch.object(policy.subprocess, "run", return_value=result):
                with self.assertRaises(policy.PolicyError) as caught:
                    policy.GitHub().request("GET", "repos/example/example/protection", missing=True)
            self.assertNotIn(sensitive, str(caught.exception))

    def test_transport_uses_existing_gh_and_exact_json_input(self):
        with patch.object(policy.subprocess, "run", return_value=self.response(body='{"ok":true}')) as run:
            body = {"allowed_merge_methods": ["squash"]}
            self.assertEqual(policy.GitHub().request("PUT", "repos/example/example/rulesets/1", body), {"ok": True})
        command = run.call_args.args[0]
        self.assertEqual(command[0], "/opt/homebrew/bin/gh")
        self.assertIn("--include", command)
        self.assertEqual(json.loads(run.call_args.kwargs["input"]), body)

    def test_invalid_duplicate_or_nonfinite_json_is_rejected(self):
        for body in ("invalid", '{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}'):
            with self.subTest(body=body), patch.object(policy.subprocess, "run", return_value=self.response(body=body)):
                with self.assertRaises(policy.PolicyError):
                    policy.GitHub().request("GET", "repos/example/example")

    def test_repeated_or_excessive_pages_fail_closed(self):
        class Repeating:
            def request(self, *_args):
                return list(range(100))

        with self.assertRaisesRegex(policy.PolicyError, "repeated"):
            policy.pages(Repeating(), "repos/example/example/rulesets")
        with patch.object(policy, "MAX_PAGES", 1), self.assertRaisesRegex(policy.PolicyError, "limit"):
            policy.pages(Repeating(), "repos/example/example/rulesets")


if __name__ == "__main__":
    unittest.main()
