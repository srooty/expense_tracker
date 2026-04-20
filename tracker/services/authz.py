from __future__ import annotations

from django.http import Http404

from tracker.models import Expense, Group


def get_group_for_user_or_404(*, group_id: int, user) -> Group:
    try:
        return Group.objects.get(id=group_id, members=user)
    except Group.DoesNotExist as exc:
        raise Http404("Group not found") from exc


def get_expense_for_user_or_404(*, expense_id: int, user) -> Expense:
    try:
        return Expense.objects.select_related("group", "payer", "category").get(
            id=expense_id,
            group__members=user,
        )
    except Expense.DoesNotExist as exc:
        raise Http404("Expense not found") from exc

