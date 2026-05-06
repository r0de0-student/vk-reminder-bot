import re
import threading
import time
import random
import os
from datetime import datetime, timedelta
import pytz
from vk_api import VkApi
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.utils import get_random_id
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import json
import sys

TOKEN = os.environ.get('TOKEN')
GROUP_ID = int(os.environ.get('GROUP_ID', 238286097))
ADMIN_ID = 540139562
GROUP_LINK = os.environ.get('GROUP_LINK', 'https://vk.com/club238286097')

REMINDERS_FILE = "reminders.json"
FEEDBACK_FILE = "feedback.json"

TIMEZONE = pytz.timezone('Asia/Novosibirsk')

VERSION = "2.5"


class ReminderBot:
    def __init__(self, token, group_id):
        self.token = token
        self.group_id = group_id
        self.vk_session = None
        self.vk = None
        self.longpoll = None
        self.user_states = {}
        self.reminders = self.load_reminders()
        self.feedbacks = self.load_feedbacks()
        self.check_thread = None
        self.running = True
        self.init_vk_session()
        print("✅ Бот успешно запущен!")

    def get_now(self):
        return datetime.now(TIMEZONE)

    def init_vk_session(self):
        try:
            self.vk_session = VkApi(token=self.token)
            self.vk = self.vk_session.get_api()
            self.longpoll = VkBotLongPoll(self.vk_session, self.group_id, wait=25)
            print("✅ Сессия ВК успешно создана")
            return True
        except Exception as e:
            print(f"❌ Ошибка инициализации: {e}")
            return False

    def load_reminders(self):
        if os.path.exists(REMINDERS_FILE):
            try:
                with open(REMINDERS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_reminders(self):
        try:
            with open(REMINDERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.reminders, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")

    def load_feedbacks(self):
        if os.path.exists(FEEDBACK_FILE):
            try:
                with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []

    def save_feedbacks(self):
        try:
            with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.feedbacks, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ Ошибка сохранения обращений: {e}")

    def add_feedback(self, user_id, message):
        now = self.get_now()
        feedback = {
            "id": len(self.feedbacks) + 1,
            "user_id": user_id,
            "message": message,
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "new"
        }
        self.feedbacks.append(feedback)
        self.save_feedbacks()
        self.notify_admin(feedback)
        return feedback

    def notify_admin(self, feedback):
        try:
            msg = f"📨 НОВОЕ ОБРАЩЕНИЕ!\n\n"
            msg += f"🆔 ID: {feedback['id']}\n"
            msg += f"👤 User ID: {feedback['user_id']}\n"
            msg += f"📅 Дата и время: {feedback['created_at']}\n"
            msg += f"📝 Сообщение:\n{feedback['message']}\n\n"
            msg += f"📊 Статус: {feedback['status']}"

            self.vk.messages.send(
                user_id=ADMIN_ID,
                message=msg,
                random_id=get_random_id()
            )
            print(f"✅ Уведомление админу о обращении #{feedback['id']}")
        except Exception as e:
            print(f"❌ Ошибка уведомления админа: {e}")

    def send_message(self, user_id, message, keyboard=None):
        try:
            self.vk.messages.send(
                user_id=user_id,
                message=message,
                random_id=get_random_id(),
                keyboard=keyboard.get_keyboard() if keyboard else None
            )
            print(f"✅ Ответ для {user_id}")
            return True
        except Exception as e:
            print(f"❌ Ошибка отправки: {e}")
            return False

    def parse_datetime(self, text):
        text_lower = text.lower().strip()

        is_tomorrow = False
        if "завтра" in text_lower:
            is_tomorrow = True
            text_lower = text_lower.replace("завтра", "").strip()

        pattern_with_date = r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+в?\s*(\d{1,2}):(\d{2})'
        match = re.search(pattern_with_date, text_lower)

        months_ru = {
            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
            'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
            'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
        }

        now = self.get_now()

        if match:
            day = int(match.group(1))
            month_name = match.group(2)
            hour = int(match.group(3))
            minute = int(match.group(4))
            month = months_ru[month_name]

            year = now.year
            if month < now.month or (month == now.month and day < now.day):
                year += 1
            elif is_tomorrow:
                year += 1

            try:
                return TIMEZONE.localize(datetime(year, month, day, hour, minute))
            except:
                return None

        pattern_time = r'(\d{1,2}):(\d{2})'
        match = re.search(pattern_time, text_lower)

        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))

            if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                return None

            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            if target <= now or is_tomorrow:
                target += timedelta(days=1)

            return target

        return None

    def add_reminder(self, user_id, target_datetime, text):
        user_id_str = str(user_id)
        if user_id_str not in self.reminders:
            self.reminders[user_id_str] = []

        reminder = {
            "id": len(self.reminders[user_id_str]) + 1,
            "datetime": target_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "date": target_datetime.strftime("%d.%m.%Y"),
            "time": target_datetime.strftime("%H:%M"),
            "text": text,
            "created_at": self.get_now().strftime("%Y-%m-%d %H:%M:%S")
        }

        self.reminders[user_id_str].append(reminder)
        self.save_reminders()
        return reminder

    def get_user_reminders(self, user_id):
        return self.reminders.get(str(user_id), [])

    def delete_reminder(self, user_id, reminder_id):
        user_id_str = str(user_id)
        if user_id_str in self.reminders:
            original_count = len(self.reminders[user_id_str])
            self.reminders[user_id_str] = [r for r in self.reminders[user_id_str] if r['id'] != reminder_id]
            if len(self.reminders[user_id_str]) < original_count:
                self.save_reminders()
                return True
        return False

    def check_reminders(self):
        print("🔄 Проверка напоминаний запущена...")
        while self.running:
            try:
                current = self.get_now()
                current_datetime_str = current.strftime("%Y-%m-%d %H:%M")

                for user_id_str, user_reminders in self.reminders.items():
                    for reminder in user_reminders[:]:
                        reminder_datetime_str = reminder["datetime"][:16]

                        if reminder_datetime_str == current_datetime_str:
                            msg = f"🔔 НАПОМИНАНИЕ!\n\n📝 {reminder['text']}\n\n📅 {reminder['date']} в {reminder['time']}"
                            self.send_message(int(user_id_str), msg)
                            user_reminders.remove(reminder)
                            self.save_reminders()
                            print(f"✅ Напоминание отправлено {user_id_str}")

                time.sleep(30)
            except Exception as e:
                print(f"❌ Ошибка проверки: {e}")
                time.sleep(60)

    def get_main_keyboard(self):
        keyboard = VkKeyboard(one_time=False)
        keyboard.add_button("➕ НАПОМИНАНИЕ", color=VkKeyboardColor.POSITIVE)
        keyboard.add_button("📋 МОИ НАПОМИНАНИЯ", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("❓ ПОМОЩЬ", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("✍️ ПОДДЕРЖКА", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("📢 ПОДПИСАТЬСЯ", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("📰 НОВОСТИ", color=VkKeyboardColor.PRIMARY)
        return keyboard

    def get_subscribe_keyboard(self):
        keyboard = VkKeyboard(one_time=False)
        keyboard.add_openlink_button("🔔 ПЕРЕЙТИ В СООБЩЕСТВО", GROUP_LINK)
        keyboard.add_button("❓ ПОМОЩЬ", color=VkKeyboardColor.SECONDARY)
        keyboard.add_button("🔙 ГЛАВНОЕ МЕНЮ", color=VkKeyboardColor.PRIMARY)
        return keyboard

    def get_cancel_keyboard(self):
        keyboard = VkKeyboard(one_time=False)
        keyboard.add_button("❌ ОТМЕНА", color=VkKeyboardColor.NEGATIVE)
        return keyboard

    def get_list_with_delete_keyboard(self, reminders):
        keyboard = VkKeyboard(one_time=False)

        for r in reminders[:8]:
            keyboard.add_button(f"🗑 УДАЛИТЬ #{r['id']}", color=VkKeyboardColor.NEGATIVE)

        keyboard.add_line()
        keyboard.add_button("🔙 МЕНЮ", color=VkKeyboardColor.PRIMARY)
        keyboard.add_button("➕ НОВОЕ", color=VkKeyboardColor.POSITIVE)

        return keyboard

    def run(self):
        self.check_thread = threading.Thread(target=self.check_reminders, daemon=True)
        self.check_thread.start()

        print(f"✅ Бот версии {VERSION} готов к работе!")
        print(f"📍 Время: {self.get_now().strftime('%d.%m.%Y %H:%M:%S')}")

        while self.running:
            try:
                if self.longpoll is None:
                    print("🔄 Переподключение...")
                    if not self.init_vk_session():
                        time.sleep(5)
                        continue

                for event in self.longpoll.listen():
                    if not self.running:
                        break

                    if event.type == VkBotEventType.MESSAGE_NEW:
                        msg = event.obj.message
                        user_id = msg['from_id']
                        text = msg['text'].strip()
                        print(f"📨 {user_id}: {text}")

                        # Обработка кнопок
                        if text == "➕ НАПОМИНАНИЕ":
                            self.user_states[user_id] = {'step': 'awaiting_datetime'}
                            self.send_message(user_id,
                                "⏰ Введите дату и время:\n\n"
                                "• 19:00 (сегодня)\n"
                                "• завтра в 10:00\n"
                                "• 3 мая в 19:00\n\n"
                                "ОТМЕНА - отменить",
                                self.get_cancel_keyboard())
                            continue

                        elif text == "📋 МОИ НАПОМИНАНИЯ":
                            reminders = self.get_user_reminders(user_id)
                            if not reminders:
                                self.send_message(user_id, "📭 У вас нет напоминаний.\n\n➕ НАПОМИНАНИЕ - чтобы создать", self.get_main_keyboard())
                            else:
                                msg_text = "📋 ВАШИ НАПОМИНАНИЯ:\n\n"
                                for r in reminders:
                                    msg_text += f"🔹 #{r['id']} | {r['date']} в {r['time']}\n   📝 {r['text']}\n\n"
                                msg_text += "👇 Нажмите на кнопку с номером для удаления"
                                self.send_message(user_id, msg_text, self.get_list_with_delete_keyboard(reminders))
                            continue

                        elif text.startswith("🗑 УДАЛИТЬ #"):
                            try:
                                reminder_id = int(text.split("#")[1])
                                if self.delete_reminder(user_id, reminder_id):
                                    self.send_message(user_id, f"✅ Напоминание #{reminder_id} удалено!", self.get_main_keyboard())
                                else:
                                    self.send_message(user_id, f"❌ Напоминание #{reminder_id} не найдено", self.get_main_keyboard())
                            except:
                                self.send_message(user_id, "❌ Ошибка удаления", self.get_main_keyboard())
                            continue

                        elif text == "❓ ПОМОЩЬ":
                            help_message = (
                                "📖 ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ\n"
                                "─────────────────────────────\n\n"
                                "Что умеет бот:\n"
                                "• Создавать напоминания с датой и временем\n"
                                "• Присылать уведомления в нужное время\n"
                                "• Показывать список ваших напоминаний\n"
                                "• Удалять ненужные напоминания\n"
                                "• Принимать обращения к администратору\n\n"
                                "Форматы даты и времени:\n"
                                "• 19:00 — сегодня в 19:00\n"
                                "• завтра в 10:00 — завтра в 10 утра\n"
                                "• 3 мая в 19:00 — 3 мая в 19:00\n\n"
                                "Часовой пояс: Новосибирск (UTC+7)\n"
                                "Если время прошло — напомню завтра!\n\n"
                                "Кнопки меню:\n"
                                "• НАПОМИНАНИЕ — создать новое\n"
                                "• МОИ НАПОМИНАНИЯ — посмотреть и удалить\n"
                                "• ПОДДЕРЖКА — написать администратору\n"
                                "• ПОДПИСАТЬСЯ — на новости\n"
                                "• НОВОСТИ — обновления бота\n\n"
                                "Просто нажмите кнопку и следуйте инструкциям!"
                            )
                            self.send_message(user_id, help_message, self.get_main_keyboard())
                            continue

                        elif text == "✍️ ПОДДЕРЖКА":
                            self.user_states[user_id] = {'step': 'awaiting_feedback'}
                            self.send_message(user_id, 
                                "✍️ Напишите ваше сообщение:\n\n"
                                "Жалобы, пожелания, предложения — всё рассмотрим!\n\n"
                                "ОТМЕНА - отправить обращение",
                                self.get_cancel_keyboard())
                            continue

                        elif text == "📢 ПОДПИСАТЬСЯ":
                            self.send_message(user_id, 
                                "🔔 БУДЬТЕ В КУРСЕ!\n\n"
                                "Подпишитесь на наше сообщество, чтобы первыми узнавать о:\n"
                                "• Новых функциях бота\n"
                                "• Важных обновлениях\n"
                                "• Анонсах\n\n"
                                "👇 Нажмите на кнопку ниже!",
                                self.get_subscribe_keyboard())
                            continue

                        elif text == "📰 НОВОСТИ":
                            news_message = (
                                "📢 ИСТОРИЯ ОБНОВЛЕНИЙ БОТА\n"
                                "─────────────────────────────\n\n"
                                f"Версия {VERSION} — ТЕКУЩАЯ\n"
                                "  • Улучшенный дизайн ответов\n"
                                "  • Исправлена кнопка подписки\n"
                                "  • Чистое форматирование\n\n"
                                "В ПЛАНАХ:\n"
                                "  • Повторяющиеся напоминания\n"
                                "  • Ежедневный отчёт\n"
                                "  • Интеграция с календарём\n\n"
                                "Есть идеи? Жми ПОДДЕРЖКА!"
                            )
                            self.send_message(user_id, news_message, self.get_main_keyboard())
                            continue

                        elif text in ["🔙 МЕНЮ", "🔙 ГЛАВНОЕ МЕНЮ", "❌ ОТМЕНА"]:
                            if user_id in self.user_states:
                                del self.user_states[user_id]
                            self.send_message(user_id, "ГЛАВНОЕ МЕНЮ\n\nВыберите действие:", self.get_main_keyboard())
                            continue

                        elif text in ["обновление", "обновить", "обнова", "апдейт", "update"]:
                            update_message = (
                                f"🔄 ТЕКУЩАЯ ВЕРСИЯ: {VERSION}\n"
                                "─────────────────────────────\n\n"
                                "Новое в версии 2.5:\n"
                                "  • Улучшенный дизайн ответов\n"
                                "  • Исправлена кнопка подписки\n"
                                "  • Чистое форматирование без звёздочек\n"
                                "  • Обновлённая помощь\n\n"
                                "Подробнее — в НОВОСТИ"
                            )
                            self.send_message(user_id, update_message, self.get_main_keyboard())
                            continue

                        # Состояния диалога
                        if user_id in self.user_states:
                            state = self.user_states[user_id]

                            if state['step'] == 'awaiting_datetime':
                                target_datetime = self.parse_datetime(text)
                                if target_datetime:
                                    self.user_states[user_id]['datetime'] = target_datetime
                                    self.user_states[user_id]['step'] = 'awaiting_text'
                                    self.send_message(user_id, 
                                        f"✅ ДАТА ПРИНЯТА\n\n"
                                        f"📅 {target_datetime.strftime('%d.%m.%Y в %H:%M')}\n\n"
                                        f"✏️ Напишите текст напоминания:\n\n"
                                        f"ОТМЕНА - отменить",
                                        self.get_cancel_keyboard())
                                else:
                                    self.send_message(user_id, 
                                        "❌ НЕВЕРНЫЙ ФОРМАТ\n\n"
                                        "Примеры правильного ввода:\n"
                                        "• 19:00\n"
                                        "• завтра в 10:00\n"
                                        "• 3 мая в 19:00\n\n"
                                        "ОТМЕНА - отменить",
                                        self.get_cancel_keyboard())

                            elif state['step'] == 'awaiting_text':
                                reminder = self.add_reminder(user_id, state['datetime'], text)
                                self.send_message(user_id, 
                                    f"✅ НАПОМИНАНИЕ СОЗДАНО!\n\n"
                                    f"📅 {reminder['date']} в {reminder['time']}\n"
                                    f"📝 {text}\n\n"
                                    f"🔔 Я пришлю уведомление вовремя!",
                                    self.get_main_keyboard())
                                del self.user_states[user_id]

                            elif state['step'] == 'awaiting_feedback':
                                feedback = self.add_feedback(user_id, text)
                                self.send_message(user_id, 
                                    f"✅ ОБРАЩЕНИЕ ПРИНЯТО!\n\n"
                                    f"🆔 Номер: #{feedback['id']}\n"
                                    f"📅 {feedback['created_at']}\n\n"
                                    f"Спасибо! Мы рассмотрим его в ближайшее время.",
                                    self.get_main_keyboard())
                                del self.user_states[user_id]
                            continue

                        # Спасибо
                        if any(word in text.lower() for word in ["спасибо", "благодарю", "спс", "пасиб", "thanks"]):
                            thanks_list = [
                                "🤗 Пожалуйста! Рад помочь!",
                                "😊 Обращайся! Всегда на связи!",
                                "👍 Рад помочь! Хорошего дня!",
                                "💫 Всегда пожалуйста!",
                                "🌟 Приятно слышать! Спасибо!",
                                "💖 Пожалуйста! Буду рад помочь снова!"
                            ]
                            self.send_message(user_id, random.choice(thanks_list), self.get_main_keyboard())

                        # Обновления через команду
                        elif any(word in text.lower() for word in ["обновление", "обновить", "обнова", "журнал", "лог", "log", "changes"]):
                            log_message = (
                                f"📋 ЖУРНАЛ ИЗМЕНЕНИЙ\n"
                                "─────────────────────────────\n\n"
                                f"Версия {VERSION} (текущая)\n"
                                "  • Улучшенный дизайн ответов\n"
                                "  • Исправлена кнопка подписки\n"
                                "  • Чистое форматирование\n\n"
                                "Версия 2.3\n"
                                "  • Удаление из списка\n"
                                "  • Кнопка отмены\n\n"
                                "Версия 2.0\n"
                                "  • Новосибирское время\n"
                                "  • Красивые кнопки\n\n"
                                "Полную историю смотри в НОВОСТИ"
                            )
                            self.send_message(user_id, log_message, self.get_main_keyboard())

                        # Приветствие
                        elif any(word in text.lower() for word in ["привет", "начать", "старт"]):
                            self.send_message(user_id, 
                                f"👋 ПРИВЕТ!\n\n"
                                f"Я бот-напоминалочка 🤖\n\n"
                                f"📌 Версия {VERSION}\n"
                                f"🌏 Новосибирское время\n\n"
                                f"❓ Нажмите ПОМОЩЬ для инструкции\n"
                                f"➕ Или создайте напоминание прямо сейчас!",
                                self.get_main_keyboard())

                        else:
                            self.send_message(user_id, 
                                "❓ НЕ ПОНЯЛ КОМАНДУ\n\n"
                                "Нажмите ПОМОЩЬ для инструкции\n"
                                "Или выберите действие из меню 👇",
                                self.get_main_keyboard())

            except Exception as e:
                print(f"❌ Ошибка: {e}")
                self.longpoll = None
                time.sleep(5)


if __name__ == "__main__":
    if not TOKEN:
        print("❌ Ошибка: TOKEN не задан!")
        sys.exit(1)
    bot = ReminderBot(TOKEN, GROUP_ID)
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
        bot.running = False
        sys.exit(0)
