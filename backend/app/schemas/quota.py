from pydantic import BaseModel


class QuotaOut(BaseModel):
    period: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_cny: float
    limit_tokens: int
    remaining_tokens: int
    exhausted: bool
