import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, and_, create_engine, or_
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

# ==========================================
# 1. НАСТРОЙКА ЛОГИРОВАНИЯ И ИНФРАСТРУКТУРЫ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MyNetworkServer")

SQLALCHEMY_DATABASE_URL = "sqlite:///./messenger.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ==========================================
# 2. МОДЕЛИ БАЗЫ ДАННЫХ (SQLAlchemy ORM)
# ==========================================
class DBUser(Base):
    """Модель пользователя в базе данных"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=utc_now)
    last_active = Column(DateTime, default=utc_now)

    messages_sent = relationship(
        "DBPrivateMessage",
        foreign_keys="DBPrivateMessage.sender_id",
        back_populates="sender",
    )
    messages_received = relationship(
        "DBPrivateMessage",
        foreign_keys="DBPrivateMessage.receiver_id",
        back_populates="receiver",
    )


class DBPrivateMessage(Base):
    """Модель приватного сообщения"""

    __tablename__ = "private_messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(String(1000), nullable=False)
    timestamp = Column(DateTime, default=utc_now)
    is_read = Column(Integer, default=0)  # 0 - не прочитано, 1 - прочитано

    sender = relationship("DBUser", foreign_keys=[sender_id], back_populates="messages_sent")
    receiver = relationship("DBUser", foreign_keys=[receiver_id], back_populates="messages_received")


class DBGroupChat(Base):
    """Модель многопользовательского (группового) чата"""

    __tablename__ = "group_chats"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now)

    creator = relationship("DBUser", foreign_keys=[creator_id])
    members = relationship(
        "DBGroupMember", back_populates="group", cascade="all, delete-orphan"
    )
    messages = relationship(
        "DBGroupMessage", back_populates="group", cascade="all, delete-orphan"
    )


class DBGroupMember(Base):
    """Участник группового чата"""

    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("group_chats.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    group = relationship("DBGroupChat", back_populates="members")
    user = relationship("DBUser")


class DBGroupMessage(Base):
    """Сообщение в групповом чате"""

    __tablename__ = "group_messages"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("group_chats.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(String(1000), nullable=False)
    timestamp = Column(DateTime, default=utc_now)

    group = relationship("DBGroupChat", back_populates="messages")
    sender = relationship("DBUser")


# Создание таблиц при запуске
Base.metadata.create_all(bind=engine)


# ==========================================
# 3. СХЕМЫ ВАЛИДАЦИИ DTO (Pydantic)
# ==========================================
class UserAuth(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, description="Имя пользователя")
    password: str = Field(..., min_length=3, description="Пароль пользователя")


class PrivateMessageCreate(BaseModel):
    sender: str
    receiver: str
    text: str = Field(..., min_length=1, max_length=1000)


class MessageResponse(BaseModel):
    id: int
    sender: str
    receiver: str
    text: str
    timestamp: datetime
    is_read: int
    model_config = {"from_attributes": True}


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Название чата")
    creator: str = Field(..., description="Имя создателя чата")
    members: List[str] = Field(default_factory=list, description="Список участников")


class GroupResponse(BaseModel):
    id: int
    name: str
    creator: str
    members: List[str]
    created_at: datetime


class GroupMessageCreate(BaseModel):
    sender: str
    text: str = Field(..., min_length=1, max_length=1000)


class GroupMessageResponse(BaseModel):
    id: int
    group_id: int
    sender: str
    text: str
    timestamp: datetime


# ==========================================
# 4. ВСПОМОГАТЕЛЬНЫЕ СЕРВИСЫ
# ==========================================
def get_db():
    """Генератор сессий базы данных (Dependency Injection)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    """Криптографическое хэширование пароля (SHA-256)"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_user_by_username(db: Session, username: str) -> Optional[DBUser]:
    """Поиск пользователя по логину"""
    return db.query(DBUser).filter(DBUser.username == username).first()


# ==========================================
# 5. ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ
# ==========================================
app = FastAPI(
    title="MyNetwork Messenger API",
    description="Сервер для обмена личными и групповыми сообщениями",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# 6. КОНТРОЛЛЕРЫ: АВТОРИЗАЦИЯ И КОНТАКТЫ
# ==========================================
@app.post("/login", summary="Аутентификация и регистрация", tags=["Авторизация"])
def login_or_register(user: UserAuth, db: Session = Depends(get_db)):
    logger.info(f"Попытка входа пользователя: {user.username}")
    db_user = get_user_by_username(db, user.username)
    hashed_pw = hash_password(user.password)

    if not db_user:
        logger.info(f"Создание нового аккаунта: {user.username}")
        new_user = DBUser(username=user.username, password_hash=hashed_pw)
        db.add(new_user)
        db.commit()
        return {"status": "registered", "message": "Аккаунт успешно создан"}

    if db_user.password_hash != hashed_pw:
        logger.warning(f"Неверный пароль для пользователя: {user.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный пароль",
        )

    db_user.last_active = utc_now()
    db.commit()
    logger.info(f"Успешный вход: {user.username}")
    return {"status": "success", "message": "Успешная авторизация"}


@app.get("/contacts", response_model=List[str], summary="Список пользователей", tags=["Контакты"])
def get_contacts(db: Session = Depends(get_db)):
    users = db.query(DBUser.username).order_by(DBUser.username).all()
    return [user.username for user in users]


# ==========================================
# 7. КОНТРОЛЛЕРЫ: ЛИЧНЫЕ СООБЩЕНИЯ
# ==========================================
@app.post("/send", summary="Отправить личное сообщение", tags=["Личные сообщения"])
def send_private_message(msg: PrivateMessageCreate, db: Session = Depends(get_db)):
    sender = get_user_by_username(db, msg.sender)
    receiver = get_user_by_username(db, msg.receiver)

    if not sender or not receiver:
        logger.error(f"Ошибка отправки: {msg.sender} -> {msg.receiver}")
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    db_msg = DBPrivateMessage(
        sender_id=sender.id,
        receiver_id=receiver.id,
        text=msg.text,
    )
    db.add(db_msg)
    db.commit()
    db.refresh(db_msg)
    logger.info(f"Личное сообщение от {msg.sender} к {msg.receiver} доставлено.")
    return {"status": "ok", "message_id": db_msg.id}


@app.get(
    "/messages/{user1}/{user2}",
    response_model=List[MessageResponse],
    summary="История личного диалога",
    tags=["Личные сообщения"],
)
def get_dialog_history(user1: str, user2: str, db: Session = Depends(get_db)):
    u1 = get_user_by_username(db, user1)
    u2 = get_user_by_username(db, user2)

    if not u1 or not u2:
        return []

    messages = (
        db.query(DBPrivateMessage)
        .filter(
            or_(
                and_(DBPrivateMessage.sender_id == u1.id, DBPrivateMessage.receiver_id == u2.id),
                and_(DBPrivateMessage.sender_id == u2.id, DBPrivateMessage.receiver_id == u1.id),
            )
        )
        .order_by(DBPrivateMessage.timestamp)
        .all()
    )

    history = []
    for m in messages:
        sender_name = u1.username if m.sender_id == u1.id else u2.username
        receiver_name = u2.username if m.sender_id == u1.id else u1.username
        history.append(
            {
                "id": m.id,
                "sender": sender_name,
                "receiver": receiver_name,
                "text": m.text,
                "timestamp": m.timestamp,
                "is_read": m.is_read,
            }
        )
    return history


# ==========================================
# 8. КОНТРОЛЛЕРЫ: ГРУППОВЫЕ ЧАТЫ
# ==========================================
@app.post(
    "/groups",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать многопользовательский чат",
    tags=["Групповые чаты"],
)
def create_group(group_data: GroupCreate, db: Session = Depends(get_db)):
    creator = get_user_by_username(db, group_data.creator)
    if not creator:
        raise HTTPException(status_code=404, detail="Создатель не найден")

    clean_name = group_data.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Название чата не может быть пустым")

    new_group = DBGroupChat(name=clean_name, creator_id=creator.id)
    db.add(new_group)
    db.commit()
    db.refresh(new_group)

    # Собираем уникальных существующих участников (создатель добавляется всегда)
    member_usernames = set(group_data.members)
    member_usernames.add(creator.username)

    added_usernames = []
    for uname in sorted(member_usernames):
        user_obj = get_user_by_username(db, uname)
        if user_obj:
            db.add(DBGroupMember(group_id=new_group.id, user_id=user_obj.id))
            added_usernames.append(user_obj.username)

    db.commit()
    logger.info(f"Создан групповой чат '{new_group.name}' (id={new_group.id}) пользователем {creator.username}")
    return GroupResponse(
        id=new_group.id,
        name=new_group.name,
        creator=creator.username,
        members=added_usernames,
        created_at=new_group.created_at,
    )


@app.get(
    "/groups/{username}",
    response_model=List[GroupResponse],
    summary="Получить групповые чаты пользователя",
    tags=["Групповые чаты"],
)
def get_user_groups(username: str, db: Session = Depends(get_db)):
    user = get_user_by_username(db, username)
    if not user:
        return []

    memberships = db.query(DBGroupMember).filter(DBGroupMember.user_id == user.id).all()
    group_ids = [m.group_id for m in memberships]
    if not group_ids:
        return []

    groups = (
        db.query(DBGroupChat)
        .filter(DBGroupChat.id.in_(group_ids))
        .order_by(DBGroupChat.created_at.desc())
        .all()
    )

    result = []
    for g in groups:
        members_list = sorted([m.user.username for m in g.members if m.user])
        result.append(
            GroupResponse(
                id=g.id,
                name=g.name,
                creator=g.creator.username if g.creator else "",
                members=members_list,
                created_at=g.created_at,
            )
        )
    return result


@app.delete(
    "/groups/{group_id}",
    summary="Удалить многопользовательский чат",
    tags=["Групповые чаты"],
)
def delete_group(
    group_id: int,
    username: str = Query(..., description="Логин пользователя, удаляющего чат"),
    db: Session = Depends(get_db),
):
    group = db.query(DBGroupChat).filter(DBGroupChat.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Групповой чат не найден")

    creator_username = group.creator.username if group.creator else ""
    if creator_username != username and username != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Удалить чат может только его создатель",
        )

    group_name = group.name
    db.delete(group)
    db.commit()
    logger.info(f"Групповой чат '{group_name}' (id={group_id}) удалён пользователем {username}")
    return {"status": "ok", "message": f"Чат '{group_name}' успешно удалён"}


@app.post(
    "/groups/{group_id}/send",
    summary="Отправить сообщение в групповой чат",
    tags=["Групповые чаты"],
)
def send_group_message(
    group_id: int, msg: GroupMessageCreate, db: Session = Depends(get_db)
):
    group = db.query(DBGroupChat).filter(DBGroupChat.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Групповой чат не найден")

    sender = get_user_by_username(db, msg.sender)
    if not sender:
        raise HTTPException(status_code=404, detail="Отправитель не найден")

    is_member = (
        db.query(DBGroupMember)
        .filter(DBGroupMember.group_id == group_id, DBGroupMember.user_id == sender.id)
        .first()
    )
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы не являетесь участником этого чата",
        )

    db_msg = DBGroupMessage(group_id=group_id, sender_id=sender.id, text=msg.text)
    db.add(db_msg)
    db.commit()
    db.refresh(db_msg)
    logger.info(f"Сообщение от {sender.username} в группу '{group.name}' доставлено.")
    return {"status": "ok", "message_id": db_msg.id}


@app.get(
    "/groups/{group_id}/messages",
    response_model=List[GroupMessageResponse],
    summary="История сообщений группового чата",
    tags=["Групповые чаты"],
)
def get_group_messages(group_id: int, db: Session = Depends(get_db)):
    group = db.query(DBGroupChat).filter(DBGroupChat.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Групповой чат не найден")

    messages = (
        db.query(DBGroupMessage)
        .filter(DBGroupMessage.group_id == group_id)
        .order_by(DBGroupMessage.timestamp)
        .all()
    )
    return [
        GroupMessageResponse(
            id=m.id,
            group_id=m.group_id,
            sender=m.sender.username if m.sender else "Неизвестный",
            text=m.text,
            timestamp=m.timestamp,
        )
        for m in messages
    ]


if __name__ == "__main__":
    logger.info("Запуск сервера MyNetwork...")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)