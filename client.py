import threading
import time
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk
import requests

SERVER_URL = "http://127.0.0.1:8000"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class TelegramCloneApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MyNetwork - Приватные и групповые чаты")
        self.geometry("1050x680")
        self.minsize(850, 520)

        # Состояние приложения
        self.current_user = None
        self.chat_type = None          # "private" или "group"
        self.current_chat = None       # username (для личного) или group_id (для группы)
        self.current_group_info = None # словарь с данными активной группы

        self.contacts_list = []
        self.groups_list = []

        self.last_msg_signature = None
        self.rendered_contacts_state = None
        self.rendered_groups_state = None
        self.is_running = True

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.build_login_screen()

    # ==========================================
    # 1. ЭКРАН АВТОРИЗАЦИИ
    # ==========================================
    def build_login_screen(self):
        self.login_frame = ctk.CTkFrame(self)
        self.login_frame.pack(expand=True, fill="both")

        self.logo_lbl = ctk.CTkLabel(
            self.login_frame, text="MyNetwork", font=ctk.CTkFont(size=32, weight="bold")
        )
        self.logo_lbl.pack(pady=(120, 10))

        self.sub_lbl = ctk.CTkLabel(
            self.login_frame, text="Безопасное общение", text_color="gray"
        )
        self.sub_lbl.pack(pady=(0, 30))

        self.login_entry = ctk.CTkEntry(
            self.login_frame, placeholder_text="Имя пользователя", width=280, height=45
        )
        self.login_entry.pack(pady=10)

        self.pass_entry = ctk.CTkEntry(
            self.login_frame, placeholder_text="Пароль", show="•", width=280, height=45
        )
        self.pass_entry.pack(pady=10)

        self.auth_btn = ctk.CTkButton(
            self.login_frame,
            text="Войти в аккаунт",
            width=280,
            height=45,
            command=self.do_login,
        )
        self.auth_btn.pack(pady=25)
        self.bind("<Return>", lambda e: self.do_login())

        self.err_lbl = ctk.CTkLabel(self.login_frame, text="", text_color="#ff5555")
        self.err_lbl.pack()

    def do_login(self):
        username = self.login_entry.get().strip()
        password = self.pass_entry.get().strip()

        if len(username) < 2 or len(password) < 3:
            self.err_lbl.configure(text="Логин (от 2 симв.), Пароль (от 3 симв.)")
            return

        self.auth_btn.configure(state="disabled", text="Подключение...")
        threading.Thread(
            target=self._async_login, args=(username, password), daemon=True
        ).start()

    def _async_login(self, username, password):
        try:
            res = requests.post(
                f"{SERVER_URL}/login",
                json={"username": username, "password": password},
                timeout=5,
            )
            if res.status_code == 200:
                self.current_user = username
                self.after(0, self._transition_to_main)
            else:
                self.after(
                    0, lambda: self._show_login_error("Неверный пароль или ошибка сервера")
                )
        except requests.exceptions.RequestException:
            self.after(
                0,
                lambda: self._show_login_error("Сервер недоступен. Проверьте подключение."),
            )

    def _show_login_error(self, message):
        self.err_lbl.configure(text=message)
        self.auth_btn.configure(state="normal", text="Войти в аккаунт")

    def _transition_to_main(self):
        self.unbind("<Return>")
        self.login_frame.destroy()
        self.build_main_screen()

    # ==========================================
    # 2. ГЛАВНЫЙ ЭКРАН МЕССЕНДЖЕРА
    # ==========================================
    def build_main_screen(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- ЛЕВАЯ ПАНЕЛЬ ---
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(3, weight=1)
        self.sidebar.grid_rowconfigure(4, weight=1)

        # Профиль
        self.profile_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.profile_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            self.profile_frame, text="👤", font=ctk.CTkFont(size=22)
        ).pack(side="left")
        ctk.CTkLabel(
            self.profile_frame,
            text=self.current_user,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(side="left", padx=10)

        # Кнопка выхода
        self.logout_btn = ctk.CTkButton(
            self.sidebar,
            text="Выйти",
            fg_color="#553333",
            hover_color="#773333",
            command=self.logout,
        )
        self.logout_btn.grid(row=1, column=0, padx=20, pady=(0, 8), sticky="ew")

        # Кнопка создания группового чата
        self.create_group_btn = ctk.CTkButton(
            self.sidebar,
            text="+ Создать группу",
            fg_color="#246b42",
            hover_color="#2e8552",
            command=self.open_create_group_dialog,
        )
        self.create_group_btn.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")

        # Список групповых чатов
        self.groups_frame = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent", label_text="Групповые чаты"
        )
        self.groups_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 5))

        # Список личных контактов
        self.contacts_frame = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent", label_text="Контакты"
        )
        self.contacts_frame.grid(row=4, column=0, sticky="nsew", padx=10, pady=(5, 10))

        # --- ПРАВАЯ ПАНЕЛЬ (Окно чата) ---
        self.chat_area = ctk.CTkFrame(self, fg_color="transparent")
        self.chat_area.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.chat_area.grid_rowconfigure(1, weight=1)
        self.chat_area.grid_columnconfigure(0, weight=1)

        # Шапка чата
        self.chat_header = ctk.CTkFrame(self.chat_area, height=55)
        self.chat_header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.chat_header.grid_columnconfigure(0, weight=1)

        self.header_text_frame = ctk.CTkFrame(self.chat_header, fg_color="transparent")
        self.header_text_frame.grid(row=0, column=0, sticky="w", padx=15, pady=8)

        self.chat_title = ctk.CTkLabel(
            self.header_text_frame,
            text="Выберите диалог или группу",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.chat_title.pack(anchor="w")

        self.chat_subtitle = ctk.CTkLabel(
            self.header_text_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.chat_subtitle.pack(anchor="w")

        self.delete_group_btn = ctk.CTkButton(
            self.chat_header,
            text="Удалить чат",
            width=120,
            height=34,
            fg_color="#8b2635",
            hover_color="#a83244",
            command=self.delete_current_group,
        )
        # Изначально кнопка скрыта (показывается только в созданной пользователем группе)

        # Область сообщений
        self.chat_box = ctk.CTkScrollableFrame(self.chat_area, fg_color="#2b2b2b")
        self.chat_box.grid(row=1, column=0, sticky="nsew", pady=(0, 15))

        # Панель ввода
        self.input_frame = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        self.input_frame.grid(row=2, column=0, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.msg_entry = ctk.CTkEntry(
            self.input_frame,
            placeholder_text="Напишите сообщение...",
            height=50,
            state="disabled",
        )
        self.msg_entry.grid(row=0, column=0, padx=(0, 15), sticky="ew")
        self.msg_entry.bind("<Return>", lambda e: self.send_msg())

        self.send_btn = ctk.CTkButton(
            self.input_frame,
            text="Отправить",
            width=130,
            height=50,
            state="disabled",
            command=self.send_msg,
        )
        self.send_btn.grid(row=0, column=1)

        # Запуск фонового опроса сервера
        self.is_running = True
        threading.Thread(target=self.poll_updates, daemon=True).start()

    # ==========================================
    # 3. ФОНОВЫЕ ПРОЦЕССЫ И ОБНОВЛЕНИЕ UI
    # ==========================================
    def poll_updates(self):
        while self.is_running:
            try:
                # 1. Запрашиваем контакты
                res_contacts = requests.get(f"{SERVER_URL}/contacts", timeout=3)
                if res_contacts.status_code == 200:
                    contacts = res_contacts.json()
                    self.contacts_list = contacts
                    self.after(0, self._render_contacts, contacts)

                # 2. Запрашиваем групповые чаты текущего пользователя
                res_groups = requests.get(
                    f"{SERVER_URL}/groups/{self.current_user}", timeout=3
                )
                if res_groups.status_code == 200:
                    groups = res_groups.json()
                    self.groups_list = groups
                    self.after(0, self._render_groups, groups)

                # 3. Запрашиваем сообщения открытого чата
                if self.chat_type == "private" and self.current_chat:
                    res_msgs = requests.get(
                        f"{SERVER_URL}/messages/{self.current_user}/{self.current_chat}",
                        timeout=3,
                    )
                    if res_msgs.status_code == 200:
                        msgs = res_msgs.json()
                        last_id = msgs[-1]["id"] if msgs else None
                        sig = ("private", self.current_chat, len(msgs), last_id)
                        if sig != self.last_msg_signature:
                            self.last_msg_signature = sig
                            self.after(0, self._render_messages, msgs)

                elif self.chat_type == "group" and self.current_chat is not None:
                    res_msgs = requests.get(
                        f"{SERVER_URL}/groups/{self.current_chat}/messages", timeout=3
                    )
                    if res_msgs.status_code == 200:
                        msgs = res_msgs.json()
                        last_id = msgs[-1]["id"] if msgs else None
                        sig = ("group", self.current_chat, len(msgs), last_id)
                        if sig != self.last_msg_signature:
                            self.last_msg_signature = sig
                            self.after(0, self._render_messages, msgs)
                    elif res_msgs.status_code == 404:
                        # Группу удалили с другого клиента
                        self.after(0, self._reset_chat_view, "Групповой чат был удалён")

            except requests.exceptions.RequestException:
                pass

            time.sleep(1.5)

    def _render_contacts(self, contacts):
        filtered = [c for c in contacts if c != self.current_user]
        active_key = self.current_chat if self.chat_type == "private" else None
        state = (tuple(filtered), active_key)
        if state == self.rendered_contacts_state:
            return
        self.rendered_contacts_state = state

        for widget in self.contacts_frame.winfo_children():
            widget.destroy()

        for c in filtered:
            btn_color = "#1f538d" if c == active_key else "#333333"
            btn = ctk.CTkButton(
                self.contacts_frame,
                text=f"👤 {c}",
                fg_color=btn_color,
                anchor="w",
                height=35,
                command=lambda user=c: self.open_private_chat(user),
            )
            btn.pack(pady=3, fill="x", padx=5)

    def _render_groups(self, groups):
        active_id = self.current_chat if self.chat_type == "group" else None
        state = (
            tuple((g["id"], g["name"], len(g["members"])) for g in groups),
            active_id,
        )
        if state == self.rendered_groups_state:
            return
        self.rendered_groups_state = state

        for widget in self.groups_frame.winfo_children():
            widget.destroy()

        if not groups:
            ctk.CTkLabel(
                self.groups_frame, text="Нет групповых чатов", text_color="gray"
            ).pack(pady=8)
            return

        for g in groups:
            btn_color = "#1f538d" if g["id"] == active_id else "#333333"
            btn = ctk.CTkButton(
                self.groups_frame,
                text=f"👥 {g['name']} ({len(g['members'])})",
                fg_color=btn_color,
                anchor="w",
                height=35,
                command=lambda grp=g: self.open_group_chat(grp),
            )
            btn.pack(pady=3, fill="x", padx=5)

    def _render_messages(self, msgs):
        for widget in self.chat_box.winfo_children():
            widget.destroy()

        if not msgs:
            ctk.CTkLabel(
                self.chat_box, text="Сообщений пока нет. Напишите первым!", text_color="gray"
            ).pack(pady=20)
            return

        for m in msgs:
            is_mine = m["sender"] == self.current_user
            bg = "#1f538d" if is_mine else "#444444"
            align = "e" if is_mine else "w"

            try:
                dt = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
                t_str = dt.strftime("%H:%M")
            except Exception:
                t_str = ""

            if is_mine:
                text = f"{m['text']}  [{t_str}]"
            else:
                text = f"{m['sender']} [{t_str}]:\n{m['text']}"

            lbl = ctk.CTkLabel(
                self.chat_box,
                text=text,
                fg_color=bg,
                corner_radius=15,
                padx=15,
                pady=10,
                justify="left",
                wraplength=420,
            )
            lbl.pack(anchor=align, pady=5, padx=15)

        self.chat_box._parent_canvas.yview_moveto(1.0)

    # ==========================================
    # 4. РАБОТА С ЧАТАМИ (ЛИЧНЫЕ И ГРУППОВЫЕ)
    # ==========================================
    def open_private_chat(self, user):
        self.chat_type = "private"
        self.current_chat = user
        self.current_group_info = None
        self.last_msg_signature = None

        self.chat_title.configure(text=f"Диалог: {user}")
        self.chat_subtitle.configure(text="Личный чат")
        self.delete_group_btn.grid_forget()

        self.msg_entry.configure(state="normal", placeholder_text=f"Написать {user}...")
        self.send_btn.configure(state="normal")

        self.rendered_contacts_state = None
        self.rendered_groups_state = None
        self._render_contacts(self.contacts_list)
        self._render_groups(self.groups_list)

    def open_group_chat(self, group_info):
        self.chat_type = "group"
        self.current_chat = group_info["id"]
        self.current_group_info = group_info
        self.last_msg_signature = None

        members_str = ", ".join(group_info.get("members", []))
        self.chat_title.configure(text=f"Группа: {group_info['name']}")
        self.chat_subtitle.configure(
            text=f"Создатель: {group_info['creator']} | Участники: {members_str}"
        )

        # Кнопка удаления видна только создателю группы (или admin)
        if (
            group_info["creator"] == self.current_user
            or self.current_user == "admin"
        ):
            self.delete_group_btn.grid(row=0, column=1, padx=15, pady=10, sticky="e")
        else:
            self.delete_group_btn.grid_forget()

        self.msg_entry.configure(
            state="normal", placeholder_text=f"Написать в группу «{group_info['name']}»..."
        )
        self.send_btn.configure(state="normal")

        self.rendered_contacts_state = None
        self.rendered_groups_state = None
        self._render_contacts(self.contacts_list)
        self._render_groups(self.groups_list)

    def _reset_chat_view(self, title_text="Выберите диалог или группу"):
        self.chat_type = None
        self.current_chat = None
        self.current_group_info = None
        self.last_msg_signature = None

        self.chat_title.configure(text=title_text)
        self.chat_subtitle.configure(text="")
        self.delete_group_btn.grid_forget()

        self.msg_entry.delete(0, "end")
        self.msg_entry.configure(state="disabled", placeholder_text="Напишите сообщение...")
        self.send_btn.configure(state="disabled")

        for widget in self.chat_box.winfo_children():
            widget.destroy()

        self.rendered_contacts_state = None
        self.rendered_groups_state = None
        self._render_contacts(self.contacts_list)
        self._render_groups(self.groups_list)

    # ==========================================
    # 5. СОЗДАНИЕ И УДАЛЕНИЕ ГРУППОВОГО ЧАТА
    # ==========================================
    def open_create_group_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Новый групповой чат")
        dialog.geometry("400x480")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="Создание многопользовательского чата",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(20, 10))

        name_entry = ctk.CTkEntry(
            dialog, placeholder_text="Введите название группы...", width=340, height=40
        )
        name_entry.pack(pady=(5, 15))

        ctk.CTkLabel(
            dialog, text="Выберите участников:", font=ctk.CTkFont(size=13)
        ).pack(anchor="w", padx=30)

        members_scroll = ctk.CTkScrollableFrame(dialog, width=320, height=220)
        members_scroll.pack(pady=10, padx=25, fill="both", expand=True)

        checkbox_vars = {}
        available_users = [u for u in self.contacts_list if u != self.current_user]

        if not available_users:
            ctk.CTkLabel(
                members_scroll, text="Нет других пользователей", text_color="gray"
            ).pack(pady=10)
        else:
            for user in available_users:
                var = ctk.BooleanVar(value=False)
                cb = ctk.CTkCheckBox(members_scroll, text=user, variable=var)
                cb.pack(anchor="w", pady=4, padx=10)
                checkbox_vars[user] = var

        error_lbl = ctk.CTkLabel(dialog, text="", text_color="#ff5555")
        error_lbl.pack()

        def submit_group():
            group_name = name_entry.get().strip()
            selected = [u for u, var in checkbox_vars.items() if var.get()]

            if not group_name:
                error_lbl.configure(text="Введите название чата")
                return
            if not selected:
                error_lbl.configure(text="Выберите хотя бы одного участника")
                return

            create_btn.configure(state="disabled", text="Создание...")
            threading.Thread(
                target=self._async_create_group,
                args=(group_name, selected, dialog, error_lbl, create_btn),
                daemon=True,
            ).start()

        create_btn = ctk.CTkButton(
            dialog,
            text="Создать чат",
            width=340,
            height=42,
            fg_color="#246b42",
            hover_color="#2e8552",
            command=submit_group,
        )
        create_btn.pack(pady=(5, 20))

    def _async_create_group(self, group_name, selected_members, dialog, error_lbl, create_btn):
        try:
            res = requests.post(
                f"{SERVER_URL}/groups",
                json={
                    "name": group_name,
                    "creator": self.current_user,
                    "members": selected_members,
                },
                timeout=5,
            )
            if res.status_code == 201:
                created_group = res.json()
                self.after(0, lambda: self._on_group_created(dialog, created_group))
            else:
                detail = res.json().get("detail", "Ошибка создания чата")
                self.after(
                    0,
                    lambda: (
                        error_lbl.configure(text=detail),
                        create_btn.configure(state="normal", text="Создать чат"),
                    ),
                )
        except requests.exceptions.RequestException:
            self.after(
                0,
                lambda: (
                    error_lbl.configure(text="Нет связи с сервером"),
                    create_btn.configure(state="normal", text="Создать чат"),
                ),
            )

    def _on_group_created(self, dialog, created_group):
        dialog.destroy()
        self.groups_list.insert(0, created_group)
        self.open_group_chat(created_group)

    def delete_current_group(self):
        if self.chat_type != "group" or not self.current_group_info:
            return

        group_id = self.current_group_info["id"]
        group_name = self.current_group_info["name"]

        confirmed = messagebox.askyesno(
            "Удаление группового чата",
            f"Вы уверены, что хотите удалить чат «{group_name}»?\nВся переписка в группе будет удалена безвозвратно.",
        )
        if not confirmed:
            return

        threading.Thread(
            target=self._async_delete_group, args=(group_id,), daemon=True
        ).start()

    def _async_delete_group(self, group_id):
        try:
            res = requests.delete(
                f"{SERVER_URL}/groups/{group_id}",
                params={"username": self.current_user},
                timeout=5,
            )
            if res.status_code == 200:
                self.groups_list = [g for g in self.groups_list if g["id"] != group_id]
                self.after(0, lambda: self._reset_chat_view("Групповой чат удалён"))
            else:
                detail = res.json().get("detail", "Не удалось удалить чат")
                self.after(0, lambda: messagebox.showerror("Ошибка", detail))
        except requests.exceptions.RequestException:
            self.after(
                0, lambda: messagebox.showerror("Ошибка", "Сервер недоступен")
            )

    # ==========================================
    # 6. ОТПРАВКА СООБЩЕНИЙ И ВЫХОД
    # ==========================================
    def send_msg(self):
        text = self.msg_entry.get().strip()
        if not text or not self.current_chat:
            return

        self.msg_entry.delete(0, "end")
        if self.chat_type == "private":
            threading.Thread(
                target=self._async_send_private,
                args=(self.current_chat, text),
                daemon=True,
            ).start()
        elif self.chat_type == "group":
            threading.Thread(
                target=self._async_send_group,
                args=(self.current_chat, text),
                daemon=True,
            ).start()

    def _async_send_private(self, receiver, text):
        try:
            requests.post(
                f"{SERVER_URL}/send",
                json={"sender": self.current_user, "receiver": receiver, "text": text},
                timeout=3,
            )
        except requests.exceptions.RequestException:
            pass

    def _async_send_group(self, group_id, text):
        try:
            requests.post(
                f"{SERVER_URL}/groups/{group_id}/send",
                json={"sender": self.current_user, "text": text},
                timeout=3,
            )
        except requests.exceptions.RequestException:
            pass

    def logout(self):
        self.is_running = False
        self.current_user = None
        self.chat_type = None
        self.current_chat = None
        self.current_group_info = None
        self.last_msg_signature = None
        self.rendered_contacts_state = None
        self.rendered_groups_state = None

        for widget in self.winfo_children():
            widget.destroy()

        self.build_login_screen()

    def on_closing(self):
        self.is_running = False
        self.destroy()


if __name__ == "__main__":
    app = TelegramCloneApp()
    app.mainloop()