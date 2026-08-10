"""Natural-language intent detection for the local NL->SQL engine."""
import re

from .columns import _match_col, _simple_stem
from .questions import _preferred_metric


def _match_metric(word: str, numeric_cols: list):
    """Match a question's metric word against the numeric/metric columns only.

    Extends _match_col with a token-prefix rule so that a noun like "units"
    resolves to "units_sold" or "net_revenue" from "revenue". The rule is
    deliberately restricted to numeric columns: "Which cities have the most
    suppliers?" must never resolve the noun "suppliers" to a *text* column
    such as "supplier_name" (that question is a grouped COUNT, not a metric
    ranking).
    """
    hit = _match_col(word, numeric_cols)
    if hit:
        return hit
    stem = _simple_stem(word.strip())
    if len(stem) < 3:
        return None
    for c in numeric_cols:
        for token in c.lower().replace("_", " ").split():
            t_stem = _simple_stem(token)
            if len(t_stem) >= 3 and (t_stem.startswith(stem) or stem.startswith(t_stem)):
                return c
    return None

# Nouns/phrases that signal a numeric MEASURE is being asked about. Used to
# decide whether a fallback metric applies: "Which cities have the most
# suppliers?" must COUNT suppliers, NOT aggregate whatever the first numeric
# column happens to be (e.g. a "since" year). "Which region has the most
# sales?" still aggregates the measure.
_METRIC_NOUNS = (
    "revenue", "sales", "amount", "spend", "spending", "spent", "expense",
    "expenses", "cost", "costs", "price", "unit", "units", "quantity", "qty",
    "salary", "salaries", "profit", "income", "value", "margin", "volume",
    "gross", "net", "total", "sum", "average", "avg", "score", "rating",
    "count", "fee", "budget", "payout", "purchase", "purchases", "order value",
    "revenue by", "sales by",
)


def _mentions_metric(phrase: str) -> bool:
    """True when a phrase refers to a numeric measure (not just an entity)."""
    low = (phrase or "").lower()
    for w in re.findall(r"[a-z']+", low):
        if w in _METRIC_NOUNS:
            return True
    return False


