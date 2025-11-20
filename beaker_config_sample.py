# ===========================================
# Beaker Notebook Service Configuration File
# ===========================================
# This file demonstrates all configurable traitlets in the Beaker Notebook service.
# Copy this file to jupyter_server_config.py or beaker_config.py in your Jupyter config directory.
# Uncomment and modify values as needed for your deployment.

c = get_config()  # noqa

#------------------------------------------------------------------------------
# BaseBeakerApp(ServerApp) configuration
#------------------------------------------------------------------------------
## Customizable ServerApp for use with Beaker

## Username for the Beaker kernel agent process
#  Default: ''
# c.BaseBeakerApp.agent_user = ''

## Set the Access-Control-Allow-Credentials: true header
#  Default: False
# c.BaseBeakerApp.allow_credentials = False

## Whether or not to allow external kernels, whose connection files are placed in
#  external_connection_dir.
#  Default: False
# c.BaseBeakerApp.allow_external_kernels = False

#  Default: '*'
# c.BaseBeakerApp.allow_origin = '*'

## Use a regular expression for the Access-Control-Allow-Origin header
#
#          Requests from an origin matching the expression will get replies with:
#
#              Access-Control-Allow-Origin: origin
#
#          where `origin` is the origin of the request.
#
#          Ignored if allow_origin is set.
#  Default: ''
# c.BaseBeakerApp.allow_origin_pat = ''

## Allow requests where the Host header doesn't point to a local server
#
#         By default, requests get a 403 forbidden response if the 'Host' header
#         shows that the browser thinks it's on a non-local domain.
#         Setting this option to True disables this check.
#
#         This protects against 'DNS rebinding' attacks, where a remote web server
#         serves you a page and then changes its DNS to send later requests to a
#         local IP, bypassing same-origin checks.
#
#         Local IP addresses (such as 127.0.0.1 and ::1) are allowed as local,
#         along with hostnames configured in local_hostnames.
#  Default: False
# c.BaseBeakerApp.allow_remote_access = False

## Whether to allow the user to run the server as root.
#  Default: False
# c.BaseBeakerApp.allow_root = False

## Allow unauthenticated access to endpoints without authentication rule.
#
#          When set to `True` (default in jupyter-server 2.0, subject to change
#          in the future), any request to an endpoint without an authentication rule
#          (either `@tornado.web.authenticated`, or `@allow_unauthenticated`)
#          will be permitted, regardless of whether user has logged in or not.
#
#          When set to `False`, logging in will be required for access to each endpoint,
#          excluding the endpoints marked with `@allow_unauthenticated` decorator.
#
#          This option can be configured using `JUPYTER_SERVER_ALLOW_UNAUTHENTICATED_ACCESS`
#          environment variable: any non-empty value other than "true" and "yes" will
#          prevent unauthenticated access to endpoints without `@allow_unauthenticated`.
#  Default: True
# c.BaseBeakerApp.allow_unauthenticated_access = True

## Answer yes to any prompts.
#  Default: False
# c.BaseBeakerApp.answer_yes = False

#  Default: ''
# c.BaseBeakerApp.app_slug = ''

## "
#          Require authentication to access prometheus metrics.
#  Default: True
# c.BaseBeakerApp.authenticate_prometheus = True

## The authorizer class to use.
#  Default: 'jupyter_server.auth.authorizer.AllowAllAuthorizer'
# c.BaseBeakerApp.authorizer_class = 'jupyter_server.auth.authorizer.AllowAllAuthorizer'

## Reload the webapp when changes are made to any Python src files.
#  Default: False
# c.BaseBeakerApp.autoreload = False

## The base URL for the Jupyter server.
#
#                         Leading and trailing slashes can be omitted,
#                         and will automatically be added.
#  Default: '/'
# c.BaseBeakerApp.base_url = '/'

#  Default: traitlets.Undefined
# c.BaseBeakerApp.beaker_config_path = traitlets.Undefined

#  Default: {}
# c.BaseBeakerApp.beaker_extension_app = {}

## Specify what command to use to invoke a web
#                        browser when starting the server. If not specified, the
#                        default browser will be determined by the `webbrowser`
#                        standard library module, which allows setting of the
#                        BROWSER environment variable to override it.
#  Default: ''
# c.BaseBeakerApp.browser = ''

## The full path to an SSL/TLS certificate file.
#  Default: ''
# c.BaseBeakerApp.certfile = ''

## The full path to a certificate authority certificate for SSL/TLS client
#  authentication.
#  Default: ''
# c.BaseBeakerApp.client_ca = ''

## Full path of a config file.
#  Default: ''
# c.BaseBeakerApp.config_file = ''

#  Default: ''
# c.BaseBeakerApp.config_file_name = ''

## The config manager class to use
#  Default: 'jupyter_server.services.config.manager.ConfigManager'
# c.BaseBeakerApp.config_manager_class = 'jupyter_server.services.config.manager.ConfigManager'

#  Default: ''
# c.BaseBeakerApp.connection_dir = ''

## The random bytes used to secure cookies.
#          By default this is generated on first start of the server and persisted across server
#          sessions by writing the cookie secret into the `cookie_secret_file` file.
#          When using an executable config file you can override this to be random at each server restart.
#
#          Note: Cookie secrets should be kept private, do not share config files with
#          cookie_secret stored in plaintext (you can read the value from a file).
#  Default: b''
# c.BaseBeakerApp.cookie_secret = b''

## The file where the cookie secret is stored.
#  Default: ''
# c.BaseBeakerApp.cookie_secret_file = ''

## Override URL shown to users.
#
#          Replace actual URL, including protocol, address, port and base URL,
#          with the given value when displaying URL to the users. Do not change
#          the actual connection URL. If authentication token is enabled, the
#          token is added to the custom URL automatically.
#
#          This option is intended to be used when the URL to display to the user
#          cannot be determined reliably by the Jupyter server (proxified
#          or containerized setups for example).
#  Default: ''
# c.BaseBeakerApp.custom_display_url = ''

## The default URL to redirect to from `/`
#  Default: '/'
# c.BaseBeakerApp.default_url = '/'

#  Default: '/'
# c.BaseBeakerApp.extension_url = '/'

## The directory to look at for external kernel connection files, if
#  allow_external_kernels is True. Defaults to Jupyter
#  runtime_dir/external_kernels. Make sure that this directory is not filled with
#  left-over connection files, that could result in unnecessary kernel manager
#  creations.
#  Default: None
# c.BaseBeakerApp.external_connection_dir = None

