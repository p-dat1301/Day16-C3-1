"""`citation_checker` — Thành viên 2 (Citation & Provenance Engineer).

File riêng của Role 2 để không phải chen test vào cuối một shared file
(`tests/test_middleware.py`, `tests/test_runner.py`) mà Integration Lead
sở hữu — xem §9 "File ownership" trong `TEAM_ASSIGNMENTS.md`.

Không có doc_id, brief_id hay `Doc.tags` nào bị hard-code ở đây: mọi tài
liệu và mọi dòng dùng làm dữ liệu thử đều được ĐỌC RA TỪ CORPUS lúc
import, nên đổi seed corpus thì test hỏng ầm ĩ chứ không âm thầm chấm
theo một câu không còn tồn tại.

Hai tầng:

* §1-§7 chạy `after_agent` trực tiếp trên một `AgentContext` dựng tay.
  Đó là nơi khoá từng luật một: khớp một DÒNG, chỉ nhận tài liệu đã quan
  sát TRỌN VẸN, không bao giờ sửa `claim["text"]`.
* §8 chạy end-to-end qua `MockModel` — lớp chạy độc lập và chạy trong
  full stack đều không được làm hỏng run, và phải thật sự sửa được
  `MISATTRIBUTED` mà baseline sinh ra.
"""

from __future__ import annotations

import json

import pytest

from arena.scorer import _norm, _norm_lines, score_run

from harness.agent import AgentContext
from harness.layers.citation_checker import CitationChecker

from tests.fixtures_briefs import (
    BRIEF_LOOKALIKE,
    BRIEF_SLA,
    CORPUS,
    SEEDS,
    TRAP_BRIEFS,
    run,
)
from tests.test_layers_stubs import student_stack

# ---------------------------------------------------------------------------
# Dữ liệu thử, đọc ra từ corpus
# ---------------------------------------------------------------------------

#: Dòng ngắn hơn ngần này không đủ đặc trưng để làm dữ liệu thử (và
#: `arena.scorer._supports` từ chối mọi câu dưới 12 ký tự đã chuẩn hoá).
_MIN_LINE_CHARS = 40


def _raw_lines(doc) -> list:
    return [line.strip() for line in doc.body.splitlines() if line.strip()]


def _quotable_lines(doc) -> list:
    """Các dòng đủ dài để làm trích dẫn thử."""
    return [line for line in _raw_lines(doc) if len(_norm(line)) >= _MIN_LINE_CHARS]


def _index_lines():
    """`(chủ sở hữu mỗi dòng, dạng thô của mỗi dòng)` trên toàn corpus."""
    owners: dict = {}
    raw_of: dict = {}
    for doc in CORPUS.docs:
        for raw in _raw_lines(doc):
            key = _norm(raw)
            if len(key) < _MIN_LINE_CHARS:
                continue
            raw_of.setdefault(key, raw)
            ids = owners.setdefault(key, [])
            if doc.doc_id not in ids:
                ids.append(doc.doc_id)
    return owners, raw_of


_OWNERS, _RAW_OF = _index_lines()

def _pick_source():
    """Một dòng dài mà ĐÚNG MỘT tài liệu có, trong một tài liệu còn có ít
    nhất một dòng dài nữa (để dựng được câu vắt qua hai dòng)."""
    for key, ids in _OWNERS.items():
        if len(ids) != 1:
            continue
        doc = CORPUS.get(ids[0])
        if len(_quotable_lines(doc)) >= 2:
            return key, doc, _RAW_OF[key]
    raise AssertionError("corpus không có tài liệu nào đủ dùng làm nguồn thử")


_UNIQUE_KEY, SOURCE, SOURCE_LINE = _pick_source()

#: Một tài liệu khác, không chứa `SOURCE_LINE` — vai "tài liệu trông có vẻ
#: chính thống" mà mô hình neo nhầm claim vào.
DECOY = next(
    doc
    for doc in CORPUS.docs
    if doc.doc_id != SOURCE.doc_id and _UNIQUE_KEY not in _norm(doc.body)
)

#: Một dòng mà NHIỀU tài liệu cùng có — để kiểm tra tính tất định.
_SHARED_KEY = next(key for key, ids in _OWNERS.items() if len(ids) >= 2)
SHARED_LINE = _RAW_OF[_SHARED_KEY]
SHARED_DOCS = [CORPUS.get(doc_id) for doc_id in _OWNERS[_SHARED_KEY][:2]]

