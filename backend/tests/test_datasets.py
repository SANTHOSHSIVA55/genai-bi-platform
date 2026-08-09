import io

from conftest import _unique, upload_csv


class TestUpload:
    def test_upload_csv(self, client, user):
        ds = upload_csv(client, user)
        assert ds["row_count"] == 5
        assert ds["column_count"] == 4
        assert ds["file_type"] == "csv"
        assert ds["name"]
        assert ds["table_name"].startswith("ds_")

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


class TestSecurity:
    def test_sql_injection_dataset_id(self, client, user):
        res = client.get("/api/data/datasets/1; DROP TABLE users;", headers=user.headers)
        assert res.status_code in (404, 422)

    def test_path_traversal_dataset_id(self, client, user):
        res = client.get("/api/data/datasets/../../etc/passwd", headers=user.headers)
        assert res.status_code in (404, 422)
