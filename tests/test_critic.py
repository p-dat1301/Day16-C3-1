"""Acceptance tests owned by the Grounding & Critic Engineer."""

from __future__ import annotations

from dataclasses import dataclass

from arena.corpus import Corpus
from harness.layers.critic import Critic


@dataclass
class _Context:
    corpus: object
    observed_text: str

    def saw(self, text: str) -> bool:
        return bool(text) and text in self.observed_text


def _report(claims, **overrides):
    report = {
        "answer": "Báo cáo của mô hình.",
        "claims": claims,
        "citations": ["doc-thừa"],
        "abstain": False,
    }
    report.update(overrides)
    return report


def test_critic_removes_fabrication_and_abstains_when_no_claim_survives():
    corpus = Corpus.generate(seed=42)
    report = _report([{"text": "Số liệu không hề có trong evidence.", "doc_id": "doc-0004"}])

    result = Critic().after_agent(_Context(corpus, "quan sát vô can"), report)

    assert result["claims"] == []
    assert result["citations"] == []
    assert result["abstain"] is True
    assert "Không đủ căn cứ" in result["answer"]


def test_critic_keeps_observed_claim_byte_for_byte_and_rebuilds_citations():
    corpus = Corpus.generate(seed=42)
    text = corpus.get("doc-0004").body.splitlines()[-1]
    claim = {"text": text, "doc_id": "doc-9999", "metadata": {"keep": True}}

    result = Critic().after_agent(_Context(corpus, text), _report([claim]))

    assert result["claims"] == [claim]
    assert result["claims"][0]["text"] == text
    assert result["citations"] == ["doc-9999"]
    assert result["abstain"] is False


def test_critic_splits_a_fused_claim_only_when_two_full_documents_were_observed():
    corpus = Corpus.generate(seed=42)
    first, second = corpus.get("doc-0001"), corpus.get("doc-0002")
    left = first.body.splitlines()[-1][:80]
    right = second.body.splitlines()[-1][-80:]
    fused = f"{left} và {right}"

    result = Critic().after_agent(
        _Context(corpus, first.body + "\n" + second.body),
        _report([{"text": fused, "doc_id": "doc-0001"}]),
    )

    assert result["claims"] == [
        {"text": left, "doc_id": first.doc_id},
        {"text": right, "doc_id": second.doc_id},
    ]
    assert result["citations"] == sorted([first.doc_id, second.doc_id])
    assert result["abstain"] is True


def test_critic_rejects_fused_claim_when_one_source_was_not_fully_observed():
    corpus = Corpus.generate(seed=42)
    first, second = corpus.get("doc-0001"), corpus.get("doc-0002")
    left = first.body.splitlines()[-1][:80]
    right = second.body.splitlines()[-1][-80:]

    result = Critic().after_agent(
        _Context(corpus, first.body + "\n" + right),
        _report([{"text": f"{left} và {right}", "doc_id": first.doc_id}]),
    )

    assert result["claims"] == []
    assert result["citations"] == []
    assert result["abstain"] is True
