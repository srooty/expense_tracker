from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from tracker.models import Category, Expense, Group, Settlement, Split


class Command(BaseCommand):
    help = "Seed realistic demo users, groups, expenses, splits, and settlements."

    default_password = "demo1234"
    category_names = ["Food", "Travel", "Bills", "Shopping", "Entertainment"]
    user_specs = [
        ("ananya", "Ananya"),
        ("ravi", "Ravi"),
        ("meera", "Meera"),
        ("arjun", "Arjun"),
        ("isha", "Isha"),
        ("kabir", "Kabir"),
    ]
    group_specs = {
        "Weekend Trip": ["ananya", "ravi", "meera", "arjun"],
        "Flatmates": ["ananya", "isha", "kabir"],
        "Office Lunch Club": ["ravi", "meera", "arjun", "isha", "kabir"],
    }
    descriptions = {
        "Food": [
            "Team dinner",
            "Cafe brunch",
            "Pizza night",
            "Groceries run",
            "Bakery order",
        ],
        "Travel": [
            "Airport cab",
            "Fuel refill",
            "Train tickets",
            "Weekend bus ride",
            "Parking fees",
        ],
        "Bills": [
            "Electricity bill",
            "Internet recharge",
            "Water bill",
            "Gas cylinder",
            "Maintenance dues",
        ],
        "Shopping": [
            "Household supplies",
            "Pharmacy pickup",
            "Decor items",
            "Stationery restock",
            "Essentials order",
        ],
        "Entertainment": [
            "Movie tickets",
            "Streaming subscription",
            "Game night snacks",
            "Concert booking",
            "Bowling evening",
        ],
    }

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(20260420)
        today = timezone.localdate()

        categories = {}
        for name in self.category_names:
            categories[name], _ = Category.objects.get_or_create(name=name)

        users = {}
        for username, first_name in self.user_specs:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first_name},
            )
            if created or not user.has_usable_password():
                user.set_password(self.default_password)
                user.first_name = first_name
                user.save()
            users[username] = user

        groups = {}
        for group_name, usernames in self.group_specs.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            group.members.set([users[username] for username in usernames])
            groups[group_name] = group

        Expense.objects.filter(group__in=groups.values()).delete()
        Settlement.objects.filter(group__in=groups.values()).delete()

        expense_count = rng.randint(140, 180)
        expenses_created = 0
        settlements_created = 0

        for _ in range(expense_count):
            group = rng.choice(list(groups.values()))
            members = list(group.members.all())
            payer = rng.choice(members)
            category_name = rng.choice(self.category_names)
            category = categories[category_name]
            description = rng.choice(self.descriptions[category_name])
            amount = Decimal(str(rng.randrange(100, 2001))).quantize(Decimal("0.01"))
            expense_date = today - timedelta(days=rng.randint(0, 179))

            expense = Expense.objects.create(
                group=group,
                description=description,
                amount=amount,
                payer=payer,
                date=expense_date,
                category=category,
                split_type=Expense.SplitType.EQUAL,
            )

            per_head = (amount / len(members)).quantize(Decimal("0.01"))
            splits = [Split(expense=expense, user=member, amount=per_head) for member in members]
            rounded_total = sum((split.amount for split in splits), Decimal("0.00"))
            diff = (amount - rounded_total).quantize(Decimal("0.01"))
            if diff != Decimal("0.00"):
                payer_split = next((split for split in splits if split.user_id == payer.id), splits[0])
                payer_split.amount = (payer_split.amount + diff).quantize(Decimal("0.01"))
            Split.objects.bulk_create(splits)
            expenses_created += 1

        for group in groups.values():
            members = list(group.members.all())
            for _ in range(rng.randint(3, 6)):
                payer = rng.choice(members)
                receiver_choices = [member for member in members if member.id != payer.id]
                receiver = rng.choice(receiver_choices)
                Settlement.objects.create(
                    group=group,
                    payer=payer,
                    receiver=receiver,
                    amount=Decimal(str(rng.randrange(150, 901))).quantize(Decimal("0.01")),
                    date=today - timedelta(days=rng.randint(0, 120)),
                )
                settlements_created += 1

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
        self.stdout.write(f"Users created/updated: {len(users)}")
        self.stdout.write(f"Groups created/updated: {len(groups)}")
        self.stdout.write(f"Expenses created: {expenses_created}")
        self.stdout.write(f"Settlements created: {settlements_created}")
        self.stdout.write(f"Default password for demo users: {self.default_password}")
        self.stdout.write("Demo usernames: " + ", ".join(sorted(users.keys())))
