import logging
import os
import sys
import asyncio
import vmelogger
import json
import pika
from vmepython.vmevcenter import VCenterClient
from pyVmomi import vim, vmodl
from pyVmomi.VmomiSupport import (
    Object,
    DataObject,
    F_LINK,
    ManagedObject,
    UnknownManagedMethod,
    ManagedMethod,
    binary,
    Iso8601,
)
from datetime import datetime
from PcFilter import PcFilter
from dotenv import load_dotenv

# Define logging
vmelogger.setup_logging()
logger = logging.getLogger(__name__)

# Reduce logs from pika, which was very verbose
logging.getLogger("pika").setLevel(logging.WARNING)

# Load env vars
load_dotenv()


def event_to_name_value(val, info=Object(name="", type=object, flags=0), indent=0):
    """
    Converts an event object to a name-value pair.
    This function takes a value and an info object which provides additional context
    about the value. It formats the value based on its type and the flags provided
    in the info object. For complex types like DataObject or ManagedObject, the function
    recurses through their properties and formats them into a dictionary.
    Parameters:
    - val: The value to be converted into a name-value pair. It can be of various types
      like None, DataObject, ManagedObject, list, type, etc.
    - info: An object with `name`, `type`, and `flags` attributes used for providing
      additional formatting information (default is an object with empty name, object type,
      and zero flags).
    - indent: An integer representing the current indentation level for formatting
      (default is 0). It is used to control the formatting in recursive calls.
    Returns:
    A tuple containing two elements:
    - name: A string representing the name of the value. It is derived from the info
      object if provided.
    - result: The formatted value, which could be None, a string, a dictionary, or
      other data types based on the input value.
    The function handles various types and formats them appropriately:
    - None is returned as None.
    - DataObject is returned as a string with its class name and key, or a dictionary
      of its properties.
    - ManagedObject is returned as a string with its class name and identifiers.
    - A list is iterated over and each item is formatted as a name-value pair.
    - Types are returned as their name.
    - UnknownManagedMethod is returned as its name.
    - ManagedMethod is returned as a string of its type name and method name.
    - Boolean values are returned as 'true' or 'false'.
    - datetime objects are formatted according to ISO8601 format.
    - binary data is converted to a UTF-8 string.
    - Other types are represented by their `repr`, with leading and trailing single quotes stripped.
    The info object and indent parameter are primarily used for internal recursive calls
    and are not typically set by the caller.
    
    Example usage:
    # Given a val of type DataObject with properties, and no additional info or indent:
    name, value = event_to_name_value(data_object_val)
    
    Note:
    The function assumes that the types DataObject, ManagedObject, UnknownManagedMethod,
    ManagedMethod, and binary are defined within the calling context.
    """
    name = info.name and "%s" % info.name or ""

    if val is None:
        result = None
    elif isinstance(val, DataObject):
        if info.flags & F_LINK:
            # result = "%s:%s" % (val.__class__.__name__, val.key)
            result = f"{val.__class__.__name__}:{val.key}"
        else:
            result = {}
            for prop in val._GetPropertyList():
                res_name, res_val = event_to_name_value(
                    getattr(val, prop.name), prop, indent + 1
                )
                # if res_val is not {}, [], None or empty
                if res_val:
                    result.update({res_name: res_val})
    elif isinstance(val, ManagedObject):
        if val._serverGuid is None:
            # result = "%s:%s" % (val.__class__.__name__, val._moId)
            result = f"{val.__class__.__name__}:{val._moId}"
        else:
            # result = "%s:%s:%s" % (val.__class__.__name__, val._serverGuid, val._moId)
            result = f"{val.__class__.__name__}:{val._serverGuid}:{val._moId}"
    elif isinstance(val, list):
        itemType = getattr(val, "Item", getattr(info.type, "Item", object))
        if val:
            item = Object(name="", type=itemType, flags=info.flags)
            result = {}
            name_count = 1
            for obj in val:
                res_name, res_val = event_to_name_value(obj, item, indent + 1)
                # if res2 is not {}
                if res_val:
                    if res_name == "":
                        res_name = f"data{name_count}"
                        name_count = name_count + 1
                        result.update({res_name: res_val})
        else:
            result = None
    elif isinstance(val, type):
        result = val.__name__
    elif isinstance(val, UnknownManagedMethod):
        result = val.name
    elif isinstance(val, ManagedMethod):
        result = f"{val.info.type.__name__}.{val.info.name}"
    elif isinstance(val, bool):
        result = val and "true" or "false"
    elif isinstance(val, datetime):
        result = Iso8601.ISO8601Format(val)
    elif isinstance(val, binary):
        result = str(result, "utf-8")
    else:
        result = repr(val).strip("'")

    return name, result