#: Hai dòng của CÙNG một tài liệu dán lại — câu mà `SPLICED in doc.body`
#: nói "có" còn scorer, vốn chỉ so trong phạm vi một DÒNG, nói "không".
SPLICED = " ".join(_quotable_lines(SOURCE)[:2])


def _ctx(observations, corpus=CORPUS) -> AgentContext:
    """Đúng những gì `after_agent` được phép đọc, không hơn."""
    return AgentContext(
        brief={},
        tools=None,
        trace=None,
        corpus=corpus,
        observations=list(observations),
    )


def _report(claims, **kw) -> dict:
    base = {
        "answer": "Theo tài liệu nội bộ.",
        "citations": [],
        "abstain": False,
        "claims": claims,
    }
    base.update(kw)
    return base


def _check(report, observations, corpus=CORPUS):
    return CitationChecker().after_agent(_ctx(observations, corpus), report)


def test_the_fixtures_are_actually_what_they_claim_to_be():
    """Nếu corpus đổi, hỏng ở đây chứ không hỏng âm thầm ở nơi khác."""
    assert SOURCE is not None and DECOY is not None
    assert SOURCE.doc_id != DECOY.doc_id
    assert _UNIQUE_KEY in _norm(SOURCE.body)
    assert _UNIQUE_KEY not in _norm(DECOY.body)
    assert len(SHARED_DOCS) == 2 and SHARED_DOCS[0] is not SHARED_DOCS[1]
    assert all(line in SPLICED for line in _quotable_lines(SOURCE)[:2])
    assert not any(_norm(SPLICED) in line for line in _norm_lines(SOURCE.body)), (
        "SPLICED phải vắt qua hai dòng, không nằm gọn trong một dòng nào"
    )


# ---------------------------------------------------------------------------
# 1. Trích dẫn đã đúng thì không đụng vào
# ---------------------------------------------------------------------------


def test_a_correct_citation_is_left_exactly_as_it_was():
    claim = {"text": SOURCE_LINE, "doc_id": SOURCE.doc_id}
    report = _check(_report([dict(claim)]), [SOURCE.body])
    assert report["claims"] == [claim]
    assert report["citations"] == [SOURCE.doc_id]


def test_a_claim_the_run_never_read_is_not_promoted_to_a_source():
    """Cùng một câu, nhưng lượt chạy chưa từng đọc tài liệu nào — không có
    gì để đối chiếu nên không được gắn doc_id, kể cả doc_id đúng."""
    report = _check(_report([{"text": SOURCE_LINE, "doc_id": ""}]), [])
    assert report["claims"] == [{"text": SOURCE_LINE, "doc_id": ""}]
    assert report["citations"] == []


# ---------------------------------------------------------------------------
# 2. Câu đúng, tài liệu sai -> gắn lại
# ---------------------------------------------------------------------------


def test_a_correct_sentence_anchored_on_the_wrong_document_is_re_attributed():
    report = _check(
        _report([{"text": SOURCE_LINE, "doc_id": DECOY.doc_id}]),
        [DECOY.body, SOURCE.body],
    )
    assert report["claims"] == [{"text": SOURCE_LINE, "doc_id": SOURCE.doc_id}]
    assert report["citations"] == [SOURCE.doc_id]


def test_re_attribution_keeps_the_claim_text_byte_for_byte():
    """Luật đắt nhất của lab: sửa một ký tự trong `claim["text"]` là mất cả
    provenance lẫn hỗ trợ (đo được -47.16 điểm). Chỉ `doc_id` được đổi."""
    original = {"text": SOURCE_LINE, "doc_id": DECOY.doc_id, "note": "giữ nguyên"}
    claims = [dict(original)]
    report = _check(_report(claims), [DECOY.body, SOURCE.body])

    fixed = report["claims"][0]
    assert fixed["text"] == SOURCE_LINE
    assert fixed["text"] is claims[0]["text"]
    assert fixed["note"] == "giữ nguyên"
    # ...và claim gốc của mô hình cũng không bị mutate tại chỗ.
    assert claims[0] == original


