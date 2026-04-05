"""Synthetic text helpers for Presidio-style "synthesize" de-identification."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

from faker import Faker


_PLACEHOLDER_RE = re.compile(r"<([A-Z_]+)>")
_FAKER = Faker()


@dataclass
class SyntheticConfig:
    provider: str = "faker"  # faker | openai | azure_openai
    model: str = "gpt-4o-mini"
    api_key: str = ""
    api_base: str = ""
    deployment_id: str = ""
    api_version: str = os.environ.get("ANON_SYNTH_API_VERSION", "2024-08-01-preview")
    temperature: float = 0.2
    max_tokens: int = 800


@dataclass
class SyntheticResult:
    text: str
    backend: str
    message: str = ""


def _faker_value(entity_type: str) -> str:
    et = str(entity_type or "").upper()
    if et in {"PERSON", "NRP"}:
        return _FAKER.name()
    if et in {"ORGANIZATION", "ORG"}:
        return _FAKER.company()
    if et in {"LOCATION", "GPE", "LOC"}:
        return _FAKER.city()
    if et == "EMAIL_ADDRESS":
        return _FAKER.email()
    if et == "PHONE_NUMBER":
        return _FAKER.phone_number()
    if et == "DATE_TIME":
        return _FAKER.iso8601()
    if et == "IP_ADDRESS":
        return _FAKER.ipv4_public()
    if et == "URL":
        return _FAKER.url()
    if et == "US_SSN":
        return _FAKER.ssn()
    if et in {"CREDIT_CARD", "US_BANK_NUMBER"}:
        return _FAKER.credit_card_number()
    if et in {"US_DRIVER_LICENSE", "US_PASSPORT", "US_ITIN", "MEDICAL_LICENSE"}:
        return _FAKER.bothify(text="??########")
    return _FAKER.word().title()


def _synthesize_with_faker(text: str) -> str:
    if not text:
        return ""

    def _replace(match: re.Match[str]) -> str:
        return _faker_value(match.group(1))

    return _PLACEHOLDER_RE.sub(_replace, text)


def _build_prompt(anonymized_text: str) -> str:
    return (
        "Create synthetic text from de-identified text where placeholders look like <PERSON> or <EMAIL_ADDRESS>. "
        "Replace placeholders with realistic fake values. Keep structure, punctuation, and line breaks. "
        "If no placeholders exist, return the input unchanged.\n\n"
        f"Input:\n{anonymized_text}\n\nOutput:"
    )


def _synthesize_with_openai(anonymized_text: str, cfg: SyntheticConfig) -> str:
    # Imported lazily so OpenAI is optional in local dev.
    from openai import OpenAI, AzureOpenAI  # type: ignore

    provider = str(cfg.provider or "openai").strip().lower()
    model = str(cfg.model or "").strip()
    if provider == "azure_openai":
        client = AzureOpenAI(
            api_key=cfg.api_key,
            api_version=cfg.api_version or "2024-08-01-preview",
            azure_endpoint=cfg.api_base or None,
        )
        model_name = str(cfg.deployment_id or model or "").strip()
    else:
        client = OpenAI(
            api_key=cfg.api_key,
            base_url=(cfg.api_base or None),
        )
        model_name = model

    if not model_name:
        raise ValueError("OpenAI model/deployment is empty.")

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "You generate privacy-safe synthetic text. "
                    "Never leak original PII. Keep formatting close to input."
                ),
            },
            {"role": "user", "content": _build_prompt(anonymized_text)},
        ],
        temperature=float(cfg.temperature or 0.2),
        max_tokens=max(64, int(cfg.max_tokens or 800)),
    )
    content: Optional[str] = None
    if response and response.choices:
        content = response.choices[0].message.content if response.choices[0].message else None
    out = str(content or "").strip()
    if not out:
        raise RuntimeError("OpenAI returned empty synthetic output.")
    return out


def synthesize_from_anonymized_text(anonymized_text: str, cfg: SyntheticConfig) -> SyntheticResult:
    """Convert placeholder text (e.g., <PERSON>) to synthetic content."""
    text = str(anonymized_text or "")
    provider = str(cfg.provider or "faker").strip().lower()
    has_placeholders = bool(_PLACEHOLDER_RE.search(text))

    if not text:
        return SyntheticResult(text="", backend="none", message="No input text.")
    if not has_placeholders:
        return SyntheticResult(text=text, backend="none", message="No placeholders found; output unchanged.")

    if provider in {"openai", "azure_openai"}:
        if not str(cfg.api_key or "").strip():
            fake = _synthesize_with_faker(text)
            return SyntheticResult(
                text=fake,
                backend="faker",
                message="No API key configured; used local Faker synthesis.",
            )
        try:
            out = _synthesize_with_openai(text, cfg)
            return SyntheticResult(text=out, backend=provider, message="Synthetic output generated with LLM.")
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            fake = _synthesize_with_faker(text)
            return SyntheticResult(
                text=fake,
                backend="faker",
                message=f"LLM synthesis failed ({exc}); used local Faker synthesis.",
            )

    fake = _synthesize_with_faker(text)
    return SyntheticResult(text=fake, backend="faker", message="Synthetic output generated with local Faker.")

