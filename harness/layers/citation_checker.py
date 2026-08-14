"""LỚP `citation_checker` — bài giảng Day 16, §11 (Grounding & Citations).

NHIỆM VỤ: chỉ cần MỘT tài liệu gắn nhãn `lookalike` hoặc `outdated` lọt
vào bằng chứng là mô hình neo TOÀN BỘ claim vào đúng tài liệu trông có vẻ
"chính thống" đó — dù mỗi câu được lấy nguyên văn từ một tài liệu khác.
Câu thì thật, trích dẫn thì sai. Đây là kiểu sai nguy hiểm nhất trong RAG
vì báo cáo đọc vào vẫn rất thuyết phục.

TÍN HIỆU (chính xác, không cần đoán):

    claim["text"] KHÔNG khớp NGUYÊN VĂN một DÒNG nào trong
    corpus.get(claim["doc_id"]).body
    nhưng CHÍNH câu đó CÓ trong bằng chứng agent đã quan sát

Chú ý chữ DÒNG: kiểm tra `claim["text"] in doc.body` (cả khối, không
tách dòng) là SAI — scorer chỉ nhận trích dẫn khớp nguyên văn MỘT DÒNG
(xem "ĐƯỢC PHÉP VÀ KHÔNG ĐƯỢC PHÉP" ngay dưới đây). `in doc.body` coi
một câu vắt qua hai dòng là hợp lệ, trong khi scorer thì không — tín
hiệu kiểu đó khiến bạn giữ nguyên một trích dẫn mà scorer vẫn chấm
`HALLUCINATED`.

Vế thứ hai mới là phần quan trọng: nó tách việc của bạn khỏi việc của
`critic` (§2). Câu có trong bằng chứng nhưng gắn sai tài liệu -> GẮN LẠI
(việc của bạn). Câu không có trong bằng chứng nào -> BỊA, để `critic` xoá.
Hai điều kiện loại trừ nhau nên hai lớp không giành điểm của nhau.

ĐƯỢC PHÉP VÀ KHÔNG ĐƯỢC PHÉP:
  * ĐƯỢC: đổi `claim["doc_id"]`, cập nhật `report["citations"]`.
  * KHÔNG: sửa `claim["text"]`. Scorer chỉ cho điểm khi câu là trích dẫn
    nguyên văn của MỘT DÒNG trong tài liệu được trích VÀ đúng là chữ mô
    hình đã viết. Thêm dấu chấm, đổi dấu nháy, "chuẩn hoá" khoảng trắng,
    hay vá lại câu bị cắt bằng nội dung lấy từ corpus đều làm mất cả hai
    điều kiện cùng lúc (đo được: -40 điểm).

CHỈ ĐƯỢC GẮN VÀO TÀI LIỆU ĐÃ QUAN SÁT. Trích một tài liệu mà lượt chạy
chưa từng đọc bị chấm `UNRETRIEVED`. Vì vậy hãy tìm nguồn trong
`ctx.observed_text`, đừng quét cả corpus rồi gắn bừa: điều kiện
`doc.body in ctx.observed_text` nghĩa là "tài liệu này đã về nguyên vẹn
từ một lần fetch sạch" — một đoạn snippet hay một bản bị cắt không tính.

CÔNG CỤ CÓ SẴN:
    ctx.observed_text  -> toàn bộ quan sát agent đã thấy, nối lại
    ctx.corpus.get(doc_id) -> Doc | None
    ctx.corpus.docs    -> danh sách Doc (doc_id, title, body); qua
                          `ctx.corpus`, `Doc.tags` LUÔN RỖNG — CẢ Ở VÒNG
                          LUYỆN TẬP LẪN VÒNG CHẤM ĐIỂM, vì corpus mà code
                          của bạn cầm bị gỡ nhãn bẫy ('outdated',
                          'contradiction', 'injection'…) ngay khi runner
                          dựng lên nó, không phải chỉ lúc chấm điểm. Đọc
                          nhãn là tra bảng chứ không phải kỹ năng lab này
                          chấm. Ở vòng LUYỆN TẬP seed 42 thì file TRÊN ĐĨA
                          `data/corpus/*.json` (khác với `ctx.corpus`)
                          vẫn có nhãn: hard-code được từ đó, và điều đó
                          được nói thẳng ra ở đây thay vì giấu đi.

Cài đặt:  ReActAgent(..., middleware=[..., CitationChecker(), ...])
Xem `harness/middleware.py` để biết thứ tự các hook.

--------------------------------------------------------------------------
CÀI ĐẶT NÀY QUYẾT ĐỊNH NHỮNG GÌ
--------------------------------------------------------------------------

Một claim được trỏ về `doc.doc_id` khi và chỉ khi `doc` thoả CẢ HAI:

  1. ĐÃ QUAN SÁT TRỌN VẸN — `doc.body in ctx.observed_text`. Kết quả
     `search` chỉ trả snippet 180 ký tự và một lần `fetch_doc` bị cắt
     (flaky `truncate`) chỉ trả một phần thân, nên cả hai đều KHÔNG thoả.
     Điều kiện này chặt hơn hẳn `retrieved` của scorer (vốn còn tính cả
     hit của `search`), nên mọi doc_id lớp này gán ra đều nằm trong
     `retrieved`: không bao giờ tự tạo ra `UNRETRIEVED` mới.
  2. THẬT SỰ CHỨA CÂU ĐÓ, ở phạm vi MỘT DÒNG — theo đúng
     `arena.scorer._supports`.

Ưu tiên chính tài liệu mà claim đang trích: nếu nó đã thoả cả hai thì
trích dẫn vốn đã đúng, giữ nguyên. Nếu không, quét `ctx.corpus.docs`
theo thứ tự corpus và lấy tài liệu đầu tiên thoả — thứ tự corpus là cố
định nên khi nhiều tài liệu cùng chứa một dòng, kết quả vẫn tất định.

Không tìm được nguồn nào -> KHÔNG đụng vào claim. Câu bịa là việc của
`critic`; đoán một doc_id ở đây chỉ biến `HALLUCINATED` thành
`FABRICATED_CITATION` (phạt nặng hơn).

`claim["text"]` không bao giờ bị sửa: khi phải đổi `doc_id`, lớp này tạo
một dict MỚI (`{**claim, "doc_id": ...}`) nên claim gốc của mô hình cũng
không bị mutate tại chỗ.
"""

