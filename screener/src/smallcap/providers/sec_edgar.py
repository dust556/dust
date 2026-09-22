"""SEC EDGAR provider: XBRL company facts, share counts and insider filings.

Three public endpoints, no API key:

* ``www.sec.gov/files/company_tickers_exchange.json`` -- ticker -> CIK + exchange
* ``data.sec.gov/api/xbrl/companyfacts/CIK##########.json`` -- every XBRL fact
  the company has ever tagged, with the filing date of each
* ``data.sec.gov/submissions/CIK##########.json`` -- the filing index, used to
  find the Form 3/4/5 ownership documents

**Point-in-time discipline.** Every fact carries the date it was filed. When
``as_of`` is supplied, facts filed after it are dropped before anything is
computed, and where several filings report the same period (an original 10-Q
and a later restating 10-K), the most recently filed value that was public by
``as_of`` wins. That is exactly the information set an investor had on the
day, which is what makes a historical run mean anything.
"""

from __future__ import annotations

import datetime as dt
import re
import threading
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..config import Config
from ..models import (
    CompanyFinancials,
    FinancialPeriod,
    InsiderHolding,
    InsiderOwnership,
    MarketData,
)
from ..util.http import HttpClient, HTTPError
from .base import ProviderError
from .concepts import (
    DURATION_CONCEPTS,
    INSTANT_CONCEPTS,
    SHARE_CONCEPTS,
)

TICKER_INDEX_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}/{document}"

# Exchanges we consider in scope for a US small-cap screen. OTC names are
# excluded by default: the coverage argument in the brief is about
# under-followed *listed* companies, not about unlisted paper.
DEFAULT_EXCHANGES = {"NYSE", "Nasdaq", "NYSE American", "NYSEAmerican", "CBOE"}


def _parse_date(value: Optional[str]) -> Optional[dt.date]:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


