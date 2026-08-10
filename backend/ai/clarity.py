"""Ambiguity and unsupported-question detection.

The assistant must never fabricate an answer:

- AMBIGUOUS: "What is the best product?" when the dataset has several measures
  (revenue / units / rating) and the question does not name one. Ask which
  measure defines "best" instead of silently picking one.
- UNSUPPORTED: "Why did sales decrease?" asks for a causal explanation the
  pipeline cannot derive from a single dataset. Point at what CAN be answered
  (grouped comparisons, trends) instead of inventing causes.

Both are returned to the API layer as guidance messages before any SQL is
generated.
"""
import re

from .columns import _parse_columns_info


def _metric_columns(cols_meta: list) -> list:
    return [c.get("name") for c in (cols_meta or []) if c.get("type") == "metric"]


def _dimension_columns(cols_meta: list) -> list:
    return [c.get("name") for c in (cols_meta or [])
            if c.get("type") in ("categorical", "text")]


def detect_ambiguous_question(question: str, cols_meta: list) -> str | None:
    """Return a clarification message when the question is genuinely ambiguous."""
    q = question.lower().strip()
    metric_cols = _metric_columns(cols_meta)
    if len(metric_cols) < 2:
        return None

    # A specific measure is named in the question -> not ambiguous.
    if any(m.lower() in q for m in metric_cols):
        return None

    # Singular superlative over an entity: "What is the best product?" /
    # "which is the worst product?" Exclude "best-selling" (selling implies a
    # sales/units measure) and "best price"/explicit measure phrases.
    m = re.search(r"\b(best|worst)\s+(?:one\s+)?([a-z][\w\s'-]*?)\s*\??$", q)
    if not m:
        m = re.search(r"\b(?:what|which)\s+is\s+the\s+(best|worst)\s+([a-z][\w\s'-]*?)\s*\??$", q)
    if m:
        if "selling" in m.group(2) or "seller" in m.group(2):
            return None
        superlative = m.group(1)
        entity_phrase = m.group(2).strip()
        if not entity_phrase or any(w in entity_phrase for w in ("price", "rating", "score")):
            return None
        dimension_cols = _dimension_columns(cols_meta)
        for w in re.findall(r"\w+", entity_phrase):
            stem = w[:-1] if w.endswith("s") and not w.endswith("ss") else w
            for c in dimension_cols:
                c_low = c.lower()
                if c_low == w or c_low == stem or c_low.replace("_", " ") == w:
                    return (
                        f"The dataset has several measures for '{c}': "
                        f"{', '.join(metric_cols)}. Which one should define "
                        f"'{superlative}'? Try e.g. \"{superlative} {c} by "
                        f"{metric_cols[0]}\"."
                    )
    return None


def detect_unsupported_question(question: str, cols_meta: list) -> str | None:
    """Return a limitation message for questions the pipeline cannot answer."""
    q = question.lower().strip()

    # Causal "why" questions: "why did sales decrease", "why is revenue so low".
    why_increase = re.search(r"\bwhy\s+(?:did|is|are|has|have|does|do)\s+(.+?)\s+(?:increase|decrease|rise|fall|drop|decline|grow|shrink|improve|deteriorate)\b", q)
    why_state = re.search(r"\bwhy\s+(?:is|are)\s+(.+?)\s+(?:so\s+)?(?:high|low|bad|good|large|small|expensive|cheap)\b", q)
    why = why_increase or why_state
    if why:
        return (
            "This question asks for a causal explanation. I can show how values "
            "vary and which groups differ, but I can't determine why something "
            "changed from this dataset alone. Try grouping the data instead, e.g. "
            "'show the metric by category/region' or compare two periods."
        )

    # "Predict the future" style questions.
    if re.search(r"\b(predict|forecast|future|will\s+(?:sales|revenue|profits?)\s+(?:be|go|increase|decrease))\b", q):
        return (
            "I can't forecast future values from this data alone. I can describe "
            "the historical trend, averages and changes over time instead."
        )

    return None


def check_question_feasibility(question: str, cols_meta: list) -> dict:
    """Return ``{"guidance": <message>}`` or ``{"guidance": None}``."""
    for detector in (detect_ambiguous_question, detect_unsupported_question):
        msg = detector(question, cols_meta)
        if msg:
            return {"guidance": msg}
    return {"guidance": None}