## handlers that should be loaded at higher priority than the default services
#  Default: []
# c.BaseBeakerApp.extra_services = []

## Extra paths to search for serving static files.
#
#          This allows adding javascript/css to be available from the Jupyter server machine,
#          or overriding individual files in the IPython
#  Default: []
# c.BaseBeakerApp.extra_static_paths = []

## Extra paths to search for serving jinja templates.
#
#          Can be used to override templates from jupyter_server.templates.
#  Default: []
# c.BaseBeakerApp.extra_template_paths = []

## Open the named file when the application is launched.
#  Default: ''
# c.BaseBeakerApp.file_to_run = ''

## The URL prefix where files are opened directly.
#  Default: 'notebooks'
# c.BaseBeakerApp.file_url_prefix = 'notebooks'

## Generate default config file.
#  Default: False
# c.BaseBeakerApp.generate_config = False

## The identity provider class to use.
#  Default: 'jupyter_server.auth.identity.PasswordIdentityProvider'
# c.BaseBeakerApp.identity_provider_class = 'jupyter_server.auth.identity.PasswordIdentityProvider'

## The IP address the Jupyter server will listen on.
#  Default: 'localhost'
# c.BaseBeakerApp.ip = 'localhost'

## Supply extra arguments that will be passed to Jinja environment.
#  Default: {}
# c.BaseBeakerApp.jinja_environment_options = {}

## Extra variables to supply to jinja templates when rendering.
#  Default: {}
# c.BaseBeakerApp.jinja_template_vars = {}

## Dict of Python modules to load as Jupyter server extensions.Entry values can
#  be used to enable and disable the loading ofthe extensions. The extensions
#  will be loaded in alphabetical order.
#  Default: {}
# c.BaseBeakerApp.jpserver_extensions = {}

## Include local kernel specs
#  Default: True
# c.BaseBeakerApp.kernel_spec_include_local = True

## Kernel specification managers indexed by extension name
#  Default: {}
# c.BaseBeakerApp.kernel_spec_managers = {}

## The kernel websocket connection class to use.
#  Default: 'jupyter_server.services.kernels.connection.base.BaseKernelWebsocketConnection'
# c.BaseBeakerApp.kernel_websocket_connection_class = 'jupyter_server.services.kernels.connection.base.BaseKernelWebsocketConnection'

## The full path to a private key file for usage with SSL/TLS.
#  Default: ''
# c.BaseBeakerApp.keyfile = ''

## Hostnames to allow as local when allow_remote_access is False.
#
#         Local IP addresses (such as 127.0.0.1 and ::1) are automatically accepted
#         as local as well.
#  Default: ['localhost']
# c.BaseBeakerApp.local_hostnames = ['localhost']

## The date format used by logging formatters for %(asctime)s
#  Default: '%Y-%m-%d %H:%M:%S'
# c.BaseBeakerApp.log_datefmt = '%Y-%m-%d %H:%M:%S'

## The Logging format template
#  Default: '[%(name)s]%(highlevel)s %(message)s'
# c.BaseBeakerApp.log_format = '[%(name)s]%(highlevel)s %(message)s'

## Set the log level by value or name.
#  Choices: any of [0, 10, 20, 30, 40, 50, 'DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL']
#  Default: 30
# c.BaseBeakerApp.log_level = 30

## Enable request logging
#  Default: False
# c.BaseBeakerApp.log_requests = False

## Configure additional log handlers.
#
#  The default stderr logs handler is configured by the log_level, log_datefmt
#  and log_format settings.
#
#  This configuration can be used to configure additional handlers (e.g. to
#  output the log to a file) or for finer control over the default handlers.
#
#  If provided this should be a logging configuration dictionary, for more
#  information see:
#  https://docs.python.org/3/library/logging.config.html#logging-config-
#  dictschema
#
#  This dictionary is merged with the base logging configuration which defines
#  the following:
#
#  * A logging formatter intended for interactive use called
#    ``console``.
#  * A logging handler that writes to stderr called
#    ``console`` which uses the formatter ``console``.
#  * A logger with the name of this application set to ``DEBUG``
#    level.
#
#  This example adds a new handler that writes to a file:
#
#  .. code-block:: python
#
#     c.Application.logging_config = {
#         "handlers": {
#             "file": {
#                 "class": "logging.FileHandler",
#                 "level": "DEBUG",
#                 "filename": "<path/to/file>",
#             }
#         },
#         "loggers": {
#             "<application-name>": {
#                 "level": "DEBUG",
#                 # NOTE: if you don't list the default "console"
#                 # handler here then it will be disabled
#                 "handlers": ["console", "file"],
#             },
#         },
#     }
#  Default: {}
# c.BaseBeakerApp.logging_config = {}

## The login handler class to use.
#  Default: 'jupyter_server.auth.login.LegacyLoginHandler'
# c.BaseBeakerApp.login_handler_class = 'jupyter_server.auth.login.LegacyLoginHandler'

## The logout handler class to use.
#  Default: 'jupyter_server.auth.logout.LogoutHandler'
# c.BaseBeakerApp.logout_handler_class = 'jupyter_server.auth.logout.LogoutHandler'

## Sets the maximum allowed size of the client request body, specified in the
#  Content-Length request header field. If the size in a request exceeds the
#  configured value, a malformed HTTP message is returned to the client.
#
#  Note: max_body_size is applied even in streaming mode.
#  Default: 536870912
# c.BaseBeakerApp.max_body_size = 536870912

## Gets or sets the maximum amount of memory, in bytes, that is allocated for use
#  by the buffer manager.
#  Default: 536870912
# c.BaseBeakerApp.max_buffer_size = 536870912

## Gets or sets a lower bound on the open file handles process resource limit.
#  This may need to be increased if you run into an OSError: [Errno 24] Too many
#  open files. This is not applicable when running on Windows.
#  Default: 0
# c.BaseBeakerApp.min_open_files_limit = 0

#  Default: 'beaker'
# c.BaseBeakerApp.name = 'beaker'

#  Default: False
# c.BaseBeakerApp.open_browser = False

## The port the server will listen on (env: JUPYTER_PORT).
#  Default: 0
# c.BaseBeakerApp.port = 0

## The number of additional ports to try if the specified port is not available
#  (env: JUPYTER_PORT_RETRIES).
#  Default: 50
# c.BaseBeakerApp.port_retries = 50

## DISABLED: use %pylab or %matplotlib in the notebook to enable matplotlib.
#  Default: 'disabled'
# c.BaseBeakerApp.pylab = 'disabled'

