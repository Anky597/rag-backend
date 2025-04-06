# app/models.py
from pydantic import BaseModel

class QueryRequest(BaseModel):
    """Pydantic model for the expected request body."""
    question: str

class RecommendationResponse(BaseModel):
    """Pydantic model for the structured response."""
    answer: str
    # sources: list = [] # Optional: Could add sources later