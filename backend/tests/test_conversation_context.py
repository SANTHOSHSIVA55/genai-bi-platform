import io

from conftest import _unique, upload_csv
from ai.context import resolve_followup_question

ID_CSV_CONTENT = (
    "supplier_id,supplier_name,revenue,region\n"
    "101,Acme,1200,North\n"
    "102,Globex,340,South\n"
    "103,Initech,890,East\n"
    "104,Umbrella,1500,West\n"
)


def run_query(client, user, question, dataset_id, context=None):
    payload = {"question": question, "dataset_id": dataset_id}
    if context is not None:
        payload["context"] = context
    return client.post("/api/query", json=payload, headers=user.headers)


def upload_id_csv(client, user):
    return upload_csv(client, user, content=ID_CSV_CONTENT)


class TestContextResolver:
    """Pure unit tests for the follow-up question resolver."""

    COLS = [
        {"name": "category", "type": "categorical"},
        {"name": "region", "type": "categorical"},
        {"name": "revenue", "type": "metric"},
        {"name": "units", "type": "metric"},
    ]

    PREVIOUS = {
        "question": "What is total revenue?",
        "sql": 'SELECT SUM("revenue") AS sum_revenue FROM "ds_abc"',
        "columns": ["sum_revenue"],
    }

    def test_implicit_groupby_followup(self):
        assert resolve_followup_question(
            "Show me by region", self.PREVIOUS, self.COLS
        ) == "Show total revenue by region"

    def test_superlative_followup(self):
        assert resolve_followup_question(
            "Which one is worst?", self.PREVIOUS, self.COLS
        ) == "Which category has the lowest revenue?"

    def test_why_followup_uses_comparison(self):
        assert resolve_followup_question(
            "Why did revenue decrease?", self.PREVIOUS, self.COLS
        ) == "Show total revenue by category"

    def test_top_n_followup(self):
        assert resolve_followup_question(
            "top 5", self.PREVIOUS, self.COLS
        ) == "Show top 5 category by revenue"

    def test_details_followup(self):
        assert resolve_followup_question(
            "show me the details", self.PREVIOUS, self.COLS
        ) == "Show total revenue by category"

    def test_self_contained_question_untouched(self):
        assert resolve_followup_question(
            "What is total revenue?", self.PREVIOUS, self.COLS
        ) == "What is total revenue?"

    def test_new_topic_untouched(self):
        assert resolve_followup_question(
            "Show suppliers by country", self.PREVIOUS, self.COLS
        ) == "Show suppliers by country"


class TestConversationContextApi:
    """End-to-end: a follow-up question must be grounded in the last turn."""

    def test_followup_groups_by_prior_metric(self, client, user, dataset):
        first = run_query(client, user, "What is total revenue?", dataset["id"])
        assert first.status_code == 200

        context = [
            {
                "question": first.json()["question"],
                "sql": first.json()["generated_sql"],
                "columns": list(first.json()["data"][0].keys()) if first.json()["data"] else [],
                "dataset_id": dataset["id"],
            }
        ]
        res = run_query(client, user, "show me by region", dataset["id"], context=context)
        assert res.status_code == 200
        body = res.json()
        assert body["question"] == "Show total revenue by region"
        assert "GROUP BY" in body["generated_sql"].upper()
        assert "REGION" in body["generated_sql"].upper()

    def test_followup_without_context_stays_grounded(self, client, user, dataset):
        # No context: the bare "by region" cannot be resolved to a grouped
        # comparison and must never fabricate one.
        res = run_query(client, user, "by region", dataset["id"])
        assert res.status_code == 200
        assert "GROUP BY" not in res.json()["generated_sql"].upper()


class TestIdentifierAggregationGate:
    """SUM/AVERAGE of an identifier column must be refused with guidance."""

    def test_sum_of_id_returns_guidance(self, client, user):
        ds = upload_id_csv(client, user)
        res = run_query(client, user, "What is the total supplier_id?", ds["id"])
        assert res.status_code == 200
        body = res.json()
        assert body["generated_sql"] == ""
        assert body["answer_status"] == "clarification"
        description = body["chart_config"].get("description", "")
        assert "identifier" in description.lower()
        assert "supplier_id" in description.lower()

    def test_count_of_id_still_allowed(self, client, user):
        ds = upload_id_csv(client, user)
        res = run_query(client, user, "How many supplier ids are there?", ds["id"])
        assert res.status_code == 200
        assert "COUNT" in res.json()["generated_sql"].upper()

    def test_sum_of_metric_on_id_dataset_allowed(self, client, user):
        ds = upload_id_csv(client, user)
        res = run_query(client, user, "What is total revenue by region?", ds["id"])
        assert res.status_code == 200
        body = res.json()
        assert "GROUP BY" in body["generated_sql"].upper()


class TestQueryCache:
    def test_second_identical_query_hits_cache(self, client, user, dataset):
        first = run_query(client, user, "What is total revenue?", dataset["id"])
        assert first.status_code == 200
        assert first.json()["pipeline_timings_ms"].get("cached") is False

        second = run_query(client, user, "What is total revenue?", dataset["id"])
        assert second.status_code == 200
        timings = second.json()["pipeline_timings_ms"]
        assert timings.get("cached") is True
        assert timings.get("total_ms", 0) >= 0

    def test_cache_cleared_on_new_upload(self, client, user, dataset):
        run_query(client, user, "What is total revenue?", dataset["id"])
        upload_csv(client, user)  # new upload invalidates the cache
        again = run_query(client, user, "What is total revenue?", dataset["id"])
        assert again.status_code == 200
        assert again.json()["pipeline_timings_ms"].get("cached") is False

    def test_cache_respects_question(self, client, user, dataset):
        run_query(client, user, "What is total revenue?", dataset["id"])
        different = run_query(client, user, "What is total units?", dataset["id"])
        assert different.status_code == 200
        assert different.json()["pipeline_timings_ms"].get("cached") is False
