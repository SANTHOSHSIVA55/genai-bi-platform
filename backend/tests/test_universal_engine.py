"""Universal engine regression suite.

The assistant must work generically across file formats, schemas, domains and
question phrasings. These tests lock in the generic behaviours that fix the
historical Suppliers alias/currency bug and protect against regressions:

- grouped COUNT queries (``supplier_count`` from ``COUNT(*)``) validate,
  execute, and are formatted as plain integers (never currency);
- the SQL validator resolves SELECT aliases instead of mistaking them for
  missing physical columns;
- NL variations ("Which products sold the most?" / "best-selling products" /
  "top products") map to equivalent intents from the actual schema;
- numeric WHERE filters, percentages, dates and multi-format ingestion work.
"""
import io
import json
import os
import tempfile

import pandas as pd
import pytest

from ai.columns import _parse_columns_info
from ai.clarity import check_question_feasibility, detect_ambiguous_question, detect_unsupported_question
from ai.intent import _detect_intent
from ai.profile import detect_currency
from ai.semantics import analyze_sql_semantics, format_semantic_value
from ai.sql_generator import _canonicalize_table_refs, _local_nl_to_sql
from ai.sql_validator import validate_sql_intent
from data_cleaner import assess_data_quality, read_uploaded_file
from conftest import _unique, upload_csv

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
SUPPLIERS = os.path.join(FIXTURES, "suppliers.csv")

SUPPLIERS_COLS = json.dumps([
    {"name": "city", "dtype": "object", "type": "text", "unique": 3},
    {"name": "supplier_name", "dtype": "object", "type": "text", "unique": 3},
])

SALES_COLS = json.dumps([
    {"name": "product", "dtype": "object", "type": "categorical", "unique": 4},
    {"name": "region", "dtype": "object", "type": "categorical", "unique": 3},
    {"name": "revenue", "dtype": "int64", "type": "metric", "unique": 20},
    {"name": "units", "dtype": "int64", "type": "metric", "unique": 20},
    {"name": "sale_date", "dtype": "object", "type": "date", "unique": 20},
])


def run_query(client, user, question, dataset_id):
    return client.post(
        "/api/query",
        json={"question": question, "dataset_id": dataset_id},
        headers=user.headers,
    )


