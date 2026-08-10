"""Column classification and dataset capability helpers.

These helpers introspect a dataset's schema (``columns_info`` produced by
``data_cleaner``) to decide what the NL->SQL engine and insight generator may do
with it. They are intentionally conservative: when a dataset lacks date columns,
metrics or categories, capabilities are reduced rather than guessed.
"""
import json
from typing import Optional


def _parse_columns_info(columns_info: str) -> list:
    try:
        return json.loads(columns_info) if columns_info else []
    except json.JSONDecodeError:
        return []


# Names that denote a real numeric measure even when their values are fully
# unique (a per-row revenue/amount/salary column must never be mistaken for an
# ID just because every row has a different number).
_METRIC_NAME_HINTS = (
    "revenue", "sales", "amount", "price", "cost", "expense", "spend",
    "profit", "income", "salary", "units", "quantity", "qty", "count",
    "score", "rating", "total", "sum", "avg", "value", "margin", "share",
    "rate", "ratio", "volume", "gross", "net", "budget", "payout", "fee",
    "weight", "size", "year", "age", "duration", "time",
)


def _is_id_column(col_name: str, dtype: str = "", nunique: int = 0, total_rows: int = 0) -> bool:
    low = col_name.lower().strip()
    id_keywords = ["id", "code", "key", "sku", "uuid", "hash"]
    if any(kw in low for kw in id_keywords):
        return True
    # A fully-unique integer column is only ID-like when its name gives no
    # signal that it is a real measure (e.g. order_number, employee_number).
    if dtype in ("int64", "int32") and total_rows > 0 and nunique == total_rows and nunique > 10:
        if not any(hint in low for hint in _METRIC_NAME_HINTS):
            return True
    return False


def _get_column_type(col_name: str, dtype: str, nunique: int, total_rows: int) -> str:
    low = col_name.lower().strip()
    if _is_id_column(col_name, dtype, nunique, total_rows):
        return "id"
    if "date" in low or "time" in low:
        return "date"
    if dtype in ("float64", "int64", "float32", "int32"):
        return "metric"
    if dtype in ("object", "str", "string"):
        ratio = nunique / total_rows if total_rows > 0 else 1
        if ratio < 0.5:
            return "categorical"
        return "text"
    return "text"


def _get_dataset_capabilities(cols: list) -> dict:
    """Map available columns to business analysis capabilities."""
    col_names_lower = [c["name"].lower() for c in cols]
    capabilities = {
        "product_analysis": ["product", "item", "sku", "goods"],
        "sales_analysis": ["sales", "quantity", "volume", "units_sold", "sold", "orders", "qty"],
        "pricing_analysis": ["price", "cost", "unitprice", "unit_price", "rate", "fee"],
        "supplier_analysis": ["supplier", "vendor", "manufacturer", "distributor"],
        "customer_analysis": ["customer", "client", "buyer", "member"],
        "inventory_analysis": ["inventory", "stock", "on_hand", "reorder", "warehouse"],
        "financial_analysis": ["revenue", "profit", "margin", "income", "expense", "revenue"],
        "trend_analysis": ["date", "time", "month", "year", "quarter", "day"],
        "category_analysis": ["category", "type", "segment", "department", "group", "class"],
        "performance_analysis": ["score", "rating", "rank", "grade", "performance", "kpi"],
    }
    result = {}
    readable = []
    for domain, keywords in capabilities.items():
        found = any(any(kw in name for name in col_names_lower) for kw in keywords)
        result[domain] = found
        label = domain.replace("_", " ").title()
        if found:
            readable.append(label)
    result["readable_available"] = readable
    result["readable_unavailable"] = [
        d.replace("_", " ").title()
        for d, v in result.items()
        if not v and d not in ("readable_available", "readable_unavailable")
    ]
    return result


