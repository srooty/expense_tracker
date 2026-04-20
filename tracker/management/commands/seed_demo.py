from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from tracker.models import Expense, Group, Split


class Command(BaseCommand):
    help = "Seed demo users, a group, and sample expenses."

    @transaction.atomic
    def handle(self, *args, **options):
        alice, alice_created = User.objects.get_or_create(username="alice")
        if alice_created or not alice.has_usable_password():
            alice.set_password("pass1234")
            alice.save()

        bob, bob_created = User.objects.get_or_create(username="bob")
        if bob_created or not bob.has_usable_password():
            bob.set_password("pass1234")
            bob.save()

        group, _ = Group.objects.get_or_create(name="Trip")
        group.members.add(alice, bob)

        created = 0

        def add_expense(description: str, amount: Decimal, payer: User):
            nonlocal created
            expense = Expense.objects.create(
                group=group,
                description=description,
                amount=float(amount),
                payer=payer,
            )
            members = list(group.members.all())
            split_amount = float((amount / len(members)).quantize(Decimal("0.01")))
            for m in members:
                Split.objects.create(expense=expense, user=m, amount=split_amount)
            created += 1

        # Only seed sample expenses if the group has none yet
        if not Expense.objects.filter(group=group).exists():
            add_expense("Hotel", Decimal("1200.00"), payer=alice)
            add_expense("Dinner", Decimal("600.00"), payer=bob)
            add_expense("Taxi", Decimal("300.00"), payer=alice)

        self.stdout.write(self.style.SUCCESS("Seed complete."))
        self.stdout.write("Login credentials:")
        self.stdout.write("  alice / pass1234")
        self.stdout.write("  bob   / pass1234")
        self.stdout.write("Group created/updated:")
        self.stdout.write("  Trip (alice, bob)")
        self.stdout.write(f"Sample expenses created this run: {created}")

