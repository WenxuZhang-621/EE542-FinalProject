"""
Shared data contracts for the PO follow-up pipeline.

    ingest/   produces  EmailMessage
    extract/  consumes  EmailMessage, produces POExtraction
    dashboard/ consumes POExtraction
    rules.py  consumes  POExtraction, produces POException
    agent/    consumes  POException + emails, produces FollowUpDraft

Locked on Day 1. Changing any field requires agreement from all three module owners.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import json


# --------------------------------------------------------------------------- #
# ingest -> extract
# --------------------------------------------------------------------------- #

@dataclass
class PurchaseOrder:
    """Original order terms; CSV requested_ship_date maps to requested_date."""

    po_number: str
    supplier: str
    supplier_email: str
    item: str
    quantity: float
    unit_price: float
    currency: str
    sent_date: str
    requested_date: str


@dataclass
class Attachment:
    filename: str
    text: str                      # extracted text (pdfplumber / openpyxl); "" if unreadable
    mime_type: str = ""


@dataclass
class EmailMessage:
    email_id: str                  # Gmail message id
    from_addr: str
    subject: str
    date: str                      # ISO 8601, e.g. "2026-11-10"
    body_text: str                 # plain text (HTML already stripped)
    attachments: list[Attachment] = field(default_factory=list)
    thread_id: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "EmailMessage":
        atts = [Attachment(**a) for a in d.get("attachments", [])]
        return cls(**{**d, "attachments": atts})


# --------------------------------------------------------------------------- #
# extract -> dashboard
# --------------------------------------------------------------------------- #

class POStatus(str, Enum):
    PENDING = "pending"            # PO sent, no confirmation yet
    CONFIRMED = "confirmed"        # supplier confirmed date + qty as ordered
    DELAYED = "delayed"            # confirmed_date later than original_date
    PARTIAL = "partial"            # supplier can ship only part of the quantity
    OUT_OF_STOCK = "out_of_stock"  # supplier cannot supply
    PRICE_CHANGE = "price_change"  # supplier changed unit price


class ChangeType(str, Enum):
    NONE = "none"
    DATE_CHANGE = "date_change"
    QUANTITY_CHANGE = "quantity_change"
    PRICE_CHANGE = "price_change"
    CANCELLATION = "cancellation"
    OTHER = "other"


@dataclass
class POExtraction:
    po_number: Optional[str]       # None if the email does not reference a PO
    supplier: str
    status: POStatus
    change_type: ChangeType
    source_email_id: str
    original_date: Optional[str] = None     # ISO 8601
    confirmed_date: Optional[str] = None    # ISO 8601
    quantity_ordered: Optional[float] = None
    quantity_confirmed: Optional[float] = None
    unit_price: Optional[float] = None
    currency: Optional[str] = None
    confidence: float = 0.0        # 0–1, model self-reported
    notes: str = ""                # free-text reason, e.g. "factory holiday"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["change_type"] = self.change_type.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "POExtraction":
        d = dict(d)
        d["status"] = POStatus(d["status"])
        d["change_type"] = ChangeType(d["change_type"])
        return cls(**d)


# --------------------------------------------------------------------------- #
# rules -> dashboard / API
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class POException:
    po_number: str
    kind: str                      # delayed | partial | out_of_stock | price_change | no_reply
    detail: str                    # one line, e.g. "2026-12-01 → 2026-12-15 (+14 days)"
    detected_at: str               # ISO 8601, first time the exception was seen
    source_email_id: Optional[str] = None


# --------------------------------------------------------------------------- #
# agent -> API / Gmail drafts (added for M3)
# --------------------------------------------------------------------------- #

@dataclass
class FollowUpDraft:
    """A follow-up email written by the digital clone, waiting for the buyer's approval.

    agent/ fills the content; the API stores it and moves `state`; ingest/gmail_drafts.py
    saves an approved draft to Gmail (never sends) and fills `gmail_draft_id`.
    """

    draft_id: str
    po_number: str
    to: str                        # supplier email address
    subject: str
    body: str
    why: str                       # one or two sentences: which situation and which rule
    rule_ids: list[str] = field(default_factory=list)    # playbook rules cited, e.g. ["3", "7"]
    email_ids: list[str] = field(default_factory=list)   # emails cited
    language: str = "en"           # "en" | "zh", follows the supplier's latest email
    reply_to_email_id: Optional[str] = None   # the Gmail draft goes into this email's thread
    thread_id: Optional[str] = None
    created_at: str = ""           # ISO 8601
    state: str = "review"          # review | saved | rejected
    gmail_draft_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FollowUpDraft":
        return cls(**d)


# JSON schema handed to the LLM for structured output (extract/ uses this).
PO_EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "po_number": {"type": ["string", "null"]},
        "supplier": {"type": "string"},
        "status": {"type": "string", "enum": [s.value for s in POStatus]},
        "change_type": {"type": "string", "enum": [c.value for c in ChangeType]},
        "original_date": {"type": ["string", "null"], "description": "ISO 8601 date"},
        "confirmed_date": {"type": ["string", "null"], "description": "ISO 8601 date"},
        "quantity_ordered": {"type": ["number", "null"]},
        "quantity_confirmed": {"type": ["number", "null"]},
        "unit_price": {"type": ["number", "null"]},
        "currency": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "notes": {"type": "string"},
    },
    "required": ["po_number", "supplier", "status", "change_type", "confidence", "notes"],
    "additionalProperties": False,
}
