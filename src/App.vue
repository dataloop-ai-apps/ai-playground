<template>
    <DlThemeProvider :is-dark="isDark" class="main-background">
        <!-- Global drop overlay that covers the entire window - just a subtle film effect -->
        <div v-if="isDragging" class="global-drop-overlay"></div>

        <div v-if="!isReady" class="loading-spinner">
            <dl-spinner type="clock" text="Loading..." />
        </div>
        <div
            v-if="isReady"
            class="chat-container"
            @dragover.prevent="handleDragOver"
            @dragleave.prevent="handleDragLeave"
            @drop.prevent="handleDrop"
        >
            <!-- Drop zone overlay that appears when dragging files -->
            <div v-if="isDragging" class="drop-zone-overlay">
                <div class="drop-zone-content">
                    <dl-icon icon="icon-dl-attach" size="xl" />
                    <dl-typography variant="h3" color="var(--dell-gray-800)">Drop file here</dl-typography>
                    <dl-typography color="var(--dell-gray-800)">Release to upload new image</dl-typography>
                    <div class="drop-zone-border"></div>
                </div>
            </div>

            <div class="top-bar">
                <div class="select-group">
                    <dl-select
                        class="choose-option"
                        v-model="choosed_option"
                        :options="choose_options"
                        size="m"
                        :width="'140px'"
                        @change="handleOptionChange"
                    />
                    <dl-select
                        v-if="choosed_option === 'Pipeline'"
                        v-model="selectedOption"
                        searchable
                        :options="pipeline_options"
                        placeholder="Choose a pipeline"
                        size="m"
                        width="60%"
                    />

                    <dl-select
                        v-if="choosed_option === 'Model'"
                        v-model="selectedOption"
                        searchable
                        :options="model_options"
                        placeholder="Choose a model"
                        size="m"
                        width="60%"
                    />
                </div>
                <div class="top-bar-actions">
                    <div class="llm-trace-toggle">
                        <dl-typography variant="small" color="var(--dell-gray-800)">LLM Trace</dl-typography>
                        <dl-switch
                            :model-value="useLlmTrace"
                            @update:model-value="toggleLlmTrace"
                        />
                    </div>
                    <dl-button
                        round
                        icon="icon-dl-refresh"
                        size="s"
                        class="restart-button"
                        hover-bg-color="var(--dell-gray-100)"
                        color="var(--dell-gray-100)"
                        text-color="var(--dell-gray-800)"
                        hover-text-color="var(--dell-gray-800)"
                        @click="restartChat"
                        tooltip="Restart chat"
                    />
                </div>
            </div>

            <div class="first-div">
                <div class="message-group" v-for="(message, index) in messages" :key="index">
                    <div class="single-massage">
                        <dl-avatar v-if="message.sender === 'user_new'" class="massage-item">
                            {{ currentUser.charAt(0).toUpperCase() }}
                        </dl-avatar>
                        <dl-icon
                            v-if="message.sender === 'bot'"
                            class="massage-item"
                            icon="icon-dl-dataloop"
                            size="l"
                            :svg="true"
                        ></dl-icon>

                        <dl-typography
                            v-if="message.sender === 'bot'"
                            color="textPrimary "
                            class="massage-item bot-message"
                        >
                            <div v-if="message.text !== ''" class="bot-text">
                                <BotTextDark v-if="isDark" :source="message.text" />
                                <BotTextLight v-else :source="message.text" />
                            </div>

                            <div v-else class="status-message">
                                <span>
                                    {{ choosed_option === 'Pipeline' ? 'Pipeline' : 'Model' }} execution:
                                    {{ statusMessage }}
                                </span>
                                <dl-spinner type="clock" :size="'10px'" class="inline-spinner" />
                            </div>
                        </dl-typography>
                        <div v-else class="user-message">
                            <img v-if="message.image" :src="message.image" alt="Message Image" class="user-image" />
                            <dl-typography color="textPrimary" class="chat-bubble"> {{ message.text }}</dl-typography>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Second Div: Adjusts to the height of its content -->
            <div class="second-div">
                <dl-alert v-if="showAlert" :type="alertType" class="chat-alert" :fluid="true">
                    <span v-if="alertType === 'warning'">
                        Please select a <strong>{{ choosed_option }}</strong> from the dropdown.
                    </span>
                    <span v-else>
                        {{ alertMessage }}
                    </span>
                </dl-alert>
                <div class="textarea-wrapper">
                    <!-- Image Preview -->
                    <div v-if="selectedImage" class="image-preview">
                        <img :src="imagePreview" alt="Preview" class="preview-thumbnail" />
                        <dl-button
                            round
                            dense
                            icon="icon-dl-close"
                            size="5px"
                            class="delete-button"
                            hover-bg-color="var(--dell-gray-800)"
                            hover-text-color="var(--dell-white)"
                            @click="deleteImage"
                        />
                    </div>
                    <dl-text-area
                        ref="textarea"
                        v-model="userQuestion"
                        placeholder="Ask Dataloop AI"
                        @keydown="handleKeyDown"
                        @input="autoResize"
                        hideClearButton
                        maxHeight="150px"
                        minHeight="50px"
                        class="borderless-textarea"
                    />
                    <div class="textarea-actions">
                        <input
                            type="file"
                            ref="fileInput"
                            accept="image/*"
                            style="display: none"
                            @change="handleFileUpload"
                        />
                        <dl-button
                            round
                            icon="icon-dl-attach"
                            size="s"
                            class="action-button"
                            hover-bg-color="var(--dell-gray-100)"
                            color="var(--dell-gray-100)"
                            text-color="var(--dell-gray-800)"
                            hover-text-color="var(--dell-gray-800)"
                            @click="handleClick"
                        />
                        <dl-button
                            dense
                            round
                            filled
                            icon="icon-dl-arrow-up"
                            size="xl"
                            class="send-button"
                            :disabled="!userQuestion"
                            hover-bg-color="var(--dell-gray-100)"
                            color="var(--dell-gray-100)"
                            text-color="var(--dell-gray-800)"
                            hover-text-color="var(--dell-gray-800)"
                            @click="sendMessage"
                        />
                    </div>
                </div>
            </div>
        </div>
    </DlThemeProvider>
