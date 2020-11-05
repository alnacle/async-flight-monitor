# Event Driven Flight status notification service using Twilio

REST has become one of the most used communication layers in the recent years:
allows developers to decouple the implementation from the specification and
works nicely as public interface for users to connect to your service. However
there are some caveats not always easy to solve: what if your API takes time to
answer? What if we don't want to wait that long to get the answer? and more
interesting: What if more than one API consumer is interested in receveing
asynchronous events from the system?

In the following article we will describe the implementation of a small
prototype of microservices architectures using asynchronous communication to
provide notifications about flight status changes coming from the Airline.

## Introducing One Demand Flight Status

On-Demand Flight Status API provides real time flight schedule data from a
given flight. A flight is represented by a ternary: the airline carrier code,
the flight number and the departure date. The API will return:

- Departure and arrival times.
- Flight duration.
- Airport information, such as terminal and gate.

Let's use `cURL` to retrieve the schedule information from flight `KL-1772` departuring on 29th of October 2020:

```
curl https://test.api.amadeus.com/v2/schedule/flights?carrierCode=KL&flightNumber=1772&scheduledDepartureDate=2020-10-29
```

If we analyse the response, we see that JSON contains `segment` and `legs` information:

```
"segments": [
    {
        "boardPointIataCode": "FRA",
        "offPointIataCode": "AMS",
        "scheduledSegmentDuration": "PT1H15M",
        "partnership": {
            "operatingFlight": {
                "carrierCode": "CZ",
                "flightNumber": 7690
            }
        }
    }
],

```

In this case, the flight is composed by one single segment: departure from
Frankfurt and arrival in Amsterdam Schiphol Airport. Besides origin and
destination, we see that the duration of the flight will last 1 hour and 15
minutes and the flight is operated in partnership with China Southern Airlines.

Interesting part comes under `flightPoints` section of the JSON:

```
"flightPoints": [
    {
        "iataCode": "FRA",
        "departure": {
            "terminal": {
                "code": "1"
            },
            "gate": {
                "mainGate": "B20"
            },
            "timings": [
                {
                    "qualifier": "STD",
                    "value": "2020-10-28T18:20+01:00"
                }
            ]
        }
    },
    {
        "iataCode": "AMS",
        "arrival": {
            "terminal": {
                "code": "1"
            },
            "gate": {
                "mainGate": "A04"
            },
            "timings": [
                {
                    "qualifier": "STA",
                    "value": "2020-10-28T19:35+01:00"
                }
            ]
        }
    }
],
```
We can see that the Airline has recently updated some information:

- Departure will take place from Terminal 1, gate B22 of the Frankfurt International Airport.
- We will arrive at Terminal 1, main gate A22 of Amsterdam Schiphol Airport.

The question is: what if any of this information changes? What if the boarding
gate changes 1 hour before departure time? How can we be up to dated? Well, we
could always check the monitors at the airport but we all are very busy
watching our favourite TV-show on the tablet or mobile phone. Wouldn't be cool
to receive an SMS to our phone with the update? That is indeed the main goal of
our prototype.

## What is an Event-Driven Microservice Architecture?

An event-driven architecture is a methodoly for defining relationships between
peers in order to consume events (or changes) around a particular state or
resource.

The architecture will be composed by several services, each of them
implementing one single task and producing an output that other service will
eventually consume. Services will run independently and don't have dependencies
among them.

There are different strategies for implementing and consuming APIs
asynchronously (webhooks, resthooks or websockets just to name a few) but in
this article we will focus on the `publish-subscribe` pattern, where events
are published to a channel where the consumer of the events can subscribe to.

There are different messaging protocols which implement the `publish-subscribe`
pattern. In this prototype we will use the `MQTT` protocol, which provides a
lightweight publish-subscribe messaging pattern focused on low resources
consumption.

## Describing our architecture

The idea of our prototype is to implement an asynchronous notification service
to notify users when flight information changes, such as boarding gate or
arrival terminal. A potential use case of this service could be implemented,
for example, by a company willing to notify employees traveling for business
purposes.