## If True, display controls to shut down the Jupyter server, such as menu items
#  or buttons.
#  Default: True
# c.BaseBeakerApp.quit_button = True

## The directory to use for notebooks and kernels.
#  Default: ''
# c.BaseBeakerApp.root_dir = ''

## Username under which the Beaker service is running
#  Default: ''
# c.BaseBeakerApp.service_user = ''

## Instead of starting the Application, dump configuration to stdout
#  Default: False
# c.BaseBeakerApp.show_config = False

## Instead of starting the Application, dump configuration to stdout (as JSON)
#  Default: False
# c.BaseBeakerApp.show_config_json = False

## Shut down the server after N seconds with no kernelsrunning and no activity.
#  This can be used together with culling idle kernels
#  (MappingKernelManager.cull_idle_timeout) to shutdown the Jupyter server when
#  it's not in use. This is not precisely timed: it may shut down up to a minute
#  later. 0 (the default) disables this automatic shutdown.
#  Default: 0
# c.BaseBeakerApp.shutdown_no_activity_timeout = 0

## The UNIX socket the Jupyter server will listen on.
#  Default: ''
# c.BaseBeakerApp.sock = ''

## The permissions mode for UNIX socket creation (default: 0600).
#  Default: '0600'
# c.BaseBeakerApp.sock_mode = '0600'

## Supply SSL options for the tornado HTTPServer.
#              See the tornado docs for details.
#  Default: {}
# c.BaseBeakerApp.ssl_options = {}

## Paths to set up static files as immutable.
#
#  This allow setting up the cache control of static files as immutable. It
#  should be used for static file named with a hash for instance.
#  Default: []
# c.BaseBeakerApp.static_immutable_cache = []

## Username under which subkernels (Python, R, etc.) are executed
#  Default: ''
# c.BaseBeakerApp.subkernel_user = ''

## Supply overrides for terminado. Currently only supports "shell_command".
#  Default: {}
# c.BaseBeakerApp.terminado_settings = {}

## Set to False to disable terminals.
#
#           This does *not* make the server more secure by itself.
#           Anything the user can in a terminal, they can also do in a notebook.
#
#           Terminals may also be automatically disabled if the terminado package
#           is not available.
#  Default: False
# c.BaseBeakerApp.terminals_enabled = False

## Supply overrides for the tornado.web.Application that the Jupyter server uses.
#  Default: {}
# c.BaseBeakerApp.tornado_settings = {}

## Whether to trust or not X-Scheme/X-Forwarded-Proto and X-Real-Ip/X-Forwarded-
#  For headerssent by the upstream reverse proxy. Necessary if the proxy handles
#  SSL
#  Default: False
# c.BaseBeakerApp.trust_xheaders = False

## Working directory for kernel execution and file operations
#  Default: ''
# c.BaseBeakerApp.ui_path = ''

## Disable launching browser by redirect file
#       For versions of notebook > 5.7.2, a security feature measure was added that
#       prevented the authentication token used to launch the browser from being visible.
#       This feature makes it difficult for other users on a multi-user system from
#       running code in your Jupyter session as you.
#       However, some environments (like Windows Subsystem for Linux (WSL) and Chromebooks),
#       launching a browser using a redirect file can lead the browser failing to load.
#       This is because of the difference in file structures/paths between the runtime and
#       the browser.
#
#       Disabling this setting to False will disable this behavior, allowing the browser
#       to launch by using a URL and visible token (as before).
#  Default: True
# c.BaseBeakerApp.use_redirect_file = True

## Specify where to open the server on startup. This is the
#          `new` argument passed to the standard library method `webbrowser.open`.
#          The behaviour is not guaranteed, but depends on browser support. Valid
#          values are:
#
#           - 2 opens a new tab,
#           - 1 opens a new window,
#           - 0 opens in an existing window.
#
#          See the `webbrowser.open` documentation for details.
#  Default: 2
# c.BaseBeakerApp.webbrowser_open_new = 2

## Set the tornado compression options for websocket connections.
#
#  This value will be returned from
#  :meth:`WebSocketHandler.get_compression_options`. None (default) will disable
#  compression. A dict (even an empty one) will enable compression.
#
#  See the tornado docs for WebSocketHandler.get_compression_options for details.
#  Default: None
# c.BaseBeakerApp.websocket_compression_options = None

## Configure the websocket ping interval in seconds.
#
#  Websockets are long-lived connections that are used by some Jupyter Server
#  extensions.
#
#  Periodic pings help to detect disconnected clients and keep the connection
#  active. If this is set to None, then no pings will be performed.
#
#  When a ping is sent, the client has ``websocket_ping_timeout`` seconds to
#  respond. If no response is received within this period, the connection will be
#  closed from the server side.
#  Default: 0
# c.BaseBeakerApp.websocket_ping_interval = 0

## Configure the websocket ping timeout in seconds.
#
#  See ``websocket_ping_interval`` for details.
#  Default: 0
# c.BaseBeakerApp.websocket_ping_timeout = 0

## The base URL for websockets,
#          if it differs from the HTTP server (hint: it almost certainly doesn't).
#
#          Should be in the form of an HTTP origin: ws[s]://hostname[:port]
#  Default: ''
# c.BaseBeakerApp.websocket_url = ''

## Working directory for kernel execution and file operations
#  Default: ''
# c.BaseBeakerApp.working_dir = ''

#------------------------------------------------------------------------------
# BeakerIdentityProvider(IdentityProvider) configuration
#------------------------------------------------------------------------------
## Header name for Beaker kernel authentication
#  Default: 'X-AUTH-BEAKER'
# c.BeakerIdentityProvider.beaker_kernel_header = 'X-AUTH-BEAKER'

## Name of the cookie to set for persisting login. Default: username-${Host}.
#  Default: ''
# c.BeakerIdentityProvider.cookie_name = ''

## Extra keyword arguments to pass to `set_secure_cookie`. See tornado's
#  set_secure_cookie docs for details.
#  Default: {}
# c.BeakerIdentityProvider.cookie_options = {}

## Extra keyword arguments to pass to `get_secure_cookie`. See tornado's
#  get_secure_cookie docs for details.
#  Default: {}
# c.BeakerIdentityProvider.get_secure_cookie_kwargs = {}

## The login handler class to use, if any.
#  Default: 'jupyter_server.auth.login.LoginFormHandler'
# c.BeakerIdentityProvider.login_handler_class = 'jupyter_server.auth.login.LoginFormHandler'

## The logout handler class to use.
#  Default: 'jupyter_server.auth.logout.LogoutHandler'
# c.BeakerIdentityProvider.logout_handler_class = 'jupyter_server.auth.logout.LogoutHandler'