from __future__ import annotations

import re
import unicodedata

from harness.middleware import Middleware

# ---------------------------------------------------------------------------
# Luật provenance. Mượn thẳng của scorer thay vì viết lại: một trích dẫn
# chỉ được tính điểm khi `arena.scorer._supports` nói có, nên một bản cài
# đặt thứ hai lệch đi dù chỉ một ký tự sẽ gắn lại những claim mà scorer
# vẫn chấm `HALLUCINATED`. Bản sao cục bộ bên dưới chỉ là lưới an toàn để
# harness không phụ thuộc vào việc grader có import được hay không — cùng
# một dàn xếp mà `harness/agent.py` dùng cho `_canonicalise`.
# ---------------------------------------------------------------------------

#: Câu ngắn hơn ngần này không "đỡ" được gì (`arena.scorer.MIN_SUPPORT_CHARS`).
_MIN_SUPPORT_CHARS = 12

_WS_RE = re.compile(r"\s+")


def _local_norm(text) -> str:
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    return _WS_RE.sub(" ", unicodedata.normalize("NFC", text).casefold()).strip()


def _local_norm_lines(text) -> tuple:
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    return tuple(line for line in (_local_norm(raw) for raw in text.splitlines()) if line)


def _local_supports(normalised_lines, normalised_claim: str) -> bool:
    if len(normalised_claim) < _MIN_SUPPORT_CHARS:
        return False
    return any(normalised_claim in line for line in normalised_lines)


def _scorer_rule():
    """`(_norm, _norm_lines, _supports)` của scorer, hoặc bản sao cục bộ."""
    try:
        from arena.scorer import _norm, _norm_lines, _supports
    except Exception:  # pragma: no cover - scorer luôn đi kèm lab
        return _local_norm, _local_norm_lines, _local_supports
    return _norm, _norm_lines, _supports


_norm, _norm_lines, _supports = _scorer_rule()


# ---------------------------------------------------------------------------
# Lớp
# ---------------------------------------------------------------------------


