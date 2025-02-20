<template>
    <Markdown :source="source" />
</template>

<script setup lang="ts">
import Markdown from 'vue3-markdown-it'
import 'highlight.js/styles/atom-one-dark.css'

defineProps<{
    source: string
}>()
</script>

<script lang="ts">
export default {
    name: 'BotTextDark'
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
    color: #abb2bf;
    background: #282c34;
}

:deep(.hljs-comment),
:deep(.hljs-quote) {
    color: #5c6370;
    font-style: italic;
}

:deep(.hljs-doctag),
:deep(.hljs-keyword),
:deep(.hljs-formula) {
    color: #c678dd;
}

:deep(.hljs-section),
:deep(.hljs-name),
:deep(.hljs-selector-tag),
:deep(.hljs-deletion),
:deep(.hljs-subst) {
    color: #e06c75;
}

:deep(.hljs-literal) {
    color: #56b6c2;
}

:deep(.hljs-string),
:deep(.hljs-regexp),
:deep(.hljs-addition),
:deep(.hljs-attribute),
:deep(.hljs-meta .hljs-string) {
    color: #98c379;
}

:deep(.hljs-attr),
:deep(.hljs-variable),
:deep(.hljs-template-variable),
:deep(.hljs-type),
:deep(.hljs-selector-class),
:deep(.hljs-selector-attr),
:deep(.hljs-selector-pseudo),
:deep(.hljs-number) {
    color: #d19a66;
}

:deep(.hljs-symbol),
:deep(.hljs-bullet),
:deep(.hljs-link),
:deep(.hljs-meta),
:deep(.hljs-selector-id),
:deep(.hljs-title) {
    color: #61aeee;
}

:deep(.hljs-built_in),
:deep(.hljs-title.class_),
:deep(.hljs-class .hljs-title) {
    color: #e6c07b;
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

/* overwrite all h1, h2, h3, h4, h5, h6 to be bold */
:deep(h1),
:deep(h2),
:deep(h3),
:deep(h4),
:deep(h5),
:deep(h6) {
    color: var(--dl-color-darker);
}
</style>