## Specify whether login cookie should have the `secure` property (HTTPS-
#  only).Only needed when protocol-detection gives the wrong answer due to
#  proxies.
#  Default: None
# c.BeakerIdentityProvider.secure_cookie = None

## Token used for authenticating first-time connections to the server.
#
#          The token can be read from the file referenced by JUPYTER_TOKEN_FILE or set directly
#          with the JUPYTER_TOKEN environment variable.
#
#          When no password is enabled,
#          the default is to generate a new, random token.
#
#          Setting to an empty string disables authentication altogether, which
#  is NOT RECOMMENDED.
#
#          Prior to 2.0: configured as ServerApp.token
#  Default: '<generated>'
# c.BeakerIdentityProvider.token = '<generated>'


#------------------------------------------------------------------------------
# BeakerContentsManager(AsyncLargeFileManager) configuration
#------------------------------------------------------------------------------
## Allow access to hidden files
#  Default: False
# c.BeakerContentsManager.allow_hidden = False

## If True, deleting a non-empty directory will always be allowed.
#          WARNING this may result in files being permanently removed; e.g. on Windows,
#          if the data size is too big for the trash/recycle bin the directory will be permanently
#          deleted. If False (default), the non-empty directory will be sent to the trash only
#          if safe. And if ``delete_to_trash`` is True, the directory won't be deleted.
#  Default: False
# c.BeakerContentsManager.always_delete_dir = False

#  Default: None
# c.BeakerContentsManager.checkpoints = None

#  Default: 'jupyter_server.services.contents.checkpoints.AsyncCheckpoints'
# c.BeakerContentsManager.checkpoints_class = 'jupyter_server.services.contents.checkpoints.AsyncCheckpoints'

#  Default: {}
# c.BeakerContentsManager.checkpoints_kwargs = {}

## If True (default), deleting files will send them to the
#          platform's trash/recycle bin, where they can be recovered. If False,
#          deleting files really deletes them.
#  Default: True
# c.BeakerContentsManager.delete_to_trash = True

#  Default: None
# c.BeakerContentsManager.event_logger = None

## handler class to use when serving raw file requests.
#
#          Default is a fallback that talks to the ContentsManager API,
#          which may be inefficient, especially for large files.
#
#          Local files-based ContentsManagers can use a StaticFileHandler subclass,
#          which will be much more efficient.
#
#          Access to these files should be Authenticated.
#  Default: 'jupyter_server.files.handlers.FilesHandler'
# c.BeakerContentsManager.files_handler_class = 'jupyter_server.files.handlers.FilesHandler'

## Extra parameters to pass to files_handler_class.
#
#          For example, StaticFileHandlers generally expect a `path` argument
#          specifying the root directory from which to serve files.
#  Default: {}
# c.BeakerContentsManager.files_handler_params = {}

## Hash algorithm to use for file content, support by hashlib
#  Choices: any of ['blake2s', 'md5', 'sha256', 'sha3_512', 'sm3', 'shake_256', 'sha512_256', 'sha3_224', 'ripemd160', 'sha1', 'blake2b', 'sha512', 'sha3_256', 'shake_128', 'sha384', 'sha224', 'sha3_384', 'sha512_224', 'md5-sha1']
#  Default: 'sha256'
# c.BeakerContentsManager.hash_algorithm = 'sha256'

## Glob patterns to hide in file and directory listings.
#  Default: ['__pycache__', '*.pyc', '*.pyo', '.DS_Store', '*~']
# c.BeakerContentsManager.hide_globs = ['__pycache__', '*.pyc', '*.pyo', '.DS_Store', '*~']

## The max folder size that can be copied
#  Default: 500
# c.BeakerContentsManager.max_copy_folder_size_mb = 500

## Python callable or importstring thereof
#
#          to be called on the path of a file just saved.
#
#          This can be used to process the file on disk,
#          such as converting the notebook to a script or HTML via nbconvert.
#
#          It will be called as (all arguments passed by keyword)::
#
#              hook(os_path=os_path, model=model, contents_manager=instance)
#
#          - path: the filesystem path to the file just written
#          - model: the model representing the file
#          - contents_manager: this ContentsManager instance
#  Default: None
# c.BeakerContentsManager.post_save_hook = None

## Python callable or importstring thereof
#
#          To be called on a contents model prior to save.
#
#          This can be used to process the structure,
#          such as removing notebook outputs or other side effects that
#          should not be saved.
#
#          It will be called as (all arguments passed by keyword)::
#
#              hook(path=path, model=model, contents_manager=self)
#
#          - model: the model to be saved. Includes file contents.
#            Modifying this dict will affect the file that is stored.
#          - path: the API path of the save destination
#          - contents_manager: this ContentsManager instance
#  Default: None
# c.BeakerContentsManager.pre_save_hook = None

## Preferred starting directory to use for notebooks. This is an API path (`/`
#  separated, relative to root dir)
#  Default: ''
# c.BeakerContentsManager.preferred_dir = ''

#  Default: ''
# c.BeakerContentsManager.root_dir = ''

## The base name used when creating untitled directories.
#  Default: 'Untitled Folder'
# c.BeakerContentsManager.untitled_directory = 'Untitled Folder'

## The base name used when creating untitled files.
#  Default: 'untitled'
# c.BeakerContentsManager.untitled_file = 'untitled'

## The base name used when creating untitled notebooks.
#  Default: 'Untitled'
# c.BeakerContentsManager.untitled_notebook = 'Untitled'

## By default notebooks are saved on disk on a temporary file and then if successfully written, it replaces the old ones.
#        This procedure, namely 'atomic_writing', causes some bugs on file system without operation order enforcement (like some networked fs).
#        If set to False, the new notebook is written directly on the old one which could fail (eg: full filesystem or quota )
#  Default: True
# c.BeakerContentsManager.use_atomic_writing = True

#------------------------------------------------------------------------------
# BeakerKernelMappingManager(AsyncMappingKernelManager) configuration
#------------------------------------------------------------------------------
## Whether to send tracebacks to clients on exceptions.
#  Default: True
# c.BeakerKernelMappingManager.allow_tracebacks = True

## White list of allowed kernel message types.
#          When the list is empty, all message types are allowed.
#  Default: []
# c.BeakerKernelMappingManager.allowed_message_types = []

