#!/usr/bin/env python

# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Python sample for connecting to Google Cloud IoT Core via MQTT, using JWT.
This example connects to Google Cloud IoT Core via MQTT, using a JWT for device
authentication. After connecting, by default the device publishes 100 messages
to the device's MQTT topic at a rate of one per second, and then exits.
Before you run the sample, you must follow the instructions in the README
for this sample.
"""

import argparse
import datetime
import os
import random
import ssl
import time
import json

import jwt
import paho.mqtt.client as mqtt

# The maximum backoff time before giving up, in seconds.
MAXIMUM_BACKOFF_TIME = 128

def create_jwt(project_id, private_key_file, algorithm):
    """Creates a JWT (https://jwt.io) to establish an MQTT connection.
        Args:
         project_id: The cloud project ID this device belongs to
         private_key_file: A path to a file containing either an RSA256 or
                 ES256 private key.
         algorithm: The encryption algorithm to use. Either 'RS256' or 'ES256'
        Returns:
            A JWT generated from the given project_id and private key, which
            expires in 20 minutes. After 20 minutes, your client will be
            disconnected, and a new JWT will have to be generated.
        Raises:
            ValueError: If the private_key_file does not contain a known key.
        """

    token = {
            # The time that the token was issued at
            'iat': datetime.datetime.utcnow(),
            # The time the token expires.
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=60),
            # The audience field should always be set to the GCP project id.
            'aud': project_id
    }

    # Read the private key file.
    with open(private_key_file, 'r') as f:
        private_key = f.read()

    print('Creating JWT using {} from private key file {}'.format(
            algorithm, private_key_file))

    return jwt.encode(token, private_key, algorithm=algorithm)

def error_str(rc):
    """Convert a Paho error to a human readable string."""
    return '{}: {}'.format(rc, mqtt.error_string(rc))

class Mqtt(object):
    """Represents the state of a device."""

    def __init__(self, config):
        # Configuration parameters
        self.config = config
        self.publishing_default_topic = '/devices/{}/{}'.format(self.config['device_id'], 'events')

        self.connected = False
        self.should_backoff = True
        self.minimum_backoff_time = 1
        self.jwt_exp_mins = 60
        
        # Connect the client.
        self.__connect_with_retry()

    def __connect_with_retry(self):
        global MAXIMUM_BACKOFF_TIME
        
        self.__init_and_connect()

        while self.should_backoff:
            print('will do the backoff')

            # If backoff time is too large, give up.
            if self.minimum_backoff_time > MAXIMUM_BACKOFF_TIME:
                print('Exceeded maximum backoff time. Giving up.')
                return

            # Otherwise, wait and connect again.
            delay = self.minimum_backoff_time + random.randint(0, 1000) / 1000.0
            print('Waiting for {} before reconnecting.'.format(delay))
            time.sleep(delay)

            # Check if something changed after the sleep
            if not self.should_backoff:
                return

            self.minimum_backoff_time *= 2
            self.client.connect(
                self.config['mqtt_bridge_hostname'], 
                self.config['mqtt_bridge_port'])

            self.client.loop_start()

            # This is the topic that the device will receive configuration updates on.
            mqtt_config_topic = '/devices/{}/config'.format(self.config['device_id'])
            # The topic that the device will receive commands on.
            mqtt_command_topic = '/devices/{}/commands/#'.format(self.config['device_id'])

            print('Subscribing to {} and {}'.format(
                mqtt_config_topic, mqtt_command_topic))
            self.client.subscribe(mqtt_config_topic, qos=1)
            self.client.subscribe(mqtt_command_topic, qos=0)

    def __init_and_connect(self):
        client_id = 'projects/{}/locations/{}/registries/{}/devices/{}'.format(
            self.config['project_id'], 
            self.config['cloud_region'], 
            self.config['registry_id'], 
            self.config['device_id'])
        print('Device client_id is \'{}\''.format(client_id))

        self.client = mqtt.Client(client_id=client_id)

        self.jwt_iat = datetime.datetime.utcnow()
        
        # With Google Cloud IoT Core, the username field is ignored, and the
        # password field is used to transmit a JWT to authorize the device.
        self.client.username_pw_set(
                username='unused',
                password=create_jwt(
                        self.config['project_id'], 
                        self.config['private_key_file'], 
                        self.config['algorithm']))

        # Enable SSL/TLS support.
        self.client.tls_set(
            ca_certs=self.config['ca_certs'], tls_version=ssl.PROTOCOL_TLSv1_2)

        # Register message callbacks. https://eclipse.org/paho/clients/python/docs/
        # describes additional callbacks that Paho supports. In this example, the
        # callbacks just print to standard out.
        self.client.on_connect = self.on_connect
        self.client.on_publish = self.on_publish
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

        # Connect to the Google MQTT bridge.
        print('Connecting client')
        self.client.connect(
            self.config['mqtt_bridge_hostname'], 
            self.config['mqtt_bridge_port'])
        self.client.loop_start()

        # This is the topic that the device will receive configuration updates on.
        mqtt_config_topic = '/devices/{}/config'.format(self.config['device_id'])
        # The topic that the device will receive commands on.
        mqtt_command_topic = '/devices/{}/commands/#'.format(self.config['device_id'])

        print('Subscribing to {} and {}'.format(
            mqtt_config_topic, mqtt_command_topic))
        self.client.subscribe(mqtt_config_topic, qos=1)
        self.client.subscribe(mqtt_command_topic, qos=0)

    def __check_and_refresh_jwt(self):
        seconds_since_issue = (datetime.datetime.utcnow() - self.jwt_iat).seconds
        if seconds_since_issue > 60 * self.jwt_exp_mins:
            print('Refreshing token after {}s'.format(seconds_since_issue))
            self.jwt_iat = datetime.datetime.utcnow()

            self.client.disconnect()
            self.__connect_with_retry()

    def publish(self, key, value, topic=''):
        # Check if JWT expired
        self.__check_and_refresh_jwt()
        payload = json.dumps({key: value})
        print('Publishing payload', payload)
        if topic == '':
            topic = self.publishing_default_topic
        self.client.publish(topic, payload, qos=1)

    def deinit(self):
        self.client.disconnect()
        self.client.loop_stop()
        print('Finished loop successfully.')

    def on_connect(self, unused_client, unused_userdata, unused_flags, rc):
        """Callback for when a device connects."""
        print('Connection Result:', error_str(rc))
        self.connected = True
        self.should_backoff = False
        self.minimum_backoff_time = 1

    def on_disconnect(self, unused_client, unused_userdata, rc):
        """Callback for when a device disconnects."""
        print('Disconnected:', error_str(rc))
        self.connected = False
        self.should_backoff = True
        
        #TODO: check if needed
        # self.client.loop_stop()

    def on_publish(self, unused_client, unused_userdata, unused_mid):
        """Callback when the device receives a PUBACK from the MQTT bridge."""
        print('Published message acked.')

    def on_subscribe(self, unused_client, unused_userdata, unused_mid,
                     granted_qos):
        """Callback when the device receives a SUBACK from the MQTT bridge."""
        print('Subscribed: ', granted_qos)
        if granted_qos[0] == 128:
            print('Subscription failed.')

    def on_message(self, unused_client, unused_userdata, message):
        """Callback when the device receives a message on a subscription."""
        payload = message.payload.decode('utf-8')
        print('Received message \'{}\' on topic \'{}\' with Qos {}'.format(
            payload, message.topic, str(message.qos)))

        if self.message_cb and payload:
            self.message_cb(payload)

    def register_cb(self, callback_fn):
        self.message_cb = callback_fn
