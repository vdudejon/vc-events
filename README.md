# vc-events

A lightweight event listener for VMware vCenter that streams all vCenter events to a RabbitMQ server. This makes it easy to aggregate events from multiple vCenter servers into a single message queue, enabling centralized monitoring, alerting, and automation workflows.

## Overview

This application connects to a VMware vCenter server, listens for all events in real-time, and publishes them to a RabbitMQ exchange. Each event is converted to JSON format and routed based on its event type, making it easy to build event-driven automation and monitoring systems.

## Prerequisites

- Python 3.12 or higher (or Docker)
- Access to a VMware vCenter server
- A RabbitMQ server with:
  - Virtual host named `vcenter_events`
  - Exchange named `vcenter.events` (will be used for publishing events)
  - Appropriate user credentials with publish permissions

## Installation

### Local Installation

1. Clone this repository:
```bash
git clone https://github.com/vdudejon/vc-events.git
cd vc-events
```

2. Install dependencies:
```bash
pip install -r app/requirements.txt
```

3. Create a `.env` file in the project root (see Configuration section below)

### Docker Installation

1. Clone this repository:
```bash
git clone https://github.com/vdudejon/vc-events.git
cd vc-events
```

2. Create a `.env` file in the project root (see Configuration section below)

3. Build the Docker image:
```bash
docker build -t vc-events .
```

## Configuration

Create a `.env` file in the project root with the following variables:

```env
# vCenter Configuration
VCENTER=vcenter.example.com
VSPHERE_USER=your-vcenter-username
VSPHERE_PASSWORD=your-vcenter-password

# RabbitMQ Configuration
RABBIT_HOST=rabbitmq.example.com
RABBIT_PORT=5672
RABBIT_USER=your-rabbitmq-username
RABBIT_PASSWORD=your-rabbitmq-password

# Optional: Logging Level (defaults to DEBUG)
LOGLEVEL=INFO
```

### RabbitMQ Setup

Before running the application, ensure your RabbitMQ server has:

1. A virtual host named `vcenter_events`:
```bash
rabbitmqctl add_vhost vcenter_events
```

2. User permissions for the virtual host:
```bash
rabbitmqctl set_permissions -p vcenter_events your-rabbitmq-username ".*" ".*" ".*"
```

The application will publish events to the `vcenter.events` exchange, with the routing key set to the event type (e.g., `VmPoweredOnEvent`, `VmCreatedEvent`, etc.).

## Usage

### Running Locally

```bash
python app/main.py
```

### Running with Docker

```bash
docker run --env-file .env vc-events
```

Or with docker-compose:

```yaml
version: '3'
services:
  vc-events:
    build: .
    env_file:
      - .env
    restart: unless-stopped
```

## Event Format

Events are published as JSON messages with the following structure:

```json
{
  "vcenter": "vcenter.example.com",
  "event_id": "VmPoweredOnEvent",
  "fullFormattedMessage": "Virtual machine vm-name on host-name in datacenter-name is powered on",
  "createdTime": "2024-01-15T10:30:00.000Z",
  "userName": "DOMAIN\\username",
  "vm": "VirtualMachine:vm-123",
  ...
}
```

The routing key for each message is the `event_id`, allowing you to create targeted queue bindings for specific event types.

## Example Consumer

To consume events from RabbitMQ, bind a queue to the `vcenter.events` exchange. For example, to receive only VM power events:

```python
import pika

connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='rabbitmq.example.com', virtual_host='vcenter_events')
)
channel = connection.channel()
channel.queue_declare(queue='vm_power_events')
channel.queue_bind(exchange='vcenter.events', queue='vm_power_events', routing_key='VmPoweredOnEvent')
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

---

(Personal Note): This was an early project that I published before I learned about things like uv, pydantic settings, and loguru. I'm leaving it intact for now to demonstrate growth.
