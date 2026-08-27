<script setup lang="ts">
import { ref } from 'vue'

// M1: static UI only — real authentication arrives in milestone M2.
const email = ref('')
const password = ref('')

function onSubmit() {
  console.log('login submit (stub):', { email: email.value })
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
      <button type="submit">Log in</button>
    </form>
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
</style>
