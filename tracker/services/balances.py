from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.contrib.auth.models import User

from tracker.models import Expense, Group, Settlement, Split


TWOPLACES = Decimal("0.01")


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
        net[u] = net[u].quantize(TWOPLACES)

    return dict(net)


def simplify_debts(group: Group) -> list[dict[str, User | Decimal]]:
    """
    Build a minimal-looking set of settlements for a group's expense history.

    Steps:
      1. Compute how much each user paid across the group's expenses.
      2. Compute how much each user owes from the recorded splits.
      3. Convert those totals into a net balance per user.
         - positive => creditor (they should receive money)
         - negative => debtor (they should pay money)
      4. Greedily match the largest creditor with the largest debtor until all
         balances are settled.

    The greedy approach avoids circular debts and produces a clean settlement
    list with a low number of transactions.
    """
    total_paid: dict[User, Decimal] = defaultdict(lambda: Decimal("0.00"))
    total_share: dict[User, Decimal] = defaultdict(lambda: Decimal("0.00"))

    # Start every group member at zero so members with no activity are handled
    # consistently and never raise missing-key issues.
    members = list(group.members.all().order_by("username"))
    for member in members:
        total_paid[member] = Decimal("0.00")
        total_share[member] = Decimal("0.00")

    # Sum the full amount each payer covered for the group.
    expenses = (
        Expense.objects.filter(group=group)
        .select_related("payer")
        .only("amount", "payer_id")
    )
    for expense in expenses:
        total_paid[expense.payer] += expense.amount

    # Sum each participant's share of those expenses.
    splits = (
        Split.objects.filter(expense__group=group)
        .select_related("user")
        .only("amount", "user_id")
    )
    for split in splits:
        total_share[split.user] += split.amount

    # Apply any already-recorded settlements so we only suggest the remaining
    # outstanding transfers.
    recorded_settlements = (
        Settlement.objects.filter(group=group)
        .select_related("payer", "receiver")
        .only("amount", "payer_id", "receiver_id")
    )
    for settlement in recorded_settlements:
        total_paid[settlement.payer] += settlement.amount
        total_paid[settlement.receiver] -= settlement.amount

    # Convert the totals into net balances.
    creditors: list[list[User | Decimal]] = []
    debtors: list[list[User | Decimal]] = []

    for member in members:
        net_balance = (total_paid[member] - total_share[member]).quantize(TWOPLACES)
        if net_balance > Decimal("0.00"):
            creditors.append([member, net_balance])
        elif net_balance < Decimal("0.00"):
            debtors.append([member, net_balance])

    # Highest positive balance first, most negative balance first.
    creditors.sort(key=lambda item: item[1], reverse=True)
    debtors.sort(key=lambda item: item[1])

    settlements: list[dict[str, User | Decimal]] = []
    creditor_index = 0
    debtor_index = 0

    while creditor_index < len(creditors) and debtor_index < len(debtors):
        creditor_user, creditor_amount = creditors[creditor_index]
        debtor_user, debtor_amount = debtors[debtor_index]

        settlement_amount = min(creditor_amount, abs(debtor_amount)).quantize(TWOPLACES)
        settlements.append(
            {
                "from": debtor_user,
                "to": creditor_user,
                "amount": settlement_amount,
            }
        )

        creditor_amount = (creditor_amount - settlement_amount).quantize(TWOPLACES)
        debtor_amount = (debtor_amount + settlement_amount).quantize(TWOPLACES)

        creditors[creditor_index][1] = creditor_amount
        debtors[debtor_index][1] = debtor_amount

        if creditor_amount == Decimal("0.00"):
            creditor_index += 1
        if debtor_amount == Decimal("0.00"):
            debtor_index += 1

    return settlements