</template>

<script setup lang="ts">
import {
    DlThemeProvider,
    DlSpinner,
    DlInput,
    DlButton,
    DlTypography,
    DlIcon,
    DlBadge,
    DlAvatar,
    DlSelect,
    DlTextArea,
    DlAlert,
    DlSwitch
} from '@dataloop-ai/components'
import { DlEvent, DlFrameEvent, SDKPipeline, ThemeType } from '@dataloop-ai/jssdk'
import { ref, onMounted, onUnmounted, computed, nextTick } from 'vue-demi'
import BotTextDark from './components/BotTextDark.vue'
import BotTextLight from './components/BotTextLight.vue'

const statusMessage = ref<string>('')
const messageQueue = ref<string[]>([])
const isProcessing = ref<boolean>(false)
const isReady = ref<boolean>(false)
const currentTheme = ref<ThemeType>(ThemeType.DARK)
const userQuestion = ref<string>('')
const currentUser = ref<string>('')
const messages = ref<Array<{ text: string; sender: string; image?: string }>>([])
const askDisabled = ref<boolean>(false)
const sessionId = ref<string>('')
const currentTypingInterval = ref<ReturnType<typeof setInterval> | null>(null)

const project_id = ref<string>('')
const selectedOption = ref<{ label: string; value: string }>()

const last_option = ref<string>('Pipeline')
const choose_options = ref(['Model', 'Pipeline'])
const choosed_option = ref<string>('Pipeline')
const pipeline_options = ref<{ label: string; value: string }[]>([])

const model_options = ref<{ label: string; value: string }[]>([])