class CitationChecker(Middleware):
    """Trỏ mỗi claim về đúng tài liệu thật sự chứa câu đó."""

    name = "citation_checker"

    def after_agent(self, ctx, report):
        claims = report.get("claims") if isinstance(report, dict) else None
        corpus = getattr(ctx, "corpus", None)
        if not isinstance(claims, list) or corpus is None:
            return report

        observed = _fully_observed(ctx, corpus)
        lines = {doc.doc_id: _norm_lines(doc.body) for doc in observed}

        checked: list = []
        reattributed = 0
        unsourced = 0
        for claim in claims:
            source = _source_of(claim, observed, lines)
            if source is None:
                # Không tài liệu nào đã quan sát chứa câu này. Để nguyên
                # cho `critic` quyết định — nó chạy sau lớp này.
                unsourced += 1
                checked.append(claim)
            elif source == _doc_id(claim):
                checked.append(claim)
            else:
                checked.append({**claim, "doc_id": source})
                reattributed += 1

        report["claims"] = checked
        # Citations luôn dựng lại từ claims cuối cùng, theo thứ tự claim và
        # bỏ trùng — cùng quy ước mà `arena.model._final_payload` dùng, nên
        # `citations[0]` vẫn là nguồn chính. Scorer chỉ chấm `claims`;
        # citations là thông tin, và một ID không claim nào đỡ là rác.
        report["citations"] = _citations(checked)
        _record(ctx, observed, checked, reattributed, unsourced)
        return report


# ---------------------------------------------------------------------------
# Chi tiết
# ---------------------------------------------------------------------------


def _doc_id(claim) -> str:
    """`claim["doc_id"]`, đọc y hệt cách `arena.scorer._claim_doc_id` đọc."""
    if not isinstance(claim, dict):
        return ""
    value = claim.get("doc_id")
    return value.strip() if isinstance(value, str) else ""


def _fully_observed(ctx, corpus) -> list:
    """Tài liệu lượt chạy đã đọc TRỌN VẸN, giữ nguyên thứ tự corpus.

    `fetch_doc` trả về đúng `doc.body`, nên phép kiểm tra này đúng bằng
    "đã có một lần fetch sạch". Snippet của `search`, một lần fetch bị
    `truncate`, hay một quan sát đã bị `injection_guard` thay bằng
    placeholder đều trượt — và đó là chủ ý.
    """
    observed_text = getattr(ctx, "observed_text", "") or ""
    if not observed_text:
        return []
    docs = getattr(corpus, "docs", None) or ()
    return [doc for doc in docs if doc.body and doc.body in observed_text]


def _source_of(claim, observed: list, lines: dict):
    """doc_id mà claim này đáng được trỏ tới, hoặc None nếu không có.

    `lines` chỉ chứa các tài liệu đã quan sát trọn vẹn, nên phép thử
    `cited in lines` chính là điều kiện "tài liệu đang trích đã được đọc
    thật" — một tài liệu chưa fetch không bao giờ được giữ lại làm nguồn
    hợp lệ, và cũng không bao giờ được gắn mới.
    """
    if not isinstance(claim, dict):
        return None
    text = claim.get("text")
    if not isinstance(text, str):
        return None

    normalised = _norm(text)
    cited = _doc_id(claim)
    if cited in lines and _supports(lines[cited], normalised):
        return cited
    for doc in observed:
        if _supports(lines[doc.doc_id], normalised):
            return doc.doc_id
    return None


def _citations(claims: list) -> list:
    """doc_id của các claim, theo thứ tự xuất hiện, không trùng."""
    out: list = []
    for claim in claims:
        doc_id = _doc_id(claim)
        if doc_id and doc_id not in out:
            out.append(doc_id)
    return out


def _record(ctx, observed: list, claims: list, reattributed: int, unsourced: int) -> None:
    """Số liệu bàn giao trên `ctx.state` — chỉ scalar, không giữ tham chiếu."""
    state = getattr(ctx, "state", None)
    if isinstance(state, dict):
        state["citation_checker"] = {
            "observed_docs": len(observed),
            "claims": len(claims),
            "reattributed": reattributed,
            "unsourced": unsourced,
        }


__all__ = ["CitationChecker"]
