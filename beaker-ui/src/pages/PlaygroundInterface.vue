<template>
    <div class="playground-container">
        <!-- tab navigation -->
        <div class="tab-navigation">
            <Button 
                v-for="tab in tabs" 
                :key="tab.id"
                :label="tab.label"
                :class="['tab-button', { active: activeTab === tab.id }]"
                @click="activeTab = tab.id"
                text
            />
        </div>

        <!-- tab content -->
        <div class="tab-content">
            <!-- theme tab (default) -->
            <div v-show="activeTab === 'theme'" class="tab-panel">
                <Card class="theme-showcase">
                    <template #title>
                        <div class="showcase-header">
                            <h2>Beaker Theme Color Palette</h2>
                            <Button 
                                :icon="`pi ${isDarkMode ? 'pi-sun' : 'pi-moon'}`"
                                @click="toggleTheme"
                                text
                                rounded
                                v-tooltip.bottom="`Switch to ${isDarkMode ? 'light' : 'dark'} mode`"
                            />
                        </div>
                    </template>
                    <template #content>
                        <div class="color-sections">
                            <section class="color-section">
                                <h3>Primary Colors</h3>
                                <div class="color-grid">
                                    <div class="color-card" v-for="(value, key) in primaryColors" :key="key">
                                        <div class="color-swatch" :style="{backgroundColor: `var(--p-${key})`}"></div>
                                        <div class="color-info">
                                            <code class="color-name">--p-{{ key }}</code>
                                            <span class="color-value" :style="{color: `var(--p-${key})`}">●</span>
                                        </div>
                                    </div>
                                </div>
                            </section>

                            <!-- surfaces -->
                            <section class="color-section">
                                <h3>Surface Colors</h3>
                                <div class="color-grid">
                                    <div class="color-card" v-for="surface in surfaceColors" :key="surface">
                                        <div class="color-swatch" :style="{backgroundColor: `var(--p-surface-${surface})`}"></div>
                                        <div class="color-info">
                                            <code class="color-name">--p-surface-{{ surface }}</code>
                                            <span class="color-value" :style="{color: `var(--p-surface-${surface})`}">●</span>
                                        </div>
                                    </div>
                                </div>
                            </section>

                            <!-- text -->
                            <section class="color-section">
                                <h3>Text Colors</h3>
                                <div class="color-grid">
                                    <div class="color-card" v-for="textColor in textColors" :key="textColor">
                                        <div class="color-swatch text-demo" :style="{backgroundColor: 'var(--p-surface-a)', color: `var(--${textColor})`}">
                                            Sample Text
                                        </div>
                                        <div class="color-info">
                                            <code class="color-name">--{{ textColor }}</code>
                                            <span class="color-value" :style="{color: `var(--${textColor})`}">●</span>
                                        </div>
                                    </div>
                                </div>
                            </section>

                            <!-- semantic -->
                            <section class="color-section">
                                <h3>Semantic Colors & Others</h3>
                                <div class="semantic-colors">
                                    <div v-for="(colors, colorName) in semanticColors" :key="colorName" class="semantic-group">
                                        <h4 class="semantic-title">{{ colorName.charAt(0).toUpperCase() + colorName.slice(1) }}</h4>
                                        <div class="color-row">
                                            <div class="color-card small" v-for="shade in colors" :key="shade">
                                                <div class="color-swatch small" :style="{backgroundColor: `var(--p-${colorName}-${shade})`}"></div>
                                                <div class="color-info small">
                                                    <code class="color-name small">--p-{{ colorName }}-{{ shade }}</code>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </section>

                        </div>
                    </template>
                </Card>
            </div>

            <!-- query cell demo tab -->
            <div v-show="activeTab === 'query-cells'" class="tab-panel">
                <Card class="query-cell-demo">
                    <template #title>
                        <h2>Query Cell Badge States Demo</h2>
                    </template>
                    <template #content>
                        <p class="demo-description">Hover over each badge to see tooltips. This demonstrates all the different states of query cell badges.</p>
                        
                        <div class="demo-grid">
                            <div class="demo-item">
                                <h3>Pending</h3>
                                <BeakerQueryCell
                                    :index="0" 
                                    :cell="pendingCell" 
                                />
                            </div>
                            
                            <div class="demo-item">
                                <h3>In Progress</h3>
                                <BeakerQueryCell
                                    :index="1" 
                                    :cell="inProgressCell" 
                                />
                            </div>
                            
                            <div class="demo-item">
                                <h3>Success</h3>
                                <BeakerQueryCell
                                    :index="2" 
                                    :cell="successCell" 
                                />
                            </div>
                            
                            <div class="demo-item">
                                <h3>Aborted</h3>
                                <BeakerQueryCell
                                    :index="3" 
                                    :cell="abortedCell" 
                                />
                            </div>
                            
                            <div class="demo-item">
                                <h3>Failed</h3>
                                <BeakerQueryCell
                                    :index="4" 
                                    :cell="failedCell" 
                                />
                            </div>
                        </div>
                    </template>
                </Card>
            </div>

            <!-- widgets tab -->
            <div v-show="activeTab === 'widgets'" class="tab-panel">
                <Card class="widget-examples">
                    <template #title>
                        <h2>Widget Usage Examples</h2>
                    </template>
                    <template #content>
                        <p class="demo-description">Examples of various widgets and components available in the system.</p>
                        
                        <div class="widget-grid">
                            <!-- cards -->
                            <div class="widget-section">
                                <h3>Card Components</h3>
                                <div class="card-examples">
                                    <Card class="example-card">
                                        <template #title>
                                            <h4>Basic Card</h4>
                                        </template>
                                        <template #content>
                                            <p>This is a basic card component with title and content sections.</p>
                                        </template>
                                    </Card>
                                    
                                    <Card class="example-card">
                                        <template #title>
                                            <h4>Card with Actions</h4>
                                        </template>
                                        <template #content>
                                            <p>Card content with action buttons below.</p>
                                        </template>
                                        <template #footer>
                                            <div class="card-actions">
                                                <Button label="Save" icon="pi pi-check" />
                                                <Button label="Cancel" severity="secondary" text />
                                            </div>
                                        </template>
                                    </Card>
                                </div>
                            </div>

                            <!-- badges -->
                            <div class="widget-section">
                                <h3>Badge Components</h3>
                                <div class="badge-examples">
                                    <div class="badge-item">
                                        <span class="badge success">Success</span>
                                        <span class="badge warning">Warning</span>
                                        <span class="badge error">Error</span>
                                        <span class="badge info">Info</span>
                                    </div>
                                    <div class="badge-item">
                                        <span class="badge primary">Primary</span>
                                        <span class="badge secondary">Secondary</span>
                                        <span class="badge outline">Outline</span>
                                    </div>
                                </div>
                            </div>

                            <!-- buttons -->
                            <div class="widget-section">
                                <h3>Button Variants</h3>
                                <div class="button-examples">
                                    <Button label="Primary" class="mr-2" />
                                    <Button label="Secondary" severity="secondary" class="mr-2" />
                                    <Button label="Success" severity="success" class="mr-2" />
                                    <Button label="Warning" severity="warn" class="mr-2" />
                                    <Button label="Danger" severity="danger" class="mr-2" />
                                    <Button label="Info" severity="info" class="mr-2" />
                                </div>
                                <div class="button-examples mt-3">
                                    <Button label="Outlined" outlined class="mr-2" />
                                    <Button label="Text" text class="mr-2" />
                                    <Button label="Rounded" rounded class="mr-2" />
                                    <Button icon="pi pi-star" class="mr-2" />
                                </div>
                            </div>

                            <!-- form elements -->
                            <div class="widget-section">
                                <h3>Form Elements</h3>
                                <div class="form-examples">
                                    <div class="form-row">
                                        <label>Input Field:</label>
                                        <input type="text" placeholder="Enter text..." class="form-input" />
                                    </div>
                                    <div class="form-row">
                                        <label>Select:</label>
                                        <select class="form-select">
                                            <option>Option 1</option>
                                            <option>Option 2</option>
                                            <option>Option 3</option>
                                        </select>
                                    </div>
                                    <div class="form-row">
                                        <label>Checkbox:</label>
                                        <input type="checkbox" class="form-checkbox" />
                                    </div>
                                </div>
                            </div>
                        </div>
                    </template>
                </Card>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue';
