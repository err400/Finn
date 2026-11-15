from sqlalchemy.orm import Session
from app.models.entities import ResearchRun
from app.providers.interfaces import ResearchRepository

class SqlResearchRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_unavailable(self, owner_id: str, ticker: str, question: str) -> int:
        run = ResearchRun(owner_id=owner_id, ticker=ticker, question=question, status="analysis_not_connected")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run.id

class ResearchService:
    def __init__(self, repository: ResearchRepository):
        self.repository = repository

    def request(self, owner_id: str, ticker: str, question: str):
        run_id = self.repository.create_unavailable(owner_id, ticker, question)
        return {"id": run_id, "ticker": ticker, "status": "analysis_not_connected", "answer": None,
                "citations": [], "message": "Research generation is not connected. Inspect retrieved primary sources through the data API. No financial analysis has been generated."}