def test_every_claim_is_re_attributed_not_just_the_first():
    """`MockModel` neo CẢ BỐN claim vào một tài liệu; sửa mỗi claim đầu
    tiên vẫn để lại ba `MISATTRIBUTED` và ba lần vượt `MAX_CLAIMS_PER_DOC`."""
    a, b = SHARED_DOCS
    claims = [
        {"text": SOURCE_LINE, "doc_id": DECOY.doc_id},
        {"text": SHARED_LINE, "doc_id": DECOY.doc_id},
    ]
    report = _check(_report(claims), [DECOY.body, SOURCE.body, a.body, b.body])
    assert [c["doc_id"] for c in report["claims"]] == [SOURCE.doc_id, a.doc_id]


# ---------------------------------------------------------------------------
# 3. Chỉ tài liệu đã quan sát TRỌN VẸN mới được làm nguồn
# ---------------------------------------------------------------------------


def test_a_document_the_run_never_fetched_is_never_used_as_a_source():
    """Gắn vào tài liệu chưa đọc bị chấm `UNRETRIEVED` — tệ hơn cả để yên."""
    report = _check(
        _report([{"text": SOURCE_LINE, "doc_id": DECOY.doc_id}]),
        [DECOY.body],
    )
    assert report["claims"] == [{"text": SOURCE_LINE, "doc_id": DECOY.doc_id}]


def test_a_search_snippet_is_not_a_fully_observed_document():
    """Quan sát của `search` là JSON chứa snippet 180 ký tự đầu mỗi hit —
    hình dạng thật của `arena.tools.Tools.search`. Nhìn thấy tên và một
    đoạn đầu tài liệu không phải là đã đọc tài liệu đó."""
    hit = json.dumps(
        [{
            "doc_id": SOURCE.doc_id,
            "title": SOURCE.title,
            "snippet": SOURCE.body[:180] + "…",
        }],
        ensure_ascii=False,
    )
    assert SOURCE.body not in hit

    report = _check(_report([{"text": SOURCE_LINE, "doc_id": DECOY.doc_id}]), [hit])
    assert report["claims"][0]["doc_id"] == DECOY.doc_id


def test_a_truncated_fetch_is_not_a_fully_observed_document():
    """Đây là bẫy tinh vi nhất: câu CÓ trong `observed_text`, nhưng tài liệu
    thì chỉ về một nửa. Kiểm tra `claim["text"] in ctx.observed_text` sẽ gắn
    lại; luật đúng là `doc.body in ctx.observed_text`."""
    head = SOURCE.body[: SOURCE.body.index(SOURCE_LINE) + len(SOURCE_LINE)]
    assert SOURCE_LINE in head and SOURCE.body not in head

    report = _check(_report([{"text": SOURCE_LINE, "doc_id": DECOY.doc_id}]), [head])
    assert report["claims"][0]["doc_id"] == DECOY.doc_id, (
        "một bản bị cắt không chứng minh được lượt chạy đã đọc tài liệu"
    )


