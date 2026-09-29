"""Print the OpenAPI document without starting a server.

    uv run python -m sentinel.openapi_export > ../frontend/src/api/openapi.json

The frontend generates its TypeScript types from this file (npm run gen:api).
"""

import json

from sentinel.config import Settings
from sentinel.main import create_app

if __name__ == "__main__":
    spec = create_app(Settings(mode="local")).openapi()
    print(json.dumps(spec, indent=2, sort_keys=True))
