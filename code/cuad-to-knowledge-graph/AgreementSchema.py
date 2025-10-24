
from typing import List
from enum import Enum
from pydantic import BaseModel

# Define a Pydantic model for the Agreement schema
class Party(BaseModel):
    name: str
    role: str
    incorporation_country: str
    incorporation_state: str

class GoverningLaw(BaseModel):
    country: str
    state: str
    most_favored_country: str

class ContractClauseExcerpt(BaseModel):
    excerpt: str
    page_number: int

class ContractClause(BaseModel):
    clause_type: str
    found_in_contract: bool
    excerpts: List[ContractClauseExcerpt]


class Agreement(BaseModel):  
    agreement_name: str
    file_name: str
    agreement_type: str
    effective_date: str
    expiration_date: str
    renewal_term: str
    notice_period_to_terminate_Renewal: str
    parties: List[Party]
    governing_law: GoverningLaw
    clauses: List[ContractClause]


class ClauseType(Enum):
    ANTI_ASSIGNMENT = "Anti-Assignment"
    COMPETITIVE_RESTRICTION = "Competitive Restriction Exception"
    NON_COMPETE = "Non-Compete"
    EXCLUSIVITY = "Exclusivity"
    NO_SOLICIT_CUSTOMERS = "No-Solicit of Customers"
    NO_SOLICIT_EMPLOYEES = "No-Solicit Of Employees"
    NON_DISPARAGEMENT = "Non-Disparagement"
    TERMINATION_FOR_CONVENIENCE = "Termination For Convenience"
    ROFR_ROFO_ROFN = "Rofr/Rofo/Rofn"
    CHANGE_OF_CONTROL = "Change of Control"
    REVENUE_PROFIT_SHARING = "Revenue/Profit Sharing"
    PRICE_RESTRICTION = "Price Restrictions"
    MINIMUM_COMMITMENT = "Minimum Commitment"
    VOLUME_RESTRICTION = "Volume Restriction"
    IP_OWNERSHIP_ASSIGNMENT = "IP Ownership Assignment"
    JOINT_IP_OWNERSHIP = "Joint IP Ownership"
    LICENSE_GRANT = "License grant"
    NON_TRANSFERABLE_LICENSE = " Non-Transferable License"
    AFFILIATE_LICENSE_LICENSOR = "Affiliate License-Licensor"
    AFFILIATE_LICENSE_LICENSEE = "Affiliate License-Licensee"
    UNLIMITED_LICENSE = "Unlimited/All-You-Can-Eat-License"
    PERPETUAL_LICENSE = "Irrevocable Or Perpetual License"
    SOURCE_CODE_SCROW = "Source Code Escrow"
    POST_TERMINATION_SERVICES = "Post-Termination Services"
    AUDIT_RIGHTS = "Audit Rights"
    UNCAPPED_LIABILITY = "Uncapped Liability"
    CAP_ON_LIABILITY = "Cap On Liability"
    LIQUIDATED_DAMAGES = "Liquidated Damages"
    WARRANTY_DURATION = "Warranty Duration"
    INSURANCE = "Insurance"
    COVENANT_NOT_TO_SUE = "Covenant Not To Sue"
    THIRD_PARTY_BENEFICIARY = "Third Party Beneficiary"
    
