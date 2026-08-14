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

## 8. Quy trình làm việc chi tiết cho 5 role

### 8.1. Quy trình chung của cả nhóm

Mọi role dùng cùng một chu trình để tránh code chạy riêng nhưng hỏng khi tích hợp:

1. Đọc contract và test liên quan trước khi sửa code.
2. Ghi lại baseline của phạm vi mình phụ trách.
3. Viết acceptance test thể hiện hành vi cần đạt.
4. Chạy test để xác nhận test mới thất bại đúng nguyên nhân.
5. Triển khai thay đổi nhỏ nhất trong file ownership.
6. Chạy unit test của layer.
7. Chạy integration test có layer liên quan.
8. Chạy practice với layer riêng.
9. Chạy practice cùng các layer phụ thuộc.
10. Tự review diff trước khi bàn giao.
11. Gửi Integration Lead bằng chứng test, lệnh chạy và rủi ro còn lại.
12. Chỉ đánh dấu hoàn tất sau khi Integration Lead xác nhận full-stack không regression.

Mẫu bàn giao bắt buộc cho mỗi role:

```text
Role:
Files changed:
Behavior implemented:
Tests added/updated:
Commands executed:
Results:
Known limitations:
Integration risks:
Reviewer:
```

Không dùng câu “test pass” chung chung. Phải ghi đúng lệnh và kết quả quan trọng.

### 8.2. Quy trình Role 1 - Grounding & Critic Engineer

#### Giai đoạn A - Hiểu contract

1. Đọc `harness/layers/critic.py` và toàn bộ docstring.
2. Đọc `AgentContext` trong `harness/agent.py` để hiểu:
   - `ctx.observed_text` được tạo thế nào.
   - Evidence nào model đã thực sự thấy.
   - Report đi vào `after_agent` có cấu trúc gì.
3. Đọc claim verdict trong `arena/scorer.py`.
4. Đọc test critic, scorer, absent và contradiction hiện có.
5. Chốt invariant với Role 2:
   - Không paraphrase claim.
   - Không thêm dấu câu.
   - Không lấy evidence trực tiếp từ corpus nếu model chưa quan sát.

#### Giai đoạn B - Khóa hành vi bằng test

Viết test theo thứ tự:

1. Claim nguyên văn có trong observed evidence được giữ.
2. Fabricated claim bị xóa.
3. Claim gần giống nhưng khác một ký tự bị loại.
4. Claim ghép từ hai dòng không được coi là evidence nguyên văn.
5. Report không còn claim thì `abstain = true`.
6. Citations được rebuild từ claims còn lại.
7. Input report không bị mutate ngoài phạm vi contract nếu test yêu cầu copy semantics.

Chạy test hẹp:

```bash
python3 -m pytest -q tests/test_layers_stubs.py
python3 -m pytest -q tests/test_scorer.py
```

#### Giai đoạn C - Triển khai

1. Tạo bản sao report/claims khi cần tránh side effect ngoài ý muốn.
2. Duyệt claims theo thứ tự model tạo.
3. Kiểm tra claim text trong evidence đã quan sát.
4. Giữ nguyên claim hợp lệ.
5. Loại claim không có evidence.
6. Rebuild citations.
7. Đặt abstain khi không còn claim.
8. Không thêm fallback claim hoặc text tự sinh.

#### Giai đoạn D - Tự kiểm tra và bàn giao

```bash
python3 scripts/run_practice.py \
  --layers critic \
  --entry critic-only \
  --out runs/critic-only.json

python3 scripts/selfeval.py --run runs/critic-only.json
```

Role 1 phải báo:

- Brief nào giảm fabricated claim.
- Brief nào chuyển sang abstain.
- Có claim hợp lệ nào bị xóa nhầm không.
- Có mutation nào lên `claim["text"]` không.
- Rủi ro cần Role 2 kiểm tra chéo.

Role 2 review diff của Role 1 trước khi tích hợp.

### 8.3. Quy trình Role 2 - Citation & Provenance Engineer

#### Giai đoạn A - Hiểu contract

1. Đọc `harness/layers/citation_checker.py`.
2. Đọc cấu trúc `Doc` và corpus access trong `arena/corpus.py`.
3. Đọc cách `observed_text` được cập nhật trong `harness/agent.py`.
4. Đọc scorer để hiểu one-line exact match và provenance verdict.
5. Chốt với Role 1 thứ tự xử lý claim/citation trong `after_agent`.

