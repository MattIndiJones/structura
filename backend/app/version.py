"""Single source of the application version.

FastAPI's OpenAPI metadata, /health and the frontend package all read this
number; a test keeps frontend/package.json aligned. Each delivery merged into
main is tagged v<VERSION> in git.
"""

VERSION = "0.3.0"
