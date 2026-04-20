from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.contrib.auth.models import User

from tracker.models import Expense, Group, Settlement, Split


def compute_net_balances(*, group: Group) -> dict[User, Decimal]:
    """
    Net balance per user within a group.
    Convention:
      - positive => user is owed money (creditor)
      - negative => user owes money (debtor)
    """
    net: dict[User, Decimal] = defaultdict(lambda: Decimal("0.00"))

    expenses = (
        Expense.objects.filter(group=group)
        .select_related("payer")
        .only("id", "amount", "payer_id")
    )

    splits = (
        Split.objects.filter(expense__group=group)
        .select_related("user", "expense__payer")
        .only("id", "amount", "user_id", "expense_id", "expense__payer_id")
    )

    # Payer gets credited full amount.
    for e in expenses:
        net[e.payer] += e.amount

    # Every participant (including payer if present) owes their split.
    for s in splits:
        net[s.user] -= s.amount

    settlements = (
        Settlement.objects.filter(group=group)
        .select_related("payer", "receiver")
        .only("id", "amount", "payer_id", "receiver_id")
    )

    # Settlement: payer paid receiver, reducing payer debt and reducing receiver credit.
    for st in settlements:
        net[st.payer] += st.amount
        net[st.receiver] -= st.amount

    # Normalize to 2dp
    for u in list(net.keys()):
        net[u] = net[u].quantize(Decimal("0.01"))

    return dict(net)

