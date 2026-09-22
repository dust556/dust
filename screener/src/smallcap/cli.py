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

    universe = subparsers.add_parser(
        "universe", help="list the screenable ticker universe"
    )
    _add_common(universe)
    universe.add_argument(
        "--exchanges", help="comma-separated exchange filter, e.g. Nasdaq,NYSE"
    )
    universe.add_argument("--out", help="write the tickers to this file")
    universe.set_defaults(func=cmd_universe)

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
