import logging
import os
import sys
import time
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN', None)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', None)
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', None)

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_ATTRIBUTES = ('id',
                       'status',
                       'homework_name',
                       'reviewer_comment',
                       'date_updated',
                       'lesson_name')

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    format=('%(asctime)s - %(levelname)s - %(message)s - %(name)s'),
    level=logging.DEBUG,
)


def check_tokens():
    """Проверяет доступность переменных окружения.
    Если отсутствует хотя бы одна переменная окружения,
    то продолжать работу бота нет смысла.
    """
    try:
        if (PRACTICUM_TOKEN is None
                or TELEGRAM_TOKEN is None
                or TELEGRAM_CHAT_ID is None):
            raise LookupError('Проблема с переменными окружения.')
    except Exception as error:
        logging.critical(
            f'Проверка при проверке токенов {error}'
        )
        exit()


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра в функцию передаётся временная метка.
    В случае успешного запроса должна вернуть ответ API,
    приведя его из формата JSON к типам данных Python.
    """
    try:
        response = requests.get(ENDPOINT,
                                headers=HEADERS,
                                params={'from_date': timestamp})
    except requests.RequestException() as error:
        raise requests.HTTPError(
            f'Проблема с запросом к эндпоинту {error}'
        )

    if response.status_code != HTTPStatus.OK:
        raise requests.HTTPError('Код ответа не 200')
    else:
        return response.json()


def check_response(response: dict):
    """Проверяет ответ API на соответствие документации.
    В качестве параметра функция получает ответ API,
    приведённый к типам данных Python. Если в ответе есть сданные
    домашние задания, то проверяет были ли обновления с момента предыдущего
    запроса. Если были, то возвращает последнее домашнее задание.
    """
    if not isinstance(response, dict):
        raise TypeError('Response должен быть dict.')

    if 'homeworks' not in response or 'current_date' not in response:
        raise KeyError('Нехватает ключа в response.')

    if (not isinstance(response['homeworks'], list)
            or not isinstance(response['current_date'], int)):
        raise TypeError('Значения ключей response имеют неправильный тип.')

    if not response['homeworks']:
        raise ValueError('Обновлений нет')
    else:
        for homework in response['homeworks']:
            if not isinstance(homework, dict):
                raise TypeError('Домашнее задание должно иметь тип dict.')
            for homework_attribute in homework:
                if homework_attribute not in HOMEWORK_ATTRIBUTES:
                    raise KeyError('Атрибутивный состав ответа'
                                   ' не соответствует ожиданиям.')
        return response['homeworks'][0]


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра функция получает только один элемент из списка
    домашних работ. В случае успеха функция возвращает подготовленную для
    отправки в Telegram строку, содержащую один из вердиктов словаря
    HOMEWORK_VERDICTS.
    """
    if 'status' not in homework or 'homework_name' not in homework:
        raise KeyError('Атрибуты отсутствует в homework.')
    homework_name = homework['homework_name']
    status = homework['status']
    if status in HOMEWORK_VERDICTS:
        verdict = HOMEWORK_VERDICTS[status]
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    else:
        raise KeyError('Недокументированный статус домашки.')


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )
        logging.debug('Сообщение успешно отправлено в Телеграмм')
    except Exception as error:
        logging.error(f'Ошибка при отправке в Телеграмм {error}')


def main():
    """Основная логика работы бота."""
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler(stream=sys.stdout)
    logger.addHandler(handler)

    check_tokens()
    while True:
        try:
            answer = get_api_answer(timestamp)
            logging.debug('Получен ответ от API')
            check_answer = check_response(answer)
            message = parse_status(check_answer)
            send_message(bot, message)
        except Exception as error:
            message = (f'Проблема: {error}')
            logging.error(message)
            send_message(bot, message)
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
