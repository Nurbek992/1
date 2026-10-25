"""Логика обменного пункта: курсы, касса, покупка и продажа валюты.

Все операции описаны с точки зрения обменного пункта:

* ``buy``  — пункт покупает иностранную валюту у клиента по курсу покупки
  и выдаёт клиенту базовую валюту;
* ``sell`` — пункт продаёт иностранную валюту клиенту по курсу продажи
  и получает от клиента базовую валюту.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
RATE_PRECISION = Decimal("0.000001")

BUY = "buy"
SELL = "sell"
DEPOSIT = "deposit"
WITHDRAW = "withdraw"


class ExchangeError(Exception):
    """Базовая ошибка обменного пункта."""


class InvalidCurrencyError(ExchangeError):
    pass


class InvalidAmountError(ExchangeError):
    pass


class InvalidRateError(ExchangeError):
    pass


class UnknownRateError(ExchangeError):
    pass


class InsufficientFundsError(ExchangeError):
    pass


def normalize_currency(code: str) -> str:
    code = str(code).strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise InvalidCurrencyError(f"Некорректный код валюты: {code!r} (нужно 3 буквы, например USD)")
    return code


def to_decimal(value, what: str = "сумма") -> Decimal:
    try:
        result = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        raise InvalidAmountError(f"Некорректная {what}: {value!r}") from None
    if not result.is_finite():
        raise InvalidAmountError(f"Некорректная {what}: {value!r}")
    return result


def to_amount(value) -> Decimal:
    amount = to_decimal(value, "сумма")
    if amount <= 0:
        raise InvalidAmountError("Сумма должна быть больше нуля")
    if amount != amount.quantize(CENT):
        raise InvalidAmountError("Сумма может содержать не больше двух знаков после запятой")
    return amount.quantize(CENT)


@dataclass(frozen=True)
class Rate:
    """Курс за 1 единицу иностранной валюты в базовой валюте."""

    buy: Decimal
    sell: Decimal

    def to_dict(self) -> dict:
        return {"buy": str(self.buy), "sell": str(self.sell)}

    @classmethod
    def from_dict(cls, data: dict) -> "Rate":
        return cls(buy=Decimal(data["buy"]), sell=Decimal(data["sell"]))


@dataclass(frozen=True)
class Transaction:
    id: int
    kind: str
    currency: str
    amount: Decimal
    rate: Decimal | None
    base_amount: Decimal
    profit: Decimal
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "currency": self.currency,
            "amount": str(self.amount),
            "rate": None if self.rate is None else str(self.rate),
            "base_amount": str(self.base_amount),
            "profit": str(self.profit),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Transaction":
        return cls(
            id=int(data["id"]),
            kind=data["kind"],
            currency=data["currency"],
            amount=Decimal(data["amount"]),
            rate=None if data.get("rate") is None else Decimal(data["rate"]),
            base_amount=Decimal(data["base_amount"]),
            profit=Decimal(data["profit"]),
            timestamp=data["timestamp"],
        )


class ExchangeOffice:
    """Обменный пункт с кассой в нескольких валютах.

    Для каждой иностранной валюты хранится средняя себестоимость остатка
    (по скользящему среднему курсу покупки). При продаже прибыль считается
    как ``(курс продажи - себестоимость) * сумма``.
    """

    def __init__(self, base_currency: str = "RUB"):
        self.base_currency = normalize_currency(base_currency)
        self.rates: dict[str, Rate] = {}
        self.balances: dict[str, Decimal] = {}
        self.avg_cost: dict[str, Decimal] = {}
        self.transactions: list[Transaction] = []

    # --- курсы -------------------------------------------------------------

    def set_rate(self, currency: str, buy, sell) -> Rate:
        currency = self._foreign(currency)
        buy = to_decimal(buy, "курс покупки")
        sell = to_decimal(sell, "курс продажи")
        if buy <= 0 or sell <= 0:
            raise InvalidRateError("Курс должен быть больше нуля")
        if buy > sell:
            raise InvalidRateError("Курс покупки не может быть выше курса продажи")
        rate = Rate(buy=buy.quantize(RATE_PRECISION).normalize(), sell=sell.quantize(RATE_PRECISION).normalize())
        self.rates[currency] = rate
        return rate

    def remove_rate(self, currency: str) -> None:
        currency = self._foreign(currency)
        if currency not in self.rates:
            raise UnknownRateError(f"Курс для {currency} не задан")
        del self.rates[currency]

    def get_rate(self, currency: str) -> Rate:
        currency = self._foreign(currency)
        try:
            return self.rates[currency]
        except KeyError:
            raise UnknownRateError(f"Курс для {currency} не задан") from None

    # --- касса -------------------------------------------------------------

    def balance(self, currency: str) -> Decimal:
        return self.balances.get(normalize_currency(currency), Decimal("0.00"))

    def deposit(self, currency: str, amount) -> Transaction:
        """Внести наличные в кассу.

        Себестоимостью внесённой иностранной валюты считается текущий курс покупки.
        """
        currency = normalize_currency(currency)
        amount = to_amount(amount)
        rate = None
        base_amount = amount
        if currency != self.base_currency:
            rate = self.get_rate(currency).buy
            base_amount = (amount * rate).quantize(CENT, ROUND_HALF_UP)
            self._add_inventory(currency, amount, rate)
        else:
            self._change(currency, amount)
        return self._record(DEPOSIT, currency, amount, rate, base_amount)

    def withdraw(self, currency: str, amount) -> Transaction:
        """Изъять наличные из кассы."""
        currency = normalize_currency(currency)
        amount = to_amount(amount)
        self._require(currency, amount)
        self._change(currency, -amount)
        cost = self.avg_cost.get(currency) if currency != self.base_currency else None
        base_amount = amount if cost is None else (amount * cost).quantize(CENT, ROUND_HALF_UP)
        self._drop_cost_if_empty(currency)
        return self._record(WITHDRAW, currency, amount, cost, base_amount)

    # --- обмен -------------------------------------------------------------

    def quote(self, kind: str, currency: str, amount) -> Decimal:
        """Сколько базовой валюты пункт выдаст (buy) или получит (sell) за ``amount``."""
        amount = to_amount(amount)
        rate = self.get_rate(currency)
        if kind == BUY:
            # Выдаём клиенту — округляем вниз, в пользу пункта.
            return (amount * rate.buy).quantize(CENT, ROUND_DOWN)
        if kind == SELL:
            # Получаем от клиента — округляем вверх, в пользу пункта.
            return (amount * rate.sell).quantize(CENT, ROUND_UP)
        raise ExchangeError(f"Неизвестный тип операции: {kind!r}")

    def buy(self, currency: str, amount) -> Transaction:
        """Купить у клиента ``amount`` иностранной валюты."""
        currency = self._foreign(currency)
        amount = to_amount(amount)
        rate = self.get_rate(currency).buy
        payout = self.quote(BUY, currency, amount)
        self._require(self.base_currency, payout)
        self._change(self.base_currency, -payout)
        self._add_inventory(currency, amount, rate)
        return self._record(BUY, currency, amount, rate, payout)

    def sell(self, currency: str, amount) -> Transaction:
        """Продать клиенту ``amount`` иностранной валюты."""
        currency = self._foreign(currency)
        amount = to_amount(amount)
        rate = self.get_rate(currency).sell
        self._require(currency, amount)
        received = self.quote(SELL, currency, amount)
        cost = (amount * self.avg_cost[currency]).quantize(CENT, ROUND_HALF_UP)
        profit = received - cost
        self._change(currency, -amount)
        self._change(self.base_currency, received)
        self._drop_cost_if_empty(currency)
        return self._record(SELL, currency, amount, rate, received, profit)

    # --- отчёты ------------------------------------------------------------

    def total_profit(self) -> Decimal:
        return sum((t.profit for t in self.transactions), Decimal("0.00"))

    def profit_by_currency(self) -> dict[str, Decimal]:
        result: dict[str, Decimal] = {}
        for t in self.transactions:
            if t.kind == SELL:
                result[t.currency] = result.get(t.currency, Decimal("0.00")) + t.profit
        return result

    def turnover(self) -> dict[str, dict[str, Decimal]]:
        """Объём купленной и проданной валюты по каждой валюте."""
        result: dict[str, dict[str, Decimal]] = {}
        for t in self.transactions:
            if t.kind in (BUY, SELL):
                entry = result.setdefault(t.currency, {BUY: Decimal("0.00"), SELL: Decimal("0.00")})
                entry[t.kind] += t.amount
        return result

    # --- сериализация ------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "base_currency": self.base_currency,
            "rates": {c: r.to_dict() for c, r in sorted(self.rates.items())},
            "balances": {c: str(v) for c, v in sorted(self.balances.items())},
            "avg_cost": {c: str(v) for c, v in sorted(self.avg_cost.items())},
            "transactions": [t.to_dict() for t in self.transactions],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExchangeOffice":
        office = cls(data["base_currency"])
        office.rates = {c: Rate.from_dict(r) for c, r in data.get("rates", {}).items()}
        office.balances = {c: Decimal(v) for c, v in data.get("balances", {}).items()}
        office.avg_cost = {c: Decimal(v) for c, v in data.get("avg_cost", {}).items()}
        office.transactions = [Transaction.from_dict(t) for t in data.get("transactions", [])]
        return office

    # --- внутреннее --------------------------------------------------------

    def _foreign(self, currency: str) -> str:
        currency = normalize_currency(currency)
        if currency == self.base_currency:
            raise InvalidCurrencyError(f"{currency} — базовая валюта пункта, её нельзя покупать или продавать")
        return currency

    def _require(self, currency: str, amount: Decimal) -> None:
        available = self.balance(currency)
        if available < amount:
            raise InsufficientFundsError(
                f"Недостаточно {currency} в кассе: нужно {amount}, есть {available}"
            )

    def _change(self, currency: str, delta: Decimal) -> None:
        self.balances[currency] = (self.balance(currency) + delta).quantize(CENT)

    def _add_inventory(self, currency: str, amount: Decimal, rate: Decimal) -> None:
        held = self.balance(currency)
        old_cost = self.avg_cost.get(currency, rate)
        new_cost = (held * old_cost + amount * rate) / (held + amount)
        self.avg_cost[currency] = new_cost.quantize(RATE_PRECISION, ROUND_HALF_UP)
        self._change(currency, amount)

    def _drop_cost_if_empty(self, currency: str) -> None:
        if currency != self.base_currency and self.balance(currency) == 0:
            self.avg_cost.pop(currency, None)

    def _record(
        self,
        kind: str,
        currency: str,
        amount: Decimal,
        rate: Decimal | None,
        base_amount: Decimal,
        profit: Decimal = Decimal("0.00"),
    ) -> Transaction:
        tx = Transaction(
            id=len(self.transactions) + 1,
            kind=kind,
            currency=currency,
            amount=amount,
            rate=rate,
            base_amount=base_amount,
            profit=profit.quantize(CENT),
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self.transactions.append(tx)
        return tx
