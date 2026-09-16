from pricing import customer_total, invoice_total


def render_report(subtotal: float, premium: bool) -> str:
    customer = customer_total(subtotal, premium)
    invoice = invoice_total(subtotal, premium)
    return f"customer={customer:.2f}\ninvoice={invoice:.2f}\n"