import Card from 'primevue/card';
import Button from 'primevue/button';
import BeakerQueryCell from '@/components/cell/BeakerQueryCell.vue';
import type { IBeakerTheme } from '@/plugins/theme';

const beakerApp = inject<any>("beakerAppConfig");
beakerApp?.setPage("playground");

const { theme, toggleDarkMode } = inject<IBeakerTheme>('theme');

const isDarkMode = computed(() => theme.mode === 'dark');

const toggleTheme = () => {
    toggleDarkMode();
};

const tabs = [
    { id: 'theme', label: 'Theme' },
    { id: 'query-cells', label: 'Query Cells' },
    { id: 'widgets', label: 'Widgets' }
];

const activeTab = ref('theme');

const pendingCell = ref({
  id: 'demo-pending',
  source: 'This is a pending query',
  status: 'idle',
  metadata: { query_status: 'pending' },
  events: [],
  last_execution: {},
  children: [],
  cell_type: 'query',
});

const inProgressCell = ref({
  id: 'demo-in-progress',
  source: 'This query is running',
  status: 'busy',
  metadata: { query_status: 'in-progress' },
  events: [{ type: 'thought', content: 'Thinking...' }],
  last_execution: {},
  children: [],
  cell_type: 'query',
});

const successCell = ref({
  id: 'demo-success',
  source: 'This query completed successfully',
  status: 'idle',
  metadata: { query_status: 'success' },
  events: [
    { type: 'thought', content: 'Processing...' },
    { type: 'response', content: 'Success! Here are the results...' }
  ],
  last_execution: { status: 'ok' },
  children: [],
  cell_type: 'query',
});

