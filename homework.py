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


def check_tokens():
    """Проверяет доступность переменных окружения.
    Если отсутствует хотя бы одна переменная окружения,
    то продолжать работу бота нет смысла.
    """
    assert PRACTICUM_TOKEN is not None
    assert TELEGRAM_TOKEN is not None
    assert TELEGRAM_CHAT_ID is not None


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
        if response.status_code != HTTPStatus.OK:
            raise requests.HTTPError('Эндпоинт недоступен.')
        else:
            if isinstance(response.json(), dict):
                return response.json()
    except requests.RequestException():
        raise requests.RequestException('Другой сбой при запросе к эндпоинту.')


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
        return None
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
        message = (f'Произошла ошибка при отправке сообщения'
                   f' в Телеграмм: {error}')
        logging.error(message)


def main():
    """Основная логика работы бота."""
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = 0
    # int(time.time())

    logging.basicConfig(
        format=('%(asctime)s - %(levelname)s - %(message)s - %(name)s'),
        level=logging.DEBUG,
    )
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler(stream=sys.stdout)
    logger.addHandler(handler)

    step_error_status = {'step_0': True,
                         'step_1': True,
                         'step_2': True,
                         'step_3': True}

    # 0. Проверка переменных среды.
    try:
        check_tokens()
    except Exception as error:
        message = (
            f'Отсутствие обязательных переменных '
            f'окружения во время запуска бота: {error}'
        )
        logging.critical(message)
        # send_message(bot, message)
        step_error_status['step_0'] = False

    while step_error_status['step_0'] is True:
        # Шаг 1. Сделать запрос к API.
        try:
            answer = get_api_answer(timestamp)
            logging.debug('Получен ответ от API')
            step_error_status['step_1'] = True
        except requests.HTTPError as error:
            message = (f'Эндпоинт недоступен: {error}.')
            logging.error(message)
            if step_error_status['step_1'] is True:
                send_message(bot, message)
                step_error_status['step_1'] = False
            time.sleep(RETRY_PERIOD)
            continue
        except requests.RequestException as error:
            message = (f'Другие сбои при запросе к эндпоинту: {error}.')
            logging.error(message)
            if step_error_status['step_1'] is True:
                send_message(bot, message)
                step_error_status['step_1'] = False
            time.sleep(RETRY_PERIOD)
            continue
        except Exception as error:
            message = (f'Другие сбои: {error}.')
            logging.error(message)
            if step_error_status['step_1'] is True:
                send_message(bot, message)
                step_error_status['step_1'] = False
            time.sleep(RETRY_PERIOD)
            continue

        # Шаг 2. Проверить ответ.
        try:
            check_answer = check_response(answer)
            if check_answer is not None:
                logging.debug('Проверка полей прошла успешно,'
                              ' есть обновления.')
                step_error_status['step_2'] = True
            else:
                logging.debug('проверка прошла успешно, с'
                              ' момента предыдущего запроса обновлений нет')
                time.sleep(RETRY_PERIOD)
                continue
        except Exception as error:
            message = (f'Нарушение структуры ответа API: {error}.')
            logging.error(message)
            if step_error_status['step_2'] is True:
                send_message(bot, message)
                step_error_status['step_2'] = False
            time.sleep(RETRY_PERIOD)
            continue

        # Шаг 3. Если есть обновления — получить статус работы из обновления.
        try:
            message = parse_status(check_answer)
            logging.debug(message)
            send_message(bot, message)
            step_error_status['step_3'] = True
        except Exception as error:
            message = (f'Неожиданный статус домашней работы, '
                       f'обнаруженный в ответе API {error}')
            logging.error(message)
            if step_error_status['step_3'] is True:
                send_message(bot, message)
                step_error_status['step_3'] = False
            time.sleep(RETRY_PERIOD)
            continue

        #  После удачного прохождения всех шагов - подождать некоторое время
        # и вернуться на шаг 1.
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
