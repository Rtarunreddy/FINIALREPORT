"""Database-backed job queue. Web processes enqueue; workers (threads here, or `python -m app.worker`) claim and run jobs."""
from __future__ import annotations

import logging
import tempfile
import threading
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select, update

from . import pdf_export
from .db_models import Document, Job, User, utcnow
from .formatting import apply_profile
from .services import record_usage, store_document
from .summary import summarize

LOG = logging.getLogger(__name__)
GENERIC_ERROR = "This document contains unsupported formatting. Your original is unchanged; try a fresh DOCX saved from Word."


class JobRunner:
    def __init__(self, settings, session_factory, storage):
        self.settings, self.session_factory, self.storage = settings, session_factory, storage
        self._stop, self._wake, self._threads = threading.Event(), threading.Event(), []

    # ---- queue ----
    def claim(self) -> str | None:
        """Atomically move one queued job to running. Safe with several workers or processes."""
        with self.session_factory() as db:
            for job_id in db.scalars(select(Job.id).where(Job.status == "queued").order_by(Job.created_at).limit(5)).all():
                claimed = db.execute(update(Job).where(Job.id == job_id, Job.status == "queued")
                                     .values(status="running", started_at=utcnow(), attempts=Job.attempts + 1)).rowcount
                db.commit()
                if claimed == 1: return job_id
        return None

    def recover_stale(self) -> int:
        """Jobs left 'running' by a crashed process are failed so users are not stuck waiting."""
        limit = utcnow() - timedelta(minutes=self.settings.stale_job_minutes)
        with self.session_factory() as db:
            count = db.execute(update(Job).where(Job.status == "running", Job.started_at < limit)
                               .values(status="failed", error="This job was interrupted. Please format the report again.", finished_at=utcnow())).rowcount
            db.commit()
        return count

    def notify(self): self._wake.set()

    def run_one(self) -> bool:
        job_id = self.claim()
        if job_id is None: return False
        self.process(job_id); return True

    def run_pending(self, limit: int = 100) -> int:
        done = 0
        while done < limit and self.run_one(): done += 1
        return done

    # ---- execution ----
    def process(self, job_id: str):
        with self.session_factory() as db:
            job = db.get(Job, job_id)
            try:
                if job.kind == "pdf": self._export_pdf(db, job)
                else: self._format(db, job)
            except Exception as exc:
                db.rollback()
                if not isinstance(exc, ValueError): LOG.exception("Job %s failed", job_id)
                job = db.get(Job, job_id)
                job.status, job.finished_at = "failed", utcnow()
                job.error = str(exc)[:500] if isinstance(exc, ValueError) else GENERIC_ERROR
                db.commit()

    def _source(self, db, job, kind) -> Document:
        source = db.get(Document, job.source_doc_id) if job.source_doc_id else None
        if source is None or source.deleted_at is not None or (source.expires_at and source.expires_at < utcnow()) or source.kind != kind:
            raise ValueError("The file for this job is no longer available. Please upload it again.")
        return source

    def _format(self, db, job: Job):
        source, user = self._source(db, job, "upload"), db.get(User, job.user_id)
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.settings.data_dir) as folder, self.storage.local_copy(source.storage_key) as src:
            dest = Path(folder) / "formatted.docx"
            report = apply_profile(src, dest, job.params_json["profile"]); report["sourceId"] = source.id
            try: report["summary"] = summarize(src, dest)
            except Exception: LOG.exception("Before/after summary failed for job %s", job.id)  # informational only
            output = store_document(db, self.storage, self.settings, user, dest, Path(source.original_name).stem + "-formatted.docx", "output")
        job.status, job.report_json, job.output_doc_id, job.finished_at = "done", report, output.id, utcnow(); db.commit()
        record_usage(db, user, "format", job.id)

    def _export_pdf(self, db, job: Job):
        source, user = self._source(db, job, "output"), db.get(User, job.user_id)
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.settings.data_dir) as folder, self.storage.local_copy(source.storage_key) as src:
            copy = Path(folder) / "formatted.docx"; copy.write_bytes(src.read_bytes())
            pdf, engine = pdf_export.convert(self.settings, copy, Path(folder))
            report = {"engine": engine, "note": pdf_export.NOTE if engine == "libreoffice" else ""}
            try:
                import fitz
                with fitz.open(pdf) as document: report["pages"] = len(document)
            except Exception: pass
            output = store_document(db, self.storage, self.settings, user, pdf, "formatted-report.pdf", "output")
        job.status, job.report_json, job.output_doc_id, job.finished_at = "done", report, output.id, utcnow(); db.commit()
        record_usage(db, user, "export", job.id)

    # ---- threads ----
    def _loop(self):
        while not self._stop.is_set():
            try: worked = self.run_one()
            except Exception: LOG.exception("Worker loop error"); worked = False
            if not worked: self._wake.wait(self.settings.job_poll_seconds); self._wake.clear()

    def start(self):
        self.recover_stale()
        for index in range(max(0, self.settings.workers)):
            thread = threading.Thread(target=self._loop, name=f"report-ready-worker-{index}", daemon=True); thread.start(); self._threads.append(thread)

    def stop(self):
        self._stop.set(); self._wake.set()
        for thread in self._threads: thread.join(timeout=30)
        self._threads.clear()


def main():
    """Standalone worker: `python -m app.worker`. Run with REPORT_READY_WORKERS=0 on the web service."""
    import time
    from .config import Settings
    from .db import make_engine, make_session_factory
    from .storage import make_storage
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env(); engine = make_engine(settings.database_url)
    runner = JobRunner(settings, make_session_factory(engine), make_storage(settings)); runner.recover_stale()
    LOG.info("Report Ready worker started")
    while True:
        if not runner.run_one(): time.sleep(settings.job_poll_seconds)


if __name__ == "__main__": main()