## Whether messages from kernels whose frontends have disconnected should be
#  buffered in-memory.
#
#          When True (default), messages are buffered and replayed on reconnect,
#          avoiding lost messages due to interrupted connectivity.
#
#          Disable if long-running kernels will produce too much output while
#          no frontends are connected.
#  Default: True
# c.BeakerKernelMappingManager.buffer_offline_messages = True

## Directory for kernel connection files
#  Default: '/home/matt/.local/share/beaker/runtime/kernelfiles'
# c.BeakerKernelMappingManager.connection_dir = '/home/matt/.local/share/beaker/runtime/kernelfiles'

## Whether to consider culling kernels which are busy.
#          Only effective if cull_idle_timeout > 0.
#  Default: False
# c.BeakerKernelMappingManager.cull_busy = False

## Whether to consider culling kernels which have one or more connections.
#          Only effective if cull_idle_timeout > 0.
#  Default: False
# c.BeakerKernelMappingManager.cull_connected = False

## Timeout in seconds for culling idle kernels
#  Default: 0
# c.BeakerKernelMappingManager.cull_idle_timeout = 0

## The interval (in seconds) on which to check for idle kernels exceeding the
#  cull timeout value.
#  Default: 300
# c.BeakerKernelMappingManager.cull_interval = 300

## The name of the default kernel to start
#  Default: 'python3'
# c.BeakerKernelMappingManager.default_kernel_name = 'python3'

## Timeout for giving up on a kernel (in seconds).
#
#          On starting and restarting kernels, we check whether the
#          kernel is running and responsive by sending kernel_info_requests.
#          This sets the timeout in seconds for how long the kernel can take
#          before being presumed dead.
#          This affects the MappingKernelManager (which handles kernel restarts)
#          and the ZMQChannelsHandler (which handles the startup).
#  Default: 60
# c.BeakerKernelMappingManager.kernel_info_timeout = 60

#  Default: ''
# c.BeakerKernelMappingManager.root_dir = ''

## Share a single zmq.Context to talk to all my kernels
#  Default: True
# c.BeakerKernelMappingManager.shared_context = True

## Message to print when allow_tracebacks is False, and an exception occurs
#  Default: 'An exception occurred at runtime, which is not shown due to security reasons.'
# c.BeakerKernelMappingManager.traceback_replacement_message = 'An exception occurred at runtime, which is not shown due to security reasons.'

## List of kernel message types excluded from user activity tracking.
#
#          This should be a superset of the message types sent on any channel other
#          than the shell channel.
#  Default: ['comm_info_request', 'comm_info_reply', 'kernel_info_request', 'kernel_info_reply', 'shutdown_request', 'shutdown_reply', 'interrupt_request', 'interrupt_reply', 'debug_request', 'debug_reply', 'stream', 'display_data', 'update_display_data', 'execute_input', 'execute_result', 'error', 'status', 'clear_output', 'debug_event', 'input_request', 'input_reply']
# c.BeakerKernelMappingManager.untracked_message_types = ['comm_info_request', 'comm_info_reply', 'kernel_info_request', 'kernel_info_reply', 'shutdown_request', 'shutdown_reply', 'interrupt_request', 'interrupt_reply', 'debug_request', 'debug_reply', 'stream', 'display_data', 'update_display_data', 'execute_input', 'execute_result', 'error', 'status', 'clear_output', 'debug_event', 'input_request', 'input_reply']

## Whether to make kernels available before the process has started.  The
#          kernel has a `.ready` future which can be awaited before connecting
#  Default: False
# c.BeakerKernelMappingManager.use_pending_kernels = False

#------------------------------------------------------------------------------
# BeakerKernelSpecManager(KernelSpecManager) configuration
#------------------------------------------------------------------------------
## List of allowed kernel names.
#
#          By default, all installed kernels are allowed.
#  Default: set()
# c.BeakerKernelSpecManager.allowed_kernelspecs = set()

## If there is no Python kernelspec registered and the IPython
#          kernel is available, ensure it is added to the spec list.
#  Default: True
# c.BeakerKernelSpecManager.ensure_native_kernel = True

## The kernel spec class.  This is configurable to allow
#          subclassing of the KernelSpecManager for customized behavior.
#  Default: 'jupyter_client.kernelspec.KernelSpec'
# c.BeakerKernelSpecManager.kernel_spec_class = 'jupyter_client.kernelspec.KernelSpec'

#------------------------------------------------------------------------------
# BeakerSessionManager(SessionManager) configuration
#------------------------------------------------------------------------------
## The filesystem path to SQLite Database file (e.g.
#  /path/to/session_database.db). By default, the session database is stored in-
#  memory (i.e. `:memory:` setting from sqlite3) and does not persist when the
#  current Jupyter Server shuts down.
#  Default: ':memory:'
# c.BeakerSessionManager.database_filepath = ':memory:'

#------------------------------------------------------------------------------
# ConnectionFileMixin(LoggingConfigurable) configuration
#------------------------------------------------------------------------------
## Mixin for configurable classes that work with connection files

## JSON file in which to store connection info [default: kernel-<pid>.json]
#
#      This file will contain the IP, ports, and authentication key needed to connect
#      clients to this kernel. By default, this file will be created in the security dir
#      of the current profile, but can be specified by absolute path.
#  Default: ''
# c.ConnectionFileMixin.connection_file = ''

## set the control (ROUTER) port [default: random]
#  Default: 0
# c.ConnectionFileMixin.control_port = 0

## set the heartbeat port [default: random]
#  Default: 0
# c.ConnectionFileMixin.hb_port = 0

## set the iopub (PUB) port [default: random]
#  Default: 0
# c.ConnectionFileMixin.iopub_port = 0

## Set the kernel's IP address [default localhost].
#          If the IP address is something other than localhost, then
#          Consoles on other machines will be able to connect
#          to the Kernel, so be careful!
#  Default: ''
# c.ConnectionFileMixin.ip = ''

## set the shell (ROUTER) port [default: random]
#  Default: 0
# c.ConnectionFileMixin.shell_port = 0

## set the stdin (ROUTER) port [default: random]
#  Default: 0
# c.ConnectionFileMixin.stdin_port = 0

#  Choices: any of ['tcp', 'ipc'] (case-insensitive)
#  Default: 'tcp'
# c.ConnectionFileMixin.transport = 'tcp'


#------------------------------------------------------------------------------
# KernelManager(ConnectionFileMixin) configuration
#------------------------------------------------------------------------------
## Manages a single kernel in a subprocess on this host.
#
#  This version starts kernels with Popen.

## Should we autorestart the kernel if it dies.
#  Default: True
# c.KernelManager.autorestart = True

## True if the MultiKernelManager should cache ports for this KernelManager
#  instance
#  Default: False
# c.KernelManager.cache_ports = False

