"""Validated contracts shared by extraction, matching and the API."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Requirement(Contract):
    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=1000)
    category: Literal["skill", "experience", "education", "language", "certification"]
    must_have: bool = False
    minimum_years: float | None = Field(default=None, ge=0, le=80)

    @model_validator(mode="after")
    def valid_years(self):
        if self.minimum_years is not None and self.category != "experience":
            raise ValueError("minimum_years is only valid for experience requirements")
        return self


class RequirementsUpdate(Contract):
    requirements: list[Requirement] = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({r.id for r in self.requirements}) != len(self.requirements):
            raise ValueError("Requirement IDs must be unique")
        return self


class JobCreate(Contract):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=30, max_length=30000)


class JobExtraction(Contract):
    job_title: str
    required_skills: list[str] = Field(description="Mandatory technical skills, e.g. Python, SQL. Exclude degrees, certificates, languages and durations.")
    nice_to_have_skills: list[str] = Field(description="Preferred technical skills or tools explicitly described as optional or nice to have.")
    years_of_experience: float | None = Field(ge=0, le=80, description="Numeric minimum experience, e.g. 2 for at least 2 years; null if unstated.")
    experience_notes: str = Field(description="Experience requirement with its original scope and conditions.")
    education: list[str] = Field(description="Academic degrees and fields of study only.")
    languages: list[str] = Field(description="Human languages and any stated proficiency only.")
    certifications: list[str] = Field(description="Named professional certificates or credentials only. A programming skill is not a certification. Empty when no certification is requested.")


class WorkExperience(Contract):
    title: str = ""
    company: str = ""
    duration: str = ""
    description: str = ""


class Education(Contract):
    degree: str = ""
    institution: str = ""
    years: str = ""


class CandidateInfo(Contract):
    candidate_name: str = ""
    skills: list[str] = Field(default_factory=list)
    work_experience: list[WorkExperience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


class Assessment(Contract):
    requirement_id: str
    status: Literal["meets", "partially_meets", "does_not_meet", "no_evidence"]
    evidence: str = ""
    explanation: str = ""


class AssessmentBatch(Contract):
    assessments: list[Assessment]


class DecisionUpdate(Contract):
    decision: Literal["shortlist", "review_later", "reject"]


class GmailRequest(Contract):
    query: str = Field(min_length=1, max_length=2000)
    max_results: int = Field(default=50, ge=1, le=500)


class JobResponse(BaseModel):
    id: str
    title: str
    description: str
    requirements: list[Requirement]
    confirmed: bool
    revision: int
    created_at: str


class SemanticMatch(BaseModel):
    similarity: float = Field(ge=-1.001, le=1.001)
    passage: str


class MatchResponse(Requirement):
    status: Literal["meets", "partially_meets", "does_not_meet", "no_evidence"]
    evidence: str
    explanation: str
    semantic: SemanticMatch | None = None


class CandidateResponse(BaseModel):
    id: str
    job_id: str
    filename: str
    source: dict[str, Any]
    info: CandidateInfo
    matches: list[MatchResponse]
    qualified: bool
    missing_must_haves: list[str]
    score: float = Field(ge=0, le=100)
    semantic_enabled: bool = False
    job_revision: int
    decision: Literal["shortlist", "review_later", "reject"]
    created_at: str
    stale: bool = False
    rank: int | None = Field(default=None, ge=1)


class BatchItem(BaseModel):
    status: Literal["processed", "duplicate", "error"]
    candidate_id: str | None = None
    email_id: str | None = None
    filename: str | None = None
    error: str | None = None


class BatchResponse(BaseModel):
    results: list[BatchItem]


class GmailResponse(BatchResponse):
    emails_found: int = Field(ge=0)


class StatisticsResponse(BaseModel):
    total: int = Field(ge=0)
    qualified: int = Field(ge=0)
    needs_review: int = Field(ge=0)
    stale: int = Field(ge=0)


class RankingResponse(BaseModel):
    qualified: list[CandidateResponse]
    review: list[CandidateResponse]
    top_candidates: list[CandidateResponse]
    statistics: StatisticsResponse


class HealthResponse(BaseModel):
    status: Literal["ok"]