const abortedCell = ref({
  id: 'demo-aborted',
  source: 'This query was aborted',
  status: 'idle',
  metadata: { query_status: 'aborted' },
  events: [
    { type: 'thought', content: 'Processing...' },
    { type: 'abort', content: 'Request interrupted' }
  ],
  last_execution: { status: 'abort' },
  children: [],
  cell_type: 'query',
});

const failedCell = ref({
  id: 'demo-failed',
  source: 'This query failed',
  status: 'idle',
  metadata: { query_status: 'failed' },
  events: [
    { type: 'thought', content: 'Processing...' },
    { type: 'error', content: 'An error occurred' }
  ],
  last_execution: { status: 'error' },
  children: [],
  cell_type: 'query',
});

// const currentStatus = ref('idle');
// const currentQueryStatus = ref('pending');
// const lastExecutionStatus = ref('ok');
// const interactiveEvents = ref([]);

// const interactiveCell = computed(() => ({
//   id: 'demo-interactive',
//   source: 'Interactive demo cell - change the controls above',
//   status: currentStatus.value,
//   metadata: { query_status: currentQueryStatus.value },
//   events: interactiveEvents.value,
//   last_execution: { status: lastExecutionStatus.value },
//   children: [],
//   cell_type: 'query',
// }));

// const addEvent = (type) => {
//   interactiveEvents.value.push({
//     type,
//     content: `Demo ${type} event`,
//     id: Date.now()
//   });
// };

// const clearEvents = () => {
//   interactiveEvents.value = [];
// };

const primaryColors = {
    'primary-color': 'Primary',
    'primary-50': '50',
    'primary-100': '100',
    'primary-200': '200',
    'primary-300': '300',
    'primary-400': '400',
    'primary-500': '500',
    'primary-600': '600',
    'primary-700': '700',
    'primary-800': '800',
    'primary-900': '900',
    'primary-950': '950',
};