# ─── Unit: SQL validator alias matrix ──────────────────────────────────────
class TestValidatorAliasMatrix:
    """Arbitrary aliases must validate; aliases must never be treated as
    missing physical columns."""

    # (sql, columns_info) pairs: every alias variant against a schema where
    # the referenced physical columns exist.
    @pytest.mark.parametrize("sql,cols", [
        ('SELECT "city", COUNT(*) AS "supplier_count" FROM "t" GROUP BY "city" ORDER BY "supplier_count" DESC', SUPPLIERS_COLS),
        ('SELECT "city", COUNT(*) AS supplier_count FROM "t" GROUP BY "city" ORDER BY supplier_count DESC', SUPPLIERS_COLS),
        ('SELECT "region", SUM("revenue") AS total_revenue FROM "t" GROUP BY "region" ORDER BY total_revenue DESC', SALES_COLS),
        ('SELECT "region", AVG("price") AS average_price FROM "t" GROUP BY "region"', json.dumps([
            {"name": "region", "dtype": "object", "type": "categorical", "unique": 3},
            {"name": "price", "dtype": "float64", "type": "metric", "unique": 20},
        ])),
        ('SELECT COUNT(DISTINCT "customer_id") AS unique_customers FROM "t"', json.dumps([
            {"name": "customer_id", "dtype": "object", "type": "id", "unique": 50},
        ])),
        ('SELECT MAX("salary") AS highest_salary FROM "t"', json.dumps([
            {"name": "salary", "dtype": "int64", "type": "metric", "unique": 30},
        ])),
        ('SELECT MIN("amount") AS minimum_amount FROM "t"', json.dumps([
            {"name": "amount", "dtype": "float64", "type": "metric", "unique": 30},
        ])),
        ('SELECT "product", SUM("revenue") AS revenue_category FROM "t" GROUP BY "product"', SALES_COLS),
        ('SELECT "region", ROUND(SUM("revenue") * 100.0 / NULLIF(SUM("revenue"), 0), 2) AS share FROM "t"', SALES_COLS),
        ('SELECT "region", SUM(CASE WHEN "region" = \'North\' THEN "revenue" ELSE 0 END) AS north_revenue FROM "t" GROUP BY "region"', SALES_COLS),
    ])
    def test_aliases_validate(self, sql, cols):
        res = validate_sql_intent("show by region", sql, "t", cols)
        assert res["valid"] is True, (sql, res)
        assert "does not exist" not in " ".join(res["issues"]).lower()

    def test_table_ref_canonicalization(self):
        # LLM-generated SQL frequently changes the table name's case or quoting;
        # it must be rewritten to the canonical quoted form so the safety
        # validator (case-sensitive allowed_tables) accepts it.
        tbl = "ds_459e97392f"
        assert _canonicalize_table_refs(f'SELECT * FROM {tbl.upper()}', tbl) == f'SELECT * FROM "{tbl}"'
        assert _canonicalize_table_refs(f'SELECT * FROM "{tbl.upper()}"', tbl) == f'SELECT * FROM "{tbl}"'
        assert _canonicalize_table_refs(f'SELECT * FROM "ds_459e97392f"', tbl) == f'SELECT * FROM "ds_459e97392f"'
        # A different table name is left untouched.
        assert _canonicalize_table_refs('SELECT * FROM "other_table"', tbl) == 'SELECT * FROM "other_table"'
        # AI-style mangled reference then validates against the canonical table.
        sql = f'SELECT "city", COUNT(*) FROM {tbl.upper()} GROUP BY "city"'
        fixed = _canonicalize_table_refs(sql, tbl)
        res = validate_sql_intent("count by city", fixed, tbl, SUPPLIERS_COLS)
        assert res["valid"] is True, res

    def test_unknown_physical_column_still_rejected(self):
        sql = 'SELECT "totally_fake_col" FROM "t"'
        res = validate_sql_intent("show me the data", sql, "t", SALES_COLS)
        assert res["valid"] is False

    def test_aggregate_on_id_is_note_not_blocking(self):
        sql = 'SELECT "country", AVG("supplierid") AS avg_supplier_id FROM "t" GROUP BY "country"'
        cols = json.dumps([
            {"name": "country", "dtype": "object", "type": "categorical", "unique": 3},
            {"name": "supplierid", "dtype": "int64", "type": "id", "unique": 100},
        ])
        res = validate_sql_intent("average supplier id by country", sql, "t", cols)
        assert res["valid"] is True
        assert any("id" in (n or "").lower() for n in res.get("notes", []))


# ─── Unit: semantic typing / formatting ────────────────────────────────────
class TestResultSemantics:
    def test_supplier_count_is_integer_not_currency(self):
        sql = 'SELECT "city", COUNT(*) AS supplier_count FROM "t" GROUP BY "city" ORDER BY supplier_count DESC'
        cols_meta = _parse_columns_info(SUPPLIERS_COLS)
        sem = analyze_sql_semantics(sql, ["city", "supplier_count"], cols_meta,
                                    [{"city": "London", "supplier_count": 1}])
        assert sem["supplier_count"] == "count"
        assert format_semantic_value(1, sem["supplier_count"], "₹") == "1"
        assert format_semantic_value(1250, "currency", "₹") == "₹1,250"

    @pytest.mark.parametrize("name,expected", [
        ("supplier_count", "count"),
        ("total_count", "count"),
        ("unique_customers", "count"),
        ("total_revenue", "currency"),
        ("avg_price", "currency"),
        ("amount", "currency"),
        ("conversion_rate", "percentage"),
        ("completion_percentage", "percentage"),
        ("margin", "percentage"),
        ("units_sold", "number"),
        ("score", "number"),
    ])
    def test_infer_semantic_type_names(self, name, expected):
        from ai.semantics import infer_semantic_type
        assert infer_semantic_type(name) == expected

    def test_format_semantic_value_rules(self):
        assert format_semantic_value(1, "count", None) == "1"
        assert format_semantic_value(1234, "count", "₹") == "1,234"   # never currency
        assert format_semantic_value(1234.5, "currency", "$") == "$1,234.50"
        assert format_semantic_value(0.184, "percentage", None) == "0.18"
        assert format_semantic_value(None, "count", None) == ""


