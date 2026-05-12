<template>
  <div class="demo-container">
    <h2>Query Cell Badge States Demo</h2>
    
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import BeakerQueryCell from './BeakerQueryCell.vue';

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

const currentStatus = ref('idle');
const currentQueryStatus = ref('pending');
const lastExecutionStatus = ref('ok');

onMounted(() => {
  const mockBeakerSession = {
    cellRegistry: {},
  };
});
</script>

<style lang="scss">
.demo-container {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.demo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 2rem;
  margin: 2rem 0;
}

.demo-item {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 1rem;
  background: #f9f9f9;
  
  h3 {
    margin-top: 0;
    margin-bottom: 1rem;
    color: #333;
  }
}

.demo-controls {
  background: #f0f0f0;
  padding: 1.5rem;
  border-radius: 8px;
  margin: 2rem 0;
  
  .control-group {
    margin: 1rem 0;
    display: flex;
    align-items: center;
    gap: 1rem;
    
    label {
      font-weight: bold;
      min-width: 120px;
    }
    
    select, button {
      padding: 0.5rem;
      border: 1px solid #ccc;
      border-radius: 4px;
    }
    
    button {
      background: #007bff;
      color: white;
      border: none;
      cursor: pointer;
      
      &:hover {
        background: #0056b3;
      }
    }
  }
}

.demo-cell {
  border: 2px solid #007bff;
  border-radius: 8px;
  padding: 1rem;
  margin: 2rem 0;
  
  h3 {
    margin-top: 0;
    color: #007bff;
  }
}
</style>
