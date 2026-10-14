# -*- coding: utf-8 -*-
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
import random
import config

def get_random_id():
    return random.randint(1, 2**31)

vk_session = vk_api.VkApi(token=config.VK_TOKEN)
vk = vk_session.get_api()
longpoll = VkLongPoll(vk_session)

def send(uid, text, keyboard=None):
    params = {"user_id": uid, "message": text, "random_id": get_random_id()}
    if keyboard:
        params["keyboard"] = keyboard
    vk.messages.send(**params)

def main_keyboard():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "🏪 Магазины"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "ℹ️ О сервисе"}, "color": "secondary"}],
        ]
    }

def run_vk():
    print("🚀 ВКонтакте запущен")
    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            uid = event.user_id
            text = (event.text or "").strip()

            if text.lower() in ("начать", "start", "/start", "привет"):
                send(uid,
                    f"🌸 Добро пожаловать в {config.SERVICE_NAME}!\n\n"
                    f"🚚 Доставка цветов по городу {config.CITY}\n"
                    f"🕐 Работаем: {config.WORK_HOURS}",
                    main_keyboard())
            elif text == "ℹ️ О сервисе":
                send(uid,
                    f"🌸 {config.SERVICE_NAME}\n📍 {config.CITY}\n"
                    f"🕐 {config.WORK_HOURS}\n📞 {config.SUPPORT_PHONE}\n"
                    f"✈️ {config.SERVICE_VK_TG}")
            else:
                send(uid, "Нажмите /start", main_keyboard())
