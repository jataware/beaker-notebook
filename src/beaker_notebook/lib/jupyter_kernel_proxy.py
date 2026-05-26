#!/usr/bin/env python
# -*- encoding: utf8 -*-
#
# Copyright (c) 2022 ESET spol. s r.o.
# Author: Marc-Etienne M.Léveillé <leveille@eset.com>
# See LICENSE file for redistribution.

import datetime
import glob
import hashlib
import hmac
import json
import logging
import os
import uuid
from collections import OrderedDict, namedtuple
from operator import attrgetter

import six
import zmq
from jupyter_core.paths import jupyter_runtime_dir
from tornado import ioloop
from zmq.eventloop import zmqstream

logger = logging.getLogger(__name__)


SocketInfo = namedtuple(
    "SocketInfo",
    (
        "name",
        "server_type",
        "client_type",
        "signed",
    ),
)

KERNEL_SOCKETS = (
    SocketInfo("hb", zmq.REP, zmq.REQ, False),
    SocketInfo("iopub", zmq.PUB, zmq.SUB, True),
    SocketInfo("control", zmq.ROUTER, zmq.DEALER, True),
    SocketInfo("stdin", zmq.ROUTER, zmq.DEALER, True),
    SocketInfo("shell", zmq.ROUTER, zmq.DEALER, True),
)

KERNEL_SOCKETS_NAMES = tuple(map(attrgetter("name"), KERNEL_SOCKETS))

SocketGroup = namedtuple("SocketGroup", KERNEL_SOCKETS_NAMES)

JupyterMessageTuple = namedtuple(
    "JupyterMessageTuple",
    (
        "identities",  # -type: list of byte strings # "<IDS|MSG>" delimiter goes here
        "signature",  # -type: bytes
        "header",  #
        "parent_header",  # -type: dict or bytes (JSON)
        "metadata",  #
        "content",  #
        "buffers",  # -type: list of byte strings
    ),
)


class JupyterMessage(JupyterMessageTuple):
    # As defined here:
    # https://jupyter-client.readthedocs.io/en/stable/messaging.html#the-wire-protocol
    DELIMITER = b"<IDS|MSG>"

    @classmethod
    def parse(cls, parts, verify_using=None):
        i = parts.index(cls.DELIMITER)
        if i < 0:
            raise ValueError
        identities = parts[:i]
        signature = parts[i + 1]
        payloads = parts[i + 2 : i + 6]
        buffers = parts[i + 6 :]
        raw_msg = cls._make([identities, signature] + payloads + [buffers])
        if verify_using and not raw_msg.has_valid_signature(verify_using):
            raise ValueError("Signature verification failed")
        return raw_msg.parsed

    @property
    def _json_fields_slice(self):
        return slice(2, 6)

    @property
    def json_fields(self):
        return self[self._json_fields_slice]

    @property
    def json_field_names(self):
        return self._fields[self._json_fields_slice]

    @property
    def parsed(self):
        def ensure_parsed(field):
            if isinstance(field, six.binary_type):
                return json.loads(field)
            else:
                return field

        parsed_fields = [ensure_parsed(f) for f in self.json_fields]
        return self._replace(**dict(zip(self.json_field_names, parsed_fields)))

    @property
    def serialized(self):
        def ensure_serialized(field):
            if not isinstance(field, six.binary_type):
                return six.ensure_binary(json.dumps(field))
            else:
                return field

        serialized_fields = [ensure_serialized(f) for f in self.json_fields]
        return self._replace(**dict(zip(self.json_field_names, serialized_fields)))

    @property
    def parts(self):
        return (
            self.identities
            + [self.DELIMITER, self.signature]
            + list(self.serialized.json_fields)
            + self.buffers
        )

    def _compute_signature(self, key):
        h = hmac.HMAC(six.ensure_binary(key), digestmod=hashlib.sha256)
        for f in list(self.serialized.json_fields) + self.buffers:
            h.update(six.ensure_binary(f))
        return six.ensure_binary(h.hexdigest())

    def has_valid_signature(self, key):
        return self.signature == self._compute_signature(key)

    def sign_using(self, key):
        return self._replace(signature=self._compute_signature(key))


