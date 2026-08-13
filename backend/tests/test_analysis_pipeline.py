"""Tests for the data-sufficiency gate, question<->result validation, statistics
and multi-dataset JOIN analysis.

These lock in the core audit guarantees:

- a question whose required data does not exist is answered with an
  INSUFFICIENT explanation, NEVER a fabricated ``COUNT(*)`` (critical bug:
  "How many customers purchased two items together?" on a customer directory);
- measures (average/total/median...) only answer against real metric columns or
  a genuinely matching dataset domain;
- question<->result validation catches wrong-answer patterns post-execution;
- multi-dataset analysis uses only verified relationships and validated SQL.
"""
import json
import os

import pytest

from conftest import _unique, register_user, upload_csv

from ai.joins import build_multi_table_sql
from ai.result_check import validate_result
from ai.sql_generator import _local_statistical_sql
from ai.sql_validator import validate_sql_intent_multi
from ai.sufficiency import check_sufficiency

# ─── Schema fixtures (mirror the spec's Customers dataset) ─────────────────
CUSTOMERS_COLS = json.dumps([
    {"name": "CustomerID", "dtype": "int64", "type": "id", "unique": 91},
    {"name": "CustomerName", "dtype": "object", "type": "text", "unique": 91},
    {"name": "City", "dtype": "object", "type": "categorical", "unique": 69},
    {"name": "Country", "dtype": "object", "type": "categorical", "unique": 21},
])

ORDERS_COLS = json.dumps([
    {"name": "OrderID", "dtype": "int64", "type": "id", "unique": 40},
    {"name": "CustomerID", "dtype": "int64", "type": "id", "unique": 20},
    {"name": "ProductID", "dtype": "int64", "type": "id", "unique": 8},
    {"name": "Quantity", "dtype": "int64", "type": "metric", "unique": 4},
])

CUSTOMERS_ONLY = [{"name": "Customers", "table_name": "Customers", "columns_info": CUSTOMERS_COLS, "row_count": 91}]

CUSTOMERS_ORDERS = CUSTOMERS_ONLY + [
    {"name": "Orders", "table_name": "Orders", "columns_info": ORDERS_COLS, "row_count": 40}
]

RELS = [{
    "table_a": "Orders", "col_a": "CustomerID",
    "table_b": "Customers", "col_b": "CustomerID",
    "a_is_unique": False, "b_is_unique": True, "overlap": 0.9,
}]

CUSTOMERS_CSV = (
    "CustomerID,CustomerName,City,Country\n"
    "1,Alfreds,London,UK\n"
    "2,Ana,Berlin,Germany\n"
    "3,Antonio,Mexico City,Mexico\n"
    "4,Thomas,London,UK\n"
    "5,Han,London,UK\n"
    "6,Christina,Madrid,Spain\n"
    "7,Hanna,Munich,Germany\n"
)
ORDERS_CSV = (
    "OrderID,CustomerID,ProductID,Quantity\n"
    "101,1,11,2\n"
    "102,1,12,1\n"
    "103,2,11,3\n"
    "104,3,13,1\n"
    "105,4,11,2\n"
    "106,4,12,2\n"
    "107,5,14,1\n"
    "108,6,11,1\n"
    "109,7,12,4\n"
    "110,1,14,1\n"
)


