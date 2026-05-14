import client from './client'
import type { TokenResponse, UserProfile, UserUpdate } from '../types/api'

export async function login(email: string, password: string): Promise<TokenResponse> {
  const params = new URLSearchParams()
  params.append('username', email)
  params.append('password', password)
  const res = await client.post<TokenResponse>('/auth/token', params, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return res.data
}

export async function getMe(): Promise<UserProfile> {
  const res = await client.get<UserProfile>('/auth/me')
  return res.data
}

export async function updateMe(payload: UserUpdate): Promise<UserProfile> {
  const res = await client.patch<UserProfile>('/auth/me', payload)
  return res.data
}
