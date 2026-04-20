from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase

from tracker.models import Category, Expense, Group, Settlement, Split
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


class SignupTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_user("alice", password="pass1234")

    def test_duplicate_username_shows_message_instead_of_crashing(self):
        response = self.client.post(
            "/signup/",
            {"username": "alice", "password": "pass1234"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Username already exists")
        self.assertEqual(User.objects.filter(username="alice").count(), 1)


class DashboardTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.alice = User.objects.create_user("alice", password="pass1234")
        self.bob = User.objects.create_user("bob", password="pass1234")
        self.group = Group.objects.create(name="Trip")
        self.group.members.add(self.alice, self.bob)
        self.client.login(username="alice", password="pass1234")

    def test_empty_dashboard_uses_safe_chart_defaults(self):
        response = self.client.get(f"/groups/{self.group.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "window.dashboardChartData")
        self.assertContains(response, "labels: []", html=False)
        self.assertContains(response, "No expenses yet")

    def test_dashboard_populates_chart_data(self):
        category = Category.objects.create(name="Food")
        expense = Expense.objects.create(
            group=self.group,
            description="Dinner",
            amount=Decimal("450.00"),
            payer=self.alice,
            category=category,
        )
        Split.objects.create(expense=expense, user=self.alice, amount=Decimal("225.00"))
        Split.objects.create(expense=expense, user=self.bob, amount=Decimal("225.00"))

        response = self.client.get(f"/groups/{self.group.id}/")

        self.assertContains(response, "categoryPieChart")
        self.assertContains(response, '"Food"', html=False)
        self.assertContains(response, "450.0", html=False)

    def test_expense_edit_prefills_existing_split_values(self):
        category = Category.objects.create(name="Travel")
        expense = Expense.objects.create(
            group=self.group,
            description="Cab fare",
            amount=Decimal("300.00"),
            payer=self.alice,
            category=category,
            split_type="EXACT",
        )
        Split.objects.create(expense=expense, user=self.alice, amount=Decimal("120.00"))
        Split.objects.create(expense=expense, user=self.bob, amount=Decimal("180.00"))

        response = self.client.get(f"/groups/{self.group.id}/expenses/{expense.id}/edit/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="split_exact_{}'.format(self.alice.id), html=False)
        self.assertContains(response, 'value="120.00"', html=False)
        self.assertContains(response, 'value="180.00"', html=False)


class SeedDemoCommandTests(TestCase):
    def test_seed_demo_populates_realistic_data(self):
        call_command("seed_demo")

        self.assertGreaterEqual(User.objects.count(), 6)
        self.assertGreaterEqual(Group.objects.count(), 3)
        self.assertGreaterEqual(Expense.objects.count(), 100)
        self.assertGreaterEqual(Split.objects.count(), Expense.objects.count() * 3)
        self.assertGreaterEqual(Category.objects.count(), 5)
