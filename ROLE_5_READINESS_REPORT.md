# Role 5 Readiness Report

## Phạm vi

Ngày thực hiện: 2026-08-14

Role 5 đã kiểm tra baseline, frozen boundary, middleware wiring, integration matrix và khả năng smoke test model thật. Không sửa logic của `harness/layers/`.

## Công việc đã thực hiện

1. Kiểm tra worktree trước validation. Chỉ phát hiện `.omo/` untracked đã tồn tại; Role 5 không sửa source runtime hoặc frozen files.
2. Đọc và đối chiếu runtime flow:
   - `scripts/run_practice.py`
   - `harness/middleware.py`
   - `harness/agent.py`
   - `scripts/verify.py`
3. Xác nhận `STACK_ORDER` và onion semantics của sáu middleware hook.
4. Chạy toàn bộ test suite:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
```

5. Chạy verification đầy đủ, gồm frozen-file integrity, trace, provenance, deterministic execution, offline path và student-layer smoke:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify.py --full
```

6. Chạy baseline không layer, full stack và full stack không flaky; output ghi ngoài repo tại `/tmp/opencode/`.
7. Chạy integration matrix:
   - Năm layer riêng lẻ.
   - `critic,citation_checker`.
   - `budget_policy,retry`.
   - `injection_guard,critic,citation_checker`.
   - Năm leave-one-out stack.
8. So sánh mean score, trace gate, số FINAL và số tool call từ JSON output.
9. Kiểm tra readiness của real model bằng sự tồn tại của `ARENA_API_KEY`, `ARENA_BASE_URL`, `ARENA_MODEL`; không in hoặc lưu credential.
10. Tổng hợp blockers, bàn giao cần nhận và quyết định release.

## Chưa thực hiện

- Không sửa `critic.py`, `citation_checker.py`, `budget_policy.py`, `retry.py` hoặc `injection_guard.py`; các file này thuộc Role 1-4.
- Không chạy HTTP smoke test model thật vì environment chưa đủ credential/configuration.
- Không sign-off release vì full stack chưa cải thiện baseline và tool budget chưa được kiểm soát.

## Quality Gates

| Gate | Kết quả | Bằng chứng |
| --- | --- | --- |
| Test suite | PASS | `757 passed in 34.68s` |
| Verify full | PASS | `22/22 mục đạt (34.5s)` |
| Frozen files | PASS | `verify.py --full` xác nhận 5 file frozen nguyên vẹn |
| Public briefs | PASS | 9 briefs hợp lệ |
| Trace gate | PASS | 9/9 run ở baseline, full stack và matrix |
| No-FINAL | PASS | 0/9 run không có FINAL |
| Worktree source | PASS | Chỉ có `.omo/` untracked đã tồn tại; không có source diff từ Role 5 |

## Middleware Wiring

Stack được xác nhận tại `scripts/run_practice.py`:

```text
injection_guard
critic
citation_checker
budget_policy
retry
```

Semantics được xác nhận tại `harness/middleware.py`:

- `before_agent` và `before_model` chạy theo thứ tự stack.
- `wrap_model_call` và `wrap_tool_call` có layer đầu ngoài cùng.
- `after_model` và `after_agent` chạy ngược.
- Vì vậy `after_agent` xử lý theo thứ tự thực tế: `retry`, `budget_policy`, `citation_checker`, `critic`, `injection_guard`.
- `ReActAgent.run()` gọi `after_agent` trước `tools.submit`, sau đó ghi `agent_end`.

## Runtime Baseline

| Run | Mean score | Gate | No FINAL | Max tool calls |
| --- | ---: | --- | ---: | ---: |
| Không layer | 24.2747 | 9/9 | 0 | 12 |
| Full stack hiện tại | 24.2747 | 9/9 | 0 | 12 |
| Full stack `--no-flaky` | 24.7072 | 9/9 | 0 | 11 |

Artifacts chỉ nằm trong `/tmp/opencode/`:

- `/tmp/opencode/role5-baseline.json`
- `/tmp/opencode/role5-full-stack.json`
- `/tmp/opencode/role5-full-stack-stable.json`

## Integration Matrix

Các run đã thực hiện:

- Từng layer: `critic`, `citation_checker`, `injection_guard`, `retry`, `budget_policy`.
- Cặp phụ thuộc: `critic,citation_checker`; `budget_policy,retry`.
- Safety/grounding stack: `injection_guard,critic,citation_checker`.
- Leave-one-out đủ năm biến thể.

Kết quả: mọi run trong matrix có `mean_total = 24.2747`, `trace gate = 9/9`, `max_tool_calls = 12`.

## Blockers

### BLOCKER 1 - Năm layer chưa có hiệu lực

Full stack hiện bằng baseline. Matrix và leave-one-out không tạo khác biệt. Điều này khớp với trạng thái TODO/no-op trong:

- `harness/layers/critic.py`
- `harness/layers/citation_checker.py`
- `harness/layers/budget_policy.py`
- `harness/layers/retry.py`
- `harness/layers/injection_guard.py`

Hệ quả: Role 5 chưa thể xác nhận grounding, citation provenance, injection safety, retry hoặc budget control.

### BLOCKER 2 - Tool budget chưa được kiểm soát

Baseline và full stack đều quan sát `max_tool_calls = 12`, vượt budget public mặc định có `max_tool_calls = 8` gồm cả `submit`. Role 3 phải hoàn thiện `budget_policy.py` và phối hợp với `retry.py`.

### BLOCKER 3 - Model thật chưa thể smoke test

Thiếu ít nhất một biến môi trường trong bộ sau:

```text
ARENA_API_KEY
ARENA_BASE_URL
ARENA_MODEL
```

Không có smoke test HTTP thật. Không dùng `MockModel` hoặc fake transport để kết luận real-model readiness.

## Bàn giao cần nhận

| Owner | Bắt buộc trước integration lại |
| --- | --- |
| Role 1 | `critic.py`, acceptance tests fabricated/absent/contradiction, run critic-only |
| Role 2 | `citation_checker.py`, tests one-line/re-attribution/provenance, run citation-only và grounding stack |
| Role 3 | `retry.py`, `budget_policy.py`, tests degraded result + submit reserve, run reliability stack |
| Role 4 | `injection_guard.py`, tests hostile block/canary, run injection-only và safety-grounding stack |

Mỗi bàn giao phải gồm: files changed, behavior, tests, commands, results, limitations và integration risks.

## Release Decision

```text
Unit tests: PASS
Verify: PASS
Trace gate: PASS
Full-stack behavior: BLOCKED
Leave-one-out value: BLOCKED
Real-model smoke: NOT RUN
Frozen files unchanged: YES
Release decision: NOT READY
```

Role 5 tiếp tục khi nhận đủ bốn bàn giao hoặc khi Anh Đạt yêu cầu nhận một layer cụ thể.
