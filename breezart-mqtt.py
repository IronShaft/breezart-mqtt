#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = "IronShaft"
__license__ = "GPL"
__version__ = "1.0.1"

# Warning! VAV not supported!

'''
Roadmap:
1. Add VAV support
2. Add sensors stat reading
3. Add scenes parameters reading
4. Add vent datetime sync
5. Testing and fix bugs :)
'''

import sys
import daemon
import json
import socket
import syslog
import time
import threading
import paho.mqtt.client as mqtt

# define the TCP conection to the vent
TCP_IP = '192.168.X.X'
TCP_PORT = 1560
# password for vent
TCP_PASS = 12345
BUFFER_SIZE = 128
# interval auto requests unit state, sec
INTERVAL = 60

# define the MQTT connection for communication with openHAB
BROKER = '127.0.0.1'
USERNAME = 'mqtt'
PASSWORD='password'
# prefix of MQTT topics
PREFIX = 'breezart/vent'
# string or None for auto generate
CLIENT_ID = 'BreezartVent'

# global vars
temperature_min = 5
temperature_max = 45
speed_min = 1
speed_max = 10
humidity_min = 0
humidity_max = 100
is_humidifier = False
is_cooler = False
is_auto = False
is_vav = False
is_regpressvav = False
is_sceneblock = False
is_powerblock = False

timer = None
s = None

def on_connect_mqtt(client, userdata, flags, rc):
    client.publish(PREFIX + '/LWT', 'Online', 0, True)
    client.subscribe(PREFIX + '/POWER', 0)
    client.subscribe(PREFIX + '/SPEED', 0)
    client.subscribe(PREFIX + '/TEMPERATURE', 0)
    client.subscribe(PREFIX + '/HUMIDITY', 0)
    client.subscribe(PREFIX + '/COMFORT', 0)
    client.subscribe(PREFIX + '/MODE', 0)
    client.subscribe(PREFIX + '/SCENE', 0)
    client.message_callback_add(PREFIX + '/POWER', on_power_message)
    client.message_callback_add(PREFIX + '/SPEED', on_speed_message)
    client.message_callback_add(PREFIX + '/TEMPERATURE', on_temperature_message)
    client.message_callback_add(PREFIX + '/HUMIDITY', on_humidity_message)
    client.message_callback_add(PREFIX + '/COMFORT', on_comfort_message)
    client.message_callback_add(PREFIX + '/MODE', on_mode_message)
    client.message_callback_add(PREFIX + '/SCENE', on_scene_message)

def on_power_message(client, userdata, message):
    '''
    Код запроса клиента: VWPwr_Pass_X
    Запрос на изменение состояние (включения / отключения) установки
    Описание переменных X = 11 – Включить питание, X = 10 – Отключить питание.
    Код ответа при корректном запросе ОК_VWPwr_X , где X – переданное значение (10 или 11)
    '''
    if is_powerblock:
        syslog.syslog(syslog.LOG_ERR, 'Can\'t change power state, power is blocked')
        return
    if message.payload.decode('utf-8').upper() not in ('ON', 'OFF'):
        syslog.syslog(syslog.LOG_ERR, 'Value for power (ON/OFF) incorrect: {0}'.format(message.payload.decode('utf-8')))
        return
    global s
    global timer
    mode = 10 if message.payload.decode('utf-8').upper() == "OFF" else 11
    request = '{0}_{1:2X}_{2:X}'.format('VWPwr', TCP_PASS, mode)
    s.settimeout(5.0)
    s.send(request)
    data = str( s.recv(BUFFER_SIZE) )
    if data != 'OK_VWPwr_{0:X}'.format(mode):
        syslog.syslog(syslog.LOG_ERR, 'Can\'t change power state: {0}'.format(mode))
    else:
        if timer: timer.cancel()
        time.sleep(0.5)
        get_vent_status()

