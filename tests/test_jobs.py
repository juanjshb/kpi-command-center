def test_bhd_job_permissions_single_active_run_and_history(client, headers, monkeypatch):
    monkeypatch.setattr("app.api.v1.jobs.run_bhd_location_job", lambda job_id: None)

    denied = client.post("/api/v1/jobs/bhd-locations", headers=headers["ANALYST"])
    assert denied.status_code == 403

    started = client.post("/api/v1/jobs/bhd-locations", headers=headers["OPERATOR"])
    assert started.status_code == 202
    payload = started.json()
    assert payload["job_key"] == "bhd_locations_sync"
    assert payload["status"] == "PENDING"

    duplicate = client.post("/api/v1/jobs/bhd-locations", headers=headers["ADMIN"])
    assert duplicate.status_code == 409

    listing = client.get("/api/v1/jobs", headers=headers["ANALYST"])
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == payload["id"]

    detail = client.get(f"/api/v1/jobs/{payload['id']}", headers=headers["ANALYST"])
    assert detail.status_code == 200
    assert detail.json()["message"] == "Job registrado; esperando ejecución"
