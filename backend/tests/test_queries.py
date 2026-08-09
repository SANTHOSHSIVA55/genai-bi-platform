import io

from conftest import _unique, upload_csv


def run_query(client, user, question, dataset_id):
    return client.post(
        "/api/query",
        json={"question": question, "dataset_id": dataset_id},
        headers=user.headers,
    )


class TestQuery:
    def test_analysis_intent_generates_aggregation_sql(self, client, user, dataset):
        res = run_query(client, user, "Analyze this dataset and give me a complete summary", dataset["id"])
        assert res.status_code == 200
        body = res.json()
        sql = body["generated_sql"].upper()
        assert any(k in sql for k in ("AVG(", "SUM(", "COUNT(", "MIN(", "MAX("))
        assert body["data"]
        assert body["summary"]["executive_summary"]
        assert isinstance(body["follow_up_questions"], list)

    def test_count_intent(self, client, user, dataset):
        res = run_query(client, user, "How many rows are in this dataset?", dataset["id"])
        assert res.status_code == 200
        assert "COUNT" in res.json()["generated_sql"].upper()

    def test_ranking_intent(self, client, user, dataset):
        res = run_query(client, user, "Show top 5 by revenue", dataset["id"])
        assert res.status_code == 200
        sql = res.json()["generated_sql"].upper()
        assert "LIMIT 5" in sql

    def test_list_intent(self, client, user, dataset):
        res = run_query(client, user, "List all data", dataset["id"])
        assert res.status_code == 200
        sql = res.json()["generated_sql"].upper()
        assert sql.startswith("SELECT")
        assert "FROM" in sql

    def test_query_requires_auth(self, client, dataset):
        res = client.post("/api/query", json={"question": "How many?", "dataset_id": dataset["id"]})
        assert res.status_code == 401

    def test_query_other_users_dataset_forbidden(self, client, user, second_user, dataset):
        res = run_query(client, second_user, "How many?", dataset["id"])
        assert res.status_code == 403

    def test_query_unknown_dataset(self, client, user):
        res = run_query(client, user, "How many?", "000000000000")
        assert res.status_code == 404

    def test_query_empty_question_rejected(self, client, user, dataset):
        res = run_query(client, user, "", dataset["id"])
        assert res.status_code == 422

    def test_query_too_short_question_rejected(self, client, user, dataset):
        res = run_query(client, user, "hi", dataset["id"])
        assert res.status_code == 422

    def test_query_sql_injection_question(self, client, user, dataset):
        res = run_query(client, user, "1; DROP TABLE users; SELECT * FROM users", dataset["id"])
        assert res.status_code in (200, 400)
        if res.status_code == 200:
            # table must still exist
            me = client.get("/api/auth/me", headers=user.headers)
            assert me.status_code == 200


class TestHistory:
    def test_history_records_queries(self, client, user, dataset):
        run_query(client, user, "Analyze this dataset", dataset["id"])
        run_query(client, user, "How many rows?", dataset["id"])
        res = client.get("/api/query/history", headers=user.headers)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 2
        assert all("question" in q for q in body["queries"])

    def test_history_requires_auth(self, client):
        res = client.get("/api/query/history")
        assert res.status_code == 401

    def test_history_is_user_scoped(self, client, user, second_user, dataset):
        run_query(client, user, "Analyze this dataset", dataset["id"])
        res = client.get("/api/query/history", headers=second_user.headers)
        assert res.status_code == 200
        assert res.json()["total"] == 0


class TestHealth:
    def test_health_public(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["database"] == "ok"
        assert "ai_provider" in body
