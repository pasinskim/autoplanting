import board
import digitalio
import adafruit_dht
import busio

import time
import asyncio
from datetime import datetime, timedelta
import argparse
import json

import character_lcd_pcf8574 as char_lcd
import schedule
import mqtt

def parse_command_line_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=(
            'Automatic gardening IoT client.'))
    parser.add_argument(
            '--algorithm',
            choices=('RS256', 'ES256'),
            required=True,
            help='Which encryption algorithm to use to generate the JWT.')
    parser.add_argument(
            '--ca_certs',
            default='roots.pem',
            help='CA root from https://pki.google.com/roots.pem')
    parser.add_argument(
            '--cloud_region', default='us-central1', help='GCP cloud region')
    parser.add_argument(
            '--device_id', required=True, help='Cloud IoT Core device id')
    parser.add_argument(
            '--mqtt_bridge_hostname',
            default='mqtt.googleapis.com',
            help='MQTT bridge hostname.')
    parser.add_argument(
            '--mqtt_bridge_port',
            choices=(8883, 443),
            default=8883,
            type=int,
            help='MQTT bridge port.')
    parser.add_argument(
            '--private_key_file',
            required=True,
            help='Path to private key file.')
    parser.add_argument(
            '--project_id',
            help='GCP cloud project name')
    parser.add_argument(
            '--registry_id', required=True, help='Cloud IoT Core registry id')
    parser.add_argument(
            '--schedule_file',
            default='cron',
            help='Cron like file containing the jobs.')
    parser.add_argument(
            '--do_mqtt',
            action='store_true',
            help='Enable MQTT connection to GCP IoT Core.')

    return parser.parse_args()

def initDevices():
    # initialize lcd
    lcd_columns = 16
    lcd_rows = 2
    i2c = busio.I2C(board.SCL, board.SDA)
    lcd = char_lcd.Character_LCD_I2C_PCF8574(i2c, lcd_columns, lcd_rows, address=0x27)

    # and write a simple message
    lcd.clear()
    lcd.backlight = True
    lcd.message = "initializing..."

    # initialize the pump controlling relay pin
    pump = digitalio.DigitalInOut(board.D23)
    pump.direction = digitalio.Direction.OUTPUT
    # low state is causing NO raly pin to activate
    # so we need to initialize it with high state first
    pump.value = True

    # initialize water level sensor
    level = digitalio.DigitalInOut(board.D4)
    level.direction = digitalio.Direction.INPUT

    # initialize the lump controlling relay pin
    lamp = digitalio.DigitalInOut(board.D24)
    lamp.direction = digitalio.Direction.OUTPUT
    lamp.value = True

    lcd.clear()
    lcd.message = "init done"

    # initialize the dht device
    dhtDevice = adafruit_dht.DHT11(board.D18)

    return {"pump": pump, "lamp": lamp, "display": lcd, "level": level, "dht": dhtDevice}

async def getTempAndHumid(dht):
    # as the single measurment is not always accurate we do a series
    # and take the average excluding max and min values
    temperature = []
    humidity = []
    for _ in range(5):
        try:
            temperature.append(dht.temperature)
            humidity.append(dht.humidity)
        except RuntimeError as error:
            print(error.args[0])
        await asyncio.sleep(1)
    # remove max and min and return average
    temperature.remove(max(temperature))
    temperature.remove(min(temperature))
    humidity.remove(max(humidity))
    humidity.remove(min(humidity))

    return {"temp": sum(temperature)/len(temperature), "humid": sum(humidity)/len(humidity)}

async def getLevel(level):
    # read a few times just in case there are some fluctuations
    data = []
    for _ in range(5):
        data.append(level.value)
        await asyncio.sleep(1)
    # we have 5 results in the table so need to check if at least 3 are true
    return sum(data)/3.0 >= 1