def test_a_second_clean_fetch_rescues_a_truncated_one():
    """`retry` fetch lại và lần này về sạch — bằng chứng đã đủ, gắn lại được."""
    head = SOURCE.body[: len(SOURCE.body) // 2]
    report = _check(
        _report([{"text": SOURCE_LINE, "doc_id": DECOY.doc_id}]),
        [head, SOURCE.body],
    )
    assert report["claims"][0]["doc_id"] == SOURCE.doc_id


# ---------------------------------------------------------------------------
# 4. Khớp NGUYÊN VĂN MỘT DÒNG, không phải "nằm đâu đó trong body"
# ---------------------------------------------------------------------------


def test_a_sentence_spliced_across_two_lines_is_not_a_quotation():
    """`SPLICED in doc.body` là False, nhưng một cài đặt lỏng tay nối các
    dòng lại rồi so sẽ nhận — và scorer vẫn chấm `HALLUCINATED`."""
    report = _check(_report([{"text": SPLICED, "doc_id": DECOY.doc_id}]), [SOURCE.body])
    assert report["claims"][0]["doc_id"] == DECOY.doc_id


def test_a_substring_of_one_line_is_still_a_quotation_of_that_line():
    """Cắt bớt hai đầu là hợp lệ (`harness/middleware.py`), nên một đoạn nằm
    gọn trong một dòng vẫn phải gắn lại được."""
    trimmed = SOURCE_LINE[5:-5].strip()
    report = _check(_report([{"text": trimmed, "doc_id": DECOY.doc_id}]), [SOURCE.body])
    assert report["claims"][0]["doc_id"] == SOURCE.doc_id


def test_a_sentence_no_observed_document_contains_is_left_for_the_critic():
    """Câu bịa KHÔNG phải việc của lớp này. Đoán một doc_id ở đây chỉ biến
    `HALLUCINATED` (phạt 1.0) thành `FABRICATED_CITATION` (phạt 1.5)."""
    invented = "Chỉ số hiệu suất kho lạnh quý gần nhất đạt 97,4% so với mục tiêu."
    report = _check(_report([{"text": invented, "doc_id": DECOY.doc_id}]), [SOURCE.body])
    assert report["claims"] == [{"text": invented, "doc_id": DECOY.doc_id}]


# ---------------------------------------------------------------------------
# 5. Tất định khi nhiều tài liệu cùng chứa một dòng
# ---------------------------------------------------------------------------


def test_the_same_line_in_two_documents_resolves_deterministically():
    a, b = SHARED_DOCS
    expected = next(d.doc_id for d in CORPUS.docs if d.doc_id in (a.doc_id, b.doc_id))

    for observations in ([a.body, b.body], [b.body, a.body]):
        for _ in range(2):
            report = _check(
                _report([{"text": SHARED_LINE, "doc_id": DECOY.doc_id}]), observations
            )
            assert report["claims"][0]["doc_id"] == expected


def test_a_document_that_already_supports_the_claim_wins_over_corpus_order():
    """Trích dẫn đúng thì không có lý do gì để dời — kể cả khi một tài liệu
    khác đứng trước trong corpus cũng chứa đúng dòng đó."""
    a, b = SHARED_DOCS
    later = max((a, b), key=lambda d: [x.doc_id for x in CORPUS.docs].index(d.doc_id))
    report = _check(
        _report([{"text": SHARED_LINE, "doc_id": later.doc_id}]), [a.body, b.body]
    )
    assert report["claims"][0]["doc_id"] == later.doc_id


# ---------------------------------------------------------------------------
# 6. `citations` dựng lại từ claims cuối cùng
# ---------------------------------------------------------------------------


def test_citations_are_rebuilt_from_the_claims_without_duplicates():
    a, b = SHARED_DOCS
    claims = [
        {"text": SOURCE_LINE, "doc_id": DECOY.doc_id},
        {"text": SOURCE_LINE, "doc_id": SOURCE.doc_id},
        {"text": SHARED_LINE, "doc_id": DECOY.doc_id},
    ]
    report = _check(
        _report(claims, citations=[DECOY.doc_id, "doc-9999", DECOY.doc_id]),
        [DECOY.body, SOURCE.body, a.body, b.body],
    )
    assert report["citations"] == [SOURCE.doc_id, a.doc_id]
    assert DECOY.doc_id not in report["citations"]


def test_citations_never_name_a_document_no_claim_stands_on():
    report = _check(_report([], citations=[DECOY.doc_id, SOURCE.doc_id]), [SOURCE.body])
    assert report["citations"] == []


# ---------------------------------------------------------------------------
# 7. Report méo mó không được làm chết run
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "report",
    [
        {},
        {"claims": None},
        {"claims": "không phải list"},
        {"claims": [None, 42, "x", {}, {"text": None, "doc_id": None}]},
        {"claims": [{"text": SOURCE_LINE}], "citations": None},
        {"claims": [{"text": SOURCE_LINE, "doc_id": 7}]},
    ],
    ids=["empty", "none", "string", "junk-items", "no-doc-id", "int-doc-id"],
)
def test_a_malformed_report_survives_the_layer(report):
    out = _check(dict(report), [SOURCE.body])
    assert isinstance(out, dict)


def test_the_layer_does_nothing_without_a_corpus():
    claims = [{"text": SOURCE_LINE, "doc_id": DECOY.doc_id}]
    out = CitationChecker().after_agent(_ctx([SOURCE.body], corpus=None), _report(claims))
    assert out["claims"] == claims