## Time to wait for a kernel to terminate before killing it, in seconds. When a
#  shutdown request is initiated, the kernel will be immediately sent an
#  interrupt (SIGINT), followedby a shutdown_request message, after 1/2 of
#  `shutdown_wait_time`it will be sent a terminate (SIGTERM) request, and finally
#  at the end of `shutdown_wait_time` will be killed (SIGKILL). terminate and
#  kill may be equivalent on windows.  Note that this value can beoverridden by
#  the in-use kernel provisioner since shutdown times mayvary by provisioned
#  environment.
#  Default: 5.0
# c.KernelManager.shutdown_wait_time = 5.0

#------------------------------------------------------------------------------
# AsyncMultiKernelManager(MultiKernelManager) configuration
#------------------------------------------------------------------------------
## The kernel manager class.  This is configurable to allow
#          subclassing of the AsyncKernelManager for customized behavior.
#  Default: 'jupyter_client.ioloop.AsyncIOLoopKernelManager'
# c.AsyncMultiKernelManager.kernel_manager_class = 'jupyter_client.ioloop.AsyncIOLoopKernelManager'

#------------------------------------------------------------------------------
# MultiKernelManager(LoggingConfigurable) configuration
#------------------------------------------------------------------------------
## A class for managing multiple kernels.

## The kernel manager class.  This is configurable to allow
#          subclassing of the KernelManager for customized behavior.
#  Default: 'jupyter_client.ioloop.IOLoopKernelManager'
# c.MultiKernelManager.kernel_manager_class = 'jupyter_client.ioloop.IOLoopKernelManager'

#------------------------------------------------------------------------------
# Session(Configurable) configuration
#------------------------------------------------------------------------------
## Object for handling serialization and sending of messages.
#
#  The Session object handles building messages and sending them with ZMQ sockets
#  or ZMQStream objects.  Objects can communicate with each other over the
#  network via Session objects, and only need to work with the dict-based IPython
#  message spec. The Session will handle serialization/deserialization, security,
#  and metadata.
#
#  Sessions support configurable serialization via packer/unpacker traits, and
#  signing with HMAC digests via the key/keyfile traits.
#
#  Parameters ----------
#
#  debug : bool
#      whether to trigger extra debugging statements
#  packer/unpacker : str : 'json', 'pickle' or import_string
#      importstrings for methods to serialize message parts.  If just
#      'json' or 'pickle', predefined JSON and pickle packers will be used.
#      Otherwise, the entire importstring must be used.
#
#      The functions must accept at least valid JSON input, and output *bytes*.
#
#      For example, to use msgpack:
#      packer = 'msgpack.packb', unpacker='msgpack.unpackb'
#  pack/unpack : callables
#      You can also set the pack/unpack callables for serialization directly.
#  session : bytes
#      the ID of this Session object.  The default is to generate a new UUID.
#  username : unicode
#      username added to message headers.  The default is to ask the OS.
#  key : bytes
#      The key used to initialize an HMAC signature.  If unset, messages
#      will not be signed or checked.
#  keyfile : filepath
#      The file containing a key.  If this is set, `key` will be initialized
#      to the contents of the file.

## Threshold (in bytes) beyond which an object's buffer should be extracted to
#  avoid pickling.
#  Default: 1024
# c.Session.buffer_threshold = 1024

## Whether to check PID to protect against calls after fork.
#
#          This check can be disabled if fork-safety is handled elsewhere.
#  Default: True
# c.Session.check_pid = True

## Threshold (in bytes) beyond which a buffer should be sent without copying.
#  Default: 65536
# c.Session.copy_threshold = 65536

## Debug output in the Session
#  Default: False
# c.Session.debug = False

## The maximum number of digests to remember.
#
#          The digest history will be culled when it exceeds this value.
#  Default: 65536
# c.Session.digest_history_size = 65536

## The maximum number of items for a container to be introspected for custom serialization.
#          Containers larger than this are pickled outright.
#  Default: 64
# c.Session.item_threshold = 64

## execution key, for signing messages.
#  Default: b''
# c.Session.key = b''

## path to file containing execution key.
#  Default: ''
# c.Session.keyfile = ''

## Metadata dictionary, which serves as the default top-level metadata dict for
#  each message.
#  Default: {}
# c.Session.metadata = {}

## The name of the packer for serializing messages.
#              Should be one of 'json', 'pickle', or an import name
#              for a custom callable serializer.
#  Default: 'json'
# c.Session.packer = 'json'

## The UUID identifying this session.
#  Default: ''
# c.Session.session = ''

## The digest scheme used to construct the message signatures.
#          Must have the form 'hmac-HASH'.
#  Default: 'hmac-sha256'
# c.Session.signature_scheme = 'hmac-sha256'

## The name of the unpacker for unserializing messages.
#          Only used with custom functions for `packer`.
#  Default: 'json'
# c.Session.unpacker = 'json'

## Username for the Session. Default is your system username.
#  Default: 'matt'
# c.Session.username = 'matt'

#------------------------------------------------------------------------------
# JupyterApp(Application) configuration
#------------------------------------------------------------------------------
## Base class for Jupyter applications

## Specify a config file to load.
#  Default: ''
# c.JupyterApp.config_file_name = ''

#------------------------------------------------------------------------------
# EventLogger(LoggingConfigurable) configuration
#------------------------------------------------------------------------------
## An Event logger for emitting structured events.
#
#  Event schemas must be registered with the EventLogger using the
#  `register_schema` or `register_schema_file` methods. Every schema will be
#  validated against Jupyter Event's metaschema.

## A list of logging.Handler instances to send events to.
#
#          When set to None (the default), all events are discarded.
#  Default: None
# c.EventLogger.handlers = None


#------------------------------------------------------------------------------
# GatewayWebSocketConnection(BaseKernelWebsocketConnection) configuration
#------------------------------------------------------------------------------
## Web socket connection that proxies to a kernel/enterprise gateway.

#  Default: ''
# c.GatewayWebSocketConnection.kernel_ws_protocol = ''

#  Default: None
# c.GatewayWebSocketConnection.session = None

#------------------------------------------------------------------------------
# GatewayClient(SingletonConfigurable) configuration
#------------------------------------------------------------------------------
## This class manages the configuration.  It's its own singleton class so that we
#  can share these values across all objects.  It also contains some options.
#  helper methods to build request arguments out of the various config

