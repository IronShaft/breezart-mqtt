# breezart-mqtt
Сервис-транслятор интерфейса вентиляций Breezart с подключением к брокеру MQTT для систем
умного дома (MajorDoMo, Domoticz, OpenHAB 2 и т.д.)

## Установка и запуск

1. Скопируем файл breezart-mqtt.py в папку /usr/local/bin/
2. Отредактируем параметры подключения в заголовке файла:
- адрес пульта вентиляции в TCP_IP
- активируем пароль в настройках пульта и пропишем в TCP_PASS
3. Настроим подключение к брокеру MQTT - адрес, логин и пароль
4. Настроим запуск сервиса в автоматическом режиме с использованием systemd
- создадим файл /etc/systemd/system/breezart-mqtt.service с содержимым:

```
[Unit]
Description=breezart-mqtt
After=multi-user.target

[Service]
Type=idle
ExecStart=/usr/bin/python /usr/local/bin/breezart-mqtt.py
Restart=always

[Install]
WantedBy=multi-user.target
```

- Перезапустим systemd, добавим и запустим наш сервис:

```
sudo systemctl daemon-reload
sudo systemctl enable breezart-mqtt.service
sudo systemctl start breezart-mqtt.service
```

## MQTT Topic для получения состояния

```
breezart/vent/STATUS - состояние вентиляции
breezart/vent/LWT - Last Will and Testament
```

## MQTT Topic для изменения параметров

```
breezart/vent/POWER - "ON"/"OFF", включение/выключении вентиляции
breezart/vent/SPEED - десятичное число, установка скорости вентиляции
breezart/vent/TEMPERATURE - десятичное число, установка температуры воздуха
breezart/vent/HUMIDITY - десятичное число, установка относительной влажности воздуха (при наличии увлажнителя)
breezart/vent/COMFORT - "ON"/"OFF", включение/выключение режима КОМФОРТ
breezart/vent/MODE - десятичное число, установка режима работы вентиляции
    1 - "Обогрев"
    2 - "Охлаждение" - при наличии охладителя
    3 - "Авто"
    4 - "Вентиляция" - без нагрева и охлаждения
breezart/vent/SCENE - "ON"/"OFF"/десятичное число, включение/выключение режима сценариев по таймеру, номер сценария (от 1 до 8)
```

## Контроль работы

Сообщения о работе сервиса записываются в системный журнал (/var/log/messages)

## Известные проблемы

- недостаточно оттестировано :)
- не реализована поддержка VAV
- не реализована установка времени на вентиляции
- не реализовано получение данных с сенсоров
- не реализовано получение настроек сценариев
