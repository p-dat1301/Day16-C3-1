# Phân công dự án Agent Arena cho nhóm 5 người

## 1. Mục tiêu chung

Hoàn thiện middleware harness để Agent Arena hoạt động end-to-end với model thật, không chỉ đạt test bằng `MockModel`.

Luồng cần bảo đảm:

```text
Brief tiếng Việt
  -> ReActAgent
  -> model ACTION
  -> search / fetch_doc / calc
  -> evidence
  -> model FINAL
  -> middleware hậu kiểm
  -> submit
  -> trace + scorer
```

Sản phẩm hoàn thành phải:

- Tạo report JSON hợp lệ gồm `answer`, `claims`, `citations`, `abstain`.
- Chỉ giữ claim có bằng chứng đã quan sát.
- Trỏ citation đến đúng tài liệu đã fetch.
- Abstain khi không đủ bằng chứng.
- Chống prompt injection và không làm lộ canary.
- Retry tool result lỗi, truncated hoặc degraded.
- Không vượt tool-call budget và luôn dành lượt cho `submit`.
- Giữ trace hợp lệ.
- Chạy được với OpenAI-compatible endpoint thật.
- Không hard-code public briefs, document ID hoặc `Doc.tags`.

## 2. Ranh giới source code

### Được phép thay đổi

- `harness/layers/`
- `harness/middleware.py` và `harness/agent.py` khi Integration Lead xác nhận cần thiết.
- Test liên quan trong `tests/` theo ownership bên dưới.

### Không được thay đổi

- `arena/`: frozen runtime và scoring contract.
- `data/`: corpus và public briefs chuẩn của bài.
- `runs/`: output runtime, không phải source cần commit.

Không sửa frozen code để làm test pass hoặc tăng điểm giả tạo.

## 3. Thành viên 1 - Grounding & Critic Engineer

### Ownership

- `harness/layers/critic.py`

### Trách nhiệm

- Kiểm tra từng `claim["text"]` với `ctx.observed_text`.
- Xóa fabricated hoặc unsupported claims.
- Xử lý claim ghép từ nhiều nguồn nhưng không tồn tại nguyên văn trong evidence.
- Giữ nguyên text của claim hợp lệ; không tự diễn đạt lại.
- Xử lý absent briefs và contradiction briefs.
- Khi không còn claim có bằng chứng:
  - Đặt `abstain = true`.
  - Xóa claims và citations không hợp lệ.
- Đồng bộ citations với danh sách claims cuối cùng.

### Test phụ trách

- Claim bịa bị xóa.
- Claim đúng được giữ nguyên byte-for-byte.
- Claim ghép không hợp lệ bị loại hoặc xử lý đúng contract.
- Không đủ evidence dẫn đến abstain.
- Claims và citations luôn đồng bộ.
- Layer hoạt động khi chạy độc lập và trong full stack.

### Definition of Done

- Không còn TODO/no-op trong `critic.py`.
- Không fabricated claim trong submitted report.
- Test critic mới và test liên quan đều pass.
- Không sửa `arena/` hoặc shared runtime để né lỗi.

## 4. Thành viên 2 - Citation & Provenance Engineer

### Ownership

- `harness/layers/citation_checker.py`

### Trách nhiệm

- Kiểm tra claim khớp nguyên văn một dòng trong document.
- Re-attribute claim về đúng `doc_id` khi model cite sai tài liệu.
- Chỉ sửa `claim["doc_id"]`; không rewrite `claim["text"]`.
- Chỉ chấp nhận document đã được fetch và xuất hiện đầy đủ trong observed evidence.
- Không chấp nhận substring được tạo bằng cách nối nhiều dòng.
- Rebuild `report["citations"]` từ claims còn hợp lệ.
- Bảo đảm provenance giữa raw model output, evidence đã retrieve và submitted report.

### Test phụ trách

- Claim đúng text nhưng sai `doc_id` được sửa.
- Claim trỏ document chưa fetch không được chấp nhận.
- Claim nối qua nhiều dòng bị từ chối.
- Truncated document không được coi là fully observed.
- Citation list không chứa ID thừa hoặc sai.
- Layer hoạt động độc lập và trong full stack.

### Definition of Done

- Không còn TODO/no-op trong `citation_checker.py`.
- Mọi claim hợp lệ trỏ đúng document đã quan sát.
- Không có mutation trái phép lên claim text.
- Test provenance và scorer liên quan đều pass.

## 5. Thành viên 3 - Reliability & Budget Engineer

### Ownership

