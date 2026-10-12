"""
Приложение для управления расписанием занятий, вебинаров и учебных сессий
с функцией напоминаний.
"""

import json
import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime, timedelta

# Файл, в котором хранится расписание (рядом со скриптом).
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule_data.json")


class EventDialog(tk.Toplevel):
    """Диалог добавления/редактирования события."""

    def __init__(self, parent, title, event=None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # Название события
        ttk.Label(frame, text="Название события:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_var = tk.StringVar(value=event["name"] if event else "")
        self.name_entry = ttk.Entry(frame, textvariable=self.name_var, width=35)
        self.name_entry.grid(row=0, column=1, pady=5)

        # Дата события
        ttk.Label(frame, text="Дата (ДД.ММ.ГГГГ):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.date_var = tk.StringVar(value=event["date"] if event else datetime.now().strftime("%d.%m.%Y"))
        ttk.Entry(frame, textvariable=self.date_var, width=35).grid(row=1, column=1, pady=5)

        # Время начала
        ttk.Label(frame, text="Время начала (ЧЧ:ММ):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.time_var = tk.StringVar(value=event["time"] if event else "09:00")
        ttk.Entry(frame, textvariable=self.time_var, width=35).grid(row=2, column=1, pady=5)

        # Время напоминания
        ttk.Label(frame, text="Напомнить за (мин):").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.reminder_var = tk.StringVar(value=str(event["reminder_minutes"]) if event else "15")
        ttk.Entry(frame, textvariable=self.reminder_var, width=35).grid(row=3, column=1, pady=5)

        # Кнопки
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=15)

        ttk.Button(btn_frame, text="Сохранить", command=self.on_save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)

        self.bind("<Return>", lambda e: self.on_save())
        self.bind("<Escape>", lambda e: self.destroy())

        self.name_entry.focus_set()

    def on_save(self):
        name = self.name_var.get().strip()
        date_str = self.date_var.get().strip()
        time_str = self.time_var.get().strip()
        reminder_str = self.reminder_var.get().strip()

        if not name:
            messagebox.showerror("Ошибка", "Введите название события", parent=self)
            return

        try:
            datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный формат даты. Используйте ДД.ММ.ГГГГ", parent=self)
            return

        try:
            datetime.strptime(time_str, "%H:%M")
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный формат времени. Используйте ЧЧ:ММ", parent=self)
            return

        try:
            reminder = int(reminder_str)
            if reminder < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Напоминание должно быть неотрицательным числом", parent=self)
            return

        self.result = {
            "name": name,
            "date": date_str,
            "time": time_str,
            "reminder_minutes": reminder,
            "reminded": False
        }
        self.destroy()


class ScheduleApp:
    """Главное приложение расписания."""

    def __init__(self, root):
        self.root = root
        self.root.title("Расписание занятий")
        self.root.geometry("800x400")
        self.root.minsize(600, 300)

        self.events = []
        self.table_visible = False

        self._create_ui()
        self._load_events()
        self._schedule_reminder_check()

        # Сохранять расписание при закрытии окна (на случай, если изменения
        # не успели записаться автоматически).
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """Корректное закрытие окна: сохранить расписание и отменить таймер."""
        self._save_events()
        if getattr(self, "_reminder_job", None) is not None:
            try:
                self.root.after_cancel(self._reminder_job)
            except tk.TclError:
                pass
            self._reminder_job = None
        self.root.destroy()

    def _load_events(self):
        """Загрузить расписание из файла (пропуская повреждённые записи)."""
        if not os.path.exists(DATA_FILE):
            return

        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showwarning(
                "Предупреждение",
                f"Не удалось прочитать файл расписания:\n{e}\n"
                f"Приложение запустится с пустым расписанием."
            )
            return

        if not isinstance(data, list):
            return

        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                # Проверяем обязательные поля и их типы.
                name = str(item["name"]).strip()
                date_str = str(item["date"])
                time_str = str(item["time"])
                reminder = int(item["reminder_minutes"])
                reminded = bool(item.get("reminded", False))
                if not name or reminder < 0:
                    continue
                datetime.strptime(date_str, "%d.%m.%Y")
                datetime.strptime(time_str, "%H:%M")
            except (KeyError, TypeError, ValueError):
                continue

            self.events.append({
                "name": name,
                "date": date_str,
                "time": time_str,
                "reminder_minutes": reminder,
                "reminded": reminded,
            })

        self._refresh_table()

    def _save_events(self):
        """Сохранить расписание в файл (автосохранение, ошибки не критичны)."""
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.events, f, ensure_ascii=False, indent=2)
        except OSError:
            # Не блокируем работу приложения из-за ошибки записи.
            pass

    def _create_ui(self):
        # Верхняя панель с кнопками
        self.top_frame = ttk.Frame(self.root, padding=10)
        self.top_frame.pack(fill=tk.X)

        ttk.Button(self.top_frame, text="Развернуть", command=self._show_table).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.top_frame, text="Свернуть", command=self._hide_table).pack(side=tk.LEFT, padx=2)
        ttk.Separator(self.top_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(self.top_frame, text="Добавить", command=self._add_event).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.top_frame, text="Редактировать", command=self._edit_event).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.top_frame, text="Удалить", command=self._delete_event).pack(side=tk.LEFT, padx=2)

        # Статус
        self.status_var = tk.StringVar(value="Таблица свёрнута")
        ttk.Label(self.top_frame, textvariable=self.status_var).pack(side=tk.RIGHT, padx=5)

        # Таблица (изначально скрыта)
        table_frame = ttk.Frame(self.root, padding=10)
        self.table_frame = table_frame

        columns = ("name", "date", "time", "reminder")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=10)

        self.tree.heading("name", text="Название события")
        self.tree.heading("date", text="Дата")
        self.tree.heading("time", text="Время начала")
        self.tree.heading("reminder", text="Напомнить за (мин)")

        self.tree.column("name", width=250, minwidth=150)
        self.tree.column("date", width=120, minwidth=100)
        self.tree.column("time", width=120, minwidth=100)
        self.tree.column("reminder", width=120, minwidth=100)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", lambda e: self._edit_event())

    def _show_table(self):
        if not self.table_visible:
            self.table_frame.pack(fill=tk.BOTH, expand=True, after=self.top_frame)
            self.table_visible = True
            self.status_var.set("Таблица развёрнута")

    def _hide_table(self):
        if self.table_visible:
            self.table_frame.pack_forget()
            self.table_visible = False
            self.status_var.set("Таблица свёрнута")

    def _refresh_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for event in self.events:
            self.tree.insert("", tk.END, values=(
                event["name"],
                event["date"],
                event["time"],
                event["reminder_minutes"]
            ))

    def _add_event(self):
        dialog = EventDialog(self.root, "Добавить событие")
        self.root.wait_window(dialog)

        if dialog.result:
            self.events.append(dialog.result)
            self._refresh_table()
            self._save_events()

    def _edit_event(self):
        if not self.table_visible:
            self._show_table()
            return

        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Информация", "Выберите событие для редактирования")
            return

        item = selection[0]
        idx = self.tree.index(item)
        event = self.events[idx]

        dialog = EventDialog(self.root, "Редактировать событие", event)
        self.root.wait_window(dialog)

        if dialog.result:
            dialog.result["reminded"] = event["reminded"]
            self.events[idx] = dialog.result
            self._refresh_table()
            self._save_events()

    def _delete_event(self):
        if not self.table_visible:
            self._show_table()
            return

        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Информация", "Выберите событие для удаления")
            return

        item = selection[0]
        idx = self.tree.index(item)

        if messagebox.askyesno("Подтверждение", f"Удалить событие «{self.events[idx]['name']}»?"):
            del self.events[idx]
            self._refresh_table()
            self._save_events()

    def _schedule_reminder_check(self):
        """Запланировать следующую проверку напоминаний в главном потоке.

        Используем root.after вместо фонового потока: любой вызов tkinter
        должен происходить только из главного потока, иначе возможен
        нативный вылет (Tcl_AsyncDelete).
        """
        self._check_reminders()
        self._reminder_job = self.root.after(30_000, self._schedule_reminder_check)

    def _check_reminders(self):
        """Проверка напоминаний (выполняется в главном потоке)."""
        now = datetime.now()
        # Работаем с копией списка: пользователь может изменять events
        # через интерфейс, пока идёт проверка.
        for event in list(self.events):
            if event["reminded"]:
                continue

            try:
                event_dt = datetime.strptime(
                    f"{event['date']} {event['time']}", "%d.%m.%Y %H:%M"
                )
            except ValueError:
                continue

            reminder_dt = event_dt - timedelta(minutes=event["reminder_minutes"])

            # Напоминание срабатывает один раз, когда время напоминания наступило.
            # Окно расширено до конца события, чтобы не пропустить из-за шага
            # проверки в 30 секунд.
            if reminder_dt <= now <= event_dt + timedelta(minutes=1):
                event["reminded"] = True
                self._show_reminder(event)

    def _show_reminder(self, event):
        """Показать напоминание (выполняется в главном потоке)."""
        messagebox.showinfo(
            "Напоминание",
            f"Событие: {event['name']}\n"
            f"Дата: {event['date']}\n"
            f"Время: {event['time']}"
        )


def main():
    root = tk.Tk()
    app = ScheduleApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
