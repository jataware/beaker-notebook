from . import TemplateFile, JinjaTemplateFile


class UIPackageJsonFile(TemplateFile):
    PATH_PARTS = [
        'ui',
        'package.json',
    ]

    TEMPLATE = """\
{{
  "name": "{package_name}-ui",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {{
    "build": "vite build",
    "dev": "vite build --watch"
  }},
  "dependencies": {{
    "@jataware/beaker-client": "*",
    "@jataware/beaker-vue": "*",
    "vue": "^3.4.0"
  }},
  "devDependencies": {{
    "@vitejs/plugin-vue": "^5.0.0",
    "@vitejs/plugin-vue-jsx": "^4.0.0",
    "typescript": "^5.5.0",
    "vite": "^6.0.0",
    "vite-plugin-css-injected-by-js": "^3.5.0"
  }}
}}
"""


class UIViteConfigFile(TemplateFile):
    PATH_PARTS = [
        'ui',
        'vite.config.ts',
    ]

    TEMPLATE = """\
import {{ defineBeakerRendererConfig }} from '@jataware/beaker-vue/build';

export default defineBeakerRendererConfig({{
    build: {{
        outDir: '../src/{package_name}/assets/',
        lib: {{
            entry: {{
                "renderers": "./src/renderers.ts",
            }},
        }},
    }},
}});
"""


class UITsConfigFile(TemplateFile):
    PATH_PARTS = [
        'ui',
        'tsconfig.json',
    ]

    TEMPLATE = """\
{{
  "extends": "@jataware/beaker-vue/tsconfig.renderers.json",
  "compilerOptions": {{
    "paths": {{
      "@/*": ["./src/*"]
    }}
  }},
  "include": [
    "src/**/*.ts",
    "src/**/*.tsx",
    "src/**/*.vue"
  ]
}}
"""


class UIRenderersFile(TemplateFile):
    PATH_PARTS = [
        'ui',
        'src',
        'renderers.ts',
    ]

    TEMPLATE = """\
import type {{ BeakerMimeRenderer }} from '@jataware/beaker-vue';

// Example renderer — replace with your own custom renderers.
// Each renderer handles one or more MIME types and returns a Vue component
// with its props via the render() function.
//
// const MyRenderer: BeakerMimeRenderer = {{
//     rank: 40,
//     mimetypes: ["application/x-my-custom-type"],
//     render: (mimeType, data, metadata) => {{
//         return {{
//             component: MyComponent,
//             bindMapping: {{ data, mimeType }},
//         }};
//     }},
// }};

// Export an array of all renderers in this module.
// The Beaker frontend imports this default export and registers each renderer.
const renderers: BeakerMimeRenderer[] = [];
export default renderers;
"""


class UIContextRenderersFile(TemplateFile):
    PATH_PARTS = [
        'ui',
        'src',
        '{context_name}',
        'renderers.ts',
    ]

    TEMPLATE = """\
import type {{ BeakerMimeRenderer }} from '@jataware/beaker-vue';

// Context-level renderers for '{context_name}'.
// Export an array of BeakerMimeRenderer objects.
const renderers: BeakerMimeRenderer[] = [];
export default renderers;
"""


class UIAssetsGitkeepFile(TemplateFile):
    PATH_PARTS = [
        '{package_name}',
        'assets',
        '.gitkeep',
    ]

    TEMPLATE = ""
