---
layout: default
title: Working with Jupyter
parent: Development
nav_order: 5
has_toc: false
---

# Working with Jupyter

Communication within the Jupyter framework is all done via
[messaging](https://jupyter-client.readthedocs.io/en/latest/messaging.html),
allowing for asynchronous communication.

These messages are transferred over one of 5 different channels, each of which
has its purpose.


## Channels

* **Shell**: Used for requests and replies. This is the channel that should be
used for any custom defined action.

* **IOPub**: Used for "broadcast" messages, including the contents of stdout,
stderr, and any communication regarding what is going on inside the kernel.

* **stdin**: This channel is used to accept custom input from the front-end
when prompted by the user or kernel. This will be used for when the the LLM
agent requires asking the user questions to be able to accomplish its task.

* **Control**: This is a specialized channel that controls things like shutdown
and debug messages. You probably won't need to ever need to access this channel
directly.

* **Heartbeat**: This channel allows for a simple "ping" heartbeat check to
ensure that the connection is valid and working.


## Message format

All Jupyter messages generally will have the following format:

```json
{
  "header" : {},
  "parent_header": {},
  "metadata": {},
  "content": {},
  "buffers": [],
}
```

All of the items above are required to be defined, but may be left empty as
needed (i.e. `{}` or `[]`).

### header

All messages must have a header with the following format:

Format:
```js
{
    "msg_id": str,    // Message ID, typically a UUID, must be unique per message
    "session": str,   // Session ID, typically a UUID, should be unique per session
    "username": str,  // Username responsible for message or a blank string
    "date": str,      // ISO 8601 timestamp for when the message is created
    "msg_type": str,  // A built-in Jupter message type or a custom defined message for a specific context
    "version": "5.0", // The message protocol version
}
```
[See here for a list of all jupyter built-in message types.](https://jupyter-client.readthedocs.io/en/latest/messaging.html#messages-on-the-shell-router-dealer-channel)


### parent_header

If a message is a reply to or is created by the actions resulting from a
request message, this should contain the contents of this "parent" message.

For example, if a message came in with this header:
```js
{
  "header": {
    "msg_id": "a961fffd-70a0-4ea2-91ba-1e8a40406ccb",
    "session": "e36352db-af5a-4fcc-bc36-79795726295d",
    "username": "",
    "date": "2023-12-04T22:39:53Z",
    "msg_type": "execute_request",
    "version": "5.0"
  },
  "parent_header": {},
  ...
}
```

Then a response message should look something like this:
```js
{
  "header": {
    "msg_id": "3a300b25-a03a-45a4-ac50-635aece9c40f",
    "session": "e36352db-af5a-4fcc-bc36-79795726295d",
    "username": "",
    "date": "2023-12-04T22:39:56Z",
    "msg_type": "execute_reply",
    "version": "5.0"
  },
  "parent_header": {
    "msg_id": "a961fffd-70a0-4ea2-91ba-1e8a40406ccb",
    "session": "e36352db-af5a-4fcc-bc36-79795726295d",
    "username": "",
    "date": "2023-12-04T22:39:53Z",
    "msg_type": "execute_request",
    "version": "5.0"
  },
  ...
}
```

And an message announcing some stdout output generated during the execution
would look like this:
```js
{
  "header": {
    "msg_id": "0f66541d-23e6-497c-bdf1-96d5cdfa224a",
    "session": "e36352db-af5a-4fcc-bc36-79795726295d",
    "username": "",
    "date": "2023-12-04T22:39:55Z",
    "msg_type": "stream",
    "version": "5.0"
  },
  "parent_header": {
    "msg_id": "a961fffd-70a0-4ea2-91ba-1e8a40406ccb",
    "session": "e36352db-af5a-4fcc-bc36-79795726295d",
    "username": "",
    "date": "2023-12-04T22:39:53Z",
    "msg_type": "execute_request",
    "version": "5.0"
  },
  ...
}
```


### metadata

Metadata can be any content and behaves like you probably expect metadata to
behave. Certain message types behave differently based on the provided metadata,
dependent on message type.


### content

The content of the message is the main body of the message. The content's schema
and requirements is dictated by the message type.


### buffers

Buffers are used to transfer binary data that may be used by a message handler
that does not fit in the content. This is not commonly used and can generally be
safely ignored.