const isDark = computed<boolean>(() => {
    return currentTheme.value === ThemeType.DARK
})

const textarea = ref(null)
const fileInput = ref<HTMLInputElement | null>(null)
const selectedImage = ref<File | null>(null)
const imagePreview = ref<string>('')

// Add these refs for the alert
const showAlert = ref<boolean>(false)
const alertMessage = ref<string>('Only image files are supported.')
const alertType = ref<'warning' | 'error'>('warning')

const eventSourceRef = ref<EventSource | null>(null)

const isDragging = ref<boolean>(false)

const useLlmTrace = ref<boolean>(localStorage.getItem('useLlmTrace') === 'true')
const toggleLlmTrace = (val: boolean) => {
    useLlmTrace.value = val
    localStorage.setItem('useLlmTrace', String(val))
}

onMounted(() => {
    window.dl.on(DlEvent.READY, async () => {
        const settings = await window.dl.settings.get()
        currentUser.value = settings.currentUser
        const project = await window.dl.projects.get()
        project_id.value = project.id

        await fetchData(project_id.value)

        // @ts-ignore
        currentTheme.value = settings.theme
        window.dl.on(DlEvent.THEME, (data) => {
            currentTheme.value = data
        })
        isReady.value = true
    })
    sessionId.value = Math.random().toString(36).substring(2, 32)

    // Add global event listeners to handle drag events outside the container
    document.addEventListener('dragend', handleGlobalDragEnd)
    document.addEventListener('drop', handleGlobalDrop)
    document.addEventListener('dragover', handleGlobalDragOver)
    document.addEventListener('dragleave', handleGlobalDragLeave)
})

onUnmounted(() => {
    // Clean up global event listeners
    document.removeEventListener('dragend', handleGlobalDragEnd)
    document.removeEventListener('drop', handleGlobalDrop)
    document.removeEventListener('dragover', handleGlobalDragOver)
    document.removeEventListener('dragleave', handleGlobalDragLeave)

    // Close any open event source
    if (eventSourceRef.value) {
        eventSourceRef.value.close()
        eventSourceRef.value = null
    }
})

const handleGlobalDragOver = (event: DragEvent) => {
    event.preventDefault()
    isDragging.value = true
}

const handleGlobalDragLeave = (event: DragEvent) => {
    // Only consider dragleave events that leave the document
    if (!event.relatedTarget || event.relatedTarget === document.documentElement) {
        isDragging.value = false
    }
}

const handleGlobalDragEnd = () => {
    isDragging.value = false
}

const handleOptionChange = (value: string) => {
    if (value !== last_option.value) {
        selectedOption.value = null
        last_option.value = value
    }
}

const handleClick = () => {
    fileInput.value?.click()
}

const getEntities = async (entityType: 'pipelines' | 'models', project_id: string) => {
    const pageSize = 50
    let page = 0
    let entitiesList: any[] = []
    let response

    do {
        // @ts-ignore
        response = await window.dl[entityType].query({
            filter: { $and: [{ projectId: project_id }] },
            page,
            pageSize,
            resource: entityType
        })

        entitiesList.push(...response.items)
        page++
    } while (response.totalItemsCount > entitiesList.length)

    return entitiesList
}

// Usage
const fetchData = async (project_id: string) => {
    const [pipelines, models] = await Promise.all([
        getEntities('pipelines', project_id),
        getEntities('models', project_id)
    ])

    pipeline_options.value = pipelines
        .filter((pipeline) => pipeline.status === 'Installed')
        .map((pipeline) => ({
            label: pipeline.name,
            value: pipeline.id
        }))

    model_options.value = models
        .filter((model) => model.status === 'deployed')
        .map((model) => ({
            label: model.name,
            value: model.id
        }))
}

