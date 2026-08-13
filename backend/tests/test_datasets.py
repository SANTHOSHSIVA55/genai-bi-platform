import io

import pandas as pd

from conftest import _unique, upload_csv


class TestUpload:
    def test_upload_csv(self, client, user):
        ds = upload_csv(client, user)
        assert ds["row_count"] == 5
        assert ds["column_count"] == 4
        assert ds["file_type"] == "csv"
        assert ds["name"]
        assert ds["table_name"].startswith("ds_")

    def test_upload_xlsx_with_datetime_column(self, client, user):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            pd.DataFrame({
                "Order Date": pd.to_datetime(["2024-01-15", "2024-02-01", None]),
                "Product": ["A", "B", "C"],
                "Amount": [10.5, 20.0, 30.25],
            }).to_excel(writer, sheet_name="Data", index=False)
        files = {"file": ("book.xlsx", io.BytesIO(buf.getvalue()), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        data = {"name": _unique("ds")}
        res = client.post("/api/data/upload", files=files, data=data, headers=user.headers)
        assert res.status_code == 200, res.text
        ds = res.json()
        assert ds["row_count"] == 3
        assert ds["column_count"] == 3
        assert ds["file_type"] == "xlsx"
        assert ds["columns_info"]

    def test_upload_csv_with_colliding_column_names(self, client, user):
        content = "item,ITEM,item \n1,10,1.5\n2,20,2.5\n3,30,3.5\n"
        files = {"file": ("dup.csv", io.BytesIO(content.encode()), "text/csv")}
        data = {"name": _unique("ds")}
        res = client.post("/api/data/upload", files=files, data=data, headers=user.headers)
        assert res.status_code == 200, res.text
        ds = res.json()
        assert ds["row_count"] == 3
        assert ds["column_count"] == 3
        assert ds["columns_info"]

    def test_upload_requires_auth(self, client):
        files = {"file": ("data.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")}
        res = client.post("/api/data/upload", files=files, data={"name": "x"})
        assert res.status_code == 401

    def test_upload_unsupported_extension(self, client, user):
        files = {"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
        res = client.post("/api/data/upload", files=files, data={"name": "x"}, headers=user.headers)
        assert res.status_code == 400

    def test_upload_empty_file(self, client, user):
        files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
        res = client.post("/api/data/upload", files=files, data={"name": "x"}, headers=user.headers)
        assert res.status_code == 400

    def test_upload_garbage_content(self, client, user):
        files = {"file": ("bad.csv", io.BytesIO(b"\x00\x01\x02 not csv at all \xff"), "text/csv")}
        res = client.post("/api/data/upload", files=files, data={"name": "x"}, headers=user.headers)
        assert res.status_code == 400


class TestList:
    def test_returns_own_datasets(self, client, user, second_user):
        upload_csv(client, user, name=_unique("mine"))
        other = upload_csv(client, second_user, name=_unique("theirs"))
        res = client.get("/api/data/datasets", headers=user.headers)
        assert res.status_code == 200
        ids = [d["id"] for d in res.json()["datasets"]]
        assert other["id"] not in ids

    def test_requires_auth(self, client):
        res = client.get("/api/data/datasets")
        assert res.status_code == 401


class TestDetail:
    def test_own_dataset(self, client, user, dataset):
        res = client.get(f"/api/data/datasets/{dataset['id']}", headers=user.headers)
        assert res.status_code == 200
        assert res.json()["id"] == dataset["id"]

    def test_other_users_dataset_forbidden(self, client, user, second_user, dataset):
        res = client.get(f"/api/data/datasets/{dataset['id']}", headers=second_user.headers)
        assert res.status_code == 403

    def test_unknown_dataset_404(self, client, user):
        res = client.get("/api/data/datasets/000000000000", headers=user.headers)
        assert res.status_code == 404


class TestPreview:
    def test_preview_returns_rows_and_columns(self, client, user, dataset):
        res = client.get(f"/api/data/datasets/{dataset['id']}/preview", headers=user.headers)
        assert res.status_code == 200
        body = res.json()
        assert "category" in body["columns"]
        assert len(body["sample_rows"]) == 5

    def test_preview_other_users_dataset_forbidden(self, client, user, second_user, dataset):
        res = client.get(f"/api/data/datasets/{dataset['id']}/preview", headers=second_user.headers)
        assert res.status_code == 403


class TestDelete:
    def test_delete_own_dataset(self, client, user, dataset):
        res = client.delete(f"/api/data/datasets/{dataset['id']}", headers=user.headers)
        assert res.status_code == 200
        res2 = client.get(f"/api/data/datasets/{dataset['id']}", headers=user.headers)
        assert res2.status_code == 404

    def test_delete_other_users_dataset_forbidden(self, client, user, second_user, dataset):
        res = client.delete(f"/api/data/datasets/{dataset['id']}", headers=second_user.headers)
        assert res.status_code == 403


class TestRows:
    """Server-side pagination/sort/search for the Data Explorer."""

    def test_rows_pagination(self, client, user, dataset):
        res = client.get(f"/api/data/datasets/{dataset['id']}/rows?page=1&page_size=2", headers=user.headers)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 5
        assert len(body["rows"]) == 2
        assert body["page"] == 1
        assert "category" in body["columns"]

    def test_rows_sort(self, client, user, dataset):
        res = client.get(
            f"/api/data/datasets/{dataset['id']}/rows?sort_by=revenue&sort_dir=desc&page_size=5",
            headers=user.headers,
        )
        assert res.status_code == 200
        body = res.json()
        revenues = [r["revenue"] for r in body["rows"]]
        assert revenues == sorted(revenues, reverse=True)
        assert body["sorted_by"] == "revenue"

    def test_rows_search(self, client, user, dataset):
        res = client.get(f"/api/data/datasets/{dataset['id']}/rows?search=Electronics", headers=user.headers)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 2
        assert all(r["category"] == "Electronics" for r in body["rows"])
        assert body["search"] == "Electronics"

    def test_rows_rejects_bad_sort_column(self, client, user, dataset):
        res = client.get(
            f"/api/data/datasets/{dataset['id']}/rows?sort_by=x;DROP TABLE users",
            headers=user.headers,
        )
        assert res.status_code == 200
        # Unknown sort columns are ignored, not executed.
        assert res.json()["sorted_by"] is None

    def test_rows_requires_owner(self, client, user, second_user, dataset):
        res = client.get(f"/api/data/datasets/{dataset['id']}/rows", headers=second_user.headers)
        assert res.status_code == 403

    def test_rows_requires_auth(self, client, dataset):
        res = client.get(f"/api/data/datasets/{dataset['id']}/rows")
        assert res.status_code == 401


class TestSecurity:
    def test_sql_injection_dataset_id(self, client, user):
        res = client.get("/api/data/datasets/1; DROP TABLE users;", headers=user.headers)
        assert res.status_code in (404, 422)

    def test_path_traversal_dataset_id(self, client, user):
        res = client.get("/api/data/datasets/../../etc/passwd", headers=user.headers)
        assert res.status_code in (404, 422)