def _detect_business_intent(question: str) -> Optional[str]:
    """Detect the business domain from a natural language question."""
    q = question.lower()
    intent_map = {
        "sales_analysis": [
            "sales", "sell", "sold", "revenue", "quantity sold", "low sales",
            "best selling", "top selling", "units sold", "buying", "purchase",
        ],
        "pricing_analysis": [
            "price", "pricing", "cost", "expensive", "cheap", "affordable",
            " cheapest", "most expensive", "price range",
        ],
        "supplier_analysis": ["supplier", "vendor", "supply", "distributor"],
        "customer_analysis": ["customer", "client", "buyer", "member", "loyalty"],
        "inventory_analysis": ["inventory", "stock", "warehouse", "reorder", "stockout"],
        "financial_analysis": ["revenue", "profit", "margin", "financial", "income", "roi"],
        "product_analysis": ["product", "item", "goods", "merchandise"],
        "category_analysis": ["category", "segment", "department", "group", "classify"],
        "performance_analysis": ["performance", "score", "rating", "rank", "kpi", "metric"],
    }
    for intent_type, keywords in intent_map.items():
        if any(kw in q for kw in keywords):
            return intent_type
    return None


def _detect_business_intents(question: str) -> list:
    """Detect every business domain the question references (in order)."""
    q = question.lower()
    intent_map = {
        "sales_analysis": [
            "sales", "sell", "sold", "revenue", "quantity sold", "low sales",
            "best selling", "top selling", "units sold", "buying", "purchase",
        ],
        "pricing_analysis": [
            "price", "pricing", "cost", "expensive", "cheap", "affordable",
            " cheapest", "most expensive", "price range",
        ],
        "supplier_analysis": ["supplier", "vendor", "supply", "distributor"],
        "customer_analysis": ["customer", "client", "buyer", "member", "loyalty"],
        "inventory_analysis": ["inventory", "stock", "warehouse", "reorder", "stockout"],
        "financial_analysis": ["revenue", "profit", "margin", "financial", "income", "roi"],
        "product_analysis": ["product", "item", "goods", "merchandise"],
        "category_analysis": ["category", "segment", "department", "group", "classify"],
        "performance_analysis": ["performance", "score", "rating", "rank", "kpi", "metric"],
    }
    matched = []
    for intent_type, keywords in intent_map.items():
        if any(kw in q for kw in keywords):
            matched.append(intent_type)
    return matched


def _validate_business_question(question: str, cols: list) -> dict:
    """Check if the dataset can answer the business question asked."""
    capabilities = _get_dataset_capabilities(cols)
    candidates = _detect_business_intents(question)
    can_answer = True
    missing_capability = None
    business_intent = None
    if candidates:
        supported = [c for c in candidates if capabilities.get(c, False)]
        if supported:
            business_intent = supported[0]
        else:
            can_answer = False
            business_intent = candidates[0]
            missing_capability = business_intent
    return {
        "capabilities": capabilities,
        "business_intent": business_intent,
        "can_answer": can_answer,
        "missing_capability": missing_capability,
    }


def _get_missing_data_suggestion(missing_capability: str) -> str:
    """Generate a helpful suggestion for missing data domains."""
    suggestions = {
        "sales_analysis": "sales transaction data (quantity, revenue, orders)",
        "pricing_analysis": "pricing data (price, cost, rate)",
        "supplier_analysis": "supplier information (supplier, vendor)",
        "customer_analysis": "customer data (customer, client, demographics)",
        "inventory_analysis": "inventory data (stock, quantity on hand, reorder level)",
        "financial_analysis": "financial data (revenue, profit, margin)",
        "trend_analysis": "date or time columns for trend analysis",
        "product_analysis": "product information (product name, description, category)",
        "category_analysis": "category or segment columns",
        "performance_analysis": "performance metrics (score, rating, kpi)",
    }
    return suggestions.get(missing_capability, "additional business data relevant to your question")


def _simple_stem(word: str) -> str:
    w = word.lower().strip()
    if w.endswith('ies') and len(w) > 4:
        return w[:-3] + 'y'
    if w.endswith('ses') and len(w) > 4:
        return w[:-2]
    if w.endswith('s') and not w.endswith('ss') and len(w) > 3:
        return w[:-1]
    return w


def _match_col(text: str, col_names: list) -> Optional[str]:
    stem = _simple_stem(text.strip())
    for c in col_names:
        c_lower = c.lower()
        c_clean = c_lower.replace('_', ' ')
        if c_lower == stem or c_clean == stem:
            return c
        c_stem = _simple_stem(c_lower)
        if c_stem == stem:
            return c
        c_clean_stem = _simple_stem(c_clean)
        if c_clean_stem == stem:
            return c
    return None
