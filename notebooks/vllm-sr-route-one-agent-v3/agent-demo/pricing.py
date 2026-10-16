def customer_total(subtotal: float, premium: bool) -> float:
    discount = 0.10 if premium else 0.0
    return round(subtotal * (1 - discount), 2)


def invoice_total(subtotal: float, premium: bool) -> float:
    discount = 0.10 if premium else 0.0
    return round(subtotal * (1 - discount), 2)