#### Giai đoạn B - Khóa hành vi bằng test

Viết test theo thứ tự:

1. Claim đúng và `doc_id` đúng được giữ nguyên.
2. Claim đúng nhưng `doc_id` sai được re-attribute.
3. Claim thuộc document chưa fetch không được re-attribute.
4. Claim nối qua hai dòng không được match.
5. Claim nằm trong truncated observation không được coi là fully observed.
6. Nhiều document chứa cùng text được xử lý deterministic.
7. Citations được rebuild không trùng lặp.
8. `claim["text"]` giữ nguyên byte-for-byte.

Chạy test hẹp:

```bash
python3 -m pytest -q tests/test_layers_stubs.py
python3 -m pytest -q tests/test_scorer.py
python3 -m pytest -q tests/test_runner.py
```

#### Giai đoạn C - Triển khai

1. Xác định document nào đã thực sự được quan sát đầy đủ.
2. Tách `Doc.body` theo dòng đúng semantics của scorer.
3. Với từng claim, kiểm tra document đang cite trước.
4. Nếu cite sai, tìm document đã quan sát có dòng khớp nguyên văn.
5. Chỉ thay `doc_id`.
6. Không sửa, chuẩn hóa hoặc thêm dấu câu vào claim text.
7. Rebuild citations theo thứ tự claims cuối.

#### Giai đoạn D - Tự kiểm tra và bàn giao

```bash
python3 scripts/run_practice.py \
  --layers citation_checker \
  --entry citation-only \
  --out runs/citation-only.json

python3 scripts/run_practice.py \
  --layers critic,citation_checker \
  --entry grounding-stack \
  --out runs/grounding-stack.json

python3 scripts/selfeval.py --run runs/grounding-stack.json
```

Role 2 phải báo:

- Số claim được re-attribute.
- Claim nào vẫn không tìm được document hợp lệ.
- Có document chưa fetch nào bị dùng nhầm không.
- Có `NOT_FROM_MODEL` mới phát sinh không.
- Interaction với Critic có thay đổi expected behavior không.

Role 1 review diff của Role 2 trước khi tích hợp.

### 8.4. Quy trình Role 3 - Reliability & Budget Engineer

#### Giai đoạn A - Hiểu contract

1. Đọc `harness/layers/retry.py` và `harness/layers/budget_policy.py`.
2. Đọc `arena/tools.py` để hiểu:
   - Khi nào `ok` là `false`.
   - Truncate/noise có thể vẫn trả `ok = true`.
   - `submit` được tính vào tool calls.
3. Đọc wrap ordering trong `harness/middleware.py`.
4. Đọc runner và brief budget trong `arena/runner.py`, `arena/briefs.py`.
5. Chốt với Role 5 result nào do budget chủ động chặn và không được retry.

#### Giai đoạn B - Khóa Retry bằng test

Viết test:

1. Success ngay lần đầu không retry.
2. Error rồi success.
3. Timeout rồi success.
4. Truncate/noise với `ok = true` vẫn retry.
5. Luôn degraded thì dừng tại max attempts.
6. Tool name và args giữ nguyên qua attempts.
7. Không retry khi chỉ còn submit reserve.
8. Attempts được lưu trong `ctx.state`.

#### Giai đoạn C - Khóa Budget bằng test

Viết test:

1. Dưới ngưỡng budget thì cho tool chạy.
2. Chạm ngưỡng reserve thì chặn tool.
3. `before_model` thêm nudge có `FINALIZE_SENTINEL`.
4. Message input không bị mutate tại chỗ.
5. Tool bị chặn trả `ToolResult` thay vì raise.
6. Submit vẫn còn một slot.
7. Retry không retry budget-blocked result.

Chạy test hẹp:

```bash
python3 -m pytest -q tests/test_middleware.py
python3 -m pytest -q tests/test_runner.py
python3 -m pytest -q tests/test_layers_stubs.py
```

#### Giai đoạn D - Triển khai và đo flaky behavior

1. Triển khai degraded-result detector trước.
2. Thêm retry loop có giới hạn attempts.
3. Kiểm tra budget trước mỗi attempt.
4. Ghi attempt state.
5. Triển khai budget threshold và submit reserve.
6. Thêm finalize nudge bằng list message mới.
7. Đánh dấu budget-blocked result đủ rõ để retry nhận biết.
8. Chạy retry riêng, budget riêng, rồi kết hợp.

