"""Durable bilateral execution facts, separate from transport acknowledgements."""
from datetime import datetime

from sqlmodel import Column, Field, SQLModel, Text


class RfqElectronicExecution(SQLModel, table=True):
    __tablename__ = 'rfq_electronic_executions'
    id: str = Field(primary_key=True)
    solicitation_id: int = Field(foreign_key='rfq_solicitations.id', unique=True)
    product_id: int = Field(foreign_key='products.id')
    agreement_id: int | None = Field(default=None, foreign_key='rfq_execution_agreements.id', unique=True)
    request_message_id: str = Field(unique=True)
    request_json: str = Field(sa_column=Column(Text, nullable=False))
    request_hash: str
    role: str
    state: str
    requested_by: int = Field(foreign_key='users.id')
    received_at: datetime | None = None
    decision_json: str | None = Field(default=None, sa_column=Column(Text))
    decision_message_id: str | None = Field(default=None, unique=True)
    decided_by: int | None = Field(default=None, foreign_key='users.id')


class RfqElectronicBooking(SQLModel, table=True):
    __tablename__ = 'rfq_electronic_bookings'
    execution_id: str = Field(primary_key=True, foreign_key='rfq_electronic_executions.id')
    deal_id: int = Field(foreign_key='deals.id', unique=True)
    request_hash: str
    booked_by: int = Field(foreign_key='users.id')
    booked_at: datetime


class RfqElectronicEvidence(SQLModel, table=True):
    __tablename__ = 'rfq_electronic_evidence'
    message_id: str = Field(primary_key=True, foreign_key='rfq_transport_inbox.id')
    envelope_json: str = Field(sa_column=Column(Text, nullable=False))
    received_at: datetime
