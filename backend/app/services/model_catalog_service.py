from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import KeyMode, ModelCatalog, Provider, ProviderKey
from app.services.provider_service import provider_registry

ALL_PROVIDERS = [Provider.OPENAI, Provider.ANTHROPIC, Provider.OPENROUTER]


def _provider_scope(provider: Provider | None) -> list[Provider]:
    return [provider] if provider else ALL_PROVIDERS


def _has_vault_key(db: Session, user_id: str, provider: Provider) -> bool:
    record = (
        db.query(ProviderKey.id)
        .filter(
            ProviderKey.user_id == user_id,
            ProviderKey.provider == provider,
            ProviderKey.key_mode == KeyMode.VAULT,
        )
        .first()
    )
    return record is not None


def _ensure_utc(value: datetime) -> datetime:
    # SQLite often returns naive datetimes in tests/local.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def should_refresh_model_catalog(
    db: Session,
    user_id: str,
    provider: Provider | None,
    max_age_minutes: int,
) -> bool:
    providers = _provider_scope(provider)
    cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)

    for p in providers:
        if not _has_vault_key(db, user_id, p):
            continue

        newest = (
            db.query(ModelCatalog.last_synced_at)
            .filter(ModelCatalog.provider == p)
            .order_by(ModelCatalog.last_synced_at.desc())
            .first()
        )
        if not newest:
            return True

        last_synced = newest[0]
        if not last_synced:
            return True

        if _ensure_utc(last_synced) < cutoff:
            return True

    return False


async def refresh_model_catalog(
    db: Session,
    user_id: str,
    provider: Provider | None = None,
) -> dict[str, str | bool]:
    providers = _provider_scope(provider)
    stale = False
    stale_reasons: list[str] = []

    for p in providers:
        if not _has_vault_key(db, user_id, p):
            stale = True
            stale_reasons.append(f"Missing vault key for {p.value}")
            continue

        try:
            api_key = provider_registry.resolve_api_key(db, user_id, p, KeyMode.VAULT)
        except HTTPException as exc:
            stale = True
            detail = exc.detail if isinstance(exc.detail, str) else "Unable to resolve API key"
            stale_reasons.append(f"{p.value}: {detail}")
            continue

        adapter = provider_registry.get_adapter(p)
        models = await adapter.list_models(api_key)
        if not models:
            stale = True
            stale_reasons.append(f"No models returned for {p.value}")
            continue

        now = datetime.now(UTC)
        existing_rows = db.query(ModelCatalog).filter(ModelCatalog.provider == p).all()
        by_model_id = {row.model_id: row for row in existing_rows}
        returned_ids = {model.id for model in models}

        for row in existing_rows:
            if row.model_id not in returned_ids:
                row.is_active = False
                row.deprecation_at = now
                row.last_synced_at = now

        for model in models:
            row = by_model_id.get(model.id)
            if not row:
                row = ModelCatalog(
                    provider=p,
                    model_id=model.id,
                    capabilities=model.capabilities,
                    is_active=True,
                    deprecation_at=None,
                    last_synced_at=now,
                )
                db.add(row)
            else:
                row.capabilities = model.capabilities
                row.is_active = True
                row.deprecation_at = None
                row.last_synced_at = now

    db.commit()
    return {"stale": stale, "stale_reason": "; ".join(stale_reasons)}


def list_models(
    db: Session,
    provider: Provider | None = None,
    capability: str | None = None,
) -> list[ModelCatalog]:
    query = db.query(ModelCatalog).filter(ModelCatalog.is_active.is_(True))
    if provider:
        query = query.filter(ModelCatalog.provider == provider)

    models = query.order_by(ModelCatalog.provider.asc(), ModelCatalog.model_id.asc()).all()
    if capability:
        models = [m for m in models if bool(m.capabilities.get(capability))]
    return models