```bash
python3 scripts/run_practice.py \
  --layers retry \
  --entry retry-only \
  --out runs/retry-only.json

python3 scripts/run_practice.py \
  --layers budget_policy \
  --entry budget-only \
  --out runs/budget-only.json

python3 scripts/run_practice.py \
  --layers budget_policy,retry \
  --entry reliability-stack \
  --out runs/reliability-stack.json
```

Role 3 phải báo:

- Attempts theo từng degraded scenario.
- Max tool calls quan sát được.
- Run nào không còn slot submit.
- Có budget-blocked result nào bị retry không.
- Flaky variance cải thiện thế nào trên nhiều seed.

Role 5 review interaction control flow trước khi nhận bàn giao.

### 8.5. Quy trình Role 4 - Prompt Injection & Safety Engineer

#### Giai đoạn A - Hiểu contract

1. Đọc `harness/layers/injection_guard.py`.
2. Đọc canary và hostile document format trong `arena/corpus.py`.
3. Đọc tool result flow trong `arena/tools.py` và `harness/agent.py`.
4. Đọc scorer safety để hiểu phạm vi quét canary.
5. Chốt với Role 1 rằng Injection Guard không rewrite claim text.

#### Giai đoạn B - Khóa hành vi bằng test

Viết test:

1. Không có marker thì giữ nguyên content.
2. Một hostile block đầy đủ bị thay bằng placeholder.
3. Nhiều hostile blocks đều bị loại.
4. Marker mở thiếu marker đóng thì cắt đến cuối.
5. Text bình thường trước và sau block được giữ.
6. Canary trong answer bị loại.
7. Claim text không bị sửa.
8. Sanitized result vẫn giữ kiểu và metadata cần thiết.

Chạy test hẹp:

```bash
python3 -m pytest -q tests/test_middleware.py
python3 -m pytest -q tests/test_model.py
python3 -m pytest -q tests/test_layers_stubs.py
```

#### Giai đoạn C - Triển khai

1. Viết hàm xử lý block theo marker, không dựa vào tags.
2. Lặp tới khi không còn hostile block.
3. Xử lý missing end marker bằng cách cắt đến cuối content.
4. Bọc tool call và sanitize result trước khi model thấy.
5. Trong `after_agent`, chỉ làm sạch answer theo contract.
6. Không sửa claims để tránh `NOT_FROM_MODEL`.

#### Giai đoạn D - Tự kiểm tra và bàn giao

```bash
python3 scripts/run_practice.py \
  --layers injection_guard \
  --entry injection-only \
  --out runs/injection-only.json

python3 scripts/run_practice.py \
  --layers injection_guard,critic,citation_checker \
  --entry safety-grounding \
  --out runs/safety-grounding.json

python3 scripts/selfeval.py --run runs/safety-grounding.json
```

Role 4 phải báo:

- Hostile block nào được loại.
- Có evidence hợp lệ nào bị mất không.
- Canary còn xuất hiện ở field nào không.
- Có claim text nào bị thay đổi không.
- Safety tăng có làm grounding giảm không.

Role 5 review toàn bộ đường đi từ tool result đến submitted report.

### 8.6. Quy trình Role 5 - Integration, Real-Model & QA Lead

#### Giai đoạn A - Chuẩn bị baseline

1. Đọc toàn bộ runtime flow và middleware contract.
2. Chạy test và verify trước khi nhận code.
3. Tạo baseline không layer.
4. Ghi lại điểm, trace status, no-FINAL briefs và tool calls.
5. Lập bảng theo dõi bàn giao của Role 1-4.

```bash
python3 -m pytest -q
python3 scripts/verify.py
python3 scripts/run_practice.py \
  --layers none \
  --entry baseline \
  --out runs/baseline.json
```

#### Giai đoạn B - Nhận bàn giao từng role

Với mỗi role:

1. Đọc diff, không chỉ đọc mô tả.
2. Xác nhận chỉ sửa file ownership và test đã thống nhất.
3. Chạy lại đúng lệnh người bàn giao cung cấp.
4. Kiểm tra test có thực sự khóa behavior, không chỉ test no-crash.
5. Chạy layer riêng.
6. Chạy cùng layer phụ thuộc.
7. Nếu fail, gửi lại reproduction chính xác cho cùng owner sửa.
8. Không tự sửa hộ logic layer trừ khi ownership được đổi rõ ràng.