class AbstractProxyKernel(object):
    def __init__(self, config, role, zmq_context=zmq.Context.instance(), session_id=None):
        self.session_id = session_id
        if role not in ("server", "client"):
            raise ValueError("role value must be 'server' or 'client'")
        self.role = role
        self.config = config.copy()
        self.zmq_context = zmq_context
        if role == "server":
            self._create_sockets("bind")
        elif role == "client":
            self._create_sockets("connect")

    def _url_for_port(self, port):
        return "{:s}://{:s}:{:d}".format(
            self.config.get("transport", "tcp"),
            self.config.get("ip", "localhost"),
            port,
        )

    def _create_sockets(self, bind_or_connect):
        if bind_or_connect not in ("bind", "connect"):
            raise ValueError("bind_or_connect must be 'bind' or 'connect'")
        ctx = self.zmq_context
        zmq_type_key = self.role + "_type"
        self.sockets = SocketGroup(
            *[ctx.socket(getattr(s, zmq_type_key)) for s in KERNEL_SOCKETS]
        )
        for i, sock in enumerate(KERNEL_SOCKETS):
            sock_bind = getattr(self.sockets[i], bind_or_connect)
            sock_bind(self._url_for_port(self.config.get(sock.name + "_port", 0)))
            if getattr(sock, zmq_type_key) == zmq.SUB:
                self.sockets[i].setsockopt(zmq.SUBSCRIBE, b"")
        self.streams = SocketGroup(*map(zmqstream.ZMQStream, self.sockets))

    def sign(self, message, key=None):
        if key is None:
            key = self.config.get("key")
        h = hmac.HMAC(six.ensure_binary(key), digestmod=hashlib.sha256)
        for m in message:
            h.update(m)
        return six.ensure_binary(h.hexdigest())

    def make_multipart_message(
        self, msg_type, content={}, parent_header={}, metadata={}, msg_id=None, identities=None, session_id=None,
    ):
        if msg_id is None:
            msg_id = str(uuid.uuid4())

        session_id = session_id or self.session_id or str(uuid.uuid4())

        if identities is None:
            identities = []

        if parent_header is None:
            parent_header = {}

        header = {
            "date": datetime.datetime.now().isoformat(),
            "msg_id": msg_id,
            "username": "kernel",
            "session": session_id,
            "msg_type": msg_type,
            "version": "5.0",
        }
        msg = JupyterMessage(identities, None, header, parent_header, metadata, content, [])
        return msg.sign_using(self.config.get("key")).parts


class ProxyKernelClient(AbstractProxyKernel):
    def __init__(self, config, role="client", zmq_context=zmq.Context.instance(), session_id=None):
        super(ProxyKernelClient, self).__init__(config, role, zmq_context, session_id=session_id)


InterceptionFilter = namedtuple(
    "InterceptionFilter", ("stream_type", "msg_type", "callback")
)


class ProxyKernelServer(AbstractProxyKernel):
    def __init__(self, config, role="server", zmq_context=zmq.Context.instance(), session_id=None):
        self.manager = None
        super(ProxyKernelServer, self).__init__(config, role, zmq_context, session_id=session_id)
        self.filters = []
        self.session_id = session_id
        self.proxy_target = None

    def _proxy_to(
        self, other_stream, socktype=None, validate_using=None, resign_using=None
    ):
        # request
        # Notebook -> ProxyServer -> ProxyClient -> Real kernel
        # reply
        # Notebook <- ProxyServer <- ProxyClient <- Real kernel
        is_reply = other_stream in self.streams
        if is_reply:
            validate_using = validate_using or self.proxy_target.config.get("key")
            resign_using = resign_using or self.config.get("key")
        else:
            validate_using = validate_using or self.config.get("key")
            resign_using = resign_using or self.proxy_target.config.get("key")

        async def handler(data):
            if socktype.signed:
                msg = JupyterMessage.parse(data, validate_using)
                if is_reply and msg.header.get("msg_type", "").endswith("_reply"):
                    if not isinstance(msg.identities, list):
                        msg.identities = []
                    if self.session_id and self.session_id not in msg.identities:
                        msg.identities.append(msg.parent_header.get("session"))
                for stream_type, msg_type, callback in self.filters:
                    if stream_type == socktype and msg_type == msg.header.get(
                        "msg_type"
                    ):
                        new_data = await callback(self, other_stream, data)
                        if new_data is None:
                            return
                        else:
                            data = new_data
                if resign_using:
                    data = JupyterMessage.parse(data).sign_using(resign_using).parts
            other_stream.send_multipart(data)
            other_stream.flush()
        return handler

    def set_proxy_target(self, proxy_client):

        if self.proxy_target is not None:
            for stream in self.proxy_target.streams:
                stream.stop_on_recv()
        self.proxy_target = proxy_client
        for i, socktype in enumerate(KERNEL_SOCKETS):
            if socktype.server_type != zmq.PUB:
                self.streams[i].on_recv(
                    self._proxy_to(proxy_client.streams[i], socktype=socktype)
                )
            if socktype.client_type != zmq.PUB:
                proxy_client.streams[i].on_recv(
                    self._proxy_to(self.streams[i], socktype=socktype)
                )

    def intercept_message(self, stream_type=None, msg_type=None, callback=None):
        if stream_type in KERNEL_SOCKETS_NAMES:
            stream_type = KERNEL_SOCKETS[KERNEL_SOCKETS_NAMES.index(stream_type)]
        if stream_type not in KERNEL_SOCKETS:
            raise ValueError(
                "stream_type should be one of " + ", ".join(KERNEL_SOCKETS_NAMES)
            )
        if not callable(callback):
            raise ValueError("callback must be callable")
        self.filters.append(InterceptionFilter(stream_type, msg_type, callback))


