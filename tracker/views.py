from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import login, authenticate, logout
from .models import Group, Expense, Split, Settlement, Category
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import TruncMonth
import json

from tracker.services.authz import get_group_for_user_or_404
from tracker.services.balances import compute_net_balances
from tracker.forms import GroupForm, ExpenseForm, SettlementForm, build_splits_for_expense
from tracker.services.authz import get_expense_for_user_or_404


def _ensure_default_categories():
    default_categories = [
        "Food",
        "Transport",
        "Rent",
        "Utilities",
        "Entertainment",
        "Shopping",
        "Health",
        "Other",
    ]
    for name in default_categories:
        Category.objects.get_or_create(name=name)


@login_required
def groups_list(request):
    groups = Group.objects.filter(members=request.user).order_by("name")
    return render(request, "tracker/groups_list.html", {"groups": groups})


# SIGNUP
def signup(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']

        user = User.objects.create_user(username=username, password=password)
        login(request, user)
        return redirect('groups_list')

    return render(request, 'tracker/signup.html')


# LOGIN
def login_view(request):
    if request.method == "POST":
        user = authenticate(
            username=request.POST['username'],
            password=request.POST['password']
        )

        if user:
            login(request, user)
            return redirect('groups_list')

    return render(request, 'tracker/login.html')


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "Logged out.")
    return redirect("login")

@login_required
def group_create(request):
    if request.method == "POST":
        form = GroupForm(request_user=request.user, data=request.POST)
        if form.is_valid():
            group = form.save()
            group.members.add(request.user)
            messages.success(request, "Group created.")
            return redirect("group_dashboard", group_id=group.id)
    else:
        form = GroupForm(request_user=request.user)

    return render(request, "tracker/group_form.html", {"form": form})


@login_required
def group_dashboard(request, group_id: int):
    group = get_group_for_user_or_404(group_id=group_id, user=request.user)
    group_expenses = Expense.objects.filter(group=group)

    expenses = (
        group_expenses
        .select_related("payer", "category")
        .prefetch_related("split_set__user")
        .order_by("-date", "-id")[:20]
    )

    settlements = (
        Settlement.objects.filter(group=group)
        .select_related("payer", "receiver")
        .order_by("-date", "-id")[:20]
    )

    net_by_user = compute_net_balances(group=group)
    balances = {u.username: amt for u, amt in net_by_user.items()}

    category_totals = (
        group_expenses.values("category__name")
        .annotate(total=Sum("amount"))
        .order_by("category__name")
    )
    labels = [item["category__name"] or "Uncategorized" for item in category_totals]
    values = [float(item["total"]) for item in category_totals]

    monthly_totals = (
        group_expenses.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )
    month_labels = [item["month"].strftime("%b %Y") for item in monthly_totals]
    month_values = [float(item["total"]) for item in monthly_totals]

    trend_totals = (
        group_expenses.values("date")
        .annotate(total=Sum("amount"))
        .order_by("date")
    )
    trend_labels = [item["date"].strftime("%d %b") for item in trend_totals]
    trend_values = [float(item["total"]) for item in trend_totals]

    total_spend = float(group_expenses.aggregate(total=Sum("amount"))["total"] or 0)

    return render(
        request,
        "tracker/group_dashboard.html",
        {
            "group": group,
            "groups": Group.objects.filter(members=request.user).order_by("name"),
            "expenses": expenses,
            "settlements": settlements,
            "balances": balances,
            "labels": json.dumps(labels),
            "values": json.dumps(values),
            "month_labels": json.dumps(month_labels),
            "month_values": json.dumps(month_values),
            "trend_labels": json.dumps(trend_labels),
            "trend_values": json.dumps(trend_values),
            "total_spend": total_spend,
            "has_expense_data": bool(values),
        },
    )


@login_required
@transaction.atomic
def expense_create(request, group_id: int):
    group = get_group_for_user_or_404(group_id=group_id, user=request.user)
    members = group.members.all().order_by("username")
    _ensure_default_categories()

    if request.method == "POST":
        form = ExpenseForm(group=group, request_user=request.user, data=request.POST)
        if form.is_valid():
            expense: Expense = form.save(commit=False)
            expense.group = group
            expense.save()

            try:
                splits = build_splits_for_expense(
                    expense=expense,
                    members=members,
                    split_type=expense.split_type,
                    posted_data=request.POST,
                )
            except Exception as exc:
                expense.delete()
                messages.error(request, str(exc))
                return render(
                    request,
                    "tracker/expense_form.html",
                    {"group": group, "form": form, "members": members},
                )

            Split.objects.bulk_create(splits)
            messages.success(request, "Expense added.")
            return redirect("group_dashboard", group_id=group.id)
    else:
        form = ExpenseForm(group=group, request_user=request.user)

    return render(request, "tracker/expense_form.html", {"group": group, "form": form, "members": members})


@login_required
def settle_create(request, group_id: int):
    group = get_group_for_user_or_404(group_id=group_id, user=request.user)
    if request.method == "POST":
        form = SettlementForm(group=group, payer=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Settlement recorded.")
            return redirect("group_dashboard", group_id=group.id)
    else:
        form = SettlementForm(group=group, payer=request.user)

    return render(request, "tracker/settlement_form.html", {"group": group, "form": form})


@login_required
@transaction.atomic
def expense_edit(request, group_id: int, expense_id: int):
    group = get_group_for_user_or_404(group_id=group_id, user=request.user)
    expense = get_expense_for_user_or_404(expense_id=expense_id, user=request.user)
    if expense.group_id != group.id:
        messages.error(request, "Invalid expense.")
        return redirect("group_dashboard", group_id=group.id)

    members = group.members.all().order_by("username")
    _ensure_default_categories()

    if request.method == "POST":
        form = ExpenseForm(instance=expense, group=group, request_user=request.user, data=request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.group = group
            expense.save()
            Split.objects.filter(expense=expense).delete()

            splits = build_splits_for_expense(
                expense=expense,
                members=members,
                split_type=expense.split_type,
                posted_data=request.POST,
            )
            Split.objects.bulk_create(splits)
            messages.success(request, "Expense updated.")
            return redirect("group_dashboard", group_id=group.id)
    else:
        form = ExpenseForm(instance=expense, group=group, request_user=request.user)

    return render(
        request,
        "tracker/expense_form.html",
        {"group": group, "form": form, "members": members, "is_edit": True, "expense": expense},
    )


@login_required
@transaction.atomic
def expense_delete(request, group_id: int, expense_id: int):
    group = get_group_for_user_or_404(group_id=group_id, user=request.user)
    expense = get_expense_for_user_or_404(expense_id=expense_id, user=request.user)
    if expense.group_id != group.id:
        messages.error(request, "Invalid expense.")
        return redirect("group_dashboard", group_id=group.id)

    if request.method == "POST":
        expense.delete()
        messages.success(request, "Expense deleted.")
        return redirect("group_dashboard", group_id=group.id)

    return render(request, "tracker/expense_delete_confirm.html", {"group": group, "expense": expense})


@login_required
def leave_group(request, group_id: int):
    group = get_group_for_user_or_404(group_id=group_id, user=request.user)
    if request.method == "POST":
        group.members.remove(request.user)
        messages.success(request, f"You left {group.name}.")
        return redirect("groups_list")
    return render(request, "tracker/leave_group_confirm.html", {"group": group})

"""
Expense CRUD, leave group, settle-up are implemented in later phases (ModelForms + balances).
Existing add_expense/create_group handlers were replaced by group-scoped dashboards.
"""