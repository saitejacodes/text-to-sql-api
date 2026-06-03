from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional, Any


class RetrieveRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500, example="Which departments have more than 100 students?")

    @field_validator("question")
    @classmethod
    def not_blank(cls, v):
        if not v.strip():
            raise ValueError("Question must not be blank.")
        return v.strip()


class RetrieveDetails(BaseModel):
    relevance_score: float
    reason: str


class RetrieveResponse(BaseModel):
    retrieved_tables: List[str]
    scores: List[float]
    confidence: float
    details: Dict[str, RetrieveDetails]


class GenerateSqlRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    use_retrieved_context: bool = True

    @field_validator("question")
    @classmethod
    def not_blank(cls, v):
        if not v.strip():
            raise ValueError("Question must not be blank.")
        return v.strip()


class ExecutionResult(BaseModel):
    success: bool
    columns: List[str]
    rows: List[Any]
    row_count: int
    execution_time_ms: float
    error: Optional[str] = None


class GenerateSqlResponse(BaseModel):
    sql: str
    retrieved_tables: List[str]
    is_valid_syntax: bool
    parsing_errors: Optional[str] = None
    confidence: float
    prompt_used: str
    execution_result: Optional[ExecutionResult] = None  # NEW: actual query results


class MetricsDetails(BaseModel):
    retrieval_recall_at_5: float
    retrieval_recall_at_10: float
    sql_exact_match_accuracy: float
    sql_execution_match_accuracy: float
    parsing_success_rate: float
    average_latency_ms: float


class SubtaskBreakdown(BaseModel):
    multi_table_retrieval: float
    column_mapping: float
    join_detection: float
    domain_knowledge: float


class ErrorAnalysis(BaseModel):
    retrieval_failures: int
    parsing_failures: int
    execution_failures: int
    logic_errors: int


class BenchmarkResponse(BaseModel):
    total_queries: int
    metrics: MetricsDetails
    subtask_breakdown: SubtaskBreakdown
    error_analysis: ErrorAnalysis