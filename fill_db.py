import random
from datetime import datetime, timedelta, timezone

from server import (
    Base,
    DBGroupChat,
    DBGroupMember,
    DBGroupMessage,
    DBPrivateMessage,
    DBUser,
    SessionLocal,
    engine,
    hash_password,
)

Base.metadata.create_all(bind=engine)
db = SessionLocal()

# Очистка существующих данных в правильном порядке
db.query(DBGroupMessage).delete()
db.query(DBGroupMember).delete()
db.query(DBGroupChat).delete()
db.query(DBPrivateMessage).delete()
db.query(DBUser).delete()
db.commit()

# Словарь пользователей и их паролей
users_data = {
    "Юля": "yulya2026",
    "Егор": "egor_pass",
    "Вита": "vita_best",
    "мама": "mama1234",
    "Даша": "dasha_d",
    "Ира": "ira_secret",
    "малыш": "baby_007",
    "Саша": "sasha_win",
}

user_objects = {}
for name, pwd in users_data.items():
    user = DBUser(username=name, password_hash=hash_password(pwd))
    db.add(user)
    db.commit()
    db.refresh(user)
    user_objects[name] = user

print("Пользователи созданы. Список паролей:")
for name, pwd in users_data.items():
    print(f"Логин: {name} | Пароль: {pwd}")

# Генерация личных сообщений
phrases = [
    "Привет! Как дела?",
    "Скинула файл, посмотри.",
    "Что задали на завтра?",
    "Давай встретимся вечером.",
    "Окей, поняла.",
    "Спасибо большое!",
    "Напишу позже, сейчас занята курсачом.",
]

for sender in users_data.keys():
    for receiver in users_data.keys():
        if sender != receiver:
            for _ in range(2):
                msg = DBPrivateMessage(
                    sender_id=user_objects[sender].id,
                    receiver_id=user_objects[receiver].id,
                    text=random.choice(phrases),
                    timestamp=datetime.now(timezone.utc)
                    - timedelta(
                        hours=random.randint(1, 48), minutes=random.randint(1, 60)
                    ),
                )
                db.add(msg)

# Создание тестовых групповых чатов
demo_groups = [
    {
        "name": "Учебная группа",
        "creator": "Юля",
        "members": ["Юля", "Егор", "Даша", "Ира"],
        "messages": [
            ("Юля", "Всем привет! Кто уже сдал лабу?"),
            ("Егор", "Привет, я почти закончил."),
            ("Даша", "Скиньте пример отчёта, пожалуйста!"),
        ],
    },
    {
        "name": "Семья",
        "creator": "мама",
        "members": ["мама", "Юля", "Саша"],
        "messages": [
            ("мама", "Во сколько будете дома?"),
            ("Юля", "Буду к 19:00."),
        ],
    },
]

for g_data in demo_groups:
    group = DBGroupChat(
        name=g_data["name"], creator_id=user_objects[g_data["creator"]].id
    )
    db.add(group)
    db.commit()
    db.refresh(group)

    for member_name in g_data["members"]:
        db.add(DBGroupMember(group_id=group.id, user_id=user_objects[member_name].id))

    for idx, (sender_name, text) in enumerate(g_data["messages"]):
        db.add(
            DBGroupMessage(
                group_id=group.id,
                sender_id=user_objects[sender_name].id,
                text=text,
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=30 - idx * 5),
            )
        )

db.commit()
db.close()
print("\nБаза успешно заполнена: 8 пользователей, 112 личных сообщений и 2 групповых чата.")