const sendMessage = async () => {
    if (!userQuestion.value || askDisabled.value || isProcessing.value) return

    // Check if a pipeline or model is selected
    if (!selectedOption.value) {
        alertType.value = 'warning'
        showAlert.value = true
        setTimeout(() => {
            showAlert.value = false
        }, 5000)
        return
    }

    askDisabled.value = true
    statusMessage.value = ''
    const userQuestionValue = userQuestion.value
    userQuestion.value = ''
    nextTick(() => autoResize())

    // Create message with image if present
    const userMessage = {
        text: userQuestionValue,
        sender: 'user',
        image: selectedImage.value ? imagePreview.value : null
    }

    messages.value.push(userMessage)
    scrollToBottom()

    try {
        messages.value.push({
            text: '',
            sender: 'bot'
        })

        const formData = new FormData()
        formData.append('message', userQuestionValue)
        formData.append('session_id', sessionId.value)
        formData.append('project_id', project_id.value)
        formData.append('stream_type', choosed_option.value === 'Pipeline' ? 'pipeline' : 'model')
        formData.append('value_id', selectedOption.value.value)
        formData.append('use_llm_trace', useLlmTrace.value.toString())
        if (selectedImage.value) {
            const MAX_FILE_SIZE = 50 * 1024 * 1024
            if (selectedImage.value.size > MAX_FILE_SIZE) {
                throw new Error('File size exceeds 50MB limit')
            }
            formData.append('file', selectedImage.value)
        }
        // const payload = {
        //     file: selectedImage.value,
        //     path: '/assets/images/' + selectedImage.value.name,
        //     datasetId: '67a1c312afc4c79bd072241a',
        //     overwrite: true,
        //     binaries: false
        // }

        // const item = await window.dl.items.create(payload, { timeout: 10000 })

        // console.log(item)

        deleteImage()

        const response = await fetch('/start-stream', {
            method: 'POST',
            body: formData,
            headers: {
                Accept: 'application/json'
            }
        })

        if (!response.ok) {
            const errorData = await response.json()
            throw new Error(errorData.detail || errorData.error || 'Failed to create Prompt')
        }

        // const { session_id_response } = await response.json()

        // read the response
        const data = await response.json()
        const params = new URLSearchParams({
            project_id: project_id.value,
            value_id: selectedOption.value.value,
            item_id: data.item_id,
            stream_type: choosed_option.value === 'Pipeline' ? 'pipeline' : 'model',
            execution_id: data.execution_id
        })
        const eventSource = new EventSource(`/stream?${params.toString()}`)
        eventSourceRef.value = eventSource

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data)

                switch (data.type) {
                    case 'status':
                        statusMessage.value = data.text
                        break
                    case 'system':
                        messageQueue.value.push(data.text)
                        processQueue()
                        break
                    case 'done':
                        eventSource.close()
                        askDisabled.value = false
                        break
                    case 'error':
                        messages.value[messages.value.length - 1].text = data.text
                        eventSource.close()
                        askDisabled.value = false
                        break
                }
            } catch (parseError) {
                console.error('Failed to parse message:', parseError)
                messages.value[messages.value.length - 1].text = 'Error: Invalid response format'
                eventSource.close()
                askDisabled.value = false
            }
        }

        eventSource.onerror = (error) => {
            console.error('Stream error:', error)
            if (messages.value[messages.value.length - 1].text === '') {
                messages.value[messages.value.length - 1].text = 'Error: Failed to get response'
            }
            eventSource.close()
            askDisabled.value = false
        }
    } catch (error) {
        console.error('Error:', error)
        messages.value[messages.value.length - 1].text = `Error: ${error.message}`
        askDisabled.value = false
    }
}
const restartChat = () => {
    // Close event source if active
    if (eventSourceRef.value) {
        eventSourceRef.value.close()
        eventSourceRef.value = null
    }

    // Clear typing interval if active
    if (currentTypingInterval.value) {
        clearInterval(currentTypingInterval.value)
        currentTypingInterval.value = null
    }

    // Reset all state variables
    messages.value = []
    sessionId.value = Math.random().toString(36).substring(2, 32)
    userQuestion.value = ''
    statusMessage.value = ''
    messageQueue.value = []
    isProcessing.value = false
    askDisabled.value = false
    showAlert.value = false
    deleteImage()
}

