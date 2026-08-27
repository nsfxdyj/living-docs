import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import { router } from './router'
import './assets/motion.css'

// Gates the `.reveal` initial hidden state: without JS, content stays visible.
document.documentElement.classList.add('js')

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
