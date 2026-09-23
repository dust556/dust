"""Command-line interface.

    smallcap screen   --tickers AAPL,MSFT --out out/
    smallcap screen   --provider fixtures --fixtures data/fixtures --out out/
    smallcap explain  IDEAL --provider fixtures
    smallcap universe --exchanges Nasdaq,NYSE --out universe.txt
    smallcap dump-fixture ACME --out data/fixtures/

Every run is fully described by its arguments: provider, as-of date, config
file and any ``--set`` overrides are all echoed into the JSON output so a
result can be reproduced later.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
from dataclasses import asdict
from typing import List, Optional, Sequence

from . import __version__
from .config import Config
from .engine import ScreeningEngine
from .models import _jsonable
from .providers.base import ProviderError
from .providers.fixtures import FixtureProvider
from .providers.prices import PriceProvider
from .providers.sec_edgar import SECEdgarProvider
from .report import format_console, write_reports
from .scoring import summarise
from .util.http import HttpClient

LOGGER = logging.getLogger("smallcap")


# ----------------------------------------------------------------------
def build_config(args: argparse.Namespace) -> Config:
    config = Config.load(getattr(args, "config", None))
    if getattr(args, "as_of", None):
        # Validate early: a malformed date silently disabling point-in-time
        # filtering would be the worst possible failure mode here.
        dt.date.fromisoformat(args.as_of)
        config.as_of = args.as_of
    if getattr(args, "workers", None):
        config.workers = args.workers
    if getattr(args, "user_agent", None):
        config.user_agent = args.user_agent
    if getattr(args, "cache_dir", None):
        config.cache_dir = args.cache_dir
    for override in getattr(args, "set", None) or []:
        if "=" not in override:
            raise SystemExit(f"--set expects key=value, got: {override}")
        key, value = override.split("=", 1)
        config.override(key.strip(), value.strip())
    if getattr(args, "ai", False):
        config.ai.enabled = True
    if getattr(args, "ai_model", None):
        config.ai.model = args.ai_model
    return config


def build_provider(args: argparse.Namespace, config: Config):
    name = getattr(args, "provider", "sec")
    if name in ("fixtures", "fixture"):
        return FixtureProvider(getattr(args, "fixtures", "data/fixtures"))

    http = HttpClient(
        user_agent=config.user_agent,
        cache_dir=config.cache_dir,
        cache_ttl_hours=config.cache_ttl_hours,
        min_interval=config.request_delay_seconds,
        max_retries=config.max_retries,
        timeout=config.timeout_seconds,
        offline=getattr(args, "offline", False),
    )
    prices = PriceProvider(
        http=http,
        prices_dir=getattr(args, "prices_dir", None),
        allow_network=not getattr(args, "no_price_network", False),
    )
    return SECEdgarProvider(config, http=http, price_provider=prices)


def _check_user_agent(config: Config) -> None:
    """EDGAR rejects requests without a real contact address."""
    if "set SEC_USER_AGENT" in config.user_agent:
        LOGGER.warning(
            "SEC EDGAR requires a descriptive User-Agent with a contact address. "
            "Set SEC_USER_AGENT='Your Name your@email' or pass --user-agent, "
            "or requests will be blocked."
        )


def read_tickers(args: argparse.Namespace) -> List[str]:
    tickers: List[str] = []
    if getattr(args, "tickers", None):
        tickers.extend(t.strip() for t in args.tickers.split(",") if t.strip())
    if getattr(args, "universe_file", None):
        with open(args.universe_file, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.split("#", 1)[0].strip()
                if line:
                    tickers.append(line)
    # De-duplicate while preserving the order the user gave.
    seen = set()
    ordered = []
    for ticker in tickers:
        upper = ticker.upper()
        if upper not in seen:
            seen.add(upper)
            ordered.append(upper)
    return ordered


# ----------------------------------------------------------------------
def cmd_screen(args: argparse.Namespace) -> int:
    config = build_config(args)
    provider = build_provider(args, config)
    if args.provider not in ("fixtures", "fixture"):
        _check_user_agent(config)

    tickers = read_tickers(args)
    if not tickers:
        if hasattr(provider, "universe"):
            LOGGER.info("no tickers given; screening the provider's full universe")
            tickers = provider.universe()
        if not tickers:
            raise SystemExit("no tickers to screen: pass --tickers or --universe-file")
    if args.limit:
        tickers = tickers[: args.limit]

    engine = ScreeningEngine(provider, config)

    def progress(done: int, total: int, result) -> None:
        if args.quiet:
            return
        status = "ERR " if result.error else ("PASS" if result.all_passed else "    ")
        print(
            f"[{done:>5}/{total}] {status} {result.ticker}",
            file=sys.stderr,
            flush=True,
        )

    results = engine.screen(tickers, progress=progress)
    ranked = engine.rank(results)

    if config.ai.enabled and ranked:
        _run_ai_review(config, ranked)

    stats = summarise(results)
    if not args.quiet:
        print(
            f"\nEvaluated {stats['evaluated']} of {stats['universe_size']} "
            f"({stats['fetch_errors']} errors); "
            f"{stats['passed_all']} cleared all five conditions.",
            file=sys.stderr,
        )

    if args.out:
        paths = write_reports(
            args.out,
            results,
            ranked,
            config=_jsonable(asdict(config)),
            as_of=config.as_of,
        )
        for kind, path in paths.items():
            print(f"wrote {kind}: {path}", file=sys.stderr)
    else:
        for result in ranked or results:
            print(format_console(result))
            print()
    return 0


def _run_ai_review(config: Config, ranked: Sequence) -> None:
    from .ai import AnalystUnavailable, ClaudeAnalyst

    analyst = ClaudeAnalyst(config.ai)
    try:
        analyst.review_all(ranked)
    except AnalystUnavailable as exc:
        # The qualitative layer is commentary; losing it must not lose the run.
        LOGGER.warning("AI review skipped: %s", exc)


def cmd_explain(args: argparse.Namespace) -> int:
    config = build_config(args)
    provider = build_provider(args, config)
    if args.provider not in ("fixtures", "fixture"):
        _check_user_agent(config)
    engine = ScreeningEngine(provider, config)
    result = engine.screen_one(args.ticker)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return 0 if not result.error else 1

    print(format_console(result))
    if result.error:
        return 1
    print()
    for criterion in result.criteria:
        if not criterion.detail:
            continue
        print(f"--- {criterion.key} detail ---")
        print(json.dumps(_jsonable(criterion.detail), indent=2, ensure_ascii=False))
        print()
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    from .backtest import Backtester, BacktestConfig, load_factors
    from .backtest import report as backtest_report

    config = build_config(args)
    provider = build_provider(args, config)
    if args.provider not in ("fixtures", "fixture"):
        _check_user_agent(config)

    backtest = BacktestConfig(
        start=dt.date.fromisoformat(args.start),
        end=dt.date.fromisoformat(args.end),
        frequency=args.frequency,
        reporting_lag_days=args.reporting_lag,
        max_holdings=args.max_holdings,
        weighting=args.weighting,
        missing_price_policy=args.missing_price_policy,
        benchmark=args.benchmark,
        factors=args.factors,
        universe_history=_load_universe_history(args.universe_history),
    )

    factor_data = None
    if args.factors:
        factor_data = load_factors(args.factors)

    tickers = read_tickers(args)
    if not tickers and hasattr(provider, "universe"):
        tickers = provider.universe()
    if not tickers:
        raise SystemExit("no tickers to backtest: pass --tickers or --universe-file")
    if args.limit:
        tickers = tickers[: args.limit]

    tester = Backtester(provider, config, backtest)

    def progress(done: int, total: int, period) -> None:
        if args.quiet:
            return
        print(
            f"[{done:>4}/{total}] {period.rebalance_date} "
            f"{len(period.positions)} holdings",
            file=sys.stderr,
            flush=True,
        )

    periods = tester.run(tickers, progress=progress)
    result = tester.analyse(periods, factor_data=factor_data)

    if args.ablation:
        if not args.quiet:
            print("running per-condition ablation...", file=sys.stderr)
        result.ablation = tester.ablation(tickers, factor_data=factor_data)

    if args.out:
        paths = backtest_report.write_reports(args.out, result)
        for kind, path in paths.items():
            print(f"wrote {kind}: {path}", file=sys.stderr)
    print(backtest_report.format_console(result))
    return 0


def _load_universe_history(path: Optional[str]) -> Optional[dict]:
    """Load a point-in-time universe: {"YYYY-MM-DD": [tickers]}.

    This is what removes survivorship bias, so a malformed file is an error
    rather than a silent fall back to today's listings.
    """
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not payload:
        raise ValueError(
            f"{path}: expected a non-empty object mapping ISO dates to ticker lists"
        )
    for key, value in payload.items():
        dt.date.fromisoformat(key)
        if not isinstance(value, list):
            raise ValueError(f"{path}: value for {key} is not a list of tickers")
    return {k: [str(t).upper() for t in v] for k, v in payload.items()}


def cmd_universe(args: argparse.Namespace) -> int:
    config = build_config(args)
    _check_user_agent(config)
    provider = build_provider(args, config)
    exchanges = (
        [e.strip() for e in args.exchanges.split(",") if e.strip()]
        if args.exchanges
        else None
    )
    if isinstance(provider, SECEdgarProvider):
        tickers = provider.universe(exchanges=exchanges)
    else:
        tickers = provider.universe()

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            for ticker in tickers:
                handle.write(f"{ticker}\n")
        print(f"wrote {len(tickers)} tickers to {args.out}", file=sys.stderr)
    else:
        for ticker in tickers:
            print(ticker)
    return 0


def cmd_universe_history(args: argparse.Namespace) -> int:
    """Build point-in-time universes from EDGAR's full index."""
    from .universe import (
        UniverseBuilder,
        coverage_report,
        to_universe_history,
    )
    from .backtest.calendar import rebalance_dates

    config = build_config(args)
    _check_user_agent(config)
    provider = build_provider(args, config)
    if not isinstance(provider, SECEdgarProvider):
        raise SystemExit("universe-history requires --provider sec")

    dates = rebalance_dates(
        dt.date.fromisoformat(args.start),
        dt.date.fromisoformat(args.end),
        args.frequency,
        args.reporting_lag,
    )
    if not dates:
        raise SystemExit("no rebalance dates in that window")

    builder = UniverseBuilder(
        http=provider.http,
        ticker_index=provider.ticker_index(),
        lookback_months=args.lookback_months,
    )

    def progress(done, total, snapshot):
        if args.quiet:
            return
        print(
            f"[{done:>3}/{total}] {snapshot.date}: {len(snapshot.ciks)} filers, "
            f"{len(snapshot.tickers)} investable",
            file=sys.stderr,
            flush=True,
        )

    snapshots = builder.build(dates, progress=progress)
    coverage = coverage_report(snapshots)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(to_universe_history(snapshots), handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"wrote universe history: {args.out}", file=sys.stderr)
    if args.coverage_out:
        with open(args.coverage_out, "w", encoding="utf-8") as handle:
            json.dump(coverage, handle, indent=2)
            handle.write("\n")
        print(f"wrote coverage report: {args.coverage_out}", file=sys.stderr)

    mean = coverage["mean_coverage"]
    worst = coverage["worst_coverage"]
    if mean is not None:
        print(
            f"\nticker coverage: mean {mean * 100:.1f}%, worst {worst * 100:.1f}%"
        )
        print(
            f"about {(1 - mean) * 100:.1f}% of historical filers have no ticker "
            "today (delisted, failed or acquired) and remain outside any "
            "backtest run on this universe."
        )
    return 0