def _detect_intent(question: str, col_names: list, numeric_cols: list, text_cols: list):
    q = question.lower().strip()
    q = re.sub(r"[.!?]+\s*$", "", q)
    metric_cols = numeric_cols
    cat_cols = text_cols

    intent = {
        "intent_type": "list",
        "is_count_query": False,
        "is_aggregation": False,
        "is_comparison": False,
        "is_ranking": False,
        "is_time_series": False,
        "is_correlation": False,
        "is_list_all": False,
        "agg_func": None,
        "agg_col": None,
        "group_col": None,
        "group_by_phrase": None,
        "sort_order": None,
        "limit": None,
        "columns_to_select": [],
        "filter": None,
        "entity": None,
    }

    # 1. COUNT detection
    count_patterns = [
        r"^how many\s+(.+)\s+are there\??$",
        r"^how many\s+(.+)\??$",
        r"^number of\s+(.+)$",
        r"^count\s+(.+)$",
        r"^count of\s+(.+)$",
        r"^total number of\s+(.+)$",
        r"^what is the total number of\s+(.+)$",
        r"^give me the count of\s+(.+)$",
    ]

    # "Total amount spent" (bare "total X") -> SUM when X is a metric, not a count.
    _METRIC_WORDS = ("amount", "spend", "spent", "spending", "price", "revenue", "cost", "sales", "salary", "value", "sum", "expense", "expenses", "total")
    m_total = re.match(r"^total\s+(.+)$", q)
    if m_total:
        target = m_total.group(1).strip().rstrip("?.")
        target_low = target.lower()
        is_metric = any(c.lower().replace("_", " ") in target_low or _simple_stem(c.lower()) in target_low for c in numeric_cols)
        is_metric = is_metric or any(w in target_low for w in _METRIC_WORDS)
        if is_metric and numeric_cols:
            intent["is_aggregation"] = True
            intent["agg_func"] = "SUM"
            intent["intent_type"] = "aggregation"
            for c in numeric_cols:
                if c.lower().replace("_", " ") in target_low or _simple_stem(c.lower()) in target_low:
                    intent["agg_col"] = c
                    break
            if not intent["agg_col"]:
                intent["agg_col"] = numeric_cols[0]
        else:
            intent["is_count_query"] = True
            intent["is_aggregation"] = True
            intent["agg_func"] = "COUNT"
            intent["intent_type"] = "count"
            for c in col_names:
                if c.lower() == target or c.lower().replace("_", " ") == target:
                    intent["agg_col"] = c
                    break

    for pattern in count_patterns:
        m = re.match(pattern, q)
        if m:
            intent["is_count_query"] = True
            intent["is_aggregation"] = True
            intent["agg_func"] = "COUNT"
            intent["intent_type"] = "count"
            target = m.group(1).strip().rstrip("?.")
            for c in col_names:
                if c.lower() == target or c.lower().replace("_", " ") == target:
                    intent["agg_col"] = c
                    break
            break

    # 1.5 "Which <dim> has/had the <highest|lowest> <metric>?" plus count-ranking
    #     forms like "Which <dim> have the most <entity>?" (see 1.6 too).
    if intent["intent_type"] == "list":
        m = re.search(r"\b(?:which|what)\s+(.+?)\s+(?:has|have|had|got|sold|ordered|recorded|generated|received)\s+(?:the\s+)?(highest|lowest|most|least|largest|smallest|top|maximum|minimum|best|worst)\s+(.+)$", q)
        if m:
            dim_phrase = m.group(1).strip().rstrip("?").strip()
            qualifier = m.group(2)
            metric_phrase = m.group(3).strip().rstrip("?")
            for w in re.findall(r"\w+", dim_phrase):
                intent["group_col"] = _match_col(w, text_cols) or _match_col(w, col_names)
                if intent["group_col"]:
                    break
            agg_keywords = {
                "total": "SUM", "sum": "SUM", "average": "AVG", "avg": "AVG", "mean": "AVG",
                "maximum": "MAX", "max": "MAX", "minimum": "MIN", "min": "MIN", "count": "COUNT",
            }
            for kw, func in agg_keywords.items():
                if re.search(r"\b" + re.escape(kw) + r"\b", metric_phrase):
                    intent["agg_func"] = func
                    metric_phrase = re.sub(r"\b" + kw + r"\b", "", metric_phrase).strip()
                    break
            for w in re.findall(r"\w+", metric_phrase):
                intent["agg_col"] = _match_metric(w, numeric_cols) or _match_col(w, col_names)
                if intent["agg_col"]:
                    break
            if not intent["group_col"] and len(cat_cols) == 1:
                intent["group_col"] = cat_cols[0]
            if not intent["agg_col"] and len(metric_cols) == 1 and _mentions_metric(metric_phrase):
                intent["agg_col"] = metric_cols[0]
            elif not intent["agg_col"] and metric_cols and _mentions_metric(metric_phrase):
                intent["agg_col"] = _preferred_metric(metric_cols)
            if intent["agg_col"] and intent["group_col"]:
                intent["intent_type"] = "ranking"
                intent["is_ranking"] = True
                intent["limit"] = 1
                intent["sort_order"] = "DESC" if qualifier in ("highest", "most", "largest", "top", "maximum", "best") else "ASC"
                intent["agg_func"] = intent["agg_func"] or "SUM"
                intent["is_aggregation_rank"] = True
            elif intent["group_col"] and qualifier in ("most", "least"):
                # "Which <dim> have the most <entity>?" where the entity is not a
                # metric column -> count records grouped by the dimension.
                intent["intent_type"] = "count"
                intent["is_ranking"] = True
                intent["is_aggregation"] = True
                intent["is_count_query"] = True
                intent["agg_func"] = "COUNT"
                intent["entity"] = f"{_simple_stem(metric_phrase) or _simple_stem(intent['group_col'])}_count"
                intent["limit"] = None
                intent["sort_order"] = "DESC" if qualifier in ("highest", "most", "largest", "top", "maximum", "best") else "ASC"

    # 1.6 Natural-language ranking/count variations:
    #   "Which products sold the most?"            -> count grouped by product
    #   "What are the best-selling products?"      -> count grouped by product
    #   "Which city had the most orders?"          -> count grouped by city
    if intent["intent_type"] == "list":
        # (a) question ends at "the most|least" (entity already implied by the
        #     subject dimension): "Which products sold the most?"
        m = re.search(r"\b(?:which|what)\s+(.+?)\s+(?:sold|ordered|occurred|appeared|recorded|generated|received|has|have|had)\s+(?:the\s+)?(most|least)\s*$", q)
        if m:
            dim_phrase = m.group(1).strip()
            qualifier = m.group(2)
            for w in re.findall(r"\w+", dim_phrase):
                intent["group_col"] = _match_col(w, text_cols) or _match_col(w, col_names)
                if intent["group_col"]:
                    break
            if intent["group_col"]:
                intent["intent_type"] = "count"
                intent["is_ranking"] = True
                intent["is_aggregation"] = True
                intent["is_count_query"] = True
                intent["agg_func"] = "COUNT"
                intent["entity"] = f"{_simple_stem(intent['group_col'])}_count"
                intent["limit"] = None
                intent["sort_order"] = "DESC" if qualifier == "most" else "ASC"

        # (b) "best-selling <entity>" / "most popular <entity>" / "most common <entity>"
        m = re.search(r"(?:best[- ]?selling|most\s+popular|most\s+common|most\s+frequent)\s+([A-Za-z][A-Za-z\s'-]*?)\s*$", q)
        if m:
            entity_phrase = m.group(1).strip()
            for w in re.findall(r"\w+", entity_phrase):
                intent["group_col"] = _match_col(w, text_cols) or _match_col(w, col_names)
                if intent["group_col"]:
                    break
            if intent["group_col"]:
                intent["intent_type"] = "count"
                intent["is_ranking"] = True
                intent["is_aggregation"] = True
                intent["is_count_query"] = True
                intent["agg_func"] = "COUNT"
                intent["entity"] = f"{_simple_stem(intent['group_col']) or _simple_stem(entity_phrase)}_count"
                intent["limit"] = 10
                intent["sort_order"] = "DESC"

    # 2. COMPARISON: "compare X across Y", "X comparison by Y"
    if intent["intent_type"] == "list":
        compare_match = re.search(r'\bcompare\s+(.+?)\s+(?:across|by|with|against)\s+(.+)', q)
        if not compare_match:
            compare_match = re.search(r'(.+?)\s+comparison\s+(?:across|by|of|between|with)\s+(.+)', q)

        if compare_match:
            metric_phrase = compare_match.group(1).strip()
            group_phrase = compare_match.group(2).strip()

            agg_keywords = {
                'average': 'AVG', 'avg': 'AVG', 'mean': 'AVG',
                'total': 'SUM', 'sum': 'SUM',
                'maximum': 'MAX', 'max': 'MAX', 'highest': 'MAX',
                'minimum': 'MIN', 'min': 'MIN', 'lowest': 'MIN',
                'count': 'COUNT',
            }
            for kw, func in agg_keywords.items():
                if re.search(r"\b" + re.escape(kw) + r"\b", metric_phrase):
                    intent['agg_func'] = func
                    metric_phrase = re.sub(r'\b' + kw + r'\b', '', metric_phrase).strip()
                    break

            if not intent['agg_func']:
                intent['agg_func'] = 'SUM'

            words = re.findall(r'\w+', metric_phrase)
            for w in words:
                intent['agg_col'] = _match_metric(w, numeric_cols)
                if intent['agg_col']:
                    break
            if not intent['agg_col']:
                for w in re.findall(r'\w+', metric_phrase):
                    intent['agg_col'] = _match_col(w, col_names)
                    if intent['agg_col']:
                        break

            for w in re.findall(r'\w+', group_phrase):
                intent['group_col'] = _match_col(w, text_cols)
                if intent['group_col']:
                    break
            if not intent['group_col']:
                for w in re.findall(r'\w+', group_phrase):
                    intent['group_col'] = _match_col(w, col_names)
                    if intent['group_col']:
                        break

            if intent['agg_col'] and intent['group_col']:
                intent['intent_type'] = 'comparison'
                intent['is_comparison'] = True
                intent['is_aggregation'] = True
                intent['sort_order'] = 'DESC'

    # 3. RANKING: "top N X by Y", "rank X by Y", "bottom N X by Y", "top X"
    if intent['intent_type'] == 'list':
        rank_match = re.search(r'(?:top|bottom|rank(?:ed)?|best|worst|highest|lowest)\s+(\d+)?\s*(.+?)\s+by\s+(.+)', q)
        if not rank_match:
            rank_match = re.search(r'(?:top|bottom|rank(?:ed)?|best|worst|highest|lowest)\s+(\d+)\s+(.+)', q)
        if not rank_match:
            # "What are the top products?" (no rank number, no metric) -> the
            # entity phrase is the whole tail; ranking then falls back to count.
            rank_match = re.search(r'\b(?:top|best|leading)\s+([A-Za-z][A-Za-z0-9_\s\'\-]*?)\s*$', q)

        if rank_match:
            limit_str = rank_match.group(1) if rank_match.lastindex and rank_match.lastindex >= 2 else None
            entity_phrase = rank_match.group(2).strip() if rank_match.lastindex and rank_match.lastindex >= 2 else rank_match.group(1).strip()
            metric_phrase = rank_match.group(3).strip() if rank_match.lastindex and rank_match.lastindex >= 3 else entity_phrase

            intent['intent_type'] = 'ranking'
            intent['is_ranking'] = True
            intent['limit'] = int(limit_str) if limit_str and limit_str.isdigit() else 10

            if any(w in q for w in ['top', 'best', 'highest', 'largest']):
                intent['sort_order'] = 'DESC'
            else:
                intent['sort_order'] = 'ASC'

            for w in re.findall(r'\w+', metric_phrase):
                intent['agg_col'] = _match_metric(w, numeric_cols)
                if intent['agg_col']:
                    break
            for w in re.findall(r'\w+', entity_phrase):
                intent['group_col'] = _match_col(w, text_cols)
                if intent['group_col']:
                    break
            if not intent['group_col']:
                for w in re.findall(r'\w+', entity_phrase):
                    intent['group_col'] = _match_col(w, col_names)
                    if intent['group_col']:
                        break

            if intent['group_col'] and intent['agg_col'] and intent['group_col'] == intent['agg_col']:
                # "top 5 by revenue" resolves group and metric to the same column;
                # that is a plain sort, not a grouping.
                intent['group_col'] = None

            if intent['group_col'] and not intent['agg_col'] and numeric_cols:
                intent['agg_col'] = numeric_cols[0]
            elif intent['group_col'] and not intent['agg_col']:
                # "Top products" with no usable metric column -> rank by record
                # count grouped by the entity's dimension.
                intent['intent_type'] = 'count'
                intent['is_count_query'] = True
                intent['agg_func'] = 'COUNT'
                intent['is_aggregation'] = True
                intent['entity'] = f"{_simple_stem(intent['group_col']) or _simple_stem(entity_phrase)}_count"

    # 4. AGGREGATION (non-comparison)
    if intent['intent_type'] == 'list':
        agg_map = {
            'average': 'AVG', 'avg': 'AVG', 'mean': 'AVG',
            'total': 'SUM', 'sum': 'SUM',
            'maximum': 'MAX', 'max': 'MAX', 'highest': 'MAX', 'largest': 'MAX',
            'minimum': 'MIN', 'min': 'MIN', 'lowest': 'MIN', 'smallest': 'MIN',
        }
        for keyword, func in agg_map.items():
            if re.search(r"\b" + re.escape(keyword) + r"\b", q):
                intent['is_aggregation'] = True
                intent['agg_func'] = func
                break

        if intent['is_aggregation']:
            intent['intent_type'] = 'aggregation'
            for c in numeric_cols:
                if c.lower() in q or c.lower().replace('_', ' ') in q:
                    intent['agg_col'] = c
                    break
            if not intent['agg_col'] and numeric_cols:
                intent['agg_col'] = numeric_cols[0]

    # 5. GROUP BY detection. Only for list/count/aggregation intents that have not
    #    already resolved a dimension: ranking/comparison intents resolve their own
    #    group column (e.g. "top 10 products by revenue" groups by product, and the
    #    trailing "by revenue" is the metric, NOT the group dimension).
    group_phrases = [
        r"by\s+(\w+(?:\s+\w+)*)\s*$",
        r"per\s+(\w+(?:\s+\w+)*)",
        r"for each\s+(\w+(?:\s+\w+)*)",
        r"grouped by\s+(\w+(?:\s+\w+)*)",
        r"broken down by\s+(\w+(?:\s+\w+)*)",
        r"distribution\s+(?:by|of|per)\s+(\w+(?:\s+\w+)*)",
        r"group by\s+(\w+(?:\s+\w+)*)",
    ]
    if intent["intent_type"] in ("list", "count", "aggregation") and not intent["group_col"]:
        for phrase in group_phrases:
            m = re.search(phrase, q)
            if m:
                group_target = m.group(1).strip()
                intent["group_by_phrase"] = group_target
                for c in col_names:
                    if c.lower() == group_target or c.lower().replace("_", " ") == group_target:
                        intent["group_col"] = c
                        break
                if not intent["group_col"] and len(cat_cols) == 1:
                    intent["group_col"] = cat_cols[0]
                if intent["group_col"]:
                    break

    # Implicit aggregation: "show spending by category" -> SUM of the metric.
    # Only upgrade list intents; never override an explicit ranking/comparison/etc.
    if intent["intent_type"] == "list" and intent["group_col"] and not intent["is_aggregation"]:
        if any(w in q for w in ("spending", "spent", "spend", "amount", "costs", "sales", "revenue", "expenses", "total", "sum", "value")) and numeric_cols:
            intent["is_aggregation"] = True
            intent["agg_func"] = intent["agg_func"] or "SUM"
            intent["intent_type"] = "aggregation"
            if not intent["agg_col"]:
                intent["agg_col"] = numeric_cols[0]

    # 6. Sorting
    if any(w in q for w in ["top", "highest", "most", "best", "largest"]):
        intent["sort_order"] = "DESC"
    elif any(w in q for w in ["bottom", "lowest", "least", "worst", "smallest"]):
        intent["sort_order"] = "ASC"

    # 7. Limit
    limit_match = re.search(r"(?:top|bottom|first|last)\s+(\d+)", q)
    if limit_match:
        intent["limit"] = int(limit_match.group(1))
    elif "top" in q or "bottom" in q:
        intent["limit"] = 10

    # 8. Time series
    if any(w in q for w in ["trend", "over time", "monthly", "weekly", "daily", "timeline", "growth"]):
        intent["is_time_series"] = True
        if intent["intent_type"] == "list":
            intent["intent_type"] = "time_series"

    # 9. ANALYSIS / SUMMARY / OVERVIEW - catch-all for comprehensive business review
    analysis_keywords = [
        "analyze", "analysis", "summary", "overview", "describe",
        "tell me about", "business review", "business overview",
        "report", "review", "dashboard", "profile", "breakdown",
        "insights", "key insights", "key metrics", "key stats", "key figures", "key numbers",
    ]
    if intent["intent_type"] == "list":
        for kw in analysis_keywords:
            if kw in q:
                intent["intent_type"] = "analysis"
                break

    # 10. Correlation
    if any(w in q for w in ["correlation", "relationship", "vs", "versus", "scatter"]):
        intent["is_correlation"] = True
        if intent["intent_type"] == "list":
            intent["intent_type"] = "correlation"

    # 11. List all
    if any(w in q for w in ["all", "everything", "show me all", "list all"]):
        intent["is_list_all"] = True

    # 12. Numeric filter (WHERE): "customers with revenue above 10000",
    #     "find products priced less than 50", "revenue > 10000".
    filter_info = _extract_numeric_filter(q, col_names, metric_cols)
    if filter_info:
        intent["filter"] = filter_info

    return intent


