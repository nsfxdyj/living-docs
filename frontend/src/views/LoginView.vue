<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function onSubmit() {
  error.value = ''
  busy.value = true
  try {
    await auth.login(email.value, password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.push(redirect)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Login failed'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="login">
    <h1>Log in to Living Docs</h1>
    <form @submit.prevent="onSubmit">
      <label>
        Email
        <input v-model="email" type="email" name="email" required />
      </label>
      <label>
        Password
        <input v-model="password" type="password" name="password" required />
      </label>
      <p v-if="error" class="error">{{ error }}</p>
      <button type="submit" :disabled="busy">{{ busy ? 'Logging in…' : 'Log in' }}</button>
    </form>
    <p class="hint">
      No account yet? <router-link to="/register">Register</router-link>
    </p>
  </main>
</template>

<style scoped>
.login {
  max-width: 20rem;
  margin: 4rem auto;
  font-family: system-ui, sans-serif;
}

form {
  display: grid;
  gap: 1rem;
}

label {
  display: grid;
  gap: 0.25rem;
}

input {
  padding: 0.4rem 0.5rem;
  border: 1px solid #bbb;
  border-radius: 4px;
}

button {
  padding: 0.5rem;
  cursor: pointer;
}

.error {
  color: #b00020;
  margin: 0;
}

.hint {
  margin-top: 1rem;
}
</style>
