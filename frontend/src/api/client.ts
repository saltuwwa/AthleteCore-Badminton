import axios from 'axios'

/** Пустой baseURL в dev — запросы идут через Vite proxy (см. vite.config.ts). */
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 120_000,
})
