<template>
    <DlThemeProvider :is-dark="isDark" class="main-background">
        <div v-if="!isReady" class="loading-spinner">
            <dl-spinner type="grid" text="Loading..." />
        </div>
        <div class="chat-container">
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
                            <vue-markdown-it class="bot-text" v-if="message.text !== ''" :source="message.text" />
                            <div v-else class="dots"><span>.</span><span>.</span><span>.</span></div>
                        </dl-typography>
                        <dl-typography v-else color="textPrimary" class="chat-bubble massage-item">{{
                            message.text
                        }}</dl-typography>
                    </div>
                </div>
            </div>

            <!-- Second Div: Adjusts to the height of its content -->
            <div class="second-div">
                <dl-input
                    class="questionField"
                    margin="0 1rem 0 1rem"
                    v-model="userQuestion"
                    placeholder="Ask Dataloop AI"
                    @enter="sendMessage"
                    hideClearButton
                    expandable
                >
                    <template #append>
                        <dl-button
                            dense
                            round
                            filled
                            icon="icon-dl-arrow-up"
                            size="m"
                            :disabled="!userQuestion"
                            @click="sendMessage"
                        />
                    </template>
                </dl-input>
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
    DlAvatar
} from '@dataloop-ai/components'
import { DlEvent, DlFrameEvent, ThemeType } from '@dataloop-ai/jssdk'
import { ref, onMounted, computed, nextTick } from 'vue-demi'
import VueMarkdownIt from 'vue3-markdown-it'
import 'highlight.js/styles/atom-one-dark.css'

const messageQueue = ref<string[]>([])
const isProcessing = ref<boolean>(false)
const isReady = ref<boolean>(true)
const currentTheme = ref<ThemeType>(ThemeType.DARK)
const userQuestion = ref<string>('')
const currentUser = ref<string>('')
const messages = ref<Array<{ text: string; sender: string }>>([])
const askDisabled = ref<boolean>(false)
const sessionId = ref<string>('')
const pipelineId = ref<string>('')
const isDark = computed<boolean>(() => {
    return currentTheme.value === ThemeType.DARK
})

onMounted(() => {
    // Extract pipelineID from the URL query parameters
    const urlParams = new URLSearchParams(window.location.search)
    pipelineId.value = urlParams.get('pipeline') || ''

    // window.dl.on(DlEvent.READY, async () => {
    //     const settings = await window.dl.settings.get()
    //     currentUser.value = settings.currentUser

    //     messages.value.push({
    //         text: `Hi ${currentUser.value},\nhow can we help you?`,
    //         sender: 'bot'
    //     })

    //     // @ts-ignore
    //     currentTheme.value = settings.theme
    //     window.dl.on(DlEvent.THEME, (data) => {
    //         currentTheme.value = data
    //     })
    //     isReady.value = true
    //     console.log('ready')
    // })
    // generate a random session id with 30 characters
    sessionId.value = Math.random().toString(36).substring(2, 32)

    isReady.value = true
})

const sendMessage = async () => {
    if (!userQuestion.value || askDisabled.value || isProcessing.value) return
    askDisabled.value = true

    messages.value.push({ text: userQuestion.value, sender: 'user' })
    scrollToBottom()

    try {
        messages.value.push({
            text: '',
            sender: 'bot'
        })
        // // First POST the message and get a session ID
        // const response = await fetch('/start-stream', {
        //     method: 'POST',
        //     headers: {
        //         'Content-Type': 'application/json'
        //     },
        //     body: JSON.stringify({
        //         message: userQuestion.value,
        //         session_id: sessionId.value
        //     })
        // })

        // if (!response.ok) {
        //     throw new Error('Failed to start stream')
        // }

        // const { session_id_response } = await response.json()

        console.log(messages.value.length)
        const params = new URLSearchParams({
            session_id: sessionId.value,
            question: userQuestion.value,
            pipeline_id: pipelineId.value,
            messages_count: messages.value.length.toString()
        })
        const eventSource = new EventSource(`/stream?${params.toString()}`)

        userQuestion.value = '' // Clear input after creating EventSource

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
        messages.value[messages.value.length - 1].text = 'Error: Failed to get response'
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
</script>

<style scoped>
.main-background {
    background-color: var(--dl-color-component);
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
}

.first-div {
    flex: 1; /* Takes the remaining space */
    overflow-y: auto;
}
/* flex in r */

.second-div {
    flex: 0;
    padding-top: 1rem;
    padding-bottom: 1rem;
}

.single-massage {
    display: flex; /* Enables Flexbox layout */
    justify-content: flex-start; /* Aligns items to the start */
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
    max-width: 75%; /* Maximum width is 75% of its container */
    background-color: var(--dl-color-fill-secondary);
    border-radius: 20px; /* Rounded edges */
    padding: 10px 20px; /* Top and bottom padding of 10px, left and right padding of 20px */
    margin: 10px 0.5rem 10px auto; /* Top and bottom margin of 10px, left margin auto, right margin 0 */
    word-wrap: break-word; /* Ensures text breaks to avoid horizontal scrolling */
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1); /* Optional: adds shadow for 3D effect */
    display: block; /* Ensures it behaves like a block element */
}

.message-group {
    margin-top: 1rem;
}
.questionField {
    white-space: pre-wrap;
}

.pulse {
    display: inline-block;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background-color: #3498db;
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
</style>

<style>
.row {
    --bs-gutter-x: 0rem;
}
</style>
