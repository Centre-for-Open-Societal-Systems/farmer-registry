"""The registry-side ingestion log: JSON lines, no file contents, and the
inline-versus-name-only split the enricher reports.

Needs nothing from openg2p_registry_core, so it runs anywhere.
"""

import base64
import json
import logging
import tempfile
import unittest
from pathlib import Path

from openg2p_registry_farmer_extension import ingest_log


class TestIngestLog(unittest.TestCase):
    def test_summarize_files_splits_arrived_from_name_only(self):
        photo = base64.b64encode(b"x" * 10).decode()
        submission = {
            "__id": "uuid:1",
            "farmer_photo_section": {"farmer_photo": {"__type": "File", "name": "me.jpg", "type": "image/jpeg", "data": photo}},
            "land_info": {"land_info_repeat": [
                {"land_certificate": "deed.PDF"},
                {"land_certificate": {"__type": "File", "name": "d2.pdf", "type": "application/pdf", "data": photo}},
            ]},
            "first_name": "Desta",
            "note": "see photo.jpg for details",
        }
        embedded, bare = ingest_log.summarize_files(submission)
        self.assertEqual([e["file_name"] for e in embedded], ["me.jpg", "d2.pdf"])
        self.assertEqual(embedded[0]["size_bytes"], 10)
        self.assertEqual(bare, ["deed.PDF"])
        # No contents in what the log is given.
        self.assertNotIn(photo, json.dumps([embedded, bare]))

    def test_events_are_json_lines_without_submission_data(self):
        logger = logging.getLogger(ingest_log.INGEST_LOGGER_NAME)
        saved = (list(logger.handlers), logger.propagate, ingest_log._configured)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "logs" / "odk-ingest.jsonl"
            try:
                ingest_log._configured = False
                ingest_log.configure(str(path))
                ingest_log.log_event(
                    "files", "file_rejected", "ERROR",
                    purpose="land_certificate", file_name="deed.exe", error="type not allowed",
                    payload={"first_name": "Desta"}, data="AAAA",
                )
                for handler in logger.handlers:
                    handler.flush()
                lines = path.read_text(encoding="utf-8").splitlines()
            finally:
                for handler in logger.handlers:
                    if handler not in saved[0]:
                        handler.close()
                logger.handlers[:] = saved[0]
                logger.propagate, ingest_log._configured = saved[1], saved[2]
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual((entry["event"], entry["severity"], entry["purpose"]), ("file_rejected", "ERROR", "land_certificate"))
        self.assertNotIn("payload", entry)
        self.assertNotIn("data", entry)
        self.assertNotIn("Desta", lines[0])


if __name__ == "__main__":
    unittest.main()