class SECEdgarProvider:
    """Fetches fundamentals, share counts and insider ownership from EDGAR."""

    name = "sec_edgar"

    def __init__(
        self,
        config: Config,
        http: Optional[HttpClient] = None,
        price_provider: Any = None,
        offline: bool = False,
    ):
        self.config = config
        self.http = http or HttpClient(
            user_agent=config.user_agent,
            cache_dir=config.cache_dir,
            cache_ttl_hours=config.cache_ttl_hours,
            min_interval=config.request_delay_seconds,
            max_retries=config.max_retries,
            timeout=config.timeout_seconds,
            offline=offline,
        )
        self.price_provider = price_provider
        self._ticker_index: Optional[Dict[str, Dict[str, Any]]] = None
        self._index_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Ticker -> CIK
    # ------------------------------------------------------------------
    def ticker_index(self) -> Dict[str, Dict[str, Any]]:
        # Built once and shared by every worker thread. Without the lock, a
        # parallel run has each worker fetch and parse the whole index on its
        # first company.
        with self._index_lock:
            if self._ticker_index is not None:
                return self._ticker_index
            return self._load_ticker_index()

    def _load_ticker_index(self) -> Dict[str, Dict[str, Any]]:
        try:
            payload = self.http.get_json(TICKER_INDEX_URL)
        except HTTPError as exc:
            raise ProviderError(
                f"could not load the SEC ticker index: {exc}. "
                "Check network access and that SEC_USER_AGENT names a real "
                "contact address -- EDGAR blocks anonymous traffic."
            ) from exc
        fields = payload.get("fields") or []
        rows = payload.get("data") or []
        try:
            i_cik = fields.index("cik")
            i_name = fields.index("name")
            i_ticker = fields.index("ticker")
        except ValueError as exc:
            raise ProviderError(f"unexpected ticker index layout: {fields}") from exc
        i_exchange = fields.index("exchange") if "exchange" in fields else None

        index: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            ticker = str(row[i_ticker]).upper().strip()
            if not ticker:
                continue
            index[ticker] = {
                "cik": str(row[i_cik]).zfill(10),
                "name": row[i_name],
                "exchange": row[i_exchange] if i_exchange is not None else None,
            }
        self._ticker_index = index
        return index

    def prepare(self) -> None:
        """Load the run-level prerequisites before any worker starts.

        Failing here fails the whole run with one clear message, instead of
        producing an identical fetch error for every ticker in the universe.
        """
        self.ticker_index()

    def universe(self, exchanges: Optional[Iterable[str]] = None) -> List[str]:
        """Every listed ticker, optionally restricted to given exchanges."""
        allowed = set(exchanges) if exchanges else DEFAULT_EXCHANGES
        return sorted(
            ticker
            for ticker, meta in self.ticker_index().items()
            if not allowed or (meta.get("exchange") or "") in allowed
        )

    def resolve(self, ticker: str) -> Dict[str, Any]:
        meta = self.ticker_index().get(ticker.upper().strip())
        if not meta:
            raise ProviderError(f"{ticker}: not found in the SEC ticker index")
        return meta

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def fetch(
        self, ticker: str, as_of: Optional[dt.date] = None
    ) -> CompanyFinancials:
        meta = self.resolve(ticker)
        cik = meta["cik"]
        company = CompanyFinancials(
            ticker=ticker.upper(),
            cik=cik,
            name=meta.get("name"),
            exchange=meta.get("exchange"),
            source=self.name,
        )

        try:
            facts = self.http.get_json(COMPANY_FACTS_URL.format(cik=cik))
        except HTTPError as exc:
            raise ProviderError(f"{ticker}: company facts unavailable ({exc})") from exc

        company.periods = self._build_periods(facts, as_of)
        if not company.periods:
            company.warnings.append("no usable XBRL periods were extracted")

        shares, shares_date = self._latest_shares(facts, as_of)
        company.market = MarketData(
            ticker=company.ticker,
            shares_outstanding=shares,
            shares_date=shares_date,
        )
        if shares is None:
            company.warnings.append("share count unavailable")
        elif (
            shares_date
            and as_of
            and (as_of - shares_date).days > self.config.market_cap.shares_max_age_days
        ):
            company.warnings.append(
                f"share count is stale ({shares_date.isoformat()})"
            )

        if self.price_provider is not None:
            try:
                self.price_provider.enrich(company.market, as_of=as_of)
            except Exception as exc:  # noqa: BLE001 - a price gap must not abort the run
                company.warnings.append(f"price lookup failed: {exc}")

        if company.market.price is not None and shares is not None:
            company.market.market_cap = company.market.price * shares

        try:
            company.insiders = self.fetch_insider_ownership(cik, shares, as_of)
        except (HTTPError, ProviderError) as exc:
            # Missing ownership data costs one criterion, not the company.
            company.warnings.append(f"insider ownership unavailable: {exc}")

        return company

    # ------------------------------------------------------------------
    # XBRL fact extraction
    # ------------------------------------------------------------------
    def _build_periods(
        self, facts: Dict[str, Any], as_of: Optional[dt.date]
    ) -> List[FinancialPeriod]:
        us_gaap = (facts.get("facts") or {}).get("us-gaap") or {}

        # Duration facts are keyed by (start, end); instants by end alone.
        durations: Dict[Tuple[dt.date, dt.date], Dict[str, Any]] = {}
        instants: Dict[dt.date, Dict[str, Any]] = {}

        for field_name, concepts in DURATION_CONCEPTS.items():
            for key, entry in self._best_facts(us_gaap, concepts, as_of, instant=False).items():
                bucket = durations.setdefault(key, {"_meta": entry})
                bucket.setdefault(field_name, entry["val"])
                # Keep the newest filing metadata seen for this period.
                if entry["filed"] and (
                    bucket["_meta"]["filed"] is None
                    or entry["filed"] > bucket["_meta"]["filed"]
                ):
                    bucket["_meta"] = entry

        for field_name, concepts in INSTANT_CONCEPTS.items():
            for key, entry in self._best_facts(us_gaap, concepts, as_of, instant=True).items():
                bucket = instants.setdefault(key, {})
                bucket.setdefault(field_name, entry["val"])

        periods: List[FinancialPeriod] = []
        for (start, end), values in sorted(durations.items()):
            meta = values["_meta"]
            period = FinancialPeriod(
                end=end,
                fy=meta.get("fy"),
                fp=meta.get("fp"),
                filed=meta.get("filed"),
                form=meta.get("form"),
                duration_days=(end - start).days,
            )
            for field_name in DURATION_CONCEPTS:
                if field_name in values:
                    setattr(period, field_name, float(values[field_name]))
            # Attach the balance sheet as of this period end.
            balance = instants.get(end, {})
            for field_name in INSTANT_CONCEPTS:
                if field_name in balance and hasattr(period, field_name):
                    setattr(period, field_name, float(balance[field_name]))
            self._reconcile(period, balance)
            periods.append(period)

        return periods

    def _best_facts(
        self,
        namespace: Dict[str, Any],
        concepts: List[str],
        as_of: Optional[dt.date],
        instant: bool,
    ) -> Dict[Any, Dict[str, Any]]:
        """Pick one value per period from a preference-ordered concept list.

        Within a concept, later filings supersede earlier ones for the same
        period (restatements). Across concepts, the earlier entry in the
        preference list wins -- a period already filled by a preferred concept
        is never overwritten by a fallback.
        """
        chosen: Dict[Any, Dict[str, Any]] = {}
        for concept in concepts:
            fact = namespace.get(concept)
            if not fact:
                continue
            for unit, entries in (fact.get("units") or {}).items():
                if unit not in ("USD", "shares", "pure"):
                    continue
                for entry in entries:
                    end = _parse_date(entry.get("end"))
                    if end is None:
                        continue
                    filed = _parse_date(entry.get("filed"))
                    if as_of is not None and (filed is None or filed > as_of):
                        continue  # not public yet at as_of
                    if as_of is not None and end > as_of:
                        continue
                    if instant:
                        key: Any = end
                    else:
                        start = _parse_date(entry.get("start"))
                        if start is None:
                            continue
                        key = (start, end)
                    record = {
                        "val": entry.get("val"),
                        "filed": filed,
                        "fy": entry.get("fy"),
                        "fp": entry.get("fp"),
                        "form": entry.get("form"),
                        "concept": concept,
                    }
                    if record["val"] is None:
                        continue
                    existing = chosen.get(key)
                    if existing is None:
                        chosen[key] = record
                    elif existing["concept"] == concept:
                        # Same concept, newer filing -> restatement wins.
                        if (
                            filed is not None
                            and existing["filed"] is not None
                            and filed > existing["filed"]
                        ):
                            chosen[key] = record
        return chosen

    @staticmethod
    def _reconcile(period: FinancialPeriod, balance: Dict[str, Any]) -> None:
        """Fill derivable gaps and clean up known tagging quirks."""
        # Gross profit is often not tagged even though both inputs are.
        if period.gross_profit is None and period.revenue is not None and period.cost_of_revenue is not None:
            period.gross_profit = period.revenue - period.cost_of_revenue
        if period.cost_of_revenue is None and period.revenue is not None and period.gross_profit is not None:
            period.cost_of_revenue = period.revenue - period.gross_profit

        # Some filers tag only a combined total debt figure. Recover the
        # long-term portion rather than dropping the company from the screen.
        total_reported = balance.get("total_debt_reported")
        if period.long_term_debt is None and total_reported is not None:
            current = period.short_term_debt or 0.0
            remainder = float(total_reported) - current
            period.long_term_debt = remainder if remainder > 0 else float(total_reported)

    # ------------------------------------------------------------------
    # Share count
    # ------------------------------------------------------------------
    def _latest_shares(
        self, facts: Dict[str, Any], as_of: Optional[dt.date]
    ) -> Tuple[Optional[float], Optional[dt.date]]:
        all_facts = facts.get("facts") or {}
        for namespace, concept in SHARE_CONCEPTS:
            entries = (
                ((all_facts.get(namespace) or {}).get(concept) or {}).get("units") or {}
            ).get("shares")
            if not entries:
                continue
            best_value: Optional[float] = None
            best_end: Optional[dt.date] = None
            best_filed: Optional[dt.date] = None
            for entry in entries:
                end = _parse_date(entry.get("end"))
                filed = _parse_date(entry.get("filed"))
                if end is None:
                    continue
                if as_of is not None and (filed is None or filed > as_of):
                    continue
                value = entry.get("val")
                if value is None:
                    continue
                # Prefer the most recent period end; break ties on filing date.
                if (
                    best_end is None
                    or end > best_end
                    or (end == best_end and filed and best_filed and filed > best_filed)
                ):
                    best_value, best_end, best_filed = float(value), end, filed
            if best_value is not None:
                return best_value, best_end
        return None, None

    # ------------------------------------------------------------------
    # Insider ownership (Forms 3/4/5)
    # ------------------------------------------------------------------
    def fetch_insider_ownership(
        self,
        cik: str,
        shares_outstanding: Optional[float],
        as_of: Optional[dt.date] = None,
        max_filings: int = 120,
    ) -> InsiderOwnership:
        """Reconstruct insider holdings from ownership filings.

        Each Form 4 states, for every row, the number of shares the insider
        held *after* the reported transaction. Taking the latest such figure
        per (owner, direct/indirect ownership form) and summing across owners
        reconstructs current insider holdings.

        This is a **lower bound**, and the docstring says so because the number
        it produces looks authoritative and is not: insiders who have never
        filed since their Form 3, holdings not required to be reported, and
        unexercised derivatives are all outside it. The authoritative figure is
        the beneficial-ownership table in the DEF 14A proxy; see
        ``docs/methodology.md``.
        """
        submissions = self.http.get_json(SUBMISSIONS_URL.format(cik=cik))
        recent = (submissions.get("filings") or {}).get("recent") or {}
        forms = recent.get("form") or []
        accessions = recent.get("accessionNumber") or []
        documents = recent.get("primaryDocument") or []
        report_dates = recent.get("reportDate") or []
        filing_dates = recent.get("filingDate") or []

        cutoff = None
        if as_of is not None:
            cutoff = as_of - dt.timedelta(days=self.config.insider.max_holding_age_days)

        # (owner_cik, direct/indirect, nature) -> latest reported holding
        latest: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        notes: List[str] = []
        examined = 0

        for i, form in enumerate(forms):
            if form not in ("3", "4", "5", "3/A", "4/A", "5/A"):
                continue
            filed = _parse_date(filing_dates[i] if i < len(filing_dates) else None)
            if as_of is not None and (filed is None or filed > as_of):
                continue
            reported = _parse_date(report_dates[i] if i < len(report_dates) else None) or filed
            if cutoff is not None and reported is not None and reported < cutoff:
                continue
            if examined >= max_filings:
                notes.append(
                    f"stopped after {max_filings} ownership filings; older holdings ignored"
                )
                break
            examined += 1

            accession = str(accessions[i]).replace("-", "")
            document = documents[i] if i < len(documents) else ""
            if not document:
                continue
            url = ARCHIVE_URL.format(
                cik_int=int(cik), accession=accession, document=document
            )
            try:
                raw = self.http.get_text(url, accept="application/xml")
            except HTTPError:
                continue
            try:
                rows = parse_ownership_document(raw)
            except ET.ParseError:
                continue
            for row in rows:
                row["as_of"] = row.get("as_of") or reported
                row["accession"] = accessions[i]
                key = (row["owner_cik"] or row["owner_name"], row["ownership"], row["nature"])
                previous = latest.get(key)
                if previous is None or _row_is_newer(row, previous):
                    latest[key] = row

        holdings: List[InsiderHolding] = []
        include_ten_pct = self.config.insider.include_ten_percent_owners
        by_owner: Dict[str, InsiderHolding] = {}
        for row in latest.values():
            is_insider = row["is_officer"] or row["is_director"]
            if not is_insider and not (include_ten_pct and row["is_ten_percent_owner"]):
                continue
            owner_key = row["owner_cik"] or row["owner_name"]
            holding = by_owner.get(owner_key)
            if holding is None:
                holding = InsiderHolding(
                    owner_name=row["owner_name"],
                    owner_cik=row["owner_cik"],
                    is_officer=row["is_officer"],
                    is_director=row["is_director"],
                    is_ten_percent_owner=row["is_ten_percent_owner"],
                    shares=0.0,
                    as_of=row["as_of"],
                    source_accession=row["accession"],
                )
                by_owner[owner_key] = holding
            # Direct and each indirect ownership form are separate holdings
            # for the same person, so they add.
            holding.shares = (holding.shares or 0.0) + (row["shares"] or 0.0)
            if row["as_of"] and (holding.as_of is None or row["as_of"] > holding.as_of):
                holding.as_of = row["as_of"]
        holdings = sorted(
            by_owner.values(), key=lambda h: h.shares or 0.0, reverse=True
        )

        total = sum(h.shares or 0.0 for h in holdings) if holdings else None
        as_of_dates = [h.as_of for h in holdings if h.as_of]
        if examined == 0:
            notes.append("no ownership filings found in the window")
        if self.config.insider.warn_on_form345_basis:
            notes.append(
                "derived from Forms 3/4/5; treat as a lower bound on true "
                "insider ownership (DEF 14A is authoritative)"
            )
        return InsiderOwnership(
            total_shares=total,
            holdings=holdings,
            basis="form345",
            as_of=max(as_of_dates) if as_of_dates else None,
            notes=notes,
        )


