"""Organisation-owned CCR extensions of the existing Counterparty catalog."""
from datetime import datetime
from sqlalchemy import Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class CCRRecord(SQLModel):
    id: int | None = Field(default=None, primary_key=True)
    entity_id: int = Field(foreign_key="entities.id", index=True)
    counterparty_id: int = Field(foreign_key="counterparties.id", index=True)
    version: int = 1
    payload_json: str = Field(default="{}", sa_type=Text)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: int = Field(foreign_key="users.id")


class CCRCreditProfile(CCRRecord, table=True):
    __tablename__ = "ccr_credit_profiles"
    __table_args__ = (UniqueConstraint("entity_id", "counterparty_id"),)


class CCRMasterAgreement(CCRRecord, table=True):
    __tablename__ = "ccr_master_agreements"


class CCRCSAAgreement(CCRRecord, table=True):
    __tablename__ = "ccr_csa_agreements"


class CCRNettingSet(CCRRecord, table=True):
    __tablename__ = "ccr_netting_sets"


class CCRCreditLimit(CCRRecord, table=True):
    __tablename__ = "ccr_credit_limits"


class CCRCollateralPosition(CCRRecord, table=True):
    __tablename__ = "ccr_collateral_positions"


class CCRCreditOverride(CCRRecord, table=True):
    __tablename__ = "ccr_credit_overrides"


class CCRExposureCalculation(SQLModel, table=True):
    __tablename__ = "ccr_exposure_calculations"
    id: int | None = Field(default=None, primary_key=True)
    entity_id: int = Field(foreign_key="entities.id", index=True)
    counterparty_id: int | None = Field(default=None, foreign_key="counterparties.id", index=True)
    created_by: int = Field(foreign_key="users.id")
    calculation_timestamp: datetime = Field(default_factory=datetime.utcnow)
    as_of_date: str
    methodology: str
    input_hash: str
    inputs_json: str = Field(sa_column=Column(Text, nullable=False))
    results_json: str = Field(sa_column=Column(Text, nullable=False))


RECORDS = {
    "profiles": CCRCreditProfile, "agreements": CCRMasterAgreement,
    "csas": CCRCSAAgreement, "netting-sets": CCRNettingSet, "limits": CCRCreditLimit,
    "collateral": CCRCollateralPosition, "overrides": CCRCreditOverride,
}
