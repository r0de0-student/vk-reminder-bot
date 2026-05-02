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
ADMIN_ID = int(os.environ.get('ADMIN_ID', 540139562))
GROUP_LINK = os.environ.get('GROUP_LINK', 'https://vk.com/club238286097')

REMINDERS_FILE = "reminders.json"
FEEDBACK_FILE = "feedback.json"

# Устанавливаем часовой пояс (Москва)
TIMEZONE = pytz.timezone('Europe/Moscow')


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
        self.reconnect_attempts = 0
        self.init_vk_session()
        self.show_startup_message()

    def get_now(self):
        """Получить текущее время в московском часовом поясе"""
        return datetime.now(TIMEZONE)

    def show_startup_message(self):
        """Показать сообщение при запуске бота"""
        now = self.get_now()
        print("\n" + "=" * 60)
        print("🤖 БОТ-НАПОМИНАЛКА ЗАПУЩЕН")
        print("=" * 60)
        print("📌 Версия: 2.2")
        print("🕐 Время запуска (МСК): " + now.strftime("%d.%m.%Y %H:%M:%S"))
        print("=" * 60)
        print("\n⚠️ ИЗВИНЕНИЕ И УВЕДОМЛЕНИЕ:")
        print("-" * 60)
        print("Уважаемые пользователи, приносим извинения за возможные")
        print("неудобства в работе бота. Мы постоянно работаем над")
        print("улучшением его функционала.")
        print("\n🔧 Последние изменения:")
        print("• Исправлен часовой пояс (Москва)")
        print("• Исправлено определение времени (сегодня/завтра)")
        print("• Добавлено красивое приветствие")
        print("=" * 60 + "\n")

    def init_vk_session(self):
        try:
            self.vk_session = VkApi(token=self.token)
            self.vk = self.vk_session.get_api()
            self.longpoll = VkBotLongPoll(self.vk_session, self.group_id, wait=25)
            print("✅ Сессия ВК успешно создана")
            self.reconnect_attempts = 0
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
            message = f"📨 НОВОЕ ОБРАЩЕНИЕ!\n\n"
            message += f"🆔 ID: {feedback['id']}\n"
            message += f"👤 User ID: {feedback['user_id']}\n"
            message += f"📅 Дата и время (МСК): {feedback['created_at']}\n"
            message += f"📝 Сообщение:\n{feedback['message']}\n\n"
            message += f"📊 Статус: {feedback['status']}"

            self.vk.messages.send(
                user_id=ADMIN_ID,
                message=message,
                random_id=get_random_id()
            )
            print(f"✅ Уведомление отправлено админу о обращении #{feedback['id']}")
        except Exception as e:
            print(f"❌ Ошибка отправки уведомления админу: {e}")

    def send_message(self, user_id, message, keyboard=None):
        try:
            self.vk.messages.send(
                user_id=user_id,
                message=message,
                random_id=get_random_id(),
                keyboard=keyboard.get_keyboard() if keyboard else None
            )
            print(f"✅ Ответ для {user_id}: {message[:50]}...")
            return True
        except Exception as e:
            print(f"❌ Ошибка отправки: {e}")
            return False

    def parse_datetime(self, text):
        """Парсинг даты и времени. Если только время — сегодня. Если время прошло — завтра."""
        text_lower = text.lower().strip()

        # Проверка на "сегодня"/"завтра"
        is_tomorrow = False
        if "завтра" in text_lower:
            is_tomorrow = True
            text_lower = text_lower.replace("завтра", "").strip()

        # Паттерн с датой: "3 мая в 19:00" или "3 мая 19:00"
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

        # Только время: "19:00" или "в 19:00"
        pattern_time = r'(\d{1,2}):(\d{2})'
        match = re.search(pattern_time, text_lower)

        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))

            if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                return None

            # Сегодня в это время
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # Если время уже прошло сегодня или указано "завтра" — берём завтра
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
        print("🔄 Запущен поток проверки напоминаний...")
        while self.running:
            try:
                current = self.get_now()
                current_datetime_str = current.strftime("%Y-%m-%d %H:%M")

                for user_id_str, user_reminders in self.reminders.items():
                    for reminder in user_reminders[:]:
                        reminder_datetime_str = reminder["datetime"][:16]

                        if reminder_datetime_str == current_datetime_str:
                            message = f"🔔 НАПОМИНАНИЕ!\n\n📝 {reminder['text']}\n\n📅 {reminder['date']} в {reminder['time']}"
                            self.send_message(int(user_id_str), message)
                            user_reminders.remove(reminder)
                            self.save_reminders()
                            print(f"✅ Отправлено напоминание пользователю {user_id_str}")

                time.sleep(30)
            except Exception as e:
                print(f"❌ Ошибка в потоке проверки: {e}")
                time.sleep(60)

    def get_main_keyboard(self):
        keyboard = VkKeyboard(one_time=False)
        keyboard.add_button("➕ Новое напоминание", color=VkKeyboardColor.POSITIVE)
        keyboard.add_button("📋 Список", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("❌ Отменить напоминание", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_button("✍️ Обращение к админу", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()
        keyboard.add_button("📢 Подписаться", color=VkKeyboardColor.SECONDARY)
        return keyboard

    def get_subscribe_keyboard(self):
        keyboard = VkKeyboard(one_time=False)
        keyboard.add_openlink_button("🔔 Подписаться на сообщество", GROUP_LINK)
        keyboard.add_button("🔙 Назад", color=VkKeyboardColor.PRIMARY)
        return keyboard

    def get_cancel_keyboard(self):
        keyboard = VkKeyboard(one_time=False)
        keyboard.add_button("❌ Отмена", color=VkKeyboardColor.NEGATIVE)
        return keyboard

    def run(self):
        self.check_thread = threading.Thread(target=self.check_reminders, daemon=True)
        self.check_thread.start()

        print("✅ Бот готов к работе! Ожидание сообщений...")
        print(f"📍 Текущее время (МСК): {self.get_now().strftime('%d.%m.%Y %H:%M:%S')}")

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

                        # Кнопки
                        if text == "➕ Новое напоминание":
                            self.user_states[user_id] = {'step': 'awaiting_datetime'}
                            self.send_message(user_id,
                                              "⏰ Введите дату и время в форматах:\n\n"
                                              "• 19:00 (сегодня в 19:00)\n"
                                              "• завтра в 10:00\n"
                                              "• 3 мая в 19:00\n\n"
                                              "Если время уже прошло сегодня, напомню завтра!",
                                              self.get_main_keyboard())
                            continue

                        elif text == "📋 Список":
                            reminders = self.get_user_reminders(user_id)
                            if not reminders:
                                self.send_message(user_id, "📭 У вас нет активных напоминаний.",
                                                  self.get_main_keyboard())
                            else:
                                msg_text = "📋 Ваши напоминания:\n\n"
                                for r in reminders:
                                    msg_text += f"🔹 #{r['id']} {r['date']} в {r['time']} — {r['text']}\n"
                                self.send_message(user_id, msg_text, self.get_main_keyboard())
                            continue

                        elif text == "❌ Отменить напоминание":
                            self.user_states[user_id] = {'step': 'awaiting_delete_id'}
                            self.send_message(user_id, "🗑 Введите ID напоминания:", self.get_main_keyboard())
                            continue

                        elif text == "✍️ Обращение к админу":
                            self.user_states[user_id] = {'step': 'awaiting_feedback'}
                            self.send_message(user_id, "✍️ Напишите ваше обращение, жалобу или пожелание:",
                                              self.get_cancel_keyboard())
                            continue

                        elif text == "❌ Отмена":
                            if user_id in self.user_states:
                                del self.user_states[user_id]
                            self.send_message(user_id, "✅ Действие отменено", self.get_main_keyboard())
                            continue

                        elif text == "📢 Подписаться":
                            self.send_message(user_id, "🔔 Подпишитесь на наши обновления! 👇",
                                              self.get_subscribe_keyboard())
                            continue

                        elif text == "🔙 Назад":
                            self.send_message(user_id, "Главное меню:", self.get_main_keyboard())
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
                                                      f"✅ {target_datetime.strftime('%d.%m.%Y в %H:%M')}\n\n✏️ Теперь напишите текст напоминания:",
                                                      self.get_main_keyboard())
                                else:
                                    self.send_message(user_id,
                                                      "❌ Не понял дату и время.\n\nПримеры:\n• 19:00\n• завтра в 10:00\n• 3 мая в 19:00",
                                                      self.get_main_keyboard())

                            elif state['step'] == 'awaiting_text':
                                reminder = self.add_reminder(user_id, state['datetime'], text)
                                self.send_message(user_id,
                                                  f"✅ Напоминание создано!\n\n"
                                                  f"📅 {reminder['date']} в {reminder['time']}\n"
                                                  f"📝 {text}\n\n"
                                                  f"🔔 Я пришлю уведомление в указанное время!",
                                                  self.get_main_keyboard())
                                del self.user_states[user_id]

                            elif state['step'] == 'awaiting_feedback':
                                feedback = self.add_feedback(user_id, text)
                                self.send_message(user_id,
                                                  f"✅ Ваше обращение принято!\n\n"
                                                  f"🆔 Номер: #{feedback['id']}\n"
                                                  f"📅 {feedback['created_at']} (МСК)\n\n"
                                                  f"Спасибо! Мы рассмотрим его в ближайшее время.",
                                                  self.get_main_keyboard())
                                del self.user_states[user_id]

                            elif state['step'] == 'awaiting_delete_id':
                                try:
                                    reminder_id = int(text)
                                    if self.delete_reminder(user_id, reminder_id):
                                        self.send_message(user_id, f"✅ Напоминание #{reminder_id} отменено!",
                                                          self.get_main_keyboard())
                                    else:
                                        self.send_message(user_id, f"❌ Напоминание #{reminder_id} не найдено",
                                                          self.get_main_keyboard())
                                except:
                                    self.send_message(user_id, "❌ Введите ID (только число)", self.get_main_keyboard())
                                del self.user_states[user_id]
                            continue

                        # Спасибо
                        if any(word in text.lower() for word in ["спасибо", "благодарю", "спс", "пасиб"]):
                            thanks = ["🤗 Пожалуйста! Всегда рад помочь!", "😊 Обращайся!", "👍 Рад помочь!"]
                            self.send_message(user_id, random.choice(thanks), self.get_main_keyboard())

                        # Приветствие
                        elif any(word in text.lower() for word in
                                 ["привет", "начать", "старт", "здравствуй", "добрый день"]):
                            self.send_message(user_id,
                                              "👋 Привет! Я бот-напоминалка!\n\n"
                                              "📌 **Что я умею:**\n"
                                              "• Создавать напоминания с датой и временем\n"
                                              "• Присылать уведомления в нужное время\n"
                                              "• Показывать список ваших напоминаний\n"
                                              "• Отменять ненужные напоминания\n"
                                              "• Принимать обращения к администратору\n\n"
                                              "📅 **Форматы даты и времени:**\n"
                                              "• `19:00` — сегодня в 19:00\n"
                                              "• `завтра в 10:00` — завтра в 10 утра\n"
                                              "• `3 мая в 19:00` — 3 мая в 19:00\n\n"
                                              "⏰ **Важно:** Все даты и время в **Московском времени (МСК)**\n\n"
                                              "🔹 **Чтобы начать, нажмите:**\n"
                                              "   ➕ Новое напоминание\n\n"
                                              "🔹 **Другие кнопки:**\n"
                                              "   📋 Список — посмотреть все напоминания\n"
                                              "   ❌ Отменить — удалить напоминание по ID\n"
                                              "   ✍️ Обращение к админу — написать разработчику\n"
                                              "   📢 Подписаться — быть в курсе обновлений",
                                              self.get_main_keyboard())

                        else:
                            self.send_message(user_id,
                                              "❓ Я не понял команду.\n\n"
                                              "Используйте кнопки меню 👇\n"
                                              "Или напишите «привет» для подробной инструкции.",
                                              self.get_main_keyboard())

            except Exception as e:
                print(f"❌ Ошибка: {e}")
                self.longpoll = None
                time.sleep(5)


if __name__ == "__main__":
    if not TOKEN:
        print("❌ Ошибка: TOKEN не задан в переменных окружения!")
        sys.exit(1)
    bot = ReminderBot(TOKEN, GROUP_ID)
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
        bot.running = False
        sys.exit(0)