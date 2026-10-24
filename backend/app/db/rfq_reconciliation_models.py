"""Immutable local and peer statements about a shared electronic execution."""
from datetime import datetime
from sqlalchemy import UniqueConstraint
from sqlmodel import Column, Field, SQLModel, Text


class RfqReconciliationStatement(SQLModel, table=True):
    __tablename__ = 'rfq_reconciliation_statements'
    __table_args__ = (UniqueConstraint('execution_id', 'role', 'version'),
                      UniqueConstraint('execution_id', 'command_key'))
    message_id: str = Field(primary_key=True)
    execution_id: str = Field(foreign_key='rfq_electronic_executions.id', index=True)
    role: str
    version: int
    payload_json: str = Field(sa_column=Column(Text, nullable=False))
    payload_hash: str
    is_local: bool
    command_key: str | None = None
    recorded_at: datetime
