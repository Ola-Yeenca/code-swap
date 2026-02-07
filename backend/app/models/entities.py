from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDTimestampMixin
from app.models.enums import ChatMode, ContentPartType, DataRegion, KeyMode, Provider, Role


class User(UUIDTimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AuthIdentity(UUIDTimestampMixin, Base):
    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Session(UUIDTimestampMixin, Base):
    __tablename__ = "sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Workspace(UUIDTimestampMixin, Base):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    data_region: Mapped[DataRegion] = mapped_column(String(8), default=DataRegion.US, nullable=False)


class WorkspaceMember(UUIDTimestampMixin, Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[Role] = mapped_column(String(16), default=Role.MEMBER, nullable=False)


class WorkspaceInvite(UUIDTimestampMixin, Base):
    __tablename__ = "workspace_invites"

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    invited_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(String(16), default=Role.MEMBER, nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderKey(UUIDTimestampMixin, Base):
    __tablename__ = "provider_keys"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[Provider] = mapped_column(String(16), nullable=False)
    key_mode: Mapped[KeyMode] = mapped_column(String(16), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    masked_hint: Mapped[str] = mapped_column(String(32), nullable=False)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)


class ModelCatalog(UUIDTimestampMixin, Base):
    __tablename__ = "model_catalog"
    __table_args__ = (UniqueConstraint("provider", "model_id"),)

    provider: Mapped[Provider] = mapped_column(String(16), nullable=False)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deprecation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChatSession(UUIDTimestampMixin, Base):
    __tablename__ = "chat_sessions"

    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="New Chat", nullable=False)
    chat_mode: Mapped[ChatMode] = mapped_column(String(16), default=ChatMode.SINGLE, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session")


class ChatMessage(UUIDTimestampMixin, Base):
    __tablename__ = "chat_messages"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[Provider | None] = mapped_column(String(16), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class MessagePart(UUIDTimestampMixin, Base):
    __tablename__ = "message_parts"

    message_id: Mapped[str] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    part_type: Mapped[ContentPartType] = mapped_column(String(16), nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)


class File(UUIDTimestampMixin, Base):
    __tablename__ = "files"

    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="uploaded", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FileChunk(UUIDTimestampMixin, Base):
    __tablename__ = "file_chunks"
    __table_args__ = (UniqueConstraint("file_id", "chunk_index"),)

    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)


class FileEmbedding(UUIDTimestampMixin, Base):
    __tablename__ = "file_embeddings"

    chunk_id: Mapped[str] = mapped_column(ForeignKey("file_chunks.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[Provider] = mapped_column(String(16), nullable=False)
    embedding_json: Mapped[list[float]] = mapped_column(JSON, nullable=False)


class UsageEvent(UUIDTimestampMixin, Base):
    __tablename__ = "usage_events"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[Provider] = mapped_column(String(16), nullable=False)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class UsageDailyAgg(UUIDTimestampMixin, Base):
    __tablename__ = "usage_daily_agg"
    __table_args__ = (
        UniqueConstraint("date", "user_id", "workspace_id", "provider", "model_id"),
    )

    date: Mapped[date] = mapped_column(Date, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[Provider] = mapped_column(String(16), nullable=False)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    total_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class BillingCustomer(UUIDTimestampMixin, Base):
    __tablename__ = "billing_customers"
    __table_args__ = (UniqueConstraint("workspace_id"), UniqueConstraint("stripe_customer_id"))

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    stripe_customer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)


class BillingSubscription(UUIDTimestampMixin, Base):
    __tablename__ = "billing_subscriptions"
    __table_args__ = (UniqueConstraint("workspace_id"), UniqueConstraint("stripe_subscription_id"))

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    stripe_subscription_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="trialing", nullable=False)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Entitlement(UUIDTimestampMixin, Base):
    __tablename__ = "entitlements"
    __table_args__ = (UniqueConstraint("workspace_id", "feature_key"),)

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    feature_key: Mapped[str] = mapped_column(String(128), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quota: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AuditLog(UUIDTimestampMixin, Base):
    __tablename__ = "audit_logs"

    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class DeletionJob(UUIDTimestampMixin, Base):
    __tablename__ = "deletion_jobs"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class CrewSession(UUIDTimestampMixin, Base):
    __tablename__ = "crew_sessions"

    chat_session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    crew_config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    final_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class CrewSubtask(UUIDTimestampMixin, Base):
    __tablename__ = "crew_subtasks"

    crew_session_id: Mapped[str] = mapped_column(
        ForeignKey("crew_sessions.id", ondelete="CASCADE"), nullable=False
    )
    subtask_id: Mapped[str] = mapped_column(String(36), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_agent: Mapped[str] = mapped_column(String(128), nullable=False)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
