<template>
    <PDFControls
        @pdf-page-next="() => {
            page = clamp(page + 1, 1, pdf?.pages ?? 1)
        }"
        @pdf-page-prev="() => {
            page = clamp(page - 1, 1, pdf?.pages ?? 1)
        }"
        @pdf-zoom-in="() => {
            scaleIndex = clamp(scaleIndex + 1, 0, fixedZoomSteps.length - 1)
        }"
        @pdf-zoom-out="() => {
            scaleIndex = clamp(scaleIndex - 1, 0, fixedZoomSteps.length - 1)
        }"
        :page="page"
        :scale="fixedZoomSteps[scaleIndex]"
    />
    <PDFPage
        ref="pdf"
        :url="props.url"
        :scale="fixedZoomSteps[scaleIndex]"
        :page="page"
    />
</template>

<script setup lang="ts">
import { ref } from 'vue';
import PDFControls from './PDFControls.vue';
import PDFPage from './PDFPage.vue';

const fixedZoomSteps = [0.25, 0.5, 0.75, 0.9, 1, 1.1, 1.25, 1.5, 2, 3, 4]
const initialZoomIndex = 4;

const clamp = (num, min, max) => num <= min ? min : num >= max ? max : num;

const props = defineProps<{
    url: string
}>();

const page = ref(1);
const pdf = ref(null);
const scaleIndex = ref(initialZoomIndex);

defineExpose({ pdf });

</script>

<style lang="css" scoped>

</style>
