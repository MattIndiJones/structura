"""Additive durable transport records; local business IDs never cross installations."""
from datetime import datetime
from typing import Optional
from sqlalchemy import UniqueConstraint
from sqlmodel import SQLModel, Field, Column, Text


class RfqInstallation(SQLModel, table=True):
    __tablename__ = "rfq_installation"
    id: int = Field(default=1, primary_key=True)
    installation_id: str = Field(unique=True)


class RfqChannel(SQLModel, table=True):
    __tablename__ = "rfq_channels"
    id: str = Field(primary_key=True)
    relationship_id: int = Field(foreign_key="rfq_relationships.id", unique=True)
    relationship_version: int
    entity_id: int = Field(foreign_key="entities.id", index=True)
    role: str  # REQUESTER or BANK
    peer_installation_id: str
    peer_url: str
    secret: str
    agreement_hash: str
    active: bool = True
    confirmed_at: Optional[datetime] = None
    configured_by: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RfqRemoteLink(SQLModel, table=True):
    __tablename__ = "rfq_remote_links"
    __table_args__ = (UniqueConstraint("channel_id", "request_message_id"),)
    solicitation_id: int = Field(primary_key=True, foreign_key="rfq_solicitations.id")
    channel_id: str = Field(foreign_key="rfq_channels.id")
    request_message_id: str
    inbound: bool


class RfqTransportOutbox(SQLModel, table=True):
    __tablename__ = "rfq_transport_outbox"
    __table_args__ = (UniqueConstraint("channel_id", "request_message_id", "sequence"),)
    id: str = Field(primary_key=True)
    channel_id: str = Field(foreign_key="rfq_channels.id", index=True)
    solicitation_id: int = Field(foreign_key="rfq_solicitations.id", index=True)
    request_message_id: str
    sequence: int
    kind: str
    payload_json: str = Field(sa_column=Column(Text, nullable=False))
    payload_hash: str
    actor_user_id: int = Field(foreign_key="users.id")
    state: str = Field(default="PENDING", index=True)
    attempts: int = 0
    next_attempt_at: datetime = Field(default_factory=datetime.utcnow)
    lease_until: Optional[datetime] = None
    lease_token: Optional[str] = None
    received_at: Optional[datetime] = None
    receipt_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    signed_receipt_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RfqTransportInbox(SQLModel, table=True):
    __tablename__ = "rfq_transport_inbox"
    __table_args__ = (UniqueConstraint("channel_id", "request_message_id", "sequence"),)
    id: str = Field(primary_key=True)
    channel_id: str = Field(foreign_key="rfq_channels.id")
    request_message_id: str
    sequence: int
    payload_hash: str
    payload_json: str = Field(sa_column=Column(Text, nullable=False))
    receipt_json: str = Field(sa_column=Column(Text, nullable=False))
    received_at: datetime = Field(default_factory=datetime.utcnow)


class RfqTransportAttempt(SQLModel, table=True):
    __tablename__ = "rfq_transport_attempts"
    id: Optional[int] = Field(default=None, primary_key=True)
    message_id: str = Field(foreign_key="rfq_transport_outbox.id", index=True)
    attempted_at: datetime = Field(default_factory=datetime.utcnow)
    outcome: str
    detail: Optional[str] = None