## Accept and manage cookies sent by the service side. This is often useful
#          for load balancers to decide which backend node to use.
#          (JUPYTER_GATEWAY_ACCEPT_COOKIES env var)
#  Default: False
# c.GatewayClient.accept_cookies = False

## A comma-separated list of environment variable names that will be included,
#  along with their values, in the kernel startup request.  The corresponding
#  `client_envs` configuration value must also be set on the Gateway server -
#  since that configuration value indicates which environmental values to make
#  available to the kernel. (JUPYTER_GATEWAY_ALLOWED_ENVS env var)
#  Default: ''
# c.GatewayClient.allowed_envs = ''

## The authorization header's key name (typically 'Authorization') used in the
#  HTTP headers. The header will be formatted as::
#
#  {'{auth_header_key}': '{auth_scheme} {auth_token}'}
#
#  If the authorization header key takes a single value, `auth_scheme` should be
#  set to None and 'auth_token' should be configured to use the appropriate
#  value.
#
#  (JUPYTER_GATEWAY_AUTH_HEADER_KEY env var)
#  Default: ''
# c.GatewayClient.auth_header_key = ''

## The auth scheme, added as a prefix to the authorization token used in the HTTP
#  headers. (JUPYTER_GATEWAY_AUTH_SCHEME env var)
#  Default: ''
# c.GatewayClient.auth_scheme = ''

## The authorization token used in the HTTP headers. The header will be formatted
#  as::
#
#  {'{auth_header_key}': '{auth_scheme} {auth_token}'}
#
#  (JUPYTER_GATEWAY_AUTH_TOKEN env var)
#  Default: None
# c.GatewayClient.auth_token = None

## The filename of CA certificates or None to use defaults.
#  (JUPYTER_GATEWAY_CA_CERTS env var)
#  Default: None
# c.GatewayClient.ca_certs = None

## The filename for client SSL certificate, if any.  (JUPYTER_GATEWAY_CLIENT_CERT
#  env var)
#  Default: None
# c.GatewayClient.client_cert = None

## The filename for client SSL key, if any.  (JUPYTER_GATEWAY_CLIENT_KEY env var)
#  Default: None
# c.GatewayClient.client_key = None

## The time allowed for HTTP connection establishment with the Gateway server.
#  (JUPYTER_GATEWAY_CONNECT_TIMEOUT env var)
#  Default: 40.0
# c.GatewayClient.connect_timeout = 40.0

#  Default: None
# c.GatewayClient.event_logger = None

## The time allowed for HTTP reconnection with the Gateway server for the first
#  time. Next will be JUPYTER_GATEWAY_RETRY_INTERVAL multiplied by two in factor
#  of numbers of retries but less than JUPYTER_GATEWAY_RETRY_INTERVAL_MAX.
#  (JUPYTER_GATEWAY_RETRY_INTERVAL env var)
#  Default: 1.0
# c.GatewayClient.gateway_retry_interval = 1.0

## The maximum time allowed for HTTP reconnection retry with the Gateway server.
#  (JUPYTER_GATEWAY_RETRY_INTERVAL_MAX env var)
#  Default: 30.0
# c.GatewayClient.gateway_retry_interval_max = 30.0

## The maximum retries allowed for HTTP reconnection with the Gateway server.
#  (JUPYTER_GATEWAY_RETRY_MAX env var)
#  Default: 5
# c.GatewayClient.gateway_retry_max = 5

## The class to use for Gateway token renewal.
#  (JUPYTER_GATEWAY_TOKEN_RENEWER_CLASS env var)
#  Default: 'jupyter_server.gateway.gateway_client.GatewayTokenRenewerBase'
# c.GatewayClient.gateway_token_renewer_class = 'jupyter_server.gateway.gateway_client.GatewayTokenRenewerBase'

## Additional HTTP headers to pass on the request.  This value will be converted to a dict.
#            (JUPYTER_GATEWAY_HEADERS env var)
#  Default: '{}'
# c.GatewayClient.headers = '{}'

## The password for HTTP authentication.  (JUPYTER_GATEWAY_HTTP_PWD env var)
#  Default: None
# c.GatewayClient.http_pwd = None

## The username for HTTP authentication. (JUPYTER_GATEWAY_HTTP_USER env var)
#  Default: None
# c.GatewayClient.http_user = None

## The gateway API endpoint for accessing kernel resources
#  (JUPYTER_GATEWAY_KERNELS_ENDPOINT env var)
#  Default: '/api/kernels'
# c.GatewayClient.kernels_endpoint = '/api/kernels'

## The gateway API endpoint for accessing kernelspecs
#  (JUPYTER_GATEWAY_KERNELSPECS_ENDPOINT env var)
#  Default: '/api/kernelspecs'
# c.GatewayClient.kernelspecs_endpoint = '/api/kernelspecs'

## The gateway endpoint for accessing kernelspecs resources
#  (JUPYTER_GATEWAY_KERNELSPECS_RESOURCE_ENDPOINT env var)
#  Default: '/kernelspecs'
# c.GatewayClient.kernelspecs_resource_endpoint = '/kernelspecs'

## Timeout pad to be ensured between KERNEL_LAUNCH_TIMEOUT and request_timeout
#  such that request_timeout >= KERNEL_LAUNCH_TIMEOUT + launch_timeout_pad.
#  (JUPYTER_GATEWAY_LAUNCH_TIMEOUT_PAD env var)
#  Default: 2.0
# c.GatewayClient.launch_timeout_pad = 2.0

## The time allowed for HTTP request completion. (JUPYTER_GATEWAY_REQUEST_TIMEOUT
#  env var)
#  Default: 42.0
# c.GatewayClient.request_timeout = 42.0

## The url of the Kernel or Enterprise Gateway server where kernel specifications
#  are defined and kernel management takes place. If defined, this Notebook
#  server acts as a proxy for all kernel management and kernel specification
#  retrieval.  (JUPYTER_GATEWAY_URL env var)
#  Default: None
# c.GatewayClient.url = None

## For HTTPS requests, determines if server's certificate should be validated or
#  not. (JUPYTER_GATEWAY_VALIDATE_CERT env var)
#  Default: True
# c.GatewayClient.validate_cert = True

## The websocket url of the Kernel or Enterprise Gateway server.  If not
#  provided, this value will correspond to the value of the Gateway url with 'ws'
#  in place of 'http'.  (JUPYTER_GATEWAY_WS_URL env var)
#  Default: None
# c.GatewayClient.ws_url = None


#------------------------------------------------------------------------------
# GatewayMappingKernelManager(AsyncMappingKernelManager) configuration
#------------------------------------------------------------------------------
## Kernel manager that supports remote kernels hosted by Jupyter Kernel or
#  Enterprise Gateway.