def cmd_dump_fixture(args: argparse.Namespace) -> int:
    """Record a live fetch as a fixture, so a run can be replayed offline."""
    config = build_config(args)
    _check_user_agent(config)
    provider = build_provider(args, config)
    as_of = dt.date.fromisoformat(config.as_of) if config.as_of else None
    company = provider.fetch(args.ticker, as_of=as_of)

    payload = _jsonable(asdict(company))
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f"{company.ticker}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    print(f"wrote {path}", file=sys.stderr)
    return 0


# ----------------------------------------------------------------------
def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="path to a JSON (or YAML) config file")
    parser.add_argument(
        "--set",
        action="append",
        metavar="KEY=VALUE",
        help="override a config value, e.g. --set returns.min_roic=0.15",
    )
    parser.add_argument(
        "--as-of",
        help="ISO date; use only data that was publicly filed by then",
    )
    parser.add_argument(
        "--provider",
        default="sec",
        choices=["sec", "fixtures"],
        help="data source (default: sec)",
    )
    parser.add_argument(
        "--fixtures", default="data/fixtures", help="fixture directory"
    )
    parser.add_argument("--prices-dir", help="directory of TICKER.csv daily price files")
    parser.add_argument(
        "--no-price-network",
        action="store_true",
        help="never fetch prices over the network (use --prices-dir only)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="serve every request from the HTTP cache; a miss is an error",
    )
    parser.add_argument("--user-agent", help="User-Agent for SEC requests")
    parser.add_argument("--cache-dir", help="HTTP cache directory")
    parser.add_argument("--workers", type=int, help="parallel fetch workers")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="debug logging"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smallcap",
        description="US small-cap quantitative screening engine (five conditions).",
    )
    parser.add_argument("--version", action="version", version=f"smallcap {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    screen = subparsers.add_parser("screen", help="screen a list of tickers")
    _add_common(screen)
    screen.add_argument("--tickers", help="comma-separated tickers")
    screen.add_argument("--universe-file", help="file with one ticker per line")
    screen.add_argument("--limit", type=int, help="screen at most N tickers")
    screen.add_argument("--out", help="output directory for the reports")
    screen.add_argument("--quiet", action="store_true", help="suppress progress output")
    screen.add_argument(
        "--ai",
        action="store_true",
        help="add a Claude qualitative review of the top candidates "
        "(commentary only; never changes a verdict)",
    )
    screen.add_argument("--ai-model", help="model id for the AI review")
    screen.set_defaults(func=cmd_screen)

    explain = subparsers.add_parser(
        "explain", help="show every computed figure for one ticker"
    )
    _add_common(explain)
    explain.add_argument("ticker")
    explain.add_argument("--json", action="store_true", help="emit JSON")
    explain.set_defaults(func=cmd_explain)

    backtest = subparsers.add_parser(
        "backtest",
        help="run the screen through history and measure what it produced",
    )
    _add_common(backtest)
    backtest.add_argument("--start", required=True, help="ISO start date")
    backtest.add_argument("--end", required=True, help="ISO end date")
    backtest.add_argument(
        "--frequency",
        default="quarterly",
        choices=["monthly", "quarterly", "semiannual", "annual"],
        help="rebalance frequency (default: quarterly, matching filing cadence)",
    )
    backtest.add_argument(
        "--reporting-lag",
        type=int,
        default=75,
        help="days after period end before a filing is assumed public (default: 75)",
    )
    backtest.add_argument("--tickers", help="comma-separated tickers")
    backtest.add_argument("--universe-file", help="file with one ticker per line")
    backtest.add_argument(
        "--universe-history",
        help="JSON {date: [tickers]} of point-in-time listings; "
        "the only way to remove survivorship bias",
    )
    backtest.add_argument("--limit", type=int, help="use at most N tickers")
    backtest.add_argument("--benchmark", default="SPY", help="benchmark ticker")
    backtest.add_argument(
        "--max-holdings", type=int, help="cap the portfolio at N names"
    )
    backtest.add_argument(
        "--weighting",
        default="equal",
        choices=["equal", "score"],
        help="position weighting (default: equal)",
    )
    backtest.add_argument(
        "--missing-price-policy",
        default="drop",
        choices=["drop", "zero", "flat"],
        help="how to settle a position with no exit price; 'drop' flatters "
        "the result if the gaps are delistings, 'zero' is the pessimistic bound",
    )
    backtest.add_argument(
        "--factors",
        help="Fama-French factor CSV (Ken French data library), for alpha",
    )
    backtest.add_argument(
        "--ablation",
        action="store_true",
        help="also re-run with each condition removed in turn",
    )
    backtest.add_argument("--out", help="output directory for the reports")
    backtest.add_argument("--quiet", action="store_true", help="suppress progress")
    backtest.set_defaults(func=cmd_backtest)

    universe = subparsers.add_parser(
        "universe", help="list the screenable ticker universe"
    )
    _add_common(universe)
    universe.add_argument(
        "--exchanges", help="comma-separated exchange filter, e.g. Nasdaq,NYSE"
    )
    universe.add_argument("--out", help="write the tickers to this file")
    universe.set_defaults(func=cmd_universe)

    universe_history = subparsers.add_parser(
        "universe-history",
        help="build point-in-time universes from EDGAR's full index "
        "(reduces survivorship bias, and measures what is left)",
    )
    _add_common(universe_history)
    universe_history.add_argument("--start", required=True, help="ISO start date")
    universe_history.add_argument("--end", required=True, help="ISO end date")
    universe_history.add_argument(
        "--frequency",
        default="quarterly",
        choices=["monthly", "quarterly", "semiannual", "annual"],
        help="must match the backtest's rebalance frequency",
    )
    universe_history.add_argument("--reporting-lag", type=int, default=75)
    universe_history.add_argument(
        "--lookback-months",
        type=int,
        default=15,
        help="a company counts as active if it filed an annual report within "
        "this many months (default: 15, allowing for late filers)",
    )
    universe_history.add_argument("--out", help="write the universe history JSON here")
    universe_history.add_argument(
        "--coverage-out", help="write the survivorship coverage report here"
    )
    universe_history.add_argument("--quiet", action="store_true")
    universe_history.set_defaults(func=cmd_universe_history)

    dump = subparsers.add_parser(
        "dump-fixture", help="record a live fetch as a replayable fixture"
    )
    _add_common(dump)
    dump.add_argument("ticker")
    dump.add_argument("--out", default="data/fixtures", help="fixture directory")
    dump.set_defaults(func=cmd_dump_fixture)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except ProviderError as exc:
        # A run-level data failure (no ticker index, no credentials) is a
        # configuration problem for the user to act on, not a crash to debug.
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