class TestSufficiencyGate:
    """The critical wrong-answer patterns must never reach SQL generation."""

    def test_co_purchase_on_customer_directory_is_insufficient(self):
        v = check_sufficiency("How many customers purchased two items together?", CUSTOMERS_ONLY)
        assert v["status"] == "insufficient"
        assert any("order" in m for m in v["missing"])
        assert any("item" in m or "product" in m for m in v["missing"])
        assert v["message"]

    def test_missing_measure_is_insufficient(self):
        v = check_sufficiency("What is the average salary?", CUSTOMERS_ONLY)
        assert v["status"] == "insufficient"

    def test_missing_revenue_is_insufficient(self):
        v = check_sufficiency("What is the total revenue?", CUSTOMERS_ONLY)
        assert v["status"] == "insufficient"

    def test_plain_count_is_sufficient(self):
        assert check_sufficiency("How many customers are there?", CUSTOMERS_ONLY)["status"] == "sufficient"

    def test_record_count_is_sufficient(self):
        assert check_sufficiency("How many records are there?", CUSTOMERS_ONLY)["status"] == "sufficient"

    def test_grouped_entity_count_is_sufficient(self):
        assert check_sufficiency("Which country has the most customers?", CUSTOMERS_ONLY)["status"] == "sufficient"

    def test_explicit_column_reference_is_sufficient(self):
        assert check_sufficiency("What is the average customerid?", CUSTOMERS_ONLY)["status"] == "sufficient"

    def test_multi_table_co_purchase_is_sufficient(self):
        assert check_sufficiency("How many customers purchased two items together?", CUSTOMERS_ORDERS)["status"] == "sufficient"

    def test_multi_table_n_items_is_sufficient(self):
        assert check_sufficiency("How many customers purchased more than 2 products?", CUSTOMERS_ORDERS)["status"] == "sufficient"

    def test_multi_table_revenue_still_insufficient(self):
        assert check_sufficiency("What is the total revenue?", CUSTOMERS_ORDERS)["status"] == "insufficient"

    def test_dataset_domain_measure_is_sufficient(self):
        ds = [{"name": "daily_expenses", "table_name": "Expenses",
               "columns_info": json.dumps([
                   {"name": "Description", "dtype": "str", "type": "text", "unique": 17},
                   {"name": "Amount", "dtype": "float64", "type": "metric", "unique": 12},
               ]), "row_count": 17}]
        assert check_sufficiency("What is the average expense?", ds)["status"] == "sufficient"
        assert check_sufficiency("What are the top 5 expenses?", ds)["status"] == "sufficient"


class TestQuestionResultValidation:
    """Post-execution second net against wrong-answer patterns."""

    def test_measure_answered_with_count_is_invalid(self):
        v = validate_result("What is the average salary?", ["total_count"], [{"total_count": 90}], [],
                            'SELECT COUNT(*) AS total_count FROM "Customers"')
        assert v["status"] == "invalid"

    def test_plain_count_question_is_valid(self):
        v = validate_result("How many customers are there?", ["total_count"], [{"total_count": 90}], [],
                            'SELECT COUNT(*) AS total_count FROM "Customers"')
        assert v["status"] == "valid"

    def test_grouped_metric_by_dimension_is_valid(self):
        # Regression: "total quantity by country" (a grouped measure) must not
        # be rejected because the dimension column is named "country".
        v = validate_result("Show total quantity by country",
                            ["country", "total_quantity"],
                            [{"country": "UK", "total_quantity": 8.0},
                             {"country": "Germany", "total_quantity": 7.0}],
                            [{"name": "Country", "type": "categorical"}],
                            'SELECT b."country" AS "country", ROUND(SUM(a."quantity"), 2) AS total_quantity '
                            'FROM "Orders" a JOIN "Customers" b ON a."customerid" = b."customerid" '
                            'GROUP BY b."country" ORDER BY total_quantity DESC')
        assert v["status"] == "valid"

    def test_grouped_count_by_dimension_is_valid(self):
        # "total customers by country" is a legitimate grouped breakdown, not a
        # bare count answering a measure question.
        v = validate_result("Show total customers by country",
                            ["country", "total_customers"],
                            [{"country": "UK", "total_customers": 3},
                             {"country": "Germany", "total_customers": 4}],
                            [{"name": "Country", "type": "categorical"}],
                            'SELECT "country", COUNT(*) AS total_customers FROM "Customers" GROUP BY "country"')
        assert v["status"] != "invalid"

    def test_country_column_is_not_typed_as_count(self):
        from ai.semantics import analyze_sql_semantics
        sem = analyze_sql_semantics(
            'SELECT b."country" AS "country", SUM(a."quantity") AS total_quantity '
            'FROM "Orders" a JOIN "Customers" b ON a."customerid" = b."customerid" '
            'GROUP BY b."country"',
            ["country", "total_quantity"],
            [{"name": "Country", "type": "categorical"}],
            [{"country": "UK", "total_quantity": 8}])
        assert sem["country"] != "count"

    def test_co_purchase_answered_with_single_count_is_invalid(self):
        v = validate_result("Which products are purchased together?", ["times_together"], [{"times_together": 5}], [],
                            "SELECT COUNT(DISTINCT oid) AS times_together FROM \"Orders\"")
        assert v["status"] == "invalid"

    def test_co_purchase_with_item_pair_is_valid(self):
        v = validate_result("Which products are purchased together?",
                            ["product_a", "product_b", "times_together"],
                            [{"product_a": "X", "product_b": "Y", "times_together": 5}], [],
                            "SELECT a.item AS product_a, b.item AS product_b, COUNT(DISTINCT a.oid) AS times_together FROM \"Orders\" a JOIN \"Orders\" b ON b.oid = a.oid")
        assert v["status"] == "valid"

    def test_trend_question_without_date_dimension_is_invalid(self):
        v = validate_result("Show the revenue trend over time.", ["revenue"], [{"revenue": 100}], [],
                            "SELECT SUM(amount) AS revenue FROM \"Sales\"")
        assert v["status"] == "invalid"