# Word/phrase -> SQL comparison operator for numeric filters.
_FILTER_WORD_OPS = [
    ("greater than or equal to", ">="),
    ("less than or equal to", "<="),
    ("greater than", ">"),
    ("less than", "<"),
    ("more than", ">"),
    ("fewer than", "<"),
    ("at least", ">="),
    ("at most", "<="),
    ("above", ">"),
    ("over", ">"),
    ("exceeding", ">"),
    ("exceeds", ">"),
    ("beyond", ">"),
    ("below", "<"),
    ("under", "<"),
    ("equal to", "="),
    ("equals", "="),
]


def _extract_numeric_filter(q: str, col_names: list, numeric_cols: list):
    """Extract a single numeric comparison filter, or None.

    Handles both word operators ("revenue above 10000", "above 10000") and
    symbol operators ("revenue > 10000", "> 10000"). The target column is the
    one mentioned with the comparison, falling back to the preferred metric.
    """
    val = r"(\d[\d,]*(?:\.\d+)?)"

    def _resolve(col_word: str):
        if col_word:
            for c in col_names:
                if c.lower() == col_word or c.lower().replace("_", " ") == col_word:
                    return c
            for c in numeric_cols:
                if c.lower() in col_word or _simple_stem(c.lower()) in col_word or col_word in c.lower():
                    return c
        return _preferred_metric(numeric_cols) or (numeric_cols[0] if numeric_cols else None)

    for op_word, op in _FILTER_WORD_OPS:
        m = re.search(rf"\b(?P<col>[a-z][a-z0-9_ ]+?)\s+{re.escape(op_word)}\s+{val}\b", q)
        if m:
            col = _resolve(m.group("col").strip())
            if col:
                return {"column": col, "op": op, "value": float(m.groups()[-1].replace(",", ""))}
        m = re.search(rf"\b{re.escape(op_word)}\s+{val}\b", q)
        if m:
            col = _resolve("")
            if col:
                return {"column": col, "op": op, "value": float(m.groups()[-1].replace(",", ""))}

    m = re.search(rf"\b(?P<col>[a-z][a-z0-9_ ]+?)\s*(?P<op>>=|<=|>|<)\s*{val}\b", q)
    if m:
        col = _resolve(m.group("col").strip())
        if col:
            return {"column": col, "op": m.group("op"), "value": float(m.groups()[-1].replace(",", ""))}
    m = re.search(rf"\b(?P<op>>=|<=|>|<)\s*{val}\b", q)
    if m:
        col = _resolve("")
        if col:
            return {"column": col, "op": m.group("op"), "value": float(m.groups()[-1].replace(",", ""))}
    return None
