<template>
    <Markdown :source="source" />
</template>

<script setup lang="ts">
import Markdown from 'vue3-markdown-it'
import 'highlight.js/styles/atom-one-light.css'

defineProps<{
    source: string
}>()
</script>

<script lang="ts">
export default {
    name: 'BotTextLight'
}
</script>

<style scoped>
:deep(pre code.hljs) {
    display: block;
    overflow-x: auto;
    padding: 1em;
}

:deep(code.hljs) {
    padding: 3px 5px;
}

:deep(.hljs) {
    color: #383a42;
    background: #fafafa;
}

:deep(.hljs-comment),
:deep(.hljs-quote) {
    color: #a0a1a7;
    font-style: italic;
}

:deep(.hljs-doctag),
:deep(.hljs-keyword),
:deep(.hljs-formula) {
    color: #a626a4;
}

:deep(.hljs-section),
:deep(.hljs-name),
:deep(.hljs-selector-tag),
:deep(.hljs-deletion),
:deep(.hljs-subst) {
    color: #e45649;
}

:deep(.hljs-literal) {
    color: #0184bb;
}

:deep(.hljs-string),
:deep(.hljs-regexp),
:deep(.hljs-addition),
:deep(.hljs-attribute),
:deep(.hljs-meta .hljs-string) {
    color: #50a14f;
}

:deep(.hljs-attr),
:deep(.hljs-variable),
:deep(.hljs-template-variable),
:deep(.hljs-type),
:deep(.hljs-selector-class),
:deep(.hljs-selector-attr),
:deep(.hljs-selector-pseudo),
:deep(.hljs-number) {
    color: #986801;
}

:deep(.hljs-symbol),
:deep(.hljs-bullet),
:deep(.hljs-link),
:deep(.hljs-meta),
:deep(.hljs-selector-id),
:deep(.hljs-title) {
    color: #4078f2;
}

:deep(.hljs-built_in),
:deep(.hljs-title.class_),
:deep(.hljs-class .hljs-title) {
    color: #c18401;
}

:deep(.hljs-emphasis) {
    font-style: italic;
}

:deep(.hljs-strong) {
    font-weight: bold;
}

:deep(.hljs-link) {
    text-decoration: underline;
}

:deep(h1),
:deep(h2),
:deep(h3),
:deep(h4),
:deep(h5),
:deep(h6) {
    color: var(--dl-color-darker);
}
</style>
