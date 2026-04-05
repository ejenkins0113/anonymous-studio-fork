#!/usr/bin/env python
"""
Anonymous Studio — Demo Seed Script
=====================================
Pre-loads a compelling, realistic demo state into the configured store backend.
Run this before a live demo to skip manual data entry.

Usage:
    python scripts/demo_seed.py                  # seeds Memory store (preview only)
    ANON_STORE_BACKEND=duckdb python scripts/demo_seed.py
    ANON_STORE_BACKEND=mongo MONGODB_URI=... python scripts/demo_seed.py
    python scripts/demo_seed.py --dry-run        # print what would be created
    python scripts/demo_seed.py --count 50       # generate N sessions (default 30)

The script is idempotent for DuckDB/Mongo (checks for existing data by title).
For MemoryStore it always seeds (state resets on restart anyway).
"""
from __future__ import annotations

import argparse
import random
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from faker import Faker
from store import get_store
from store.models import PIISession, PipelineCard, Appointment, _now
from pii_engine import get_engine

fake = Faker()
random.seed(42)
Faker.seed(42)

# ── Helpers ───────────────────────────────────────────────────────────────────

OPERATORS = ["replace", "redact", "mask", "hash"]
STATUSES = ["backlog", "in_progress", "review", "done"]
PRIORITIES = ["low", "medium", "high", "critical"]
LABEL_POOL = ["HIPAA", "GDPR", "PCI-DSS", "CCPA", "SOC2", "HR", "healthcare",
              "customer-data", "research", "contracts", "finance", "legal"]
APPT_STATUSES = ["scheduled", "completed", "cancelled"]
SEVERITIES = ["info", "warning", "critical"]
ACTORS = ["admin", "compliance-bot", "Carley Fant", "Sakshi Patel",
          "Diamond Hogans", "Elijah Jenkins", "system"]

PII_TEMPLATES = [
    lambda: (
        f"Contact {fake.name()} at {fake.email()} or {fake.phone_number()}. "
        f"SSN: {fake.ssn()}. Credit card: {fake.credit_card_number(card_type='visa')}."
    ),
    lambda: (
        f"Employee {fake.name()} ({fake.email()}) submitted on {fake.date()}. "
        f"Card ending {fake.credit_card_number()[-4:]}. IP: {fake.ipv4()}."
    ),
    lambda: (
        f"Patient {fake.name()}, DOB {fake.date_of_birth(minimum_age=18, maximum_age=80)}. "
        f"Emergency contact: {fake.phone_number()}. Address: {fake.address().replace(chr(10), ', ')}."
    ),
    lambda: (
        f"Vendor {fake.company()} rep {fake.name()} — {fake.email()}, "
        f"account {fake.bban()}. Contract signed {fake.date()}."
    ),
    lambda: (
        f"Research participant {fake.name()}, email {fake.email()}, "
        f"DOB {fake.date_of_birth()}. IP: {fake.ipv4_private()}. "
        f"Phone: {fake.phone_number()}."
    ),
    lambda: (
        f"Invoice for {fake.name()} ({fake.email()}). "
        f"Billing SSN {fake.ssn()}, card {fake.credit_card_number()}. "
        f"Due {fake.future_date()}."
    ),
]

CARD_TEMPLATES = [
    ("Customer Export Anonymization", "De-identify customer names, emails, SSNs from export batch."),
    ("HR Records PII Scrub", "Remove all PII from historical HR records prior to archival."),
    ("Research Dataset Anonymization", "Apply de-identification to participant data per IRB protocol."),
    ("Patient Records HIPAA Compliance", "Scrub PHI from inbound patient dataset before ML pipeline."),
    ("Vendor Contract Data Review", "Flag and remove bank account numbers and SSNs from vendor contracts."),
    ("Financial Audit PII Removal", "Redact personal identifiers from Q-end financial audit logs."),
    ("Marketing List Compliance", "Strip emails and phone numbers from legacy marketing exports."),
    ("Insurance Claims Scrub", "Anonymize claimant PII before data warehouse ingestion."),
    ("Legal Discovery Redaction", "Mask personal data in litigation discovery documents."),
    ("Payroll Data Anonymization", "Remove SSNs and account numbers from payroll archive."),
    ("Clinical Trial De-identification", "IRB-compliant de-id of trial participant records."),
    ("Support Ticket PII Cleanup", "Redact PII from customer support tickets before analytics."),
    ("GDPR Subject Access Response", "Prepare anonymized dataset export for GDPR SAR."),
    ("Employee Benefits Data Scrub", "Remove health plan PII before third-party transfer."),
    ("Breach Notification Prep", "Identify and document PII in affected records for notification."),
]

