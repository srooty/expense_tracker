from __future__ import annotations

from decimal import Decimal

from django import forms
from django.contrib.auth.models import User

from tracker.models import Category, Expense, Group, Settlement, Split


class GroupForm(forms.ModelForm):
    members = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Group
        fields = ["name", "members"]

    def __init__(self, *, request_user: User, **kwargs):
        super().__init__(**kwargs)
        self.fields["members"].queryset = User.objects.exclude(id=request_user.id).order_by("username")
        self.fields["name"].widget.attrs.update(
            {"class": "form-control", "placeholder": "Weekend trip, Flatmates, Office team"}
        )

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Please enter a group name.")
        return name


class ExpenseForm(forms.ModelForm):
    def __init__(self, *args, group: Group | None = None, request_user: User | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.group = group
        self.fields["category"].queryset = Category.objects.order_by("name")
        if group is not None:
            self.fields["payer"].queryset = group.members.all().order_by("username")
        else:
            self.fields["payer"].queryset = User.objects.none()
        if request_user is not None and not self.instance.pk:
            self.fields["payer"].initial = request_user.id
        self.fields["description"].widget.attrs.update(
            {"class": "form-control", "placeholder": "Dinner, groceries, cab ride"}
        )
        self.fields["amount"].widget.attrs.update(
            {"class": "form-control", "placeholder": "0.00", "min": "0.01", "step": "0.01"}
        )
        self.fields["date"].widget.attrs.update({"class": "form-control"})
        self.fields["category"].widget.attrs.update({"class": "form-select"})
        self.fields["payer"].widget.attrs.update({"class": "form-select"})
        self.fields["split_type"].widget.attrs.update({"class": "form-select"})

    class Meta:
        model = Expense
        fields = ["description", "amount", "date", "category", "payer", "split_type"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_description(self):
        description = (self.cleaned_data.get("description") or "").strip()
        if not description:
            raise forms.ValidationError("Please enter a description.")
        return description

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None or amount <= Decimal("0.00"):
            raise forms.ValidationError("Amount must be greater than 0.")
        return amount

    def clean(self):
        cleaned_data = super().clean()
        payer = cleaned_data.get("payer")
        if self.group is not None and payer and not self.group.members.filter(id=payer.id).exists():
            self.add_error("payer", "Selected payer must be a member of this group.")
        return cleaned_data


class SettlementForm(forms.ModelForm):
    class Meta:
        model = Settlement
        fields = ["receiver", "amount", "date"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *, group: Group, payer: User, **kwargs):
        super().__init__(**kwargs)
        self.group = group
        self.payer = payer
        self.fields["receiver"].queryset = group.members.exclude(id=payer.id).order_by("username")
        self.fields["receiver"].widget.attrs.update({"class": "form-select"})
        self.fields["amount"].widget.attrs.update(
            {"class": "form-control", "placeholder": "0.00", "min": "0.01", "step": "0.01"}
        )
        self.fields["date"].widget.attrs.update({"class": "form-control"})

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None or amount <= Decimal("0.00"):
            raise forms.ValidationError("Settlement amount must be greater than 0.")
        return amount

    def save(self, commit=True):
        obj: Settlement = super().save(commit=False)
        obj.group = self.group
        obj.payer = self.payer
        if commit:
            obj.save()
        return obj


class SplitLineForm(forms.Form):
    user_id = forms.IntegerField(widget=forms.HiddenInput)
    exact_amount = forms.DecimalField(max_digits=10, decimal_places=2, required=False)
    percent = forms.DecimalField(max_digits=5, decimal_places=2, required=False)


def build_splits_for_expense(*, expense: Expense, members, split_type: str, posted_data: dict) -> list[Split]:
    """
    Create Split objects (not saved) according to split_type.
    posted_data expected keys for EXACT: split_exact_<user_id>
                         keys for PERCENT: split_percent_<user_id>
    """
    members = list(members)
    if not members:
        raise forms.ValidationError("Group must have at least one member.")

    amount: Decimal = expense.amount

    if split_type == Expense.SplitType.EQUAL:
        per = (amount / len(members)).quantize(Decimal("0.01"))
        # Fix rounding difference by adjusting payer's share.
        splits = [Split(expense=expense, user=m, amount=per) for m in members]
        total = sum((s.amount for s in splits), Decimal("0.00"))
        diff = (amount - total).quantize(Decimal("0.01"))
        if diff != Decimal("0.00"):
            # Put the rounding cent(s) on payer if possible; else first member.
            target = next((s for s in splits if s.user_id == expense.payer_id), splits[0])
            target.amount = (target.amount + diff).quantize(Decimal("0.01"))
        return splits

    if split_type == Expense.SplitType.EXACT:
        splits: list[Split] = []
        total = Decimal("0.00")
        for m in members:
            key = f"split_exact_{m.id}"
            raw = (posted_data.get(key) or "").strip()
            if not raw:
                raise forms.ValidationError("Please provide an exact amount for every member.")
            try:
                amt = Decimal(raw).quantize(Decimal("0.01"))
            except Exception as exc:
                raise forms.ValidationError("Invalid exact split amount.") from exc
            if amt < 0:
                raise forms.ValidationError("Exact split amounts must be >= 0.")
            splits.append(Split(expense=expense, user=m, amount=amt))
            total += amt
        if total.quantize(Decimal("0.01")) != amount.quantize(Decimal("0.01")):
            raise forms.ValidationError("Exact splits must add up to the expense amount.")
        return splits

    if split_type == Expense.SplitType.PERCENT:
        splits = []
        total_pct = Decimal("0.00")
        for m in members:
            key = f"split_percent_{m.id}"
            raw = (posted_data.get(key) or "").strip()
            if not raw:
                raise forms.ValidationError("Please provide a percent for every member.")
            try:
                pct = Decimal(raw).quantize(Decimal("0.01"))
            except Exception as exc:
                raise forms.ValidationError("Invalid percent split.") from exc
            if pct < 0:
                raise forms.ValidationError("Percent splits must be >= 0.")
            total_pct += pct
            splits.append((m, pct))
        if total_pct.quantize(Decimal("0.01")) != Decimal("100.00"):
            raise forms.ValidationError("Percent splits must add up to 100%.")

        split_objs: list[Split] = []
        total_amt = Decimal("0.00")
        for (m, pct) in splits:
            amt = (amount * pct / Decimal("100.00")).quantize(Decimal("0.01"))
            split_objs.append(Split(expense=expense, user=m, amount=amt, percent=pct))
            total_amt += amt

        diff = (amount - total_amt).quantize(Decimal("0.01"))
        if diff != Decimal("0.00"):
            target = next((s for s in split_objs if s.user_id == expense.payer_id), split_objs[0])
            target.amount = (target.amount + diff).quantize(Decimal("0.01"))
        return split_objs

    raise forms.ValidationError("Unknown split type.")
