import client from './client'
import type { DashboardResponse } from '../types/api'

export async function getDashboard(): Promise<DashboardResponse> {
  const res = await client.get<DashboardResponse>('/dashboard')
  return res.data
}