# ─── Unit: currency detection matrix ───────────────────────────────────────
class TestCurrencyDetection:
    @pytest.mark.parametrize("name,cols,expected", [
        ("Suppliers", ["city"], None),
        ("suppliers", ["city", "supplier_name"], None),
        ("Daily Expenses", ["amount", "type"], "₹"),
        ("daily_expenses", ["amount"], "₹"),
        ("Expenses", ["expense", "category"], "₹"),
        ("Sample Sales Data", ["revenue", "units_sold"], None),
        ("Employees", ["salary"], "₹"),
        ("Customers", ["customer_id"], None),
        ("Sales", ["amount"], None),  # neutral: no explicit currency marker
        ("Sales Data", ["revenue"], None),
    ])
    def test_detect_currency(self, name, cols, expected):
        assert detect_currency(name, cols) == expected


# ─── Unit: intent NL variations ────────────────────────────────────────────
class TestIntentVariations:
    def test_which_cities_most_suppliers(self):
        it = _detect_intent("Which cities have the most suppliers?",
                            ["city", "supplier_name"], [], ["city", "supplier_name"])
        assert it["intent_type"] == "count"
        assert it["group_col"] == "city"
        assert it["entity"] == "supplier_count"
        sql = _local_nl_to_sql("Which cities have the most suppliers?", "t", SUPPLIERS_COLS)
        assert 'COUNT(*)' in sql.upper() and '"city"' in sql and 'GROUP BY' in sql.upper()
        assert 'supplier_count' in sql

    def test_products_sold_the_most(self):
        cols = json.dumps([{"name": "product", "dtype": "object", "type": "text", "unique": 5}])
        it = _detect_intent("Which products sold the most?", ["product"], [], ["product"])
        assert it["intent_type"] == "count" and it["group_col"] == "product"
        assert 'COUNT(*)' in _local_nl_to_sql("Which products sold the most?", "t", cols).upper()

    def test_best_selling_products(self):
        cols = json.dumps([{"name": "product", "dtype": "object", "type": "text", "unique": 5}])
        sql = _local_nl_to_sql("What are the best-selling products?", "t", cols)
        assert 'COUNT(*)' in sql.upper() and "LIMIT 10" in sql.upper()

    def test_top_products_no_metric(self):
        cols = json.dumps([{"name": "product", "dtype": "object", "type": "text", "unique": 5}])
        sql = _local_nl_to_sql("What are the top products?", "t", cols)
        assert 'COUNT(*)' in sql.upper() and 'AS product_count' in sql

    def test_top_products_with_metric_ranks_by_metric(self):
        sql = _local_nl_to_sql("What are the top products?", "t", SALES_COLS)
        assert "COUNT(*)" not in sql.upper()
        assert '"revenue"' in sql and 'ORDER BY' in sql.upper()

    def test_top_5_by_revenue_is_clean_sort(self):
        sql = _local_nl_to_sql("Show top 5 by revenue", "t", SALES_COLS)
        assert 'LIMIT 5' in sql.upper()
        assert '"revenue", "revenue"' not in sql  # no degenerate group==metric select

    def test_metric_noun_maps_to_composite_column_token(self):
        # "units" must resolve to the units_sold column, not fall back to
        # revenue via the preferred-metric default.
        cols = json.dumps([
            {"name": "product", "dtype": "object", "type": "categorical", "unique": 4},
            {"name": "category", "dtype": "object", "type": "categorical", "unique": 3},
            {"name": "revenue", "dtype": "int64", "type": "metric", "unique": 20},
            {"name": "units_sold", "dtype": "int64", "type": "metric", "unique": 20},
            {"name": "sale_date", "dtype": "object", "type": "date", "unique": 20},
        ])
        it = _detect_intent("Which product sold the most units?", ["product", "category", "revenue", "units_sold", "sale_date"],
                            ["revenue", "units_sold"], ["product", "category"])
        assert it["agg_col"] == "units_sold"
        sql = _local_nl_to_sql("Which product sold the most units?", "t", cols)
        assert 'SUM("units_sold")' in sql and '"revenue"' not in sql

    def test_match_col_token_prefix(self):
        # _match_col keeps exact/stem semantics only...
        from ai.columns import _match_col
        assert _match_col("units", ["revenue", "units_sold", "net_revenue"]) is None
        assert _match_col("net revenue", ["revenue", "units_sold", "net_revenue"]) == "net_revenue"
        # ...while the metric matcher additionally resolves composite tokens.
        from ai.intent import _match_metric
        assert _match_metric("units", ["revenue", "units_sold"]) == "units_sold"
        assert _match_metric("revenue", ["revenue", "units_sold"]) == "revenue"
        assert _match_metric("net revenue", ["revenue", "net_revenue"]) == "net_revenue"
        assert _match_metric("price", ["revenue", "units_sold"]) is None
        # The rule must never fire against text/entity nouns in the metric slot:
        assert _match_metric("suppliers", ["revenue", "units_sold"]) is None

    def test_city_most_orders_uses_order_count_alias(self):
        cols = json.dumps([
            {"name": "city", "dtype": "object", "type": "text", "unique": 3},
            {"name": "order_id", "dtype": "object", "type": "id", "unique": 50},
        ])
        sql = _local_nl_to_sql("Which city had the most orders?", "t", cols)
        assert 'COUNT(*)' in sql.upper() and 'order_count' in sql

    def test_numeric_where_filters(self):
        assert '"revenue" > 10000' in _local_nl_to_sql("Find customers with revenue above 10000", "t", SALES_COLS)
        assert '"revenue" > 5000' in _local_nl_to_sql("Which products have revenue greater than 5000?", "t", SALES_COLS)
        assert '"units" < 50' in _local_nl_to_sql("How many records have units less than 50?", "t", SALES_COLS)
        assert '"revenue" >= 100' in _local_nl_to_sql("products with revenue at least 100", "t", SALES_COLS)

    def test_revenue_by_region_groups_and_sums(self):
        sql = _local_nl_to_sql("Show revenue by region", "t", SALES_COLS)
        assert 'SUM("revenue")' in sql and 'GROUP BY "region"' in sql

    def test_percentage_of_metric_by_dimension(self):
        sql = _local_nl_to_sql("What percentage of revenue comes from each region?", "t", SALES_COLS)
        assert '"region"' in sql and 'percentage' in sql
        assert '* 100.0' in sql and 'NULLIF' in sql
        assert 'GROUP BY "region"' in sql
        # by-variant
        sql2 = _local_nl_to_sql("What percentage of revenue by region?", "t", SALES_COLS)
        assert '"region"' in sql2 and 'GROUP BY "region"' in sql2

    def test_unique_numeric_revenue_not_mistaken_for_id(self):
        from ai.columns import _get_column_type
        assert _get_column_type("revenue", "int64", 100, 100) == "metric"
        assert _get_column_type("employee_number", "int64", 100, 100) == "id"