def on_speed_message(client, userdata, message):
    '''
    Код запроса клиента: VWSpd_Pass_SpeedTarget
    Запрос для изменения заданной скорости вентилятора.
    Описание переменных:
        SpeedTarget – заданная скорость (от SpeedMin до SpeedMax)
    '''
    try:
        level = int(message.payload.decode('utf-8'))
    except ValueError:
        syslog.syslog(syslog.LOG_ERR, 'Incorrect value for speed: {0}'.format(message.payload.decode('utf-8')))
        return
    if level not in range(speed_min, speed_max+1):
        syslog.syslog(syslog.LOG_ERR, 'Value for speed out of range ({0}-{1}): {2}'.format(speed_min, speed_max, level))
        return
    if is_vav and not is_regpressvav:
        syslog.syslog(syslog.LOG_ERR, 'Can\'t set speed, VAV activated and pressure regulation not activated.')
        return
    global s
    global timer
    request = '{0}_{1:2X}_{2:X}'.format('VWSpd', TCP_PASS, level)
    s.settimeout(5.0)
    s.send(request)
    data = str( s.recv(BUFFER_SIZE) )
    if data != 'OK_VWSpd_{0:X}'.format(level):
        syslog.syslog(syslog.LOG_ERR, 'Can\'t set speed level: {0}'.format(level))
    else:
        if timer: timer.cancel()
        time.sleep(0.5)
        get_vent_status()

def on_temperature_message(client, userdata, message):
    '''
    Код запроса клиента: VWTmp_Pass_TempTarget
    Запрос для изменения заданной температуры
    Описание переменных:
        TempTarget – заданная температура (от TempMin до TempMax)
    '''
    try:
        level = int(message.payload.decode('utf-8'))
    except ValueError:
        syslog.syslog(syslog.LOG_ERR, 'Incorrect value for temperature: {0}'.format(message.payload.decode('utf-8')))
        return
    if level not in range(temperature_min, temperature_max+1):
        syslog.syslog(syslog.LOG_ERR, 'Value for temperature out of range ({0}-{1}): {2}'.format(temperature_min, temperature_max, level))
        return
    global s
    global timer
    request = '{0}_{1:2X}_{2:X}'.format('VWTmp', TCP_PASS, level)
    s.settimeout(5.0)
    s.send(request)
    data = str( s.recv(BUFFER_SIZE) )
    if data != 'OK_VWTmp_{0:X}'.format(level):
        syslog.syslog(syslog.LOG_ERR, 'Can\'t set temperature level: {0}'.format(level))
    else:
        if timer: timer.cancel()
        time.sleep(0.5)
        get_vent_status()

def on_humidity_message(client, userdata, message):
    '''
    Код запроса клиента: VWHum_Pass_HumTarget
    Запрос для заданной влажности. Запрос разрешен только если IsHumid == 1
    Описание переменных:
        HumTarget – заданная влажность (от HumMin до HumMax)
    '''
    if not is_humidifier:
        syslog.syslog(syslog.LOG_ERR, 'Can\'t set humidity, humidifier not found')
        return
    try:
        level = int(message.payload.decode('utf-8'))
    except ValueError:
        syslog.syslog(syslog.LOG_ERR, 'Incorrect value for humidity: {0}'.format(message.payload.decode('utf-8')))
        return
    if level not in range(humidity_min, humidity_max+1):
        syslog.syslog(syslog.LOG_ERR, 'Value for humidity out of range ({0}-{1}): {2}'.format(humidity_min, humidity_max, level))
        return
    global s
    global timer
    request = '{0}_{1:2X}_{2:X}'.format('VWHum', TCP_PASS, level)
    s.settimeout(5.0)
    s.send(request)
    data = str( s.recv(BUFFER_SIZE) )
    if data != 'OK_VWHum_{0:X}'.format(level):
        syslog.syslog(syslog.LOG_ERR, 'Can\'t set humidity level: {0}'.format(level))
    else:
        if timer: timer.cancel()
        time.sleep(0.5)
        get_vent_status()

