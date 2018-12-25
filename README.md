# breezart-mqtt
Translator daemon between Breezart vent and MQTT for SmartHome

1. Скопируем файл breezart-mqtt.py в папку /usr/local/bin/
2. Отредактируем параметры подключения в заголовке файла:
- адрес пульта вентиляции в TCP_IP
- активируем пароль в настройках пульта и пропишем в TCP_PASS
3. Настроим подключение к брокеру MQTT - адрес, логин и пароль
4. Настроим запуск сервиса в автоматическом режиме с использованием systemd
- создадим файл /etc/systemd/system/breezart-mqtt.service с содержимым:

    [Unit]
    Description=breezart-mqtt
    After=multi-user.target

    [Service]
    Type=idle
    ExecStart=/usr/bin/python /usr/local/bin/breezart-mqtt.py
    Restart=always

    [Install]
    WantedBy=multi-user.target

- Перезапустим systemd, добавим и запустим наш сервис:

    sudo systemctl daemon-reload
    sudo systemctl enable breezart-mqtt.service
    sudo systemctl start breezart-mqtt.service