# ─── Unit: ambiguity / unsupported-question detection ─────────────────────
class TestClarity:
    AMBIG_COLS = [
        {"name": "product", "dtype": "object", "type": "categorical", "unique": 4},
        {"name": "revenue", "dtype": "int64", "type": "metric", "unique": 15},
        {"name": "units", "dtype": "int64", "type": "metric", "unique": 15},
        {"name": "rating", "dtype": "float64", "type": "metric", "unique": 8},
    ]

    def test_ambiguous_best_product_asks_for_metric(self):
        msg = detect_ambiguous_question("What is the best product?", self.AMBIG_COLS)
        assert msg and "revenue" in msg and "units" in msg and "rating" in msg
        assert "by revenue" in msg

    def test_explicit_metric_not_ambiguous(self):
        assert detect_ambiguous_question("What is the best product by revenue?", self.AMBIG_COLS) is None
        assert detect_ambiguous_question("Which product has the highest revenue?", self.AMBIG_COLS) is None
        assert detect_ambiguous_question("What are the best-selling products?", self.AMBIG_COLS) is None

    def test_top_products_listing_not_ambiguous(self):
        assert detect_ambiguous_question("What are the top products?", self.AMBIG_COLS) is None

    def test_unsupported_why_questions(self):
        assert detect_unsupported_question("Why did sales decrease?", self.AMBIG_COLS)
        assert detect_unsupported_question("Why is revenue so low?", self.AMBIG_COLS)

    def test_supported_questions_not_flagged(self):
        assert detect_unsupported_question("What is the total revenue?", self.AMBIG_COLS) is None
        assert detect_unsupported_question("Which region has the highest revenue?", self.AMBIG_COLS) is None

    def test_feasibility_gate(self):
        assert check_question_feasibility("What is the best product?", self.AMBIG_COLS)["guidance"]
        assert check_question_feasibility("What is the total revenue?", self.AMBIG_COLS)["guidance"] is None


