import logging
import os
import sys
import time
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot

from exceptions import AnswerCodeError

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
    tokens = (('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
              ('TELEGRAM_TOKEN', TELEGRAM_TOKEN),
              ('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID))
    check_result = True
    for token in tokens:
        if not token[1]:
            logging.critical(f'Отсутствует токен {token[0]}')
            check_result = False
    if not check_result:
        raise LookupError('Проверьте доступность переменных окружения')


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра в функцию передаётся временная метка.
    В случае успешного запроса должна вернуть ответ API,
    приведя его из формата JSON к типам данных Python.
    """
    request_get_args = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp}
    }
    try:
        logging.debug(
            f'Отправляем запрос к url={request_get_args["url"]}'
            f' c headers={request_get_args["headers"]}'
            f' и params={request_get_args["params"]}'
        )
        response = requests.get(
            url=request_get_args['url'],
            headers=request_get_args['headers'],
            params=request_get_args['params']
        )
    except requests.RequestException as error:
        raise ConnectionError(
            f'Проблема с запросом к url={request_get_args["url"]}'
            f' c headers={request_get_args["headers"]}'
            f' и params={request_get_args["params"]}: {error}'
        )

    if response.status_code != HTTPStatus.OK:
        raise AnswerCodeError(
            f'Ошибка запроса: status_code {response.status_code},'
            f' reason {response.reason},'
            # f' text {response.text},'
            f' url {response.url}'
        )
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

    if 'homeworks' not in response:
        raise KeyError('Отсутствуют ожидаемые ключи в response')

    homeworks = response['homeworks']

    if not isinstance(homeworks, list):
        raise TypeError('Значения ключей response имеют неправильный тип')

    return homeworks


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
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неожиданно принятое значение: {status}')
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )
    except Exception as error:
        logging.error(f'Ошибка при отправке в Телеграмм {error}')
        return False
    logging.debug(f'Сообщение успешно отправлено в Телеграмм: {message}')
    return True


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    logging.basicConfig(
        format=('%(asctime)s - %(levelname)s - %(message)s'
                ' - %(name)s - %(lineno)d'),
        level=logging.DEBUG,
        handlers=(logging.StreamHandler(sys.stdout),
                  logging.FileHandler(__file__ + '.log', encoding='UTF-8'))
    )
    old_statuses_of_homeworks = {}
    while True:
        try:
            answer = get_api_answer(timestamp)
            logging.debug('Получен ответ от API')
            homeworks = check_response(answer)
            if not homeworks:
                logging.info('Домашних заданий нет')
                continue
            for homework in homeworks:
                message = parse_status(homework)
                name = homework['homework_name']
                status = homework['status']
                if ((name in old_statuses_of_homeworks
                        and status != old_statuses_of_homeworks[name])
                        or (name not in old_statuses_of_homeworks)):
                    send_message(bot, message)
                old_statuses_of_homeworks[name] = status
        except Exception as error:
            message = (f'{error}')
            logging.error(message)
            send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
