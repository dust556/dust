"""US-GAAP concept mapping.

Filers tag the same economic line with different XBRL concepts -- a software
company reports revenue as ``RevenueFromContractWithCustomerExcludingAssessedTax``
while an older filer still uses ``Revenues``. Each field below lists its
acceptable concepts in preference order; the extractor walks the list and
takes the first that actually has a value for the period in question.

Getting this table wrong is the most common source of silently wrong
fundamentals, so each entry is ordered narrowest-and-most-modern first.
"""

from __future__ import annotations

from typing import Dict, List

# Duration concepts (income statement / cash flow): reported for a period.
DURATION_CONCEPTS: Dict[str, List[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
        "RevenuesNetOfInterestExpense",
    ],
    "cost_of_revenue": [
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
        "CostOfGoodsSold",
        "CostOfServices",
        "CostOfSales",
    ],
    "gross_profit": [
        "GrossProfit",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
    ],
    "income_tax_expense": [
        "IncomeTaxExpenseBenefit",
        "IncomeTaxExpenseBenefitContinuingOperations",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
    "interest_expense": [
        "InterestExpenseDebt",
        "InterestExpense",
        "InterestExpenseNonoperating",
        "InterestAndDebtExpense",
        "InterestExpenseBorrowings",
    ],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForCapitalImprovements",
    ],
    "acquisitions": [
        "PaymentsToAcquireBusinessesNetOfCashAcquired",
        "PaymentsToAcquireBusinessesAndInterestInAffiliatesNetOfCashAcquired",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
}

# Instant concepts (balance sheet): a stock measured at a point in time.
INSTANT_CONCEPTS: Dict[str, List[str]] = {
    "cash_and_equivalents": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashAndDueFromBanks",
    ],
    "short_term_investments": [
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    ],
    "short_term_debt": [
        "DebtCurrent",
        "LongTermDebtCurrent",
        "ShortTermBorrowings",
        "OtherShortTermBorrowings",
    ],
    "long_term_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligationsNoncurrent",
        "LongTermNotesPayable",
    ],
    # Fallback only: some filers tag a single total-debt figure. Used to
    # reconstruct the long-term portion when the noncurrent tag is absent.
    "total_debt_reported": [
        "LongTermDebt",
        "DebtLongtermAndShorttermCombinedAmount",
    ],
    "total_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "total_assets": ["Assets"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
}

# Share counts. The cover-page DEI figure is the most current, because it is
# dated at filing rather than at period end.
SHARE_CONCEPTS: List[tuple] = [
    ("dei", "EntityCommonStockSharesOutstanding"),
    ("us-gaap", "CommonStockSharesOutstanding"),
    ("us-gaap", "CommonStockSharesIssued"),
]

DILUTED_SHARE_CONCEPTS: List[tuple] = [
    ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),
    ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),
]

# Concepts whose sign convention in XBRL is "positive = cash outflow".
# They are stored as reported and negated where the maths needs a signed
# figure; keeping the list explicit avoids sign bugs in the ROIC maths.
POSITIVE_OUTFLOW_FIELDS = {"capex", "acquisitions"}
