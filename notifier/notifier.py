import os
import ast
import twilio.rest as twilio
import paho.mqtt.client as mqtt

def build_message(user, departure, arrival):
    return """Dear {}, your flight from {} to {} has changed:
        departure at {} terminal {} gate {}.
        arrival at {} terminal {} gate{}""".format(user['userName'],
                                                 departure['iataCode'],
                                                 arrival['iataCode'],
                                                 departure['scheduledTime'],
                                                 departure['terminal'],
                                                 departure['gate'],
                                                 arrival['scheduledTime'],
                                                 arrival['terminal'],
                                                 arrival['gate'])

def on_connect(client, userdata, flags, rc):
    client.subscribe("flight/update")

def on_message(client, userdata, msg):
    msg_str = msg.payload.decode("UTF-8")
    alert_msg = ast.literal_eval(msg_str)

    account_sid = os.getenv('TWILIO_SID', None)
    auth_token = os.getenv('TWILIO_TOKEN', None)
    twilio_phone = os.getenv('TWILIO_PHONE', None)

    if not account_sid or not auth_token or not twilio_phone:
        return

    client = twilio.Client(account_sid, auth_token)

    msg = build_message(alert_msg['user'],
                        alert_msg['departure'],
                        alert_msg['arrival'])

    destination_phone = alert_msg['user']['phoneNumber']

    message = client.messages.create(body=msg,
                                     from_=twilio_phone,
                                     to=destination_phone
                                     )

if __name__ == "__main__":

    client = mqtt.Client()

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect("broker", 1883, 60)
    except ConnectionRefusedError:
        print("Error: Unable to connect to broker")
    client.loop_forever()
