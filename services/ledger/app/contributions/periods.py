from datetime import date


def contribution_month(payment_date: date) -> tuple[int, int]:
    payment_month = payment_date.month
    payment_year = payment_date.year

    if payment_date.day >= 8:
        return (payment_year, payment_month)

    if payment_month == 1:
        return (payment_year - 1, 12)

    return (payment_year, payment_month - 1)
