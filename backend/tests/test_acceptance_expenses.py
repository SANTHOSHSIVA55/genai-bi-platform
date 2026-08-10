"""Acceptance tests for the AI Data Analyst behaviour using the spec's
``daily_expenses.xlsx`` fixture (17 transactions, total Rs 3,983).

Covers the 8 acceptance questions plus the schema-aware follow-up,
honest-confidence and pipeline-display guarantees.
"""
import io
import os

import pandas as pd
import pytest

from conftest import _unique

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "daily_expenses.xlsx")


def _upload_expenses(client, user):
    with open(FIXTURE, "rb") as f:
        files = {"file": ("daily_expenses.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        data = {"name": "daily_expenses"}
        res = client.post("/api/data/upload", files=files, data=data, headers=user.headers)
    assert res.status_code == 200, res.text
    return res.json()


def run_query(client, user, question, dataset_id):
    return client.post(
        "/api/query",
        json={"question": question, "dataset_id": dataset_id},
        headers=user.headers,
    )


class TestDailyExpenses:
    @pytest.fixture(autouse=True)
    def setup(self, client, user):
        self.dataset = _upload_expenses(client, user)
        self.id = self.dataset["id"]

    def _q(self, client, user, question):
        res = run_query(client, user, question, self.id)
        assert res.status_code == 200, (question, res.text)
        return res.json()

    def test_total_amount_spent(self, client, user):
        body = self._q(client, user, "What is the total amount spent?")
        assert body["generated_sql"].upper().startswith("SELECT")
        assert abs(body["data"][0]["sum_amount"] - 3983.0) < 0.01
        joined = " ".join(body["summary"]["executive_summary"])
        assert "3,983" in joined and "total" in joined.lower()

    def test_average_expense(self, client, user):
        body = self._q(client, user, "What is the average expense?")
        assert abs(body["data"][0]["avg_amount"] - 234.29) < 0.01

    def test_highest_category_total_spending(self, client, user):
        body = self._q(client, user, "Which category has the highest total spending?")
        joined = " ".join(body["summary"]["executive_summary"])
        assert "Food" in joined
        assert body["data"] and list(body["data"][0].values())[0] == "Food"

    def test_spending_by_category(self, client, user):
        body = self._q(client, user, "Show spending by category")
        assert len(body["data"]) == 4
        categories = {row["type"] for row in body["data"]}
        assert categories == {"Food", "Fun", "Office", "Investment"}
        assert body["chart_type"] in ("bar", "donut", "table", "kpi")

    def test_top_5_expenses(self, client, user):
        body = self._q(client, user, "What are the top 5 expenses?")
        assert len(body["data"]) == 5
        amounts = [row["amount"] for row in body["data"]]
        assert amounts == sorted(amounts, reverse=True)

    def test_key_insights(self, client, user):
        body = self._q(client, user, "Give me 5 key insights")
        sql = body["generated_sql"].upper()
        assert any(k in sql for k in ("AVG(", "SUM(", "COUNT(", "MIN(", "MAX("))
        assert body["data"][0]["total_records"] == 17
        assert body["summary"]["executive_summary"]

    def test_percentage_of_total(self, client, user):
        body = self._q(client, user, "What percentage of total spending is Food?")
        row = body["data"][0]
        assert abs(row["percentage"] - 31.38) < 0.1
        joined = " ".join(body["summary"]["executive_summary"])
        assert "Food" in joined and "%" in joined

    def test_trend_without_date_column_gives_guidance(self, client, user):
        body = self._q(client, user, "What is the trend over time?")
        assert body["generated_sql"] == ""
        assert body["chart_type"] == "table"
        message = body["summary"]["executive_summary"][0]
        assert "date/time" in message
        assert body["follow_up_questions"]

    def test_follow_ups_never_suggest_missing_date_columns(self, client, user):
        for question in [
            "What is the total amount spent?",
            "Give me 5 key insights",
            "Which category has the highest total spending?",
            "Show spending by category",
        ]:
            body = self._q(client, user, question)
            for fu in body["follow_up_questions"]:
                low = fu.lower()
                assert not any(w in low for w in ("trend", "over time", "timeline", "monthly", "weekly", "daily")), (question, fu)

    def test_confidence_is_honest_level(self, client, user):
        body = self._q(client, user, "What is the total amount spent?")
        assert body["ai_quality"]["confidence_level"] in ("High", "Medium", "Low")
        assert body["ai_quality"]["overall_score"] is not None

    def test_pipeline_stages_reported(self, client, user):
        body = self._q(client, user, "What is the total amount spent?")
        assert body["pipeline_stages"]
        assert body["pipeline_stages"][0]["status"] == "done"
        assert all(s["stage"] for s in body["pipeline_stages"])
        guidance = self._q(client, user, "What is the trend over time?")
        statuses = [s["status"] for s in guidance["pipeline_stages"]]
        assert "done" in statuses and "skipped" in statuses


class TestDatasetProfile:
    def test_profile_endpoint(self, client, user):
        dataset = _upload_expenses(client, user)
        res = client.get(f"/api/data/datasets/{dataset['id']}/profile", headers=user.headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["currency"] == "₹"
        assert body["overview"]["row_count"] == 17
        assert "amount" in body["overview"]["numeric_columns"]
        assert "type" in body["overview"]["categorical_columns"]
        assert body["insights"]

    def test_questions_endpoint_is_schema_aware(self, client, user):
        dataset = _upload_expenses(client, user)
        res = client.get(f"/api/data/datasets/{dataset['id']}/questions", headers=user.headers)
        assert res.status_code == 200, res.text
        body = res.json()
        all_q = body["overview"] + body["category"] + body["insights"]
        assert all_q
        assert any("amount" in q for q in body["overview"])
        assert any("type" in q for q in body["category"])


class TestSalesDataset:
    """The assistant must work with arbitrary datasets (not just daily_expenses)."""

    FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_sales_data.csv")

    @pytest.fixture(autouse=True)
    def setup(self, client, user):
        with open(self.FIXTURE, "rb") as f:
            files = {"file": ("sample_sales_data.csv", f, "text/csv")}
            res = client.post("/api/data/upload", files=files, data={"name": "sample_sales_data"}, headers=user.headers)
        assert res.status_code == 200, res.text
        self.dataset = res.json()
        self.id = self.dataset["id"]

    def _q(self, client, user, question):
        res = run_query(client, user, question, self.id)
        assert res.status_code == 200, (question, res.text)
        return res.json()

    def test_revenue_by_category_groups(self, client, user):
        body = self._q(client, user, "Show revenue by category")
        assert len(body["data"]) == 3
        assert "category" in body["data"][0]

    def test_percentage_of_total(self, client, user):
        body = self._q(client, user, "What percentage of total revenue is Electronics?")
        row = body["data"][0]
        assert "percentage" in row
        assert 0 < row["percentage"] <= 100
        joined = " ".join(body["summary"]["executive_summary"])
        assert "Electronics" in joined and "%" in joined

    def test_trend_with_date_column_gives_line(self, client, user):
        body = self._q(client, user, "Show the trend of revenue over time.")
        assert body["chart_type"] == "line"
        assert body["generated_sql"]
        assert body["data"]

    def test_highest_category_aggregate_rank(self, client, user):
        body = self._q(client, user, "Which category has the highest revenue?")
        row = body["data"][0]
        assert list(row.values())[0] in ("Electronics", "Home Office", "Grocery")
        assert "sum_revenue" in row

    def test_top_products_by_revenue(self, client, user):
        body = self._q(client, user, "What are the top 3 products by revenue?")
        assert len(body["data"]) == 3
        assert "revenue" in body["data"][0]
        revenues = [r["revenue"] for r in body["data"]]
        assert revenues == sorted(revenues, reverse=True)