- `harness/layers/retry.py`
- `harness/layers/budget_policy.py`

Hai layer dùng chung `ctx.tools.calls`, retry attempts và submit reserve nên thuộc cùng một owner.

### Trách nhiệm Retry

- Retry khi `result.ok == false`.
- Retry khi result có dấu hiệu timeout, truncate, noise hoặc degraded content dù `ok == true`.
- Giữ nguyên tool name và arguments giữa các lần thử.
- Không vượt `DEFAULT_MAX_ATTEMPTS`.
- Không retry nếu lượt tiếp theo chiếm slot dành cho `submit`.
- Ghi attempts vào `ctx.state` để theo dõi.
- Sau lần cuối, trả result cuối cho model; không nuốt lỗi hoặc tạo evidence giả.

### Trách nhiệm Budget

- Tính `submit` vào tổng tool-call budget.
- Dành đúng số call reserve cho `submit`.
- Chèn nudge chứa `FINALIZE_SENTINEL` khi agent phải chốt FINAL.
- Chặn tool call bằng `ToolResult` ổn định thay vì raise exception làm chết run.
- Không mutate message history tại chỗ.
- Không nén hoặc xóa evidence context vì sẽ phá provenance.

### Test phụ trách

- Tool error rồi success.
- Truncate/noise với `ok == true` vẫn được retry.
- Retry dừng tại max attempts.
- Retry dừng trước submit reserve.
- Tool calls không vượt `max_tool_calls`.
- Agent vẫn tạo FINAL khi tool bị budget layer chặn.
- Kết hợp retry + budget không tạo vòng lặp hoặc vượt budget.

### Definition of Done

- Không còn TODO/no-op trong `retry.py` và `budget_policy.py`.
- Không run nào vượt tool budget sau khi tính `submit`.
- Retry cải thiện flaky runs nhưng không phá trace.
- Test middleware và runner liên quan đều pass.

## 6. Thành viên 4 - Prompt Injection & Safety Engineer

### Ownership

- `harness/layers/injection_guard.py`

### Trách nhiệm

- Loại hostile block từ `BLOCK_START` đến `BLOCK_END` tại tool boundary.
- Xử lý marker mở nhưng thiếu marker đóng do result bị truncate.
- Xử lý nhiều hostile blocks trong cùng một result.
- Thay hostile content bằng `PLACEHOLDER` ổn định.
- Giữ evidence bình thường ngoài hostile blocks.
- Quét `INJECTION_CANARY` khỏi `report["answer"]` trước submit.
- Không sửa `claim["text"]`, vì mutation sẽ phá provenance.
- Không dựa vào `Doc.tags`; tags không đáng tin trong scored runtime.

### Test phụ trách

- Một hostile block đầy đủ.
- Nhiều hostile blocks.
- Block thiếu closing marker.
- Canary xuất hiện trong answer.
- Evidence bình thường ngoài block vẫn được giữ.
- Không canary leak trong submitted report theo scorer contract.
- Layer hoạt động độc lập và trong full stack.

### Definition of Done

- Không còn TODO/no-op trong `injection_guard.py`.
- Không hostile instruction nào đi nguyên vẹn vào model observation.
- Không canary leak trong report cuối.
- Test injection, middleware và model liên quan đều pass.

## 7. Thành viên 5 - Integration, Real-Model & QA Lead

### Ownership độc quyền

- `harness/middleware.py`
- `harness/agent.py`
- `scripts/run_practice.py`
- Integration test coordination trong:
  - `tests/test_middleware.py`
  - `tests/test_runner.py`
  - `tests/test_trace.py`

Integration Lead không nên kiêm thêm critic hoặc citation layer vì khối lượng tích hợp cuối kỳ cao.

### Trách nhiệm

- Bảo vệ middleware stack order:

```text
injection_guard
critic
citation_checker
budget_policy
retry
```

- Kiểm tra middleware semantics:
  - Before hooks chạy xuôi.
  - Wrap hooks lồng nhau, layer đầu nằm ngoài cùng.
  - After hooks chạy ngược.
- Không để contributor khác thêm workaround vào `agent.py` hoặc `middleware.py`.
- Giữ `MAX_STEPS >= 40`.
- Kiểm tra ACTION/FINAL parser, report normalization và fallback abstention.
- Bảo đảm mọi run gọi `submit` và tạo trace hợp lệ.
- Chạy full stack, leave-one-out, flaky seeds và trace gate.
- Thiết lập và chạy smoke test với OpenAI-compatible endpoint thật.
- Xác nhận real-model path dùng đúng system prompt và environment variables.
- Review diff để bảo đảm không sửa `arena/`, không hard-code public data.
- Quản lý merge conflict ở shared tests và runtime files.