APPT_TEMPLATES = [
    ("Compliance Review", "Review de-identified dataset with the compliance team.", 60),
    ("IRB Attestation Session", "Post-anonymization IRB attestation.", 45),
    ("HIPAA Sign-off Meeting", "Final HIPAA compliance sign-off.", 30),
    ("Data Governance Check-in", "Quarterly data governance review.", 60),
    ("PII Audit Walkthrough", "Walk through audit log with security officer.", 90),
    ("GDPR Readiness Review", "Validate GDPR controls on anonymized exports.", 45),
    ("Legal Discovery Sign-off", "Attorney review of redacted discovery documents.", 60),
    ("HR Records Attestation", "Final attestation for HR archive anonymization.", 30),
    ("Vendor Data Review", "Review anonymized vendor contract data.", 45),
    ("Breach Response Debrief", "Post-incident review of PII handling procedures.", 90),
    ("Clinical Trial IRB Check", "IRB check on trial participant de-identification.", 60),
    ("Finance Audit Close-out", "Close out finance PII scrub with internal audit team.", 45),
]


def _ts_offset(days: int) -> str:
    """ISO-8601 timestamp offset by `days` from today."""
    dt = datetime.now() + timedelta(days=days)
    return dt.isoformat(timespec="seconds")


# ── Seed Logic ────────────────────────────────────────────────────────────────

def _existing_titles(store, kind: str) -> set:
    if kind == "cards":
        return {c.title for c in store.list_cards()}
    if kind == "appts":
        return {a.title for a in store.list_appointments()}
    return set()