def _row_is_newer(row: Dict[str, Any], previous: Dict[str, Any]) -> bool:
    new_date = row.get("transaction_date") or row.get("as_of")
    old_date = previous.get("transaction_date") or previous.get("as_of")
    if new_date and old_date:
        return new_date > old_date
    return bool(new_date) and not old_date


def _strip_namespace(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _text(node: Optional[ET.Element], path: str) -> Optional[str]:
    if node is None:
        return None
    found = node.find(path)
    if found is None:
        return None
    # Ownership XML wraps most values in a <value> child, sometimes alongside
    # a <footnoteId>; the direct text is used when there is no wrapper.
    value = found.find("value")
    text = (value.text if value is not None else found.text) or ""
    return text.strip() or None


def _flag(node: Optional[ET.Element], path: str) -> bool:
    raw = _text(node, path)
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes"}


def parse_ownership_document(xml_text: str) -> List[Dict[str, Any]]:
    """Parse a Form 3/4/5 XML document into per-holding rows.

    Exposed separately from the fetching code so it can be tested against
    recorded filings without touching the network.
    """
    # Ownership documents are sometimes wrapped in an SGML container.
    match = re.search(r"<ownershipDocument.*?</ownershipDocument>", xml_text, re.S)
    if match:
        xml_text = match.group(0)
    root = ET.fromstring(xml_text)
    for element in root.iter():
        element.tag = _strip_namespace(element.tag)

    period = _parse_date(_text(root, "periodOfReport"))

    owners = []
    for owner_node in root.findall("reportingOwner"):
        identity = owner_node.find("reportingOwnerId")
        relationship = owner_node.find("reportingOwnerRelationship")
        owners.append(
            {
                "owner_cik": _text(identity, "rptOwnerCik"),
                "owner_name": _text(identity, "rptOwnerName") or "unknown",
                "is_officer": _flag(relationship, "isOfficer"),
                "is_director": _flag(relationship, "isDirector"),
                "is_ten_percent_owner": _flag(relationship, "isTenPercentOwner"),
            }
        )
    if not owners:
        return []

    rows: List[Dict[str, Any]] = []
    # A Form 4 reports transactions; a Form 3 reports only holdings. Both
    # carry the post-event share count we need.
    sources = [
        ("nonDerivativeTransaction", "postTransactionAmounts/sharesOwnedFollowingTransaction"),
        ("nonDerivativeHolding", "postTransactionAmounts/sharesOwnedFollowingTransaction"),
    ]
    for container in root.findall("nonDerivativeTable"):
        for tag, shares_path in sources:
            for node in container.findall(tag):
                shares_text = _text(node, shares_path)
                if shares_text is None:
                    continue
                try:
                    shares = float(shares_text)
                except ValueError:
                    continue
                nature_node = node.find("ownershipNature")
                ownership = (_text(nature_node, "directOrIndirectOwnership") or "D").upper()
                nature = _text(nature_node, "natureOfOwnership") or ""
                transaction_date = _parse_date(_text(node, "transactionDate"))
                for owner in owners:
                    rows.append(
                        {
                            **owner,
                            "shares": shares,
                            "ownership": ownership,
                            "nature": nature,
                            "transaction_date": transaction_date,
                            "as_of": period,
                        }
                    )
    return rows
