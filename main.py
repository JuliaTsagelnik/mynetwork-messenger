from datetime import datetime
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

import models
import schemas
from database import Base, engine, get_db

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Private Network Messenger API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- ПОЛЬЗОВАТЕЛИ ---

@app.post("/api/v1/users", status_code=201)
def create_or_login_user(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == user_data.username).first()
    if user:
        user.last_active = datetime.utcnow()
        db.commit()
        return {"id": user.id, "username": user.username, "role": user.role, "status": "logged_in"}

    new_user = models.User(username=user_data.username, role=user_data.role)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"id": new_user.id, "username": new_user.username, "role": new_user.role, "status": "created"}


@app.get("/api/v1/users")
def get_users(db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    return [{"id": u.id, "username": u.username, "role": u.role, "last_active": u.last_active} for u in users]


# --- ЛИЧНЫЕ СООБЩЕНИЯ ---

@app.post("/api/v1/messages", status_code=201)
def send_message(msg: schemas.MessageCreate, db: Session = Depends(get_db)):
    new_msg = models.Message(sender=msg.sender, receiver=msg.receiver, text=msg.text)
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    return {
        "message_id": new_msg.id,
        "status": "success",
        "timestamp": new_msg.timestamp,
    }


@app.get("/api/v1/messages/{user1}/{user2}")
def get_dialog_history(user1: str, user2: str, db: Session = Depends(get_db)):
    messages = (
        db.query(models.Message)
        .filter(
            or_(
                and_(models.Message.sender == user1, models.Message.receiver == user2),
                and_(models.Message.sender == user2, models.Message.receiver == user1),
            )
        )
        .order_by(models.Message.timestamp)
        .all()
    )
    return [
        {
            "id": m.id,
            "sender": m.sender,
            "receiver": m.receiver,
            "text": m.text,
            "timestamp": m.timestamp,
        }
        for m in messages
    ]


@app.delete("/api/v1/messages")
def clear_all_messages(user_role: str = Header(default="user"), db: Session = Depends(get_db)):
    if user_role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Недостаточно прав. Данная операция разрешена только администратору.",
        )
    db.query(models.Message).delete()
    db.commit()
    return {"status": "success", "detail": "История личных сообщений очищена"}


# --- МНОГОПОЛЬЗОВАТЕЛЬСКИЕ (ГРУППОВЫЕ) ЧАТЫ ---

@app.post("/api/v1/groups", status_code=201)
def create_group(group_data: schemas.GroupCreate, db: Session = Depends(get_db)):
    new_group = models.GroupChat(name=group_data.name, creator=group_data.creator)
    db.add(new_group)
    db.commit()
    db.refresh(new_group)

    unique_members = set(group_data.members)
    unique_members.add(group_data.creator)

    for username in unique_members:
        member = models.GroupMember(group_id=new_group.id, username=username)
        db.add(member)

    db.commit()
    return {
        "id": new_group.id,
        "name": new_group.name,
        "creator": new_group.creator,
        "members": list(unique_members),
    }


@app.get("/api/v1/groups/{username}")
def get_user_groups(username: str, db: Session = Depends(get_db)):
    memberships = (
        db.query(models.GroupMember)
        .filter(models.GroupMember.username == username)
        .all()
    )
    group_ids = [m.group_id for m in memberships]
    if not group_ids:
        return []

    groups = (
        db.query(models.GroupChat)
        .filter(models.GroupChat.id.in_(group_ids))
        .all()
    )
    return [
        {"id": g.id, "name": g.name, "creator": g.creator, "created_at": g.created_at}
        for g in groups
    ]


@app.delete("/api/v1/groups/{group_id}")
def delete_group(group_id: int, username: str, db: Session = Depends(get_db)):
    group = db.query(models.GroupChat).filter(models.GroupChat.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Групповой чат не найден")

    if group.creator != username and username != "admin":
        raise HTTPException(
            status_code=403, detail="Удалить чат может только его создатель"
        )

    db.delete(group)
    db.commit()
    return {"status": "success", "detail": f"Чат '{group.name}' успешно удален"}


@app.post("/api/v1/groups/{group_id}/messages", status_code=201)
def send_group_message(
    group_id: int, msg: schemas.GroupMessageCreate, db: Session = Depends(get_db)
):
    is_member = (
        db.query(models.GroupMember)
        .filter(
            models.GroupMember.group_id == group_id,
            models.GroupMember.username == msg.sender,
        )
        .first()
    )
    if not is_member:
        raise HTTPException(
            status_code=403, detail="Вы не являетесь участником этого чата"
        )

    new_msg = models.GroupMessage(
        group_id=group_id, sender=msg.sender, text=msg.text
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    return {
        "id": new_msg.id,
        "group_id": new_msg.group_id,
        "sender": new_msg.sender,
        "text": new_msg.text,
        "timestamp": new_msg.timestamp,
    }


@app.get("/api/v1/groups/{group_id}/messages")
def get_group_messages(group_id: int, db: Session = Depends(get_db)):
    messages = (
        db.query(models.GroupMessage)
        .filter(models.GroupMessage.group_id == group_id)
        .order_by(models.GroupMessage.timestamp)
        .all()
    )
    return [
        {
            "id": m.id,
            "sender": m.sender,
            "text": m.text,
            "timestamp": m.timestamp,
        }
        for m in messages
    ]