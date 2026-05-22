---
layout: default
title: Custom Messages
parent: Context Development
grand_parent: Development
nav_order: 2
has_toc: true
---

# Custom Messages

Beaker allows you to define custom messages to communicate with your front-end,
allowing you to call custom functions in your context, or to trigger
updates/changes in your front-end environment.

This can be used to provide automatic updating of a preview widget of variables
being used within a notebook environment.

## Custom message flow

Custom messages can flow in either directions.

The front-end can send a "request" message over the `shell` channel, requesting
that the kernel take some action and return a "reply" message when complete.

Alternatively, the kernel can send a custom message at any time on the `iopub`
channel that the front-end is listening for and triggers an update based on the
message.

## Parts of a custom message

All custom messages should always conform to the structure of the
[Jupyter message format](./jupyter.html#message-format).

### Requests/Replies

The most common way to think about custom requests is that they are like an
asynchronous remote-procedure-call with result handling via callbacks.

Like with `execute`, custom messages start with a `request` and end with a
`reply`.

When working with request/reply custom messages, the `msg_type` attribute of the
message will consist of the custom message prefix and a standard message
postfix for the common types.

For example, if you wanted to have a custom message for saving a variable in the
to an external store, you might want to have a "save_var" message type. In this
case, you will start by sending a `save_var_request` message from the front-end
to Beaker.

The kernel may then send any other messages, including
`stdout`/`stderr` messages over the `iopub` channel, `save_var_response` over
the `iopub` channel to return details about the save such as the variable's new
ID in the datastore.

Finally, the kernel should return a message of type `save_var_reply` which
should always be the final message of the flow and indicates that the request is
complete, along with the final status in the message payload.
