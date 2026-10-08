from docx import Document
from io import BytesIO

from app.formatting import DEFAULT_PROFILE
from conftest import run_apply, sign_up


def docx_bytes(text="Private report."):
    d = Document(); d.add_paragraph(text); s = BytesIO(); d.save(s); return s.getvalue()


def upload(c, text="Private report."):
    r = c.post("/api/uploads", files={"file": ("r.docx", docx_bytes(text))}); assert r.status_code == 200, r.text; return r.json()["id"]


def test_users_cannot_touch_each_others_documents(cloud):
    alice, bob = sign_up(cloud.app, "alice@example.com"), sign_up(cloud.app, "bob@example.com")
    doc = upload(alice)
    result = run_apply(alice, doc, DEFAULT_PROFILE)
    out = result["id"]
    body = {"profile": DEFAULT_PROFILE}
    for method, url, kw in [("post", f"/api/uploads/{doc}/audit", {"json": body}), ("post", f"/api/uploads/{doc}/apply", {"json": body}), ("get", f"/api/jobs/{result['jobId']}", {}), ("post", f"/api/outputs/{out}/pdf", {}),
                            ("post", f"/api/uploads/{doc}/learn-profile", {}), ("post", f"/api/uploads/{doc}/convert-to-docx", {}),
                            ("delete", f"/api/uploads/{doc}", {}), ("get", f"/api/outputs/{out}/document", {}),
                            ("get", f"/api/outputs/{out}/report", {})]:
        assert getattr(bob, method)(url, **kw).status_code == 404, url
    assert alice.get(f"/api/outputs/{out}/document").status_code == 200   # untouched by Bob's attempts
    assert alice.post(f"/api/uploads/{doc}/audit", json=body).status_code == 200


def test_upload_id_cannot_be_used_as_output_and_vice_versa(cloud):
    c = sign_up(cloud.app); doc = upload(c)
    out = run_apply(c, doc, DEFAULT_PROFILE)["id"]
    assert c.get(f"/api/outputs/{doc}/document").status_code == 404
    assert c.post(f"/api/uploads/{out}/audit", json={"profile": DEFAULT_PROFILE}).status_code == 404


def test_templates_are_private_and_not_overwritable(cloud):
    alice, bob = sign_up(cloud.app, "alice@example.com"), sign_up(cloud.app, "bob@example.com")
    saved = alice.post("/api/profiles", json={**DEFAULT_PROFILE, "id": "", "name": "Alice thesis"}).json()
    assert saved["id"] not in {"generic", "technical", "ieee"}
    assert saved["id"] in [p["id"] for p in alice.get("/api/profiles").json()]
    assert saved["id"] not in [p["id"] for p in bob.get("/api/profiles").json()]
    assert bob.delete(f"/api/profiles/{saved['id']}").status_code == 404
    hijack = bob.post("/api/profiles", json={**DEFAULT_PROFILE, "id": saved["id"], "name": "Bob copy"}).json()
    assert hijack["id"] != saved["id"]
    assert [p["name"] for p in alice.get("/api/profiles").json() if p["id"] == saved["id"]] == ["Alice thesis"]
    assert alice.post("/api/profiles", json={**saved, "name": "Alice thesis v2"}).json()["id"] == saved["id"]
    assert alice.delete(f"/api/profiles/{saved['id']}").status_code == 200


def test_jobs_and_usage_are_recorded(cloud):
    from app.db_models import Job, UsageEvent
    c = sign_up(cloud.app); doc = upload(c)
    result = run_apply(c, doc, DEFAULT_PROFILE)
    c.post(f"/api/uploads/{doc}/learn-profile")
    with cloud.app.state.session_factory() as db:
        job = db.get(Job, result["jobId"])
        assert job.status == "done" and job.output_doc_id == result["id"] and job.report_json["sourceId"] == doc
        assert sorted(e.event for e in db.query(UsageEvent)) == ["format", "learn"]
