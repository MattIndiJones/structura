"""Bilateral trading relationships and local execution reconciliation."""
from datetime import datetime
from sqlalchemy import UniqueConstraint
from sqlmodel import SQLModel, Field


class TradingRelationship(SQLModel, table=True):
    __tablename__ = "trading_relationships"
    __table_args__ = (UniqueConstraint("entity_id", "counterparty_id", "reference"),)
    id: int | None = Field(default=None, primary_key=True)
    entity_id: int = Field(foreign_key="entities.id", index=True)
    counterparty_id: int = Field(foreign_key="counterparties.id")
    reference: str
    version: int = 1
    terms_json: str
    updated_by: int = Field(foreign_key="users.id")
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TradingExecution(SQLModel, table=True):
    __tablename__ = "trading_executions"
    __table_args__ = (UniqueConstraint("entity_id", "trade_reference"),)
    id: int | None = Field(default=None, primary_key=True)
    entity_id: int = Field(foreign_key="entities.id", index=True)
    user_id: int = Field(foreign_key="users.id")
    deal_id: int = Field(foreign_key="deals.id")
    relationship_id: int = Field(foreign_key="trading_relationships.id")
    trade_reference: str
    request_hash: str
    issuer: str
    our_side: str
    instrument_reference: str
    settlement_status: str = "PENDING"
    settlement_reference: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
