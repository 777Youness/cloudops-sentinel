"""Print the OpenAPI document without starting a server.

    uv run python -m sentinel.openapi_export > ../frontend/src/api/openapi.json

The frontend generates its TypeScript types from this file (npm run gen:api).
"""

import json
import os

# Before importing sentinel.main: its module-level app (for uvicorn) would otherwise open,
# and migrate, the developer's database just to print a document.
os.environ["SENTINEL_DB_PATH"] = ":memory:"

from sentinel.config import Settings  # noqa: E402
from sentinel.main import create_app  # noqa: E402

if __name__ == "__main__":
    spec = create_app(Settings(mode="local", db_path=":memory:")).openapi()
    print(json.dumps(spec, indent=2, sort_keys=True))