def on_comfort_message(client, userdata, message):
    '''
    Код запроса клиента: VWFtr_Pass_bitFeature
    Запрос на изменение режима работы и вкл. / откл. функций
    Описание переменных:
        bitFeature:
            Bit 6-5 – Комфорт:
                1 – Включено
                2 – Отключено
                0 -  без изменений.
    '''
    if message.payload.decode('utf-8').upper() not in ('ON', 'OFF'):
        return
    mode = 1 if message.payload.decode('utf-8').upper() == 'ON' else 2
    global s
    global timer
    request = '{0}_{1:2X}_{2:X}'.format('VWFtr', TCP_PASS, mode << 5)
    s.settimeout(5.0)
    s.send(request)
    data = str( s.recv(BUFFER_SIZE) )
    if data != 'OK_VWFtr_{0:X}'.format(mode << 5):
        syslog.syslog(syslog.LOG_ERR, 'Can\'t change comfort mode: {0}'.format(mode))
    else:
        if timer: timer.cancel()
        time.sleep(0.5)
        get_vent_status()

def on_mode_message(client, userdata, message):
    '''
    Код запроса клиента: VWFtr_Pass_bitFeature
    Запрос на изменение режима работы и вкл. / откл. функций
    Описание переменных:
        bitFeature:
            Bit 2-0 – ModeSet - режим работы:
                1 – Обогрев
                2 – Охлаждение
                3 – Авто
                4 – Отключено (без обогрева и охлаждения)
                0 – режим остается без изменений.
    '''
    try:
        mode = int(message.payload.decode('utf-8'))
    except ValueError:
        syslog.syslog(syslog.LOG_ERR, 'Incorrect value for vent mode: {0}'.format(message.payload.decode('utf-8')))
        return
    if mode == 2 and not is_cooler:
        syslog.syslog(syslog.LOG_ERR, 'Can\'t change vent mode, cooler is not found')
        return
    if mode == 3 and not is_auto:
        syslog.syslog(syslog.LOG_ERR, 'Can\'t change vent mode, auto mode is disabled')
        return
    if mode not in (1, 2, 3, 4):
        syslog.syslog(syslog.LOG_ERR, 'Can\'t change vent mode, mode is unknown')
        return
    global s
    global timer
    request = '{0}_{1:2X}_{2:X}'.format('VWFtr', TCP_PASS, mode)
    s.settimeout(5.0)
    s.send(request)
    data = str( s.recv(BUFFER_SIZE) )
    if data != 'OK_VWFtr_{0:X}'.format(mode):
        syslog.syslog(syslog.LOG_ERR, 'Can\'t change vent mode: {0}'.format(mode))
    else:
        if timer: timer.cancel()
        time.sleep(0.5)
        get_vent_status()

def on_scene_message(client, userdata, message):
    '''
    Код запроса клиента: VWScn_Pass_bitNScen
    Запрос для активации сценария. Запрос разрешен, только если ScenBlock == 0
    Описание переменных:
        bitNScen:
            Bit 3-0 – номер сценария, который нужно активировать (от 1 до 8) или 0, если включать сценарий не
            нужно.
            Bit 7-4 – 10 - отключить выполнение сценариев по таймерам; 11 – включить выполнение сценариев
            по таймерам. При других значениях это поле ни на что не влияет.
    '''
    if is_sceneblock:
        syslog.syslog(syslog.LOG_ERR, 'Can\'t change scene, scene is blocked')
        return
    mode = message.payload.decode('utf-8').upper()
    if mode in ('ON', 'OFF'):
        command = (10 if mode == 'OFF' else 11) << 4
    else:
        try:
            mode = int(mode)
        except ValueError:
            syslog.syslog(syslog.LOG_ERR, 'Incorrect value for scene: {0}'.format(message.payload.decode('utf-8')))
            return
        if mode in (1,2,3,4,5,6,7,8):
            command = mode
        else:
            syslog.syslog(syslog.LOG_ERR, 'Can\'t change scene, scene number must be in range 1-8')
            return
    global s
    global timer
    request = '{0}_{1:2X}_{2:X}'.format('VWScn', TCP_PASS, command)
    s.settimeout(5.0)
    s.send(request)
    data = str( s.recv(BUFFER_SIZE) )
    if data != 'OK_VWScn_{0:X}'.format(command):
        syslog.syslog(syslog.LOG_ERR, 'Can\'t change scene: {0}'.format(mode))
    else:
        if timer: timer.cancel()
        time.sleep(0.5)
        get_vent_status()

