import os
import unittest
from datetime import date
from types import SimpleNamespace

os.environ["SMARTBIZ_DATABASE_URL"] = "sqlite://"
os.environ["SMARTBIZ_JWT_SECRET"] = "test-only-secret-that-is-long-enough"

from fastapi import HTTPException

from backend import main, models
from backend.database import Base, SessionLocal, engine


class RecordRemovalTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def add_customer(self, customer_id="CUST-TEST"):
        customer = models.DBCustomer(
            id=customer_id,
            name="Test Customer",
            email=f"{customer_id.lower()}@example.test",
            phone="555-0100",
            tier="Standard",
            spend=0,
        )
        self.db.add(customer)
        self.db.commit()
        return customer

    def add_invoice(self, invoice_id, customer_id, invoice_status):
        invoice = models.DBInvoice(
            id=invoice_id,
            customer_id=customer_id,
            customer_name="Test Customer",
            date="2026-01-01",
            amount=125.0,
            status=invoice_status,
            item="Test item",
            qty=1,
            unit_price=125.0,
        )
        self.db.add(invoice)
        self.db.commit()
        return invoice

    def test_customer_audit_log_records_create_update_delete_and_actor(self):
        actor = SimpleNamespace(username="admin")
        customer = main.create_customer(
            main.CustomerCreate(
                name="Audit Customer",
                email="audit@example.test",
                phone="555-0123",
                tier="Standard",
            ),
            self.db,
            current_user=actor,
        )
        main.update_customer(
            customer.id,
            main.CustomerCreate(
                name="Updated Audit Customer",
                email="audit@example.test",
                phone="555-0123",
                tier="Growth",
            ),
            self.db,
            current_user=actor,
        )

        updated_logs = main.get_customer_audit_log(customer.id, self.db)

        self.assertEqual([entry["action"] for entry in updated_logs], ["updated", "created"])
        self.assertEqual(updated_logs[0]["changed_fields"], ["name", "tier"])
        self.assertEqual(updated_logs[0]["actor"], "admin")
        self.assertNotIn("audit@example.test", str(updated_logs))

        main.delete_customer(customer.id, self.db, current_user=actor)
        deleted_logs = main.get_customer_audit_log(customer.id, self.db)

        self.assertEqual(deleted_logs[0]["action"], "deleted")
        self.assertEqual(deleted_logs[0]["actor"], "admin")

    def test_customer_with_invoice_history_cannot_be_deleted(self):
        customer = self.add_customer()
        self.add_invoice("INV-TEST", customer.id, "VOID")

        with self.assertRaises(HTTPException) as raised:
            main.delete_customer(
                customer.id,
                self.db,
                current_user=SimpleNamespace(username="admin"),
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIsNotNone(self.db.get(models.DBCustomer, customer.id))

    def test_unreferenced_customer_can_be_deleted(self):
        customer = self.add_customer()

        main.delete_customer(
            customer.id,
            self.db,
            current_user=SimpleNamespace(username="admin"),
        )

        self.assertIsNone(self.db.get(models.DBCustomer, customer.id))

    def test_customer_can_be_edited_without_changing_identity(self):
        customer = self.add_customer()

        updated = main.update_customer(
            customer.id,
            main.CustomerCreate(
                name="Updated Customer",
                email="updated@example.test",
                phone="555-0199",
                tier="Growth",
            ),
            self.db,
            current_user=SimpleNamespace(username="admin"),
        )

        self.assertEqual(updated.id, customer.id)
        self.assertEqual(updated.name, "Updated Customer")
        self.assertEqual(updated.tier, "Growth")

    def test_invoice_voiding_preserves_history_and_blocks_payment(self):
        customer = self.add_customer()
        product = models.DBProduct(
            id="PROD-TEST",
            sku="SKU-TEST",
            name="Test item",
            category="General",
            price=125.0,
            stock=4,
            min_stock=1,
        )
        self.db.add(product)
        self.db.commit()
        self.add_invoice("INV-PENDING", customer.id, "PENDING")

        voided = main.void_invoice("INV-PENDING", self.db)

        self.assertEqual(voided.status, "VOID")
        self.assertEqual(self.db.get(models.DBProduct, product.id).stock, 5)
        main.void_invoice("INV-PENDING", self.db)
        self.assertEqual(self.db.get(models.DBProduct, product.id).stock, 5)
        self.assertEqual(main.get_kpi_metrics(self.db)["receivables"], 0)
        with self.assertRaises(HTTPException) as raised:
            main.mark_invoice_as_paid("INV-PENDING", self.db)
        self.assertEqual(raised.exception.status_code, 409)

    def test_pending_invoice_edit_adjusts_inventory_and_total(self):
        customer = self.add_customer()
        old_product = models.DBProduct(
            id="PROD-OLD",
            sku="SKU-OLD",
            name="Old item",
            category="General",
            price=10.0,
            stock=8,
            min_stock=1,
        )
        new_product = models.DBProduct(
            id="PROD-NEW",
            sku="SKU-NEW",
            name="New item",
            category="General",
            price=20.0,
            stock=5,
            min_stock=1,
        )
        self.db.add_all([old_product, new_product])
        self.db.commit()
        invoice = models.DBInvoice(
            id="INV-EDIT",
            customer_id=customer.id,
            customer_name=customer.name,
            date="2026-01-01",
            amount=21.6,
            status="PENDING",
            item=old_product.name,
            qty=2,
            unit_price=10.0,
        )
        self.db.add(invoice)
        self.db.commit()

        updated = main.update_invoice(
            "INV-EDIT",
            main.InvoiceUpdate(
                customer_id=customer.id,
                product_id=new_product.id,
                issue_date=date(2026, 2, 1),
                quantity=1,
            ),
            self.db,
        )

        self.assertEqual(updated.item, new_product.name)
        self.assertEqual(updated.amount, 21.6)
        self.assertEqual(self.db.get(models.DBProduct, old_product.id).stock, 10)
        self.assertEqual(self.db.get(models.DBProduct, new_product.id).stock, 4)

    def test_product_with_invoice_history_cannot_be_deleted_or_renamed(self):
        customer = self.add_customer()
        product = models.DBProduct(
            id="PROD-USED",
            sku="SKU-USED",
            name="Used item",
            category="General",
            price=10.0,
            stock=1,
            min_stock=1,
        )
        self.db.add(product)
        self.db.commit()
        invoice = models.DBInvoice(
            id="INV-USED",
            customer_id=customer.id,
            customer_name=customer.name,
            date="2026-01-01",
            amount=10.8,
            status="PAID",
            item=product.name,
            qty=1,
            unit_price=10.0,
        )
        self.db.add(invoice)
        self.db.commit()

        with self.assertRaises(HTTPException) as delete_error:
            main.delete_product(product.id, self.db)
        with self.assertRaises(HTTPException) as rename_error:
            main.update_product(
                product.id,
                main.ProductCreate(name="Renamed", category="General", price=10, stock=1, min_stock=1),
                self.db,
            )

        self.assertEqual(delete_error.exception.status_code, 409)
        self.assertEqual(rename_error.exception.status_code, 409)

    def test_archiving_excludes_expense_from_totals_and_restore_reverses_it(self):
        expense = models.DBExpense(
            date="2026-01-01",
            description="Test expense",
            category="Operations",
            amount=125.0,
            vendor="Test vendor",
            anomaly=False,
        )
        self.db.add(expense)
        self.db.commit()
        expense_id = expense.id

        main.archive_expense(expense_id, self.db)

        self.assertEqual(main.get_expenses(self.db), [])
        self.assertEqual([item.id for item in main.get_archived_expenses(self.db)], [expense_id])
        self.assertEqual(main.get_kpi_metrics(self.db)["total_expenses"], 0)

        main.restore_expense(expense_id, self.db)

        self.assertEqual([item.id for item in main.get_expenses(self.db)], [expense_id])
        self.assertEqual(main.get_kpi_metrics(self.db)["total_expenses"], 125.0)

    def test_expense_edit_recalculates_anomaly_flag(self):
        expense = models.DBExpense(
            date="2026-01-01",
            description="Small expense",
            category="Operations",
            amount=10.0,
            vendor="Test vendor",
            anomaly=False,
        )
        self.db.add(expense)
        self.db.commit()

        updated = main.update_expense(
            expense.id,
            main.ExpenseUpdate(
                date=date(2026, 1, 2),
                description="Large expense",
                category="Operations",
                amount=1500.0,
                vendor="Test vendor",
            ),
            self.db,
        )

        self.assertEqual(updated.description, "Large expense")
        self.assertTrue(updated.anomaly)


if __name__ == "__main__":
    unittest.main()