def get_event_id(event):
    """Get the event id"""
    # The event id is always added to these EventEx type events
    if isinstance(event, vim.event.EventEx):
        event_id = event.eventTypeId

    # Get the event id as a string using type()
    else:
        event_id = type(event).__name__
    return event_id


def create_event_message(event_dict, event, vcenter_name):
    """Create an event message, based on the event dict and inserting the vcenter name and event id"""
    event_id = get_event_id(event)
    event_id_dict = {"vcenter": vcenter_name, "event_id": event_id}
    event_message = {**event_id_dict, **event_dict}

    return event_message


def connect_rabbitmq(rabbit_host, rabbit_port, rabbit_user, rabbit_password):
    """Connect to the rabbit mq server and return the connection as channel"""
    credentials = pika.PlainCredentials(username=rabbit_user, password=rabbit_password)
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=rabbit_host,
            port=rabbit_port,
            credentials=credentials,
            virtual_host="vcenter_events",
        )
    )
    channel = connection.channel()

    # Send a message to the 'hello' queue
    channel.basic_publish(exchange="", routing_key="hello", body="Hello, RabbitMQ!")
    print(" [x] Sent 'Hello, RabbitMQ!'")

    return channel


async def send_rabbit_message(channel, event_message):
    """Send the rabbit mq message"""
    message = json.dumps(event_message)
    routing_key = event_message["event_id"]
    channel.basic_publish(
        exchange="vcenter.events", routing_key=routing_key, body=message
    )
    logger.debug(
        "# %s # %s # %s",
        event_message["vcenter"],
        event_message["event_id"],
        event_message["fullFormattedMessage"],
    )


async def create_event_publisher(event_collector, mq_channel, vcenter_name):
    """Listen for new events and send them to Rabbit MQ"""
    with PcFilter(event_collector, ["latestPage"]) as pc:
        pc.wait()  # Get all the current events from the past.
        while True:
            updt = pc.wait()
            if updt is not None:
                new_events = event_collector.ReadNext(100)
                if new_events:
                    for event in new_events:
                        event_dict = event_to_name_value(event, indent=4)
                        event_message = create_event_message(
                            event_dict[1], event, vcenter_name
                        )
                        await send_rabbit_message(mq_channel, event_message)


async def main():
    """
    The main program
    Connect to vCenter, create the event collector, connect to Rabbit, and send all events to Rabbit
    """
    logger.debug("Starting program")

    vcenter = os.environ.get("VCENTER")
    vc_user = os.environ.get("VSPHERE_USER")
    vc_password = os.environ.get("VSPHERE_PASSWORD")
    rabbit_host = os.environ.get("RABBIT_HOST")
    rabbit_port = os.environ.get("RABBIT_PORT")
    rabbit_user = os.environ.get("RABBIT_USER")
    rabbit_password = os.environ.get("RABBIT_PASSWORD")

    # Connect to vCenter
    vc = VCenterClient(vcenter)
    conn_status, si = vc.connect_vc(vc_user=vc_user, vc_pass=vc_password)
    if conn_status != "Connected":
        logger.error("Could not connect to vCenter.  Exiting program")
        sys.exit(1)

    # Create the event collector
    byTime = vim.event.EventFilterSpec.ByTime(beginTime=si.CurrentTime())
    filterSpec = vim.event.EventFilterSpec(time=byTime)
    event_collector = si.content.eventManager.CreateCollector(filterSpec)

    # Connect to rabbit mq and create a channel
    channel = connect_rabbitmq(
        f"{rabbit_host}", rabbit_port, rabbit_user, rabbit_password
    )

    # Listen for events and push them to listener
    try:
        await create_event_publisher(event_collector, channel, vcenter)

    # Remove event collector
    finally:
        event_collector.Remove()


if __name__ == "__main__":
    asyncio.run(main())
