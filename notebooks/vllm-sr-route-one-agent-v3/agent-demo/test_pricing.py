from pricing import customer_total, invoice_total
from reporting import render_report


def test_regular_customer_totals() -> None:
    assert customer_total(100, False) == 100
    assert invoice_total(100, False) == 100


def test_premium_customer_totals() -> None:
    assert customer_total(100, True) == 90
    assert invoice_total(100, True) == 90


def test_report() -> None:
    assert render_report(100, True) == "customer=90.00\ninvoice=90.00\n"
