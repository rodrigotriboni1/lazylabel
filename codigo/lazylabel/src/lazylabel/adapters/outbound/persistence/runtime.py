"""Local clocks, identifiers and privacy-safe selected-field digests."""
import hashlib
import json
import time
from datetime import datetime, timezone
from uuid import uuid4


class LocalRuntime:
    def new_id(self):
        return uuid4().hex

    def now(self):
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    def monotonic(self):
        return time.monotonic()

    def selected_digest(self, values):
        encoded = json.dumps(values, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), default=str)
        return hashlib.sha256(encoded.encode('utf-8')).hexdigest()

    def record_ref(self, source_name, record_id):
        return hashlib.sha256('{}\0{}'.format(source_name, record_id).encode('utf-8')).hexdigest()