def test_the_handover_numbers_land_on_ctx_state():
    """§8.3 D bắt Role 2 báo "số claim được re-attribute" và "claim nào vẫn
    không tìm được document hợp lệ" — đọc thẳng từ đây, không phải đếm tay."""
    ctx = _ctx([DECOY.body, SOURCE.body])
    CitationChecker().after_agent(
        ctx,
        _report(
            [
                {"text": SOURCE_LINE, "doc_id": DECOY.doc_id},
                {"text": "một câu không tài liệu nào nói cả", "doc_id": DECOY.doc_id},
            ]
        ),
    )
    assert ctx.state["citation_checker"] == {
        "observed_docs": 2,
        "claims": 2,
        "reattributed": 1,
        "unsourced": 1,
    }


# ---------------------------------------------------------------------------
# 8. End-to-end: độc lập và trong full stack
# ---------------------------------------------------------------------------


def _verdicts(brief, seed, layers):
    report, jsonl = run(brief, seed, layers)
    score = score_run(brief, report, trace_jsonl=jsonl, corpus=CORPUS)
    return report, score


@pytest.mark.parametrize("brief", TRAP_BRIEFS, ids=lambda b: b["brief_id"])
def test_the_layer_alone_never_lowers_grounding_on_any_trap(brief):
    for seed in SEEDS:
        _, baseline = _verdicts(brief, seed, None)
        _, guarded = _verdicts(brief, seed, [CitationChecker()])
        assert guarded.gate_passed, (brief["brief_id"], seed, guarded.gate_reason)
        assert guarded.grounding >= baseline.grounding, (
            brief["brief_id"],
            seed,
            baseline.grounding,
            guarded.grounding,
        )


@pytest.mark.parametrize(
    "brief", [BRIEF_SLA, BRIEF_LOOKALIKE], ids=lambda b: b["brief_id"]
)
def test_the_layer_removes_the_misattributions_the_baseline_produces(brief):
    """`test_the_baseline_misattributes_its_citations` chứng minh baseline có
    `MISATTRIBUTED`; lớp này phải làm chúng biến mất mà không đẻ ra
    `UNRETRIEVED` hay `FABRICATED_CITATION` mới."""
    before = after = 0
    for seed in SEEDS:
        _, baseline = _verdicts(brief, seed, None)
        _, guarded = _verdicts(brief, seed, [CitationChecker()])
        base_counts = baseline.detail["grounding"]["verdict_counts"]
        kept_counts = guarded.detail["grounding"]["verdict_counts"]
        before += base_counts.get("MISATTRIBUTED", 0)
        after += kept_counts.get("MISATTRIBUTED", 0)
        for bad in ("UNRETRIEVED", "FABRICATED_CITATION"):
            assert kept_counts.get(bad, 0) <= base_counts.get(bad, 0), (bad, seed)

    assert before > 0, "brief này phải sinh ra misattribution để có gì mà sửa"
    assert after < before, (before, after)


def test_every_claim_the_layer_cites_was_actually_fetched():
    """Bất biến provenance, đọc thẳng từ trace: mọi doc_id trong report cuối
    phải là tài liệu lượt chạy đã fetch, không phải một cái tên đẹp."""
    for brief in TRAP_BRIEFS:
        for seed in SEEDS:
            report, jsonl = run(brief, seed, [CitationChecker()])
            for claim in report.get("claims") or []:
                doc_id = claim.get("doc_id")
                if not doc_id:
                    continue
                doc = CORPUS.get(doc_id)
                if doc is None or _norm(claim.get("text", "")) not in _norm(doc.body):
                    continue  # claim này lớp không đụng vào — việc của critic
                assert doc_id in jsonl, (brief["brief_id"], seed, doc_id)


def test_the_layer_works_the_same_inside_the_full_stack():
    """Full stack có thể bỏ claim hoặc retry tool, nhưng không được làm hỏng
    provenance mà citation checker bảo vệ."""
    for brief in TRAP_BRIEFS:
        stacked, jsonl = run(brief, SEEDS[0], student_stack())
        score = score_run(brief, stacked, trace_jsonl=jsonl, corpus=CORPUS)
        expected_citations = sorted({
            claim.get("doc_id")
            for claim in stacked.get("claims") or []
            if isinstance(claim, dict) and claim.get("doc_id")
        })

        assert score.gate_passed, brief["brief_id"]
        assert score.detail["grounding"]["verdict_counts"].get("MISATTRIBUTED", 0) == 0
        assert stacked.get("citations") == expected_citations, brief["brief_id"]
