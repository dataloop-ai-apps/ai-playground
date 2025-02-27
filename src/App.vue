<template>
    <DlThemeProvider :is-dark="isDark" class="main-background">
        <div v-if="!isReady" class="loading-spinner">
            <dl-spinner type="clock" text="Loading..." />
        </div>
        <div v-if="isReady" class="chat-container">
            <div class="top-bar">
                <dl-select
                    class="choose-option"
                    v-model="choosed_option"
                    :options="choose_options"
                    size="m"
                    width="30%"
                    @change="handleOptionChange"
                />
                <dl-select
                    v-if="choosed_option === 'Pipeline'"
                    v-model="selectedOption"
                    :options="pipeline_options"
                    placeholder="Choose a pipeline"
                    size="m"
                    width="30%"
                />

                <dl-select
                    v-if="choosed_option === 'Model'"
                    v-model="selectedOption"
                    :options="model_options"
                    placeholder="Choose a model"
                    size="m"
                    width="30%"
                />

                <!-- <div class="theme-toggle">
                    <button @click="toggleTheme" class="theme-button">
                        {{ isDark ? '☀️' : '🌙' }}
                    </button>
                </div> -->
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
                            icon="dataloop-logo"
                            :svgSource="'assets'"
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
                            <div v-else class="dots"><span>.</span><span>.</span><span>.</span></div>
                        </dl-typography>
                        <div v-else class="user-message">
                            <img v-if="message.image" :src="message.image" alt="Message Image" class="user-image" />
                            <dl-typography color="textPrimary" class="chat-bubble">{{ message.text }}</dl-typography>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Second Div: Adjusts to the height of its content -->
            <div class="second-div">
                <dl-alert v-if="showAlert" type="warning" class="chat-alert" :fluid="true">
                    Please select a <strong>{{ choosed_option }}</strong> from the dropdown.
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
                            hover-bg-color="var(--dl-color-darker)"
                            hover-text-color="var(--dl-color-bg)"
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
                            hover-bg-color="var(--dl-color-fill-hover)"
                            color="var(--dl-color-fill-secondary)"
                            text-color="var(--dl-color-darker)"
                            hover-text-color="var(--dl-color-darker)"
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
                            hover-bg-color="var(--dl-color-fill-hover)"
                            color="var(--dl-color-fill-secondary)"
                            text-color="var(--dl-color-darker)"
                            hover-text-color="var(--dl-color-darker)"
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
    DlAlert
} from '@dataloop-ai/components'
import { DlEvent, DlFrameEvent, SDKPipeline, ThemeType } from '@dataloop-ai/jssdk'
import { ref, onMounted, computed, nextTick } from 'vue-demi'
import BotTextDark from './components/BotTextDark.vue'
import BotTextLight from './components/BotTextLight.vue'

const messageQueue = ref<string[]>([])
const isProcessing = ref<boolean>(false)
const isReady = ref<boolean>(false)
const currentTheme = ref<ThemeType>(ThemeType.DARK)
const userQuestion = ref<string>('')
const currentUser = ref<string>('')
const messages = ref<Array<{ text: string; sender: string; image?: string }>>([])
const askDisabled = ref<boolean>(false)
const sessionId = ref<string>('')

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
})

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
        showAlert.value = true
        setTimeout(() => {
            showAlert.value = false
        }, 5000)
        return
    }

    askDisabled.value = true
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
            throw new Error(errorData.detail || errorData.error || 'Failed to upload file')
        }

        // const { session_id_response } = await response.json()

        // read the response
        const data = await response.json()
        const params = new URLSearchParams({
            project_id: project_id.value,
            value_id: selectedOption.value.value,
            item_id: data.item_id,
            stream_type: choosed_option.value === 'Pipeline' ? 'pipeline' : 'model'
        })
        const eventSource = new EventSource(`/stream?${params.toString()}`)

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data)

                switch (data.type) {
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

const processQueue = () => {
    if (messageQueue.value.length === 0 || isProcessing.value) return

    isProcessing.value = true
    const message = messageQueue.value.shift() // Get the next message
    const messageIndex = messages.value.length - 1 // Index of the last bot message
    let currentText = messages.value[messageIndex]?.text || '' // Use the existing message as the starting point
    let index = currentText.length // Start appending from where the current message ends

    const typingInterval = setInterval(() => {
        if (index < message.length) {
            // Append one character at a time from the new portion
            currentText += message[index]
            messages.value[messageIndex].text = currentText // Update the message in the UI
            scrollToBottom()
            index++
        } else {
            // Typing is complete
            clearInterval(typingInterval)
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
        selectedImage.value = target.files[0]
        const reader = new FileReader()
        reader.onload = (e) => {
            if (e.target?.result) {
                imagePreview.value = e.target.result as string
            }
        }
        reader.readAsDataURL(target.files[0])
    }
}
</script>

<style scoped>
.main-background {
    background-color: var(--dl-color-component);
}

.top-bar {
    height: 50px;
    padding: 0 1rem;
    display: flex;
    align-items: center;
    background-color: var(--dl-color-component);
    border-bottom: 1px solid var(--dl-color-separator);
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
    background-color: var(--dl-color-fill-secondary);
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
    margin-top: -7px;
}

.dots span {
    animation: blink 1.2s infinite;
    animation-delay: calc(0.4s * var(--i));
    opacity: 0;
}

.dots span:nth-child(1) {
    --i: 0;
}

.dots span:nth-child(2) {
    --i: 1;
}

.dots span:nth-child(3) {
    --i: 2;
}

.bot-text {
    margin-top: 7px;
    white-space: normal;
}

@keyframes blink {
    0%,
    20% {
        opacity: 0;
    }
    40% {
        opacity: 1;
    }
    100% {
        opacity: 0;
    }
}

.auto-expand {
    resize: none;
    overflow-y: hidden;
    height: auto;
}

.textarea-wrapper {
    background-color: var(--dl-color-fill-secondary);
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
    border: 1px solid var(--dl-color-separator) !important;
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
    border: 1px solid var(--dl-color-fill-hover) !important;
    background-color: var(--dl-color-black) !important;
    color: var(--dl-color-white) !important;
    opacity: 1 !important;
}

[data-theme='dark-mode'] .delete-button :deep(button) {
    background-color: var(--dl-color-white) !important;
    color: var(--dl-color-black) !important;
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
</style>

<style>
.row {
    --bs-gutter-x: 0rem;
}
</style>
