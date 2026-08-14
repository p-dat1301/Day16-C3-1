# Role 5 Readiness Report

## Kết luận

Ngày nghiệm thu: 2026-08-14

Candidate được kiểm tra: `origin/main` tại commit `0b6cf54` (`fix: defer unsupported real-model finals`)

**Trạng thái: READY cho offline/public evaluation; CONDITIONAL READY cho real-model evaluation.**

Toàn bộ Role 1-4 đã được tích hợp. Test, frozen-file verification, trace gate, FINAL parsing, tool budget và public practice đều đạt. Điều kiện còn thiếu duy nhất cho real-model sign-off là environment chưa export `ARENA_API_KEY`, `ARENA_BASE_URL`, `ARENA_MODEL`.

## Phạm vi Role 5

Role 5 thực hiện nghiệm thu và viết report, không sửa logic của Role 1-4:

- Xác nhận commit tích hợp mới nhất trên `origin/main`.
- Chạy full test suite và focused acceptance tests.
- Chạy `scripts/verify.py --full`.
- Chạy full stack strict ở chế độ mặc định và `--no-flaky`.
- Chạy năm leave-one-out stacks.
- Kiểm tra trace gate, FINAL output và tool-call budget từ JSON artifacts.
- Kiểm tra readiness của real-model environment mà không đọc hoặc in secret.
- Xác nhận frozen files không bị thay đổi.

## Branch và commit đã nghiệm thu

Các thay đổi Role được tích hợp trên `origin/main`:

| Commit | Nội dung |
| --- | --- |
| `4b4ef8e` | Integrate Role 2 citation provenance |
| `f57f2fc` | Integrate Role 3 reliability and budget |
| `0c850c4` | Integrate Role 4 injection safety |
| `24ec3d2` | Integrate Role 1 grounding and protect local env |
| `2531e2f` | Make integrated Arena runnable on Windows |
| `7ebc082` | Support OpenRouter Luna configuration |
| `8b18666` | Enable real-model retrieval prompt by default |
| `0b6cf54` | Defer unsupported real-model finals |

Role 5 report được đẩy trực tiếp lên `main` theo yêu cầu; code candidate được đo trực tiếp từ detached worktree của `origin/main` tại commit nêu trên.

## Quality Gates

| Gate | Kết quả | Bằng chứng |
| --- | --- | --- |
| Full pytest | PASS | `808 passed in 33.33s` |
| Verify full | PASS | `22/22 mục đạt` |
| Focused layer tests | PASS | `49 passed in 1.78s` |
| Frozen files | PASS | 5 frozen files nguyên vẹn |
| Public briefs | PASS | 9/9 briefs hoàn tất |
| Trace gate | PASS | 9/9 ở mọi matrix run |
| FINAL parsing | PASS | 0 run thiếu FINAL |
| Full-stack tool budget | PASS | tối đa 8 calls, gồm `submit` |
| Source worktree | PASS | candidate detached worktree sạch |
| Real-model smoke | NOT RUN | thiếu environment variables |

### Lệnh chính

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify.py --full
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_citation_checker.py tests/test_critic.py \
  tests/test_injection_guard.py tests/test_reliability_budget.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_practice.py \
  --quiet --strict --out /tmp/opencode/role5-final-full.json
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_practice.py \
  --quiet --strict --no-flaky \
  --out /tmp/opencode/role5-final-stable.json
