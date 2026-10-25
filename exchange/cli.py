"""Командная строка обменного пункта.

Примеры::

    python -m exchange init --base RUB
    python -m exchange deposit RUB 1000000
    python -m exchange rate USD 90.50 92.00
    python -m exchange buy USD 100
    python -m exchange sell USD 50
    python -m exchange balance
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

from . import storage
from .core import BUY, DEPOSIT, SELL, WITHDRAW, ExchangeError, ExchangeOffice

DEFAULT_DATA = "exchange_data.json"

KIND_NAMES = {
    BUY: "покупка",
    SELL: "продажа",
    DEPOSIT: "внесение",
    WITHDRAW: "изъятие",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="exchange", description="Обменный пункт: покупка и продажа валюты")
    parser.add_argument(
        "--data",
        default=os.environ.get("EXCHANGE_DATA", DEFAULT_DATA),
        help=f"файл с данными (по умолчанию $EXCHANGE_DATA или {DEFAULT_DATA})",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="команда")

    p = sub.add_parser("init", help="создать новый обменный пункт")
    p.add_argument("--base", default="RUB", help="базовая валюта (по умолчанию RUB)")
    p.add_argument("--force", action="store_true", help="перезаписать существующий файл")

    p = sub.add_parser("rate", help="установить курс покупки и продажи")
    p.add_argument("currency")
    p.add_argument("buy", help="курс покупки (пункт покупает)")
    p.add_argument("sell", help="курс продажи (пункт продаёт)")

    p = sub.add_parser("unrate", help="удалить курс валюты")
    p.add_argument("currency")

    sub.add_parser("rates", help="показать курсы")

    p = sub.add_parser("quote", help="рассчитать сумму без проведения операции")
    p.add_argument("kind", choices=[BUY, SELL])
    p.add_argument("currency")
    p.add_argument("amount")

    p = sub.add_parser("buy", help="купить валюту у клиента")
    p.add_argument("currency")
    p.add_argument("amount")

    p = sub.add_parser("sell", help="продать валюту клиенту")
    p.add_argument("currency")
    p.add_argument("amount")

    p = sub.add_parser("deposit", help="внести наличные в кассу")
    p.add_argument("currency")
    p.add_argument("amount")

    p = sub.add_parser("withdraw", help="изъять наличные из кассы")
    p.add_argument("currency")
    p.add_argument("amount")

    sub.add_parser("balance", help="остатки в кассе")

    p = sub.add_parser("history", help="журнал операций")
    p.add_argument("--limit", type=int, default=20, help="сколько последних операций показать (0 — все)")

    sub.add_parser("report", help="оборот и прибыль")

    return parser


def main(argv: list[str] | None = None, out=None) -> int:
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    path = Path(args.data)

    def say(text: str = "") -> None:
        print(text, file=out)

    try:
        if args.command == "init":
            if path.exists() and not args.force:
                raise ExchangeError(f"Файл {path} уже существует (используйте --force, чтобы перезаписать)")
            office = ExchangeOffice(args.base)
            storage.save(office, path)
            say(f"Создан обменный пункт, базовая валюта {office.base_currency}. Данные: {path}")
            return 0

        if not path.exists():
            raise ExchangeError(f"Файл {path} не найден. Сначала выполните: exchange init")
        office = storage.load(path)
        base = office.base_currency
        changed = True

        if args.command == "rate":
            rate = office.set_rate(args.currency, args.buy, args.sell)
            say(f"{args.currency.upper()}: покупка {rate.buy}, продажа {rate.sell} {base}")
        elif args.command == "unrate":
            office.remove_rate(args.currency)
            say(f"Курс {args.currency.upper()} удалён")
        elif args.command == "buy":
            tx = office.buy(args.currency, args.amount)
            say(f"Куплено {tx.amount} {tx.currency} по {tx.rate}. Выдать клиенту: {tx.base_amount} {base}")
        elif args.command == "sell":
            tx = office.sell(args.currency, args.amount)
            say(f"Продано {tx.amount} {tx.currency} по {tx.rate}. Получить от клиента: {tx.base_amount} {base}")
            say(f"Прибыль по операции: {tx.profit} {base}")
        elif args.command == "deposit":
            tx = office.deposit(args.currency, args.amount)
            say(f"Внесено {tx.amount} {tx.currency}. Остаток: {office.balance(tx.currency)} {tx.currency}")
        elif args.command == "withdraw":
            tx = office.withdraw(args.currency, args.amount)
            say(f"Изъято {tx.amount} {tx.currency}. Остаток: {office.balance(tx.currency)} {tx.currency}")
        else:
            changed = False
            if args.command == "rates":
                show_rates(office, say)
            elif args.command == "quote":
                total = office.quote(args.kind, args.currency, args.amount)
                action = "Выдать клиенту" if args.kind == BUY else "Получить от клиента"
                say(f"{action}: {total} {base}")
            elif args.command == "balance":
                show_balance(office, say)
            elif args.command == "history":
                show_history(office, say, args.limit)
            elif args.command == "report":
                show_report(office, say)

        if changed:
            storage.save(office, path)
        return 0
    except ExchangeError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1


def show_rates(office: ExchangeOffice, say) -> None:
    if not office.rates:
        say("Курсы не заданы. Используйте: exchange rate USD <покупка> <продажа>")
        return
    say(f"{'Валюта':<8}{'Покупка':>14}{'Продажа':>14}   ({office.base_currency} за 1 ед.)")
    for currency, rate in sorted(office.rates.items()):
        say(f"{currency:<8}{rate.buy:>14}{rate.sell:>14}")


def show_balance(office: ExchangeOffice, say) -> None:
    if not office.balances:
        say("Касса пуста")
        return
    say(f"{'Валюта':<8}{'Остаток':>16}{'Себестоимость':>16}")
    for currency, amount in sorted(office.balances.items()):
        cost = office.avg_cost.get(currency)
        say(f"{currency:<8}{amount:>16}{'' if cost is None else cost:>16}")


def show_history(office: ExchangeOffice, say, limit: int) -> None:
    txs = office.transactions if limit <= 0 else office.transactions[-limit:]
    if not txs:
        say("Операций нет")
        return
    for t in txs:
        rate = "" if t.rate is None else f" по {t.rate}"
        profit = f", прибыль {t.profit}" if t.kind == SELL else ""
        say(
            f"#{t.id} {t.timestamp} {KIND_NAMES.get(t.kind, t.kind)} "
            f"{t.amount} {t.currency}{rate} = {t.base_amount} {office.base_currency}{profit}"
        )


def show_report(office: ExchangeOffice, say) -> None:
    base = office.base_currency
    turnover = office.turnover()
    profits = office.profit_by_currency()
    if not turnover:
        say("Обменных операций ещё не было")
        return
    say(f"{'Валюта':<8}{'Куплено':>14}{'Продано':>14}{'Прибыль':>14}")
    for currency in sorted(turnover):
        entry = turnover[currency]
        say(f"{currency:<8}{entry[BUY]:>14}{entry[SELL]:>14}{profits.get(currency, Decimal('0.00')):>14}")
    say(f"Итого прибыль: {office.total_profit()} {base}")


if __name__ == "__main__":
    sys.exit(main())