const processQueue = () => {
    if (messageQueue.value.length === 0 || isProcessing.value) return

    isProcessing.value = true
    const message = messageQueue.value.shift() // Get the next message
    const messageIndex = messages.value.length - 1 // Index of the last bot message
    let currentText = messages.value[messageIndex]?.text || '' // Use the existing message as the starting point
    let index = currentText.length // Start appending from where the current message ends

    // Clear any existing interval
    if (currentTypingInterval.value !== null) {
        clearInterval(currentTypingInterval.value)
    }

    // Set up the new interval directly to the ref
    currentTypingInterval.value = setInterval(() => {
        if (index < message.length) {
            // Append one character at a time from the new portion
            currentText += message[index]
            messages.value[messageIndex].text = currentText // Update the message in the UI
            scrollToBottom()
            index++
        } else {
            // Typing is complete
            clearInterval(currentTypingInterval.value!)
            currentTypingInterval.value = null
            isProcessing.value = false
            processQueue() // Process the next message in the queue
        }
    }, 25) // Adjust typing speed here
}

const scrollToBottom = () => {
    nextTick(() => {
        const chatContainer = document.querySelector('.first-div')
        chatContainer?.scrollTo(0, chatContainer.scrollHeight)
    })
}

const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault()
        sendMessage()
    }
}

const autoResize = () => {
    nextTick(() => {
        const element = textarea.value?.$refs.textarea
        if (element) {
            element.style.height = '50px'
            element.style.height = `${element.scrollHeight}px`
        }
    })
}

const toggleTheme = () => {
    currentTheme.value = currentTheme.value === ThemeType.DARK ? ThemeType.LIGHT : ThemeType.DARK
}

const deleteImage = () => {
    selectedImage.value = null
    imagePreview.value = ''
    if (fileInput.value) {
        fileInput.value.value = ''
    }
}

const handleFileUpload = (event: Event) => {
    const target = event.target as HTMLInputElement
    if (target.files && target.files.length > 0) {
        const file = target.files[0]

        // Check if file is an image
        if (!file.type.startsWith('image/')) {
            // Show error message for non-image files
            alertMessage.value = 'Only image files are supported.'
            alertType.value = 'error'
            showAlert.value = true
            setTimeout(() => {
                showAlert.value = false
            }, 5000)

            // Reset the file input
            if (fileInput.value) {
                fileInput.value.value = ''
            }
            return
        }

        selectedImage.value = file
        const reader = new FileReader()
        reader.onload = (e) => {
            if (e.target?.result) {
                imagePreview.value = e.target.result as string
            }
        }
        reader.readAsDataURL(file)
    }
}

const handleDragOver = (event: DragEvent) => {
    event.preventDefault()
    isDragging.value = true
}

const handleDragLeave = (event: DragEvent) => {
    event.preventDefault()

    // Check if the drag leave event is leaving the container
    // by checking if the related target is not within the container
    const container = event.currentTarget as HTMLElement
    const relatedTarget = event.relatedTarget as Node

    if (!relatedTarget || !container.contains(relatedTarget)) {
        isDragging.value = false
    }
}

const handleDrop = (event: DragEvent) => {
    event.preventDefault()
    isDragging.value = false
    processDroppedFile(event)
}

const handleGlobalDrop = (event: DragEvent) => {
    event.preventDefault()
    isDragging.value = false

    // Only process if we're dropping on the document (not on our chat container)
    if (event.target && !isElementInChatContainer(event.target as Node)) {
        processDroppedFile(event)
    }
}

// Helper to check if an element is within our chat container
const isElementInChatContainer = (element: Node): boolean => {
    const chatContainer = document.querySelector('.chat-container')
    return chatContainer ? chatContainer.contains(element) : false
}