We are going to define two messages to model the events managed by subscriber
and publishers:

- A message to subscribe to changes. This event will queue a new flight to be monitored.
- A message to notify changes. Once we detect a change on the flight status,
  the service will trigger the notification event to notify the user.

As we will implement a microservice architecture, we will have different
services, each of them providing specific functionality:

- Subscriber service, which provides a simple web interface to allow users to
subscribe to flight updates.

- Monitor service, which receives and queues flight information to query the REST
API looking for changes. Once a change has been detected the service will
notify the change to all subscribers.

- Notifier service, which receives the notification of changes on the flight and
notifies the change to the user via SMS.

As messages will be shared among services, it is extremely important to
correctly specify the interface of each message. Please welcome `AsyncAPI`! 

### AsyncAPI to the rescue

In the same way our REST APIs must be correctly defined and documented, our
event-driven architecture should be documented as well. We are going to use
`AsyncAPI`, an easy-to-use specification (and toolchain) to define asynchronous
APIs. You can think about `AsyncAPI` as the `OpenAPI` for asynchronous APIs.

As we mention on the previous section, we will implement two different
messages. Each message will be emitted on a different channel or topic, where
subscribers can subscribe to:

```
channels:
  flight/queue:
    description: |
      Queue flight in order to retrieve status
    publish:
      summary: Subscribe about the status of a given flight
      message:
        $ref: '#/components/messages/flightQueue'
  flight/update:
    description: |
      Provides updates from a subscribed flight
    subscribe:
      summary: Inform about the status of a subscribed flight
      message:
        $ref: '#/components/messages/flightStatus'
```

The first channel `flight/queue`, will be use to queue flights in order to be
monitored by the `monitor` service. Thus, once the user fill in the required
information of the flight (carrier code, flight number and departure date)
using a web interface, the `subscriber` service will emit the `flightQueue`
message, which will be received by the `notifier` service, which will add the
payload of the message to internal list of flights to be monitored.

The `flightQueue` message will be composed of two main `schemas`: `user`,
corresponding to the user personal information (name and phone number) who will
receive the notification, and `flight`, modeling the information about the
flight to be monitored. 

One of the main beneficts of using `AsyncAPI` is to allow us to reuse `JSON
schemas` from our `OpenAPI REST` specification. In our case, we are going to
reuse the `flight schema` from the synchronous API: 

```
type: object
properties:
  carrierCode:
    type: string
    description: 2 to 3-character IATA carrier code
    example: "LH"
  flightNumber:
    type: integer
    minimum: 1
    description: 1 to 4-digit number of the flight
    example: "193"
  scheduledDepartureDate:
    type: string
    format: date-time
    description: scheduled departure date of the flight, local to the departure airport.
    example: "2020-10-20"
```

Integrating and connecting asynchronous APIs has never been easier!

Once the `monitor` service detects a change on the status of the flight (for
example, the boarding gate has changed), the service will emit the
`flightStatus` message to inform subscribers about the change. The `notifier`
service will be the service subscribed to changes, as it will notify the user
via SMS. 

The payload of the `flightStatus` messge will consist on the following structure:

- `flight schema` to identify the flight emitting the event.
- `user schema` to idenfify the user that shall be reported.
- Two `segments sechemas`, corresponding to the origin and destination. This way
we could notify about potential changes at departure and arrival.

Let's take a look to the `segment schema`:

```
type: object
properties:
  iataCode:
    type: string
    description: 2 to 3-character IATA carrier code
    example: "MAD"
  scheduledDate:
    type: string
    format: date-time
    description: scheduled date of the flight, local to the airport.
    example: "2020-10-20"
  gate:
    type: string
    description: departure gate
    example: "2D"
  terminal:
    type: string
    description: airport terminal
    example: "4"
```



## Microservices implementation

### Monitor

### Subscriber

### Notifier

### Running everything up

## Improvements and next steps


