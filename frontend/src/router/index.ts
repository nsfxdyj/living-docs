import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import JoinView from '../views/JoinView.vue'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import WorkspaceView from '../views/WorkspaceView.vue'
import GardenView from '../views/GardenView.vue'
import DocumentEditView from '../views/DocumentEditView.vue'
import DocumentView from '../views/DocumentView.vue'
import { getToken } from '../api/client'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/login', name: 'login', component: LoginView },
    { path: '/register', name: 'register', component: RegisterView },
    { path: '/join/:token', name: 'join', component: JoinView },
    { path: '/w/:id', name: 'workspace', component: WorkspaceView },
    { path: '/w/:id/garden', name: 'garden', component: GardenView },
    { path: '/w/:id/docs/new', name: 'doc-new', component: DocumentEditView },
    { path: '/docs/:id', name: 'doc-view', component: DocumentView },
    { path: '/docs/:id/edit', name: 'doc-edit', component: DocumentEditView },
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
