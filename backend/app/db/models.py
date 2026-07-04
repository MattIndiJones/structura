from __future__ import annotations
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, Text


class Entity(SQLModel, table=True):
    __tablename__ = "entities"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: str = Field(default="user")          # "admin" | "user"
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Folder(SQLModel, table=True):
    __tablename__ = "folders"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    parent_id: Optional[int] = Field(default=None, foreign_key="folders.id")
    user_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Script(SQLModel, table=True):
    __tablename__ = "scripts"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: str = Field(default="")
    folder_id: Optional[int] = Field(default=None, foreign_key="folders.id")
    user_id: int = Field(foreign_key="users.id")
    script_text: str = Field(default="")
    params_json: str = Field(default="{}")        # paramOverrides
    constats_json: str = Field(default="{}")      # constatOverrides (raw values)
    global_params_json: str = Field(default="{}")  # r, T, model, underlyings, etc.
    category: str = Field(default="")
    tags: str = Field(default="")                 # comma-separated
    is_shared: bool = Field(default=False)        # visible to same entity members
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Deal(SQLModel, table=True):
    __tablename__ = "deals"
    id: Optional[int] = Field(default=None, primary_key=True)
    reference: str = Field(index=True)
    entity_id: Optional[int] = Field(default=None, foreign_key="entities.id")
    user_id: int = Field(foreign_key="users.id")

    # Script frozen at booking time
    script_snapshot: str = Field(default="", sa_column=Column(Text))
    script_id: Optional[int] = Field(default=None, foreign_key="scripts.id")

    # Deal economics
    sens: str = Field(default="vente")         # "achat" | "vente"
    contrepartie: str = Field(default="")
    devise: str = Field(default="EUR")
    nominal: float = Field(default=0.0)
    fair_value: float = Field(default=0.0)     # % at booking time
    price_traded: float = Field(default=0.0)   # % actually traded

    # Dates (ISO strings)
    trade_date: str = Field(default="")
    strike_date: str = Field(default="")
    value_date: str = Field(default="")
    maturity_date: str = Field(default="")
    T: float = Field(default=0.0)

    # JSON blobs
    underlyings_json: str = Field(default="[]", sa_column=Column(Text))   # [{name, ticker, s0_abs}]
    market_snapshot_json: str = Field(default="{}", sa_column=Column(Text))

    status: str = Field(default="actif")  # actif | callé | échu | résilié

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Document(SQLModel, table=True):
    __tablename__ = "documents"
    id: Optional[int] = Field(default=None, primary_key=True)
    deal_id: Optional[int] = Field(default=None, foreign_key="deals.id")
    user_id: int = Field(foreign_key="users.id")
    doc_type: str = Field(default="")   # kid | termsheet_indicatif | termsheet_final | confirmation | autre
    title: str = Field(default="")
    filename: str = Field(default="")
    file_path: str = Field(default="")  # path relative to data/documents/
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata_json: str = Field(default="{}", sa_column=Column(Text))


class AmcStudy(SQLModel, table=True):
    __tablename__ = "amc_studies"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    isin: str = Field(default="", index=True)
    product_name: str = Field(default="")
    label: str = Field(default="")
    folder: str = Field(default="")
    manifest_json: str = Field(default="{}", sa_column=Column(Text))
    result_json: str = Field(default="{}", sa_column=Column(Text))
    synthese_text: str = Field(default="", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DealEvent(SQLModel, table=True):
    __tablename__ = "deal_events"
    id: Optional[int] = Field(default=None, primary_key=True)
    deal_id: int = Field(foreign_key="deals.id", index=True)
    event_index: int = Field(default=0)
    event_date: str = Field(default="")    # ISO calendar date
    t_years: float = Field(default=0.0)    # time from value_date in years
    spots_json: str = Field(default="{}")  # {underlying_name: spot_value}
    source: str = Field(default="pending") # pending | auto | manuel
    status: str = Field(default="futur")   # futur | observé | callé | ki | final
    label: str = Field(default="")
