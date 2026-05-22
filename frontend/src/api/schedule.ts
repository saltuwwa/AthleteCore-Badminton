import { apiClient } from './client'

export const getSchedule = async () => {
  const { data } = await apiClient.get('/api/schedule')
  return data
}

export const confirmSchedule = async (scheduleId: string) => {
  const { data } = await apiClient.post(`/api/schedule/${scheduleId}/confirm`)
  return data
}