SALARY_COLS = json.dumps([
    {"name": "CustomerID", "dtype": "int64", "type": "id", "unique": 91},
    {"name": "CustomerName", "dtype": "object", "type": "text", "unique": 91},
    {"name": "Salary", "dtype": "int64", "type": "metric", "unique": 80},
])

class TestStatisticsGeneration:
    def test_median(self):
        sql = _local_statistical_sql("What is the median salary?", "Customers", SALARY_COLS)
        assert "PERCENTILE_CONT(0.5)" in sql and "Salary" in sql

    def test_stddev(self):
        sql = _local_statistical_sql("What is the standard deviation of salary?", "Customers", SALARY_COLS)
        assert "STDDEV(" in sql

    def test_variance(self):
        sql = _local_statistical_sql("What is the variance of salary?", "Customers", SALARY_COLS)
        assert "VAR_SAMP(" in sql

    def test_percentile(self):
        sql = _local_statistical_sql("What is the 75th percentile salary?", "Customers", SALARY_COLS)
        assert "PERCENTILE_CONT(0.75)" in sql

    def test_stat_not_triggered_for_count(self):
        assert _local_statistical_sql("How many customers are there?", "Customers", SALARY_COLS) is None


class TestMultiTableValidator:
    def test_valid_join_passes(self):
        sql = ('SELECT b."CustomerName" AS "CustomerName", ROUND(SUM(a."Quantity"), 2) AS total_Quantity '
               'FROM "Orders" a JOIN "Customers" b ON b."CustomerID" = a."CustomerID" '
               'GROUP BY b."CustomerName" ORDER BY total_Quantity DESC LIMIT 100')
        v = validate_sql_intent_multi("total quantity by customer", sql, CUSTOMERS_ORDERS)
        assert v["valid"], v["issues"]

    def test_unknown_table_fails(self):
        sql = 'SELECT COUNT(*) AS c FROM "Other"'
        v = validate_sql_intent_multi("test", sql, CUSTOMERS_ORDERS)
        assert not v["valid"]

    def test_bad_qualified_column_fails(self):
        sql = ('SELECT b."CustomerName" FROM "Orders" a JOIN "Customers" b '
               'ON b."CustomerID" = a."CustomerID" WHERE b."DoesNotExist" > 1')
        v = validate_sql_intent_multi("test", sql, CUSTOMERS_ORDERS)
        assert not v["valid"]

    def test_subquery_plan_passes(self):
        sql = ('SELECT COUNT(DISTINCT t."CustomerID") AS customer_count FROM ('
               'SELECT "CustomerID", "OrderID", COUNT(DISTINCT "ProductID") AS items '
               'FROM "Orders" GROUP BY "CustomerID", "OrderID") t WHERE t.items >= 2')
        v = validate_sql_intent_multi("How many customers purchased two items together?", sql, CUSTOMERS_ORDERS)
        assert v["valid"], v["issues"]