async def getAndPublishMeasurements(loop, devices, mqttClient):
    while True:
        data = await getTempAndHumid(devices["dht"])
        level = await getLevel(devices["level"])

        devices["display"].clear()
        if level:
            devices["display"].message = "tank empty"
        else:
            devices["display"].message = "Temp: {:.1f} C\nHumidity: {:.1f} %".format(
                data["temp"], data["humid"])        
        
        print("Temp: {:.1f} C\nHumidity: {:.1f} %\nLevel: {}".format(
            data["temp"], data["humid"], "empty" if level else "full"))

        if mqttClient:
            loop.call_soon(mqttClient.publish, 'temp', data["temp"])
            loop.call_soon(mqttClient.publish, 'humid', data["humid"])
            loop.call_soon(mqttClient.publish, 'level', "empty" if level else "full")
        
        
        # measurements will be taken always every minute
        await asyncio.sleep(60)


async def startPump(pump, level, period=30):
    endTime = datetime.now() + timedelta(seconds=period)
    print("will try to start pump for {} seconds".format(period))
    try:
        while datetime.now() < endTime:
            # check the level sensor first
            if level.value == True:
                pump.value = True
                print("water level is too low; can not start pump")
                return

            pump.value = False
            # switch the pump on for one second and then
            # run the loop again to check the level sensor
            await asyncio.sleep(1)
    except Exception as e:
        print("some error occured: {}".format(e))
    finally:
        # make sure that the pump is off at the end
        print("stopping pump...")
        pump.value = True

async def startLamp(lamp, period=30):
    print("will try to start lamp for {} seconds".format(period))
    try:
        lamp.value = False
        # switch the pump on for one second and then
        # run the loop again to check the level sensor
        await asyncio.sleep(period)
    except Exception as e:
        print("some error occured while starting lamp: {}".format(e))
    finally:
        # make sure that the lamp is off at the end
        print("stopping lamp...")
        lamp.value = True


async def doWatering(devices, attr=None):
    print("do watering {}".format(attr))
    await startPump(devices["pump"], devices["level"], int(attr[0]) if attr else 10)

async def doLight(devices, attr=None):
    print("do light: {}".format(attr))
    await startLamp(devices["lamp"], int(attr[0]) if attr else 10)

def getAction(entry):
    actions = {
        "lamp": doLight,
        "pump": doWatering
    }
    action = actions.get(entry)
    if action == None:
        print("invalid job: {}".format(entry))
    return action


async def updateSchedule(loop, devices, cronFile):
    while True:
        jobs = schedule.getNextJobs(cronFile)
        print(jobs)

        # check if we need to execute something now
        if (jobs[0][0] - datetime.now()).total_seconds() < 60:
            print("scheduling job")
            for job in jobs:
                # figure out what command to run
                action = getAction(job[1])
                if action == None:
                    continue
                print("creating task for [{}][{}]".format(job[0], job[1]))
                loop.create_task(action(devices, job[2]))
        
        # update the schedule every minute
        #IMPORTANT: it needs to be one minute else it won't work
        await asyncio.sleep(60)

# helper task to only await (break the waiting loop) so that all the tasks 
# created in 'handleMqtt()' can be executed
async def ticker():
    while True:
        await asyncio.sleep(1)

# let's use the clousure here to access devices and loop
def handleMqtt(devices, loop):

    def handler(data):
        print("got MQTT data: {}".format(data))

        # the command is passed in the payload of the message. In this example,
        # the server sends a serialized JSON string.
        try:
            cmd = json.loads(data)
            if cmd["command"] == "pump_on":
                loop.create_task(doWatering(devices, [cmd["duration"]]))
            elif cmd["command"] == "lamp_on":
                loop.create_task(doLight(devices, [cmd["duration"]]))
            else:
                print("unknown command from server: {}".format(cmd))
        except Exception as e:
            print("error occured while processing server data: {}".format(e))

    return handler

def run(args):
    devices = initDevices()
    
    # run the mian loop
    loop = asyncio.get_event_loop()
    mqttClient = None

    if args.do_mqtt:
        mqttClient = mqtt.Mqtt(vars(args))
        mqttClient.register_cb(handleMqtt(devices, loop))

    try:
        loop.create_task(getAndPublishMeasurements(loop, devices, mqttClient))
        loop.create_task(updateSchedule(loop, devices, args.schedule_file))
        if args.do_mqtt:
            loop.create_task(ticker())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        #TODO: make sure to stop everything
        loop.close()
        mqtt.deinit()

if __name__ == "__main__":
    args = parse_command_line_args()
    run(args)

