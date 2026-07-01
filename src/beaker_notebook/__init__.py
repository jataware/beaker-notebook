from beaker_notebook.util.refactor import redirect_imports, ImportRedirectMap

redirect_map: ImportRedirectMap = {
    'beaker_kernel.service.admin_utils': {
        'build_edges_map': 'beaker_kernel.lib.admin',
        'build_proc_info': 'beaker_kernel.lib.admin',
        'fetch_kernel_info': 'beaker_kernel.lib.admin',
        'fetch_system_stats': 'beaker_kernel.lib.admin',
    },
    'beaker_kernel.service.api': {},
    'beaker_kernel.service.api.handlers': {
        'add_handler_prefix': 'beaker_kernel.app.api.handlers',
        'find_api_handlers': 'beaker_kernel.app.api.handlers',
        'register_api_handlers': 'beaker_kernel.app.api.handlers',
    },
    'beaker_kernel.service.api.integrations': {
        'BeakerAPIMixin': 'beaker_kernel.app.api.integrations',
        'IntegrationHandler': 'beaker_kernel.app.api.integrations',
        'IntegrationResourceHandler': 'beaker_kernel.app.api.integrations',
        'get_context': 'beaker_kernel.app.api.integrations',
    },
    'beaker_kernel.service.api.notebook': {
        'NotebookHandler': 'beaker_kernel.app.api.notebook'
    },
    'beaker_kernel.service.auth': {
        'BeakerUser': 'beaker_kernel.services.auth',
        'current_request': 'beaker_kernel.services.auth',
        'current_user': 'beaker_kernel.services.auth',
        'BeakerAuthorizer': 'beaker_kernel.services.auth',
        'BeakerIdentityProvider': 'beaker_kernel.services.auth',
        'BeakerPermission': 'beaker_kernel.services.auth',
        'BeakerRole': 'beaker_kernel.services.auth',
        'RoleBasedUser': 'beaker_kernel.services.auth',
    },
    'beaker_kernel.service.auth.dummy': {
        'DummyAuthorizer': 'beaker_kernel.services.auth.dummy',
        'DummyIdentityProvider': 'beaker_kernel.services.auth.dummy',
    },
    'beaker_kernel.service.auth.notebook': {
        'NotebookAuthorizer': 'beaker_kernel.services.auth.notebook',
        'NotebookIdentityProvider': 'beaker_kernel.services.auth.notebook',
    },
    'beaker_kernel.service.base': {
        'BaseBeakerApp': 'beaker_kernel.app.base',
        'BeakerKernelManager': 'beaker_kernel.services.kernel.manager',
        'BeakerKernelMappingManager': 'beaker_kernel.services.kernel.mappingmanager',
        'BeakerKernelSpecManager': 'beaker_kernel.services.kernel.spec',
        'BeakerSessionManager': 'beaker_kernel.services.session',
    },
    'beaker_kernel.service.dev': {
        'BeakerWatchDog': 'beaker_kernel.app.dev_app',
        'DevBeakerJupyterApp': 'beaker_kernel.app.dev_app',
        'create_observer': 'beaker_kernel.app.dev_app',
    },
    'beaker_kernel.service.handlers': {
        'ConfigController': 'beaker_kernel.app.handlers',
        'ConfigHandler': 'beaker_kernel.app.handlers',
        'ContextHandler': 'beaker_kernel.app.handlers',
        'ExportAsHandler': 'beaker_kernel.app.handlers',
        'PageHandler': 'beaker_kernel.app.handlers',
        'StatsHandler': 'beaker_kernel.app.handlers',
        'register_handlers': 'beaker_kernel.app.handlers',
        'request_log_handler': 'beaker_kernel.app.handlers',
        'sanitize_env': 'beaker_kernel.app.handlers',
    },
    'beaker_kernel.service.notebook': {
        'BeakerNotebookApp': 'beaker_kernel.app.notebook_app'
    },
    'beaker_kernel.service.server': {
        'BeakerServerApp': 'beaker_kernel.app.server_app'
    },
    'beaker_kernel.service.storage': {},
    'beaker_kernel.service.storage.base': {
        'BaseBeakerContentsManager': 'beaker_kernel.services.storage.base',
        'BeakerLocalContentsHandler': 'beaker_kernel.services.storage.base',
        'BeakerLocalContentsManager': 'beaker_kernel.services.storage.base',
        'BeakerStorageManager': 'beaker_kernel.services.storage.base',
        'with_hidden_files': 'beaker_kernel.services.storage.base',
    },
    'beaker_kernel.service.storage.notebook': {
        'BaseNotebookManager': 'beaker_kernel.services.storage.notebook',
        'FileNotebookManager': 'beaker_kernel.services.storage.notebook',
        'NotebookInfo': 'beaker_kernel.services.storage.notebook',
        'with_hidden_files': 'beaker_kernel.services.storage.notebook',
    },
    'beaker_notebook.service.admin_utils': {
        'build_edges_map': 'beaker_notebook.lib.admin',
        'build_proc_info': 'beaker_notebook.lib.admin',
        'fetch_kernel_info': 'beaker_notebook.lib.admin',
        'fetch_system_stats': 'beaker_notebook.lib.admin',
    },
    'beaker_notebook.service.api': {},
    'beaker_notebook.service.api.handlers': {
        'add_handler_prefix': 'beaker_notebook.app.api.handlers',
        'find_api_handlers': 'beaker_notebook.app.api.handlers',
        'register_api_handlers': 'beaker_notebook.app.api.handlers',
    },
    'beaker_notebook.service.api.integrations': {
        'BeakerAPIMixin': 'beaker_notebook.app.api.integrations',
        'IntegrationHandler': 'beaker_notebook.app.api.integrations',
        'IntegrationResourceHandler': 'beaker_notebook.app.api.integrations',
        'get_context': 'beaker_notebook.app.api.integrations',
    },
    'beaker_notebook.service.api.notebook': {
        'NotebookHandler': 'beaker_notebook.app.api.notebook'
    },
    'beaker_notebook.service.auth': {
        'BeakerUser': 'beaker_notebook.services.auth',
        'current_request': 'beaker_notebook.services.auth',
        'current_user': 'beaker_notebook.services.auth',
        'BeakerAuthorizer': 'beaker_notebook.services.auth',
        'BeakerIdentityProvider': 'beaker_notebook.services.auth',
        'BeakerPermission': 'beaker_notebook.services.auth',
        'BeakerRole': 'beaker_notebook.services.auth',
        'RoleBasedUser': 'beaker_notebook.services.auth',
    },
    'beaker_notebook.service.auth.dummy': {
        'DummyAuthorizer': 'beaker_notebook.services.auth.dummy',
        'DummyIdentityProvider': 'beaker_notebook.services.auth.dummy',
    },
    'beaker_notebook.service.auth.notebook': {
        'NotebookAuthorizer': 'beaker_notebook.services.auth.notebook',
        'NotebookIdentityProvider': 'beaker_notebook.services.auth.notebook',
    },
    'beaker_notebook.service.base': {
        'BaseBeakerApp': 'beaker_notebook.app.base',
        'BeakerKernelManager': 'beaker_notebook.services.kernel.manager',
        'BeakerKernelMappingManager': 'beaker_notebook.services.kernel.mappingmanager',
        'BeakerKernelSpecManager': 'beaker_notebook.services.kernel.spec',
        'BeakerSessionManager': 'beaker_notebook.services.session',
    },
    'beaker_notebook.service.dev': {
        'BeakerWatchDog': 'beaker_notebook.app.dev_app',
        'DevBeakerJupyterApp': 'beaker_notebook.app.dev_app',
        'create_observer': 'beaker_notebook.app.dev_app',
    },
    'beaker_notebook.service.handlers': {
        'ConfigController': 'beaker_notebook.app.handlers',
        'ConfigHandler': 'beaker_notebook.app.handlers',
        'ContextHandler': 'beaker_notebook.app.handlers',
        'ExportAsHandler': 'beaker_notebook.app.handlers',
        'PageHandler': 'beaker_notebook.app.handlers',
        'StatsHandler': 'beaker_notebook.app.handlers',
        'register_handlers': 'beaker_notebook.app.handlers',
        'request_log_handler': 'beaker_notebook.app.handlers',
        'sanitize_env': 'beaker_notebook.app.handlers',
    },
    'beaker_notebook.service.notebook': {
        'BeakerNotebookApp': 'beaker_notebook.app.notebook_app'
    },
    'beaker_notebook.service.server': {
        'BeakerServerApp': 'beaker_notebook.app.server_app'
    },
    'beaker_notebook.service.storage': {},
    'beaker_notebook.service.storage.base': {
        'BaseBeakerContentsManager': 'beaker_notebook.services.storage.base',
        'BeakerLocalContentsHandler': 'beaker_notebook.services.storage.base',
        'BeakerLocalContentsManager': 'beaker_notebook.services.storage.base',
        'BeakerStorageManager': 'beaker_notebook.services.storage.base',
        'with_hidden_files': 'beaker_notebook.services.storage.base',
    },
    'beaker_notebook.service.storage.notebook': {
        'BaseNotebookManager': 'beaker_notebook.services.storage.notebook',
        'FileNotebookManager': 'beaker_notebook.services.storage.notebook',
        'NotebookInfo': 'beaker_notebook.services.storage.notebook',
        'with_hidden_files': 'beaker_notebook.services.storage.notebook',
    },
}

redirect_imports(redirect_map)
