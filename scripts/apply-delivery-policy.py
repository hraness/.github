#!/usr/bin/env /usr/bin/python3
"""Apply the Hraness unattended-delivery baseline to one repository.

usage: scripts/apply-delivery-policy.py <repo> --mode checked-pr|direct [--context NAME ...] [--dry-run]

checked-pr: one branch ruleset "Protect main delivery" on the default branch:
  deletion + non_fast_forward blocked, pull_request required with 0 approvals and
  no thread-resolution/codeowner/last-push ceremony, required status checks (given
  contexts, non-strict so auto-merge never stalls behind main). Without --context the
  ruleset requires a pull request but no check, so auto-merge merges at once; rerun
  with the repository's `Required` context as soon as main produces it. Other
  rulesets that target only the default branch are removed as redundant once the new
  ruleset is in place, and their bypass actors carry over so deploy-key and admin
  automation keeps working. Classic branch protection is removed. Tag rulesets and
  rulesets for other branches are preserved.
direct: same ruleset but without pull_request / status-check rules.
Both: allow_auto_merge, delete_branch_on_merge, allow_update_branch, squash with
PR title/body; main_policy custom property set to the mode; environment reviewers
and wait timers removed.
GitHub Actions cannot be a ruleset bypass actor, so a repository whose workflows push
to main with GITHUB_TOKEN breaks under checked-pr; move those pushes to a GitHub App
or deploy key first.
"""
import json, subprocess, sys, argparse
GH="/opt/homebrew/bin/gh"; ORG="hraness"
def api(method, path, body=None, ok404=False):
    cmd=[GH,"api","-X",method,path,"-H","Accept: application/vnd.github+json"]
    if body is not None: cmd+=["--input","-"]
    r=subprocess.run(cmd,input=json.dumps(body) if body is not None else None,capture_output=True,text=True)
    if r.returncode!=0:
        if ok404 and "404" in r.stderr: return None
        raise SystemExit(f"{method} {path} failed: {r.stderr.strip()}\n{r.stdout[:500]}")
    return json.loads(r.stdout) if r.stdout.strip() else None
def covers(have, want):
    if isinstance(want, dict): return isinstance(have, dict) and all(covers(have.get(k), v) for k, v in want.items())
    if isinstance(want, list): return isinstance(have, list) and len(have)==len(want) and all(any(covers(h, w) for h in have) for w in want)
    return have==want
def actor(b):
    t=b.get("actor_type")
    return {"actor_id":1 if t=="OrganizationAdmin" else b.get("actor_id"),"actor_type":t,"bypass_mode":b.get("bypass_mode") or "always"}
ap=argparse.ArgumentParser(); ap.add_argument("repo"); ap.add_argument("--mode",required=True,choices=["checked-pr","direct"]); ap.add_argument("--context",action="append",default=[]); ap.add_argument("--dry-run",action="store_true")
a=ap.parse_args(); R=f"repos/{ORG}/{a.repo}"; summary={"repo":a.repo,"mode":a.mode,"actions":[]}
def act(msg,fn):
    summary["actions"].append(msg)
    if not a.dry_run: fn()
meta=api("GET",R); default=meta["default_branch"]
# 1. repository settings
want={"allow_auto_merge":True,"delete_branch_on_merge":True,"allow_update_branch":True,"allow_squash_merge":True,"squash_merge_commit_title":"PR_TITLE","squash_merge_commit_message":"PR_BODY"}
delta={k:v for k,v in want.items() if meta.get(k)!=v}
if delta: act(f"settings {delta}",lambda: api("PATCH",R,delta))
# 2. custom property
props={p["property_name"]:p["value"] for p in api("GET",f"{R}/properties/values")}
if props.get("main_policy")!=a.mode: act(f"main_policy {props.get('main_policy')} -> {a.mode}",lambda: api("PATCH",f"{R}/properties/values",{"properties":[{"property_name":"main_policy","value":a.mode}]}))
# 3. rulesets: collect the default-branch rulesets and their bypass actors
main_refs={"~DEFAULT_BRANCH",f"refs/heads/{default}"}
keep=None; redundant=[]; bypass=[]
for r in api("GET",f"{R}/rulesets") or []:
    if r.get("source_type")!="Repository": summary["actions"].append(f"note: org ruleset {r['name']} untouched"); continue
    full=api("GET",f"{R}/rulesets/{r['id']}")
    if full["target"]!="branch": continue
    inc=set((full.get("conditions") or {}).get("ref_name",{}).get("include",[]))
    if inc and inc<=main_refs:
        for b in full.get("bypass_actors") or []:
            if actor(b) not in bypass: bypass.append(actor(b))
        if keep is None and full["name"]=="Protect main delivery": keep=full
        else: redundant.append(full)
    elif inc & main_refs: summary["actions"].append(f"warning: ruleset {full['name']!r} spans main and other refs {sorted(inc)}; left in place")
rules=[{"type":"deletion"},{"type":"non_fast_forward"}]
if a.mode=="checked-pr":
    rules.append({"type":"pull_request","parameters":{"required_approving_review_count":0,"dismiss_stale_reviews_on_push":False,"require_code_owner_review":False,"require_last_push_approval":False,"required_review_thread_resolution":False,"allowed_merge_methods":["merge","squash","rebase"]}})
    if a.context: rules.append({"type":"required_status_checks","parameters":{"strict_required_status_checks_policy":False,"do_not_enforce_on_create":False,"required_status_checks":[{"context":c} for c in a.context]}})
    else: summary["actions"].append("warning: no required status check; auto-merge merges at once until Required is added")
want_rs={"name":"Protect main delivery","target":"branch","enforcement":"active","bypass_actors":bypass,"conditions":{"ref_name":{"include":["~DEFAULT_BRANCH"],"exclude":[]}},"rules":rules}
if keep is None: act(f"create 'Protect main delivery' contexts={a.context} bypass={[b['actor_type'] for b in bypass]}",lambda: api("POST",f"{R}/rulesets",want_rs))
elif not covers({**keep,"bypass_actors":[actor(b) for b in keep.get("bypass_actors") or []]},want_rs): act(f"update 'Protect main delivery' contexts={a.context} bypass={[b['actor_type'] for b in bypass]}",lambda: api("PUT",f"{R}/rulesets/{keep['id']}",want_rs))
for full in redundant: act(f"delete redundant main ruleset {full['name']!r} ({full['id']}) rules={[x['type'] for x in full.get('rules',[])]}",lambda rid=full["id"]: api("DELETE",f"{R}/rulesets/{rid}"))
# 4. classic branch protection, removed once the ruleset is in place
if api("GET",f"{R}/branches/{default}/protection",ok404=True): act("remove classic branch protection",lambda: api("DELETE",f"{R}/branches/{default}/protection"))
# 5. environments: strip reviewers / wait timers
envs=(api("GET",f"{R}/environments") or {}).get("environments",[])
for e in envs:
    if any(p["type"] in ("required_reviewers","wait_timer") for p in e.get("protection_rules",[])):
        body={"wait_timer":0,"reviewers":[],"prevent_self_review":False}
        dbp=e.get("deployment_branch_policy")
        if dbp: body["deployment_branch_policy"]={"protected_branches":dbp["protected_branches"],"custom_branch_policies":dbp["custom_branch_policies"]}
        act(f"environment {e['name']}: remove reviewers/wait timer",lambda n=e["name"],b=body: api("PUT",f"{R}/environments/{n}",b))
if not summary["actions"]: summary["actions"].append("already compliant")
print(json.dumps(summary,indent=1))
