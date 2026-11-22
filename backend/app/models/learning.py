"""v1.8 学习目标、诊断与计划领域模型。

本文件先定义学习目标相关表；诊断和计划模型将在相应能力实现时追加。
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, relationship, mapped_column

from app.core.database import Base


class LearningGoal(Base):
    """学生学习目标的稳定身份，当前状态由不可变版本承载。"""

    __tablename__ = "learning_goals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    current_version_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "learning_goal_versions.id",
            use_alter=True,
            name="fk_learning_goals_current_version",
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    current_version: Mapped["LearningGoalVersion | None"] = relationship(
        "LearningGoalVersion", foreign_keys=[current_version_id], post_update=True
    )
    versions: Mapped[list["LearningGoalVersion"]] = relationship(
        "LearningGoalVersion",
        foreign_keys="LearningGoalVersion.goal_id",
        order_by="LearningGoalVersion.version_no",
    )

    __table_args__ = (Index("idx_learning_goal_student", "student_id", "current_version_id"),)

    @property
    def current_version_no(self) -> int | None:
        return self.current_version.version_no if self.current_version else None


class LearningGoalVersion(Base):
    """学习目标的不可变配置与受控知识版本快照。"""

    __tablename__ = "learning_goal_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    goal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("learning_goals.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_versions.id"), nullable=False
    )
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    weekly_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str] = mapped_column(String(20), nullable=False)
    target_level: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    change_reason: Mapped[str] = mapped_column(String(50), nullable=False, default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    targets: Mapped[list["LearningGoalTarget"]] = relationship(
        "LearningGoalTarget",
        cascade="all, delete-orphan",
        order_by="LearningGoalTarget.id",
    )

    __table_args__ = (
        UniqueConstraint("goal_id", "version_no", name="uk_learning_goal_version_no"),
        Index("idx_goal_version_knowledge", "knowledge_version_id", "status"),
    )


class LearningGoalTarget(Base):
    """一个目标版本包含的目标知识点。"""

    __tablename__ = "learning_goal_targets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    goal_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("learning_goal_versions.id", ondelete="CASCADE"), nullable=False
    )
    knowledge_point_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_points.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("goal_version_id", "knowledge_point_id", name="uk_goal_target"),
    )