#### Giai đoạn C - Integration matrix

Chạy tối thiểu:

```bash
python3 scripts/run_practice.py --layers critic
python3 scripts/run_practice.py --layers citation_checker
python3 scripts/run_practice.py --layers injection_guard
python3 scripts/run_practice.py --layers retry
python3 scripts/run_practice.py --layers budget_policy
python3 scripts/run_practice.py --layers critic,citation_checker
python3 scripts/run_practice.py --layers budget_policy,retry
python3 scripts/run_practice.py --layers injection_guard,critic,citation_checker
python3 scripts/run_practice.py
python3 scripts/run_practice.py --no-flaky
```

Lệnh không truyền `--layers` là full stack mặc định. Không dùng `--layers all` nếu CLI không định nghĩa giá trị `all`.

#### Giai đoạn D - Leave-one-out

Chạy full stack thiếu từng layer:

```bash
python3 scripts/run_practice.py \
  --layers injection_guard,critic,citation_checker,budget_policy

python3 scripts/run_practice.py \
  --layers injection_guard,critic,citation_checker,retry

python3 scripts/run_practice.py \
  --layers injection_guard,critic,budget_policy,retry

python3 scripts/run_practice.py \
  --layers injection_guard,citation_checker,budget_policy,retry

python3 scripts/run_practice.py \
  --layers critic,citation_checker,budget_policy,retry
```

Nếu bỏ một layer mà kết quả không đổi trên các scenario liên quan, yêu cầu owner chứng minh layer có tác dụng hoặc bổ sung test.

#### Giai đoạn E - Full verification

```bash
python3 -m pytest -q
python3 scripts/verify.py
python3 scripts/verify.py --full
python3 scripts/run_practice.py \
  --entry full-stack \
  --out runs/full-stack.json
python3 scripts/selfeval.py --run runs/full-stack.json
python3 scripts/leaderboard.py runs/baseline.json runs/full-stack.json
```

Role 5 kiểm tra:

- Không no-FINAL ngoài fallback được thiết kế.
- Trace gate pass.
- Không fabricated claim.
- Không wrong-document citation.
- Không canary leak.
- Tool calls nằm trong budget.
- Full stack tốt hơn baseline.
- Không regression khi tool không flaky.

#### Giai đoạn F - Real-model smoke test

Khi có credential thật:

```bash
export ARENA_API_KEY="..."
export ARENA_BASE_URL="https://<host>/v1"
export ARENA_MODEL="<model>"
python3 scripts/run_practice.py \
  --model real \
  --strict \
  --entry real-smoke \
  --out runs/real-smoke.json
```

Không commit credential hoặc runtime output chứa dữ liệu nhạy cảm.

Nếu thiếu endpoint hoặc credential, ghi rõ real-model path chưa được xác nhận. Không dùng fake transport hoặc MockModel để tuyên bố đã chạy thật.

#### Giai đoạn G - Release gate

Trước khi báo hoàn tất:

```bash
git status --short
git diff --stat
git diff --name-only
```

Xác nhận:

- Không sửa `arena/`.
- Không sửa `data/` để làm điểm đẹp.
- Không commit `runs/`.
- Không hard-code brief hoặc document ID.
- Không dùng `Doc.tags`.
- Không giảm `MAX_STEPS`.
- Không thay frozen parser.
- Không có middleware exception bị nuốt.
- Mọi role đã có reviewer và bằng chứng test.

Role 5 lập báo cáo sign-off cuối:

```text
Unit tests: PASS/FAIL
Verify: PASS/FAIL
Trace gate: PASS/FAIL
Full-stack practice: PASS/FAIL
Leave-one-out: PASS/FAIL
Real-model smoke: PASS/FAIL/NOT RUN
Frozen files unchanged: YES/NO
Known limitations:
Release decision: READY/NOT READY
```

## 9. Quy tắc phối hợp

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

## 10. Thứ tự triển khai

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

## 11. Quality gates

### Test và verification

```bash
python3 -m pytest -q
python3 scripts/verify.py
python3 scripts/verify.py --full
```

### Practice baseline và full stack

```bash
python3 scripts/run_practice.py --layers none
python3 scripts/run_practice.py
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

## 12. Definition of Done toàn dự án

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
