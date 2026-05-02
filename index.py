import re
import threading
import time
import random
import os
from datetime import datetime, timedelta
from vk_api import VkApi
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.utils import get_random_id
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import json
import sys

TOKEN = os.environ.get('TOKEN')
GROUP_ID = int(os.environ.get('GROUP_ID', 238286097))
ADMIN_ID = int(os.environ.get('ADMIN_ID', 238286097))
GROUP_LINK = os.environ.get('GROUP_LINK', 'https://vk.com/club238286097')

REMINDERS_FILE = "reminders.json"
FEEDBACK_FILE = "feedback.json"

# Список запрещённых слов
FORBIDDEN_WORDS = [
    'через', 'час', 'минут', 'секунд', 'полчаса', 'полтора', 'суток', 'дней',
    'завтра', 'послезавтра', 'сегодня', 'вчера', 'понедельник', 'вторник',
    'среда', 'четверг', 'пятница', 'суббота', 'воскресенье', 'неделю', 'месяц'
]

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

    def show_startup_message(self):
        """Показать сообщение при запуске бота"""
        print("\n" + "="*60)
        print("🤖 БОТ-НАПОМИНАЛКА ЗАПУЩЕН")
        print("="*60)
        print("📌 Версия: 2.1")
        print("🕐 Время запуска: " + datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
        print("="*60)
        print("\n⚠️ ИЗВИНЕНИЕ И УВЕДОМЛЕНИЕ:")
        print("-"*60)
        print("Уважаемые пользователи, приносим извинения за возможные")
        print("неудобства в работе бота. Мы постоянно работаем над")
        print("улучшением его функционала.")
        print("\n🔧 Последние изменения:")
        print("• Добавлена система обратной связи")
        print("• Исправлена обработка дат и времени")
        print("• Добавлена поддержка формата '3 мая в 19:00'")
        print("• Улучшена стабильность работы")
        print("\n📝 Если бот работает некорректно, используйте кнопку")
        print("   ✍️ Обращение к админу")
        print("="*60 + "\n")

    def init_vk_session(self):
        """Инициализация сессии ВКонтакте"""
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
        """Загрузить напоминания из файла"""
        if os.path.exists(REMINDERS_FILE):
            try:
                with open(REMINDERS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_reminders(self):
        """Сохранить напоминания в файл"""
        try:
            with open(REMINDERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.reminders, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")

    def load_feedbacks(self):
        """Загрузить обращения из файла"""
        if os.path.exists(FEEDBACK_FILE):
            try:
                with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []

    def save_feedbacks(self):
        """Сохранить обращения в файл"""
        try:
            with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.feedbacks, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ Ошибка сохранения обращений: {e}")

    def add_feedback(self, user_id, message):
        """Добавить новое обращение"""
        feedback = {
            "id": len(self.feedbacks) + 1,
            "user_id": user_id,
            "message": message,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "new"
        }
        self.feedbacks.append(feedback)
        self.save_feedbacks()
        
        # Отправляем уведомление админу
        self.notify_admin(feedback)
        
        return feedback

    def notify_admin(self, feedback):
        """Отправить уведомление администратору"""
        try:
            message = f"📨 НОВОЕ ОБРАЩЕНИЕ!\n\n"
            message += f"🆔 ID: {feedback['id']}\n"
            message += f"👤 User ID: {feedback['user_id']}\n"
            message += f"📅 Дата и время: {feedback['created_at']}\n"
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

    def get_feedbacks_list(self, status=None):
        """Получить список обращений (для админа)"""
        if status:
            return [f for f in self.feedbacks if f['status'] == status]
        return self.feedbacks

    def send_message(self, user_id, message, keyboard=None):
        """Отправить сообщение пользователю"""
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

    def validate_datetime_format(self, text):
        """Проверка корректности формата даты и времени"""
        text_lower = text.lower().strip()
        
        for forbidden in FORBIDDEN_WORDS:
            if forbidden in text_lower:
                return False, f"❌ Использование слова '{forbidden}' недопустимо.\n\n✅ Правильные форматы:\n• 3 мая в 19:00\n• 15 мая в 09:30"
        
        pattern = r'^(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+в\s+(\d{1,2}):(\d{2})$'
        match = re.match(pattern, text_lower)
        
        if not match:
            return False, "❌ Неверный формат!\n\n✅ Формат: ДЕНЬ МЕСЯЦ в ЧАС:МИНУТА\nПример: 3 мая в 19:00"
        
        day = int(match.group(1))
        month_name = match.group(2)
        hour = int(match.group(3))
        minute = int(match.group(4))
        
        if hour < 0 or hour > 23:
            return False, "❌ Часы должны быть от 0 до 23"
        if minute < 0 or minute > 59:
            return False, "❌ Минуты должны быть от 0 до 59"
        
        return True, (day, month_name, hour, minute)

    def parse_datetime(self, text):
        """Парсинг даты и времени"""
        text_lower = text.lower().strip()
        pattern = r'^(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+в\s+(\d{1,2}):(\d{2})$'
        match = re.match(pattern, text_lower)
        
        if not match:
            return None
        
        months_ru = {
            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
            'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
            'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
        }
        
        now = datetime.now()
        day = int(match.group(1))
        month_name = match.group(2)
        hour = int(match.group(3))
        minute = int(match.group(4))
        month = months_ru[month_name]
        
        year = now.year
        if month < now.month or (month == now.month and day < now.day):
            year += 1
        elif month == now.month and day == now.day and hour < now.hour:
            year += 1
        elif month == now.month and day == now.day and hour == now.hour and minute <= now.minute:
            year += 1
        
        try:
            return datetime(year, month, day, hour, minute)
        except:
            return None

    def add_reminder(self, user_id, target_datetime, text):
        """Добавить напоминание"""
        user_id_str = str(user_id)
        if user_id_str not in self.reminders:
            self.reminders[user_id_str] = []

        reminder = {
            "id": len(self.reminders[user_id_str]) + 1,
            "datetime": target_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "date": target_datetime.strftime("%d.%m.%Y"),
            "time": target_datetime.strftime("%H:%M"),
            "text": text,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        """Поток для проверки и отправки напоминаний"""
        print("🔄 Запущен поток проверки напоминаний...")
        while self.running:
            try:
                current_datetime = datetime.now()
                current_datetime_str = current_datetime.strftime("%Y-%m-%d %H:%M")

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
                            self.send_message(user_id, "⏰ Введите дату в формате: 3 мая в 19:00", self.get_main_keyboard())
                            continue

                        elif text == "📋 Список":
                            reminders = self.get_user_reminders(user_id)
                            if not reminders:
                                self.send_message(user_id, "📭 Нет напоминаний", self.get_main_keyboard())
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
                            self.send_message(user_id, "✍️ Напишите ваше обращение:", self.get_cancel_keyboard())
                            continue

                        elif text == "❌ Отмена":
                            if user_id in self.user_states:
                                del self.user_states[user_id]
                            self.send_message(user_id, "✅ Отменено", self.get_main_keyboard())
                            continue

                        elif text == "📢 Подписаться":
                            self.send_message(user_id, "🔔 Подпишитесь!", self.get_subscribe_keyboard())
                            continue

                        elif text == "🔙 Назад":
                            self.send_message(user_id, "Главное меню:", self.get_main_keyboard())
                            continue

                        # Состояния диалога
                        if user_id in self.user_states:
                            state = self.user_states[user_id]

                            if state['step'] == 'awaiting_datetime':
                                is_valid, result = self.validate_datetime_format(text)
                                if is_valid:
                                    target_datetime = self.parse_datetime(text)
                                    if target_datetime:
                                        self.user_states[user_id]['datetime'] = target_datetime
                                        self.user_states[user_id]['step'] = 'awaiting_text'
                                        self.send_message(user_id, f"✅ {target_datetime.strftime('%d.%m.%Y в %H:%M')}\n✏️ Текст:", self.get_main_keyboard())
                                    else:
                                        self.send_message(user_id, "❌ Дата уже прошла!", self.get_main_keyboard())
                                else:
                                    self.send_message(user_id, result, self.get_main_keyboard())

                            elif state['step'] == 'awaiting_text':
                                reminder = self.add_reminder(user_id, state['datetime'], text)
                                self.send_message(user_id, f"✅ Создано!\n📅 {reminder['date']} в {reminder['time']}\n📝 {text}", self.get_main_keyboard())
                                del self.user_states[user_id]

                            elif state['step'] == 'awaiting_feedback':
                                feedback = self.add_feedback(user_id, text)
                                self.send_message(user_id, f"✅ Обращение #{feedback['id']} принято!\n📅 {feedback['created_at']}", self.get_main_keyboard())
                                del self.user_states[user_id]

                            elif state['step'] == 'awaiting_delete_id':
                                try:
                                    reminder_id = int(text)
                                    if self.delete_reminder(user_id, reminder_id):
                                        self.send_message(user_id, f"✅ Напоминание #{reminder_id} отменено!", self.get_main_keyboard())
                                    else:
                                        self.send_message(user_id, f"❌ Напоминание #{reminder_id} не найдено", self.get_main_keyboard())
                                except:
                                    self.send_message(user_id, "❌ Введите число", self.get_main_keyboard())
                                del self.user_states[user_id]
                            continue

                        # Спасибо
                        if any(word in text.lower() for word in ["спасибо", "благодарю", "спс"]):
                            thanks = ["🤗 Пожалуйста!", "😊 Обращайся!", "👍 Рад помочь!"]
                            self.send_message(user_id, random.choice(thanks), self.get_main_keyboard())

                        # Привет
                        elif any(word in text.lower() for word in ["привет", "начать", "старт"]):
                            self.send_message(user_id, "👋 Привет! Используй кнопки меню 👇", self.get_main_keyboard())

                        else:
                            self.send_message(user_id, "❓ Не понял. Используй кнопки 👇", self.get_main_keyboard())
                            
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
