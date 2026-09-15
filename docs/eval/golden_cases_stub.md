# Golden cases V0

Canonical pack: [`eval/golden_cases_v0.json`](../../eval/golden_cases_v0.json) (48 cases).
Spec: [`docs/EVAL_SPEC_V0.md`](../EVAL_SPEC_V0.md).

IDs `golden-01` … `golden-48` are grouped by conflict label (8 each). Expected
enter/size/manage/exit values are left unset until research session IDs are
attached. The harness still enforces **sealed cutoff** (`timestamp < decision_ts`)
and **bans post-fill rationalization as enter-evidence**.

```bash
uv run alexrag eval-golden --pack eval/golden_cases_v0.json
```
