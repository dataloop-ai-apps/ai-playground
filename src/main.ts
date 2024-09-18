import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import globals from './globals'
import { initializeFrameDriver, xFrameDriver } from '@dataloop-ai/jssdk'

declare global {
    interface Window {
        dl: xFrameDriver
    }
}

initializeFrameDriver().then(() => {
    createApp(App).use(globals).mount('#app')
})