## Timeout (in seconds) after which a kernel is considered idle and ready to be culled.
#          Values of 0 or lower disable culling. Very short timeouts may result in kernels being culled
#          for users with poor network connections.
#  Default: 0
# c.GatewayMappingKernelManager.cull_idle_timeout = 0


#------------------------------------------------------------------------------
# ServerApp(JupyterApp) configuration
#------------------------------------------------------------------------------
## The Jupyter Server application class.

## Set the Access-Control-Allow-Origin header
#
#          Use '*' to allow any origin to access your server.
#
#          Takes precedence over allow_origin_pat.
#  Default: ''
# c.ServerApp.allow_origin = ''

## The content manager class to use.
#  Default: 'jupyter_server.services.contents.largefilemanager.AsyncLargeFileManager'
# c.ServerApp.contents_manager_class = 'jupyter_server.services.contents.largefilemanager.AsyncLargeFileManager'

## Disable cross-site-request-forgery protection
#
#          Jupyter server includes protection from cross-site request forgeries,
#          requiring API requests to either:
#
#          - originate from pages served by this server (validated with XSRF cookie and token), or
#          - authenticate with a token
#
#          Some anonymous compute resources still desire the ability to run code,
#          completely without authentication.
#          These services can disable all authentication and security checks,
#          with the full knowledge of what that implies.
#  Default: False
# c.ServerApp.disable_check_xsrf = False

## The kernel manager class to use.
#  Default: 'jupyter_server.services.kernels.kernelmanager.MappingKernelManager'
# c.ServerApp.kernel_manager_class = 'jupyter_server.services.kernels.kernelmanager.MappingKernelManager'

## The kernel spec manager class to use. Should be a subclass of
#  `jupyter_client.kernelspec.KernelSpecManager`.
#
#  The Api of KernelSpecManager is provisional and might change without warning
#  between this version of Jupyter and the next stable one.
#  Default: 'builtins.object'
# c.ServerApp.kernel_spec_manager_class = 'builtins.object'

## Whether to open in a browser after starting.
#                          The specific browser used is platform dependent and
#                          determined by the python standard library `webbrowser`
#                          module, unless it is overridden using the --browser
#                          (ServerApp.browser) configuration option.
#  Default: False
# c.ServerApp.open_browser = False

## Reraise exceptions encountered loading server extensions?
#  Default: False
# c.ServerApp.reraise_server_extension_failures = False

## The session manager class to use.
#  Default: 'builtins.object'
# c.ServerApp.session_manager_class = 'builtins.object'

#------------------------------------------------------------------------------
# ConfigManager(LoggingConfigurable) configuration
#------------------------------------------------------------------------------
## Config Manager used for storing frontend config

## Name of the config directory.
#  Default: 'serverconfig'
# c.ConfigManager.config_dir_name = 'serverconfig'




#------------------------------------------------------------------------------
# FileContentsManager(FileManagerMixin, ContentsManager) configuration
#------------------------------------------------------------------------------
## A file contents manager.

#  Default: None
# c.FileContentsManager.checkpoints = None

#  Default: 'jupyter_server.services.contents.checkpoints.Checkpoints'
# c.FileContentsManager.checkpoints_class = 'jupyter_server.services.contents.checkpoints.Checkpoints'

#  Default: {}
# c.FileContentsManager.checkpoints_kwargs = {}


#------------------------------------------------------------------------------
# AsyncContentsManager(ContentsManager) configuration
#------------------------------------------------------------------------------
## Base class for serving files and directories asynchronously.

#  Default: '/'
# c.AsyncContentsManager.root_dir = '/'


#------------------------------------------------------------------------------
# BaseKernelWebsocketConnection(LoggingConfigurable) configuration
#------------------------------------------------------------------------------
## A configurable base class for connecting Kernel WebSockets to ZMQ sockets.

## Preferred kernel message protocol over websocket to use (default: None). If an
#  empty string is passed, select the legacy protocol. If None, the selected
#  protocol will depend on what the front-end supports (usually the most recent
#  protocol supported by the back-end and the front-end).
#  Default: None
# c.BaseKernelWebsocketConnection.kernel_ws_protocol = None

#------------------------------------------------------------------------------
# ZMQChannelsWebsocketConnection(BaseKernelWebsocketConnection) configuration
#------------------------------------------------------------------------------
## A Jupyter Server Websocket Connection

## (bytes/sec)
#          Maximum rate at which stream output can be sent on iopub before they are
#          limited.
#  Default: 1000000
# c.ZMQChannelsWebsocketConnection.iopub_data_rate_limit = 1000000

## (msgs/sec)
#          Maximum rate at which messages can be sent on iopub before they are
#          limited.
#  Default: 1000
# c.ZMQChannelsWebsocketConnection.iopub_msg_rate_limit = 1000

## Whether to limit the rate of IOPub messages (default: True). If True, use
#  iopub_msg_rate_limit, iopub_data_rate_limit and/or rate_limit_window to tune
#  the rate.
#  Default: True
# c.ZMQChannelsWebsocketConnection.limit_rate = True

## (sec) Time window used to
#          check the message and data rate limits.
#  Default: 3
# c.ZMQChannelsWebsocketConnection.rate_limit_window = 3




#------------------------------------------------------------------------------
# NotebookNotary(LoggingConfigurable) configuration
#------------------------------------------------------------------------------
## A class for computing and verifying notebook signatures.

## The hashing algorithm used to sign notebooks.
#  Choices: any of ['sha384', 'sha512', 'blake2s', 'sha3_256', 'sha224', 'md5', 'sha3_384', 'sha3_224', 'sha256', 'sha1', 'sha3_512', 'blake2b']
#  Default: 'sha256'
# c.NotebookNotary.algorithm = 'sha256'

## The storage directory for notary secret and database.
#  Default: ''
# c.NotebookNotary.data_dir = ''

## The sqlite file in which to store notebook signatures.
#          By default, this will be in your Jupyter data directory.
#          You can set it to ':memory:' to disable sqlite writing to the filesystem.
#  Default: ''
# c.NotebookNotary.db_file = ''

## The secret key with which notebooks are signed.
#  Default: b''
# c.NotebookNotary.secret = b''

## The file where the secret key is stored.
#  Default: ''
# c.NotebookNotary.secret_file = ''

## A callable returning the storage backend for notebook signatures.
#           The default uses an SQLite database.
#  Default: traitlets.Undefined
# c.NotebookNotary.store_factory = traitlets.Undefined