class TestMultiTableJoins:
    def test_customers_with_n_items_pattern(self):
        plan = build_multi_table_sql("How many customers purchased two items together?", CUSTOMERS_ORDERS, RELS)
        assert plan and "COUNT(DISTINCT t.\"CustomerID\")" in plan["sql"]
        assert "items >= 2" in plan["sql"]

    def test_customers_with_more_than_n_items_pattern(self):
        plan = build_multi_table_sql("How many customers purchased more than 2 products?", CUSTOMERS_ORDERS, RELS)
        assert plan and "items >= 3" in plan["sql"] or (plan and "products > 2" in plan["sql"])

    def test_co_purchase_pair_pattern(self):
        plan = build_multi_table_sql("Which products are purchased together?", CUSTOMERS_ORDERS, RELS)
        assert plan
        assert 'product_a' in plan["sql"] and 'product_b' in plan["sql"]
        assert "HAVING COUNT(DISTINCT a.\"OrderID\") > 1" in plan["sql"]

    def test_grouped_metric_across_tables(self):
        plan = build_multi_table_sql("Show total quantity by customer", CUSTOMERS_ORDERS, RELS)
        assert plan and "JOIN" in plan["sql"]
        assert plan["tables_used"] == ["Orders", "Customers"]

    def test_no_pattern_for_simple_count(self):
        assert build_multi_table_sql("How many customers are there?", CUSTOMERS_ORDERS, RELS) is None


class TestEndToEnd:
    """The critical bug must not regress through the real API."""

    def test_co_purchase_question_on_customers_only_is_insufficient(self, client, user):
        ds = upload_csv(client, user, name=_unique("customers"))
        res = client.post("/api/query", json={
            "question": "How many customers purchased two items together?",
            "dataset_id": ds["id"],
        }, headers=user.headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["answer_status"] == "insufficient"
        assert body["generated_sql"] == ""
        assert body["data"] == []
        assert "order" in " ".join(body["summary"]["executive_summary"]).lower()
        assert body["ai_quality"]["overall_score"] < 100

    def test_missing_measure_is_insufficient(self, client, user):
        ds = upload_csv(client, user, name=_unique("customers"))
        res = client.post("/api/query", json={
            "question": "What is the average salary?",
            "dataset_id": ds["id"],
        }, headers=user.headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["answer_status"] == "insufficient"
        assert body["data"] == []

    def test_plain_count_still_answers(self, client, user):
        ds = upload_csv(client, user, name=_unique("customers"))
        res = client.post("/api/query", json={
            "question": "How many customers are there?",
            "dataset_id": ds["id"],
        }, headers=user.headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["answer_status"] == "answered"
        assert body["data"]

    def test_explicit_id_aggregate_answers(self, client, user):
        ds = upload_csv(client, user, name=_unique("customers"))
        res = client.post("/api/query", json={
            "question": "What is the average customerid?",
            "dataset_id": ds["id"],
        }, headers=user.headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["answer_status"] == "answered"

    def test_multi_dataset_join_end_to_end(self, client, user):
        customers = upload_csv(client, user, content=CUSTOMERS_CSV, name=_unique("customers"))
        orders = upload_csv(client, user, content=ORDERS_CSV, name=_unique("orders"))
        res = client.post("/api/query", json={
            "question": "How many customers purchased two items together?",
            "dataset_id": customers["id"],
            "dataset_ids": [orders["id"]],
        }, headers=user.headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["answer_status"] == "answered"
        assert body["data"], body["summary"]
        assert set(body["datasets_used"]) == {customers["table_name"], orders["table_name"]}