// Common function to process dropped files
const processDroppedFile = (event: DragEvent) => {
    if (!event.dataTransfer?.files.length) return

    const file = event.dataTransfer.files[0]

    // Check if file is an image
    if (!file.type.startsWith('image/')) {
        // Show error message for non-image files
        alertMessage.value = 'Only image files are supported.'
        alertType.value = 'error'
        showAlert.value = true
        setTimeout(() => {
            showAlert.value = false
        }, 5000)
        return
    }

    // Use the existing file handling logic
    selectedImage.value = file
    const reader = new FileReader()
    reader.onload = (e) => {
        if (e.target?.result) {
            imagePreview.value = e.target.result as string
        }
    }
    reader.readAsDataURL(file)
}
</script>

<style scoped>
.main-background {
    background-color: var(--dell-white);
}

.top-bar {
    height: 50px;
    padding: 0 1rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background-color: var(--dell-white);
    border-bottom: 1px solid var(--dell-gray-300);
}

.loading-spinner {
    display: grid;
    place-items: center;
    height: 100vh;
}

.chat-container {
    display: flex;
    flex-direction: column;
    height: 100vh;
    max-width: 48rem;
    margin: 0 auto;
    width: 100%;
    position: relative;
}

.first-div {
    flex: 1; /* Takes the remaining space */
    overflow-y: auto;
}

.second-div {
    position: relative;
    flex: 0;
    padding-top: 1rem;
    padding-bottom: 1rem;
}

.single-massage {
    display: flex; /* Enables Flexbox layout */
    justify-content: flex-start; /* Aligns items to the start */
    padding: 0.2rem 0 0.2rem 0;
}

.massage-item {
    margin-right: 0.5rem;
    margin-left: 0.5rem;
    margin-bottom: 1rem;
    white-space: pre-wrap;
}

.bot-message {
    max-width: calc(100% - 4rem); /* Maximum width is 100% minus 2rem */
    word-wrap: break-word; /* Ensures text wraps */ /* Adjust as needed */
}

.chat-bubble {
    background-color: var(--dell-gray-100);
    border-radius: 20px; /* Rounded edges */
    padding: 10px 20px; /* Top and bottom padding of 10px, left and right padding of 20px */
    margin: 0 0.5rem 0 0; /* Top and bottom margin of 10px, left margin auto, right margin 0 */
    word-wrap: break-word; /* Ensures text breaks to avoid horizontal scrolling */
    box-shadow: var(--dl-date-picker-shadow); /* Optional: adds shadow for 3D effect */
    display: block; /* Ensures it behaves like a block element */
}

.user-message {
    max-width: 75%;
    margin-left: auto;
    margin-top: 0.5rem;
    white-space: pre-wrap;
}

.questionField {
    white-space: pre-wrap;
}

.pulse {
    display: inline-block;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    animation: pulse 1.5s infinite;
}

@keyframes pulse {
    0% {
        transform: scale(1);
        opacity: 1;
    }
    50% {
        transform: scale(1.5);
        opacity: 0.5;
    }
    100% {
        transform: scale(1);
        opacity: 1;
    }
}

.dots {
    display: inline-block;
    font-size: 24px;
    margin-top: -15px;
}

.status-message {
    display: flex;
    align-items: center; /* Vertically center the items */
    margin-top: 7px;
}

.inline-spinner {
    margin-left: 5px; /* Add some space between the text and the spinner */
}
.bot-text {
    margin-top: 7px;
    white-space: normal;
}

.auto-expand {
    resize: none;
    overflow-y: hidden;
    height: auto;
}

.textarea-wrapper {
    background-color: var(--dell-gray-100);
    padding: 10px;
    border-radius: 8px;
    margin: 0 1rem;
    display: flex;
    flex-direction: column;
}

