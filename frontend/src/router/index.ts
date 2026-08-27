import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import JoinView from '../views/JoinView.vue'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import { getToken } from '../api/client'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/login', name: 'login', component: LoginView },
    { path: '/register', name: 'register', component: RegisterView },
    { path: '/join/:token', name: 'join', component: JoinView },
  ],
})

const PUBLIC_ROUTES = new Set(['login', 'register'])

router.beforeEach((to) => {
  const loggedIn = getToken() !== null
  if (!loggedIn && !PUBLIC_ROUTES.has(to.name as string)) {
    // Keep the target so the user lands back here after logging in.
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (loggedIn && PUBLIC_ROUTES.has(to.name as string)) {
    return { name: 'home' }
  }
})