def seed(dry_run: bool = False, count: int = 30) -> None:
    store = get_store()
    engine = get_engine()

    existing_cards = _existing_titles(store, "cards")
    existing_appts = _existing_titles(store, "appts")

    print("━" * 60)
    print("  Anonymous Studio — Demo Seed")
    print("━" * 60)
    if dry_run:
        print("  DRY RUN — no data will be written\n")

    # ── PII Sessions ──────────────────────────────────────────────────────────
    print(f"\n[1/3] PII Sessions  (generating {count})")
    sessions_created = []
    entities_list = ["EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN",
                     "CREDIT_CARD", "PERSON", "IP_ADDRESS", "DATE_TIME"]

    for i in range(count):
        operator = random.choice(OPERATORS)
        text = random.choice(PII_TEMPLATES)()
        title = f"{fake.bs().title()} — {fake.date()}"
        print(f"  • [{i+1}/{count}] {title[:45]!r}...", end=" ", flush=True)
        try:
            result = engine.anonymize(text, operator=operator, entities=entities_list)
            session = PIISession(
                title=title,
                original_text=result.original_text,
                anonymized_text=result.anonymized_text,
                entities=result.entities,
                entity_counts=result.entity_counts,
                operator=result.operator_used,
                source_type=random.choice(["text", "file"]),
                file_name=fake.file_name(extension="csv") if random.random() > 0.5 else None,
                processing_ms=round(random.uniform(12.0, 850.0), 1),
            )
            if not dry_run:
                store.add_session(session)
            sessions_created.append(session)
            summary = ", ".join(f"{k}×{v}" for k, v in result.entity_counts.items()) or "0 entities"
            print(f"✓  ({summary})")
        except Exception as exc:
            print(f"✗  {exc}")

    # ── Pipeline Cards ────────────────────────────────────────────────────────
    n_cards = min(len(CARD_TEMPLATES), max(15, count // 2))
    print(f"\n[2/3] Pipeline Cards  (generating {n_cards})")
    cards_created = []
    session_ids = [s.id for s in sessions_created]

    for i, (base_title, base_desc) in enumerate(CARD_TEMPLATES[:n_cards]):
        title = f"{base_title} — {fake.date()}"
        if title in existing_cards:
            print(f"  • {title!r} — already exists, skipping")
            continue
        status = random.choice(STATUSES)
        attested = status == "done" and random.random() > 0.4
        assignee = random.choice(ACTORS[2:])  # skip system actors
        labels = random.sample(LABEL_POOL, k=random.randint(1, 3))
        session_id = session_ids[i] if i < len(session_ids) else None

        print(f"  • Creating: {title[:45]!r}...", end=" ", flush=True)
        try:
            card = PipelineCard(
                title=title,
                description=base_desc,
                status=status,
                assignee=assignee,
                priority=random.choice(PRIORITIES),
                labels=labels,
                session_id=session_id,
                attested=attested,
                attested_by="Compliance Officer" if attested else "",
                attestation="Verified: all PII removed per protocol." if attested else "",
                attested_at=_ts_offset(-random.randint(1, 30)) if attested else None,
                done_at=_ts_offset(-random.randint(1, 14)) if status == "done" else None,
            )
            if not dry_run:
                store.add_card(card)
                if attested:
                    store.update_card(
                        card.id,
                        attested=True,
                        attested_by=card.attested_by,
                        attestation=card.attestation,
                    )
            cards_created.append(card)
            attest_note = " [attested]" if attested else ""
            print(f"✓  ({status}{attest_note})")
        except Exception as exc:
            print(f"✗  {exc}")

    card_ids = [c.id for c in cards_created]

    # ── Appointments ──────────────────────────────────────────────────────────
    n_appts = min(len(APPT_TEMPLATES), max(10, count // 3))
    print(f"\n[3/3] Appointments  (generating {n_appts})")

    for i, (base_title, desc, duration) in enumerate(APPT_TEMPLATES[:n_appts]):
        title = f"{base_title} — {fake.date_this_year()}"
        if title in existing_appts:
            print(f"  • {title!r} — already exists, skipping")
            continue
        appt_status = random.choice(APPT_STATUSES)
        day_offset = random.randint(-30, 60)
        scheduled = _ts_offset(day_offset)
        attendees = [random.choice(ACTORS[2:]) for _ in range(random.randint(2, 4))]

        print(f"  • Creating: {title[:45]!r}...", end=" ", flush=True)
        try:
            appt = Appointment(
                title=title,
                description=desc,
                scheduled_for=scheduled,
                duration_mins=duration,
                attendees=list(set(attendees)),
                status=appt_status,
                pipeline_card_id=card_ids[i] if i < len(card_ids) else None,
            )
            if not dry_run:
                store.add_appointment(appt)
            print(f"✓  ({scheduled[:10]}, {appt_status})")
        except Exception as exc:
            print(f"✗  {exc}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "━" * 60)
    if not dry_run:
        stats = store.stats()
        print(f"  Store now contains:")
        print(f"    Sessions      : {stats['total_sessions']}")
        print(f"    Cards         : {sum(stats['pipeline_by_status'].values())}")
        print(f"    Appointments  : {stats['total_appointments']}")
        print(f"    Audit entries : {stats['total_audit_entries']}")
        print(f"    Entities redacted: {stats['total_entities_redacted']}")
    else:
        print(f"  Would create: {count} sessions, {n_cards} cards, {n_appts} appointments")
    print("━" * 60)
    print("  Done. Start the app with: .venv/bin/taipy run main.py")
    print("━" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data into Anonymous Studio")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be seeded without writing anything")
    parser.add_argument("--count", type=int, default=30,
                        help="Number of PII sessions to generate (default: 30)")
    args = parser.parse_args()
    seed(dry_run=args.dry_run, count=args.count)
