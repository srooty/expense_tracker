from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase

from tracker.models import Expense, Group, Settlement, Split
from tracker.services.balances import compute_net_balances


class AuthzTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pass1234")
        self.bob = User.objects.create_user("bob", password="pass1234")
        self.eve = User.objects.create_user("eve", password="pass1234")
        self.group = Group.objects.create(name="Trip")
        self.group.members.add(self.alice, self.bob)

    def test_non_member_cannot_access_group_dashboard(self):
        c = Client()
        c.login(username="eve", password="pass1234")
        resp = c.get(f"/groups/{self.group.id}/")
        self.assertEqual(resp.status_code, 404)


class BalanceTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pass1234")
        self.bob = User.objects.create_user("bob", password="pass1234")
        self.group = Group.objects.create(name="Trip")
        self.group.members.add(self.alice, self.bob)

    def test_equal_split_balance(self):
        ex = Expense.objects.create(group=self.group, description="Dinner", amount=Decimal("100.00"), payer=self.alice)
        Split.objects.create(expense=ex, user=self.alice, amount=Decimal("50.00"))
        Split.objects.create(expense=ex, user=self.bob, amount=Decimal("50.00"))
        net = compute_net_balances(group=self.group)
        self.assertEqual(net[self.alice], Decimal("50.00"))
        self.assertEqual(net[self.bob], Decimal("-50.00"))

    def test_settlement_adjusts_balance(self):
        ex = Expense.objects.create(group=self.group, description="Dinner", amount=Decimal("100.00"), payer=self.alice)
        Split.objects.create(expense=ex, user=self.alice, amount=Decimal("50.00"))
        Split.objects.create(expense=ex, user=self.bob, amount=Decimal("50.00"))
        Settlement.objects.create(group=self.group, payer=self.bob, receiver=self.alice, amount=Decimal("20.00"))
        net = compute_net_balances(group=self.group)
        self.assertEqual(net[self.alice], Decimal("30.00"))
        self.assertEqual(net[self.bob], Decimal("-30.00"))
