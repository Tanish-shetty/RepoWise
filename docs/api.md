# API

FastAPI publishes interactive OpenAPI at `/docs` and the machine schema at `/openapi.json`. Mutating operations use validated Pydantic request models. Repository creation accepts exactly one of `github_url` and `local_path`; search caps results at 30; debugging requires a meaningful problem statement; test execution accepts only `pytest` or `npm_test`. Run responses store both state and final evidence so clients may render progress without parsing prose.

