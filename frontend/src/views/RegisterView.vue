<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const email = ref('')
const password = ref('')
const displayName = ref('')
const error = ref('')
const busy = ref(false)

async function onSubmit() {
  error.value = ''
  busy.value = true
  try {
    await auth.register(email.value, password.value, displayName.value)
    router.push('/')
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Registration failed'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="register">
    <h1>Create your account</h1>
    <form @submit.prevent="onSubmit">
      <label>
        Display name
        <input v-model="displayName" type="text" name="display_name" required />
      </label>
      <label>
        Email
        <input v-model="email" type="email" name="email" required />
      </label>
      <label>
        Password (min. 8 characters)
        <input
          v-model="password"
          type="password"
          name="password"
          minlength="8"
          required
        />
      </label>
      <p v-if="error" class="error">{{ error }}</p>
      <button type="submit" :disabled="busy">
        {{ busy ? 'Creating account…' : 'Register' }}
      </button>
    </form>
    <p class="hint">
      Already have an account? <router-link to="/login">Log in</router-link>
    </p>
  </main>
</template>

<style scoped>
.register {
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
