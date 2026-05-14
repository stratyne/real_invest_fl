import client from './client'
import type { CountyResponse } from '../types/api'

export async function listCounties(): Promise<CountyResponse[]> {
  const res = await client.get<CountyResponse[]>('/counties')
  return res.data
}
