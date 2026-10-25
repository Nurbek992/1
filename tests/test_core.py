import unittest
from decimal import Decimal

from exchange import (
    ExchangeOffice,
    InsufficientFundsError,
    InvalidAmountError,
    InvalidCurrencyError,
    InvalidRateError,
    UnknownRateError,
)


def make_office() -> ExchangeOffice:
    office = ExchangeOffice("RUB")
    office.deposit("RUB", "100000")
    office.set_rate("USD", "90", "92")
    return office


class RateTests(unittest.TestCase):
    def test_set_rate(self):
        office = ExchangeOffice("RUB")
        rate = office.set_rate("usd", "90,5", "92")
        self.assertEqual(rate.buy, Decimal("90.5"))
        self.assertEqual(rate.sell, Decimal("92"))
        self.assertIn("USD", office.rates)

    def test_buy_rate_above_sell_rejected(self):
        with self.assertRaises(InvalidRateError):
            ExchangeOffice("RUB").set_rate("USD", "93", "92")

    def test_non_positive_rate_rejected(self):
        with self.assertRaises(InvalidRateError):
            ExchangeOffice("RUB").set_rate("USD", "0", "92")

    def test_base_currency_rate_rejected(self):
        with self.assertRaises(InvalidCurrencyError):
            ExchangeOffice("RUB").set_rate("RUB", "1", "1")

    def test_bad_currency_code(self):
        with self.assertRaises(InvalidCurrencyError):
            ExchangeOffice("RUB").set_rate("US", "1", "2")

    def test_remove_rate(self):
        office = make_office()
        office.remove_rate("USD")
        with self.assertRaises(UnknownRateError):
            office.buy("USD", "1")


class TradeTests(unittest.TestCase):
    def test_buy_pays_client_at_buy_rate(self):
        office = make_office()
        tx = office.buy("USD", "100")
        self.assertEqual(tx.base_amount, Decimal("9000.00"))
        self.assertEqual(office.balance("RUB"), Decimal("91000.00"))
        self.assertEqual(office.balance("USD"), Decimal("100.00"))

    def test_sell_charges_client_at_sell_rate_and_records_profit(self):
        office = make_office()
        office.buy("USD", "100")
        tx = office.sell("USD", "40")
        self.assertEqual(tx.base_amount, Decimal("3680.00"))
        self.assertEqual(tx.profit, Decimal("80.00"))
        self.assertEqual(office.balance("USD"), Decimal("60.00"))
        self.assertEqual(office.balance("RUB"), Decimal("94680.00"))
        self.assertEqual(office.total_profit(), Decimal("80.00"))

    def test_average_cost_across_rates(self):
        office = make_office()
        office.buy("USD", "100")  # по 90
        office.set_rate("USD", "94", "96")
        office.buy("USD", "100")  # по 94
        self.assertEqual(office.avg_cost["USD"], Decimal("92"))
        tx = office.sell("USD", "200")  # по 96
        self.assertEqual(tx.profit, Decimal("800.00"))
        self.assertNotIn("USD", office.avg_cost)

    def test_cannot_sell_more_than_in_stock(self):
        office = make_office()
        office.buy("USD", "10")
        with self.assertRaises(InsufficientFundsError):
            office.sell("USD", "11")
        self.assertEqual(office.balance("USD"), Decimal("10.00"))

    def test_cannot_buy_without_enough_base_currency(self):
        office = ExchangeOffice("RUB")
        office.set_rate("USD", "90", "92")
        office.deposit("RUB", "100")
        with self.assertRaises(InsufficientFundsError):
            office.buy("USD", "2")
        self.assertEqual(office.balance("RUB"), Decimal("100.00"))
        self.assertEqual(len(office.transactions), 1)

    def test_rounding_favours_office(self):
        office = ExchangeOffice("RUB")
        office.deposit("RUB", "1000")
        office.set_rate("EUR", "99.995", "100.005")
        self.assertEqual(office.quote("buy", "EUR", "1"), Decimal("99.99"))
        self.assertEqual(office.quote("sell", "EUR", "1"), Decimal("100.01"))

    def test_invalid_amounts(self):
        office = make_office()
        for bad in ("0", "-5", "abc", "1.001", "nan", "inf"):
            with self.subTest(amount=bad), self.assertRaises(InvalidAmountError):
                office.buy("USD", bad)

    def test_cannot_trade_base_currency(self):
        with self.assertRaises(InvalidCurrencyError):
            make_office().buy("RUB", "1")

    def test_foreign_deposit_uses_buy_rate_as_cost(self):
        office = make_office()
        office.deposit("USD", "50")
        self.assertEqual(office.avg_cost["USD"], Decimal("90"))
        tx = office.sell("USD", "50")
        self.assertEqual(tx.profit, Decimal("100.00"))

    def test_foreign_deposit_without_rate_rejected(self):
        with self.assertRaises(UnknownRateError):
            make_office().deposit("EUR", "10")

    def test_withdraw(self):
        office = make_office()
        office.withdraw("RUB", "500")
        self.assertEqual(office.balance("RUB"), Decimal("99500.00"))
        with self.assertRaises(InsufficientFundsError):
            office.withdraw("RUB", "1000000")


class ReportTests(unittest.TestCase):
    def test_turnover_and_profit_by_currency(self):
        office = make_office()
        office.set_rate("EUR", "100", "103")
        office.buy("USD", "100")
        office.buy("EUR", "10")
        office.sell("USD", "30")
        office.sell("EUR", "10")
        self.assertEqual(office.turnover()["USD"], {"buy": Decimal("100.00"), "sell": Decimal("30.00")})
        self.assertEqual(office.profit_by_currency(), {"USD": Decimal("60.00"), "EUR": Decimal("30.00")})
        self.assertEqual(office.total_profit(), Decimal("90.00"))


class SerializationTests(unittest.TestCase):
    def test_round_trip(self):
        office = make_office()
        office.buy("USD", "100")
        office.sell("USD", "25")
        restored = ExchangeOffice.from_dict(office.to_dict())
        self.assertEqual(restored.to_dict(), office.to_dict())
        self.assertEqual(restored.transactions, office.transactions)


if __name__ == "__main__":
    unittest.main()
