from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    role = Column(String, default="user")
    last_active = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String, nullable=False)
    receiver = Column(String, nullable=False)
    text = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class GroupChat(Base):
    __tablename__ = "group_chats"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    creator = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship(
        "GroupMember", back_populates="group", cascade="all, delete-orphan"
    )
    messages = relationship(
        "GroupMessage", back_populates="group", cascade="all, delete-orphan"
    )


class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("group_chats.id"), nullable=False)
    username = Column(String, nullable=False)

    group = relationship("GroupChat", back_populates="members")


class GroupMessage(Base):
    __tablename__ = "group_messages"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("group_chats.id"), nullable=False)
    sender = Column(String, nullable=False)
    text = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    group = relationship("GroupChat", back_populates="messages")