class KernelProxyManager(object):
    def __init__(self, server, session_id=None):
        if isinstance(server, ProxyKernelServer):
            self.server = server
        else:
            self.server = ProxyKernelServer(server, session_id=session_id)
        self.server.manager = self

        self.session_id = session_id
        self._kernel_info_requests = []
        self.server.intercept_message(
            "shell", "kernel_info_request", self._on_kernel_info_request
        )
        self.server.intercept_message(
            "shell", "kernel_info_reply", self._on_kernel_info_reply
        )

    def update_running_kernels(self):
        "Update self.kernels with an ordered dict where keys are file name and"
        "values are the configuration (file content) as dict"

        from beaker_kernel.lib.config import config as beaker_config

        kernelfile_dir = os.path.join(beaker_config.beaker_run_path, "kernelfiles")
        files = glob.glob(os.path.join(jupyter_runtime_dir(), "kernel-*.json"))
        if kernelfile_dir:
            files += glob.glob(os.path.join(kernelfile_dir, "kernel-*.json"))

        self.kernels = OrderedDict()
        for path in reversed(sorted(files, key=lambda f: os.stat(f).st_atime)):
            try:
                filename = os.path.basename(path)
                with open(path, "r") as f:
                    config = json.load(f)
                    if config != self.server.config:
                        self.kernels[filename] = config
            except:
                # print something to stderr
                pass
        return self.kernels

    async def _on_kernel_info_request(self, server, target_stream, data):
        msg = JupyterMessage.parse(data)
        self._kernel_info_requests.append(msg.header.get("msg_id"))
        ioloop.IOLoop.current().call_later(3, self._send_proxy_kernel_info, data)
        return data

    async def _on_kernel_info_reply(self, server, target_stream, data):
        msg = JupyterMessage.parse(data)
        if msg.parent_header.get("msg_id") in self._kernel_info_requests:
            self._kernel_info_requests.remove(msg.parent_header.get("msg_id"))
        elif len(self._kernel_info_requests) > 0:
            self._kernel_info_requests.pop(0)
        return data

    async def _send_proxy_kernel_info(self, request):
        parent = JupyterMessage.parse(request)
        if not parent.header.get("msg_id") in self._kernel_info_requests:
            return
        msg = self.server.make_multipart_message(
            "kernel_info_reply",
            {
                "status": "ok",
                "protocol_version": "5.3",
                "implementation": "proxy",
                "banner": "Jupyter kernel proxy. Not connected or connected to unresponsive kernel. Use %proxy to connect.",
                "language_info": {
                    "name": "magic",
                },
            },
            parent_header=parent.header,
        )
        self.server.streams.shell.send_multipart(parent.identities + msg)
        self.server.streams.iopub.send_multipart(
            self.server.make_multipart_message(
                "stream",
                {
                    "name": "stderr",
                    "text": "Target kernel did not reply. "
                    "Use `%proxy list` and `%proxy connect` to use to "
                    "another kernel.",
                },
            )
        )
        self.server.streams.iopub.send_multipart(
            self.server.make_multipart_message(
                "status", {"execution_state": "idle"}, parent_header=parent.header
            )
        )
        self._kernel_info_requests.remove(parent.header.get("msg_id"))

    def connect_to(self, kernel_file_name):
        matching = next((n for n in self.kernels if kernel_file_name in n), None)
        if matching is None:
            raise ValueError("Unknown kernel " + kernel_file_name)
        if self.kernels[matching] == self.server.config:
            raise ValueError("Refusing loopback connection")
        self.connected_kernel_name = matching
        self.connected_kernel = ProxyKernelClient(self.kernels[matching], session_id=self.session_id)
        self.server.set_proxy_target(self.connected_kernel)