def split_data(data, array_len=0):
    data_array = data.split('_')
    if len(data_array) != array_len:
        return None
    return data_array

def check_vent_params():
    global s
    global temperature_min, temperature_max
    global speed_min, speed_max
    global humidity_min, humidity_max
    global is_humidifier, is_cooler, is_auto
    global is_vav, is_regpressvav

    # VPr07_Pass
    request = '{0}_{1:2X}'.format('VPr07', TCP_PASS)
    s.settimeout(5.0)
    s.send(request)
    data = str( s.recv(BUFFER_SIZE) )
    '''
    VPr07_bitTempr_bitSpeed_bitHumid_bitMisc_BitPrt_BitVerTPD_BitVerContr
    Описание переменных:
        bitTemper:
            Bit 7-0 – TempMin – минимально допустимая заданная температура (от 5 до 15)
            Bit 15-8 –TempMax – максимально допустимая заданная температура (от 30 до 45)
        bitSpeed:
            Bit 7-0 – SpeedMin - минимальная скорость (от 1 до 7).
            Bit 15-8 – SpeedMax - максимальная скорость (от 2 до 10).
        bitHumid:
            Bit 7-0 – HumidMin – минимальная заданная влажность, от 0 до 100%.
            Bit 15-8 – HumidMax - максимальная заданная влажность, от 0 до 100%.
        bitMisc:
            Bit 4 - 0 – NVAVZone – кол-во зон в режиме VAV (от 1 до 20).
            Bit 7 - 5 – резерв
            Bit 8 – VAVMode – режим VAV включен.
            Bit 9 – IsRegPressVAV – включена возможность регулирования давления в канале в режиме VAV.
            Bit 10 – IsShowHum – включено отображение влажности.
            Bit 11 – IsCascRegT – включен каскадный регулятор T.
            Bit 12 – IsCascRegH – включен каскадный регулятор H.
            Bit 13 – IsHumid – есть увлажнитель.
            Bit 14 – IsCooler – есть охладитель.
            Bit 15 – IsAuto – есть режим Авто переключения Обогрев / Охлаждение.
        BitPrt:
            Bit 7-0 – ProtSubVers – субверсия протокола обмена (от 1 до 255)
            Bit 15-8 – ProtVers – версия протокола обмена (от 100 до 255)
        BitVerTPD:
            Bit 7-0 – LoVerTPD – младший байт версии прошивки пульта
            Bit 15-8 – HiVerTPD – старший байт версии прошивки пульта
            BitVerContr - Firmware_Ver – версия прошивки контроллера
    '''
    data_array = split_data(data, 8)
    if not data_array:
        syslog.syslog(syslog.LOG_ERR, 'Incorrect answer: {0}'.format(data))
        return False
    try:
        version = int(data_array[5],16) >> 8
        subversion = int(data_array[5],16) & 0xFF
    except ValueError:
        syslog.syslog(syslog.LOG_ERR, 'Incorrect value for version/subversion')
        return False
    if version != 107:
        syslog.syslog(syslog.LOG_ERR, 'Incompatible protocol version: {0}.{1}'.format(version, subversion))
        return False
    try:
        temperature_min = int(data_array[1],16) & 0xFF
        temperature_max = (int(data_array[1],16) & 0xFF00) >> 8
        speed_min = int(data_array[2],16) & 0xFF
        speed_max = (int(data_array[2],16) & 0xFF00) >> 8
        humidity_min = int(data_array[3],16) & 0xFF
        humidity_max = (int(data_array[3],16) & 0xFF00) >> 8
        is_vav = True if int(data_array[4],16) & 0x100 else False
        is_regpressvav = True if int(data_array[4],16) & 0x200 else False
        is_humidifier = True if int(data_array[4],16) & 0x2000 else False
        is_cooler = True if int(data_array[4],16) & 0x4000 else False
        is_auto = True if int(data_array[4],16) & 0x8000 else False
    except ValueError:
        syslog.syslog(syslog.LOG_ERR, 'Incorrect value for vent parameters')
        return False
    return True