.textarea-actions {
    display: flex;
    justify-content: space-between;
    margin-top: 10px;
    gap: 8px;
}

.borderless-textarea :deep(textarea) {
    border: none !important;
    background: transparent !important;
    padding: 0 !important;
}

.send-button :deep(button),
.action-button :deep(button) {
    width: 26px !important;
    height: 26px !important;
    border: 1px solid var(--dell-gray-300) !important;
}

.restart-button :deep(button) {
    width: 26px !important;
    height: 26px !important;
    border: 1px solid var(--dell-gray-300) !important;
}

.theme-toggle {
    top: 1rem;
    right: 1rem;
    z-index: 1000;
}

.theme-button {
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    padding: 0.5rem;
    border-radius: 50%;
}

.image-preview {
    position: relative;
    display: inline-block;
    margin-bottom: 10px;
    border-radius: 4px;
    overflow: visible;
    width: 50px;
    height: 50px;
}

.user-image {
    display: block;
    max-width: calc(100% - 8px);
    max-height: 12rem;
    object-fit: cover;
    border-radius: 4px;
    margin-bottom: 0.25rem;
    margin-right: 8px;
    margin-left: auto;
}

.preview-thumbnail {
    width: 50px;
    height: 50px;
    object-fit: cover;
    border-radius: 4px;
    display: block;
}

.delete-button {
    position: absolute !important;
    top: -11px;
    right: -5px;
    z-index: 1;
}

.choose-option {
    margin-right: 1rem;
}

.delete-button :deep(button) {
    width: 12px !important;
    height: 12px !important;
    min-width: 12px !important;
    min-height: 12px !important;
    border: 1px solid var(--dell-blue-600) !important;
    background-color: var(--dell-gray-900) !important;
    color: var(--dell-white) !important;
    opacity: 1 !important;
}

[data-theme='dark-mode'] .delete-button :deep(button) {
    background-color: var(--dell-white) !important;
    color: var(--dell-gray-900) !important;
}

.chat-alert {
    position: absolute;
    bottom: calc(100% - 13px); /* Position 5px above the text area */
    left: 50%;
    transform: translateX(-50%);
    width: calc(100% - 32px) !important;
    max-width: 46rem;
    z-index: 100;
}

.select-group {
    display: flex;
    width: 60%;
}

.top-bar-actions {
    display: flex;
    align-items: center;
    gap: 12px;
}

.llm-trace-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
}

.drop-zone-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(var(--dell-gray-800-rgb), 0.7);
    z-index: 1001; /* Higher than global overlay */
    display: flex;
    justify-content: center;
    align-items: center;
    pointer-events: none;
    animation: fadeIn 0.2s ease-in-out;
}

.drop-zone-content {
    background-color: var(--dell-gray-100);
    border-radius: 8px;
    padding: 2rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    box-shadow: var(--dl-date-picker-shadow);
    animation: scaleIn 0.3s ease-in-out;
    position: relative;
    overflow: hidden;
}

.drop-zone-border {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    border: 2px dashed var(--dell-gray-100);
    border-radius: 6px;
    pointer-events: none;
    animation: pulse 2s infinite;
}

@keyframes fadeIn {
    from {
        opacity: 0;
    }
    to {
        opacity: 1;
    }
}

@keyframes scaleIn {
    from {
        transform: scale(0.95);
    }
    to {
        transform: scale(1);
    }
}

.global-drop-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.2);
    backdrop-filter: blur(1px);
    z-index: 999; /* Lower than the drop zone overlay */
    pointer-events: none;
    animation: fadeIn 0.2s ease-in-out;
}

.drop-zone-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(var(--dell-gray-800-rgb), 0.7);
    z-index: 1001; /* Higher than global overlay */
    display: flex;
    justify-content: center;
    align-items: center;
    pointer-events: none;
    animation: fadeIn 0.2s ease-in-out;
}
</style>

<style>
.row {
    --bs-gutter-x: 0rem;
}
</style>
