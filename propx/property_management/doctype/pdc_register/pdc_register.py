import frappe
from frappe.model.document import Document
from frappe.utils import today, flt, nowdate


class PDCRegister(Document):

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def validate(self):
        self._fetch_property_from_lease()
        self._check_bounce_history()

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _fetch_property_from_lease(self):
        """Auto-fill property and unit from the linked Lease."""
        if not self.lease:
            return
        lease = frappe.db.get_value(
            "Lease", self.lease,
            ["property", "unit"],
            as_dict=True
        )
        if not lease:
            return
        if not self.property and lease.property:
            self.property = lease.property
        if not self.unit and lease.unit:
            self.unit = lease.unit

    def _check_bounce_history(self):
        """Count prior bounced PDCs for this tenant and update read-only field."""
        if not self.tenant:
            return
        count = frappe.db.count(
            "PDC Register",
            {
                "tenant": self.tenant,
                "status": "Bounced",
                "name": ["!=", self.name or ""],
            }
        )
        self.previous_bounces = count

    # ------------------------------------------------------------------
    # Whitelisted actions (called from JS buttons / API)
    # ------------------------------------------------------------------

    @frappe.whitelist()
    def deposit(self):
        """Mark this PDC as Deposited."""
        if self.status != "Received":
            frappe.throw(
                f"Cannot deposit a PDC with status '{self.status}'. "
                "Only 'Received' cheques can be deposited."
            )
        frappe.db.set_value("PDC Register", self.name, {
            "status": "Deposited",
            "deposited_date": today(),
        })
        frappe.msgprint(f"PDC {self.name} marked as Deposited.", alert=True)

    @frappe.whitelist()
    def clear(self):
        """Mark this PDC as Cleared and create a Payment Entry."""
        if self.status not in ("Received", "Deposited"):
            frappe.throw(
                f"Cannot clear a PDC with status '{self.status}'. "
                "Only 'Received' or 'Deposited' cheques can be cleared."
            )
        pe_name = self._create_payment_entry()
        frappe.db.set_value("PDC Register", self.name, {
            "status": "Cleared",
            "cleared_date": today(),
            "payment_entry": pe_name,
        })
        frappe.msgprint(
            f"PDC {self.name} cleared. Payment Entry {pe_name} created.",
            alert=True
        )
        return pe_name

    @frappe.whitelist()
    def bounce(self, reason=None):
        """Mark this PDC as Bounced, raise penalty invoice, notify stakeholders."""
        if self.status not in ("Received", "Deposited"):
            frappe.throw(
                f"Cannot bounce a PDC with status '{self.status}'."
            )
        update = {
            "status": "Bounced",
            "bounce_date": today(),
        }
        if reason:
            update["bounce_reason"] = reason

        frappe.db.set_value("PDC Register", self.name, update)

        # Increment previous_bounces on other PDCs for this tenant
        self._increment_tenant_bounce_count()

        # Create bounce penalty invoice (if lease has penalty configured)
        penalty_inv = self._create_bounce_penalty_invoice()

        # Realtime notification to Property Manager
        self._notify_bounce(penalty_inv)

        frappe.msgprint(
            f"PDC {self.name} marked as Bounced." +
            (f" Penalty invoice {penalty_inv} raised." if penalty_inv else ""),
            alert=True
        )
        return penalty_inv

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_payment_entry(self):
        """
        Create a Payment Entry that settles the linked Sales Invoice.

        For a 'Receive' payment:
          paid_from = customer AR account (debit side cleared)
          paid_to   = bank GL account (credit side — where cash lands)
        """
        # Resolve company from lease
        company = frappe.db.get_value("Lease", self.lease, "company") if self.lease else None
        if not company:
            frappe.throw("Cannot create Payment Entry: Lease has no Company set.")

        # paid_from: customer receivable (AR) account
        paid_from = frappe.db.get_value("Company", company, "default_receivable_account")

        # paid_to: bank GL account — prefer deposit batch's bank account, else company default
        paid_to = None
        if self.deposit_batch:
            bank_account_name = frappe.db.get_value(
                "PDC Deposit Batch", self.deposit_batch, "bank_account"
            )
            if bank_account_name:
                paid_to = frappe.db.get_value("Bank Account", bank_account_name, "account")
        if not paid_to:
            paid_to = frappe.db.get_value("Company", company, "default_bank_account")
        if not paid_to:
            frappe.throw(
                "Cannot create Payment Entry: no bank account configured. "
                "Set a bank account on the PDC Deposit Batch or the Company default."
            )

        pe = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "posting_date": today(),
            "company": company,
            "party_type": "Customer",
            "party": self.tenant,
            "paid_amount": flt(self.amount),
            "received_amount": flt(self.amount),
            "source_exchange_rate": 1,
            "target_exchange_rate": 1,
            "paid_from": paid_from,
            "paid_to": paid_to,
            "paid_to_account_currency": self.currency or "AED",
            "reference_no": self.cheque_number,
            "reference_date": self.cheque_date,
            "remarks": f"PDC clearance – {self.name}" + (
                f"\nInvoice: {self.against_invoice}" if self.against_invoice else ""
            ),
        })

        # Link to invoice if present
        if self.against_invoice:
            outstanding = flt(
                frappe.db.get_value(
                    "Sales Invoice", self.against_invoice, "outstanding_amount"
                )
            )
            if outstanding > 0:
                pe.append("references", {
                    "reference_doctype": "Sales Invoice",
                    "reference_name": self.against_invoice,
                    "allocated_amount": min(flt(self.amount), outstanding),
                })

        pe.insert(ignore_permissions=True)
        pe.submit()
        return pe.name

    def _increment_tenant_bounce_count(self):
        """Update previous_bounces on all other PDCs for this tenant."""
        if not self.tenant:
            return
        frappe.db.sql(
            """
            UPDATE `tabPDC Register`
               SET previous_bounces = (
                   SELECT COUNT(*) FROM (
                       SELECT name FROM `tabPDC Register`
                        WHERE tenant = %(tenant)s
                          AND status = 'Bounced'
                   ) AS sub
               )
             WHERE tenant = %(tenant)s
               AND name != %(name)s
            """,
            {"tenant": self.tenant, "name": self.name}
        )

    def _create_bounce_penalty_invoice(self):
        """
        Create a Sales Invoice for the bounce penalty charge if the lease
        has a bounce_penalty_amount > 0.
        """
        if not self.lease:
            return None

        penalty_amount = flt(
            frappe.db.get_value("Lease", self.lease, "bounce_penalty_amount")
        )
        if penalty_amount <= 0:
            return None

        company = frappe.db.get_value("Lease", self.lease, "company")
        income_account = frappe.db.get_value(
            "Company", company, "default_income_account"
        )

        inv = frappe.get_doc({
            "doctype": "Sales Invoice",
            "customer": self.tenant,
            "company": company,
            "posting_date": today(),
            "due_date": today(),
            "remarks": f"Bounce penalty for PDC {self.name} (Cheque {self.cheque_number})",
            "items": [{
                "item_name": "PDC Bounce Penalty",
                "description": (
                    f"Bounce penalty – cheque {self.cheque_number} "
                    f"dated {self.cheque_date}"
                ),
                "qty": 1,
                "rate": penalty_amount,
                "income_account": income_account,
            }],
        })
        inv.insert(ignore_permissions=True)
        inv.submit()

        # Store JE reference on this PDC for traceability
        frappe.db.set_value(
            "PDC Register", self.name, "journal_entry_bounce", inv.name
        )
        return inv.name

    def _notify_bounce(self, penalty_invoice=None):
        """Send a realtime notification to the Property Manager role."""
        message = (
            f"PDC Bounced: {self.name} | "
            f"Cheque {self.cheque_number} | "
            f"Tenant: {self.tenant} | "
            f"Amount: {self.currency} {flt(self.amount):,.2f}"
        )
        if penalty_invoice:
            message += f" | Penalty Invoice: {penalty_invoice}"

        frappe.publish_realtime(
            event="pdc_bounce_alert",
            message={"message": message, "pdc": self.name},
            user=None,  # broadcast to all users with the role
        )

        # Also create a Frappe Notification
        try:
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": f"PDC Bounce – {self.cheque_number}",
                "email_content": message,
                "type": "Alert",
                "document_type": "PDC Register",
                "document_name": self.name,
                "for_user": frappe.db.get_value(
                    "User",
                    {"role_profile_name": "Property Manager"},
                    "name"
                ) or "Administrator",
            }).insert(ignore_permissions=True)
        except Exception:
            # Non-fatal — notification failure should not block the bounce
            pass