### Test phụ trách

- Full test suite.
- Full middleware stack.
- Leave-one-out từng layer.
- Flaky runs trên nhiều seed.
- No-FINAL fallback.
- Trace conformance gate.
- Real endpoint smoke test.
- So sánh baseline không layer với full stack.

### Definition of Done

- Tất cả quality gates pass.
- Full stack cải thiện rõ so với baseline.
- Không layer nào chỉ hoạt động nhờ MockModel-specific behavior.
- Có bằng chứng smoke run với model endpoint thật.
- Không có thay đổi ngoài phạm vi đã thống nhất.

## 8. Quy tắc phối hợp

### File ownership

- Mỗi người chỉ sửa file mình sở hữu.
- Mọi thay đổi `harness/agent.py`, `harness/middleware.py` hoặc `scripts/run_practice.py` phải qua Integration Lead.
- Không để nhiều người cùng thêm test vào cuối một shared file mà không chia class/function trước.

### Invariant giữa Critic và Citation Checker

- Claim text chỉ được giữ nguyên hoặc xóa theo contract.
- Citation Checker chỉ sửa `doc_id`.
- Critic quyết định claim có evidence hay không.
- Citations phải rebuild từ claims cuối cùng.
- Không layer nào tự tạo claim mới ngoài output đã có provenance từ model.

### Invariant giữa Retry và Budget

- Retry phải tự kiểm tra budget trước mỗi attempt.
- Budget phải dành call cuối cho `submit`.
- Tool bị chặn phải trả result ổn định; không raise làm chết agent.
- Retry không được retry result do chính budget layer chủ động chặn.

### Review chéo

- Thành viên 1 review logic của Thành viên 2.
- Thành viên 2 review logic của Thành viên 1.
- Thành viên 3 review interaction retry/budget với Integration Lead.
- Thành viên 4 review toàn bộ đường đi của tool content đến report.
- Thành viên 5 review integration, trace và phạm vi diff của tất cả thành viên.

## 9. Thứ tự triển khai

1. Cả nhóm đọc:
   - `README.md`
   - `phases/README.md`
   - `harness/middleware.py`
   - `harness/agent.py`
   - `arena/scorer.py`
   - `arena/tools.py`
   - `arena/corpus.py`
2. Thành viên 1-4 viết acceptance tests cho layer của mình trước.
3. Thành viên 1-4 triển khai song song trên file ownership riêng.
4. Thành viên 1 và 2 xác nhận invariant claim/citation.
5. Thành viên 3 xác nhận retry reserve và budget behavior.
6. Thành viên 4 xác nhận injection không đi vào observation/report.
7. Thành viên 5 tích hợp full stack.
8. Chạy mock baseline và full-stack comparison.
9. Chạy full verification và flaky seed matrix.
10. Chạy smoke test với model endpoint thật.
11. Chỉ sign-off khi toàn bộ Definition of Done đạt.

## 10. Quality gates

### Test và verification

```bash
python3 -m pytest -q
python3 scripts/verify.py
python3 scripts/verify.py --full
```

### Practice baseline và full stack

```bash
python3 scripts/run_practice.py --layers none
python3 scripts/run_practice.py --layers all
python3 scripts/run_practice.py --no-flaky
python3 scripts/run_practice.py --strict
```

### Real-model smoke test

```bash
export ARENA_API_KEY=...
export ARENA_BASE_URL=https://<host>/v1
export ARENA_MODEL=<model>
python3 scripts/run_practice.py --model real --strict
```

MockModel chỉ dùng cho test deterministic và baseline. Mock score hoặc test xanh không đủ để sign-off real-model readiness.

## 11. Definition of Done toàn dự án

Dự án hoàn thành khi:

- Năm layer không còn TODO/no-op.
- Full test suite pass.
- `scripts/verify.py --full` pass.
- Full-stack practice tốt hơn baseline.
- Leave-one-out chứng minh từng layer tạo giá trị.
- Không fabricated claim.
- Citation trỏ đúng document đã fetch.
- Không canary leak.
- Không vượt tool-call budget.
- Trace gate pass trên mọi run.
- Real-model smoke test thành công trên nhiều brief.
- Không hard-code public briefs, document ID hoặc `Doc.tags`.
- Không sửa frozen `arena/` hoặc dữ liệu chuẩn để làm test pass.