const surfaceColors = [
    'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l',
    'border', 'ground', '0', '50', '100', '200', '300', '400', '500', 
    '600', '700', '800', '900', '950'
];

const textColors = [
    'text-color',
    'text-color-secondary', 
    'highlight-text-color',
];

const semanticColors = {
    green: ['200', '300', '400', '500', '600', '700'],
    orange: ['200', '300', '400', '500', '600', '700'],
    blue: ['200', '300', '400', '500', '600', '700'],
    yellow: ['200', '300', '400', '500', '600', '700'],
    gray: ['200', '300', '400', '500', '600', '700'],
    slate: ['200', '300', '400', '500', '600', '700'],
};

const componentColors = [
    'content-background',
    'toolbar-background',
    'toolbar-border-color',
    'surface-border-radius',
];
</script>

<style lang="scss" scoped>
.playground-container {
    padding: 1rem;
    height: 100%;
    overflow-y: auto;
}

.tab-navigation {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 2rem;
    border-bottom: 2px solid var(--p-surface-border);
    padding-bottom: 0.5rem;
}

.tab-button {
    padding: 0.75rem 1.5rem;
    border-radius: 8px 8px 0 0;
    border: none;
    background: transparent;
    color: var(--p-text-color-secondary);
    font-weight: 500;
    transition: all 0.2s ease;
    
    &:hover {
        background: var(--p-surface-b);
        color: var(--p-text-color);
    }
    
    &.active {
        background: var(--p-primary-color);
        color: white;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }
}

.tab-content {
    min-height: 500px;
}

.tab-panel {
    animation: fadeIn 0.3s ease-in-out;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.query-cell-demo {
    margin-bottom: 2rem;
}

.demo-description {
    color: var(--p-text-color-secondary);
    margin-bottom: 1.5rem;
    font-style: italic;
}

.demo-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 1.5rem;
    margin-bottom: 2rem;
}

.demo-item {
    border: 1px solid var(--p-surface-border);
    border-radius: 8px;
    padding: 1rem;
    background: var(--p-surface-a);
    
    h3 {
        margin-top: 0;
        margin-bottom: 1rem;
        color: var(--p-primary-color);
        font-size: 1.1rem;
    }
}

.demo-controls {
    background: var(--p-surface-b);
    padding: 1.5rem;
    border-radius: 8px;
    margin: 2rem 0;
    border: 1px solid var(--p-surface-border);
    
    h3 {
        margin-top: 0;
        color: var(--p-primary-color);
        margin-bottom: 1.5rem;
    }
    
    .control-group {
        margin: 1rem 0;
        display: flex;
        align-items: center;
        gap: 1rem;
        
        label {
            font-weight: 600;
            min-width: 120px;
            color: var(--p-text-color);
        }
        
        select, button {
            padding: 0.5rem;
            border: 1px solid var(--p-surface-border);
            border-radius: 4px;
            background: var(--p-surface-a);
            color: var(--p-text-color);
        }
        
        button {
            background: var(--p-primary-color);
            color: white;
            border: none;
            cursor: pointer;
            font-weight: 500;
            
            &:hover {
                background: var(--p-primary-600);
            }
        }
    }
}

.demo-cell {
    border: 2px solid var(--p-primary-color);
    border-radius: 8px;
    padding: 1rem;
    margin: 2rem 0;
    background: var(--p-surface-a);
    
    h3 {
        margin-top: 0;
        color: var(--p-primary-color);
        margin-bottom: 1rem;
    }
}

.theme-showcase {
    max-width: 100%;
    margin: 0 auto;
}

.showcase-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
}

.color-sections {
    display: flex;
    flex-direction: column;
    gap: 2rem;
}

