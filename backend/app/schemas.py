from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class RepositoryCreate(BaseModel):
    github_url: HttpUrl | None = None
    local_path: str | None = None

    @model_validator(mode="after")
    def exactly_one_source(self):
        if bool(self.github_url) == bool(self.local_path):
            raise ValueError("Provide exactly one of github_url or local_path")
        return self


class RepositoryView(BaseModel):
    id: int
    name: str
    source: str
    status: str
    profile: dict

    model_config = {"from_attributes": True}


class RunRequest(BaseModel):
    repository_id: int


class DebugRequest(RunRequest):
    problem: str = Field(min_length=10, max_length=4000)


class SearchRequest(RunRequest):
    query: str = Field(min_length=2, max_length=500)
    language: str | None = None
    path_prefix: str | None = None
    limit: int = Field(default=8, ge=1, le=30)


class TestGenerateRequest(RunRequest):
    target: str = Field(min_length=1, max_length=500)
    behavior: str = Field(min_length=5, max_length=2000)


class TestExecuteRequest(RunRequest):
    runner: Literal["pytest", "npm_test"]


class Issue(BaseModel):
    severity: Literal["critical", "high", "medium", "low", "info"]
    category: str
    title: str
    explanation: str
    file: str
    line: int
    evidence: str
    suggested_fix: str


class Verification(BaseModel):
    status: Literal["verified", "partially_verified", "failed", "unable_to_verify"]
    summary: str
    evidence: list[str] = []


class RunView(BaseModel):
    id: int
    repository_id: int
    kind: str
    status: str
    request: str
    result: dict

    model_config = {"from_attributes": True}
