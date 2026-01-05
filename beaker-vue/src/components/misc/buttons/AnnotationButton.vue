<template>
    <Button
        @click="handleAction"
        size="small"
        :disabled="busy"
        :loading="busy"
    >
        <template #icon>
            <span class="pi pi-search pi-exclamation-triangle"/>
        </template>
    </Button>
</template>

<script lang="ts" setup>
import { ref } from "vue";
import Button from "primevue/button";

interface Props {
    action: () => Promise<any>;
}

const props = withDefaults(defineProps<Props>(), {
    async action() {
        console.log("no action defined");
    }
})

const busy = ref<boolean>(false);

const handleAction = async () => {
    busy.value = true;
    try {
        await props.action();
    }
    finally {
        busy.value = false;
    }
}

</script>

<style lang="scss">
    span.pi.pi-search.pi-exclamation-triangle {
        position: relative;

        &::after {
            content: "\e922";
            position: absolute;
            top: 12.5%;
            left: 12.5%;
            font-size: 60%;
        }
    }
</style>