.color-section {
    h3 {
        color: var(--p-primary-color);
        margin-bottom: 1rem;
        border-bottom: 2px solid var(--p-surface-border);
        padding-bottom: 0.5rem;
    }
}

.color-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 1rem;
}

.color-card {
    background: var(--p-surface-a);
    border: 1px solid var(--p-surface-border);
    border-radius: 8px;
    padding: 1rem;
    transition: all 0.2s ease;

    &:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        border-color: var(--p-primary-color);
    }

    &.small {
        padding: 0.5rem;
        min-width: 120px;
    }
}

.color-swatch {
    width: 100%;
    height: 60px;
    border-radius: 6px;
    border: 1px solid var(--p-surface-border);
    margin-bottom: 0.5rem;
    
    &.small {
        height: 40px;
    }

    &.text-demo {
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 600;
        font-size: 0.9rem;
    }
}

.color-info {
    display: flex;
    justify-content: space-between;
    align-items: center;
    
    &.small {
        flex-direction: column;
        align-items: flex-start;
        gap: 0.25rem;
    }
}

.color-name {
    font-family: 'Courier New', monospace;
    font-size: 0.8rem;
    background: var(--p-surface-c);
    color: var(--p-text-color);
    padding: 0.2rem 0.4rem;
    border-radius: 4px;
    
    &.small {
        font-size: 0.7rem;
        padding: 0.1rem 0.3rem;
    }
}

.color-value {
    font-size: 1.5rem;
    font-weight: bold;
}

.semantic-colors {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
}

.semantic-group {
    .semantic-title {
        color: var(--p-text-color);
        margin-bottom: 0.5rem;
        font-size: 1.1rem;
    }
}

.color-row {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
}

.usage-examples {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 1rem;
}

.example-card {
    padding: 1.5rem;
    border-radius: 8px;
    
    h4 {
        margin-top: 0;
        margin-bottom: 1rem;
    }
    
    p {
        margin: 0.5rem 0;
    }
}

.color-chips {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-top: 1rem;
}

.chip {
    padding: 0.3rem 0.8rem;
    border-radius: 16px;
    font-size: 0.8rem;
    font-weight: 600;
}

.widget-examples {
    margin-bottom: 2rem;
}

.widget-grid {
    display: flex;
    flex-direction: column;
    gap: 2rem;
}

.widget-section {
    h3 {
        color: var(--p-primary-color);
        margin-bottom: 1rem;
        border-bottom: 2px solid var(--p-surface-border);
        padding-bottom: 0.5rem;
    }
}

.card-examples {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 1rem;
}

.badge-examples {
    display: flex;
    flex-direction: column;
    gap: 1rem;
}

.badge-item {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
}

.badge {
    padding: 0.5rem 1rem;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    
    &.success { background: var(--p-green-500); color: white; }
    &.warning { background: var(--p-orange-500); color: white; }
    &.error { background: var(--p-red-500); color: white; }
    &.info { background: var(--p-blue-500); color: white; }
    &.primary { background: var(--p-primary-color); color: white; }
    &.secondary { background: var(--p-gray-500); color: white; }
    &.outline { 
        background: transparent; 
        color: var(--p-primary-color); 
        border: 2px solid var(--p-primary-color);
    }
}

.button-examples {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    align-items: center;
}

.form-examples {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    max-width: 400px;
}

.form-row {
    display: flex;
    align-items: center;
    gap: 1rem;
    
    label {
        min-width: 100px;
        font-weight: 600;
        color: var(--p-text-color);
    }
    
    .form-input, .form-select {
        flex: 1;
        padding: 0.5rem;
        border: 1px solid var(--p-surface-border);
        border-radius: 4px;
        background: var(--p-surface-a);
        color: var(--p-text-color);
    }
    
    .form-checkbox {
        width: 18px;
        height: 18px;
    }
}

.card-actions {
    display: flex;
    gap: 0.5rem;
    justify-content: flex-end;
}

.mr-2 { margin-right: 0.5rem; }
.mt-3 { margin-top: 1rem; }
</style> 