```

## Full-stack kết quả

| Run | Mean score | Trace gate | No FINAL | Max tool calls |
| --- | ---: | ---: | ---: | ---: |
| Full stack strict | 81.7116 | 9/9 | 0 | 8 |
| Full stack strict `--no-flaky` | 81.7116 | 9/9 | 0 | 8 |

Kết quả khớp mốc full-stack công khai `81.71` mô tả trong README. Public score chỉ dùng để kiểm tra behavior; không được xem là dự báo private score.

Artifacts được ghi ngoài repo:

- `/tmp/opencode/role5-final-full.json`
- `/tmp/opencode/role5-final-stable.json`
- `/tmp/opencode/role5-final-retry-only.json`
- `/tmp/opencode/role5-final-without-injection.json`
- `/tmp/opencode/role5-final-without-critic.json`
- `/tmp/opencode/role5-final-without-citation.json`
- `/tmp/opencode/role5-final-without-budget.json`
- `/tmp/opencode/role5-final-without-retry.json`

## Leave-one-out matrix

| Stack | Mean | Delta so với full | Max tools | Kết luận |
| --- | ---: | ---: | ---: | --- |
| Full stack | 81.7116 | 0.0000 | 8 | Reference |
| Không `injection_guard` | 72.6430 | -9.0686 | 8 | Safety layer có giá trị |
| Không `critic` | 69.7712 | -11.9404 | 8 | Grounding/honesty layer có giá trị |
| Không `citation_checker` | 52.6164 | -29.0952 | 8 | Citation layer có giá trị lớn nhất |
| Không `budget_policy` | 74.9258 | -6.7858 | 11 | Budget layer chặn vượt budget |
| Không `retry` | 81.7116 | 0.0000 | 8 | `--no-flaky` không tạo retry signal |

`retry` không tạo delta trong no-flaky matrix theo thiết kế. Focused acceptance tests xác nhận retry xử lý degraded/error result, dừng tại `max_attempts` và giữ phần ngân sách dành cho `submit`. Retry-only run mặc định đạt `24.7072`, gate 9/9.

## Regression blockers cũ

Ba blocker từ review trước đã có implementation/test tương ứng trên candidate:

1. Citation provenance: `tests/test_citation_checker.py` kiểm tra re-attribution và observed-document contract.
2. Critic line matching: `tests/test_critic.py` kiểm tra fabrication, contradiction và claim provenance.
3. Retry/budget boundary: `tests/test_reliability_budget.py` kiểm tra max attempts, degraded result và submit reserve.
4. Injection cleanup: `tests/test_injection_guard.py` kiểm tra complete/multiple/unclosed hostile blocks và canary handling.

Bốn focused files chạy cùng nhau: `49 passed`.

## Middleware wiring

Stack tại `scripts/run_practice.py`:

```text
injection_guard
critic
citation_checker
budget_policy
retry
```

`after_agent` chạy ngược nên thứ tự thực tế là `retry`, `budget_policy`, `citation_checker`, `critic`, `injection_guard`. Injection guard vì vậy là final safety sweep trước `tools.submit`.

## Real-model readiness

Environment hiện tại:

```text
ARENA_API_KEY=MISSING
ARENA_BASE_URL=MISSING
ARENA_MODEL=MISSING
```

Role 5 không chạy HTTP smoke khi thiếu credential/config và không thay bằng fake transport để tuyên bố real-model pass.

Sau khi cấu hình environment, chạy:

```bash
set -a
source .env
set +a
python3 scripts/run_practice.py --model real --strict \
  --out /tmp/opencode/role5-real-model.json
```

Real-model sign-off yêu cầu:

- Process exit code 0.
- 9/9 trace gates pass.
- 0 run thiếu FINAL.
- Không canary leak.
- Không vượt tool budget.
- Không xuất hiện credential trong logs/artifact.

## Hạn chế

- Runtime validation dùng Python `3.11.7`; README ghi yêu cầu Python 3.12+, dù `verify.py` chấp nhận và toàn suite pass trên 3.11.7.
- Không có private briefs; public mean không dự báo private score.
- Không có real-provider evidence do environment variables chưa được export.
- `scripts/leaderboard.py` cảnh báo public practice không có gradient so với blind-paste estimate; đây là giới hạn của public benchmark, không phải test failure.

## Release Decision

```text
Candidate commit: 0b6cf54
Unit/integration tests: PASS (808)
Focused layer tests: PASS (49)
Verify: PASS (22/22)
Frozen files: PASS
Trace gate: PASS (9/9)
FINAL outputs: PASS (9/9)
Full-stack behavior: PASS (81.7116)
Tool budget: PASS (max 8)
Leave-one-out value: PASS for 4 measured layers
Retry behavior tests: PASS
Real-model smoke: NOT RUN
Offline/public release: READY
Real-model release: CONDITIONAL READY
```

Bước còn lại: export đủ ba biến môi trường và chạy real-model smoke trên đúng endpoint sẽ dùng khi chấm.
