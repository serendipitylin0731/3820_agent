"""系统输入、来源和结果的共享契约。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorInfo(ContractModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$", min_length=1)
    message: str = Field(min_length=1)


class SourceRef(ContractModel):
    source_file: str = Field(min_length=1)
    page_or_slide: int | str | None = None
    section: str | None = None
    data_version: str = Field(min_length=1)
    verified: bool


class KnowledgeHit(ContractModel):
    chunk_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source: SourceRef
    score: float | None = None
    score_kind: Literal["l2_distance", "similarity"] | None = None

    @model_validator(mode="after")
    def score_has_kind(self):
        if (self.score is None) != (self.score_kind is None):
            raise ValueError("score 和 score_kind 必须同时填写或同时为空")
        return self


class KnowledgeResult(ContractModel):
    status: Literal["ok", "insufficient_evidence", "error"]
    hits: list[KnowledgeHit] = Field(default_factory=list)
    error: ErrorInfo | None = None

    @model_validator(mode="after")
    def consistent_status(self):
        if self.status == "ok" and not self.hits:
            raise ValueError("ok 状态必须包含至少一个片段")
        if self.status != "ok" and self.hits:
            raise ValueError("非 ok 状态不得包含片段")
        if self.status == "error" and self.error is None:
            raise ValueError("error 状态必须包含错误信息")
        if self.status != "error" and self.error is not None:
            raise ValueError("只有 error 状态能包含错误信息")
        return self


class SubTask(ContractModel):
    type: Literal["planning", "indicator", "spatial", "evaluation"]
    question: str = Field(min_length=1)
    key: str | None = None
    years: list[int] | None = None
    keyword: str | None = None
    stype: str | None = None

    @field_validator("question", "key", "keyword", "stype")
    @classmethod
    def no_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("字段不得为空白")
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def required_parameters(self):
        if self.type == "indicator" and not self.key:
            raise ValueError("indicator 子任务必须提供 key")
        if self.type == "spatial" and not self.keyword:
            raise ValueError("spatial 子任务必须提供 keyword")
        if self.years is not None and (not self.years or any(year < 1 for year in self.years)):
            raise ValueError("years 必须包含正整数年份")
        return self


class AgentResult(ContractModel):
    role: str = Field(pattern=r"^[a-z][a-z0-9_]*$", min_length=1)
    status: Literal["ok", "insufficient_evidence", "error"]
    data: Any = None
    sources: list[SourceRef] = Field(default_factory=list)
    error: ErrorInfo | None = None

    @model_validator(mode="after")
    def consistent_status(self):
        if self.status == "error" and self.error is None:
            raise ValueError("error 状态必须包含错误信息")
        if self.status != "error" and self.error is not None:
            raise ValueError("只有 error 状态能包含错误信息")
        return self


class ChatRequest(ContractModel):
    question: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = Field(default=None, max_length=128)

    @field_validator("question", "thread_id")
    @classmethod
    def no_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("字段不得为空白")
        return value.strip() if value is not None else None


class ChatResponse(ContractModel):
    request_id: str = Field(min_length=1)
    status: Literal["ok", "partial", "error"]
    answer: str
    results: dict[str, AgentResult] = Field(default_factory=dict)


class ChatError(ContractModel):
    request_id: str = Field(min_length=1)
    status: Literal["error"] = "error"
    error: ErrorInfo