# ─── Unit: multi-format ingestion ──────────────────────────────────────────
class TestMultiFormatIngestion:
    def test_tsv(self):
        content = "product\trevenue\nA\t100\nB\t200\n"
        df = read_uploaded_file(content.encode(), "sales.tsv")
        assert list(df.columns) == ["product", "revenue"]
        assert len(df) == 2

    def test_json_array_of_records(self):
        content = b'[{"product": "A", "revenue": 100}, {"product": "B", "revenue": 200}]'
        df = read_uploaded_file(content, "sales.json")
        assert list(df.columns) == ["product", "revenue"]
        assert len(df) == 2

    def test_json_wrapped_records(self):
        content = json.dumps({"data": [{"a": 1}, {"a": 2}]}).encode()
        df = read_uploaded_file(content, "data.json")
        assert list(df.columns) == ["a"] and len(df) == 2

    def test_multi_sheet_xlsx_picks_most_data_rich(self):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            pd.DataFrame({"hdr": [1, 2], "junk": ["x", "y"]}).to_excel(writer, sheet_name="small", index=False)
            pd.DataFrame({"a": [1, 2, 3, 4], "b": [5, 6, 7, 8]}).to_excel(writer, sheet_name="big", index=False)
        df = read_uploaded_file(buf.getvalue(), "book.xlsx")
        assert list(df.columns) == ["a", "b"]
        assert len(df) == 4

    def test_csv_fallback_encoding(self):
        content = "name,value\n" + "caf\xe9,1\n".encode("latin-1").decode("latin-1") + "\n"
        df = read_uploaded_file(content.encode("latin-1"), "data.csv")
        assert len(df) == 1

    def test_data_quality_flags_duplicates_and_missing(self):
        content = "a,b\n1,x\n1,x\n,\n3,z\n"
        df = read_uploaded_file(content.encode(), "q.csv")
        q = assess_data_quality(df)
        assert q["duplicate_rows"] == 1
        assert q["missing_cells"] >= 1
        assert q["warnings"]
        assert q["issues_count"] > 0


# ─── End-to-end API: Suppliers regression ──────────────────────────────────
class TestSuppliersEndToEnd:
    @pytest.fixture(autouse=True)
    def setup(self, client, user):
        with open(SUPPLIERS, "rb") as f:
            files = {"file": ("suppliers.csv", f, "text/csv")}
            res = client.post("/api/data/upload", files=files, data={"name": "suppliers"}, headers=user.headers)
        assert res.status_code == 200, res.text
        self.dataset = res.json()
        self.id = self.dataset["id"]

    def _q(self, client, user, question):
        res = run_query(client, user, question, self.id)
        assert res.status_code == 200, (question, res.text)
        return res.json()

    def test_suppliers_query(self, client, user):
        body = self._q(client, user, "Which cities have the most suppliers?")
        sql = body["generated_sql"]
        assert 'COUNT(*)' in sql.upper()
        assert 'GROUP BY' in sql.upper()
        assert body["validation_info"]["valid"] is True
        assert not body["validation_info"]["issues"]
        rows = body["data"]
        assert len(rows) == 3
        cities = {r["city"] for r in rows}
        assert cities == {"Ann Arbor", "New Orleans", "London"}
        count_key = next(k for k in rows[0] if k != "city")
        assert all(r[count_key] == 1 for r in rows)
        assert isinstance(rows[0][count_key], int)
        assert body["semantic_types"][count_key] == "count"
        assert body["currency"] is None
        assert body["chart_type"] == "bar"

    def test_suppliers_summary_no_fake_insights(self, client, user):
        body = self._q(client, user, "Which cities have the most suppliers?")
        joined = " ".join(body["summary"]["executive_summary"])
        assert "₹" not in joined
        assert "Ann Arbor" in joined or "supplier" in joined.lower()
        assert body["follow_up_questions"]
        assert all("does not exist" not in fu.lower() for fu in body["follow_up_questions"])

    def test_suppliers_via_generic_phrasings(self, client, user):
        for q in ("Which cities have the most suppliers?", "What are the top suppliers by city?"):
            body = self._q(client, user, q)
            assert body["validation_info"]["valid"] is True
            assert body["data"]

    def test_count_semantics_never_currency(self, client, user):
        body = self._q(client, user, "How many suppliers are there?")
        row = body["data"][0]
        key = list(row)[0]
        assert row[key] == 3
        assert body["semantic_types"][key] == "count"
        assert body["currency"] is None


