# Contents

- `profile/README.md` is the public Hraness organization profile.
- `DOCUMENTATION_GUIDELINES.md` is the shared reader-need, evidence, and review contract for every Hraness documentation surface.
- `README_GUIDELINES.md` is the shared information architecture and review contract for Hraness repository READMEs and their website projections.
- `STYLE.md` defines the public and reader-facing prose contract.
- `CONTRIBUTING.md` provides default contributor guidance for repositories without their own.
- `.agents/skills/` contains portable repository orchestration skills.

# Guidelines

- Keep this repository public, self-contained, and free of private repository names, paths, credentials, provider operations, or publication mechanics.
- For every documentation surface, follow `DOCUMENTATION_GUIDELINES.md`: distinguish guided learning, task completion, factual reference, and explanation; keep each page or section focused on its reader's need, and link between forms. Verify prerequisites, capabilities, effects, and a complete path to the stated result.
- Treat `DOCUMENTATION_GUIDELINES.md` as the canonical cross-repository documentation framework. Adopt it explicitly in each affected repository's root guide and contribution path; this repository's `AGENTS.md` is not inherited across repositories.
- Treat `README_GUIDELINES.md` as the canonical cross-repository README framework. Change it when recurring evidence warrants a shared rule, then adopt the change deliberately in affected repositories.
- Follow `STYLE.md` for the organization profile and other public repository prose.
- Keep the organization profile short. Link to shared guidance instead of copying it into `profile/README.md`.

<!-- hra-local-efficiency:start -->
- Treat the user's request to change this repository as standing authorization for routine task-owned commits, pushes, pull requests, merges, releases, deployments, and production verification after the repository's required validation, review, identity, and rollout gates pass. Do not ask for another confirmation at each delivery step.
- Use the repository's documented delivery workflow and preserve every runtime-enforced approval, branch protection, environment rule, safety policy, and final gate. Ask for user input only when delivery needs a material product decision, missing credentials or authority, an irreversibly destructive action outside task scope, or resolution of a release failure that cannot be handled safely and autonomously.
- Prefer short-lived repository workload identities such as OIDC trusted publishing, GitHub Apps, and narrowly scoped machine identities. Do not add long-lived personal tokens, weaken two-factor authentication, or bypass provider controls to eliminate an interactive prompt. Batch unavoidable human-gated production promotions into intentional stable releases while agents publish validated prerelease or beta channels through workload identities when the repository supports them.
- Preserve useful reasoning fan-out, but avoid unnecessary checkout fan-out. Prefer subagents in the current task for bounded research, review, diagnosis, and focused checks when they can safely share one working tree; create a separate task or worktree only for independently deliverable divergent edits, an isolated verification tree, or a different execution environment.
- Give each expensive focused validation command and external wait one owner. The integration owner reviews that evidence and runs the repository-required aggregate or final gate once after convergence. Reuse evidence only for the exact Git tree, command, lockfiles, toolchain, relevant environment, and validity period, and never to skip a required final integration, merge, release, deployment, or production-verification gate.
- On Hraness development machines, use `$hra-local-efficiency` and the installed host scheduler for heavyweight top-level commands when available. Keep ordinary work in the compute lane; give authenticated browser/dev-server/Chromium work one `browser-auth` owner and Mac-only validation one `mac-native` owner.
- When a CI or policy gate scans complete Git history, check out the exact governed SHA and fetch only the fully qualified governed refs before scanning. Preserve the complete-history gate and reject unexpected refs instead of importing unrelated concurrent heads.
- At closeout, record applicable branch, PR, check, merge, release, deployment, and production evidence. Archive only conclusively finished tasks, never from silence alone, and reclaim only freshly revalidated clean merged worktrees through the guarded exact-path flow.
<!-- hra-local-efficiency:end -->