def get_vent_status():
    global timer
    global s
    global is_sceneblock, is_powerblock
    timer = threading.Timer(INTERVAL, get_vent_status)
    timer.start()

    # VSt07_Pass
    request = '{0}_{1:2X}'.format('VSt07', TCP_PASS)
    s.settimeout(5.0)
    s.send(request)
    data = str( s.recv(BUFFER_SIZE) )
    # VSt07_bitState_bitMode_bitTempr_bitHumid_bitSpeed_bitMisc_bitTime_bitDate_bitYear_Msg
    data_array = split_data(data, 11)
    if not data_array:
        syslog.syslog(syslog.LOG_ERR, 'Incorrect answer: {0}'.format(data))
        return
    '''
    bitState:
        Bit 0 – PwrBtnState – состояние кнопки питания (вкл / выкл).
        Bit 1 – IsWarnErr – есть предупреждение. В Msg содержится текст сообщения.
        Bit 2 – IsFatalErr – есть критическая ошибка. В Msg содержится текст сообщения.
        Bit 3 – DangerOverheat – угроза перегрева калорифера (для установки с электрокалорифером).
        Bit 4 – AutoOff – установка автоматически выключена на 5 минут для автоподстройки нуля
        датчика давления.
        Bit 5 – ChangeFilter – предупреждение о необходимости замены фильтра.
        Bit 8-6 – ModeSet – установленный режим работы.
            1 – Обогрев
            2 – Охлаждение
            3 – Авто
            4 – Отключено (вентиляция без обогрева и охлаждения)
        Bit 9 – HumidMode – селектор Увлажнитель активен (стоит галочка).
        Bit 10 – SpeedIsDown – скорость вентилятора автоматически снижена.
        Bit 11 – FuncRestart – включена функция Рестарт при сбое питания.
        Bit 12 – FuncComfort – включена функция Комфорт.
        Bit 13 – HumidAuto – увлажнение включено (в режиме Авто).
        Bit 14 – ScenBlock – сценарии заблокированы режимом ДУ.
        Bit 15 – BtnPwrBlock – кнопка питания заблокирована режимом ДУ.
    '''
    status = {}
    status['Temperature'] = {}
    status['Humidity'] = {}
    status['Speed'] = {}
    status['DateTime'] = {}
    status['Scene'] = {}
    status['Settings'] = {}
    status['State'] = {}

    status['State']['Power'] = 'ON' if int(data_array[1], 16) & 0x01 else 'OFF'
    status['State']['Warning'] = 'ON' if int(data_array[1], 16) & 0x02 else 'OFF'
    status['State']['Critical'] = 'ON' if int(data_array[1], 16) & 0x04 else 'OFF'
    status['State']['Overheat'] = 'ON' if int(data_array[1], 16) & 0x08 else 'OFF'
    status['State']['AutoOff'] = 'ON' if int(data_array[1], 16) & 0x10 else 'OFF'
    status['State']['ChangeFilter'] = 'ON' if int(data_array[1], 16) & 0x20 else 'OFF'
    status['Settings']['Mode'] = (int(data_array[1], 16) & 0x1C0) >> 6
    status['Humidity']['Mode'] = 'ON' if int(data_array[1], 16) & 0x200 else 'OFF'
    status['Speed']['SpeedIsDown'] = 'ON' if int(data_array[1], 16) & 0x400 else 'OFF'
    status['State']['AutoRestart'] = 'ON' if int(data_array[1], 16) & 0x800 else 'OFF'
    status['State']['Comfort'] = 'ON' if int(data_array[1], 16) & 0x1000 else 'OFF'
    status['Humidity']['Auto'] = 'ON' if int(data_array[1], 16) & 0x2000 else 'OFF'
    is_sceneblock = True if int(data_array[1], 16) & 0x4000 else False
    status['Scene']['Block'] = 'ON' if is_sceneblock else 'OFF'
    is_powerblock = True if int(data_array[1], 16) & 0x8000 else False
    status['State']['PowerBlock'] = 'ON' if is_powerblock else 'OFF'
    '''
    bitMode:
        Bit 1, 0 – UnitState – состояние установки:
            0 – Выключено.
            1 – Включено.
            2 – Выключение (переходный процесс перед отключением).
            3 – Включение (переходный процесс перед включением).
        Bit 2 – ScenAllow – разрешена работа по сценариям.
        Bit 5-3 – Mode – режим работы:
            0 – Обогрев
            1 – Охлаждение
            2 – Авто-Обогрев
            3 – Авто-Охлаждение
            4 – Отключено (вентиляция без обогрева и охлаждения)
            5 – Нет (установка выключена)
        Bit 9-6 – NumActiveScen – номер активного сценария (от 1 до 8), 0 если нет.
        Bit 12-10 – WhoActivateScen – кто запустил (активировал) сценарий:
            0 – активного сценария нет и запущен не будет
            1 – таймер1
            2 – таймер2
            3 – пользователь вручную
            4 – сценарий будет запущен позднее (сейчас активного сценария нет)
        Bit 13-15 – NumIcoHF – номер иконки Влажность / фильтр.
    '''
    unitstate = {0:'Выключено', 1:'Включено', 2:'Выключение', 3:'Включение'}
    status['State']['Unit'] = unitstate[(int(data_array[2], 16) & 0x03)]
    status['Scene']['SceneState'] = 'ON' if int(data_array[2], 16) & 0x04 else 'OFF'
    unitmode = {0:'Обогрев', 1:'Охлаждение', 2:'Авто-Обогрев', 3:'Авто-Охлаждение', 4:'Вентиляция', 5:'Выключено'}
    status['State']['Mode'] = unitmode[(int(data_array[2], 16) & 0x38) >> 3]
    status['Scene']['Number'] = (int(data_array[2], 16) & 0x3C0) >> 6
    '''
    bitTempr:
        Bit 7-0 – Tempr signed char – текущая температура, °С. Диапазон значений от -50 до 70.
        Bit 15-8 – TemperTarget – заданная температура, °С. Диапазон значений от 0 до 50.
    '''
    status['Temperature']['Current'] = (int(data_array[3], 16) & 0xFF)
    status['Temperature']['Target'] = (int(data_array[3], 16) & 0xFF00) >> 8
    '''
    bitHumid:
        Bit 7-0 – Humid – текущая влажность (при наличии увлажнители или датчика влажности). Диапазон
        значений от 0 до 100. При отсутствии данных значение равно 255.
        Bit 15-8 – HumidTarget – заданная влажность. Диапазон значений от 0 до 100.
    '''
    status['Humidity']['Current'] = (int(data_array[4], 16) & 0xFF)
    status['Humidity']['Target'] = (int(data_array[4], 16) & 0xFF00) >> 8
    '''
    bitSpeed:
        Bit 3-0 – Speed – текущая скорость вентилятора, диапазон от 0 до 10.
        Bit 7-4 – SpeedTarget – заданная скорость вентилятора, диапазон от 0 до 10.
        Bit 15-8 – SpeedFact – фактическая скорость вентилятора 0 – 100%. Если не определено, то 255.
    '''
    status['Speed']['Current'] = (int(data_array[5], 16) & 0x0F)
    status['Speed']['Target'] = (int(data_array[5], 16) & 0xF0) >> 4
    status['Speed']['Actual'] = (int(data_array[5], 16) & 0xFF00) >> 8
    '''
    bitMisc:
        Bit 3-0 – TempMin – минимально допустимая заданная температура (от 5 до 15). Может изменяться
        в зависимости от режима работы вентустановки
        Bit 5, 4 – ColorMsg – иконка сообщения Msg для различных состояний установки:
            0 – Нормальная работа (серый)
            1 – Предупреждение (желтый)
            2 – Ошибка (красный)
        Bit 7, 6 – ColorInd – цвет индикатора на кнопке питания для различных состояний установки:
            0 – Выключено (серый)
            1 – Переходный процесс включения / отключения (желтый)
            2 – Включено (зеленый)
        Bit 15-8 – FilterDust – загрязненность фильтра 0 - 250%, если не определено, то 255.
    '''
    status['Temperature']['Minimum'] = (int(data_array[6], 16) & 0x0F)
    status['State']['ColorMsg'] = (int(data_array[6], 16) & 0x30) >> 4
    status['State']['ColorInd'] = (int(data_array[6], 16) & 0xC0) >> 6
    status['State']['FilterDust'] = (int(data_array[6], 16) & 0xFF00) >> 8
    '''
    bitTime:
        Bit 7-0 – nn – минуты (от 00 до 59)
        Bit 15-8 – hh – часы (от 00 до 23)
    '''
    status['DateTime']['Time'] = '{0:02d}:{1:02d}'.format((int(data_array[7], 16) & 0xFF00) >> 8, int(data_array[7], 16) & 0xFF)
    '''
    bitDate:
        Bit 7-0 – dd – день месяца (от 1 до 31)
        Bit 15-8 – mm – месяц (от 1 до 12)
    bitYear:
        Bit 7-0 – dow – день недели (от 1-Пн до 7-Вс)
        Bit 15-8 – yy – год (от 0 до 99, последние две цифры года).
    '''
    status['DateTime']['Date'] = '{0:02d}-{1:02d}-20{2:02d}'.format(int(data_array[8], 16) & 0xFF, (int(data_array[8], 16) & 0xFF00) >> 8, (int(data_array[9], 16) & 0xFF00) >> 8)
    '''
    Msg - текстовое сообщение о состоянии установки длиной от 5 до 70 символов.
    '''
    status['Msg'] = data_array[10]
    client.publish(PREFIX + '/STATUS', json.dumps(status, ensure_ascii=False))

# if __name__ == '__main__':
with daemon.DaemonContext():
    syslog.syslog(syslog.LOG_INFO, 'Translator started')
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((TCP_IP, TCP_PORT))
        if not check_vent_params(): sys.exit(-1)

        client = mqtt.Client(CLIENT_ID, True if CLIENT_ID else False)
        client.will_set(PREFIX + '/LWT', 'Offline', 0, True)
        client.on_connect = on_connect_mqtt
        client.username_pw_set(USERNAME, PASSWORD)
        client.connect(BROKER, 1883, 60)

        client.loop_start()
        get_vent_status()

        # infinite loop ...
        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        sys.exit(0)
    except:
        syslog.syslog(syslog.LOG_ERR, 'Translator terminated with error')
        sys.exit(-1)
    finally:
        if s: s.close()
        if timer: timer.cancel()
        syslog.syslog(syslog.LOG_INFO, 'Translator terminated')