# ─── End-to-end API: sales-style dataset ───────────────────────────────────
SALES_CSV = (
    "product,category,revenue,units_sold,sale_date\n"
    "Widget A,Electronics,125000,3200,2024-01-01\n"
    "Widget B,Home Office,98000,2800,2024-01-05\n"
    "Widget C,Electronics,87000,2100,2024-01-10\n"
    "Widget D,Home Office,72000,1900,2024-01-15\n"
    "Widget E,Furniture,65000,1700,2024-01-20\n"
    "Widget F,Furniture,54000,1400,2024-01-25\n"
    "Widget G,Home Office,43000,1100,2024-01-28\n"
    "Widget H,Electronics,38000,900,2024-01-30\n"
    "Widget I,Furniture,25000,600,2024-02-02\n"
    "Widget J,Electronics,15000,400,2024-02-05\n"
    "Widget K,Electronics,12000,350,2024-02-10\n"
    "Widget L,Home Office,9900,300,2024-02-12\n"
    "Widget M,Furniture,7500,250,2024-02-15\n"
    "Widget N,Home Office,6100,200,2024-02-18\n"
    "Widget O,Electronics,4800,150,2024-02-20\n"
)


class TestSalesEngine:
    @pytest.fixture(autouse=True)
    def setup(self, client, user):
        self.dataset = upload_csv(client, user, content=SALES_CSV, name=_unique("sales"))
        self.id = self.dataset["id"]

    def test_upload_response_includes_data_quality(self, client, user):
        dataset = upload_csv(client, user, content="a,b\n1,x\n1,x\n", name=_unique("dq"))
        assert dataset["data_quality"]["duplicate_rows"] == 1
        assert dataset["data_quality"]["warnings"]

    def _q(self, client, user, question):
        res = run_query(client, user, question, self.id)
        assert res.status_code == 200, (question, res.text)
        return res.json()

    def test_total_revenue(self, client, user):
        body = self._q(client, user, "What is the total revenue?")
        row = body["data"][0]
        assert abs(row["sum_revenue"] - 662300.0) < 0.01
        assert body["semantic_types"]["sum_revenue"] == "currency"
        assert body["currency"] is None  # neutral when ambiguous dataset name
        assert "662,300" in " ".join(body["summary"]["executive_summary"])

    def test_revenue_by_category(self, client, user):
        body = self._q(client, user, "Show revenue by category")
        assert len(body["data"]) == 3
        joined = " ".join(body["summary"]["executive_summary"])
        assert "Electronics" in joined

    def test_monthly_trend(self, client, user):
        body = self._q(client, user, "Show the trend of revenue over time.")
        assert body["generated_sql"]
        assert body["data"]
        assert body["chart_type"] in ("line", "bar")

    def test_percentage_of_total(self, client, user):
        body = self._q(client, user, "What percentage of total revenue is Electronics?")
        row = body["data"][0]
        assert "percentage" in row
        assert 0 < row["percentage"] <= 100
        assert body["semantic_types"]["percentage"] == "percentage"
        joined = " ".join(body["summary"]["executive_summary"])
        assert "Electronics" in joined and "%" in joined

    def test_where_filter(self, client, user):
        body = self._q(client, user, "Which products have revenue greater than 90000?")
        assert '"revenue" > 90000' in body["generated_sql"]
        assert body["data"] and all(r["revenue"] > 90000 for r in body["data"])

    def test_zero_result_query_returns_empty_not_error(self, client, user):
        body = self._q(client, user, "Which products have revenue greater than 99999999?")
        assert body["validation_info"]["valid"] is True
        assert body["data"] == []

    def test_top_products_by_revenue(self, client, user):
        body = self._q(client, user, "What are the top 3 products by revenue?")
        assert len(body["data"]) == 3
        revenues = [r["revenue"] for r in body["data"]]
        assert revenues == sorted(revenues, reverse=True)

    def test_ambiguous_best_product_returns_guidance(self, client, user):
        body = self._q(client, user, "What is the best product?")
        assert body["generated_sql"] == ""
        assert body["data"] == []
        assert body["chart_type"] == "table"
        message = body["summary"]["executive_summary"][0]
        assert "measures" in message and "revenue" in message

    def test_unsupported_why_returns_guidance(self, client, user):
        body = self._q(client, user, "Why did sales decrease?")
        assert body["generated_sql"] == ""
        message = body["summary"]["executive_summary"][0]
        assert "can't determine why" in message
